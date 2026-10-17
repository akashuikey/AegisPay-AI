"""Pydantic schemas for automated fraud response orchestration & customer intervention (P2-A7)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.response_orchestration import NotificationChannel


class ExecuteResponseRequest(BaseModel):
    """Request payload to trigger automated response orchestration."""

    idempotency_key: str | None = Field(
        default=None,
        max_length=128,
        description="Optional idempotency key to prevent duplicate response execution on retries.",
    )
    channel: NotificationChannel = Field(
        default=NotificationChannel.IN_APP_SIMULATED,
        description="Simulated communication channel for customer notification dispatch.",
    )
    simulate_notification_failure: bool = Field(
        default=False,
        description="If True, tests simulated notification failure without altering decision.",
    )


class NotificationResponse(BaseModel):
    """Serialized representation of a simulated customer notification."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel: str
    recipient_masked: str
    subject: str | None = None
    message_body: str
    delivery_status: str
    failure_reason: str | None = None
    created_at: datetime
    delivered_at: datetime | None = None


class CustomerInterventionResponse(BaseModel):
    """Customer-facing safe intervention details.

    Contains zero sensitive internal detection rules, risk scores, or confidential tokens.
    """

    transaction_id: UUID
    response_type: str
    headline: str
    customer_message: str
    customer_action_required: str
    next_steps: list[str] = Field(default_factory=list)
    simulated_payment_status: str
    notification_delivered: bool
    notification_channel: str
    is_simulated: bool = True


class FraudResponseDetails(BaseModel):
    """Comprehensive details of an automated response for fraud operators."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    decision_id: UUID | None = None
    response_type: str
    action: str
    processing_status: str
    from_state: str
    to_state: str
    headline: str
    customer_message: str
    customer_action_required: str
    next_steps: list[str] = Field(default_factory=list)
    idempotency_key: str | None = None
    created_at: datetime
    notifications: list[NotificationResponse] = Field(default_factory=list)
    is_simulated: bool = True
