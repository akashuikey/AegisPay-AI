"""SQLAlchemy database models for transaction and audit domain."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.state_machine import TransactionState


class OperatorModel(Base):
    """A fraud-operations analyst identity authorized to use the operations console."""

    __tablename__ = "operators"
    __table_args__ = (UniqueConstraint("username", name="uq_operators_username"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


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

    # Relationship to automated decision records
    decisions: Mapped[list["TransactionDecisionModel"]] = relationship(
        "TransactionDecisionModel",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionDecisionModel.created_at.desc()",
    )

    # Relationship to simulated verification challenges
    verification_challenges: Mapped[list["VerificationChallengeModel"]] = relationship(
        "VerificationChallengeModel",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="VerificationChallengeModel.created_at.desc()",
    )

    # Relationship to coercion analysis records (P2-A6)
    coercion_analyses: Mapped[list["TransactionCoercionAnalysisModel"]] = relationship(
        "TransactionCoercionAnalysisModel",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionCoercionAnalysisModel.created_at.desc()",
    )

    # Relationship to automated response records (P2-A7)
    responses: Mapped[list["TransactionResponseModel"]] = relationship(
        "TransactionResponseModel",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionResponseModel.created_at.desc()",
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


class TransactionDecisionModel(Base):
    """Auditable automated decision record produced by the P2-A4 workflow.

    Companion to the append-only ``transaction_audits`` trail: it stores the
    structured policy decision (action, policy version, references, reason codes)
    alongside the state transition it drove, so a decision can be reconstructed.
    """

    __tablename__ = "transaction_decisions"
    __table_args__ = (Index("ix_transaction_decisions_tx_created", "transaction_id", "created_at"),)

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
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transaction_investigations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    requires_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    from_state: Mapped[str] = mapped_column(String(32), nullable=False)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    workflow_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    triggered_rule_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    investigation_finding_refs: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    supporting_evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    missing_information: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    transaction: Mapped["TransactionModel"] = relationship(
        "TransactionModel",
        back_populates="decisions",
    )


class VerificationChallengeModel(Base):
    """Simulated customer verification challenge (OTP) bound to a transaction.

    The plaintext OTP is NEVER stored — only a keyed HMAC digest. The ``version``
    column provides optimistic single-use consumption under concurrency.
    """

    __tablename__ = "verification_challenges"
    __table_args__ = (
        Index("ix_verification_challenges_tx_status", "transaction_id", "status"),
        Index(
            "uq_verification_challenges_pending_tx",
            "transaction_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
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
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    otp_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transaction_decisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    transaction: Mapped["TransactionModel"] = relationship(
        "TransactionModel",
        back_populates="verification_challenges",
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


class TransactionCoercionAnalysisModel(Base):
    """Forensic voice duress and coercion intelligence record (P2-A6)."""

    __tablename__ = "transaction_coercion_analyses"
    __table_args__ = (
        Index("ix_transaction_coercion_analyses_tx_created", "transaction_id", "created_at"),
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
    transcript_snippet: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    overall_coercion_level: Mapped[str] = mapped_column(
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
    voice_stress_signals: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    legitimate_explanations: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    uncertainty_notes: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    missing_information: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    model_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="COMPLETED",
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
        back_populates="coercion_analyses",
    )


class TransactionResponseModel(Base):
    """Persistent record of automated response orchestration & customer intervention (P2-A7)."""

    __tablename__ = "transaction_responses"
    __table_args__ = (
        Index("ix_transaction_responses_tx_created", "transaction_id", "created_at"),
        UniqueConstraint(
            "transaction_id",
            "idempotency_key",
            name="uq_transaction_responses_tx_idempotency",
        ),
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
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transaction_decisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    response_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    processing_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="COMPLETED",
    )
    from_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    to_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    headline: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    customer_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    customer_action_required: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="NONE",
    )
    next_steps: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
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
        back_populates="responses",
    )
    decision: Mapped["TransactionDecisionModel | None"] = relationship(
        "TransactionDecisionModel",
    )
    notifications: Mapped[list["TransactionNotificationModel"]] = relationship(
        "TransactionNotificationModel",
        back_populates="response",
        cascade="all, delete-orphan",
        order_by="TransactionNotificationModel.created_at.asc()",
    )


class TransactionNotificationModel(Base):
    """Persistent record of a simulated customer notification (P2-A7)."""

    __tablename__ = "transaction_notifications"
    __table_args__ = (
        Index("ix_transaction_notifications_tx_created", "transaction_id", "created_at"),
        UniqueConstraint(
            "response_id",
            "channel",
            name="uq_transaction_notifications_response_channel",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    response_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transaction_responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    recipient_masked: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    subject: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    message_body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    delivery_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DELIVERED_SIMULATED",
    )
    failure_reason: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    response: Mapped["TransactionResponseModel"] = relationship(
        "TransactionResponseModel",
        back_populates="notifications",
    )
    transaction: Mapped["TransactionModel"] = relationship(
        "TransactionModel",
    )
