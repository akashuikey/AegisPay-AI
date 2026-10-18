"""FastAPI REST endpoints for dynamic simulated customer calls and chat dialogue (Option A)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.investigations import get_default_ai_client
from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, AuthorizationError, NotFoundError
from app.core.logging import get_logger
from app.core.security import decode_access_token, decode_customer_verification_token
from app.db.models import OperatorModel, TransactionCallSessionModel
from app.db.session import get_db_session
from app.domain.customer_dialogue import (
    CallSessionDirection,
    CallSessionStatus,
    DialogueChannel,
)
from app.repositories.operator_repository import OperatorRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.customer_dialogue import (
    CallSessionResponse,
    CustomerDialogueTurnResponse,
    DeclineCallSessionRequest,
    InitiateCallSessionRequest,
    LiveAnalysisResponse,
    SubmitCustomerDialogueTurnRequest,
    TranscriptSegmentResponse,
)
from app.services.ai_client import AIInvestigationClient
from app.services.coercion_service import CoercionService
from app.services.customer_dialogue_service import CustomerDialogueService
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)

router = APIRouter(tags=["Simulated Customer Calls & Dialogue"])

_bearer_scheme = HTTPBearer(auto_error=False)


def get_customer_dialogue_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CustomerDialogueService:
    """Dependency provider composing CustomerDialogueService."""
    repository = TransactionRepository(session)
    transaction_service = TransactionService(repository)
    coercion_service = CoercionService(repository, transaction_service, ai_client)
    return CustomerDialogueService(
        repository=repository,
        transaction_service=transaction_service,
        ai_client=ai_client,
        settings=settings,
        coercion_service=coercion_service,
    )


async def get_current_operator_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OperatorModel | None:
    """Resolve operator if a valid operator bearer token is supplied, else return None."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        operator_id = decode_access_token(credentials.credentials, settings)
        op_repo = OperatorRepository(session)
        operator = await op_repo.get_by_id(UUID(operator_id))
        if operator is not None and operator.is_active:
            return operator
    except Exception:
        return None
    return None


async def authorize_call_access(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    operator: Annotated[OperatorModel | None, Depends(get_current_operator_optional)],
) -> dict[str, str]:
    """Authorize access by an operator or a customer session token.

    A customer verification token is bound to a single transaction; its
    ``transaction_id`` claim is returned so route handlers can confirm the token
    is being used only against its own transaction's call sessions.
    """
    if operator is not None:
        return {"role": "operator", "sub": str(operator.id)}

    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication credentials required for call session")

    token = credentials.credentials
    try:
        claims = decode_customer_verification_token(token, settings)
        return {
            "role": "customer",
            "sub": claims.get("customer_id", "unknown"),
            "transaction_id": claims.get("transaction_id", ""),
        }
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError("Invalid or expired authentication credentials") from exc


def _is_operator(auth_ctx: dict[str, str]) -> bool:
    """Return True if the authorized principal is an operator."""
    return auth_ctx.get("role") == "operator"


def _enforce_transaction_scope(auth_ctx: dict[str, str], transaction_id: UUID) -> None:
    """Reject a customer token used against a transaction it is not bound to.

    Operators have console-wide access; a customer verification session may act
    only on its own transaction (prevents horizontal access to other customers'
    call sessions).
    """
    if _is_operator(auth_ctx):
        return
    bound = auth_ctx.get("transaction_id") or ""
    if bound != str(transaction_id):
        raise AuthorizationError("This session is not authorized for the requested transaction")


async def _enforce_call_scope(
    service: CustomerDialogueService,
    auth_ctx: dict[str, str],
    call_id: UUID,
) -> TransactionCallSessionModel:
    """Load a call session and enforce the customer transaction scope before acting.

    Returns the loaded session so the caller can avoid a second fetch. Operators
    skip the scope check but the session is still loaded (and 404s if missing).
    """
    session = await service.get_call_session(call_id)
    _enforce_transaction_scope(auth_ctx, session.transaction_id)
    return session


def _to_call_session_response(
    session: TransactionCallSessionModel, *, include_internal: bool
) -> CallSessionResponse:
    """Format a database session entity into a typed API response.

    ``include_internal`` controls whether confidential forensic fields (internal
    observations, uncertainty notes, suggested action, coercion cues, risk
    sentiment, evidence references) are exposed. These are operator-only bank
    intelligence and must never be returned to a customer session, which sees only
    the conversational content it is party to.
    """
    turns_responses: list[CustomerDialogueTurnResponse] = []
    if session.conversation and session.conversation.turns:
        for t in session.conversation.turns:
            meta = t.model_metadata or {}
            if include_internal:
                turns_responses.append(
                    CustomerDialogueTurnResponse(
                        id=t.id,
                        turn_index=t.turn_index,
                        role=t.role,
                        content=t.content,
                        evidence_provenance=t.evidence_provenance,
                        evidence_references=t.evidence_references or [],
                        internal_observations=meta.get("internal_observations", []),
                        uncertainty_notes=meta.get("uncertainty_notes", []),
                        suggested_action=meta.get("suggested_action"),
                        is_terminal_turn=bool(meta.get("is_terminal_turn", False)),
                        risk_sentiment=t.risk_sentiment,
                        coercion_cues=meta.get("coercion_cues", []),
                        created_at=t.created_at,
                    )
                )
            else:
                turns_responses.append(
                    CustomerDialogueTurnResponse(
                        id=t.id,
                        turn_index=t.turn_index,
                        role=t.role,
                        content=t.content,
                        evidence_provenance=None,
                        evidence_references=[],
                        internal_observations=[],
                        uncertainty_notes=[],
                        suggested_action=None,
                        is_terminal_turn=bool(meta.get("is_terminal_turn", False)),
                        risk_sentiment=None,
                        coercion_cues=[],
                        created_at=t.created_at,
                    )
                )

    return CallSessionResponse(
        id=session.id,
        transaction_id=session.transaction_id,
        conversation_id=session.conversation_id,
        channel=DialogueChannel(session.channel),
        status=CallSessionStatus(session.status),
        direction=CallSessionDirection(session.direction),
        attempt_number=session.attempt_number,
        idempotency_key=session.idempotency_key,
        started_at=session.started_at,
        connected_at=session.connected_at,
        ended_at=session.ended_at,
        duration_seconds=session.duration_seconds,
        failure_reason=session.failure_reason,
        customer_phone_masked=session.customer_phone_masked,
        version=session.version,
        turns=turns_responses,
        coercion_analysis_id=session.coercion_analysis_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/transactions/{transaction_id}/calls",
    response_model=CallSessionResponse,
    summary="Initiate a simulated customer call or chat session",
)
async def initiate_call_session(
    transaction_id: UUID,
    payload: InitiateCallSessionRequest,
    response: Response,
    service: Annotated[CustomerDialogueService, Depends(get_customer_dialogue_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_call_access)],
) -> CallSessionResponse:
    """Initiate a simulated customer phone call or interactive chat session.

    Generates the initial AI inquiry dynamically based on transaction context.
    Idempotent on repeated calls with identical idempotency_key.
    """
    _enforce_transaction_scope(auth_ctx, transaction_id)
    if not _is_operator(auth_ctx):
        raise AuthorizationError(
            "Customer tokens are not permitted to initiate outbound call sessions; "
            "calls must be initiated by authorized bank policy or operators."
        )
    session, created = await service.initiate_call_session(
        transaction_id=transaction_id,
        channel=payload.channel,
        idempotency_key=payload.idempotency_key,
        correlation_id=payload.correlation_id,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _to_call_session_response(session, include_internal=_is_operator(auth_ctx))


@router.get(
    "/transactions/{transaction_id}/calls",
    response_model=list[CallSessionResponse],
    summary="List all simulated call sessions for a transaction",
)
async def list_call_sessions(
    transaction_id: UUID,
    service: Annotated[CustomerDialogueService, Depends(get_customer_dialogue_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_call_access)],
) -> list[CallSessionResponse]:
    """Retrieve all simulated call sessions for a transaction in chronological order."""
    _enforce_transaction_scope(auth_ctx, transaction_id)
    sessions = await service.list_sessions_for_transaction(transaction_id)
    include_internal = _is_operator(auth_ctx)
    return [_to_call_session_response(s, include_internal=include_internal) for s in sessions]


@router.get(
    "/transactions/{transaction_id}/calls/latest",
    response_model=CallSessionResponse,
    summary="Get the latest call session for a transaction",
)
async def get_latest_call_session(
    transaction_id: UUID,
    service: Annotated[CustomerDialogueService, Depends(get_customer_dialogue_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_call_access)],
) -> CallSessionResponse:
    """Retrieve the most recent call session for a transaction."""
    _enforce_transaction_scope(auth_ctx, transaction_id)
    session = await service.get_latest_session_for_transaction(transaction_id)
    if session is None:
        raise NotFoundError(f"No call sessions found for transaction '{transaction_id}'")
    return _to_call_session_response(session, include_internal=_is_operator(auth_ctx))


@router.get(
    "/calls/{call_id}",
    response_model=CallSessionResponse,
    summary="Get details of a specific call session",
)
async def get_call_session_by_id(
    call_id: UUID,
    service: Annotated[CustomerDialogueService, Depends(get_customer_dialogue_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_call_access)],
) -> CallSessionResponse:
    """Retrieve a call session and its full dialogue turn history by ID."""
    session = await _enforce_call_scope(service, auth_ctx, call_id)
    return _to_call_session_response(session, include_internal=_is_operator(auth_ctx))


@router.get(
    "/calls/{call_id}/transcript",
    response_model=list[TranscriptSegmentResponse],
    summary="Get the persisted live-voice transcript for a call session",
)
async def get_call_transcript(
    call_id: UUID,
    service: Annotated[CustomerDialogueService, Depends(get_customer_dialogue_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_call_access)],
) -> list[TranscriptSegmentResponse]:
    """Return the ordered final transcript segments recorded during a live call."""
    await _enforce_call_scope(service, auth_ctx, call_id)
    segments = await service.repository.list_transcript_segments(call_id)
    return [TranscriptSegmentResponse.model_validate(s) for s in segments]


@router.get(
    "/calls/{call_id}/live-analysis",
    response_model=LiveAnalysisResponse,
    summary="Get the latest incremental evidence analysis for a call (operator-only)",
)
async def get_call_live_analysis(
    call_id: UUID,
    service: Annotated[CustomerDialogueService, Depends(get_customer_dialogue_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_call_access)],
) -> LiveAnalysisResponse:
    """Return the most recent live evidence-analysis snapshot.

    Internal forensic intelligence: restricted to operators.
    """
    await _enforce_call_scope(service, auth_ctx, call_id)
    if not _is_operator(auth_ctx):
        raise AuthorizationError("Live evidence analysis is restricted to operators")
    analysis = await service.repository.get_latest_live_analysis(call_id)
    if analysis is None:
        raise NotFoundError(f"No live analysis available for call '{call_id}'")
    return LiveAnalysisResponse.model_validate(analysis)


@router.post(
    "/calls/{call_id}/connect",
    response_model=CallSessionResponse,
    summary="Customer answers incoming call (transitions to CONNECTED)",
)
async def connect_call_session(
    call_id: UUID,
    service: Annotated[CustomerDialogueService, Depends(get_customer_dialogue_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_call_access)],
) -> CallSessionResponse:
    """Customer answers the incoming call. Transitions session to CONNECTED."""
    await _enforce_call_scope(service, auth_ctx, call_id)
    session = await service.connect_call_session(call_id)
    return _to_call_session_response(session, include_internal=_is_operator(auth_ctx))


@router.post(
    "/calls/{call_id}/turns",
    response_model=CallSessionResponse,
    summary="Submit a customer response turn and receive Gemini's next question",
)
async def submit_dialogue_turn(
    call_id: UUID,
    payload: SubmitCustomerDialogueTurnRequest,
    service: Annotated[CustomerDialogueService, Depends(get_customer_dialogue_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_call_access)],
) -> CallSessionResponse:
    """Submit a customer statement (verbal speech or typed chat).

    Gemini dynamically analyzes the input, updates internal observations,
    and returns the next relevant inquiry or completion message.
    """
    await _enforce_call_scope(service, auth_ctx, call_id)
    session, _ = await service.submit_turn(
        call_id=call_id,
        customer_message=payload.customer_message,
        source=payload.source,
        client_turn_id=payload.client_turn_id,
        correlation_id=payload.correlation_id,
    )
    return _to_call_session_response(session, include_internal=_is_operator(auth_ctx))


@router.post(
    "/calls/{call_id}/complete",
    response_model=CallSessionResponse,
    summary="Complete a call session",
)
async def complete_call_session(
    call_id: UUID,
    service: Annotated[CustomerDialogueService, Depends(get_customer_dialogue_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_call_access)],
) -> CallSessionResponse:
    """Mark the call session as completed."""
    await _enforce_call_scope(service, auth_ctx, call_id)
    session = await service.complete_call_session(call_id)
    return _to_call_session_response(session, include_internal=_is_operator(auth_ctx))


@router.post(
    "/calls/{call_id}/decline",
    response_model=CallSessionResponse,
    summary="Decline an incoming simulated call",
)
async def decline_call_session(
    call_id: UUID,
    service: Annotated[CustomerDialogueService, Depends(get_customer_dialogue_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_call_access)],
    payload: DeclineCallSessionRequest | None = None,
) -> CallSessionResponse:
    """Customer declines the incoming call. Transitions session to DECLINED."""
    await _enforce_call_scope(service, auth_ctx, call_id)
    reason = payload.reason if payload else None
    session = await service.decline_call_session(call_id, reason=reason)
    return _to_call_session_response(session, include_internal=_is_operator(auth_ctx))
