"""API routes for simulated transactions, state transitions, and audit trails."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.domain.risk_engine import RecommendedAction, RiskLevel
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.risk import (
    AssessTransactionRequest,
    RiskAssessmentResponse,
    TriggeredRuleResponse,
)
from app.schemas.transaction import (
    AuditHistoryResponse,
    CreateTransactionRequest,
    TransactionAuditResponse,
    TransactionListResponse,
    TransactionResponse,
    TransitionTransactionRequest,
)
from app.services.risk_service import RiskService
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/transactions", tags=["Transactions"])


def get_transaction_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TransactionService:
    """Dependency provider for TransactionService with request-scoped DB session."""
    repository = TransactionRepository(session)
    return TransactionService(repository)


def get_risk_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RiskService:
    """Dependency provider for RiskService with request-scoped DB session."""
    repository = TransactionRepository(session)
    transaction_service = TransactionService(repository)
    return RiskService(repository, transaction_service)


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


@router.post(
    "/{transaction_id}/assess",
    response_model=RiskAssessmentResponse,
    summary="Assess transaction risk",
    description=(
        "Deterministically evaluates transaction risk, advancing state through "
        "ASSESSING -> RISK_ASSESSED -> DECISION_READY."
    ),
)
async def assess_transaction(
    transaction_id: UUID,
    request: AssessTransactionRequest,
    service: Annotated[RiskService, Depends(get_risk_service)],
) -> RiskAssessmentResponse:
    """Evaluate deterministic risk rules and advance transaction lifecycle states."""
    domain_evidence = request.evidence.to_domain() if request.evidence else None
    _, assessment = await service.assess_transaction(
        transaction_id=transaction_id,
        evidence=domain_evidence,
        actor_type=request.actor_type,
        reason=request.reason,
        correlation_id=request.correlation_id,
    )
    return RiskAssessmentResponse(
        id=assessment.id,
        transaction_id=assessment.transaction_id,
        risk_score=assessment.risk_score,
        risk_level=RiskLevel(assessment.risk_level),
        recommended_action=RecommendedAction(assessment.recommended_action),
        explanation=assessment.explanation,
        triggered_rules=[
            TriggeredRuleResponse(
                rule_id=r["rule_id"],
                rule_name=r["rule_name"],
                description=r["description"],
                weight=r["weight"],
                severity=RiskLevel(r["severity"]),
                evidence=r["evidence"],
            )
            for r in assessment.triggered_rules
        ],
        supporting_evidence=assessment.supporting_evidence,
        missing_evidence=assessment.missing_evidence,
        source="backend",
        created_at=assessment.created_at,
    )


@router.get(
    "/{transaction_id}/assessment",
    response_model=RiskAssessmentResponse,
    summary="Get latest transaction assessment",
    description="Retrieve the most recent risk assessment result for a transaction.",
)
async def get_latest_transaction_assessment(
    transaction_id: UUID,
    service: Annotated[RiskService, Depends(get_risk_service)],
) -> RiskAssessmentResponse:
    """Retrieve the most recent risk assessment result."""
    assessment = await service.get_latest_assessment(transaction_id)
    return RiskAssessmentResponse(
        id=assessment.id,
        transaction_id=assessment.transaction_id,
        risk_score=assessment.risk_score,
        risk_level=RiskLevel(assessment.risk_level),
        recommended_action=RecommendedAction(assessment.recommended_action),
        explanation=assessment.explanation,
        triggered_rules=[
            TriggeredRuleResponse(
                rule_id=r["rule_id"],
                rule_name=r["rule_name"],
                description=r["description"],
                weight=r["weight"],
                severity=RiskLevel(r["severity"]),
                evidence=r["evidence"],
            )
            for r in assessment.triggered_rules
        ],
        supporting_evidence=assessment.supporting_evidence,
        missing_evidence=assessment.missing_evidence,
        source="backend",
        created_at=assessment.created_at,
    )
