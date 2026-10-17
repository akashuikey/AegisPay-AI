"""Create scenario_runs table for end-to-end simulation & explainability (P2-A8).

Revision ID: 0012_scenario_runs
Revises: 0011_fraud_responses
Create Date: 2026-10-18 03:30:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_scenario_runs"
down_revision: str | None = "0011_fraud_responses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenario_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_version", sa.String(length=32), nullable=False),
        sa.Column("catalog_version", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("ai_provider", sa.String(length=64), nullable=True),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("stages", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_scenario_runs_idempotency_key"),
    )
    op.create_index("ix_scenario_runs_scenario_id", "scenario_runs", ["scenario_id"], unique=False)
    op.create_index(
        "ix_scenario_runs_transaction_id", "scenario_runs", ["transaction_id"], unique=False
    )
    op.create_index("ix_scenario_runs_created_at", "scenario_runs", ["created_at"], unique=False)
    op.create_index(
        "ix_scenario_runs_scenario_created",
        "scenario_runs",
        ["scenario_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scenario_runs_scenario_created", table_name="scenario_runs")
    op.drop_index("ix_scenario_runs_created_at", table_name="scenario_runs")
    op.drop_index("ix_scenario_runs_transaction_id", table_name="scenario_runs")
    op.drop_index("ix_scenario_runs_scenario_id", table_name="scenario_runs")
    op.drop_table("scenario_runs")
