"""Domain models and value types for voice duress and coercion intelligence (P2-A6).

Defines structured categories of psychological coercion, social-engineering pressure,
and simulated acoustic voice-stress indicators extracted from call transcripts.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class CoercionCategory(StrEnum):
    """Specific categories of duress, coercion, and social engineering pressure."""

    AUTHORITY_IMPERSONATION = "AUTHORITY_IMPERSONATION"
    LEGAL_OR_CONSEQUENCE_THREAT = "LEGAL_OR_CONSEQUENCE_THREAT"
    URGENT_TRANSFER_DEMAND = "URGENT_TRANSFER_DEMAND"
    SECRECY_DEMAND = "SECRECY_DEMAND"
    BYPASS_SAFEGUARDS_INSTRUCTION = "BYPASS_SAFEGUARDS_INSTRUCTION"
    REMOTE_ACCESS_PRESSURE = "REMOTE_ACCESS_PRESSURE"
    INVESTMENT_GUARANTEE = "INVESTMENT_GUARANTEE"
    LEGITIMATE_EXPLANATION = "LEGITIMATE_EXPLANATION"


class CoercionSeverity(StrEnum):
    """Severity or strength of detected coercion evidence."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class CoercionLevel(StrEnum):
    """Aggregate coercion classification for the analyzed dialogue."""

    NONE = "NONE"
    SUSPECTED = "SUSPECTED"
    CONFIRMED_COERCION = "CONFIRMED_COERCION"
    UNKNOWN = "UNKNOWN"


class VoiceStressLevel(StrEnum):
    """Simulated acoustic tension level (advisory only)."""

    NONE = "NONE"
    LOW = "LOW"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"


@dataclass(frozen=True)
class VoiceStressEvidence:
    """Simulated voice-derived acoustic indicators.

    Mandatory Policy Rule: Voice stress alone is NOT proof of deception, fraud, or duress.
    It represents an advisory simulated acoustic telemetry signal only.
    """

    detected: bool | None = None
    level: VoiceStressLevel = VoiceStressLevel.NONE
    acoustic_indicators: list[str] = field(default_factory=list)
    speech_rate_wpm: int | None = None
    provenance: str = "simulated_acoustic_telemetry"
    is_simulated: bool = True
    disclaimer: str = (
        "Simulated acoustic indicator; voice stress is advisory only and not proof of "
        "deception or fraud."
    )


@dataclass(frozen=True)
class CoercionFinding:
    """An individual piece of coercion or mitigating evidence grounded in a transcript."""

    id: str
    category: CoercionCategory
    severity: CoercionSeverity
    is_explicit: bool
    explanation: str
    supporting_excerpt: str
    start_offset: int | None = None
    end_offset: int | None = None
    provenance: str = "simulated_call_transcript"


@dataclass(frozen=True)
class CoercionAnalysisResult:
    """Complete domain representation of a call transcript coercion analysis."""

    overall_coercion_level: CoercionLevel
    confidence: str  # LOW, MEDIUM, HIGH
    confidence_score: float  # Qualitative model certainty (0.0 to 1.0); NOT a fraud probability
    findings: list[CoercionFinding]
    voice_stress_signals: VoiceStressEvidence | None
    legitimate_explanations: list[str] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    summary: str = ""
    status: str = "COMPLETED"


def validate_transcript_excerpt(
    excerpt: str, transcript: str
) -> tuple[bool, int | None, int | None]:
    """Validate that a supporting excerpt exists as an exact verbatim substring in transcript.

    Returns:
        (is_valid, start_offset, end_offset)
    """
    if not excerpt or not transcript:
        return False, None, None

    # First attempt exact substring match
    start = transcript.find(excerpt)
    if start != -1:
        return True, start, start + len(excerpt)

    # Second attempt: strip leading/trailing quotes, backticks, or whitespace
    # that models sometimes add
    stripped = excerpt.strip(" \"'“”`\n\r\t")
    if stripped and len(stripped) >= 4:
        start = transcript.find(stripped)
        if start != -1:
            return True, start, start + len(stripped)

    return False, None, None
