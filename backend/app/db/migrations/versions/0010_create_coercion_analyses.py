"""Create transaction_coercion_analyses table for voice duress and coercion intelligence (P2-A6).

Revision ID: 0010_coercion_analyses
Revises: 0009_single_pending_challenge
Create Date: 2026-10-18 01:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_coercion_analyses"
down_revision: str | None = "0009_single_pending_challenge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transaction_coercion_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("transcript_snippet", sa.Text(), nullable=False),
        sa.Column("overall_coercion_level", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("findings", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("voice_stress_signals", sa.JSON(), nullable=True),
        sa.Column("legitimate_explanations", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("uncertainty_notes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("missing_information", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("model_metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="COMPLETED", nullable=False),
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
        "ix_transaction_coercion_analyses_transaction_id",
        "transaction_coercion_analyses",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_coercion_analyses_created_at",
        "transaction_coercion_analyses",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_transaction_coercion_analyses_tx_created",
        "transaction_coercion_analyses",
        ["transaction_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transaction_coercion_analyses_tx_created",
        table_name="transaction_coercion_analyses",
    )
    op.drop_index(
        "ix_transaction_coercion_analyses_created_at",
        table_name="transaction_coercion_analyses",
    )
    op.drop_index(
        "ix_transaction_coercion_analyses_transaction_id",
        table_name="transaction_coercion_analyses",
    )
    op.drop_table("transaction_coercion_analyses")
