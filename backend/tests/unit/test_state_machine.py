"""Unit tests for the transaction workflow state machine and transition policy."""

import pytest

from app.core.errors import InvalidStateTransitionError
from app.domain.state_machine import (
    ALLOWED_TRANSITIONS,
    ActorType,
    TransactionState,
    can_transition,
    is_terminal,
    validate_transition,
)


def test_transaction_state_enum_members() -> None:
    """Verify all 10 authoritative workflow states exist."""
    expected_states = {
        "INITIATED",
        "ASSESSING",
        "RISK_ASSESSED",
        "DECISION_READY",
        "VERIFICATION_REQUIRED",
        "HELD_FOR_VERIFICATION",
        "INVESTIGATING",
        "HUMAN_REVIEW",
        "SETTLED_SIMULATED",
        "CANCELLED_SIMULATED",
    }
    actual_states = {s.value for s in TransactionState}
    assert actual_states == expected_states


def test_actor_type_enum_members() -> None:
    """Verify required actor types exist."""
    assert ActorType.SYSTEM.value == "SYSTEM"
    assert ActorType.CUSTOMER.value == "CUSTOMER"
    assert ActorType.INVESTIGATOR.value == "INVESTIGATOR"
    assert ActorType.POLICY_ENGINE.value == "POLICY_ENGINE"


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        (TransactionState.INITIATED, TransactionState.ASSESSING),
        (TransactionState.INITIATED, TransactionState.CANCELLED_SIMULATED),
        (TransactionState.ASSESSING, TransactionState.RISK_ASSESSED),
        (TransactionState.ASSESSING, TransactionState.HUMAN_REVIEW),
        (TransactionState.RISK_ASSESSED, TransactionState.DECISION_READY),
        (TransactionState.RISK_ASSESSED, TransactionState.HUMAN_REVIEW),
        (TransactionState.DECISION_READY, TransactionState.VERIFICATION_REQUIRED),
        (TransactionState.DECISION_READY, TransactionState.HELD_FOR_VERIFICATION),
        (TransactionState.DECISION_READY, TransactionState.SETTLED_SIMULATED),
        (TransactionState.DECISION_READY, TransactionState.CANCELLED_SIMULATED),
        (TransactionState.DECISION_READY, TransactionState.HUMAN_REVIEW),
        (TransactionState.VERIFICATION_REQUIRED, TransactionState.INVESTIGATING),
        (TransactionState.VERIFICATION_REQUIRED, TransactionState.CANCELLED_SIMULATED),
        (TransactionState.HELD_FOR_VERIFICATION, TransactionState.INVESTIGATING),
        (TransactionState.HELD_FOR_VERIFICATION, TransactionState.CANCELLED_SIMULATED),
        (TransactionState.INVESTIGATING, TransactionState.DECISION_READY),
        (TransactionState.INVESTIGATING, TransactionState.HUMAN_REVIEW),
        (TransactionState.INVESTIGATING, TransactionState.CANCELLED_SIMULATED),
        (TransactionState.HUMAN_REVIEW, TransactionState.DECISION_READY),
        (TransactionState.HUMAN_REVIEW, TransactionState.HELD_FOR_VERIFICATION),
        (TransactionState.HUMAN_REVIEW, TransactionState.CANCELLED_SIMULATED),
    ],
)
def test_allowed_transitions_succeed(
    from_state: TransactionState, to_state: TransactionState
) -> None:
    """Ensure every permitted state transition validates successfully."""
    assert can_transition(from_state, to_state) is True
    # Should not raise exception
    validate_transition(from_state, to_state)


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        # Prohibited direct settlement:
        (TransactionState.INITIATED, TransactionState.SETTLED_SIMULATED),
        (TransactionState.INITIATED, TransactionState.DECISION_READY),
        (TransactionState.INITIATED, TransactionState.INVESTIGATING),
        (TransactionState.ASSESSING, TransactionState.SETTLED_SIMULATED),
        (TransactionState.RISK_ASSESSED, TransactionState.SETTLED_SIMULATED),
        # Terminal states cannot transition:
        (TransactionState.SETTLED_SIMULATED, TransactionState.INITIATED),
        (TransactionState.SETTLED_SIMULATED, TransactionState.CANCELLED_SIMULATED),
        (TransactionState.CANCELLED_SIMULATED, TransactionState.INITIATED),
        (TransactionState.CANCELLED_SIMULATED, TransactionState.SETTLED_SIMULATED),
        (TransactionState.HUMAN_REVIEW, TransactionState.SETTLED_SIMULATED),
    ],
)
def test_prohibited_transitions_fail(
    from_state: TransactionState, to_state: TransactionState
) -> None:
    """Ensure invalid transitions raise InvalidStateTransitionError with HTTP 400."""
    assert can_transition(from_state, to_state) is False
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        validate_transition(from_state, to_state)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"


def test_terminal_states() -> None:
    """Verify terminal state detection."""
    assert is_terminal(TransactionState.SETTLED_SIMULATED) is True
    assert is_terminal(TransactionState.CANCELLED_SIMULATED) is True
    assert is_terminal(TransactionState.INITIATED) is False
    assert is_terminal(TransactionState.DECISION_READY) is False
    assert is_terminal("UNKNOWN_STATE") is False


def test_unknown_states_raise_validation_error() -> None:
    """Verify unknown or malformed state strings raise InvalidStateTransitionError."""
    assert can_transition("UNKNOWN_STATE", "INITIATED") is False
    with pytest.raises(InvalidStateTransitionError) as exc_from:
        validate_transition("UNKNOWN_STATE", TransactionState.INITIATED)
    assert exc_from.value.code == "INVALID_STATE_TRANSITION"

    with pytest.raises(InvalidStateTransitionError) as exc_to:
        validate_transition(TransactionState.INITIATED, "INVALID_TARGET")
    assert exc_to.value.code == "INVALID_STATE_TRANSITION"


def test_exhaustiveness_of_allowed_transitions() -> None:
    """Verify ALLOWED_TRANSITIONS defines an entry for every TransactionState."""
    for state in TransactionState:
        assert state in ALLOWED_TRANSITIONS
