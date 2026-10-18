"""Incremental evidence analysis for in-progress live voice calls (P2-A11).

Produces a versioned, advisory ``LiveEvidenceSnapshot`` grounded in actual transcript
segment spans. This is intentionally deterministic (no network) so analysis can run
continuously alongside the voice stream and be tested reliably; it mirrors the
grounded-synthesis style of the project's offline ``MockGeminiClient``. A Gemini
text-model strategy implementing the same ``analyze`` contract can be substituted
without changing callers.

Invariants:
- Findings cite the transcript segment sequence numbers that support them.
- Voice tone/emotion is never an input here; only transcript content is analyzed.
- The result is advisory only and never authorizes a transaction-state transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.investigation import ConfidenceLevel, RiskSentiment
from app.domain.live_voice import (
    LIVE_ANALYSIS_CONTRACT_VERSION,
    LiveEvidenceCategory,
    LiveEvidenceFinding,
    LiveEvidenceSnapshot,
    TranscriptSpeaker,
)


@dataclass(slots=True)
class TranscriptView:
    """A minimal, immutable view of a persisted transcript segment for analysis."""

    seq: int
    speaker: str
    content: str


# Evidence-category signal groups. These are *analysis* grounding cues over real
# transcript text, not dialogue scripts and not tied to any named demo scenario.
_SIGNALS: dict[LiveEvidenceCategory, tuple[str, ...]] = {
    LiveEvidenceCategory.AUTHORITY_IMPERSONATION: (
        "police",
        "officer",
        "cbi",
        "customs",
        "court",
        "arrest",
        "warrant",
        "enforcement",
        "investigation against",
        "legal case",
    ),
    LiveEvidenceCategory.SECRECY_PRESSURE: (
        "don't tell",
        "do not tell",
        "keep it secret",
        "keep this secret",
        "confidential",
        "stay on the line",
        "do not disconnect",
        "not tell anyone",
    ),
    LiveEvidenceCategory.URGENCY_PRESSURE: (
        "urgent",
        "immediately",
        "right now",
        "hurry",
        "within",
        "deadline",
        "before",
    ),
    LiveEvidenceCategory.REMOTE_ACCESS: (
        "anydesk",
        "teamviewer",
        "rustdesk",
        "screen share",
        "remote access",
        "install the app",
    ),
    LiveEvidenceCategory.SAFE_ACCOUNT_TRANSFER: (
        "safe account",
        "safe reserve",
        "secure account",
        "verification deposit",
        "hold the money",
    ),
    LiveEvidenceCategory.INVESTMENT_LURE: (
        "guaranteed",
        "returns",
        "profit",
        "investment",
        "crypto",
        "trading",
        "double your money",
    ),
}

# Reassuring / legitimate context that weakens a fraud hypothesis.
_MITIGATING_SIGNALS: tuple[str, ...] = (
    "my own account",
    "i know them",
    "known them for years",
    "my landlord",
    "my family",
    "my brother",
    "my sister",
    "regular payment",
    "i called them myself",
    "verified contact",
    "office supplier",
    "invoice from",
)


class LiveEvidenceAnalyzer:
    """Grounded incremental analyzer over accumulated transcript segments."""

    def analyze(
        self, segments: list[TranscriptView], context: dict[str, object] | None = None
    ) -> LiveEvidenceSnapshot:
        """Analyze transcript segments and return a point-in-time evidence snapshot."""
        findings: list[LiveEvidenceFinding] = []
        uncertainty: list[str] = []
        analyzed_through = max((s.seq for s in segments), default=-1)

        customer_segments = [s for s in segments if s.speaker == TranscriptSpeaker.CUSTOMER.value]

        # Aggregate category hits across customer statements, grounding each in the
        # specific segment sequence numbers where the signal appeared.
        category_refs: dict[LiveEvidenceCategory, list[int]] = {}
        mitigating_refs: list[int] = []
        for seg in customer_segments:
            lowered = seg.content.lower()
            for category, cues in _SIGNALS.items():
                if any(cue in lowered for cue in cues):
                    category_refs.setdefault(category, []).append(seg.seq)
            if any(cue in lowered for cue in _MITIGATING_SIGNALS):
                mitigating_refs.append(seg.seq)

        finding_index = 1
        for category, refs in category_refs.items():
            # Confidence grows when the same category is corroborated across turns.
            confidence = ConfidenceLevel.MEDIUM if len(refs) >= 2 else ConfidenceLevel.LOW
            findings.append(
                LiveEvidenceFinding(
                    id=f"LIVE-{finding_index}",
                    category=category,
                    explanation=_EXPLANATIONS[category],
                    confidence=confidence,
                    transcript_refs=sorted(set(refs)),
                    is_mitigating=False,
                )
            )
            finding_index += 1

        if mitigating_refs:
            findings.append(
                LiveEvidenceFinding(
                    id=f"LIVE-{finding_index}",
                    category=LiveEvidenceCategory.LEGITIMATE_EXPLANATION,
                    explanation=(
                        "Customer offered a routine/known-payee explanation that weakens a "
                        "coercion or scam hypothesis; corroborate against transaction history."
                    ),
                    confidence=ConfidenceLevel.LOW,
                    transcript_refs=sorted(set(mitigating_refs)),
                    is_mitigating=True,
                )
            )

        if not customer_segments:
            uncertainty.append("No customer statements transcribed yet.")
        elif not category_refs and not mitigating_refs:
            findings.append(
                LiveEvidenceFinding(
                    id="LIVE-1",
                    category=LiveEvidenceCategory.MISSING_VERIFICATION,
                    explanation=(
                        "No distinctive coercion, scam, or legitimacy signals detected so far; "
                        "continue verifying the payment purpose and payee relationship."
                    ),
                    confidence=ConfidenceLevel.LOW,
                    transcript_refs=[s.seq for s in customer_segments[-2:]],
                    is_mitigating=False,
                )
            )
            uncertainty.append("Purpose and payee relationship not yet confirmed.")

        sentiment = self._derive_sentiment(category_refs, bool(mitigating_refs))
        summary = self._summarize(category_refs, bool(mitigating_refs))

        return LiveEvidenceSnapshot(
            contract_version=LIVE_ANALYSIS_CONTRACT_VERSION,
            overall_sentiment=sentiment,
            findings=findings,
            uncertainty_notes=uncertainty,
            summary=summary,
            analyzed_through_seq=analyzed_through,
            generated_at=datetime.now(UTC),
        )

    @staticmethod
    def _derive_sentiment(
        category_refs: dict[LiveEvidenceCategory, list[int]], has_mitigating: bool
    ) -> RiskSentiment:
        coercion_categories = {
            LiveEvidenceCategory.AUTHORITY_IMPERSONATION,
            LiveEvidenceCategory.SECRECY_PRESSURE,
            LiveEvidenceCategory.SAFE_ACCOUNT_TRANSFER,
            LiveEvidenceCategory.REMOTE_ACCESS,
        }
        present = set(category_refs)
        # Require a *combination* of coercion markers before escalating to COERCED;
        # a single ambiguous mention is only SUSPICIOUS. Voice tone is never used.
        strong = present & coercion_categories
        if len(strong) >= 2:
            return RiskSentiment.COERCED
        if present:
            return RiskSentiment.SUSPICIOUS
        if has_mitigating:
            return RiskSentiment.BENIGN
        return RiskSentiment.UNKNOWN

    @staticmethod
    def _summarize(
        category_refs: dict[LiveEvidenceCategory, list[int]], has_mitigating: bool
    ) -> str:
        if not category_refs and not has_mitigating:
            return "Insufficient distinctive evidence so far; verification ongoing."
        parts: list[str] = []
        if category_refs:
            names = ", ".join(sorted(c.value for c in category_refs))
            parts.append(f"Potential risk signals: {names}.")
        if has_mitigating:
            parts.append("Some reassuring/legitimate context also reported.")
        return " ".join(parts)


_EXPLANATIONS: dict[LiveEvidenceCategory, str] = {
    LiveEvidenceCategory.AUTHORITY_IMPERSONATION: (
        "Customer referenced an authority figure (e.g. police/court/agency) in connection "
        "with the payment — a common impersonation pattern."
    ),
    LiveEvidenceCategory.SECRECY_PRESSURE: (
        "Customer was asked to keep the payment secret or stay on the line — an isolation tactic."
    ),
    LiveEvidenceCategory.URGENCY_PRESSURE: (
        "Customer described time pressure to transfer immediately."
    ),
    LiveEvidenceCategory.REMOTE_ACCESS: (
        "Customer mentioned installing remote-access/screen-sharing software."
    ),
    LiveEvidenceCategory.SAFE_ACCOUNT_TRANSFER: (
        "Customer was directed to move money to a 'safe'/verification account — banks never "
        "ask this."
    ),
    LiveEvidenceCategory.INVESTMENT_LURE: (
        "Customer described a guaranteed-return or investment opportunity."
    ),
}
