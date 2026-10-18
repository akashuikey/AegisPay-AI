"""Create fictional recipients registry and seed 20 demonstration identities (P2-A12).

Revision ID: 0015_create_fictional_recipients
Revises: 0014_live_voice_transcripts
Create Date: 2026-10-18 10:00:00.000000+00:00
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.domain.recipient_registry import FICTIONAL_RECIPIENTS_SEED_DATA

# revision identifiers, used by Alembic.
revision: str = "0015_create_fictional_recipients"
down_revision: str | None = "0014_live_voice_transcripts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = op.create_table(
        "fictional_recipients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("upi_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=False),
        sa.Column("branch_region", sa.String(length=100), nullable=False),
        sa.Column("account_age_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column(
            "is_trusted_beneficiary",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("is_flagged_mule", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("complaint_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fan_in_count_24h", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fan_out_count_24h", sa.Integer(), server_default="0", nullable=False),
        sa.Column("typical_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("typical_frequency", sa.String(length=50), nullable=True),
        sa.Column("history_summary", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("seed_version", sa.Integer(), server_default="1", nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upi_id", name="uq_fictional_recipients_upi_id"),
    )
    op.create_index(
        "ix_fictional_recipients_category",
        "fictional_recipients",
        ["category"],
        unique=False,
    )
    op.create_index(
        "ix_fictional_recipients_upi_id",
        "fictional_recipients",
        ["upi_id"],
        unique=True,
    )

    # Seed the 20 deterministic fictional recipient records
    seed_rows = []
    for r in FICTIONAL_RECIPIENTS_SEED_DATA:
        seed_rows.append(
            {
                "id": uuid.UUID(r["id"]) if isinstance(r["id"], str) else r["id"],
                "upi_id": r["upi_id"],
                "display_name": r["display_name"],
                "bank_name": r["bank_name"],
                "branch_region": r["branch_region"],
                "account_age_days": r["account_age_days"],
                "category": r["category"],
                "is_trusted_beneficiary": r["is_trusted_beneficiary"],
                "is_flagged_mule": r["is_flagged_mule"],
                "complaint_count": r["complaint_count"],
                "fan_in_count_24h": r["fan_in_count_24h"],
                "fan_out_count_24h": r["fan_out_count_24h"],
                "typical_amount": r["typical_amount"],
                "typical_frequency": r["typical_frequency"],
                "history_summary": r["history_summary"],
                "is_active": True,
                "seed_version": 1,
            }
        )

    op.bulk_insert(table, seed_rows)


def downgrade() -> None:
    op.drop_index("ix_fictional_recipients_upi_id", table_name="fictional_recipients")
    op.drop_index("ix_fictional_recipients_category", table_name="fictional_recipients")
    op.drop_table("fictional_recipients")
