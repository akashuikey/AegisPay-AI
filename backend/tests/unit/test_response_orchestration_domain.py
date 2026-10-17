"""Unit tests for automated response orchestration domain and customer intervention (P2-A7)."""

from decimal import Decimal

from app.domain.decision_policy import PolicyAction
from app.domain.response_orchestration import (
    CustomerActionRequired,
    ResponseType,
    build_customer_intervention,
    mask_recipient_contact,
)
from app.services.notification_service import SimulatedNotificationService


def test_build_customer_intervention_allow() -> None:
    """ALLOW response produces non-accusatory clear approval status."""
    intervention = build_customer_intervention(
        action=PolicyAction.ALLOW,
        amount=Decimal("1500.00"),
        currency="INR",
        recipient="Aarav Sharma",
    )
    assert intervention.response_type == ResponseType.ALLOW_SETTLED
    assert intervention.customer_action_required == CustomerActionRequired.NONE
    assert intervention.is_safe_to_proceed is True
    assert "approved" in intervention.customer_message.lower()
    assert "Aarav Sharma" in intervention.customer_message
    assert "1,500.00" in intervention.customer_message
    # No internal rule or fraud accusation
    assert "fraud" not in intervention.customer_message.lower()
    assert "rule" not in intervention.customer_message.lower()


def test_build_customer_intervention_require_verification() -> None:
    """REQUIRE_VERIFICATION explains security check and directs to verification challenge."""
    intervention = build_customer_intervention(
        action=PolicyAction.REQUIRE_VERIFICATION,
        amount=Decimal("25000.00"),
        currency="INR",
        recipient="Unknown Electronics",
    )
    assert intervention.response_type == ResponseType.VERIFICATION_REQUIRED
    assert intervention.customer_action_required == CustomerActionRequired.VERIFY_OTP
    assert intervention.is_safe_to_proceed is False
    assert "verification" in intervention.customer_message.lower()
    assert any("mobile simulator" in step.lower() for step in intervention.next_steps)
    assert "NEVER call you to request a verification code" in intervention.advisory_notes


def test_build_customer_intervention_hold_protective() -> None:
    """HOLD explains protective pause and strictly warns against suspicious caller instructions."""
    intervention = build_customer_intervention(
        action=PolicyAction.HOLD_FOR_INVESTIGATION,
        amount=Decimal("495000.00"),
        currency="INR",
        recipient="CBI Safe Escrow Account",
    )
    assert intervention.response_type == ResponseType.HOLD_PROTECTIVE
    assert intervention.customer_action_required == CustomerActionRequired.CONTACT_BANK
    assert intervention.is_safe_to_proceed is False
    # Explicit warning about callers
    assert "hang up immediately" in intervention.customer_message.lower()
    assert any(
        "trusted phone number on the back of your card" in s for s in intervention.next_steps
    )
    assert any("Hang up any active voice calls" in s for s in intervention.next_steps)


def test_build_customer_intervention_block_safety() -> None:
    """BLOCK explains rejection without exposing internal detection rules or mule keywords."""
    intervention = build_customer_intervention(
        action=PolicyAction.BLOCK,
        amount=Decimal("200000.00"),
        currency="INR",
        recipient="Apex Holdings",
    )
    assert intervention.response_type == ResponseType.BLOCK_SAFETY
    assert intervention.customer_action_required == CustomerActionRequired.CONTACT_BANK
    assert intervention.is_safe_to_proceed is False
    assert "cancelled" in intervention.customer_message.lower()
    assert "No funds have left your account" in intervention.customer_message
    # Must NOT disclose internal detection rule IDs or consortium registry specifics
    assert "RULE_FLAGGED_MULE_ACCOUNT" not in intervention.customer_message
    assert "consortium" not in intervention.customer_message.lower()
    assert "mule" not in intervention.customer_message.lower()


def test_mask_recipient_contact_phone_numbers() -> None:
    """Phone numbers are masked to hide middle digits."""
    assert mask_recipient_contact("+919876543210") == "+91***3210"
    assert mask_recipient_contact("9876543210") == "987***3210"
    assert mask_recipient_contact("+14155552671") == "+14***2671"


def test_mask_recipient_contact_emails() -> None:
    """Emails are masked around the username."""
    assert mask_recipient_contact("john.doe@example.com") == "j***e@example.com"
    assert mask_recipient_contact("ab@test.org") == "a***@test.org"


def test_mask_recipient_contact_fallback() -> None:
    """Handles short strings and empty gracefully."""
    assert mask_recipient_contact("") == "unknown"
    assert mask_recipient_contact("123") == "***"
    assert mask_recipient_contact("admin") == "ad***in"


def test_notification_sanitization_removes_sensitive_data() -> None:
    """Notification service redacts accidental credential leaks."""
    service = SimulatedNotificationService()
    leaked = "Your verification OTP: 123456 has been generated."
    sanitized = service._sanitize_message_body(leaked)
    assert "123456" not in sanitized
    assert "[REDACTED_SECURITY_DATA]" in sanitized
