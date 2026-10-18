"""Create live-voice transcript segments and incremental analysis tables (P2-A11).

Revision ID: 0014_live_voice_transcripts
Revises: 0013_customer_call_sessions
Create Date: 2026-10-18 09:30:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_live_voice_transcripts"
down_revision: str | None = "0013_customer_call_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Streaming transcript segments (final/corrected only; interim partials are not stored).
    op.create_table(
        "call_transcript_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("call_session_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("speaker", sa.String(length=16), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="final", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_offset_ms", sa.Integer(), nullable=True),
        sa.Column("end_offset_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["call_session_id"], ["transaction_call_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["investigation_conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_session_id", "seq", name="uq_transcript_segments_session_seq"),
    )
    op.create_index(
        "ix_transcript_segments_call_session_id",
        "call_transcript_segments",
        ["call_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_segments_transaction_id",
        "call_transcript_segments",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_segments_session_seq",
        "call_transcript_segments",
        ["call_session_id", "seq"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_segments_created_at",
        "call_transcript_segments",
        ["created_at"],
        unique=False,
    )

    # Incremental evidence-analysis snapshots (advisory; never drive state transitions).
    op.create_table(
        "call_live_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("call_session_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("contract_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="completed", nullable=False),
        sa.Column(
            "overall_sentiment", sa.String(length=32), server_default="UNKNOWN", nullable=False
        ),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("uncertainty_notes", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("analyzed_through_seq", sa.Integer(), server_default="-1", nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["call_session_id"], ["transaction_call_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_call_live_analyses_call_session_id",
        "call_live_analyses",
        ["call_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_call_live_analyses_transaction_id",
        "call_live_analyses",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_call_live_analyses_created_at",
        "call_live_analyses",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_call_live_analyses_session_created",
        "call_live_analyses",
        ["call_session_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_call_live_analyses_session_created", table_name="call_live_analyses")
    op.drop_index("ix_call_live_analyses_created_at", table_name="call_live_analyses")
    op.drop_index("ix_call_live_analyses_transaction_id", table_name="call_live_analyses")
    op.drop_index("ix_call_live_analyses_call_session_id", table_name="call_live_analyses")
    op.drop_table("call_live_analyses")

    op.drop_index("ix_transcript_segments_created_at", table_name="call_transcript_segments")
    op.drop_index("ix_transcript_segments_session_seq", table_name="call_transcript_segments")
    op.drop_index("ix_transcript_segments_transaction_id", table_name="call_transcript_segments")
    op.drop_index("ix_transcript_segments_call_session_id", table_name="call_transcript_segments")
    op.drop_table("call_transcript_segments")
