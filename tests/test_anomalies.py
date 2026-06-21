from decimal import Decimal

from app.services.anomaly_detector import detect_anomalies
from app.services.transaction_cleaner import CleanedTransaction


def tx(amount: str, merchant: str = "Amazon", currency: str = "INR") -> CleanedTransaction:
    from datetime import date

    return CleanedTransaction(
        txn_id=None,
        date=date(2024, 1, 1),
        merchant=merchant,
        amount=Decimal(amount),
        currency=currency,
        status="SUCCESS",
        category="Shopping",
        account_id="ACC001",
        notes=None,
        original_category_missing=False,
    )


def test_detects_statistical_and_domestic_currency_anomalies() -> None:
    transactions = [tx("100"), tx("110"), tx("120"), tx("1000", merchant="Ola", currency="USD")]

    detect_anomalies(transactions)

    assert transactions[-1].is_anomaly is True
    assert "3x account median" in transactions[-1].anomaly_reason
    assert "domestic-only merchant" in transactions[-1].anomaly_reason
