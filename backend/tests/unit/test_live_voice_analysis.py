"""Unit tests for the grounded incremental evidence analyzer (P2-A11)."""

from __future__ import annotations

from app.domain.investigation import RiskSentiment
from app.domain.live_voice import LIVE_ANALYSIS_CONTRACT_VERSION, LiveEvidenceCategory
from app.services.live_voice_analysis import LiveEvidenceAnalyzer, TranscriptView


def _views(*pairs: tuple[int, str, str]) -> list[TranscriptView]:
    return [TranscriptView(seq=s, speaker=sp, content=c) for s, sp, c in pairs]


def test_findings_are_grounded_in_transcript_refs() -> None:
    analyzer = LiveEvidenceAnalyzer()
    segments = _views(
        (0, "assistant", "What is this payment for?"),
        (1, "customer", "A police officer said I must pay urgently to a safe account."),
    )
    snapshot = analyzer.analyze(segments)
    assert snapshot.contract_version == LIVE_ANALYSIS_CONTRACT_VERSION
    assert snapshot.analyzed_through_seq == 1
    categories = {f.category for f in snapshot.findings}
    assert LiveEvidenceCategory.AUTHORITY_IMPERSONATION in categories
    assert LiveEvidenceCategory.SAFE_ACCOUNT_TRANSFER in categories
    # Every non-mitigating finding cites the customer segment (seq 1).
    for finding in snapshot.findings:
        assert 1 in finding.transcript_refs


def test_multiple_coercion_markers_escalate_to_coerced() -> None:
    analyzer = LiveEvidenceAnalyzer()
    segments = _views(
        (0, "customer", "A CBI officer is on the line and told me to keep this secret."),
        (1, "customer", "He said move it to a safe account right now."),
    )
    snapshot = analyzer.analyze(segments)
    assert snapshot.overall_sentiment == RiskSentiment.COERCED


def test_single_ambiguous_marker_is_only_suspicious_not_coerced() -> None:
    analyzer = LiveEvidenceAnalyzer()
    segments = _views((0, "customer", "They said it is a bit urgent."))
    snapshot = analyzer.analyze(segments)
    assert snapshot.overall_sentiment == RiskSentiment.SUSPICIOUS


def test_legitimate_explanation_is_mitigating_and_benign() -> None:
    analyzer = LiveEvidenceAnalyzer()
    segments = _views((0, "customer", "It's a regular payment to my landlord, I know them."))
    snapshot = analyzer.analyze(segments)
    assert snapshot.overall_sentiment == RiskSentiment.BENIGN
    assert any(f.is_mitigating for f in snapshot.findings)


def test_no_signals_yields_missing_verification() -> None:
    analyzer = LiveEvidenceAnalyzer()
    segments = _views((0, "customer", "Hello, can you hear me?"))
    snapshot = analyzer.analyze(segments)
    assert snapshot.overall_sentiment == RiskSentiment.UNKNOWN
    assert any(f.category == LiveEvidenceCategory.MISSING_VERIFICATION for f in snapshot.findings)


def test_assistant_only_segments_do_not_fabricate_customer_evidence() -> None:
    """Assistant text must not be mined for customer coercion signals."""
    analyzer = LiveEvidenceAnalyzer()
    segments = _views((0, "assistant", "Did a police officer ask you to move money urgently?"))
    snapshot = analyzer.analyze(segments)
    categories = {f.category for f in snapshot.findings}
    assert LiveEvidenceCategory.AUTHORITY_IMPERSONATION not in categories
