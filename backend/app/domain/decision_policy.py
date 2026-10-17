"""Deterministic transaction decision policy engine (P2-A4).

Receives validated, structured deterministic risk output and (optionally)
structured investigation findings, and returns a typed policy decision with an
explicitly permitted action, reason codes, and references. This is pure domain
logic with no I/O and no LLM calls.

Guardrails encoded here:
- The LLM never chooses the action. Investigation findings can only ESCALATE the
  conservative deterministic baseline; they can never downgrade it.
- The model's numeric confidence is never read — it is not a calibrated fraud
  probability. Only the categorical sentiment influences escalation.
- A missing or failed AI response never makes a high-risk transaction safe; the
  deterministic risk baseline stands.
- BLOCK is used only for an explicit, independently verified deterministic
  condition (a consortium mule-registry hit), never on model inference alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.investigation import RiskSentiment
from app.domain.risk_engine import RecommendedAction, RiskLevel

# Version every policy evaluation so decisions are reproducible and auditable.
POLICY_VERSION = "p2a4.v1"

# The single explicit deterministic condition that justifies outright BLOCK:
# an independently verified consortium mule-registry hit on the beneficiary.
CONSORTIUM_MULE_RULE_ID = "RULE_FLAGGED_MULE_ACCOUNT"


class PolicyAction(StrEnum):
    """Authoritative automated actions selected by the deterministic policy engine.

    Distinct from the risk engine's advisory ``RecommendedAction`` (which has no
    BLOCK): this is the final action the orchestrator maps to a state transition.
    """

    ALLOW = "ALLOW"
    REQUIRE_VERIFICATION = "REQUIRE_VERIFICATION"
    HOLD_FOR_INVESTIGATION = "HOLD_FOR_INVESTIGATION"
    BLOCK = "BLOCK"


# Ordered severity so escalation can take the strictly more conservative action.
_ACTION_SEVERITY: dict[PolicyAction, int] = {
    PolicyAction.ALLOW: 0,
    PolicyAction.REQUIRE_VERIFICATION: 1,
    PolicyAction.HOLD_FOR_INVESTIGATION: 2,
    PolicyAction.BLOCK: 3,
}


class VerificationOutcome(StrEnum):
    """Outcome of a simulated customer verification challenge, as a policy signal."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    EXHAUSTED = "EXHAUSTED"


@dataclass(frozen=True)
class InvestigationSignal:
    """Structured, validated investigation inputs the policy may consider."""

    available: bool = False
    provider_failed: bool = False
    sentiment: RiskSentiment | None = None
    finding_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VerificationSignal:
    """Simulated customer verification outcome as an additional (non-authorizing) signal."""

    outcome: VerificationOutcome | None = None


@dataclass(frozen=True)
class CoercionSignal:
    """Structured coercion and duress intelligence evaluated by policy (P2-A6)."""

    available: bool = False
    provider_failed: bool = False
    has_explicit_coercion: bool = False
    coercion_severity: str | None = None  # CRITICAL, HIGH, MEDIUM, LOW
    has_legitimate_explanation: bool = False
    voice_stress_only: bool = False
    finding_refs: list[str] = field(default_factory=list)
    supporting_excerpts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PolicyInput:
    """Validated structured inputs to the decision policy."""

    risk_score: int
    risk_level: RiskLevel
    recommended_action: RecommendedAction
    triggered_rule_ids: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    investigation: InvestigationSignal = field(default_factory=InvestigationSignal)
    verification: VerificationSignal = field(default_factory=VerificationSignal)
    coercion: CoercionSignal = field(default_factory=CoercionSignal)


@dataclass(frozen=True)
class PolicyDecision:
    """Typed, auditable decision produced by the policy engine."""

    policy_version: str
    action: PolicyAction
    risk_score: int
    risk_level: RiskLevel
    triggered_rule_ids: list[str]
    investigation_finding_refs: list[str]
    supporting_evidence_refs: list[str]
    reason_codes: list[str]
    missing_information: list[str]
    requires_verification: bool
    explanation: str


def _severity(action: PolicyAction) -> int:
    return _ACTION_SEVERITY[action]


def _base_action_from_risk(level: RiskLevel) -> PolicyAction:
    """Conservative baseline action from the deterministic risk tier."""
    if level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
        return PolicyAction.HOLD_FOR_INVESTIGATION
    if level == RiskLevel.MEDIUM:
        return PolicyAction.REQUIRE_VERIFICATION
    return PolicyAction.ALLOW


def _investigation_implied_action(signal: InvestigationSignal) -> PolicyAction | None:
    """Action implied by investigation sentiment alone (never downgrades).

    Numeric confidence is intentionally ignored (it is not a calibrated fraud
    probability). Returns None when the sentiment implies no escalation.
    """
    match signal.sentiment:
        case RiskSentiment.MALICIOUS | RiskSentiment.COERCED:
            return PolicyAction.HOLD_FOR_INVESTIGATION
        case RiskSentiment.SUSPICIOUS:
            return PolicyAction.REQUIRE_VERIFICATION
        case RiskSentiment.UNKNOWN:
            # Ambiguous: require verification only if the model flagged gaps.
            return PolicyAction.REQUIRE_VERIFICATION if signal.missing_information else None
        case _:
            # BENIGN or None: no escalation (and never a downgrade).
            return None


def _apply_verification(
    action: PolicyAction,
    outcome: VerificationOutcome | None,
    reason_codes: list[str],
    coercion: CoercionSignal | None = None,
) -> PolicyAction:
    """Fold the verification outcome into the deterministic action.

    - SUCCEEDED satisfies the REQUIRE_VERIFICATION gate (-> ALLOW) but never
      downgrades a HOLD or BLOCK driven by strong fraud or coercion evidence.
    - Strong explicit coercion evidence cannot be cleared by customer verification alone.
    - FAILED / EXPIRED / EXHAUSTED can never authorize settlement: a transaction
      that would otherwise ALLOW or merely REQUIRE_VERIFICATION is escalated to
      HOLD_FOR_INVESTIGATION.
    """
    if outcome is None:
        return action

    if outcome == VerificationOutcome.SUCCEEDED:
        if (
            coercion is not None
            and coercion.has_explicit_coercion
            and coercion.coercion_severity in ("CRITICAL", "HIGH")
        ):
            reason_codes.append("VERIFICATION_INSUFFICIENT_RESIDUAL_RISK")
            return (
                action
                if _severity(action) >= _severity(PolicyAction.HOLD_FOR_INVESTIGATION)
                else PolicyAction.HOLD_FOR_INVESTIGATION
            )

        if action == PolicyAction.REQUIRE_VERIFICATION:
            reason_codes.append("VERIFICATION_SATISFIED")
            return PolicyAction.ALLOW
        if action in (PolicyAction.HOLD_FOR_INVESTIGATION, PolicyAction.BLOCK):
            reason_codes.append("VERIFICATION_INSUFFICIENT_RESIDUAL_RISK")
        else:
            reason_codes.append("VERIFICATION_SUCCEEDED")
        return action

    # FAILED / EXPIRED / EXHAUSTED
    reason_codes.append(f"VERIFICATION_{outcome.value}")
    if _severity(action) < _severity(PolicyAction.HOLD_FOR_INVESTIGATION):
        reason_codes.append("VERIFICATION_FAILED_HOLD")
        return PolicyAction.HOLD_FOR_INVESTIGATION
    return action


def _explanation(action: PolicyAction, inp: PolicyInput) -> str:
    base = {
        PolicyAction.ALLOW: (
            "No significant adverse indicators; transaction may proceed through the "
            "existing simulated settlement workflow."
        ),
        PolicyAction.REQUIRE_VERIFICATION: (
            "Evidence is incomplete or signals conflict; an explicit verification step is "
            "required before any simulated settlement."
        ),
        PolicyAction.HOLD_FOR_INVESTIGATION: (
            "Multiple strong risk indicators present; the transaction is held from simulated "
            "settlement pending further investigation."
        ),
        PolicyAction.BLOCK: (
            "An explicit deterministic policy condition (verified mule-registry beneficiary) "
            "justifies rejecting the transaction via simulated cancellation."
        ),
    }[action]
    return (
        f"{base} Deterministic risk score {inp.risk_score}/100 ({inp.risk_level.value}); "
        f"policy {POLICY_VERSION}."
    )


def decide(inp: PolicyInput) -> PolicyDecision:
    """Select the permitted action from validated structured inputs."""
    reason_codes: list[str] = [f"RISK_LEVEL_{inp.risk_level.value}"]

    action = _base_action_from_risk(inp.risk_level)
    reason_codes.append(f"DETERMINISTIC_BASELINE_{action.value}")

    # Explicit, independently verified BLOCK condition.
    if CONSORTIUM_MULE_RULE_ID in inp.triggered_rule_ids and inp.risk_level == RiskLevel.CRITICAL:
        action = PolicyAction.BLOCK
        reason_codes.append("CONFIRMED_MULE_BENEFICIARY_BLOCK")

    inv = inp.investigation
    if inv.provider_failed:
        # Safe fallback: deterministic baseline stands; never downgrade.
        reason_codes.append("AI_UNAVAILABLE_DETERMINISTIC_FALLBACK")
    elif inv.available and inv.sentiment is not None:
        implied = _investigation_implied_action(inv)
        if implied is not None and _severity(implied) > _severity(action):
            action = implied
            reason_codes.append(f"INVESTIGATION_{inv.sentiment.value}_ESCALATION")
        else:
            reason_codes.append(f"INVESTIGATION_{inv.sentiment.value}_NO_ESCALATION")

    # Incomplete evidence at elevated risk must not resolve to ALLOW.
    if inp.missing_evidence and inp.risk_level in (
        RiskLevel.MEDIUM,
        RiskLevel.HIGH,
        RiskLevel.CRITICAL,
    ):
        if _severity(action) < _severity(PolicyAction.REQUIRE_VERIFICATION):
            action = PolicyAction.REQUIRE_VERIFICATION
            reason_codes.append("MISSING_EVIDENCE_REQUIRE_VERIFICATION")

    # P2-A6: Voice Duress and Coercion Intelligence
    coercion = inp.coercion
    if coercion.provider_failed:
        reason_codes.append("COERCION_ANALYSIS_UNAVAILABLE_FALLBACK")
    elif coercion.available:
        if coercion.has_legitimate_explanation:
            reason_codes.append("LEGITIMATE_EXPLANATION_NOTED")

        if coercion.voice_stress_only:
            reason_codes.append("VOICE_STRESS_ALONE_NON_DISQUALIFYING")

        if coercion.has_explicit_coercion and coercion.coercion_severity in ("CRITICAL", "HIGH"):
            if _severity(action) < _severity(PolicyAction.HOLD_FOR_INVESTIGATION):
                action = PolicyAction.HOLD_FOR_INVESTIGATION
                reason_codes.append("EXPLICIT_COERCION_HOLD")
            else:
                reason_codes.append("EXPLICIT_COERCION_MAINTAINED_HOLD")
        elif coercion.has_explicit_coercion and coercion.coercion_severity == "MEDIUM":
            if _severity(action) < _severity(PolicyAction.REQUIRE_VERIFICATION):
                action = PolicyAction.REQUIRE_VERIFICATION
                reason_codes.append("SUSPECTED_COERCION_REQUIRE_VERIFICATION")

    # Verification is an additional signal applied last; it resolves the
    # verification gate but never overrides strong fraud evidence (HOLD/BLOCK)
    # and never authorizes settlement on its own.
    action = _apply_verification(action, inp.verification.outcome, reason_codes, coercion)

    finding_refs = list(inv.finding_refs) + [
        ref for ref in coercion.finding_refs if ref not in inv.finding_refs
    ]
    evidence_refs = sorted(set(list(inv.evidence_refs) + list(coercion.supporting_excerpts)))

    return PolicyDecision(
        policy_version=POLICY_VERSION,
        action=action,
        risk_score=inp.risk_score,
        risk_level=inp.risk_level,
        triggered_rule_ids=list(inp.triggered_rule_ids),
        investigation_finding_refs=finding_refs,
        supporting_evidence_refs=evidence_refs,
        reason_codes=reason_codes,
        missing_information=list(inv.missing_information),
        requires_verification=action == PolicyAction.REQUIRE_VERIFICATION,
        explanation=_explanation(action, inp),
    )
