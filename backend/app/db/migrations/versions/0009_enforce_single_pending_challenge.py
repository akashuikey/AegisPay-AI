"""Enforce single pending verification challenge per transaction via partial unique index.

Revision ID: 0009_single_pending_challenge
Revises: 0008_verification_challenges
Create Date: 2026-10-18 00:30:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_single_pending_challenge"
down_revision: str | None = "0008_verification_challenges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Deterministically resolve existing duplicate PENDING challenges (if any)
    # without deleting audit history: keep the most recent PENDING challenge per
    # transaction and mark older duplicates as 'SUPERSEDED'.
    op.execute(
        sa.text(
            """
            UPDATE verification_challenges
            SET status = 'SUPERSEDED',
                failure_reason = 'SUPERSEDED_BY_CONCURRENT_CHALLENGE'
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY transaction_id
                               ORDER BY created_at DESC, id DESC
                           ) as rn
                    FROM verification_challenges
                    WHERE status = 'PENDING'
                ) ranked
                WHERE ranked.rn > 1
            );
            """
        )
    )

    # 2. Create partial unique index on transaction_id where status = 'PENDING'
    op.create_index(
        "uq_verification_challenges_pending_tx",
        "verification_challenges",
        ["transaction_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_verification_challenges_pending_tx",
        table_name="verification_challenges",
        postgresql_where=sa.text("status = 'PENDING'"),
    )

