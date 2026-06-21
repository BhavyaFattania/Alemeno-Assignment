"""initial schema

Revision ID: 20260618_0001
Revises:
Create Date: 2026-06-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    job_status = sa.Enum("pending", "processing", "completed", "failed", name="jobstatus")

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("row_count_raw", sa.Integer(), nullable=False),
        sa.Column("row_count_clean", sa.Integer(), nullable=False),
        sa.Column("upload_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_created_at"), "jobs", ["created_at"])
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"])

    op.create_table(
        "job_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("total_spend_by_currency", sa.JSON(), nullable=False),
        sa.Column("spend_by_category", sa.JSON(), nullable=False),
        sa.Column("top_merchants", sa.JSON(), nullable=False),
        sa.Column("anomaly_count", sa.Integer(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("llm_raw_response", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("txn_id", sa.String(length=100), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("merchant", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("account_id", sa.String(length=100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_anomaly", sa.Boolean(), nullable=False),
        sa.Column("anomaly_reason", sa.Text(), nullable=True),
        sa.Column("llm_category", sa.String(length=100), nullable=True),
        sa.Column("llm_raw_response", sa.Text(), nullable=True),
        sa.Column("llm_failed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transactions_job_id"), "transactions", ["job_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_job_id"), table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("job_summaries")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_created_at"), table_name="jobs")
    op.drop_table("jobs")
