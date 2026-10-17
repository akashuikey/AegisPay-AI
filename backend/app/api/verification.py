"""Customer-facing simulated verification submission API (P2-A5).

This router is NOT behind the operator authentication boundary. Submissions are
authorized by a distinct, server-issued customer verification session token
(a different JWT ``type`` than the operator access token), so an operator login
is never treated as proof that the simulated customer verified their identity.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.investigations import get_default_ai_client
from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, VerificationError
from app.core.security import decode_customer_verification_token
from app.db.session import get_db_session
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.decision import DecisionResponse
from app.schemas.verification import SubmitVerificationRequest, SubmitVerificationResponse
from app.services.ai_client import AIInvestigationClient
from app.services.decision_workflow_service import DecisionWorkflowService
from app.services.investigation_service import InvestigationService
from app.services.risk_service import RiskService
from app.services.transaction_service import TransactionService
from app.services.verification_service import VerificationService, VerificationSubmitResult

router = APIRouter(prefix="/verification", tags=["Customer Verification"])

_customer_bearer = HTTPBearer(auto_error=False)


def get_verification_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> VerificationService:
    """Dependency provider composing the verification service with a request session."""
    repository = TransactionRepository(session)
    transaction_service = TransactionService(repository)
    risk_service = RiskService(repository, transaction_service)
    investigation_service = InvestigationService(repository, transaction_service, ai_client)
    workflow_service = DecisionWorkflowService(
        repository, transaction_service, risk_service, investigation_service
    )
    return VerificationService(repository, transaction_service, workflow_service, settings)


async def get_customer_verification_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_customer_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Validate the customer verification session token and return its bound claims."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing customer verification session token")
    return decode_customer_verification_token(credentials.credentials, settings)


def serialize_submit_result(result: VerificationSubmitResult) -> SubmitVerificationResponse:
    """Serialize a submission result for the API."""
    from app.api.transactions import _serialize_decision

    challenge = result.challenge
    attempts_remaining = max(challenge.max_attempts - challenge.attempt_count, 0)
    decision_response: DecisionResponse | None = None
    if result.decision is not None:
        decision_response = _serialize_decision(result.decision, result.transaction_state)
    return SubmitVerificationResponse(
        challenge_id=challenge.id,
        transaction_id=challenge.transaction_id,
        result=result.result.value,
        status=challenge.status,
        attempts_remaining=attempts_remaining,
        transaction_state=result.transaction_state,
        decision=decision_response,
    )


@router.post(
    "/{challenge_id}/submit",
    response_model=SubmitVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit a verification response",
    description=(
        "Submit a simulated OTP for a verification challenge using the customer verification "
        "session token. On success, the transaction is automatically re-evaluated under the "
        "deterministic policy (verification never settles on its own or overrides strong fraud "
        "evidence)."
    ),
)
async def submit_verification(
    challenge_id: UUID,
    request: SubmitVerificationRequest,
    context: Annotated[dict[str, str], Depends(get_customer_verification_context)],
    service: Annotated[VerificationService, Depends(get_verification_service)],
) -> SubmitVerificationResponse:
    """Submit a verification response bound to the customer verification session."""
    # Token/path binding: the session token must match the challenge being submitted.
    if context["challenge_id"] != str(challenge_id):
        raise VerificationError(
            "Verification session does not authorize this challenge",
            code="VERIFICATION_CHALLENGE_INVALID",
            status_code=404,
        )

    result = await service.submit(
        challenge_id=challenge_id,
        transaction_id=UUID(context["transaction_id"]),
        customer_id=context["customer_id"],
        otp=request.otp,
    )
    return serialize_submit_result(result)
