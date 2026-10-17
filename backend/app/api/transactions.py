"""API routes for simulated transactions, state transitions, and audit trails."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.transaction import (
    AuditHistoryResponse,
    CreateTransactionRequest,
    TransactionAuditResponse,
    TransactionListResponse,
    TransactionResponse,
    TransitionTransactionRequest,
)
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/transactions", tags=["Transactions"])


def get_transaction_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TransactionService:
    """Dependency provider for TransactionService with request-scoped DB session."""
    repository = TransactionRepository(session)
    return TransactionService(repository)


@router.post(
    "",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create simulated transaction",
    description=(
        "Initiates a new simulated transaction or returns existing if idempotently replayed."
    ),
)
async def create_transaction(
    request: CreateTransactionRequest,
    response: Response,
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    """Create a simulated transaction or replay existing if idempotent key matches."""
    tx, created = await service.create_transaction(request)
    if not created:
        response.status_code = status.HTTP_200_OK
    return TransactionResponse.model_validate(tx)


@router.get(
    "",
    response_model=TransactionListResponse,
    summary="List transactions",
    description="Retrieve paginated list of transactions ordered by creation date descending.",
)
async def list_transactions(
    service: Annotated[TransactionService, Depends(get_transaction_service)],
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 50,
    offset: Annotated[int, Query(ge=0, description="Page offset")] = 0,
    customer_id: Annotated[
        str | None, Query(description="Optional filter by customer identifier")
    ] = None,
    state: Annotated[
        str | None, Query(description="Optional filter by transaction workflow state")
    ] = None,
) -> TransactionListResponse:
    """List transactions with optional filtering and bounded pagination."""
    items, total = await service.list_transactions(
        limit=limit,
        offset=offset,
        customer_id=customer_id,
        state=state,
    )
    return TransactionListResponse(
        items=[TransactionResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{transaction_id}",
    response_model=TransactionResponse,
    summary="Get transaction by ID",
    description="Fetch a single simulated transaction by its UUID.",
)
async def get_transaction(
    transaction_id: UUID,
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    """Fetch details of a transaction by ID."""
    tx = await service.get_transaction(transaction_id)
    return TransactionResponse.model_validate(tx)


@router.post(
    "/{transaction_id}/transitions",
    response_model=TransactionResponse,
    summary="Transition transaction state",
    description="Advance or branch transaction workflow state enforcing state machine rules.",
)
async def transition_transaction(
    transaction_id: UUID,
    request: TransitionTransactionRequest,
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    """Advance or branch transaction workflow state."""
    tx = await service.transition_transaction(transaction_id, request)
    return TransactionResponse.model_validate(tx)


@router.get(
    "/{transaction_id}/audit",
    response_model=AuditHistoryResponse,
    summary="Get transaction audit trail",
    description="Fetch chronological audit trail of state transitions for a transaction.",
)
async def get_transaction_audit(
    transaction_id: UUID,
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> AuditHistoryResponse:
    """Fetch chronological audit trail of state transitions."""
    audits = await service.get_audit_history(transaction_id)
    return AuditHistoryResponse(
        transaction_id=transaction_id,
        total_entries=len(audits),
        items=[TransactionAuditResponse.model_validate(audit) for audit in audits],
    )
