"""Unit tests for the deterministic decision policy engine (P2-A4)."""

from app.domain.decision_policy import (
    POLICY_VERSION,
    InvestigationSignal,
    PolicyAction,
    PolicyInput,
    decide,
)
from app.domain.investigation import RiskSentiment
from app.domain.risk_engine import RecommendedAction, RiskLevel


def _input(
    *,
    score: int,
    level: RiskLevel,
    action: RecommendedAction,
    rules: list[str] | None = None,
    missing: list[str] | None = None,
    investigation: InvestigationSignal | None = None,
) -> PolicyInput:
    return PolicyInput(
        risk_score=score,
        risk_level=level,
        recommended_action=action,
        triggered_rule_ids=rules or [],
        missing_evidence=missing or [],
        investigation=investigation or InvestigationSignal(),
    )


def test_low_risk_allows() -> None:
    decision = _input(score=5, level=RiskLevel.LOW, action=RecommendedAction.ALLOW)
    result = decide(decision)
    assert result.action == PolicyAction.ALLOW
    assert result.requires_verification is False


def test_ambiguous_requires_verification() -> None:
    result = decide(
        _input(
            score=30,
            level=RiskLevel.MEDIUM,
            action=RecommendedAction.REQUIRE_VERIFICATION,
            missing=["Recipient account age unknown"],
        )
    )
    assert result.action == PolicyAction.REQUIRE_VERIFICATION
    assert result.requires_verification is True


def test_strong_coercion_and_recipient_risk_holds_not_blocks() -> None:
    result = decide(
        _input(
            score=100,
            level=RiskLevel.CRITICAL,
            action=RecommendedAction.HOLD_FOR_INVESTIGATION,
            rules=["RULE_COERCION_AUTHORITY_PRESSURE", "RULE_NEW_RECIPIENT"],
            investigation=InvestigationSignal(
                available=True, sentiment=RiskSentiment.COERCED, finding_refs=["FINDING-COERCION"]
            ),
        )
    )
    # Strong indicators prevent settlement but do not BLOCK without a verified mule hit.
    assert result.action == PolicyAction.HOLD_FOR_INVESTIGATION


def test_verified_mule_registry_hit_blocks() -> None:
    result = decide(
        _input(
            score=90,
            level=RiskLevel.CRITICAL,
            action=RecommendedAction.HOLD_FOR_INVESTIGATION,
            rules=["RULE_FLAGGED_MULE_ACCOUNT", "RULE_MULE_VELOCITY_FAN_IN_OUT"],
        )
    )
    assert result.action == PolicyAction.BLOCK
    assert "CONFIRMED_MULE_BENEFICIARY_BLOCK" in result.reason_codes


def test_voice_stress_alone_is_not_a_fraud_verdict() -> None:
    # The risk engine scores voice stress alone as LOW; the policy must not block/hold.
    result = decide(
        _input(
            score=5,
            level=RiskLevel.LOW,
            action=RecommendedAction.ALLOW,
            rules=["RULE_VOICE_STRESS_ADVISORY"],
        )
    )
    assert result.action == PolicyAction.ALLOW
    assert result.action not in (PolicyAction.BLOCK, PolicyAction.HOLD_FOR_INVESTIGATION)


def test_provider_failure_uses_deterministic_fallback_without_downgrade() -> None:
    result = decide(
        _input(
            score=60,
            level=RiskLevel.HIGH,
            action=RecommendedAction.HOLD_FOR_INVESTIGATION,
            investigation=InvestigationSignal(available=False, provider_failed=True),
        )
    )
    # Missing AI must not make a high-risk transaction safe.
    assert result.action == PolicyAction.HOLD_FOR_INVESTIGATION
    assert "AI_UNAVAILABLE_DETERMINISTIC_FALLBACK" in result.reason_codes


def test_conflicting_signals_take_conservative_action() -> None:
    # Deterministic says LOW, but investigation flags MALICIOUS -> escalate (conservative).
    result = decide(
        _input(
            score=10,
            level=RiskLevel.LOW,
            action=RecommendedAction.ALLOW,
            investigation=InvestigationSignal(
                available=True, sentiment=RiskSentiment.MALICIOUS, finding_refs=["F-1"]
            ),
        )
    )
    assert result.action == PolicyAction.HOLD_FOR_INVESTIGATION


def test_investigation_never_downgrades_deterministic_risk() -> None:
    # Deterministic HIGH -> HOLD; a BENIGN investigation must not downgrade to ALLOW.
    result = decide(
        _input(
            score=60,
            level=RiskLevel.HIGH,
            action=RecommendedAction.HOLD_FOR_INVESTIGATION,
            investigation=InvestigationSignal(available=True, sentiment=RiskSentiment.BENIGN),
        )
    )
    assert result.action == PolicyAction.HOLD_FOR_INVESTIGATION


def test_confidence_is_not_used_as_fraud_probability() -> None:
    # The policy input has no confidence field; sentiment alone drives escalation.
    assert not hasattr(InvestigationSignal(), "confidence_score")
    suspicious = decide(
        _input(
            score=10,
            level=RiskLevel.LOW,
            action=RecommendedAction.ALLOW,
            investigation=InvestigationSignal(available=True, sentiment=RiskSentiment.SUSPICIOUS),
        )
    )
    assert suspicious.action == PolicyAction.REQUIRE_VERIFICATION


def test_policy_version_and_reason_codes_are_stable() -> None:
    result = decide(
        _input(score=85, level=RiskLevel.CRITICAL, action=RecommendedAction.HOLD_FOR_INVESTIGATION)
    )
    assert result.policy_version == POLICY_VERSION == "p2a4.v1"
    assert result.reason_codes[0] == "RISK_LEVEL_CRITICAL"
    assert "DETERMINISTIC_BASELINE_HOLD_FOR_INVESTIGATION" in result.reason_codes


def test_unknown_sentiment_with_missing_info_requires_verification() -> None:
    result = decide(
        _input(
            score=10,
            level=RiskLevel.LOW,
            action=RecommendedAction.ALLOW,
            investigation=InvestigationSignal(
                available=True,
                sentiment=RiskSentiment.UNKNOWN,
                missing_information=["No customer statement provided"],
            ),
        )
    )
    assert result.action == PolicyAction.REQUIRE_VERIFICATION
