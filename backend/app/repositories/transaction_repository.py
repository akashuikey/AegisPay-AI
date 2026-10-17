"""Repository for persistent transaction and audit operations."""

from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConcurrencyConflictError
from app.core.logging import get_logger
from app.db.models import TransactionAuditModel, TransactionModel

logger = get_logger(__name__)


class TransactionRepository:
    """Handles database persistence and queries for transactions and their audit trail."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, transaction_id: UUID) -> TransactionModel | None:
        """Fetch a transaction by primary key."""
        stmt = select(TransactionModel).where(TransactionModel.id == transaction_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_customer_and_idempotency_key(
        self, customer_id: str, idempotency_key: str
    ) -> TransactionModel | None:
        """Fetch a transaction by customer_id and idempotency_key."""
        stmt = select(TransactionModel).where(
            TransactionModel.customer_id == customer_id,
            TransactionModel.idempotency_key == idempotency_key,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        transaction: TransactionModel,
        initial_audit: TransactionAuditModel,
    ) -> TransactionModel:
        """Atomically persist a new transaction and its initial audit entry.

        Raises:
            IntegrityError: If unique constraint on (customer_id, idempotency_key) is violated.
        """
        self.session.add(transaction)
        self.session.add(initial_audit)
        try:
            await self.session.commit()
            await self.session.refresh(transaction)
            return transaction
        except IntegrityError:
            await self.session.rollback()
            raise

    async def list_transactions(
        self,
        limit: int = 50,
        offset: int = 0,
        customer_id: str | None = None,
        state: str | None = None,
    ) -> tuple[list[TransactionModel], int]:
        """Fetch paginated transactions ordered by creation date descending, with total count."""
        # Base count statement
        count_stmt = select(func.count(TransactionModel.id))
        query_stmt = select(TransactionModel).order_by(TransactionModel.created_at.desc())

        if customer_id is not None:
            count_stmt = count_stmt.where(TransactionModel.customer_id == customer_id)
            query_stmt = query_stmt.where(TransactionModel.customer_id == customer_id)

        if state is not None:
            count_stmt = count_stmt.where(TransactionModel.state == state)
            query_stmt = query_stmt.where(TransactionModel.state == state)

        # Execute total count
        count_result = await self.session.execute(count_stmt)
        total: int = count_result.scalar_one() or 0

        # Execute paginated query
        query_stmt = query_stmt.limit(limit).offset(offset)
        result = await self.session.execute(query_stmt)
        items = list(result.scalars().all())

        return items, total

    async def update_state(
        self,
        transaction_id: UUID,
        expected_version: int,
        new_state: str,
        audit_entry: TransactionAuditModel,
    ) -> TransactionModel:
        """Execute an atomic state transition with optimistic concurrency locking and audit logging.

        Raises:
            ConcurrencyConflictError: If the transaction version does not match expected_version.
        """
        stmt = (
            update(TransactionModel)
            .where(
                TransactionModel.id == transaction_id,
                TransactionModel.version == expected_version,
            )
            .values(
                state=new_state,
                version=expected_version + 1,
            )
            .execution_options(synchronize_session="fetch")
        )

        result = await self.session.execute(stmt)
        if isinstance(result, CursorResult) and result.rowcount == 0:
            await self.session.rollback()
            raise ConcurrencyConflictError(
                f"Transaction {transaction_id} was updated concurrently (version mismatch); "
                "please reload and retry"
            )

        self.session.add(audit_entry)
        await self.session.commit()

        updated_tx = await self.get_by_id(transaction_id)
        if updated_tx is None:
            raise ConcurrencyConflictError(f"Transaction {transaction_id} no longer exists")
        return updated_tx

    async def get_audit_history(self, transaction_id: UUID) -> list[TransactionAuditModel]:
        """Fetch complete audit history for a given transaction ordered chronologically."""
        stmt = (
            select(TransactionAuditModel)
            .where(TransactionAuditModel.transaction_id == transaction_id)
            .order_by(TransactionAuditModel.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
