"""Domain models, rules, and business logic."""

from app.domain.state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    ActorType,
    TransactionState,
    can_transition,
    is_terminal,
    validate_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "ActorType",
    "TransactionState",
    "can_transition",
    "is_terminal",
    "validate_transition",
]
