from decimal import Decimal

from app.services.transaction_cleaner import UNCATEGORISED, clean_rows


def test_clean_rows_normalizes_dirty_fields_and_dedupes() -> None:
    rows = [
        {
            "txn_id": "TXN1",
            "date": "2024/02/05",
            "merchant": "Swiggy",
            "amount": "$11325.79",
            "currency": "inr",
            "status": "success",
            "category": "",
            "account_id": "ACC004",
            "notes": "",
        },
        {
            "txn_id": "TXN1",
            "date": "2024/02/05",
            "merchant": "Swiggy",
            "amount": "$11325.79",
            "currency": "inr",
            "status": "success",
            "category": "",
            "account_id": "ACC004",
            "notes": "",
        },
    ]

    cleaned = clean_rows(rows)

    assert len(cleaned) == 1
    assert cleaned[0].date.isoformat() == "2024-02-05"
    assert cleaned[0].amount == Decimal("11325.79")
    assert cleaned[0].currency == "INR"
    assert cleaned[0].status == "SUCCESS"
    assert cleaned[0].category == UNCATEGORISED
    assert cleaned[0].original_category_missing is True
