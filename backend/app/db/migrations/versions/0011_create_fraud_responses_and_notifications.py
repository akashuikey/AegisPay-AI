"""Create transaction_responses and transaction_notifications tables (P2-A7).

Revision ID: 0011_fraud_responses
Revises: 0010_coercion_analyses
Create Date: 2026-10-18 01:40:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_fraud_responses"
down_revision: str | None = "0010_coercion_analyses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create transaction_responses
    op.create_table(
        "transaction_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=True),
        sa.Column("response_type", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "processing_status",
            sa.String(length=32),
            server_default="COMPLETED",
            nullable=False,
        ),
        sa.Column("from_state", sa.String(length=32), nullable=False),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("headline", sa.String(length=200), nullable=False),
        sa.Column("customer_message", sa.Text(), nullable=False),
        sa.Column(
            "customer_action_required",
            sa.String(length=64),
            server_default="NONE",
            nullable=False,
        ),
        sa.Column("next_steps", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
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
        sa.UniqueConstraint(
            "transaction_id",
            "idempotency_key",
            name="uq_transaction_responses_tx_idempotency",
        ),
    )
    op.create_index(
        "ix_transaction_responses_transaction_id",
        "transaction_responses",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_responses_decision_id",
        "transaction_responses",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_responses_created_at",
        "transaction_responses",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_responses_tx_created",
        "transaction_responses",
        ["transaction_id", "created_at"],
        unique=False,
    )

    # 2. Create transaction_notifications
    op.create_table(
        "transaction_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("response_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("recipient_masked", sa.String(length=128), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column(
            "delivery_status",
            sa.String(length=32),
            server_default="DELIVERED_SIMULATED",
            nullable=False,
        ),
        sa.Column("failure_reason", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["response_id"], ["transaction_responses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "response_id",
            "channel",
            name="uq_transaction_notifications_response_channel",
        ),
    )
    op.create_index(
        "ix_transaction_notifications_response_id",
        "transaction_notifications",
        ["response_id"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_notifications_transaction_id",
        "transaction_notifications",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_notifications_created_at",
        "transaction_notifications",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_notifications_tx_created",
        "transaction_notifications",
        ["transaction_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Drop transaction_notifications
    op.drop_index(
        "ix_transaction_notifications_tx_created",
        table_name="transaction_notifications",
    )
    op.drop_index(
        "ix_transaction_notifications_created_at",
        table_name="transaction_notifications",
    )
    op.drop_index(
        "ix_transaction_notifications_transaction_id",
        table_name="transaction_notifications",
    )
    op.drop_index(
        "ix_transaction_notifications_response_id",
        table_name="transaction_notifications",
    )
    op.drop_table("transaction_notifications")

    # Drop transaction_responses
    op.drop_index(
        "ix_transaction_responses_tx_created",
        table_name="transaction_responses",
    )
    op.drop_index(
        "ix_transaction_responses_created_at",
        table_name="transaction_responses",
    )
    op.drop_index(
        "ix_transaction_responses_decision_id",
        table_name="transaction_responses",
    )
    op.drop_index(
        "ix_transaction_responses_transaction_id",
        table_name="transaction_responses",
    )
    op.drop_table("transaction_responses")
