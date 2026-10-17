"""Unit tests for expected-versus-actual scenario evaluation (P2-A8)."""

from app.domain.decision_policy import PolicyAction, VerificationOutcome
from app.domain.response_orchestration import CustomerActionRequired, ResponseType
from app.domain.scenario_catalog import ScenarioExpectation
from app.domain.scenario_evaluation import (
    EvaluationCategory,
    ObservedOutcome,
    evaluate_scenario,
)
from app.domain.state_machine import TransactionState


def _expectation() -> ScenarioExpectation:
    return ScenarioExpectation(
        policy_action=PolicyAction.HOLD_FOR_INVESTIGATION,
        final_state=TransactionState.HELD_FOR_VERIFICATION,
        response_type=ResponseType.HOLD_PROTECTIVE,
        customer_action_required=CustomerActionRequired.CONTACT_BANK,
    )


def test_all_match_yields_overall_match() -> None:
    observed = ObservedOutcome(
        workflow_status="COMPLETED",
        final_state="HELD_FOR_VERIFICATION",
        policy_action="HOLD_FOR_INVESTIGATION",
        response_type="HOLD_PROTECTIVE",
        customer_action_required="CONTACT_BANK",
    )
    result = evaluate_scenario(_expectation(), observed)
    assert result.overall == EvaluationCategory.MATCH
    assert result.workflow_execution_success is True
    assert all(d.category == EvaluationCategory.MATCH for d in result.dimensions)


def test_wrong_action_yields_mismatch_but_preserves_observed() -> None:
    observed = ObservedOutcome(
        workflow_status="COMPLETED",
        final_state="SETTLED_SIMULATED",
        policy_action="ALLOW",
        response_type="ALLOW_SETTLED",
        customer_action_required="NONE",
    )
    result = evaluate_scenario(_expectation(), observed)
    assert result.overall == EvaluationCategory.MISMATCH
    action_dim = next(d for d in result.dimensions if d.name == "policy_action")
    assert action_dim.category == EvaluationCategory.MISMATCH
    # The observed value is preserved verbatim, never overwritten by the expectation.
    assert action_dim.observed == "ALLOW"
    assert action_dim.expected == "HOLD_FOR_INVESTIGATION"


def test_missing_observation_yields_incomplete() -> None:
    observed = ObservedOutcome(
        workflow_status="FAILED",
        incomplete_stages=["decision_policy"],
    )
    result = evaluate_scenario(_expectation(), observed)
    assert result.overall == EvaluationCategory.INCOMPLETE
    assert result.workflow_execution_success is False
    assert "decision_policy" in result.incomplete_stages


def test_verification_dimension_only_when_expected() -> None:
    exp = ScenarioExpectation(
        policy_action=PolicyAction.HOLD_FOR_INVESTIGATION,
        final_state=TransactionState.HELD_FOR_VERIFICATION,
        response_type=ResponseType.HOLD_PROTECTIVE,
        customer_action_required=CustomerActionRequired.CONTACT_BANK,
        verification_outcome=VerificationOutcome.SUCCEEDED,
    )
    observed = ObservedOutcome(
        workflow_status="COMPLETED",
        final_state="HELD_FOR_VERIFICATION",
        policy_action="HOLD_FOR_INVESTIGATION",
        response_type="HOLD_PROTECTIVE",
        customer_action_required="CONTACT_BANK",
        verification_outcome="SUCCEEDED",
    )
    result = evaluate_scenario(exp, observed)
    assert any(d.name == "verification_outcome" for d in result.dimensions)
    assert result.overall == EvaluationCategory.MATCH


def test_disclaimer_is_present_and_not_accuracy_claim() -> None:
    result = evaluate_scenario(_expectation(), ObservedOutcome(workflow_status="COMPLETED"))
    assert "not a measure of real-world" in result.disclaimer.lower()
