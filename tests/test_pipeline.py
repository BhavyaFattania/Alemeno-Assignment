from pathlib import Path

from app.services.anomaly_detector import detect_anomalies
from app.services.csv_validator import read_csv_rows, validate_csv_headers
from app.services.llm_client import apply_llm_classification
from app.services.report_builder import build_summary
from app.services.transaction_cleaner import clean_rows


class FakeLLMClient:
    def classify_transactions(self, transactions):
        return {0: "Food"}, '{"classifications":[{"index":0,"category":"Food"}]}'

    def summarize(self, transactions):
        return (
            {
                "total_spend_by_currency": {"INR": "22208.34", "USD": "91185.10"},
                "top_merchants": [{"merchant": "Swiggy", "transaction_count": 1}],
                "anomaly_count": 1,
                "narrative": "Spending is concentrated across shopping and transport. One high-risk transaction requires review.",
                "risk_level": "high",
            },
            '{"risk_level":"high"}',
        )


def test_pipeline_with_fake_llm() -> None:
    fixture = Path("tests/fixtures/transactions.csv")

    assert validate_csv_headers(fixture) == 4
    transactions = clean_rows(read_csv_rows(fixture))
    detect_anomalies(transactions)
    apply_llm_classification(transactions, FakeLLMClient())
    summary, raw = build_summary(transactions, FakeLLMClient())

    assert len(transactions) == 3
    assert any(transaction.llm_category == "Food" for transaction in transactions)
    assert summary["risk_level"] == "high"
    assert raw == '{"risk_level":"high"}'


def test_real_assignment_csv_cleaning_and_anomalies() -> None:
    fixture = Path("transactions.csv")

    rows = read_csv_rows(fixture)
    transactions = clean_rows(rows)
    detect_anomalies(transactions)

    assert validate_csv_headers(fixture) == 95
    assert len(transactions) == 85
    assert sum(transaction.is_anomaly for transaction in transactions) == 5
    assert sum(transaction.original_category_missing for transaction in transactions) == 13
