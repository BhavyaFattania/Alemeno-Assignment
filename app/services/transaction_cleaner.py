from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal, InvalidOperation


UNCATEGORISED = "Uncategorised"


@dataclass
class CleanedTransaction:
    txn_id: str | None
    date: date
    merchant: str
    amount: Decimal
    currency: str
    status: str
    category: str
    account_id: str
    notes: str | None
    original_category_missing: bool
    is_anomaly: bool = False
    anomaly_reason: str | None = None
    llm_category: str | None = None
    llm_raw_response: str | None = None
    llm_failed: bool = False


class CleaningError(ValueError):
    pass


def parse_date(value: str) -> date:
    raw = (value or "").strip()
    for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise CleaningError(f"Invalid date: {value!r}")


def parse_amount(value: str) -> Decimal:
    raw = (value or "").strip().replace("$", "").replace(",", "")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise CleaningError(f"Invalid amount: {value!r}") from None


def clean_rows(rows: list[dict[str, str]]) -> list[CleanedTransaction]:
    cleaned: list[CleanedTransaction] = []
    seen: set[tuple[tuple[str, str], ...]] = set()

    for row in rows:
        row_key = tuple(sorted((key, (value or "").strip()) for key, value in row.items()))
        if row_key in seen:
            continue
        seen.add(row_key)

        category = (row.get("category") or "").strip()
        category_missing = not category

        cleaned.append(
            CleanedTransaction(
                txn_id=(row.get("txn_id") or "").strip() or None,
                date=parse_date(row.get("date", "")),
                merchant=(row.get("merchant") or "").strip(),
                amount=parse_amount(row.get("amount", "")),
                currency=(row.get("currency") or "").strip().upper(),
                status=(row.get("status") or "").strip().upper(),
                category=category or UNCATEGORISED,
                account_id=(row.get("account_id") or "").strip(),
                notes=(row.get("notes") or "").strip() or None,
                original_category_missing=category_missing,
            )
        )

    return cleaned
