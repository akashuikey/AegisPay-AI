"""Pydantic schemas for voice duress and coercion intelligence (P2-A6)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.coercion import (
    CoercionCategory,
    CoercionLevel,
    CoercionSeverity,
    VoiceStressLevel,
)
from app.domain.investigation import ConfidenceLevel
from app.schemas.investigation import InvestigationModelMetadataResponse


class VoiceStressInput(BaseModel):
    """Simulated acoustic indicators supplied as part of coercion analysis."""

    model_config = ConfigDict(extra="forbid")

    detected: bool | None = None
    level: VoiceStressLevel = VoiceStressLevel.NONE
    acoustic_indicators: list[str] = Field(default_factory=list, max_length=10)
    speech_rate_wpm: int | None = Field(default=None, ge=0, le=500)


class VoiceStressResponse(BaseModel):
    """Voice-derived telemetry response model with explicit simulation notice."""

    model_config = ConfigDict(from_attributes=True)

    detected: bool | None = None
    level: str = "NONE"
    acoustic_indicators: list[str] = Field(default_factory=list)
    speech_rate_wpm: int | None = None
    provenance: str = "simulated_acoustic_telemetry"
    is_simulated: bool = True
    disclaimer: str = (
        "Simulated acoustic indicator; voice stress is advisory only and not proof of "
        "deception or fraud."
    )


class CoercionFindingSchema(BaseModel):
    """Structured finding emitted by Gemini model or service validation."""

    id: str = Field(..., description="Finding identifier, e.g. COERCION-1")
    category: CoercionCategory
    severity: CoercionSeverity
    is_explicit: bool = Field(
        ...,
        description="True if the threat/demand is explicitly spoken; False if inferential",
    )
    explanation: str = Field(..., description="Forensic explanation of the finding")
    supporting_excerpt: str = Field(
        ...,
        description="Exact verbatim quote from the transcript",
    )
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    provenance: str = Field(default="simulated_call_transcript")


class CoercionFindingResponse(BaseModel):
    """API response model for an individual coercion finding."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    category: CoercionCategory
    severity: CoercionSeverity
    is_explicit: bool
    explanation: str
    supporting_excerpt: str
    start_offset: int | None = None
    end_offset: int | None = None
    provenance: str = "simulated_call_transcript"


class CoercionStructuredOutput(BaseModel):
    """Target JSON schema returned by Gemini model generation for call analysis."""

    overall_coercion_level: CoercionLevel = Field(
        ...,
        description="NONE, SUSPECTED, CONFIRMED_COERCION, or UNKNOWN",
    )
    confidence: ConfidenceLevel = Field(
        ...,
        description="Qualitative model certainty: LOW, MEDIUM, or HIGH",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model assessment certainty (0.0 to 1.0); NOT a calibrated fraud probability",
    )
    findings: list[CoercionFindingSchema] = Field(default_factory=list)
    legitimate_explanations: list[str] = Field(
        default_factory=list,
        description="Facts or statements supporting genuine uncoerced intent",
    )
    uncertainty_notes: list[str] = Field(
        default_factory=list,
        description="Gaps, ambiguities, or limitations in the transcript",
    )
    missing_information: list[str] = Field(default_factory=list)
    summary: str = Field(..., description="Forensic summary of coercion evaluation")


class AnalyzeCoercionRequest(BaseModel):
    """Request payload to analyze a simulated call transcript for duress and coercion."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    call_transcript: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Simulated phone call dialogue or interview transcript",
    )
    voice_stress: VoiceStressInput | None = None
    correlation_id: str | None = Field(default=None, max_length=64)


class CoercionAnalysisResponse(BaseModel):
    """Complete API response for a transaction coercion and duress analysis."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    overall_coercion_level: str
    confidence: str
    confidence_score: float
    findings: list[CoercionFindingResponse]
    voice_stress_signals: VoiceStressResponse | None = None
    legitimate_explanations: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    summary: str
    model_metadata: InvestigationModelMetadataResponse
    status: str
    transcript_snippet: str
    created_at: datetime
