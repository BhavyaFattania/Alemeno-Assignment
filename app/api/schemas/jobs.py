from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobStatus


class UploadResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobListItem(BaseModel):
    id: str
    filename: str
    status: JobStatus
    row_count_raw: int
    row_count_clean: int
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class JobSummaryBrief(BaseModel):
    row_count_raw: int
    row_count_clean: int
    anomaly_count: int
    total_spend_by_currency: dict[str, str]
    risk_level: str


class JobStatusResponse(BaseModel):
    id: str
    filename: str
    status: JobStatus
    created_at: datetime
    completed_at: datetime | None
    error_message: str | None = None
    summary: JobSummaryBrief | None = None


class TransactionOut(BaseModel):
    txn_id: str | None
    date: date
    merchant: str
    amount: Decimal
    currency: str
    status: str
    category: str
    account_id: str
    notes: str | None
    is_anomaly: bool
    anomaly_reason: str | None
    llm_category: str | None
    llm_failed: bool

    model_config = ConfigDict(from_attributes=True)


class AnomalyOut(BaseModel):
    txn_id: str | None
    merchant: str
    amount: Decimal
    currency: str
    account_id: str
    anomaly_reason: str

    model_config = ConfigDict(from_attributes=True)


class FullSummaryOut(BaseModel):
    total_spend_by_currency: dict[str, str]
    spend_by_category: dict[str, str]
    top_merchants: list[dict[str, str | int]]
    anomaly_count: int
    narrative: str
    risk_level: str = Field(pattern="^(low|medium|high)$")


class JobResultsResponse(BaseModel):
    job_id: str
    cleaned_transactions: list[TransactionOut]
    flagged_anomalies: list[AnomalyOut]
    per_category_spend: dict[str, str]
    llm_summary: FullSummaryOut
