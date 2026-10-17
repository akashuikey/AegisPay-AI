"""Transaction state machine domain rules and transitions."""

from enum import StrEnum

from app.core.errors import InvalidStateTransitionError


class TransactionState(StrEnum):
    """Authoritative workflow states for simulated transactions."""

    INITIATED = "INITIATED"
    ASSESSING = "ASSESSING"
    RISK_ASSESSED = "RISK_ASSESSED"
    DECISION_READY = "DECISION_READY"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    HELD_FOR_VERIFICATION = "HELD_FOR_VERIFICATION"
    INVESTIGATING = "INVESTIGATING"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    SETTLED_SIMULATED = "SETTLED_SIMULATED"
    CANCELLED_SIMULATED = "CANCELLED_SIMULATED"


class ActorType(StrEnum):
    """Actors permitted to trigger transaction lifecycle changes."""

    SYSTEM = "SYSTEM"
    CUSTOMER = "CUSTOMER"
    INVESTIGATOR = "INVESTIGATOR"
    POLICY_ENGINE = "POLICY_ENGINE"


# Explicit transition mapping as defined in P1-A2 specification
ALLOWED_TRANSITIONS: dict[TransactionState, frozenset[TransactionState]] = {
    TransactionState.INITIATED: frozenset(
        {TransactionState.ASSESSING, TransactionState.CANCELLED_SIMULATED}
    ),
    TransactionState.ASSESSING: frozenset(
        {TransactionState.RISK_ASSESSED, TransactionState.HUMAN_REVIEW}
    ),
    TransactionState.RISK_ASSESSED: frozenset(
        {TransactionState.DECISION_READY, TransactionState.HUMAN_REVIEW}
    ),
    TransactionState.DECISION_READY: frozenset(
        {
            TransactionState.VERIFICATION_REQUIRED,
            TransactionState.HELD_FOR_VERIFICATION,
            TransactionState.SETTLED_SIMULATED,
            TransactionState.CANCELLED_SIMULATED,
            TransactionState.HUMAN_REVIEW,
        }
    ),
    TransactionState.VERIFICATION_REQUIRED: frozenset(
        {TransactionState.INVESTIGATING, TransactionState.CANCELLED_SIMULATED}
    ),
    TransactionState.HELD_FOR_VERIFICATION: frozenset(
        {TransactionState.INVESTIGATING, TransactionState.CANCELLED_SIMULATED}
    ),
    TransactionState.INVESTIGATING: frozenset(
        {
            TransactionState.DECISION_READY,
            TransactionState.HUMAN_REVIEW,
            TransactionState.CANCELLED_SIMULATED,
        }
    ),
    TransactionState.HUMAN_REVIEW: frozenset(
        {
            TransactionState.DECISION_READY,
            TransactionState.HELD_FOR_VERIFICATION,
            TransactionState.CANCELLED_SIMULATED,
        }
    ),
    TransactionState.SETTLED_SIMULATED: frozenset(),
    TransactionState.CANCELLED_SIMULATED: frozenset(),
}

TERMINAL_STATES: frozenset[TransactionState] = frozenset(
    {TransactionState.SETTLED_SIMULATED, TransactionState.CANCELLED_SIMULATED}
)


def can_transition(from_state: TransactionState | str, to_state: TransactionState | str) -> bool:
    """Check whether a transition between two states is permitted."""
    try:
        from_enum = TransactionState(from_state)
        to_enum = TransactionState(to_state)
    except ValueError:
        return False
    return to_enum in ALLOWED_TRANSITIONS.get(from_enum, frozenset())


def is_terminal(state: TransactionState | str) -> bool:
    """Check whether a state is terminal."""
    try:
        state_enum = TransactionState(state)
    except ValueError:
        return False
    return state_enum in TERMINAL_STATES


def validate_transition(
    from_state: TransactionState | str, to_state: TransactionState | str
) -> None:
    """Validate that a state transition is permitted.

    Raises:
        InvalidStateTransitionError: If the transition is not permitted or states are unknown.
    """
    try:
        from_enum = TransactionState(from_state)
    except ValueError:
        raise InvalidStateTransitionError(
            from_state=str(from_state),
            to_state=str(to_state),
            message=f"Unknown source transaction state: '{from_state}'",
        ) from None

    try:
        to_enum = TransactionState(to_state)
    except ValueError:
        raise InvalidStateTransitionError(
            from_state=str(from_state),
            to_state=str(to_state),
            message=f"Unknown target transaction state: '{to_state}'",
        ) from None

    allowed = ALLOWED_TRANSITIONS.get(from_enum, frozenset())
    if to_enum not in allowed:
        raise InvalidStateTransitionError(
            from_state=from_enum.value,
            to_state=to_enum.value,
            message=(
                f"Transition from '{from_enum.value}' to '{to_enum.value}' is prohibited. "
                f"Permitted next states: {sorted(s.value for s in allowed) or ['NONE (terminal)']}"
            ),
        )
