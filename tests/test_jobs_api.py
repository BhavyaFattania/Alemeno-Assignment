from pathlib import Path

from fastapi.testclient import TestClient

import app.api.routes.jobs as jobs_route
import app.tasks.process_job as process_job_module
from app.core.database import SessionLocal
from app.main import app


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


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_rejects_non_csv() -> None:
    with TestClient(app) as client:
        response = client.post("/jobs/upload", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 400


def test_upload_accepts_valid_csv_and_enqueues(monkeypatch) -> None:
    enqueued: list[str] = []
    monkeypatch.setattr(jobs_route.process_job, "delay", lambda job_id: enqueued.append(job_id))

    fixture = Path("tests/fixtures/transactions.csv")
    with TestClient(app) as client:
        with fixture.open("rb") as handle:
            response = client.post("/jobs/upload", files={"file": ("transactions.csv", handle, "text/csv")})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["job_id"] in enqueued


def test_upload_status_and_results_lifecycle(monkeypatch) -> None:
    monkeypatch.setattr(process_job_module, "apply_llm_classification", fake_classification)
    monkeypatch.setattr(process_job_module, "build_summary", fake_summary)

    def run_worker(job_id: str) -> None:
        db = SessionLocal()
        try:
            process_job_module._process_job(db, job_id)
        finally:
            db.close()

    monkeypatch.setattr(jobs_route.process_job, "delay", run_worker)

    fixture = Path("tests/fixtures/transactions.csv")
    with TestClient(app) as client:
        with fixture.open("rb") as handle:
            upload_response = client.post("/jobs/upload", files={"file": ("transactions.csv", handle, "text/csv")})

        assert upload_response.status_code == 202
        job_id = upload_response.json()["job_id"]

        status_response = client.get(f"/jobs/{job_id}/status")
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["status"] == "completed"
        assert status_body["summary"]["anomaly_count"] == 1

        results_response = client.get(f"/jobs/{job_id}/results")
        assert results_response.status_code == 200
        results_body = results_response.json()
        assert len(results_body["cleaned_transactions"]) == 3
        assert len(results_body["flagged_anomalies"]) == 1
        assert results_body["llm_summary"]["risk_level"] == "high"


def test_openapi_contains_jobs_routes() -> None:
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
    assert "/jobs/upload" in schema["paths"]
    assert "/jobs/{job_id}/status" in schema["paths"]
    assert "/jobs/{job_id}/results" in schema["paths"]
