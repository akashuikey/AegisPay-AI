"""REST endpoints for automated fraud response orchestration and customer interventions (P2-A7).

Provides:
- POST /api/v1/transactions/{id}/respond (Operator-authenticated response orchestration)
- GET /api/v1/transactions/{id}/responses (Operator-authenticated response history)
- GET /api/v1/transactions/{id}/responses/latest (Operator-authenticated latest response)
- GET /api/v1/transactions/{id}/intervention (Operator or customer-scoped intervention status)
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_operator
from app.api.investigations import get_default_ai_client
from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, NotFoundError
from app.core.security import decode_access_token, decode_customer_verification_token
from app.db.models import OperatorModel
from app.db.session import get_db_session
from app.domain.state_machine import ActorType
from app.repositories.operator_repository import OperatorRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.fraud_response import (
    CustomerInterventionResponse,
    ExecuteResponseRequest,
    FraudResponseDetails,
)
from app.services.ai_client import AIInvestigationClient
from app.services.decision_workflow_service import DecisionWorkflowService
from app.services.investigation_service import InvestigationService
from app.services.notification_service import SimulatedNotificationService
from app.services.response_orchestration_service import ResponseOrchestrationService
from app.services.risk_service import RiskService
from app.services.transaction_service import TransactionService

router = APIRouter(tags=["Fraud Response & Customer Intervention"])

_bearer_scheme = HTTPBearer(auto_error=False)


def get_response_orchestration_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
) -> ResponseOrchestrationService:
    """Dependency provider composing the response orchestration service."""
    repository = TransactionRepository(session)
    transaction_service = TransactionService(repository)
    risk_service = RiskService(repository, transaction_service)
    investigation_service = InvestigationService(repository, transaction_service, ai_client)
    workflow_service = DecisionWorkflowService(
        repository, transaction_service, risk_service, investigation_service
    )
    notification_service = SimulatedNotificationService()
    return ResponseOrchestrationService(
        repository, transaction_service, workflow_service, notification_service
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


async def authorize_operator_or_customer(
    transaction_id: UUID,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    operator: Annotated[OperatorModel | None, Depends(get_current_operator_optional)] = None,
) -> dict[str, str]:
    """Authorize access by an operator or a customer session token bound to this transaction."""
    if operator is not None:
        return {"role": "operator", "sub": str(operator.id)}

    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication credentials required to access intervention")

    token = credentials.credentials
    try:
        claims = decode_customer_verification_token(token, settings)
        if claims.get("transaction_id") != str(transaction_id):
            raise AuthenticationError("Customer token does not match the requested transaction")
        return {"role": "customer", "sub": claims.get("customer_id", "unknown")}
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError("Invalid or expired authentication credentials") from exc


@router.post(
    "/transactions/{transaction_id}/respond",
    response_model=FraudResponseDetails,
    summary="Execute automated fraud response orchestration",
)
async def execute_automated_response(
    transaction_id: UUID,
    request: ExecuteResponseRequest,
    response: Response,
    service: Annotated[ResponseOrchestrationService, Depends(get_response_orchestration_service)],
    operator: Annotated[OperatorModel, Depends(get_current_operator)],
) -> FraudResponseDetails:
    """Run automated fraud response orchestration and dispatch simulated customer notification.

    Returns HTTP 201 when a new response is executed, or HTTP 200 on idempotent replay.
    """
    result_response, _, created = await service.orchestrate_response(
        transaction_id,
        idempotency_key=request.idempotency_key,
        channel=request.channel,
        simulate_notification_failure=request.simulate_notification_failure,
        actor_type=ActorType.POLICY_ENGINE,
    )

    if created:
        response.status_code = status.HTTP_201_CREATED
    else:
        response.status_code = status.HTTP_200_OK

    return FraudResponseDetails.model_validate(result_response)


@router.get(
    "/transactions/{transaction_id}/responses",
    response_model=list[FraudResponseDetails],
    summary="List all responses executed for a transaction",
)
async def list_transaction_responses(
    transaction_id: UUID,
    service: Annotated[ResponseOrchestrationService, Depends(get_response_orchestration_service)],
    operator: Annotated[OperatorModel, Depends(get_current_operator)],
) -> list[FraudResponseDetails]:
    """Retrieve full chronological response history for a transaction."""
    responses = await service.list_responses(transaction_id)
    return [FraudResponseDetails.model_validate(r) for r in responses]


@router.get(
    "/transactions/{transaction_id}/responses/latest",
    response_model=FraudResponseDetails,
    summary="Get latest executed response for a transaction",
)
async def get_latest_transaction_response(
    transaction_id: UUID,
    service: Annotated[ResponseOrchestrationService, Depends(get_response_orchestration_service)],
    operator: Annotated[OperatorModel, Depends(get_current_operator)],
) -> FraudResponseDetails:
    """Retrieve the latest response executed for a transaction."""
    latest = await service.get_latest_response(transaction_id)
    if latest is None:
        raise NotFoundError(f"No automated response found for transaction {transaction_id}")
    return FraudResponseDetails.model_validate(latest)


@router.get(
    "/transactions/{transaction_id}/intervention",
    response_model=CustomerInterventionResponse,
    summary="Get customer-facing intervention status",
)
async def get_customer_intervention_status(
    transaction_id: UUID,
    service: Annotated[ResponseOrchestrationService, Depends(get_response_orchestration_service)],
    auth_ctx: Annotated[dict[str, str], Depends(authorize_operator_or_customer)],
) -> CustomerInterventionResponse:
    """Retrieve customer-safe intervention details.

    Zero sensitive fraud scoring, triggered rules, or confidential credentials are exposed.
    Accessible by operators or customer verification session holders.
    """
    return await service.get_customer_intervention(transaction_id)
