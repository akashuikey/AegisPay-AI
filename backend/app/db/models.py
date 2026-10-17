"""SQLAlchemy database models for transaction and audit domain."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
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

    # Relationship to AI investigation records
    investigations: Mapped[list["TransactionInvestigationModel"]] = relationship(
        "TransactionInvestigationModel",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionInvestigationModel.created_at.desc()",
    )

    # Relationship to investigation conversations
    conversations: Mapped[list["InvestigationConversationModel"]] = relationship(
        "InvestigationConversationModel",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="InvestigationConversationModel.created_at.desc()",
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


class TransactionInvestigationModel(Base):
    """Forensic AI-generated investigation records analyzing contextual evidence."""

    __tablename__ = "transaction_investigations"
    __table_args__ = (
        Index("ix_transaction_investigations_tx_created", "transaction_id", "created_at"),
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
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transaction_assessments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    overall_risk_sentiment: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    confidence: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    findings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    contradictory_evidence: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    missing_information: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    unresolved_questions: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    suggested_next_steps: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    model_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
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
        back_populates="investigations",
    )


class InvestigationConversationModel(Base):
    """Investigation conversation session associated with a transaction."""

    __tablename__ = "investigation_conversations"
    __table_args__ = (
        Index("ix_investigation_conversations_tx_created", "transaction_id", "created_at"),
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
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ACTIVE",
    )
    turn_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
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

    # Relationships
    transaction: Mapped["TransactionModel"] = relationship(
        "TransactionModel",
        back_populates="conversations",
    )
    turns: Mapped[list["InvestigationConversationTurnModel"]] = relationship(
        "InvestigationConversationTurnModel",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="InvestigationConversationTurnModel.turn_index.asc()",
    )


class InvestigationConversationTurnModel(Base):
    """Individual turn within an investigation conversation."""

    __tablename__ = "investigation_conversation_turns"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "turn_index",
            name="uq_conversation_turn_index",
        ),
        Index("ix_conversation_turns_conv_turn", "conversation_id", "turn_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("investigation_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    evidence_provenance: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    evidence_references: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    findings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    risk_sentiment: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    confidence: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    confidence_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    missing_information: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    follow_up_questions: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    model_metadata: Mapped[dict[str, Any]] = mapped_column(
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

    # Relationship to conversation
    conversation: Mapped["InvestigationConversationModel"] = relationship(
        "InvestigationConversationModel",
        back_populates="turns",
    )
