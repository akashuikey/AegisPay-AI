"""Domain definitions for automated fraud response orchestration & customer intervention (P2-A7).

Provides pure domain types, response mapping, customer-safe messaging, and contact
masking. Logic is completely decoupled from database I/O and external network calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.domain.decision_policy import PolicyAction


class ResponseType(StrEnum):
    """Categorized response type corresponding to the authoritative policy action."""

    ALLOW_SETTLED = "ALLOW_SETTLED"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    HOLD_PROTECTIVE = "HOLD_PROTECTIVE"
    BLOCK_SAFETY = "BLOCK_SAFETY"


class CustomerActionRequired(StrEnum):
    """Simulated action requested from the customer following the response."""

    NONE = "NONE"
    VERIFY_OTP = "VERIFY_OTP"
    CONTACT_BANK = "CONTACT_BANK"


class NotificationChannel(StrEnum):
    """Supported simulated communication channels for customer notifications."""

    IN_APP_SIMULATED = "IN_APP_SIMULATED"
    SMS_SIMULATED = "SMS_SIMULATED"
    EMAIL_SIMULATED = "EMAIL_SIMULATED"


class NotificationDeliveryStatus(StrEnum):
    """Simulated delivery status of a customer notification."""

    DELIVERED_SIMULATED = "DELIVERED_SIMULATED"
    FAILED_SIMULATED = "FAILED_SIMULATED"


class ResponseProcessingStatus(StrEnum):
    """Status of the automated response execution."""

    COMPLETED = "COMPLETED"
    PENDING_CUSTOMER_ACTION = "PENDING_CUSTOMER_ACTION"
    FAILED = "FAILED"


# PolicyAction to ResponseType mapping
ACTION_TO_RESPONSE_TYPE: dict[PolicyAction, ResponseType] = {
    PolicyAction.ALLOW: ResponseType.ALLOW_SETTLED,
    PolicyAction.REQUIRE_VERIFICATION: ResponseType.VERIFICATION_REQUIRED,
    PolicyAction.HOLD_FOR_INVESTIGATION: ResponseType.HOLD_PROTECTIVE,
    PolicyAction.BLOCK: ResponseType.BLOCK_SAFETY,
}


@dataclass(frozen=True)
class CustomerIntervention:
    """Structured, customer-safe intervention payload.

    Guarantees:
    - Never accuses the customer or third parties of proven crime.
    - Never exposes internal detection rules, risk thresholds, or mule registries.
    - Never directs the customer to caller-supplied numbers or external links.
    - Clearly advises verification or contacting official Aster Bank support.
    """

    response_type: ResponseType
    action: PolicyAction
    headline: str
    customer_message: str
    customer_action_required: CustomerActionRequired
    next_steps: list[str] = field(default_factory=list)
    is_safe_to_proceed: bool = True
    advisory_notes: str = ""


def build_customer_intervention(
    action: PolicyAction,
    amount: Decimal,
    currency: str = "INR",
    recipient: str = "the beneficiary",
    reference: str | None = None,
) -> CustomerIntervention:
    """Construct an understandable, non-accusatory customer intervention message."""
    formatted_amount = f"{amount:,.2f}"

    match action:
        case PolicyAction.ALLOW:
            return CustomerIntervention(
                response_type=ResponseType.ALLOW_SETTLED,
                action=action,
                headline="Payment Processing Approved",
                customer_message=(
                    f"Your payment of {currency} {formatted_amount} to {recipient} has been "
                    "approved and is being processed in our simulated clearing system."
                ),
                customer_action_required=CustomerActionRequired.NONE,
                next_steps=[
                    "No further action is required from you.",
                    "Simulated transfer confirmation will appear in your account history.",
                ],
                is_safe_to_proceed=True,
                advisory_notes=(
                    "Aster Bank will never ask for your password, PIN, or login credentials."
                ),
            )

        case PolicyAction.REQUIRE_VERIFICATION:
            return CustomerIntervention(
                response_type=ResponseType.VERIFICATION_REQUIRED,
                action=action,
                headline="Identity Verification Required",
                customer_message=(
                    f"For your account security, your payment of {currency} {formatted_amount} "
                    f"to {recipient} requires additional verification before it can proceed. "
                    "Please confirm this transfer using the secure verification challenge "
                    "in your Aster Bank app."
                ),
                customer_action_required=CustomerActionRequired.VERIFY_OTP,
                next_steps=[
                    "Complete the secure verification code challenge in your mobile simulator.",
                    "Do not disclose or forward verification codes to anyone.",
                    "If you did not initiate this payment, cancel it immediately in your app.",
                ],
                is_safe_to_proceed=False,
                advisory_notes=(
                    "Aster Bank employees will NEVER call you to request a verification code."
                ),
            )

        case PolicyAction.HOLD_FOR_INVESTIGATION:
            return CustomerIntervention(
                response_type=ResponseType.HOLD_PROTECTIVE,
                action=action,
                headline="Payment Paused for Account Protection",
                customer_message=(
                    f"Your payment of {currency} {formatted_amount} to {recipient} is "
                    "temporarily on hold for your protection while our security team completes "
                    "standard safety checks. If someone claiming to be a police officer, tax "
                    "official, government agent, or bank security officer asked you to make "
                    "this transfer or stay on the phone, please hang up immediately. Do not dial "
                    "numbers or click links provided by callers."
                ),
                customer_action_required=CustomerActionRequired.CONTACT_BANK,
                next_steps=[
                    "Hang up any active voice calls or video calls immediately.",
                    "Do not transfer funds to 'safe accounts' or 'protective escrow'.",
                    "Contact Aster Bank support exclusively using the trusted phone number on "
                    "the back of your card.",
                    "Visit an official Aster Bank branch if you believe you are under coercion.",
                ],
                is_safe_to_proceed=False,
                advisory_notes=(
                    "Law enforcement and banks will never instruct you to transfer money to a "
                    "safe account."
                ),
            )

        case PolicyAction.BLOCK:
            return CustomerIntervention(
                response_type=ResponseType.BLOCK_SAFETY,
                action=action,
                headline="Payment Rejected for Account Safety",
                customer_message=(
                    f"For your account safety, this simulated payment of {currency} "
                    f"{formatted_amount} to {recipient} could not be completed and has been "
                    "cancelled. No funds have left your account. If you believe this "
                    "cancellation was unexpected, please reach out to Aster Bank customer "
                    "support through official channels."
                ),
                customer_action_required=CustomerActionRequired.CONTACT_BANK,
                next_steps=[
                    "No funds were deducted from your account.",
                    "Do not attempt to resend funds to the same beneficiary identifier.",
                    "Contact Aster Bank customer care via the official website or mobile app.",
                ],
                is_safe_to_proceed=False,
                advisory_notes=(
                    "Aster Bank continuously screens transactions against verified fraud safety "
                    "registries."
                ),
            )


def mask_recipient_contact(contact: str) -> str:
    """Mask a customer phone number, email address, or account handle for privacy.

    Never exposes full raw contact identifiers in logs or notification records.
    """
    cleaned = contact.strip()
    if not cleaned:
        return "unknown"

    # Email pattern: user@domain.com -> u***r@domain.com
    if "@" in cleaned:
        parts = cleaned.split("@", 1)
        name, domain = parts[0], parts[1]
        if len(name) <= 2:
            masked_name = name[0] + "***"
        else:
            masked_name = name[0] + "***" + name[-1]
        return f"{masked_name}@{domain}"

    # Phone number pattern (digits, possibly with leading +)
    digits = re.sub(r"[^\d+]", "", cleaned)
    if len(digits) >= 8:
        prefix = digits[:3]
        suffix = digits[-4:]
        return f"{prefix}***{suffix}"

    if len(cleaned) > 4:
        return cleaned[:2] + "***" + cleaned[-2:]

    return "***"
