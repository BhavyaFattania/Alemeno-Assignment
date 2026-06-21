from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobSummary(Base):
    __tablename__ = "job_summaries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, nullable=False)
    total_spend_by_currency: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    spend_by_category: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    top_merchants: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    anomaly_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    llm_raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    job = relationship("Job", back_populates="summary")
