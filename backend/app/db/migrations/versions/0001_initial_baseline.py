"""Initial baseline migration.

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-10-17 12:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_initial_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Baseline migration: Domain tables will be introduced in Phase 1 Agent 2
    pass


def downgrade() -> None:
    pass
