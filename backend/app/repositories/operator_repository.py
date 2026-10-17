"""Repository for operator identity persistence and lookups."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OperatorModel


class OperatorRepository:
    """Data access for the operators (fraud-operations analyst) identity table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, operator_id: UUID) -> OperatorModel | None:
        """Fetch an operator by primary key."""
        stmt = select(OperatorModel).where(OperatorModel.id == operator_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> OperatorModel | None:
        """Fetch an operator by unique username."""
        stmt = select(OperatorModel).where(OperatorModel.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, operator: OperatorModel) -> OperatorModel:
        """Persist a new operator record."""
        self.session.add(operator)
        await self.session.commit()
        await self.session.refresh(operator)
        return operator
