"""Create transaction investigations table.

Revision ID: 0004_transaction_investigations
Revises: 0003_transaction_assessments
Create Date: 2026-10-17 14:18:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_transaction_investigations"
down_revision: str | None = "0003_transaction_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transaction_investigations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("overall_risk_sentiment", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("contradictory_evidence", sa.JSON(), nullable=False),
        sa.Column("missing_information", sa.JSON(), nullable=False),
        sa.Column("unresolved_questions", sa.JSON(), nullable=False),
        sa.Column("suggested_next_steps", sa.JSON(), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["transaction_assessments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_transaction_investigations_created_at"),
        "transaction_investigations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transaction_investigations_transaction_id"),
        "transaction_investigations",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transaction_investigations_assessment_id"),
        "transaction_investigations",
        ["assessment_id"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_investigations_tx_created",
        "transaction_investigations",
        ["transaction_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transaction_investigations_tx_created", table_name="transaction_investigations"
    )
    op.drop_index(
        op.f("ix_transaction_investigations_assessment_id"),
        table_name="transaction_investigations",
    )
    op.drop_index(
        op.f("ix_transaction_investigations_transaction_id"),
        table_name="transaction_investigations",
    )
    op.drop_index(
        op.f("ix_transaction_investigations_created_at"), table_name="transaction_investigations"
    )
    op.drop_table("transaction_investigations")
