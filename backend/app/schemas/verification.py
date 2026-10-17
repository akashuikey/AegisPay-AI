"""Pydantic schemas for the simulated customer verification flow (P2-A5)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.decision import DecisionResponse


class CreateChallengeResponse(BaseModel):
    """Response when a verification challenge is created or an active one is retrieved."""

    challenge_id: UUID
    transaction_id: UUID
    status: str
    attempt_count: int
    max_attempts: int
    attempts_remaining: int
    expires_at: datetime
    customer_session_token: str = Field(
        description="Short-lived token for the simulated customer verification session"
    )
    session_expires_in: int
    simulated: bool = Field(
        default=True,
        description="Always true: this is a SIMULATED OTP, not a real bank authentication channel.",
    )
    dev_otp: str | None = Field(
        default=None,
        description=(
            "DEV-ONLY: the simulated OTP, present only when VERIFICATION_EXPOSE_DEV_OTP is "
            "enabled. Never populated in production."
        ),
    )


class SubmitVerificationRequest(BaseModel):
    """Payload to submit a verification response for a challenge."""

    model_config = ConfigDict(extra="forbid")

    otp: str = Field(..., min_length=4, max_length=12, pattern=r"^\d+$")
    client_request_id: str | None = Field(default=None, max_length=64)


class VerificationStatusResponse(BaseModel):
    """Current status of a verification challenge."""

    model_config = ConfigDict(from_attributes=True)

    challenge_id: UUID
    transaction_id: UUID
    status: str
    attempt_count: int
    max_attempts: int
    attempts_remaining: int
    expires_at: datetime
    verified_at: datetime | None = None
    decision_id: UUID | None = None
    transaction_state: str


class SubmitVerificationResponse(BaseModel):
    """Result of submitting a verification response."""

    challenge_id: UUID
    transaction_id: UUID
    result: str = Field(description="SUCCEEDED | FAILED | EXHAUSTED")
    status: str = Field(description="Resulting challenge status")
    attempts_remaining: int
    transaction_state: str
    decision: DecisionResponse | None = Field(
        default=None,
        description="The policy decision from re-evaluation, when verification was resolved.",
    )
    simulated: bool = True
