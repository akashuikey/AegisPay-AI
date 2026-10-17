"""Simulated customer notification service for automated fraud responses (P2-A7).

Provides a decoupled notification interface and simulated implementation.
Invariants:
- Zero integration with real SMS/WhatsApp/telephony rails in this milestone.
- OTPs, customer session tokens, full call transcripts, or raw passwords must NEVER
  be placed in notification bodies, recipient fields, or log records.
- Notification failures are completely isolated: a simulated delivery timeout/failure
  must never silently rollback or invalidate an authoritative safety decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.core.logging import get_logger
from app.domain.response_orchestration import (
    NotificationChannel,
    NotificationDeliveryStatus,
    mask_recipient_contact,
)

logger = get_logger(__name__)

# Patterns that indicate accidentally leaked sensitive secrets
_SENSITIVE_PATTERNS = [
    re.compile(r"otp[_\s:]+\d{4,8}", re.IGNORECASE),
    re.compile(r"verification[_\s:]+code[_\s:]+\d{4,8}", re.IGNORECASE),
    re.compile(r"ey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),  # JWT
    re.compile(r"password[_\s:]+\S+", re.IGNORECASE),
]


@dataclass(frozen=True)
class NotificationDispatchResult:
    """Immutable outcome of a simulated customer notification dispatch."""

    channel: NotificationChannel
    recipient_masked: str
    subject: str | None
    message_body: str
    delivery_status: NotificationDeliveryStatus
    failure_reason: str | None
    delivered_at: datetime | None
    idempotency_key: str | None


class NotificationServiceProtocol(Protocol):
    """Protocol for customer notification delivery."""

    async def dispatch(
        self,
        *,
        transaction_id: UUID,
        response_id: UUID,
        channel: NotificationChannel,
        recipient_raw: str,
        subject: str | None,
        message_body: str,
        simulate_failure: bool = False,
        idempotency_key: str | None = None,
    ) -> NotificationDispatchResult:
        """Deliver a notification to the customer."""
        ...


class SimulatedNotificationService:
    """Simulated notification delivery implementation."""

    async def dispatch(
        self,
        *,
        transaction_id: UUID,
        response_id: UUID,
        channel: NotificationChannel,
        recipient_raw: str,
        subject: str | None,
        message_body: str,
        simulate_failure: bool = False,
        idempotency_key: str | None = None,
    ) -> NotificationDispatchResult:
        """Simulate delivering a customer notification."""
        # 1. Mask recipient identifier for privacy
        masked_recipient = mask_recipient_contact(recipient_raw)

        # 2. Sanitize and verify message body contains no sensitive credentials
        sanitized_body = self._sanitize_message_body(message_body)

        # 3. Handle simulated failure
        if simulate_failure:
            logger.warning(
                "Simulated notification delivery FAILED for tx=%s response=%s channel=%s to=%s",
                transaction_id,
                response_id,
                channel.value,
                masked_recipient,
            )
            return NotificationDispatchResult(
                channel=channel,
                recipient_masked=masked_recipient,
                subject=subject,
                message_body=sanitized_body,
                delivery_status=NotificationDeliveryStatus.FAILED_SIMULATED,
                failure_reason="SIMULATED_CARRIER_TIMEOUT",
                delivered_at=None,
                idempotency_key=idempotency_key,
            )

        # 4. Handle simulated successful delivery
        delivered_at = datetime.now(UTC)
        logger.info(
            "Simulated notification DELIVERED for tx=%s response=%s channel=%s to=%s",
            transaction_id,
            response_id,
            channel.value,
            masked_recipient,
        )
        return NotificationDispatchResult(
            channel=channel,
            recipient_masked=masked_recipient,
            subject=subject,
            message_body=sanitized_body,
            delivery_status=NotificationDeliveryStatus.DELIVERED_SIMULATED,
            failure_reason=None,
            delivered_at=delivered_at,
            idempotency_key=idempotency_key,
        )

    def _sanitize_message_body(self, text: str) -> str:
        """Ensure body has no leaked secrets, tokens, or plaintext OTPs."""
        sanitized = text
        for pattern in _SENSITIVE_PATTERNS:
            if pattern.search(sanitized):
                logger.error(
                    "Sensitive credential pattern detected in notification body; redacting"
                )
                sanitized = pattern.sub("[REDACTED_SECURITY_DATA]", sanitized)
        return sanitized
