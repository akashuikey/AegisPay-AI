"""API routes for simulated transactions, state transitions, and audit trails."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.conversations import serialize_conversation_response
from app.api.investigations import (
    _serialize_investigation_response,
    get_default_ai_client,
    get_investigation_service,
)
from app.db.models import TransactionDecisionModel
from app.db.session import get_db_session
from app.domain.decision_policy import PolicyAction
from app.domain.risk_engine import RecommendedAction, RiskLevel
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.decision import DecisionResponse, EvaluateTransactionRequest
from app.schemas.investigation import (
    AddConversationTurnRequest,
    InvestigateTransactionRequest,
    InvestigationConversationListResponse,
    InvestigationConversationResponse,
    InvestigationListResponse,
    StartConversationRequest,
)
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
from app.services.ai_client import AIInvestigationClient
from app.services.decision_workflow_service import DecisionWorkflowService
from app.services.investigation_service import InvestigationService
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


@router.get(
    "/{transaction_id}/investigations",
    response_model=InvestigationListResponse,
    summary="List transaction investigations",
    description=(
        "Retrieve chronological list of AI forensic investigations conducted for a transaction."
    ),
)
async def list_transaction_investigations(
    transaction_id: UUID,
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationListResponse:
    """Retrieve all AI investigations for a specific transaction."""
    records = await service.list_investigations_for_transaction(transaction_id)
    return InvestigationListResponse(
        transaction_id=transaction_id,
        total_entries=len(records),
        items=[_serialize_investigation_response(record) for record in records],
    )


@router.post(
    "/{transaction_id}/conversations",
    response_model=InvestigationConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start or resume investigation conversation",
    description=(
        "Initiates a new multi-turn AI investigation conversation for the transaction, "
        "or resumes the active conversation if one already exists."
    ),
)
async def start_or_get_transaction_conversation(
    transaction_id: UUID,
    request: StartConversationRequest,
    response: Response,
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationConversationResponse:
    """Start a new investigation conversation or resume active one."""
    existing = await service.repository.get_active_conversation_for_transaction(transaction_id)
    record = await service.start_or_get_conversation(transaction_id, request)
    if existing and existing.id == record.id and not request.initial_message:
        response.status_code = status.HTTP_200_OK
    return serialize_conversation_response(record)


@router.get(
    "/{transaction_id}/conversations/current",
    response_model=InvestigationConversationResponse,
    summary="Get current investigation conversation",
    description=(
        "Retrieve the active (or latest) multi-turn investigation conversation for a transaction."
    ),
)
async def get_current_transaction_conversation(
    transaction_id: UUID,
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationConversationResponse:
    """Fetch the active or latest conversation for a transaction."""
    record = await service.repository.get_active_conversation_for_transaction(transaction_id)
    if not record:
        from app.core.errors import NotFoundError

        raise NotFoundError(
            f"No investigation conversation found for transaction '{transaction_id}'"
        )
    return serialize_conversation_response(record)


@router.get(
    "/{transaction_id}/conversations",
    response_model=InvestigationConversationListResponse,
    summary="List transaction conversations",
    description="Retrieve all multi-turn investigation conversations recorded for a transaction.",
)
async def list_transaction_conversations(
    transaction_id: UUID,
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationConversationListResponse:
    """Fetch all conversations for a transaction."""
    records = await service.list_conversations_for_transaction(transaction_id)
    return InvestigationConversationListResponse(
        transaction_id=transaction_id,
        total_entries=len(records),
        items=[serialize_conversation_response(record) for record in records],
    )


@router.post(
    "/{transaction_id}/conversations/{conversation_id}/turns",
    response_model=InvestigationConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit turn to transaction conversation",
    description=(
        "Submit an operator message or customer evidence turn into a transaction's "
        "investigation conversation."
    ),
)
async def submit_transaction_conversation_turn(
    transaction_id: UUID,
    conversation_id: UUID,
    request: AddConversationTurnRequest,
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationConversationResponse:
    """Submit a turn to conversation while enforcing transaction scoping."""
    record = await service.submit_conversation_turn(
        conversation_id=conversation_id,
        request=request,
        transaction_id=transaction_id,
    )
    return serialize_conversation_response(record)


def get_decision_workflow_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
) -> DecisionWorkflowService:
    """Dependency provider wiring the automated decision workflow with a request session."""
    repository = TransactionRepository(session)
    transaction_service = TransactionService(repository)
    risk_service = RiskService(repository, transaction_service)
    investigation_service = InvestigationService(repository, transaction_service, ai_client)
    return DecisionWorkflowService(
        repository, transaction_service, risk_service, investigation_service
    )


def _serialize_decision(
    record: TransactionDecisionModel, transaction_state: str
) -> DecisionResponse:
    """Serialize a persisted decision record plus the current transaction state."""
    return DecisionResponse(
        id=record.id,
        transaction_id=record.transaction_id,
        transaction_state=transaction_state,
        policy_version=record.policy_version,
        action=PolicyAction(record.action),
        risk_score=record.risk_score,
        risk_level=RiskLevel(record.risk_level),
        requires_verification=record.requires_verification,
        provider_failed=record.provider_failed,
        investigation_performed=record.investigation_id is not None or record.provider_failed,
        from_state=record.from_state,
        to_state=record.to_state,
        workflow_status=record.workflow_status,
        reason_codes=record.reason_codes,
        triggered_rule_ids=record.triggered_rule_ids,
        investigation_finding_refs=record.investigation_finding_refs,
        supporting_evidence_refs=record.supporting_evidence_refs,
        missing_information=record.missing_information,
        explanation=record.explanation,
        created_at=record.created_at,
    )


@router.post(
    "/{transaction_id}/evaluate",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run automated decision workflow",
    description=(
        "Runs the automated end-to-end workflow: deterministic risk assessment, optional "
        "contextual investigation, deterministic policy decision, and the corresponding "
        "simulated state transition. Idempotent: a repeat request returns the existing decision."
    ),
)
async def evaluate_transaction(
    transaction_id: UUID,
    request: EvaluateTransactionRequest,
    response: Response,
    service: Annotated[DecisionWorkflowService, Depends(get_decision_workflow_service)],
) -> DecisionResponse:
    """Execute the automated risk + policy decision workflow for a transaction."""
    evidence = request.evidence.to_domain() if request.evidence else None

    investigation_request: InvestigateTransactionRequest | None = None
    if request.investigation is not None:
        inv = request.investigation
        investigation_request = InvestigateTransactionRequest(
            transaction_id=transaction_id,
            customer_statements=inv.customer_statements,
            document_extractions=inv.document_extractions,
            telephony_telemetry=inv.telephony_telemetry,
            recipient_intelligence=inv.recipient_intelligence,
            coercion_cues=inv.coercion_cues,
            correlation_id=request.correlation_id,
        )

    decision, tx, created = await service.evaluate(
        transaction_id=transaction_id,
        evidence=evidence,
        investigation_request=investigation_request,
        run_investigation=request.run_investigation,
        correlation_id=request.correlation_id,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return _serialize_decision(decision, tx.state)


@router.get(
    "/{transaction_id}/decision",
    response_model=DecisionResponse,
    summary="Get latest automated decision",
    description="Retrieve the most recent automated decision and its reasons for a transaction.",
)
async def get_transaction_decision(
    transaction_id: UUID,
    service: Annotated[DecisionWorkflowService, Depends(get_decision_workflow_service)],
) -> DecisionResponse:
    """Fetch the latest automated decision for a transaction."""
    decision = await service.get_latest_decision(transaction_id)
    if decision is None:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"No automated decision found for transaction '{transaction_id}'")
    tx = await service.transaction_service.get_transaction(transaction_id)
    return _serialize_decision(decision, tx.state)
