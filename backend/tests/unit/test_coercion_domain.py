"""Unit tests for coercion domain logic, prompts, and excerpt grounding (P2-A6)."""

from app.domain.coercion import (
    VoiceStressEvidence,
    VoiceStressLevel,
    validate_transcript_excerpt,
)
from app.domain.coercion_prompts import (
    COERCION_ANALYSIS_SYSTEM_INSTRUCTION,
    build_coercion_prompt,
)


def test_validate_transcript_excerpt_exact_match() -> None:
    transcript = "This is Inspector Sharma from Cyber Crime. Transfer 500000 rupees immediately."
    excerpt = "Transfer 500000 rupees immediately."
    valid, start, end = validate_transcript_excerpt(excerpt, transcript)
    assert valid is True
    assert start == transcript.find(excerpt)
    assert end == start + len(excerpt)
    assert transcript[start:end] == excerpt


def test_validate_transcript_excerpt_stripped_quotes_match() -> None:
    transcript = 'Caller: "Do not disconnect this call or talk to your family."'
    # Model surrounded the quote with markdown / extra quotes
    excerpt = '  "Do not disconnect this call or talk to your family."  '
    valid, start, end = validate_transcript_excerpt(excerpt, transcript)
    assert valid is True
    assert start is not None and end is not None
    assert "Do not disconnect this call or talk to your family." in transcript[start:end]


def test_validate_transcript_excerpt_fabricated_quote_rejected() -> None:
    transcript = "I am transferring money for my daughter's college fees."
    fabricated_excerpt = "The caller threatened me with digital arrest and arrest warrant."
    valid, start, end = validate_transcript_excerpt(fabricated_excerpt, transcript)
    assert valid is False
    assert start is None
    assert end is None


def test_validate_transcript_excerpt_empty_or_whitespace() -> None:
    assert validate_transcript_excerpt("", "some transcript") == (False, None, None)
    assert validate_transcript_excerpt("some excerpt", "") == (False, None, None)


def test_voice_stress_evidence_defaults_and_disclaimer() -> None:
    stress = VoiceStressEvidence(
        detected=True,
        level=VoiceStressLevel.HIGH,
        acoustic_indicators=["micro-tremors"],
    )
    assert stress.is_simulated is True
    assert stress.provenance == "simulated_acoustic_telemetry"
    assert "advisory only" in stress.disclaimer.lower()
    assert "not proof of deception" in stress.disclaimer.lower()


def test_build_coercion_prompt_wraps_untrusted_transcript() -> None:
    transcript = "Transfer to RBI verification account now."
    prompt = build_coercion_prompt(transcript)

    assert "<untrusted_simulated_call_transcript>" in prompt
    assert "</untrusted_simulated_call_transcript>" in prompt
    assert transcript in prompt


def test_build_coercion_prompt_includes_acoustic_disclaimer_and_context() -> None:
    transcript = "Don't tell anyone."
    stress = VoiceStressEvidence(
        detected=True,
        level=VoiceStressLevel.ELEVATED,
        acoustic_indicators=["mild jitter"],
        speech_rate_wpm=180,
    )
    context = {
        "amount": "100000",
        "currency": "INR",
        "recipient_name": "Unknown Payee",
        "purpose": "Emergency tax",
    }
    prompt = build_coercion_prompt(transcript, voice_stress=stress, context=context)

    assert "STRESS LEVEL: ELEVATED" in prompt.upper() or "Acoustic stress level: ELEVATED" in prompt
    assert "180 WPM" in prompt
    assert "Emergency tax" in prompt
    assert "100000" in prompt
    assert stress.disclaimer in prompt


def test_system_instruction_contains_integrity_rules() -> None:
    instr = COERCION_ANALYSIS_SYSTEM_INSTRUCTION
    assert "ANTI-PROMPT-INJECTION" in instr
    assert "VERBATIM EXCERPTS ONLY" in instr
    assert "VOICE STRESS DISCLOSURE" in instr
    assert "CONFIDENCE CALIBRATION" in instr
