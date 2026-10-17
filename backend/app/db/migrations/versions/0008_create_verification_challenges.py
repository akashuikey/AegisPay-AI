"""Create verification_challenges table for simulated customer verification.

Revision ID: 0008_verification_challenges
Revises: 0007_transaction_decisions
Create Date: 2026-10-18 00:10:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_verification_challenges"
down_revision: str | None = "0007_transaction_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "verification_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("otp_digest", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.Column("decision_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decision_id"], ["transaction_decisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_verification_challenges_transaction_id"),
        "verification_challenges",
        ["transaction_id"],
    )
    op.create_index(
        op.f("ix_verification_challenges_decision_id"),
        "verification_challenges",
        ["decision_id"],
    )
    op.create_index(
        op.f("ix_verification_challenges_created_at"),
        "verification_challenges",
        ["created_at"],
    )
    op.create_index(
        "ix_verification_challenges_tx_status",
        "verification_challenges",
        ["transaction_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_verification_challenges_tx_status", table_name="verification_challenges")
    op.drop_index(
        op.f("ix_verification_challenges_created_at"), table_name="verification_challenges"
    )
    op.drop_index(
        op.f("ix_verification_challenges_decision_id"), table_name="verification_challenges"
    )
    op.drop_index(
        op.f("ix_verification_challenges_transaction_id"), table_name="verification_challenges"
    )
    op.drop_table("verification_challenges")
