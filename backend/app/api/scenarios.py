"""REST endpoints for the end-to-end fraud simulation & explainability dashboard (P2-A8).

All routes are operator-authenticated (the router is mounted behind the operator
boundary in ``router.py``). Scenario creation and stage retries are idempotent.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.investigations import get_default_ai_client
from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, NotFoundError
from app.db.models import ScenarioRunModel
from app.db.session import get_db_session
from app.domain.scenario_catalog import (
    CATALOG_VERSION,
    ScenarioDefinition,
    VerificationBehavior,
    get_scenario,
    list_scenarios,
)
from app.domain.scenario_evaluation import evaluate_scenario
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.scenario import (
    EvaluationDimensionResponse,
    ScenarioEvaluationResponse,
    ScenarioExecutionMode,
    ScenarioExpectationSummary,
    ScenarioListResponse,
    ScenarioRunListResponse,
    ScenarioRunResponse,
    ScenarioSummary,
    ScenarioTransactionSummary,
    StageView,
    StartScenarioRunRequest,
)
from app.services.ai_client import AIInvestigationClient, MockGeminiClient
from app.services.scenario_orchestration_service import ScenarioOrchestrationService

router = APIRouter(prefix="/scenarios", tags=["Scenario Simulation & Explainability"])


def _build_service(
    session: AsyncSession,
    settings: Settings,
    live_ai_client: AIInvestigationClient,
    execution_mode: ScenarioExecutionMode,
) -> ScenarioOrchestrationService:
    """Construct the orchestration service with the AI client for the requested mode.

    Deterministic mode always uses a fresh offline mock client. Live mode uses the
    configured provider; it is never silently swapped for a mock.
    """
    ai_client: AIInvestigationClient = (
        MockGeminiClient()
        if execution_mode == ScenarioExecutionMode.DETERMINISTIC
        else live_ai_client
    )
    return ScenarioOrchestrationService(session, settings, ai_client, execution_mode)


def _serialize_scenario(scenario: ScenarioDefinition) -> ScenarioSummary:
    exp = scenario.expectation
    return ScenarioSummary(
        id=scenario.id,
        version=scenario.version,
        title=scenario.title,
        description=scenario.description,
        transaction=ScenarioTransactionSummary(
            amount=f"{scenario.transaction.amount:.2f}",
            currency=scenario.transaction.currency,
            payment_rail=scenario.transaction.payment_rail,
            recipient_name=scenario.transaction.recipient_name,
            recipient_identifier=scenario.transaction.recipient_identifier,
            purpose=scenario.transaction.purpose,
        ),
        expectation=ScenarioExpectationSummary(
            policy_action=exp.policy_action.value,
            final_state=exp.final_state.value,
            response_type=exp.response_type.value,
            customer_action_required=exp.customer_action_required.value,
            verification_outcome=(
                exp.verification_outcome.value if exp.verification_outcome else None
            ),
            limitations=list(exp.limitations),
        ),
        exercises_coercion_analysis=scenario.call_transcript is not None,
        exercises_verification=scenario.verification_behavior != VerificationBehavior.NONE,
    )


async def _serialize_run(
    run: ScenarioRunModel, repository: TransactionRepository
) -> ScenarioRunResponse:
    final_state: str | None = None
    if run.transaction_id is not None:
        tx = await repository.get_by_id(run.transaction_id)
        final_state = tx.state if tx is not None else None
    stages = [StageView.model_validate(s) for s in run.stages]
    stages.sort(key=lambda s: s.sequence)
    return ScenarioRunResponse(
        id=run.id,
        scenario_id=run.scenario_id,
        scenario_version=run.scenario_version,
        catalog_version=run.catalog_version,
        execution_mode=run.execution_mode,
        status=run.status,
        workflow_execution_success=run.status == "COMPLETED",
        ai_provider=run.ai_provider,
        transaction_id=run.transaction_id,
        final_state=final_state,
        error_category=run.error_category,
        detail=run.detail,
        stages=stages,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get("", response_model=ScenarioListResponse, summary="List simulation scenarios")
async def list_scenario_catalog() -> ScenarioListResponse:
    """Return the versioned scenario catalogue with declared expectations."""
    scenarios = list_scenarios()
    return ScenarioListResponse(
        catalog_version=CATALOG_VERSION,
        total=len(scenarios),
        items=[_serialize_scenario(s) for s in scenarios],
    )


@router.get("/runs", response_model=ScenarioRunListResponse, summary="List scenario runs")
async def list_runs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    live_ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    scenario_id: Annotated[str | None, Query()] = None,
) -> ScenarioRunListResponse:
    """List scenario runs (most recent first)."""
    service = _build_service(session, settings, live_ai_client, ScenarioExecutionMode.DETERMINISTIC)
    runs, total = await service.list_runs(limit, offset, scenario_id)
    return ScenarioRunListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[await _serialize_run(r, service.repository) for r in runs],
    )


@router.post(
    "/{scenario_id}/runs",
    response_model=ScenarioRunResponse,
    summary="Start a scenario run",
)
async def start_scenario_run(
    scenario_id: str,
    request: StartScenarioRunRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    live_ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
) -> ScenarioRunResponse:
    """Run a predefined scenario through the existing fraud-prevention workflow."""
    scenario = get_scenario(scenario_id)
    if scenario is None:
        raise NotFoundError(f"Unknown scenario '{scenario_id}'")

    idempotency_key = request.idempotency_key or f"{scenario_id}:{uuid4()}"
    service = _build_service(session, settings, live_ai_client, request.execution_mode)
    run, created = await service.start_run(scenario, idempotency_key)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return await _serialize_run(run, service.repository)


@router.get(
    "/runs/{run_id}",
    response_model=ScenarioRunResponse,
    summary="Get a scenario run and its explainability timeline",
)
async def get_scenario_run(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    live_ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
) -> ScenarioRunResponse:
    """Retrieve a run's current status and stage timeline."""
    service = _build_service(session, settings, live_ai_client, ScenarioExecutionMode.DETERMINISTIC)
    run = await service.get_run(run_id)
    if run is None:
        raise NotFoundError(f"Scenario run '{run_id}' was not found")
    return await _serialize_run(run, service.repository)


@router.get(
    "/runs/{run_id}/evaluation",
    response_model=ScenarioEvaluationResponse,
    summary="Get expected-versus-actual evaluation for a run",
)
async def get_run_evaluation(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    live_ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
) -> ScenarioEvaluationResponse:
    """Compare the scenario's declared expectation with the observed, persisted outcome."""
    service = _build_service(session, settings, live_ai_client, ScenarioExecutionMode.DETERMINISTIC)
    run = await service.get_run(run_id)
    if run is None:
        raise NotFoundError(f"Scenario run '{run_id}' was not found")
    scenario = get_scenario(run.scenario_id)
    if scenario is None:
        raise NotFoundError(
            f"Scenario '{run.scenario_id}' for run '{run_id}' is no longer in the catalogue"
        )

    observed = await service.build_observed_outcome(run)
    result = evaluate_scenario(scenario.expectation, observed)
    return ScenarioEvaluationResponse(
        run_id=run.id,
        scenario_id=run.scenario_id,
        scenario_version=run.scenario_version,
        workflow_execution_success=result.workflow_execution_success,
        overall=result.overall.value,
        dimensions=[
            EvaluationDimensionResponse(
                name=d.name,
                category=d.category.value,
                expected=d.expected,
                observed=d.observed,
                detail=d.detail,
            )
            for d in result.dimensions
        ],
        incomplete_stages=result.incomplete_stages,
        missing_evidence=result.missing_evidence,
        disclaimer=result.disclaimer,
    )


@router.post(
    "/runs/{run_id}/retry",
    response_model=ScenarioRunResponse,
    summary="Retry a failed scenario run",
)
async def retry_scenario_run(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    live_ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
) -> ScenarioRunResponse:
    """Safely re-run a failed scenario; idempotent sub-steps avoid duplicates."""
    # Read the run first to recover its original execution mode.
    reader = _build_service(session, settings, live_ai_client, ScenarioExecutionMode.DETERMINISTIC)
    run = await reader.get_run(run_id)
    if run is None:
        raise NotFoundError(f"Scenario run '{run_id}' was not found")
    if run.status != "FAILED":
        raise ConflictError(
            f"Scenario run '{run_id}' is in state '{run.status}' and is not retryable",
            details={"run_id": str(run_id), "status": run.status},
        )
    scenario = get_scenario(run.scenario_id)
    if scenario is None:
        raise NotFoundError(
            f"Scenario '{run.scenario_id}' for run '{run_id}' is no longer in the catalogue"
        )

    mode = ScenarioExecutionMode(run.execution_mode)
    service = _build_service(session, settings, live_ai_client, mode)
    updated = await service.retry_run(run, scenario)
    return await _serialize_run(updated, service.repository)
