from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Job, JobStatus, JobSummary, Transaction
from app.services.anomaly_detector import detect_anomalies
from app.services.csv_validator import read_csv_rows
from app.services.llm_client import apply_llm_classification
from app.services.report_builder import build_summary
from app.services.transaction_cleaner import clean_rows
from app.tasks.celery_app import celery_app


@celery_app.task(name="process_job")
def process_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        _process_job(db, job_id)
    finally:
        db.close()


def _process_job(db: Session, job_id: str) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return

    job.status = JobStatus.processing
    job.error_message = None
    db.commit()

    try:
        rows = read_csv_rows(Path(job.upload_path))
        transactions = clean_rows(rows)
        detect_anomalies(transactions)
        apply_llm_classification(transactions)
        summary_payload, summary_raw = build_summary(transactions)

        job.row_count_raw = len(rows)
        job.row_count_clean = len(transactions)
        job.transactions.clear()
        db.flush()

        db.add_all(
            [
                Transaction(
                    job_id=job.id,
                    txn_id=transaction.txn_id,
                    date=transaction.date,
                    merchant=transaction.merchant,
                    amount=transaction.amount,
                    currency=transaction.currency,
                    status=transaction.status,
                    category=transaction.category,
                    account_id=transaction.account_id,
                    notes=transaction.notes,
                    is_anomaly=transaction.is_anomaly,
                    anomaly_reason=transaction.anomaly_reason,
                    llm_category=transaction.llm_category,
                    llm_raw_response=transaction.llm_raw_response,
                    llm_failed=transaction.llm_failed,
                )
                for transaction in transactions
            ]
        )

        if job.summary:
            db.delete(job.summary)
            db.flush()

        db.add(
            JobSummary(
                job_id=job.id,
                total_spend_by_currency=summary_payload["total_spend_by_currency"],
                spend_by_category=summary_payload["spend_by_category"],
                top_merchants=summary_payload["top_merchants"],
                anomaly_count=summary_payload["anomaly_count"],
                narrative=summary_payload["narrative"],
                risk_level=summary_payload["risk_level"],
                llm_raw_response=summary_raw,
            )
        )
        job.status = JobStatus.completed
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.failed
        job.error_message = str(exc)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise
