import uuid
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.errors import IdempotencyConflictError, NotFoundError
from app.core.logging import get_logger
from app.db.models import TransactionAuditModel, TransactionModel
from app.domain.state_machine import (
    ActorType,
    TransactionState,
    validate_transition,
)
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.transaction import (
    CreateTransactionRequest,
    TransitionTransactionRequest,
)

logger = get_logger(__name__)


class TransactionService:
    """Coordinates transaction lifecycle, validation, idempotency, and audit logging."""

    def __init__(self, repository: TransactionRepository) -> None:
        self.repository = repository

    async def create_transaction(
        self, request: CreateTransactionRequest
    ) -> tuple[TransactionModel, bool]:
        """Create a new simulated transaction or return existing if idempotent replay.

        Returns:
            tuple[TransactionModel, bool]: (transaction, created_flag) where created_flag is True
            if freshly created, and False if idempotently returned.

        Raises:
            IdempotencyConflictError: If idempotency_key is reused with different payload.
        """
        payload_hash = request.compute_payload_hash()

        # Step 1: Check if an idempotent entry already exists
        existing = await self.repository.get_by_customer_and_idempotency_key(
            customer_id=request.customer_id,
            idempotency_key=request.idempotency_key,
        )
        if existing is not None:
            if existing.payload_hash == payload_hash:
                logger.info(
                    "Idempotent replay for customer=%s key=%s (tx_id=%s)",
                    request.customer_id,
                    request.idempotency_key,
                    existing.id,
                )
                return existing, False
            logger.warning(
                "Idempotency conflict for customer=%s key=%s",
                request.customer_id,
                request.idempotency_key,
            )
            raise IdempotencyConflictError(
                f"Idempotency key '{request.idempotency_key}' is already used "
                "with a different transaction payload"
            )

        # Step 2: Prepare new transaction and initial audit entry
        tx_id = uuid.uuid4()
        tx = TransactionModel(
            id=tx_id,
            customer_id=request.customer_id,
            idempotency_key=request.idempotency_key,
            payload_hash=payload_hash,
            amount=request.amount,
            currency=request.currency.upper(),
            payment_rail=request.payment_rail.upper(),
            recipient_name=request.recipient_name,
            recipient_identifier=request.recipient_identifier,
            purpose=request.purpose,
            state=TransactionState.INITIATED.value,
            version=1,
        )
        initial_audit = TransactionAuditModel(
            id=uuid.uuid4(),
            transaction_id=tx_id,
            from_state=None,
            to_state=TransactionState.INITIATED.value,
            actor_type=ActorType.CUSTOMER.value,
            reason="Simulated payment initiated by customer",
        )

        try:
            created_tx = await self.repository.create(tx, initial_audit)
            logger.info("Created simulated transaction id=%s state=INITIATED", created_tx.id)
            return created_tx, True
        except IntegrityError:
            # Handle race condition between concurrent identical requests
            conflicted = await self.repository.get_by_customer_and_idempotency_key(
                customer_id=request.customer_id,
                idempotency_key=request.idempotency_key,
            )
            if conflicted is not None and conflicted.payload_hash == payload_hash:
                return conflicted, False
            raise IdempotencyConflictError(
                f"Idempotency key '{request.idempotency_key}' was claimed concurrently "
                "with a different payload"
            ) from None

    async def get_transaction(self, transaction_id: UUID) -> TransactionModel:
        """Fetch a transaction by ID or raise NotFoundError."""
        tx = await self.repository.get_by_id(transaction_id)
        if tx is None:
            raise NotFoundError(f"Transaction with ID '{transaction_id}' was not found")
        return tx

    async def list_transactions(
        self,
        limit: int = 50,
        offset: int = 0,
        customer_id: str | None = None,
        state: str | None = None,
    ) -> tuple[list[TransactionModel], int]:
        """Fetch a paginated list of transactions with total count."""
        return await self.repository.list_transactions(
            limit=limit,
            offset=offset,
            customer_id=customer_id,
            state=state,
        )

    async def transition_transaction(
        self,
        transaction_id: UUID,
        request: TransitionTransactionRequest,
    ) -> TransactionModel:
        """Enforce domain state transition rules and record an audit log entry.

        Raises:
            NotFoundError: If the transaction does not exist.
            InvalidStateTransitionError: If the transition is prohibited.
            ConcurrencyConflictError: If a concurrent modification occurs.
        """
        tx = await self.get_transaction(transaction_id)

        # Enforce domain transition rules
        validate_transition(tx.state, request.target_state)

        # Record audit entry
        audit_entry = TransactionAuditModel(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            from_state=tx.state,
            to_state=request.target_state.value,
            actor_type=request.actor_type.value,
            reason=request.reason,
            correlation_id=request.correlation_id,
        )

        # Apply state transition with optimistic concurrency check
        updated_tx = await self.repository.update_state(
            transaction_id=tx.id,
            expected_version=tx.version,
            new_state=request.target_state.value,
            audit_entry=audit_entry,
        )

        logger.info(
            "Transitioned transaction %s: %s -> %s (actor=%s)",
            transaction_id,
            tx.state,
            request.target_state.value,
            request.actor_type.value,
        )
        return updated_tx

    async def get_audit_history(self, transaction_id: UUID) -> list[TransactionAuditModel]:
        """Fetch chronological audit history for a transaction."""
        # Ensure transaction exists first
        await self.get_transaction(transaction_id)
        return await self.repository.get_audit_history(transaction_id)
