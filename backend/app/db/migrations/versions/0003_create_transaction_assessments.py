"""Create transaction assessments table.

Revision ID: 0003_transaction_assessments
Revises: 0002_transactions
Create Date: 2026-10-17 13:36:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_transaction_assessments"
down_revision: str | None = "0002_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transaction_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("recommended_action", sa.String(length=64), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("triggered_rules", sa.JSON(), nullable=False),
        sa.Column("supporting_evidence", sa.JSON(), nullable=False),
        sa.Column("missing_evidence", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_transaction_assessments_created_at"),
        "transaction_assessments",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transaction_assessments_transaction_id"),
        "transaction_assessments",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_assessments_tx_created",
        "transaction_assessments",
        ["transaction_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transaction_assessments_tx_created",
        table_name="transaction_assessments",
    )
    op.drop_index(
        op.f("ix_transaction_assessments_transaction_id"),
        table_name="transaction_assessments",
    )
    op.drop_index(
        op.f("ix_transaction_assessments_created_at"),
        table_name="transaction_assessments",
    )
    op.drop_table("transaction_assessments")
