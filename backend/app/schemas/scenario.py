"""Pydantic schemas for the end-to-end scenario simulation dashboard (P2-A8)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScenarioExecutionMode(StrEnum):
    """Requested execution mode for a scenario run."""

    DETERMINISTIC = "DETERMINISTIC"  # Offline mock AI provider; reproducible.
    LIVE_PROVIDER = "LIVE_PROVIDER"  # Configured real AI provider (explicit opt-in).


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


class ScenarioTransactionSummary(BaseModel):
    """Summary of a scenario's simulated transaction inputs."""

    amount: str
    currency: str
    payment_rail: str
    recipient_name: str
    recipient_identifier: str
    purpose: str


class ScenarioExpectationSummary(BaseModel):
    """Operator-declared expectation (documentation only; never authoritative)."""

    policy_action: str
    final_state: str
    response_type: str
    customer_action_required: str
    verification_outcome: str | None = None
    limitations: list[str] = Field(default_factory=list)


class ScenarioSummary(BaseModel):
    """A catalogue entry describing one reusable scenario."""

    id: str
    version: str
    title: str
    description: str
    transaction: ScenarioTransactionSummary
    expectation: ScenarioExpectationSummary
    exercises_coercion_analysis: bool
    exercises_verification: bool


class ScenarioListResponse(BaseModel):
    """The full scenario catalogue and its version."""

    catalog_version: str
    total: int
    items: list[ScenarioSummary]


# ---------------------------------------------------------------------------
# Runs & timeline
# ---------------------------------------------------------------------------


class StartScenarioRunRequest(BaseModel):
    """Request to start a scenario run."""

    model_config = ConfigDict(extra="forbid")

    execution_mode: ScenarioExecutionMode = Field(
        default=ScenarioExecutionMode.DETERMINISTIC,
        description="DETERMINISTIC uses the offline mock AI provider; LIVE_PROVIDER opts in "
        "to the configured real provider.",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=128,
        description="Optional idempotency key. A repeated key returns the existing run.",
    )


class StageView(BaseModel):
    """A single explainability-timeline stage derived from real persisted artifacts."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    title: str
    status: str
    detail: str
    entity_type: str | None = None
    entity_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    error_category: str | None = None
    sequence: int


class ScenarioRunResponse(BaseModel):
    """A scenario run with its explainability timeline."""

    id: UUID
    scenario_id: str
    scenario_version: str
    catalog_version: str
    execution_mode: str
    status: str
    workflow_execution_success: bool
    ai_provider: str | None = None
    transaction_id: UUID | None = None
    final_state: str | None = None
    error_category: str | None = None
    detail: str | None = None
    stages: list[StageView] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    is_simulated: bool = True


class ScenarioRunListResponse(BaseModel):
    """A paginated list of scenario runs."""

    total: int
    limit: int
    offset: int
    items: list[ScenarioRunResponse]


class EvaluationDimensionResponse(BaseModel):
    """One expected-versus-actual comparison dimension."""

    name: str
    category: str
    expected: str | None = None
    observed: str | None = None
    detail: str


class ScenarioEvaluationResponse(BaseModel):
    """Expected-versus-actual evaluation for a scenario run."""

    run_id: UUID
    scenario_id: str
    scenario_version: str
    workflow_execution_success: bool
    overall: str
    dimensions: list[EvaluationDimensionResponse]
    incomplete_stages: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    disclaimer: str
    is_simulated: bool = True
