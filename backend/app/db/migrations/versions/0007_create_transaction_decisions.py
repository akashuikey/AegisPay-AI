"""Create transaction_decisions table for the automated decision workflow.

Revision ID: 0007_transaction_decisions
Revises: 0006_operators
Create Date: 2026-10-17 23:10:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_transaction_decisions"
down_revision: str | None = "0006_operators"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transaction_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("investigation_id", sa.Uuid(), nullable=True),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("requires_verification", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider_failed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("from_state", sa.String(length=32), nullable=False),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("workflow_status", sa.String(length=32), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("triggered_rule_ids", sa.JSON(), nullable=False),
        sa.Column("investigation_finding_refs", sa.JSON(), nullable=False),
        sa.Column("supporting_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("missing_information", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["transaction_investigations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transaction_decisions_tx_created",
        "transaction_decisions",
        ["transaction_id", "created_at"],
    )
    op.create_index(
        op.f("ix_transaction_decisions_transaction_id"),
        "transaction_decisions",
        ["transaction_id"],
    )
    op.create_index(
        op.f("ix_transaction_decisions_assessment_id"),
        "transaction_decisions",
        ["assessment_id"],
    )
    op.create_index(
        op.f("ix_transaction_decisions_investigation_id"),
        "transaction_decisions",
        ["investigation_id"],
    )
    op.create_index(
        op.f("ix_transaction_decisions_created_at"),
        "transaction_decisions",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_transaction_decisions_created_at"), table_name="transaction_decisions")
    op.drop_index(
        op.f("ix_transaction_decisions_investigation_id"), table_name="transaction_decisions"
    )
    op.drop_index(
        op.f("ix_transaction_decisions_assessment_id"), table_name="transaction_decisions"
    )
    op.drop_index(
        op.f("ix_transaction_decisions_transaction_id"), table_name="transaction_decisions"
    )
    op.drop_index("ix_transaction_decisions_tx_created", table_name="transaction_decisions")
    op.drop_table("transaction_decisions")
