"""Pydantic schemas for risk assessment requests, responses, and rule findings."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.risk_engine import (
    RecommendedAction,
    RiskLevel,
    TransactionEvidence,
)
from app.domain.state_machine import ActorType


class TransactionEvidenceRequest(BaseModel):
    """Client request schema containing transaction features and evidence indicators."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Transaction amount in fractional currency units",
        examples=[250000.00],
    )
    currency: str = Field(default="INR", max_length=3, examples=["INR"])
    payment_rail: str = Field(default="UPI", max_length=32, examples=["UPI"])
    recipient_name: str = Field(default="", max_length=255, examples=["Tech Support Inc"])
    recipient_identifier: str = Field(default="", max_length=255, examples=["support@okhdfcbank"])
    purpose: str | None = Field(default=None, max_length=255)

    # Customer Historical Context
    customer_id: str | None = Field(default=None, max_length=64)
    historical_transaction_count: int | None = Field(default=None, ge=0)
    avg_monthly_transfer_amount: Decimal | None = Field(default=None, ge=0)
    recent_fd_liquidation: bool | None = Field(
        default=None,
        description="True if customer recently liquidated term/fixed deposit savings",
    )
    recent_fd_liquidation_amount: Decimal | None = Field(default=None, ge=0)

    # Recipient Intelligence
    is_first_time_recipient: bool | None = Field(
        default=None,
        description="True if customer has never transacted with this recipient before",
    )
    is_trusted_beneficiary: bool | None = Field(
        default=None,
        description="True if recipient is an established trusted beneficiary",
    )
    recipient_account_age_days: int | None = Field(default=None, ge=0)
    fan_in_count_24h: int | None = Field(
        default=None, ge=0, description="Unique senders to recipient in past 24h"
    )
    fan_out_count_24h: int | None = Field(
        default=None, ge=0, description="Disbursement transactions in past 24h"
    )
    is_flagged_mule: bool | None = Field(
        default=None, description="True if recipient is in mule registry"
    )
    payee_name_mismatch: bool | None = Field(
        default=None, description="True if payee name differs from claimed vendor"
    )
    routing_mismatch: bool | None = Field(
        default=None, description="True if IFSC/routing differs from historical supplier"
    )

    # Behavioral Telephony Signals
    active_call_present: bool | None = Field(
        default=None, description="True if customer is on an active phone call"
    )
    screen_sharing_active: bool | None = Field(
        default=None, description="True if remote screen sharing is active"
    )
    voice_stress_detected: bool | None = Field(
        default=None, description="True if vocal acoustic stress markers detected"
    )

    # Contextual Signals
    coercive_language_detected: bool | None = Field(
        default=None, description="True if authority threats/duress detected"
    )
    guaranteed_return_claimed: bool | None = Field(
        default=None, description="True if high-yield/guaranteed profits promised"
    )
    urgency_pressure_detected: bool | None = Field(
        default=None, description="True if time-limit/countdown pressure applied"
    )
    instruction_to_ignore_bank_warnings: bool | None = Field(
        default=None, description="True if instructed to bypass bank fraud warnings"
    )
    invoice_verified: bool | None = Field(
        default=None, description="True if invoice matches vendor records"
    )

    def to_domain(self) -> TransactionEvidence:
        """Convert Pydantic schema to immutable domain dataclass."""
        return TransactionEvidence(
            amount=self.amount,
            currency=self.currency,
            payment_rail=self.payment_rail,
            recipient_name=self.recipient_name,
            recipient_identifier=self.recipient_identifier,
            purpose=self.purpose,
            customer_id=self.customer_id,
            historical_transaction_count=self.historical_transaction_count,
            avg_monthly_transfer_amount=self.avg_monthly_transfer_amount,
            recent_fd_liquidation=self.recent_fd_liquidation,
            recent_fd_liquidation_amount=self.recent_fd_liquidation_amount,
            is_first_time_recipient=self.is_first_time_recipient,
            is_trusted_beneficiary=self.is_trusted_beneficiary,
            recipient_account_age_days=self.recipient_account_age_days,
            fan_in_count_24h=self.fan_in_count_24h,
            fan_out_count_24h=self.fan_out_count_24h,
            is_flagged_mule=self.is_flagged_mule,
            payee_name_mismatch=self.payee_name_mismatch,
            routing_mismatch=self.routing_mismatch,
            active_call_present=self.active_call_present,
            screen_sharing_active=self.screen_sharing_active,
            voice_stress_detected=self.voice_stress_detected,
            coercive_language_detected=self.coercive_language_detected,
            guaranteed_return_claimed=self.guaranteed_return_claimed,
            urgency_pressure_detected=self.urgency_pressure_detected,
            instruction_to_ignore_bank_warnings=self.instruction_to_ignore_bank_warnings,
            invoice_verified=self.invoice_verified,
        )


class TriggeredRuleResponse(BaseModel):
    """Details of a policy rule triggered during risk evaluation."""

    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    rule_name: str
    description: str
    weight: int
    severity: RiskLevel
    evidence: str


class RiskAssessmentResponse(BaseModel):
    """Comprehensive explainable response for a transaction risk assessment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    transaction_id: UUID | None = None
    risk_score: int = Field(ge=0, le=100, description="Relative risk score (0 to 100)")
    risk_level: RiskLevel
    recommended_action: RecommendedAction
    explanation: str
    triggered_rules: list[TriggeredRuleResponse]
    supporting_evidence: list[str]
    missing_evidence: list[str]
    created_at: datetime | None = None


class AssessTransactionRequest(BaseModel):
    """Request payload to assess an existing transaction by UUID."""

    model_config = ConfigDict(extra="forbid")

    evidence: TransactionEvidenceRequest | None = None
    actor_type: ActorType = ActorType.SYSTEM
    reason: str | None = Field(default=None, max_length=500)
    correlation_id: str | None = Field(default=None, max_length=64)
