"""Expected-versus-actual evaluation for simulation scenario runs (P2-A8).

Pure comparison logic. It reads the operator-declared expectation and the
observed, persisted outcome and reports per-dimension results. It NEVER mutates
a decision, transaction, or response, and it NEVER lets an expectation override
the authoritative observed outcome.

Important: scenario "accuracy" here measures agreement between a small set of
hand-authored expectations and the pipeline's observed behaviour. It is NOT a
measure of real-world fraud-detection accuracy, model calibration, or
production effectiveness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.scenario_catalog import ScenarioExpectation

ACCURACY_DISCLAIMER = (
    "Scenario comparison reflects agreement with a small set of hand-authored "
    "expectations only. It is not a measure of real-world fraud-detection accuracy, "
    "statistical generalization, or production effectiveness. All outcomes are simulated."
)


class EvaluationCategory(StrEnum):
    """Result category for a single comparison dimension."""

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class ObservedOutcome:
    """The authoritative, persisted outcome observed for a scenario run."""

    workflow_status: str
    final_state: str | None = None
    policy_action: str | None = None
    response_type: str | None = None
    customer_action_required: str | None = None
    verification_outcome: str | None = None
    incomplete_stages: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationDimension:
    """A single expected-versus-actual comparison dimension."""

    name: str
    category: EvaluationCategory
    expected: str | None
    observed: str | None
    detail: str


@dataclass(frozen=True)
class ScenarioEvaluationResult:
    """Structured expected-versus-actual evaluation for a scenario run."""

    workflow_execution_success: bool
    dimensions: list[EvaluationDimension]
    incomplete_stages: list[str]
    missing_evidence: list[str]
    overall: EvaluationCategory
    disclaimer: str = ACCURACY_DISCLAIMER


def _compare(
    name: str, expected: str | None, observed: str | None, *, match_detail: str
) -> EvaluationDimension:
    if observed is None:
        return EvaluationDimension(
            name=name,
            category=EvaluationCategory.INCOMPLETE,
            expected=expected,
            observed=None,
            detail="No observed value was produced for this dimension.",
        )
    if expected == observed:
        return EvaluationDimension(
            name=name,
            category=EvaluationCategory.MATCH,
            expected=expected,
            observed=observed,
            detail=match_detail,
        )
    return EvaluationDimension(
        name=name,
        category=EvaluationCategory.MISMATCH,
        expected=expected,
        observed=observed,
        detail=f"Observed '{observed}' differs from the declared expectation '{expected}'.",
    )


def evaluate_scenario(
    expectation: ScenarioExpectation, observed: ObservedOutcome
) -> ScenarioEvaluationResult:
    """Compare the declared expectation against the observed, persisted outcome."""
    dimensions: list[EvaluationDimension] = [
        _compare(
            "policy_action",
            expectation.policy_action.value,
            observed.policy_action,
            match_detail="The authoritative policy action matched the expectation.",
        ),
        _compare(
            "final_simulated_state",
            expectation.final_state.value,
            observed.final_state,
            match_detail="The final simulated transaction state matched the expectation.",
        ),
        _compare(
            "response_type",
            expectation.response_type.value,
            observed.response_type,
            match_detail="The orchestrated response type matched the expectation.",
        ),
        _compare(
            "customer_intervention",
            expectation.customer_action_required.value,
            observed.customer_action_required,
            match_detail="The customer-facing intervention matched the expectation.",
        ),
    ]

    if expectation.verification_outcome is not None:
        dimensions.append(
            _compare(
                "verification_outcome",
                expectation.verification_outcome.value,
                observed.verification_outcome,
                match_detail="The customer verification outcome matched the expectation.",
            )
        )

    categories = {d.category for d in dimensions}
    if EvaluationCategory.INCOMPLETE in categories or observed.incomplete_stages:
        overall = EvaluationCategory.INCOMPLETE
    elif EvaluationCategory.MISMATCH in categories:
        overall = EvaluationCategory.MISMATCH
    else:
        overall = EvaluationCategory.MATCH

    return ScenarioEvaluationResult(
        workflow_execution_success=observed.workflow_status == "COMPLETED",
        dimensions=dimensions,
        incomplete_stages=list(observed.incomplete_stages),
        missing_evidence=list(observed.missing_evidence),
        overall=overall,
    )
