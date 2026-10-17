"""Create investigation conversations and conversation turns tables.

Revision ID: 0005_investigation_conversations
Revises: 0004_transaction_investigations
Create Date: 2026-10-17 15:10:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_investigation_conversations"
down_revision: str | None = "0004_transaction_investigations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investigation_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_investigation_conversations_created_at"),
        "investigation_conversations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_investigation_conversations_transaction_id"),
        "investigation_conversations",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_investigation_conversations_tx_created",
        "investigation_conversations",
        ["transaction_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "investigation_conversation_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("evidence_provenance", sa.String(length=64), nullable=True),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("risk_sentiment", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("missing_information", sa.JSON(), nullable=False),
        sa.Column("follow_up_questions", sa.JSON(), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["investigation_conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "turn_index", name="uq_conversation_turn_index"),
    )
    op.create_index(
        op.f("ix_investigation_conversation_turns_created_at"),
        "investigation_conversation_turns",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_investigation_conversation_turns_conversation_id"),
        "investigation_conversation_turns",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_turns_conv_turn",
        "investigation_conversation_turns",
        ["conversation_id", "turn_index"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_turns_conv_turn",
        table_name="investigation_conversation_turns",
    )
    op.drop_index(
        op.f("ix_investigation_conversation_turns_conversation_id"),
        table_name="investigation_conversation_turns",
    )
    op.drop_index(
        op.f("ix_investigation_conversation_turns_created_at"),
        table_name="investigation_conversation_turns",
    )
    op.drop_table("investigation_conversation_turns")

    op.drop_index(
        "ix_investigation_conversations_tx_created",
        table_name="investigation_conversations",
    )
    op.drop_index(
        op.f("ix_investigation_conversations_transaction_id"),
        table_name="investigation_conversations",
    )
    op.drop_index(
        op.f("ix_investigation_conversations_created_at"),
        table_name="investigation_conversations",
    )
    op.drop_table("investigation_conversations")
