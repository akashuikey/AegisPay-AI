"""Create transactions and audits tables.

Revision ID: 0002_transactions
Revises: 0001_initial_baseline
Create Date: 2026-10-17 12:45:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_transactions"
down_revision: str | None = "0001_initial_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_rail", sa.String(length=32), nullable=False),
        sa.Column("recipient_name", sa.String(length=255), nullable=False),
        sa.Column("recipient_identifier", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "customer_id",
            "idempotency_key",
            name="uq_transactions_customer_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_transactions_created_at"),
        "transactions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_customer_created",
        "transactions",
        ["customer_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_customer_id"),
        "transactions",
        ["customer_id"],
        unique=False,
    )
    op.create_index(op.f("ix_transactions_state"), "transactions", ["state"], unique=False)

    op.create_table(
        "transaction_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
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
        op.f("ix_transaction_audits_created_at"),
        "transaction_audits",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transaction_audits_transaction_id"),
        "transaction_audits",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_audits_tx_created",
        "transaction_audits",
        ["transaction_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_audits_tx_created", table_name="transaction_audits")
    op.drop_index(
        op.f("ix_transaction_audits_transaction_id"),
        table_name="transaction_audits",
    )
    op.drop_index(
        op.f("ix_transaction_audits_created_at"),
        table_name="transaction_audits",
    )
    op.drop_table("transaction_audits")
    op.drop_index(op.f("ix_transactions_state"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_customer_id"), table_name="transactions")
    op.drop_index("ix_transactions_customer_created", table_name="transactions")
    op.drop_index(op.f("ix_transactions_created_at"), table_name="transactions")
    op.drop_table("transactions")
