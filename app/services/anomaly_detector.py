from collections import defaultdict
from decimal import Decimal
from statistics import median

from app.services.transaction_cleaner import CleanedTransaction


DOMESTIC_ONLY_MERCHANTS = {"swiggy", "ola", "irctc"}


def detect_anomalies(transactions: list[CleanedTransaction]) -> None:
    amounts_by_account: dict[str, list[Decimal]] = defaultdict(list)
    for transaction in transactions:
        amounts_by_account[transaction.account_id].append(transaction.amount)

    medians = {
        account_id: Decimal(str(median(amounts)))
        for account_id, amounts in amounts_by_account.items()
        if amounts
    }

    for transaction in transactions:
        reasons: list[str] = []
        account_median = medians.get(transaction.account_id)
        if account_median is not None and account_median > 0 and transaction.amount > account_median * Decimal("3"):
            reasons.append(f"Amount exceeds 3x account median ({account_median})")

        if transaction.currency == "USD" and transaction.merchant.strip().lower() in DOMESTIC_ONLY_MERCHANTS:
            reasons.append("USD transaction for domestic-only merchant")

        if reasons:
            transaction.is_anomaly = True
            transaction.anomaly_reason = "; ".join(reasons)
