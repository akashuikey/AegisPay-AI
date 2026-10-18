"""Create customer call sessions table and conversation_type column (Option A).

Revision ID: 0013_customer_call_sessions
Revises: 0012_scenario_runs
Create Date: 2026-10-18 07:35:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_customer_call_sessions"
down_revision: str | None = "0012_scenario_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add conversation_type to investigation_conversations to separate operator
    # vs customer dialogues
    op.add_column(
        "investigation_conversations",
        sa.Column(
            "conversation_type",
            sa.String(length=32),
            server_default="OPERATOR_INVESTIGATION",
            nullable=False,
        ),
    )

    # 2. Create transaction_call_sessions table
    op.create_table(
        "transaction_call_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "channel", sa.String(length=32), server_default="VOICE_SIMULATED", nullable=False
        ),
        sa.Column("status", sa.String(length=32), server_default="INITIATED", nullable=False),
        sa.Column(
            "direction",
            sa.String(length=32),
            server_default="OUTBOUND_SIMULATED",
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("coercion_analysis_id", sa.Uuid(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_reason", sa.String(length=128), nullable=True),
        sa.Column(
            "customer_phone_masked",
            sa.String(length=32),
            server_default="+91 ••••• ••890",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["investigation_conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["coercion_analysis_id"], ["transaction_coercion_analyses.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transaction_id", "idempotency_key", name="uq_call_sessions_tx_idempotency"
        ),
    )
    op.create_index(
        "ix_call_sessions_transaction_id",
        "transaction_call_sessions",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_call_sessions_tx_created",
        "transaction_call_sessions",
        ["transaction_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_call_sessions_conversation",
        "transaction_call_sessions",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_call_sessions_status",
        "transaction_call_sessions",
        ["status"],
        unique=False,
    )
    # Enforce at most one active (non-terminal) call session per transaction.
    op.create_index(
        "uq_call_sessions_active_tx",
        "transaction_call_sessions",
        ["transaction_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('INITIATED', 'RINGING', 'CONNECTED')"),
    )


def downgrade() -> None:
    op.drop_index("uq_call_sessions_active_tx", table_name="transaction_call_sessions")
    op.drop_index("ix_call_sessions_status", table_name="transaction_call_sessions")
    op.drop_index("ix_call_sessions_conversation", table_name="transaction_call_sessions")
    op.drop_index("ix_call_sessions_tx_created", table_name="transaction_call_sessions")
    op.drop_index("ix_call_sessions_transaction_id", table_name="transaction_call_sessions")
    op.drop_table("transaction_call_sessions")
    op.drop_column("investigation_conversations", "conversation_type")
