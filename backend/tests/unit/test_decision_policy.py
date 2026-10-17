from app.domain.decision_policy import (
    POLICY_VERSION,
    CoercionSignal,
    InvestigationSignal,
    PolicyAction,
    PolicyInput,
    VerificationOutcome,
    VerificationSignal,
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
    coercion: CoercionSignal | None = None,
) -> PolicyInput:
    return PolicyInput(
        risk_score=score,
        risk_level=level,
        recommended_action=action,
        triggered_rule_ids=rules or [],
        missing_evidence=missing or [],
        investigation=investigation or InvestigationSignal(),
        coercion=coercion or CoercionSignal(),
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


# --- Verification signal (P2-A5) -------------------------------------------


def _input_v(
    *,
    score: int,
    level: RiskLevel,
    action: RecommendedAction,
    rules: list[str] | None = None,
    verification: VerificationOutcome | None = None,
) -> PolicyInput:
    return PolicyInput(
        risk_score=score,
        risk_level=level,
        recommended_action=action,
        triggered_rule_ids=rules or [],
        verification=VerificationSignal(outcome=verification),
    )


def test_verification_success_satisfies_medium_tier() -> None:
    result = decide(
        _input_v(
            score=30,
            level=RiskLevel.MEDIUM,
            action=RecommendedAction.REQUIRE_VERIFICATION,
            verification=VerificationOutcome.SUCCEEDED,
        )
    )
    assert result.action == PolicyAction.ALLOW
    assert "VERIFICATION_SATISFIED" in result.reason_codes


def test_verification_success_does_not_override_strong_hold() -> None:
    result = decide(
        _input_v(
            score=100,
            level=RiskLevel.CRITICAL,
            action=RecommendedAction.HOLD_FOR_INVESTIGATION,
            rules=["RULE_COERCION_AUTHORITY_PRESSURE"],
            verification=VerificationOutcome.SUCCEEDED,
        )
    )
    assert result.action == PolicyAction.HOLD_FOR_INVESTIGATION
    assert "VERIFICATION_INSUFFICIENT_RESIDUAL_RISK" in result.reason_codes


def test_verification_success_does_not_override_block() -> None:
    result = decide(
        _input_v(
            score=90,
            level=RiskLevel.CRITICAL,
            action=RecommendedAction.HOLD_FOR_INVESTIGATION,
            rules=["RULE_FLAGGED_MULE_ACCOUNT"],
            verification=VerificationOutcome.SUCCEEDED,
        )
    )
    assert result.action == PolicyAction.BLOCK


def test_verification_failure_escalates_to_hold_and_never_settles() -> None:
    for outcome in (
        VerificationOutcome.FAILED,
        VerificationOutcome.EXPIRED,
        VerificationOutcome.EXHAUSTED,
    ):
        result = decide(
            _input_v(
                score=30,
                level=RiskLevel.MEDIUM,
                action=RecommendedAction.REQUIRE_VERIFICATION,
                verification=outcome,
            )
        )
        assert result.action == PolicyAction.HOLD_FOR_INVESTIGATION
        assert result.action != PolicyAction.ALLOW
        assert f"VERIFICATION_{outcome.value}" in result.reason_codes


def test_verification_exhausted_on_low_risk_still_holds() -> None:
    result = decide(
        _input_v(
            score=5,
            level=RiskLevel.LOW,
            action=RecommendedAction.ALLOW,
            verification=VerificationOutcome.EXHAUSTED,
        )
    )
    assert result.action == PolicyAction.HOLD_FOR_INVESTIGATION


def test_explicit_coercion_escalates_to_hold() -> None:
    # Baseline is ALLOW or REQUIRE_VERIFICATION, but explicit critical coercion is detected
    result = decide(
        _input(
            score=30,
            level=RiskLevel.MEDIUM,
            action=RecommendedAction.REQUIRE_VERIFICATION,
            coercion=CoercionSignal(
                available=True,
                has_explicit_coercion=True,
                coercion_severity="CRITICAL",
                finding_refs=["COERCION-1"],
                supporting_excerpts=["You are placed under digital arrest right now."],
            ),
        )
    )
    assert result.action == PolicyAction.HOLD_FOR_INVESTIGATION
    assert "EXPLICIT_COERCION_HOLD" in result.reason_codes
    assert "COERCION-1" in result.investigation_finding_refs
    assert "You are placed under digital arrest right now." in result.supporting_evidence_refs


def test_explicit_coercion_persists_hold_after_verification_success() -> None:
    # Even if customer successfully enters OTP, strong explicit coercion prevents settlement!
    inp = PolicyInput(
        risk_score=35,
        risk_level=RiskLevel.MEDIUM,
        recommended_action=RecommendedAction.REQUIRE_VERIFICATION,
        verification=VerificationSignal(outcome=VerificationOutcome.SUCCEEDED),
        coercion=CoercionSignal(
            available=True,
            has_explicit_coercion=True,
            coercion_severity="HIGH",
            finding_refs=["COERCION-1"],
            supporting_excerpts=["Transfer immediately or police will arrive in 15 minutes."],
        ),
    )
    result = decide(inp)
    assert result.action == PolicyAction.HOLD_FOR_INVESTIGATION
    assert result.action != PolicyAction.ALLOW
    assert "VERIFICATION_INSUFFICIENT_RESIDUAL_RISK" in result.reason_codes


def test_voice_stress_alone_does_not_hold_or_block() -> None:
    # Acoustic telemetry alone is advisory; does not escalate baseline ALLOW to HOLD/BLOCK
    result = decide(
        _input(
            score=10,
            level=RiskLevel.LOW,
            action=RecommendedAction.ALLOW,
            coercion=CoercionSignal(
                available=True,
                has_explicit_coercion=False,
                voice_stress_only=True,
            ),
        )
    )
    assert result.action == PolicyAction.ALLOW
    assert "VOICE_STRESS_ALONE_NON_DISQUALIFYING" in result.reason_codes


def test_legitimate_explanation_noted_in_reason_codes() -> None:
    result = decide(
        _input(
            score=15,
            level=RiskLevel.LOW,
            action=RecommendedAction.ALLOW,
            coercion=CoercionSignal(
                available=True,
                has_explicit_coercion=False,
                has_legitimate_explanation=True,
            ),
        )
    )
    assert result.action == PolicyAction.ALLOW
    assert "LEGITIMATE_EXPLANATION_NOTED" in result.reason_codes


def test_coercion_provider_failed_preserves_deterministic_baseline() -> None:
    result = decide(
        _input(
            score=65,
            level=RiskLevel.HIGH,
            action=RecommendedAction.HOLD_FOR_INVESTIGATION,
            coercion=CoercionSignal(
                available=False,
                provider_failed=True,
            ),
        )
    )
    assert result.action == PolicyAction.HOLD_FOR_INVESTIGATION
    assert "COERCION_ANALYSIS_UNAVAILABLE_FALLBACK" in result.reason_codes
