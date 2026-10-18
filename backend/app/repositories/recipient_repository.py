"""Repository for querying and idempotently seeding fictional recipients (P2-A12)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import FictionalRecipientModel
from app.domain.recipient_registry import FICTIONAL_RECIPIENTS_SEED_DATA

logger = get_logger(__name__)


class RecipientRepository:
    """Provides database access to the fictional recipient registry."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_upi_id(self, upi_id: str) -> FictionalRecipientModel | None:
        """Resolve a fictional recipient by UPI identifier (case-insensitive)."""
        clean_upi = upi_id.strip().lower()
        stmt = select(FictionalRecipientModel).where(
            func.lower(FictionalRecipientModel.upi_id) == clean_upi,
            FictionalRecipientModel.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_id(self, recipient_id: uuid.UUID) -> FictionalRecipientModel | None:
        """Resolve a fictional recipient by UUID."""
        stmt = select(FictionalRecipientModel).where(
            FictionalRecipientModel.id == recipient_id,
            FictionalRecipientModel.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_recipients(
        self, category: str | None = None, limit: int = 50
    ) -> list[FictionalRecipientModel]:
        """List active fictional recipients with optional category filter."""
        stmt = select(FictionalRecipientModel).where(FictionalRecipientModel.is_active.is_(True))
        if category:
            stmt = stmt.where(FictionalRecipientModel.category == category.upper())
        stmt = stmt.order_by(FictionalRecipientModel.created_at.asc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def seed_if_needed(self) -> int:
        """Idempotently seed the 20 fictional recipient records if missing.

        Returns the number of newly inserted records.
        """
        inserted_count = 0
        for data in FICTIONAL_RECIPIENTS_SEED_DATA:
            clean_upi = data["upi_id"].strip().lower()
            existing = await self.get_by_upi_id(clean_upi)
            if existing is None:
                rec_id = uuid.UUID(data["id"]) if isinstance(data["id"], str) else data["id"]
                record = FictionalRecipientModel(
                    id=rec_id,
                    upi_id=data["upi_id"],
                    display_name=data["display_name"],
                    bank_name=data["bank_name"],
                    branch_region=data["branch_region"],
                    account_age_days=data["account_age_days"],
                    category=data["category"],
                    is_trusted_beneficiary=data["is_trusted_beneficiary"],
                    is_flagged_mule=data["is_flagged_mule"],
                    complaint_count=data["complaint_count"],
                    fan_in_count_24h=data["fan_in_count_24h"],
                    fan_out_count_24h=data["fan_out_count_24h"],
                    typical_amount=data["typical_amount"],
                    typical_frequency=data["typical_frequency"],
                    history_summary=data["history_summary"],
                    is_active=True,
                    seed_version=1,
                )
                self.session.add(record)
                inserted_count += 1
        if inserted_count > 0:
            await self.session.commit()
            logger.info("Idempotently seeded %d fictional recipients", inserted_count)
        return inserted_count
