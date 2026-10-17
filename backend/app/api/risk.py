"""API routes for deterministic risk assessment and scenario evaluation."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.domain.risk_engine import evaluate_risk
from app.domain.scenario_fixtures import SCENARIO_FIXTURES
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.risk import (
    RiskAssessmentResponse,
    TransactionEvidenceRequest,
    TriggeredRuleResponse,
)
from app.services.risk_service import RiskService
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/risk", tags=["Risk Engine"])


def get_risk_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RiskService:
    """Dependency provider for RiskService with request-scoped DB session."""
    repository = TransactionRepository(session)
    transaction_service = TransactionService(repository)
    return RiskService(repository, transaction_service)


@router.post(
    "/evaluate",
    response_model=RiskAssessmentResponse,
    summary="Evaluate transaction risk",
    description=(
        "Deterministically evaluates transaction features and evidence without side effects."
    ),
)
async def evaluate_transaction_risk(
    request: TransactionEvidenceRequest,
) -> RiskAssessmentResponse:
    """Perform stateless deterministic risk evaluation on provided transaction evidence."""
    domain_evidence = request.to_domain()
    result = evaluate_risk(domain_evidence)

    return RiskAssessmentResponse(
        risk_score=result.risk_score,
        risk_level=result.risk_level,
        recommended_action=result.recommended_action,
        explanation=result.explanation,
        triggered_rules=[
            TriggeredRuleResponse(
                rule_id=r.rule_id,
                rule_name=r.rule_name,
                description=r.description,
                weight=r.weight,
                severity=r.severity,
                evidence=r.evidence,
            )
            for r in result.triggered_rules
        ],
        supporting_evidence=result.supporting_evidence,
        missing_evidence=result.missing_evidence,
        source="backend",
    )


@router.get(
    "/scenarios",
    summary="List demo scenarios",
    description="Returns pre-configured feature inputs for the 6 demo fraud scenarios.",
)
async def list_demo_scenarios() -> list[dict[str, Any]]:
    """Retrieve pre-configured scenario feature inputs for demonstration and testing."""
    scenarios_list = []
    for key, data in SCENARIO_FIXTURES.items():
        ev = data["evidence"]
        scenarios_list.append(
            {
                "id": data["id"],
                "key": key,
                "title": data["title"],
                "summary": data["summary"],
                "evidence": {
                    "amount": str(ev.amount),
                    "currency": ev.currency,
                    "payment_rail": ev.payment_rail,
                    "recipient_name": ev.recipient_name,
                    "recipient_identifier": ev.recipient_identifier,
                    "purpose": ev.purpose,
                    "customer_id": ev.customer_id,
                    "is_first_time_recipient": ev.is_first_time_recipient,
                    "is_trusted_beneficiary": ev.is_trusted_beneficiary,
                    "recent_fd_liquidation": ev.recent_fd_liquidation,
                    "recent_fd_liquidation_amount": (
                        str(ev.recent_fd_liquidation_amount)
                        if ev.recent_fd_liquidation_amount
                        else None
                    ),
                    "active_call_present": ev.active_call_present,
                    "screen_sharing_active": ev.screen_sharing_active,
                    "voice_stress_detected": ev.voice_stress_detected,
                    "coercive_language_detected": ev.coercive_language_detected,
                    "guaranteed_return_claimed": ev.guaranteed_return_claimed,
                    "urgency_pressure_detected": ev.urgency_pressure_detected,
                    "instruction_to_ignore_bank_warnings": ev.instruction_to_ignore_bank_warnings,
                    "is_flagged_mule": ev.is_flagged_mule,
                    "fan_in_count_24h": ev.fan_in_count_24h,
                    "fan_out_count_24h": ev.fan_out_count_24h,
                    "payee_name_mismatch": ev.payee_name_mismatch,
                    "routing_mismatch": ev.routing_mismatch,
                    "invoice_verified": ev.invoice_verified,
                },
            }
        )
    return scenarios_list
