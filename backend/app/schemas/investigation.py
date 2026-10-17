"""Pydantic schemas for AI-powered fraud investigation requests and responses."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.investigation import (
    ConfidenceLevel,
    EvidenceProvenance,
    FindingCategory,
    RiskSentiment,
)


class CustomerStatementEvidence(BaseModel):
    """Customer dialogue turn or statement submitted as evidence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    statement_id: str = Field(
        ..., max_length=64, description="Unique identifier for evidence referencing"
    )
    question: str = Field(..., max_length=1000)
    answer: str = Field(..., max_length=4000)
    channel: str = Field(default="chat", max_length=32)
    timestamp: str | None = Field(default=None, max_length=64)


class DocumentExtractionEvidence(BaseModel):
    """Extracted text and metadata from submitted document images or PDFs."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    doc_id: str = Field(
        ..., max_length=64, description="Unique identifier for document referencing"
    )
    document_type: str = Field(default="UNKNOWN", max_length=64)
    claimed_issuer: str | None = Field(default=None, max_length=255)
    claimed_amount: Decimal | None = Field(default=None, ge=0)
    extracted_text: str = Field(..., max_length=10000)
    verification_source: str | None = Field(default=None, max_length=255)


class TelephonyTelemetryEvidence(BaseModel):
    """Behavioral device and call telemetry indicators."""

    model_config = ConfigDict(extra="forbid")

    active_call_present: bool | None = None
    screen_sharing_active: bool | None = None
    voice_stress_detected: bool | None = None
    call_duration_seconds: int | None = Field(default=None, ge=0)


class RecipientIntelligenceEvidence(BaseModel):
    """Consortium and velocity intelligence about the payment recipient."""

    model_config = ConfigDict(extra="forbid")

    is_flagged_mule: bool | None = None
    account_age_days: int | None = Field(default=None, ge=0)
    fan_in_count_24h: int | None = Field(default=None, ge=0)
    fan_out_count_24h: int | None = Field(default=None, ge=0)
    payee_name_mismatch: bool | None = None
    routing_mismatch: bool | None = None


class InvestigateTransactionRequest(BaseModel):
    """Request payload to initiate an AI investigation on an existing transaction."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: UUID = Field(..., description="Target simulated transaction ID")
    assessment_id: UUID | None = Field(
        default=None, description="Optional specific deterministic assessment ID"
    )
    customer_statements: list[CustomerStatementEvidence] = Field(
        default_factory=list, max_length=50
    )
    document_extractions: list[DocumentExtractionEvidence] = Field(
        default_factory=list, max_length=20
    )
    telephony_telemetry: TelephonyTelemetryEvidence | None = None
    recipient_intelligence: RecipientIntelligenceEvidence | None = None
    coercion_cues: list[str] = Field(default_factory=list, max_length=20)
    correlation_id: str | None = Field(default=None, max_length=64)


# -------------------------------------------------------------
# Structured Output Schema for Gemini Model Calling
# -------------------------------------------------------------


class InvestigationFindingSchema(BaseModel):
    """Forensic finding schema for Gemini structured JSON generation."""

    id: str = Field(..., description="Finding identifier, e.g. FINDING-1")
    category: FindingCategory
    explanation: str = Field(..., description="Forensic explanation of the finding")
    severity: str = Field(..., description="Severity level: LOW, MEDIUM, HIGH, or CRITICAL")
    supporting_evidence_references: list[str] = Field(
        default_factory=list,
        description="Explicit references to input IDs, e.g. stmt_1, doc_inv_1, rule:RULE_NAME",
    )
    source_provenance: EvidenceProvenance = Field(
        default=EvidenceProvenance.CUSTOMER_STATEMENT,
        description="Provenance origin of the evidence source",
    )


class InvestigationStructuredOutput(BaseModel):
    """Target JSON schema returned by Gemini model generation."""

    summary: str = Field(..., description="Concise forensic summary of the investigation findings")
    overall_risk_sentiment: RiskSentiment = Field(
        ...,
        description=(
            "Qualitative risk classification: BENIGN, SUSPICIOUS, COERCED, MALICIOUS, or UNKNOWN"
        ),
    )
    confidence: ConfidenceLevel = Field(
        ...,
        description="Qualitative model confidence level: LOW, MEDIUM, or HIGH",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Qualitative certainty score (0.0 to 1.0); NOT a calibrated fraud probability",
    )
    findings: list[InvestigationFindingSchema] = Field(default_factory=list)
    contradictory_or_mitigating_evidence: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)


# -------------------------------------------------------------
# API Response Schemas
# -------------------------------------------------------------


class InvestigationFindingResponse(BaseModel):
    """API response model for an individual investigation finding."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    category: FindingCategory
    explanation: str
    severity: str
    supporting_evidence_references: list[str]
    source_provenance: EvidenceProvenance


class InvestigationModelMetadataResponse(BaseModel):
    """Traceability metadata for the AI provider."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    model_id: str
    latency_ms: int | None = None
    correlation_id: str | None = None


class InvestigationResponse(BaseModel):
    """Complete API response for a transaction AI investigation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    assessment_id: UUID | None = None
    summary: str
    overall_risk_sentiment: RiskSentiment
    confidence: ConfidenceLevel
    confidence_score: float
    findings: list[InvestigationFindingResponse]
    contradictory_or_mitigating_evidence: list[str]
    missing_information: list[str]
    unresolved_questions: list[str]
    suggested_next_steps: list[str]
    model_metadata: InvestigationModelMetadataResponse
    created_at: datetime


class InvestigationListResponse(BaseModel):
    """List of investigations for a given transaction."""

    transaction_id: UUID
    total_entries: int
    items: list[InvestigationResponse]
