"""SQLAlchemy database models for transaction and audit domain."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.state_machine import TransactionState


class TransactionModel(Base):
    """Persistent database representation of a simulated transaction."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "idempotency_key",
            name="uq_transactions_customer_idempotency",
        ),
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        Index("ix_transactions_customer_created", "customer_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    customer_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )
    payment_rail: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    recipient_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    recipient_identifier: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    purpose: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TransactionState.INITIATED.value,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship to immutable audit log entries
    audits: Mapped[list["TransactionAuditModel"]] = relationship(
        "TransactionAuditModel",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionAuditModel.created_at.asc()",
    )

    # Relationship to deterministic risk assessment records
    assessments: Mapped[list["TransactionAssessmentModel"]] = relationship(
        "TransactionAssessmentModel",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionAssessmentModel.created_at.desc()",
    )


class TransactionAuditModel(Base):
    """Append-only audit trail recording state transitions and lifecycle events."""

    __tablename__ = "transaction_audits"
    __table_args__ = (Index("ix_transaction_audits_tx_created", "transaction_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_state: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    to_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    actor_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Relationship to parent transaction
    transaction: Mapped["TransactionModel"] = relationship(
        "TransactionModel",
        back_populates="audits",
    )


class TransactionAssessmentModel(Base):
    """Persistent representation of an explainable deterministic risk evaluation."""

    __tablename__ = "transaction_assessments"
    __table_args__ = (
        Index("ix_transaction_assessments_tx_created", "transaction_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    risk_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    risk_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    recommended_action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    triggered_rules: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    supporting_evidence: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    missing_evidence: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Relationship to parent transaction
    transaction: Mapped["TransactionModel"] = relationship(
        "TransactionModel",
        back_populates="assessments",
    )
