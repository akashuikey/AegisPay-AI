"""Domain models and value types for AI-powered fraud investigation."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FindingCategory(StrEnum):
    """Categorization of findings uncovered during AI investigation."""

    AUTHORITY_COERCION = "AUTHORITY_COERCION"
    SOCIAL_ENGINEERING = "SOCIAL_ENGINEERING"
    BENEFICIARY_INCONSISTENCY = "BENEFICIARY_INCONSISTENCY"
    URGENCY_MANIPULATION = "URGENCY_MANIPULATION"
    DOCUMENT_FABRICATION = "DOCUMENT_FABRICATION"
    MULE_VELOCITY = "MULE_VELOCITY"
    LEGITIMATE_CONTEXT = "LEGITIMATE_CONTEXT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RiskSentiment(StrEnum):
    """Overall qualitative risk sentiment assessed by the investigation agent."""

    BENIGN = "BENIGN"
    SUSPICIOUS = "SUSPICIOUS"
    COERCED = "COERCED"
    MALICIOUS = "MALICIOUS"
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(StrEnum):
    """Qualitative model certainty in the investigative findings."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EvidenceProvenance(StrEnum):
    """Origin and provenance source for individual pieces of evidence."""

    CUSTOMER_STATEMENT = "customer_statement"
    DOCUMENT_EXTRACTION = "document_extraction"
    DEVICE_TELEPHONY = "device_telephony"
    CONSORTIUM_REGISTRY = "consortium_registry"
    RISK_ENGINE = "risk_engine"
    HISTORICAL_LEDGER = "historical_ledger"
    MODEL_INFERENCE = "model_inference"
    AI_ASSISTANT = "ai_assistant"


@dataclass(frozen=True)
class InvestigationFinding:
    """An individual forensic finding discovered during AI context analysis."""

    id: str
    category: FindingCategory
    explanation: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    supporting_evidence_references: list[str] = field(default_factory=list)
    source_provenance: EvidenceProvenance = EvidenceProvenance.CUSTOMER_STATEMENT


@dataclass(frozen=True)
class InvestigationModelMetadata:
    """Traceability metadata regarding the AI provider and execution context."""

    provider: str
    model_id: str
    latency_ms: int | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class InvestigationResult:
    """Complete structured domain representation of an AI investigation."""

    summary: str
    overall_risk_sentiment: RiskSentiment
    confidence: ConfidenceLevel
    confidence_score: (
        float  # 0.0 to 1.0 (model assessment certainty, NOT calibrated fraud probability)
    )
    findings: list[InvestigationFinding]
    contradictory_or_mitigating_evidence: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    suggested_next_steps: list[str] = field(default_factory=list)
    model_metadata: InvestigationModelMetadata | None = None
    input_snapshot: dict[str, Any] = field(default_factory=dict)


class ConversationRole(StrEnum):
    """Participant role in an investigation conversation."""

    OPERATOR = "operator"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    CUSTOMER = "customer"


class ConversationStatus(StrEnum):
    """Lifecycle status of an investigation conversation."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class ConversationTurn:
    """An individual turn in a multi-turn forensic investigation conversation."""

    turn_index: int
    role: ConversationRole
    content: str
    evidence_provenance: EvidenceProvenance | None = None
    evidence_references: list[str] = field(default_factory=list)
    findings: list[InvestigationFinding] = field(default_factory=list)
    risk_sentiment: RiskSentiment | None = None
    confidence: ConfidenceLevel | None = None
    confidence_score: float | None = None
    missing_information: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    model_metadata: dict[str, Any] = field(default_factory=dict)
