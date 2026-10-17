"""Unit tests for deterministic risk engine rules, scoring, guardrails, and scenario evaluation."""

from decimal import Decimal

from app.domain.risk_engine import (
    RecommendedAction,
    RiskLevel,
    TransactionEvidence,
    evaluate_risk,
)
from app.domain.scenario_fixtures import SCENARIO_FIXTURES


def test_voice_stress_alone_is_not_proof_of_fraud() -> None:
    """Verify that voice stress alone only issues a low-weight advisory and does not block."""
    evidence = TransactionEvidence(
        amount=Decimal("5000.00"),
        recipient_name="Local Grocery",
        recipient_identifier="grocery@upi",
        voice_stress_detected=True,
        # All other signals negative or neutral
        is_first_time_recipient=False,
        is_trusted_beneficiary=True,
        active_call_present=False,
        screen_sharing_active=False,
        coercive_language_detected=False,
        guaranteed_return_claimed=False,
        recent_fd_liquidation=False,
        is_flagged_mule=False,
    )
    result = evaluate_risk(evidence)
    # Score must be low and permitted
    assert result.risk_level == RiskLevel.LOW
    assert result.recommended_action == RecommendedAction.ALLOW
    assert any(r.rule_id == "RULE_VOICE_STRESS_ADVISORY" for r in result.triggered_rules)


def test_trusted_recipient_cannot_override_coercion() -> None:
    """Verify mandatory guardrail: trusted recipient status cannot suppress coercion alerts."""
    evidence = TransactionEvidence(
        amount=Decimal("150000.00"),
        recipient_name="Trusted Friend",
        recipient_identifier="friend@upi",
        is_first_time_recipient=False,
        is_trusted_beneficiary=True,  # Trusted!
        coercive_language_detected=True,  # Under duress / authority coercion
        active_call_present=True,
    )
    result = evaluate_risk(evidence)

    # Mitigation rule MUST NOT trigger when coercion is active
    assert not any(
        r.rule_id == "RULE_ESTABLISHED_BENEFICIARY_MITIGATION" for r in result.triggered_rules
    )
    assert any(r.rule_id == "RULE_COERCION_AUTHORITY_PRESSURE" for r in result.triggered_rules)
    assert result.risk_score >= 50
    assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert "Policy Guardrail Enforced: Trusted-recipient status bypassed" in " ".join(
        result.supporting_evidence
    )


def test_missing_evidence_is_tracked_explicitly() -> None:
    """Verify missing evidence fields (None) are collected explicitly and not assumed safe."""
    evidence = TransactionEvidence(
        amount=Decimal("15000.00"),
        recipient_name="Unknown Merchant",
        recipient_identifier="merchant@upi",
        # None = unobserved/missing
        recent_fd_liquidation=None,
        active_call_present=None,
        screen_sharing_active=None,
        coercive_language_detected=None,
        guaranteed_return_claimed=None,
        is_flagged_mule=None,
        fan_in_count_24h=None,
    )
    result = evaluate_risk(evidence)

    assert "recent_fd_liquidation" in result.missing_evidence
    assert "active_call_telemetry" in result.missing_evidence
    assert "screen_sharing_telemetry" in result.missing_evidence
    assert "contextual_transcript_analysis" in result.missing_evidence
    assert "mule_registry_record" in result.missing_evidence


def test_scenario_1_digital_arrest() -> None:
    """Evaluate Scenario 1: Digital arrest / authority impersonation produces CRITICAL risk."""
    evidence = SCENARIO_FIXTURES["digital_arrest"]["evidence"]
    result = evaluate_risk(evidence)

    assert result.risk_score >= 80
    assert result.risk_level == RiskLevel.CRITICAL
    assert result.recommended_action == RecommendedAction.HOLD_FOR_INVESTIGATION
    rule_ids = {r.rule_id for r in result.triggered_rules}
    assert "RULE_HIGH_VALUE_ANOMALY" in rule_ids
    assert "RULE_NEW_RECIPIENT" in rule_ids
    assert "RULE_RECENT_FD_LIQUIDATION" in rule_ids
    assert "RULE_CALL_AND_SCREEN_SHARE" in rule_ids
    assert "RULE_COERCION_AUTHORITY_PRESSURE" in rule_ids


def test_scenario_2_investment_scam() -> None:
    """Evaluate Scenario 2: Guaranteed return investment fraud produces HIGH risk."""
    evidence = SCENARIO_FIXTURES["investment_scam"]["evidence"]
    result = evaluate_risk(evidence)

    assert result.risk_score >= 55
    assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert result.recommended_action == RecommendedAction.HOLD_FOR_INVESTIGATION
    rule_ids = {r.rule_id for r in result.triggered_rules}
    assert "RULE_GUARANTEED_RETURN_SCHEME" in rule_ids
    assert "RULE_COACHED_IGNORE_WARNINGS" in rule_ids
    assert "RULE_NEW_RECIPIENT" in rule_ids


def test_scenario_3_fake_invoice() -> None:
    """Evaluate Scenario 3: Payee identity / routing mismatch produces HIGH risk."""
    evidence = SCENARIO_FIXTURES["fake_invoice"]["evidence"]
    result = evaluate_risk(evidence)

    assert result.risk_score >= 45
    assert result.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)
    rule_ids = {r.rule_id for r in result.triggered_rules}
    assert "RULE_INVOICE_BENEFICIARY_MISMATCH" in rule_ids
    assert "RULE_NEW_RECIPIENT" in rule_ids


def test_scenario_4_mule_network() -> None:
    """Evaluate Scenario 4: Mule registry hit & high fan-in/fan-out produces HIGH/CRITICAL risk."""
    evidence = SCENARIO_FIXTURES["mule_network"]["evidence"]
    result = evaluate_risk(evidence)

    assert result.risk_score >= 50
    assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert result.recommended_action == RecommendedAction.HOLD_FOR_INVESTIGATION
    rule_ids = {r.rule_id for r in result.triggered_rules}
    assert "RULE_FLAGGED_MULE_ACCOUNT" in rule_ids


def test_scenario_5_legitimate_high_value_payment() -> None:
    """Evaluate Scenario 5: Legitimate high-value payment is ALLOWED and NOT blocked."""
    evidence = SCENARIO_FIXTURES["legitimate_high_value"]["evidence"]
    result = evaluate_risk(evidence)

    # Must be LOW risk and ALLOWed
    assert result.risk_score <= 20
    assert result.risk_level == RiskLevel.LOW
    assert result.recommended_action == RecommendedAction.ALLOW
    rule_ids = {r.rule_id for r in result.triggered_rules}
    assert "RULE_ESTABLISHED_BENEFICIARY_MITIGATION" in rule_ids
    assert "RULE_COERCION_AUTHORITY_PRESSURE" not in rule_ids


def test_scenario_6_ambiguous_payment() -> None:
    """Evaluate Scenario 6: Ambiguous payment requires verification and lists missing data."""
    evidence = SCENARIO_FIXTURES["ambiguous_payment"]["evidence"]
    result = evaluate_risk(evidence)

    # Score reflects uncertainty (MEDIUM risk, REQUIRE_VERIFICATION, NOT auto-blocked!)
    assert 25 <= result.risk_score < 55
    assert result.risk_level == RiskLevel.MEDIUM
    assert result.recommended_action == RecommendedAction.REQUIRE_VERIFICATION
    assert len(result.missing_evidence) > 0
    assert "contextual_transcript_analysis" in result.missing_evidence


def test_score_boundaries_clamping() -> None:
    """Verify that aggregate score is always clamped between 0 and 100."""
    # Negative mitigation test
    low_evidence = TransactionEvidence(
        amount=Decimal("100.00"),
        is_trusted_beneficiary=True,
        is_first_time_recipient=False,
    )
    res_low = evaluate_risk(low_evidence)
    assert res_low.risk_score >= 0

    # Over-accumulated risk test
    high_evidence = TransactionEvidence(
        amount=Decimal("500000.00"),
        is_first_time_recipient=True,
        recent_fd_liquidation=True,
        active_call_present=True,
        screen_sharing_active=True,
        coercive_language_detected=True,
        guaranteed_return_claimed=True,
        instruction_to_ignore_bank_warnings=True,
        is_flagged_mule=True,
        payee_name_mismatch=True,
    )
    res_high = evaluate_risk(high_evidence)
    assert res_high.risk_score <= 100
