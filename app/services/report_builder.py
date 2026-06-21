from typing import Any

from app.services import aggregation_service
from app.services.llm_client import LLMClient, fallback_summary
from app.services.transaction_cleaner import CleanedTransaction


def build_summary(transactions: list[CleanedTransaction], client: LLMClient | None = None) -> tuple[dict[str, Any], str | None]:
    client = client or LLMClient()
    try:
        summary, raw_response = client.summarize(transactions)
    except Exception:  # noqa: BLE001
        summary = fallback_summary(transactions)
        raw_response = None

    summary.setdefault("total_spend_by_currency", aggregation_service.total_spend_by_currency(transactions))
    summary.setdefault("top_merchants", aggregation_service.top_merchants(transactions))
    summary.setdefault("anomaly_count", aggregation_service.anomaly_count(transactions))
    summary.setdefault("narrative", fallback_summary(transactions)["narrative"])
    summary.setdefault("risk_level", fallback_summary(transactions)["risk_level"])
    summary["spend_by_category"] = aggregation_service.spend_by_category(transactions)
    summary["total_spend_by_currency"] = _string_dict(summary["total_spend_by_currency"])
    summary["spend_by_category"] = _string_dict(summary["spend_by_category"])

    if summary["risk_level"] not in {"low", "medium", "high"}:
        summary["risk_level"] = fallback_summary(transactions)["risk_level"]

    return summary, raw_response


def _string_dict(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}
