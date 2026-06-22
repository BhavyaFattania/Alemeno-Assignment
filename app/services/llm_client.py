import json
import time
from typing import Any

import httpx

from app.core.config import settings
from app.services import aggregation_service
from app.services.transaction_cleaner import CleanedTransaction, UNCATEGORISED


ALLOWED_CATEGORIES = [
    "Food",
    "Shopping",
    "Travel",
    "Transport",
    "Utilities",
    "Cash Withdrawal",
    "Entertainment",
    "Other",
]


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.openrouter_api_key
        self.model = model or settings.openrouter_model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        # Shared client reuses TCP connections across calls (keep-alive)
        # instead of creating a new socket on every request/retry
        self._http_client = httpx.Client(
            timeout=settings.llm_timeout_seconds,
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
            ),
        )

    def __del__(self) -> None:
        """Close the shared HTTP client when the LLMClient is garbage collected."""
        try:
            self._http_client.close()
        except Exception:  # noqa: BLE001
            pass

    def classify_transactions(self, transactions: list[CleanedTransaction]) -> tuple[dict[int, str], str]:
        if not transactions:
            return {}, ""

        payload_rows = [
            {
                "index": index,
                "merchant": transaction.merchant,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "notes": transaction.notes or "",
            }
            for index, transaction in enumerate(transactions)
        ]
        prompt = (
            "Classify each transaction into exactly one allowed category. "
            f"Allowed categories: {', '.join(ALLOWED_CATEGORIES)}. "
            "Return strict JSON only in this shape: "
            '{"classifications":[{"index":0,"category":"Food"}]}. '
            f"Transactions: {json.dumps(payload_rows)}"
        )
        raw = self._chat_json(prompt)
        classifications = raw.get("classifications", [])
        mapped: dict[int, str] = {}
        for item in classifications:
            index = item.get("index")
            category = item.get("category")
            if isinstance(index, int) and category in ALLOWED_CATEGORIES:
                mapped[index] = category
        return mapped, json.dumps(raw)

    def summarize(self, transactions: list[CleanedTransaction]) -> tuple[dict[str, Any], str]:
        facts = {
            "total_spend_by_currency": aggregation_service.total_spend_by_currency(transactions),
            "top_merchants": aggregation_service.top_merchants(transactions),
            "anomaly_count": aggregation_service.anomaly_count(transactions),
            "spend_by_category": aggregation_service.spend_by_category(transactions),
        }
        prompt = (
            "Create a concise financial transaction report. Return strict JSON only with keys "
            "total_spend_by_currency, top_merchants, anomaly_count, narrative, risk_level. "
            "risk_level must be low, medium, or high. narrative must be 2-3 sentences. "
            f"Facts: {json.dumps(facts)}"
        )
        raw = self._chat_json(prompt)
        return raw, json.dumps(raw)

    def _chat_json(self, prompt: str) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": settings.app_name,
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                # Reuse self._http_client — no new TCP handshake per retry
                response = self._http_client.post(self.base_url, headers=headers, json=body)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return json.loads(_extract_json(content))
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < 2:
                    time.sleep(2**attempt)
        raise RuntimeError(f"LLM call failed after retries: {last_error}") from last_error



def _extract_json(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("LLM response did not contain JSON")
    return text[start : end + 1]


def apply_llm_classification(transactions: list[CleanedTransaction], client: LLMClient | None = None) -> None:
    missing = [transaction for transaction in transactions if transaction.original_category_missing]
    if not missing:
        return

    client = client or LLMClient()
    try:
        classifications, raw_response = client.classify_transactions(missing)
    except Exception:  # noqa: BLE001
        for transaction in missing:
            transaction.llm_failed = True
        return

    for index, transaction in enumerate(missing):
        category = classifications.get(index)
        transaction.llm_raw_response = raw_response
        if category:
            transaction.category = category
            transaction.llm_category = category
        else:
            transaction.category = UNCATEGORISED
            transaction.llm_failed = True


def fallback_summary(transactions: list[CleanedTransaction]) -> dict[str, Any]:
    anomalies = aggregation_service.anomaly_count(transactions)
    risk_level = "high" if anomalies >= 5 else "medium" if anomalies >= 1 else "low"
    return {
        "total_spend_by_currency": aggregation_service.total_spend_by_currency(transactions),
        "top_merchants": aggregation_service.top_merchants(transactions),
        "anomaly_count": anomalies,
        "narrative": "The uploaded transactions were cleaned and summarized with deterministic fallback logic because the LLM summary was unavailable.",
        "risk_level": risk_level,
    }
