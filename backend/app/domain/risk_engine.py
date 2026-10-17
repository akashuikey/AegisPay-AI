"""Deterministic transaction risk evaluation engine and policy rules."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    """Categorical risk assessment tiers."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecommendedAction(StrEnum):
    """Simulated policy recommendation derived from deterministic risk evaluation."""

    ALLOW = "ALLOW"
    WARN_CUSTOMER = "WARN_CUSTOMER"
    REQUIRE_VERIFICATION = "REQUIRE_VERIFICATION"
    HOLD_FOR_INVESTIGATION = "HOLD_FOR_INVESTIGATION"


@dataclass(frozen=True)
class TransactionEvidence:
    """Structured input signals and evidence available for transaction risk evaluation.

    Missing evidence must remain None (unknown), not be assumed safe or dangerous.
    """

    # Core Transaction Features
    amount: Decimal
    currency: str = "INR"
    payment_rail: str = "UPI"
    recipient_name: str = ""
    recipient_identifier: str = ""
    purpose: str | None = None

    # Customer Historical Context
    customer_id: str | None = None
    historical_transaction_count: int | None = None
    avg_monthly_transfer_amount: Decimal | None = None
    recent_fd_liquidation: bool | None = None
    recent_fd_liquidation_amount: Decimal | None = None

    # Recipient Intelligence
    is_first_time_recipient: bool | None = None
    is_trusted_beneficiary: bool | None = None
    recipient_account_age_days: int | None = None
    fan_in_count_24h: int | None = None
    fan_out_count_24h: int | None = None
    is_flagged_mule: bool | None = None
    payee_name_mismatch: bool | None = None
    routing_mismatch: bool | None = None

    # Behavioral Signals (Device & Telephony)
    active_call_present: bool | None = None
    screen_sharing_active: bool | None = None
    voice_stress_detected: bool | None = None

    # Structured Contextual Indicators (Extracted by upstream/caller)
    coercive_language_detected: bool | None = None
    guaranteed_return_claimed: bool | None = None
    urgency_pressure_detected: bool | None = None
    instruction_to_ignore_bank_warnings: bool | None = None
    invoice_verified: bool | None = None


@dataclass(frozen=True)
class TriggeredRule:
    """An individual deterministic policy rule triggered during assessment."""

    rule_id: str
    rule_name: str
    description: str
    weight: int
    severity: RiskLevel
    evidence: str


@dataclass(frozen=True)
class RiskAssessmentResult:
    """Complete explainable result of a deterministic risk evaluation."""

    risk_score: int  # Relative risk score 0 to 100
    risk_level: RiskLevel
    recommended_action: RecommendedAction
    explanation: str
    triggered_rules: list[TriggeredRule]
    supporting_evidence: list[str]
    missing_evidence: list[str]
    input_snapshot: dict[str, Any] = field(default_factory=dict)


def evaluate_risk(evidence: TransactionEvidence) -> RiskAssessmentResult:
    """Evaluate transaction risk deterministically using supplied features and policy rules.

    Guarantees:
    - Never uses scenario names or identifiers.
    - Missing evidence is explicitly collected as unknown and never fabricated.
    - Trusted-recipient status cannot override strong coercion evidence.
    - Voice stress alone does not trigger a high risk score or block.
    - Produces explainable triggered rules and supporting evidence.
    """
    triggered_rules: list[TriggeredRule] = []
    supporting_evidence: list[str] = []
    missing_evidence: list[str] = []

    # 1. Track Missing Evidence Explicitly
    if evidence.recent_fd_liquidation is None:
        missing_evidence.append("recent_fd_liquidation")
    if evidence.is_first_time_recipient is None:
        missing_evidence.append("is_first_time_recipient")
    if evidence.is_trusted_beneficiary is None:
        missing_evidence.append("is_trusted_beneficiary")
    if evidence.is_flagged_mule is None:
        missing_evidence.append("mule_registry_record")
    if evidence.fan_in_count_24h is None:
        missing_evidence.append("payee_fan_in_velocity")
    if evidence.active_call_present is None:
        missing_evidence.append("active_call_telemetry")
    if evidence.screen_sharing_active is None:
        missing_evidence.append("screen_sharing_telemetry")
    if evidence.coercive_language_detected is None:
        missing_evidence.append("contextual_transcript_analysis")
    if evidence.guaranteed_return_claimed is None:
        missing_evidence.append("investment_prospectus_claims")
    if evidence.payee_name_mismatch is None:
        missing_evidence.append("vendor_ledger_verification")

    # -------------------------------------------------------------
    # Deterministic Rule 1: High-Value / Elevated Transfer Anomaly
    # -------------------------------------------------------------
    high_value_threshold = Decimal("100000.00")
    elevated_value_threshold = Decimal("50000.00")
    if evidence.amount >= high_value_threshold:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_HIGH_VALUE_ANOMALY",
                rule_name="High-Value Transfer Anomaly",
                description=(
                    "Transfer amount meets or exceeds the elevated review threshold of ₹1,00,000."
                ),
                weight=15,
                severity=RiskLevel.MEDIUM,
                evidence=(
                    f"Transfer amount of ₹{evidence.amount:,.2f} exceeds threshold "
                    f"of ₹{high_value_threshold:,.2f}"
                ),
            )
        )
        supporting_evidence.append(
            f"High-value payment amount: ₹{evidence.amount:,.2f} >= ₹{high_value_threshold:,.2f}"
        )
    elif evidence.amount >= elevated_value_threshold:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_ELEVATED_AMOUNT",
                rule_name="Elevated Transfer Amount",
                description=(
                    "Transfer amount meets or exceeds the monitoring threshold of ₹50,000."
                ),
                weight=10,
                severity=RiskLevel.LOW,
                evidence=(
                    f"Transfer amount of ₹{evidence.amount:,.2f} meets monitoring "
                    f"threshold of ₹{elevated_value_threshold:,.2f}"
                ),
            )
        )
        supporting_evidence.append(
            f"Elevated payment amount: ₹{evidence.amount:,.2f} >= ₹{elevated_value_threshold:,.2f}"
        )

    # -------------------------------------------------------------
    # Deterministic Rule 2: Unestablished / First-Time Beneficiary
    # -------------------------------------------------------------
    if evidence.is_first_time_recipient is True:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_NEW_RECIPIENT",
                rule_name="First-Time Recipient",
                description=(
                    "Payment is directed to a recipient with no prior payment history "
                    "from this account."
                ),
                weight=10,
                severity=RiskLevel.LOW,
                evidence=f"New payee '{evidence.recipient_name}' has no previous payment history.",
            )
        )
        supporting_evidence.append(
            f"Recipient '{evidence.recipient_name}' is an unestablished, first-time beneficiary."
        )

    # -------------------------------------------------------------
    # Deterministic Rule 3: Recent Fixed Deposit / Savings Liquidation
    # -------------------------------------------------------------
    if evidence.recent_fd_liquidation is True:
        liq_amount_str = (
            f" (₹{evidence.recent_fd_liquidation_amount:,.2f})"
            if evidence.recent_fd_liquidation_amount
            else ""
        )
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_RECENT_FD_LIQUIDATION",
                rule_name="Recent Term Deposit Liquidation",
                description=(
                    "Premature or sudden fixed deposit / savings liquidation "
                    "observed prior to transfer."
                ),
                weight=20,
                severity=RiskLevel.HIGH,
                evidence=(
                    f"Customer liquidated fixed deposits{liq_amount_str} "
                    "shortly before initiating transfer."
                ),
            )
        )
        supporting_evidence.append(
            f"Unusual pre-transfer liquidity creation: recent FD liquidation{liq_amount_str}."
        )

    # -------------------------------------------------------------
    # Deterministic Rule 4: Behavioral Telephony (Active Call & Screen Sharing)
    # -------------------------------------------------------------
    if evidence.active_call_present is True and evidence.screen_sharing_active is True:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_CALL_AND_SCREEN_SHARE",
                rule_name="Concurrent Active Call and Screen Sharing",
                description=(
                    "Device telemetry indicates remote access or screen sharing "
                    "concurrently with an active call."
                ),
                weight=25,
                severity=RiskLevel.CRITICAL,
                evidence=(
                    "Active phone call and remote screen sharing detected simultaneously "
                    "during payment initiation."
                ),
            )
        )
        supporting_evidence.append(
            "Concurrent active phone call and screen sharing detected on payer device."
        )
    elif evidence.screen_sharing_active is True:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_SCREEN_SHARE_ACTIVE",
                rule_name="Remote Screen Sharing Active",
                description=(
                    "Device telemetry indicates screen sharing or remote management "
                    "active during payment."
                ),
                weight=20,
                severity=RiskLevel.HIGH,
                evidence="Remote screen-sharing software active during payment creation.",
            )
        )
        supporting_evidence.append("Remote screen-sharing software active during payment creation.")
    elif evidence.active_call_present is True:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_ACTIVE_CALL_PRESENT",
                rule_name="Active Phone Call Telemetry",
                description=(
                    "Payer device is engaged in an active voice call while completing transaction."
                ),
                weight=10,
                severity=RiskLevel.MEDIUM,
                evidence="Active voice call in progress during transaction form submission.",
            )
        )
        supporting_evidence.append(
            "Active phone call present during transaction (amber behavioral indicator)."
        )

    # -------------------------------------------------------------
    # Deterministic Rule 5: Authority Coercion / Impersonation Indicators
    # -------------------------------------------------------------
    if evidence.coercive_language_detected is True:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_COERCION_AUTHORITY_PRESSURE",
                rule_name="Authority Impersonation / Coercive Language",
                description=(
                    "Contextual indicators detect arrest threats, legal authority claims, "
                    "or duress language."
                ),
                weight=30,
                severity=RiskLevel.CRITICAL,
                evidence=(
                    "Law enforcement / regulatory authority impersonation and legal "
                    "duress markers detected."
                ),
            )
        )
        supporting_evidence.append(
            "Severe coercion marker: legal intimidation / digital arrest narrative detected."
        )

    # -------------------------------------------------------------
    # Deterministic Rule 6: High-Yield / Guaranteed Return Scheme
    # -------------------------------------------------------------
    if evidence.guaranteed_return_claimed is True:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_GUARANTEED_RETURN_SCHEME",
                rule_name="Guaranteed Return / High-Yield Claim",
                description=(
                    "Contextual indicators detect unrealistic guaranteed financial returns "
                    "or investment scheme."
                ),
                weight=25,
                severity=RiskLevel.HIGH,
                evidence="Unrealistic guaranteed investment return or risk-free profit claim.",
            )
        )
        supporting_evidence.append(
            "High-yield investment fraud marker: promise of guaranteed or unrealistic returns."
        )

    # -------------------------------------------------------------
    # Deterministic Rule 7: Coached to Ignore Bank Warnings
    # -------------------------------------------------------------
    if evidence.instruction_to_ignore_bank_warnings is True:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_COACHED_IGNORE_WARNINGS",
                rule_name="Instructions to Bypass Bank Safeguards",
                description=(
                    "Customer was explicitly coached by a third party to dismiss bank warnings "
                    "or fabricate purpose."
                ),
                weight=20,
                severity=RiskLevel.HIGH,
                evidence=(
                    "Third-party instruction to ignore bank warnings or provide false "
                    "payment narrative."
                ),
            )
        )
        supporting_evidence.append(
            "Adversarial coaching marker: sender instructed to dismiss bank warnings."
        )

    # -------------------------------------------------------------
    # Deterministic Rule 8: Payee Identity / Routing Mismatch (Invoice Scam)
    # -------------------------------------------------------------
    if evidence.payee_name_mismatch is True or evidence.routing_mismatch is True:
        details = []
        if evidence.payee_name_mismatch:
            details.append("payee name mismatch with claimed vendor ledger")
        if evidence.routing_mismatch:
            details.append("routing/IFSC code altered from historical profile")
        detail_msg = " and ".join(details)
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_INVOICE_BENEFICIARY_MISMATCH",
                rule_name="Beneficiary Identity / Routing Mismatch",
                description=(
                    "Beneficiary account details contradict historical vendor records "
                    "or invoice documentation."
                ),
                weight=35,
                severity=RiskLevel.HIGH,
                evidence=f"Discrepancy detected: {detail_msg}.",
            )
        )
        supporting_evidence.append(f"Invoice tampering / discrepancy: {detail_msg}.")

    # -------------------------------------------------------------
    # Deterministic Rule 9: Mule Account / High Fan-In & Fan-Out Velocity
    # -------------------------------------------------------------
    if evidence.is_flagged_mule is True:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_FLAGGED_MULE_ACCOUNT",
                rule_name="Known Mule Account Registry Hit",
                description=(
                    "Beneficiary account identifier is flagged in consortium fraud registry."
                ),
                weight=40,
                severity=RiskLevel.CRITICAL,
                evidence=(
                    f"Recipient identifier '{evidence.recipient_identifier}' "
                    "flagged as mule/compromised account."
                ),
            )
        )
        supporting_evidence.append(
            f"Consortium intelligence match: payee '{evidence.recipient_identifier}' "
            "identified as mule."
        )

    if (evidence.fan_in_count_24h is not None and evidence.fan_in_count_24h >= 10) or (
        evidence.fan_out_count_24h is not None and evidence.fan_out_count_24h >= 10
    ):
        fan_in = evidence.fan_in_count_24h or 0
        fan_out = evidence.fan_out_count_24h or 0
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_MULE_VELOCITY_FAN_IN_OUT",
                rule_name="Abnormal Payee Fan-In/Fan-Out Velocity",
                description=(
                    "Beneficiary exhibits high multi-source rapid inflows followed "
                    "by rapid dispersal."
                ),
                weight=30,
                severity=RiskLevel.HIGH,
                evidence=(
                    f"High 24h velocity: {fan_in} unique senders (fan-in), "
                    f"{fan_out} rapid withdrawals (fan-out)."
                ),
            )
        )
        supporting_evidence.append(
            f"Mule velocity pattern: {fan_in} senders, {fan_out} withdrawals in 24h."
        )

    # -------------------------------------------------------------
    # Deterministic Rule 10: Voice Stress (Acoustic Tension Advisory)
    # Mandatory Rule: Voice stress alone is NOT proof of fraud!
    # -------------------------------------------------------------
    if evidence.voice_stress_detected is True:
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_VOICE_STRESS_ADVISORY",
                rule_name="Acoustic Voice Stress Indicator",
                description=(
                    "Vocal tension or stress markers detected during customer interaction."
                ),
                weight=5,  # Low weight to prevent voice stress alone from causing a block
                severity=RiskLevel.LOW,
                evidence=(
                    "Vocal acoustic analysis indicates elevated stress "
                    "(advisory signal only, not standalone fraud)."
                ),
            )
        )
        supporting_evidence.append(
            "Vocal stress telemetry detected (advisory only; not proof of fraud)."
        )

    # -------------------------------------------------------------
    # Deterministic Rule 11: Trusted Recipient Mitigation
    # Mandatory Guardrail: Trusted recipient CANNOT override strong evidence of coercion!
    # -------------------------------------------------------------
    has_coercion = evidence.coercive_language_detected is True
    if (
        evidence.is_trusted_beneficiary is True
        and evidence.is_first_time_recipient is False
        and not has_coercion
    ):
        triggered_rules.append(
            TriggeredRule(
                rule_id="RULE_ESTABLISHED_BENEFICIARY_MITIGATION",
                rule_name="Established Trusted Beneficiary Mitigation",
                description=(
                    "Recipient is an established, trusted beneficiary with consistent "
                    "historical interaction."
                ),
                weight=-25,
                severity=RiskLevel.LOW,
                evidence=(
                    f"Beneficiary '{evidence.recipient_name}' is in customer's "
                    "trusted list with confirmed history."
                ),
            )
        )
        supporting_evidence.append(
            f"Trusted relationship: '{evidence.recipient_name}' is an established "
            "beneficiary with no coercive indicators."
        )
    elif evidence.is_trusted_beneficiary is True and has_coercion:
        supporting_evidence.append(
            "Policy Guardrail Enforced: Trusted-recipient status bypassed due to "
            "presence of active coercion indicators."
        )

    # -------------------------------------------------------------
    # Score Aggregation & Bounding (0 to 100)
    # -------------------------------------------------------------
    raw_score = sum(r.weight for r in triggered_rules)
    bounded_score = max(0, min(100, raw_score))

    # -------------------------------------------------------------
    # Decision Policy Mapping
    # -------------------------------------------------------------
    if bounded_score >= 80:
        risk_level = RiskLevel.CRITICAL
        recommended_action = RecommendedAction.HOLD_FOR_INVESTIGATION
        explanation = (
            f"Critical fraud/coercion risk detected (Score {bounded_score}/100). "
            "Simulated pre-settlement hold recommended pending formal investigation."
        )
    elif bounded_score >= 50:
        risk_level = RiskLevel.HIGH
        recommended_action = RecommendedAction.HOLD_FOR_INVESTIGATION
        explanation = (
            f"High fraud risk identified (Score {bounded_score}/100). "
            "Simulated hold recommended pending verification of beneficiary or payment legitimacy."
        )
    elif bounded_score >= 25:
        risk_level = RiskLevel.MEDIUM
        recommended_action = RecommendedAction.REQUIRE_VERIFICATION
        explanation = (
            f"Elevated risk signals detected (Score {bounded_score}/100). "
            "Customer interaction or targeted confirmation required before simulated release."
        )
    else:
        risk_level = RiskLevel.LOW
        recommended_action = RecommendedAction.ALLOW
        explanation = (
            f"Transaction evaluated within normal parameters (Score {bounded_score}/100). "
            "Simulated settlement permitted."
        )

    # Snapshots of input
    snapshot = {
        "amount": str(evidence.amount),
        "currency": evidence.currency,
        "recipient_name": evidence.recipient_name,
        "recipient_identifier": evidence.recipient_identifier,
        "is_first_time_recipient": evidence.is_first_time_recipient,
        "is_trusted_beneficiary": evidence.is_trusted_beneficiary,
        "recent_fd_liquidation": evidence.recent_fd_liquidation,
        "active_call_present": evidence.active_call_present,
        "screen_sharing_active": evidence.screen_sharing_active,
        "coercive_language_detected": evidence.coercive_language_detected,
        "guaranteed_return_claimed": evidence.guaranteed_return_claimed,
        "is_flagged_mule": evidence.is_flagged_mule,
        "payee_name_mismatch": evidence.payee_name_mismatch,
    }

    return RiskAssessmentResult(
        risk_score=bounded_score,
        risk_level=risk_level,
        recommended_action=recommended_action,
        explanation=explanation,
        triggered_rules=triggered_rules,
        supporting_evidence=supporting_evidence,
        missing_evidence=missing_evidence,
        input_snapshot=snapshot,
    )
