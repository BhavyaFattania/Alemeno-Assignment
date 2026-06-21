from collections import Counter, defaultdict
from decimal import Decimal

from app.services.transaction_cleaner import CleanedTransaction


def money_to_string(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def total_spend_by_currency(transactions: list[CleanedTransaction]) -> dict[str, str]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for transaction in transactions:
        if transaction.status != "FAILED":
            totals[transaction.currency] += transaction.amount
    return {currency: money_to_string(amount) for currency, amount in sorted(totals.items())}


def spend_by_category(transactions: list[CleanedTransaction]) -> dict[str, str]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for transaction in transactions:
        if transaction.status != "FAILED":
            totals[transaction.category] += transaction.amount
    return {category: money_to_string(amount) for category, amount in sorted(totals.items())}


def top_merchants(transactions: list[CleanedTransaction], limit: int = 3) -> list[dict[str, str | int]]:
    counts = Counter(transaction.merchant for transaction in transactions)
    return [{"merchant": merchant, "transaction_count": count} for merchant, count in counts.most_common(limit)]


def anomaly_count(transactions: list[CleanedTransaction]) -> int:
    return sum(1 for transaction in transactions if transaction.is_anomaly)
