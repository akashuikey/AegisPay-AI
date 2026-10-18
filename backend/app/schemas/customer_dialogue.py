"""Pydantic schemas for simulated customer call sessions and dialogue turns (Option A)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.customer_dialogue import (
    CallSessionDirection,
    CallSessionStatus,
    DialogueChannel,
)
from app.domain.investigation import RiskSentiment


class InitiateCallSessionRequest(BaseModel):
    """Payload to initiate a new simulated call or chat session."""

    model_config = ConfigDict(extra="forbid")

    channel: DialogueChannel = Field(
        default=DialogueChannel.VOICE_SIMULATED,
        description="Channel mode: VOICE_SIMULATED or CHAT_SIMULATED",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=128,
        description="Optional client idempotency key to prevent duplicate call creation",
    )
    correlation_id: str | None = Field(default=None, max_length=64)


class SubmitCustomerDialogueTurnRequest(BaseModel):
    """Payload to submit a customer answer (speech-to-text or typed) during active dialogue."""

    model_config = ConfigDict(extra="forbid")

    customer_message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The customer's verbal answer or chat response",
    )
    source: str = Field(
        default="typed",
        max_length=32,
        description="Input source: 'speech', 'typed', or 'demo response'",
    )
    client_turn_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional client token to prevent duplicate turn submission",
    )
    correlation_id: str | None = Field(default=None, max_length=64)


class DeclineCallSessionRequest(BaseModel):
    """Payload to decline an incoming simulated call."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=128)


class CustomerDialogueTurnResponse(BaseModel):
    """API response model for an individual turn in a customer dialogue."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    turn_index: int
    role: str
    content: str
    evidence_provenance: str | None = None
    evidence_references: list[str] = Field(default_factory=list)
    internal_observations: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    suggested_action: str | None = None
    is_terminal_turn: bool = False
    risk_sentiment: RiskSentiment | None = None
    coercion_cues: list[str] = Field(default_factory=list)
    created_at: datetime


class CallSessionResponse(BaseModel):
    """API response model for a simulated call session."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    conversation_id: UUID | None = None
    channel: DialogueChannel
    status: CallSessionStatus
    direction: CallSessionDirection
    attempt_number: int
    idempotency_key: str | None = None
    started_at: datetime
    connected_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int
    failure_reason: str | None = None
    customer_phone_masked: str
    version: int
    turns: list[CustomerDialogueTurnResponse] = Field(default_factory=list)
    coercion_analysis_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class TranscriptSegmentResponse(BaseModel):
    """A single persisted live-voice transcript segment (P2-A11)."""

    model_config = ConfigDict(from_attributes=True)

    seq: int
    speaker: str
    kind: str
    content: str
    created_at: datetime


class LiveAnalysisResponse(BaseModel):
    """Latest incremental evidence-analysis snapshot for a live call (operator-only)."""

    model_config = ConfigDict(from_attributes=True)

    status: str
    contract_version: str
    overall_sentiment: str
    summary: str
    analyzed_through_seq: int
    findings: list[dict] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    created_at: datetime
