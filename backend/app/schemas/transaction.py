"""Pydantic schemas for transaction creation, transitions, and auditing."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.state_machine import ActorType, TransactionState


class CreateTransactionRequest(BaseModel):
    """Client request schema for creating a new simulated payment transaction."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier of the customer initiating the transaction",
        examples=["cust_1001"],
    )
    idempotency_key: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Client-provided idempotency key for safe duplicate replays",
        examples=["tx_req_001_abc"],
    )
    amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Transaction amount in fractional currency (e.g., 2500.50)",
        examples=[2500.00],
    )
    currency: str = Field(
        default="INR",
        min_length=3,
        max_length=3,
        description="ISO 4217 three-letter currency code",
        examples=["INR"],
    )
    payment_rail: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Simulated payment rail: UPI, IMPS, NEFT, or RTGS",
        examples=["UPI"],
    )
    recipient_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the payment recipient or beneficiary",
        examples=["Tech Support Services Inc"],
    )
    recipient_identifier: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Recipient identifier: VPA/UPI ID, Account Number, or Phone",
        examples=["support@upi"],
    )
    purpose: str | None = Field(
        default=None,
        max_length=255,
        description="Optional customer-provided description or note",
        examples=["Security upgrade refund"],
    )

    def compute_payload_hash(self) -> str:
        """Compute canonical deterministic SHA-256 hash for idempotency checking."""
        canonical_dict = {
            "amount": f"{self.amount:.2f}",
            "currency": self.currency.upper(),
            "customer_id": self.customer_id,
            "payment_rail": self.payment_rail.upper(),
            "purpose": (self.purpose or "").strip(),
            "recipient_identifier": self.recipient_identifier.strip(),
            "recipient_name": self.recipient_name.strip(),
        }
        encoded = json.dumps(canonical_dict, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class TransitionTransactionRequest(BaseModel):
    """Client request schema for transitioning a transaction to a new workflow state."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_state: TransactionState = Field(
        ...,
        description="Permitted target state in the transaction state machine",
        examples=[TransactionState.ASSESSING],
    )
    actor_type: ActorType = Field(
        default=ActorType.SYSTEM,
        description="Actor requesting or executing the state change",
        examples=[ActorType.SYSTEM],
    )
    reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Audit reason or rationale for this lifecycle transition",
        examples=["Initiated risk assessment engine"],
    )
    correlation_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional tracing or correlation identifier",
        examples=["corr_882910"],
    )


class TransactionAuditResponse(BaseModel):
    """Audit log entry for a transaction state change."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    from_state: str | None = None
    to_state: str
    actor_type: str
    reason: str | None = None
    correlation_id: str | None = None
    created_at: datetime


class TransactionResponse(BaseModel):
    """Detailed response schema for a simulated transaction."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: str
    idempotency_key: str
    amount: Decimal
    currency: str
    payment_rail: str
    recipient_name: str
    recipient_identifier: str
    purpose: str | None = None
    state: str
    version: int
    created_at: datetime
    updated_at: datetime


class TransactionListResponse(BaseModel):
    """Paginated list of transactions."""

    items: list[TransactionResponse]
    total: int
    limit: int
    offset: int


class AuditHistoryResponse(BaseModel):
    """Complete audit history for a given transaction."""

    transaction_id: UUID
    total_entries: int
    items: list[TransactionAuditResponse]
