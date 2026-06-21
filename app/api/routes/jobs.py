import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.schemas.jobs import (
    AnomalyOut,
    FullSummaryOut,
    JobListItem,
    JobResultsResponse,
    JobStatusResponse,
    JobSummaryBrief,
    TransactionOut,
    UploadResponse,
)
from app.core.config import settings
from app.core.database import get_db
from app.models import Job, JobStatus, Transaction
from app.services.csv_validator import CSVValidationError, validate_csv_headers
from app.tasks.process_job import process_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_job(file: UploadFile = File(...), db: Session = Depends(get_db)) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv uploads are supported")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name
    temp_path = settings.upload_dir / f"pending_{uuid.uuid4()}_{safe_name}"
    with temp_path.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    try:
        raw_count = validate_csv_headers(temp_path)
    except CSVValidationError as exc:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = Job(filename=safe_name, upload_path=str(temp_path), row_count_raw=raw_count, status=JobStatus.pending)
    db.add(job)
    db.commit()
    db.refresh(job)

    final_path = settings.upload_dir / f"{job.id}_{safe_name}"
    temp_path.replace(final_path)
    job.upload_path = str(final_path)
    db.commit()

    process_job.delay(job.id)
    return UploadResponse(job_id=job.id, status=job.status)


@router.get("", response_model=list[JobListItem])
def list_jobs(status_filter: JobStatus | None = Query(default=None, alias="status"), db: Session = Depends(get_db)) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc())
    if status_filter:
        stmt = stmt.where(Job.status == status_filter)
    return list(db.scalars(stmt).all())


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = db.scalar(select(Job).options(joinedload(Job.summary)).where(Job.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    summary = None
    if job.summary:
        summary = JobSummaryBrief(
            row_count_raw=job.row_count_raw,
            row_count_clean=job.row_count_clean,
            anomaly_count=job.summary.anomaly_count,
            total_spend_by_currency=job.summary.total_spend_by_currency,
            risk_level=job.summary.risk_level,
        )

    return JobStatusResponse(
        id=job.id,
        filename=job.filename,
        status=job.status,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        summary=summary,
    )


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(job_id: str, db: Session = Depends(get_db)) -> JobResultsResponse:
    job = db.scalar(select(Job).options(joinedload(Job.summary)).where(Job.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.completed or not job.summary:
        raise HTTPException(status_code=409, detail="Job results are not ready")

    transactions = list(db.scalars(select(Transaction).where(Transaction.job_id == job.id).order_by(Transaction.id)).all())
    anomalies = [
        AnomalyOut(
            txn_id=transaction.txn_id,
            merchant=transaction.merchant,
            amount=transaction.amount,
            currency=transaction.currency,
            account_id=transaction.account_id,
            anomaly_reason=transaction.anomaly_reason or "",
        )
        for transaction in transactions
        if transaction.is_anomaly
    ]

    return JobResultsResponse(
        job_id=job.id,
        cleaned_transactions=[TransactionOut.model_validate(transaction) for transaction in transactions],
        flagged_anomalies=anomalies,
        per_category_spend=job.summary.spend_by_category,
        llm_summary=FullSummaryOut(
            total_spend_by_currency=job.summary.total_spend_by_currency,
            spend_by_category=job.summary.spend_by_category,
            top_merchants=job.summary.top_merchants,
            anomaly_count=job.summary.anomaly_count,
            narrative=job.summary.narrative,
            risk_level=job.summary.risk_level,
        ),
    )
