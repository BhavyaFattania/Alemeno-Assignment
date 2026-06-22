import os
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


def _compute_llm_status(db: Session, job_id: str, llm_raw_response: str | None) -> str:
    """Derive LLM run status from persisted transaction data.

    Returns:
        'ok'       - LLM ran and classified at least one transaction successfully.
        'partial'  - LLM ran but some individual transactions still failed.
        'fallback' - LLM never ran (no API key or all calls failed).
    """
    from sqlalchemy import func

    total_needing_llm = db.scalar(
        select(func.count()).where(
            Transaction.job_id == job_id,
            Transaction.llm_failed == True,  # noqa: E712
        )
    ) or 0

    total_llm_succeeded = db.scalar(
        select(func.count()).where(
            Transaction.job_id == job_id,
            Transaction.llm_category.isnot(None),
        )
    ) or 0

    # llm_raw_response on the summary is None only when the LLM summary call itself failed
    summary_llm_ran = llm_raw_response is not None

    if total_llm_succeeded == 0 and not summary_llm_ran:
        return "fallback"
    if total_needing_llm > 0:
        return "partial"
    return "ok"



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

    # HuggingFace Spaces / single-container envs: no Redis or Celery worker available.
    # CELERY_SYNC_MODE=true bypasses Celery and runs the job synchronously in-process.
    # The API response is still 202 for interface compatibility, but by the time the
    # client polls /status the job will already be processing or completed.
    if os.getenv("CELERY_SYNC_MODE", "").lower() == "true":
        import threading
        from app.tasks.process_job import _process_job
        from app.core.database import SessionLocal

        def _run_sync(job_id: str) -> None:
            db = SessionLocal()
            try:
                _process_job(db, job_id)
            finally:
                db.close()

        threading.Thread(target=_run_sync, args=(job.id,), daemon=True).start()

    return UploadResponse(job_id=job.id, status=job.status)


@router.get("", response_model=list[JobListItem])
def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=50, ge=1, le=200, description="Max records to return"),
    db: Session = Depends(get_db),
) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc()).offset(skip).limit(limit)
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

    # Determine LLM status once the job is complete
    llm_status: str | None = None
    if job.status == JobStatus.completed and job.summary:
        llm_status = _compute_llm_status(db, job.id, job.summary.llm_raw_response)

    return JobStatusResponse(
        id=job.id,
        filename=job.filename,
        status=job.status,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        summary=summary,
        llm_status=llm_status,
    )



@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(
    job_id: str,
    skip: int = Query(default=0, ge=0, description="Number of transactions to skip"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max transactions to return"),
    db: Session = Depends(get_db),
) -> JobResultsResponse:
    job = db.scalar(select(Job).options(joinedload(Job.summary)).where(Job.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.completed or not job.summary:
        raise HTTPException(status_code=409, detail="Job results are not ready")

    transactions = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.job_id == job.id)
            .order_by(Transaction.id)
            .offset(skip)
            .limit(limit)
        ).all()
    )
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

    llm_status = _compute_llm_status(db, job.id, job.summary.llm_raw_response)

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
        llm_status=llm_status,
    )


