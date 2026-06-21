import shutil
from pathlib import Path

from app.core.database import SessionLocal, create_tables
from app.models import Job, JobStatus, Transaction
from app.tasks import process_job as process_job_module


def fake_classification(transactions):
    for transaction in transactions:
        if transaction.original_category_missing:
            transaction.category = "Food"
            transaction.llm_category = "Food"
            transaction.llm_raw_response = '{"classifications":[{"index":0,"category":"Food"}]}'


def fake_summary(transactions):
    return (
        {
            "total_spend_by_currency": {"INR": "22208.34", "USD": "91185.10"},
            "spend_by_category": {"Food": "11325.79", "Shopping": "10882.55", "Transport": "91185.10"},
            "top_merchants": [{"merchant": "Ola", "transaction_count": 1}],
            "anomaly_count": 1,
            "narrative": "The file contains concentrated transport spend and one anomaly. Review the USD Ola transaction before closing the job.",
            "risk_level": "high",
        },
        '{"risk_level":"high"}',
    )


def test_worker_processes_job_and_persists_results(monkeypatch, tmp_path) -> None:
    create_tables()
    monkeypatch.setattr(process_job_module, "apply_llm_classification", fake_classification)
    monkeypatch.setattr(process_job_module, "build_summary", fake_summary)

    upload_path = tmp_path / "transactions.csv"
    shutil.copyfile(Path("tests/fixtures/transactions.csv"), upload_path)

    db = SessionLocal()
    try:
        job = Job(filename="transactions.csv", upload_path=str(upload_path), row_count_raw=4)
        db.add(job)
        db.commit()
        db.refresh(job)

        process_job_module._process_job(db, job.id)

        db.refresh(job)
        transactions = db.query(Transaction).filter(Transaction.job_id == job.id).all()

        assert job.status == JobStatus.completed
        assert job.row_count_raw == 4
        assert job.row_count_clean == 3
        assert len(transactions) == 3
        assert job.summary is not None
        assert job.summary.anomaly_count == 1
        assert job.summary.risk_level == "high"
        assert any(transaction.llm_category == "Food" for transaction in transactions)
    finally:
        db.close()
