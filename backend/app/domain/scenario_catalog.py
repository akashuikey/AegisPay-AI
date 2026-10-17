"""Versioned end-to-end fraud simulation scenario catalogue (P2-A8).

Pure domain definitions. Each scenario declares SIMULATED transaction inputs and
contextual evidence, plus the operator-declared *expectations* (expected policy
action, final simulated state, and customer intervention).

Hard boundaries enforced by design:
- This module is data only. It performs no risk scoring, no AI calls, and no
  policy decisions. The normal assessment/decision pipeline processes these
  inputs through the same feature extraction, scoring, and decision logic.
- A scenario's declared expectation is NEVER fed into the pipeline and can NEVER
  override the authoritative policy result. Expectations exist only so the
  dashboard can compare observed-vs-expected (see ``scenario_evaluation``).
- All payment outcomes remain simulated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.domain.decision_policy import PolicyAction, VerificationOutcome
from app.domain.response_orchestration import CustomerActionRequired, ResponseType
from app.domain.state_machine import TransactionState

# Bump when the shape or membership of the catalogue changes in a way that
# consumers (dashboards, saved runs) must be able to distinguish.
CATALOG_VERSION = "p2a8.v1"


class VerificationBehavior(StrEnum):
    """How the simulation should exercise the customer verification challenge."""

    NONE = "NONE"  # Do not submit a challenge (even if one becomes available).
    SUBMIT_CORRECT_OTP = "SUBMIT_CORRECT_OTP"
    SUBMIT_INCORRECT_OTP = "SUBMIT_INCORRECT_OTP"


@dataclass(frozen=True)
class ScenarioTransactionInputs:
    """Simulated transaction creation inputs for a scenario."""

    amount: Decimal
    payment_rail: str
    recipient_name: str
    recipient_identifier: str
    purpose: str
    customer_id: str
    currency: str = "INR"


@dataclass(frozen=True)
class ScenarioExpectation:
    """Operator-declared expectation, compared against the observed outcome.

    These values are advisory documentation only. They never influence the
    authoritative pipeline and never alter a persisted decision.
    """

    policy_action: PolicyAction
    final_state: TransactionState
    response_type: ResponseType
    customer_action_required: CustomerActionRequired
    verification_outcome: VerificationOutcome | None = None
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScenarioDefinition:
    """A single, versioned, reusable end-to-end simulation scenario."""

    id: str
    version: str
    title: str
    description: str
    transaction: ScenarioTransactionInputs
    expectation: ScenarioExpectation

    # Deterministic risk-engine signal fields (bools/ints). Core transaction
    # fields (amount/currency/rail/recipient) are taken from ``transaction``.
    risk_evidence: dict[str, Any] = field(default_factory=dict)

    # Contextual investigation evidence passed to the AI investigation stage.
    customer_statements: list[dict[str, str]] = field(default_factory=list)
    telephony_telemetry: dict[str, Any] | None = None
    recipient_intelligence: dict[str, Any] | None = None
    coercion_cues: list[str] = field(default_factory=list)

    # Investigation gating: True forces it, False skips it, None auto-decides
    # from the deterministic risk tier (as the application workflow does).
    run_investigation: bool | None = None

    # Simulated call transcript + acoustic telemetry for the coercion stage.
    call_transcript: str | None = None
    voice_stress: dict[str, Any] | None = None
    # When True the coercion analysis is persisted BEFORE the decision so the
    # policy can consider it. When False it is produced after the initial
    # decision (e.g. intelligence that arrives during a verification window).
    coercion_before_decision: bool = True

    # How to drive the verification challenge when the decision requires it.
    verification_behavior: VerificationBehavior = VerificationBehavior.NONE

    # Simulated notification controls.
    simulate_notification_failure: bool = False


# ---------------------------------------------------------------------------
# The catalogue. Inputs are chosen to exercise the real pipeline; expectations
# document the intended deterministic outcome for comparison, never to force it.
# ---------------------------------------------------------------------------

_DIGITAL_ARREST = ScenarioDefinition(
    id="digital_arrest",
    version="1.0.0",
    title="Digital Arrest / Authority Impersonation",
    description=(
        "A victim is pressured by a fake law-enforcement caller into liquidating a "
        "fixed deposit and transferring funds to a 'government clearance account' while "
        "on an active call with screen sharing enabled."
    ),
    transaction=ScenarioTransactionInputs(
        amount=Decimal("250000.00"),
        payment_rail="RTGS",
        recipient_name="Govt Security Clearance Account",
        recipient_identifier="cbi.clearance@sbi",
        purpose="Urgent court identity bond",
        customer_id="cust_sim_digital_arrest",
    ),
    risk_evidence={
        "is_first_time_recipient": True,
        "is_trusted_beneficiary": False,
        "recent_fd_liquidation": True,
        "recent_fd_liquidation_amount": Decimal("250000.00"),
        "active_call_present": True,
        "screen_sharing_active": True,
        "coercive_language_detected": True,
        "urgency_pressure_detected": True,
        "voice_stress_detected": True,
    },
    customer_statements=[
        {
            "statement_id": "stmt_1",
            "question": "Why are you making this transfer now?",
            "answer": (
                "A CBI officer called and said my Aadhaar was used in money laundering. "
                "He said I am under digital arrest and must transfer to a secure "
                "clearance account or face immediate arrest. I cannot disconnect the call."
            ),
        }
    ],
    telephony_telemetry={
        "active_call_present": True,
        "screen_sharing_active": True,
        "voice_stress_detected": True,
    },
    coercion_cues=["authority_impersonation", "arrest_threat", "liquidation_pressure"],
    call_transcript=(
        "Caller: This is Inspector Sharma from the CBI cyber crime division. Your account "
        "is linked to a money laundering case and there is a non-bailable warrant. Do not "
        "disconnect this call and do not tell anyone. You must transfer the funds to our "
        "secure clearance account immediately or you will face arrest within the hour."
    ),
    voice_stress={
        "detected": True,
        "level": "HIGH",
        "acoustic_indicators": ["tremor", "elevated_pitch"],
        "speech_rate_wpm": 160,
    },
    coercion_before_decision=True,
    expectation=ScenarioExpectation(
        policy_action=PolicyAction.HOLD_FOR_INVESTIGATION,
        final_state=TransactionState.HELD_FOR_VERIFICATION,
        response_type=ResponseType.HOLD_PROTECTIVE,
        customer_action_required=CustomerActionRequired.CONTACT_BANK,
        limitations=[
            "Authority impersonation and screen-sharing signals are simulated inputs, "
            "not live device telemetry.",
        ],
    ),
)

_INVESTMENT_SCAM = ScenarioDefinition(
    id="investment_scam",
    version="1.0.0",
    title="High-Yield Investment Scam",
    description=(
        "A victim lured into a guaranteed-return crypto scheme is urged to transfer "
        "immediately and to dismiss any bank warnings."
    ),
    transaction=ScenarioTransactionInputs(
        amount=Decimal("85000.00"),
        payment_rail="IMPS",
        recipient_name="Apex Yield Asset Management",
        recipient_identifier="apexyield@icici",
        purpose="Crypto trading deposit",
        customer_id="cust_sim_investment_scam",
    ),
    risk_evidence={
        "is_first_time_recipient": True,
        "is_trusted_beneficiary": False,
        "recent_fd_liquidation": False,
        "guaranteed_return_claimed": True,
        "urgency_pressure_detected": True,
        "instruction_to_ignore_bank_warnings": True,
    },
    customer_statements=[
        {
            "statement_id": "stmt_1",
            "question": "What is this payment for?",
            "answer": (
                "I joined a Telegram group that guarantees daily returns on crypto trading. "
                "They told me to deposit quickly and to ignore any bank warnings."
            ),
        }
    ],
    coercion_cues=["guaranteed_returns", "ignore_bank_warnings"],
    run_investigation=True,
    expectation=ScenarioExpectation(
        policy_action=PolicyAction.HOLD_FOR_INVESTIGATION,
        final_state=TransactionState.HELD_FOR_VERIFICATION,
        response_type=ResponseType.HOLD_PROTECTIVE,
        customer_action_required=CustomerActionRequired.CONTACT_BANK,
        limitations=[
            "No independent verification of the investment platform is performed; the "
            "guaranteed-return claim is a simulated contextual signal.",
        ],
    ),
)

_FAKE_INVOICE = ScenarioDefinition(
    id="fake_invoice",
    version="1.0.0",
    title="Fake Invoice / Supplier Routing Mismatch",
    description=(
        "A routine supplier payment where the invoice bank details contradict the "
        "trusted vendor ledger (possible business email compromise)."
    ),
    transaction=ScenarioTransactionInputs(
        amount=Decimal("32500.00"),
        payment_rail="NEFT",
        recipient_name="Starling Supplies Private Ltd",
        recipient_identifier="9928172635@kotak",
        purpose="Invoice 48210 payment",
        customer_id="cust_sim_fake_invoice",
    ),
    risk_evidence={
        "is_first_time_recipient": True,
        "recent_fd_liquidation": False,
        "payee_name_mismatch": True,
        "routing_mismatch": True,
        "invoice_verified": False,
    },
    recipient_intelligence={
        "payee_name_mismatch": True,
        "routing_mismatch": True,
    },
    run_investigation=True,
    expectation=ScenarioExpectation(
        policy_action=PolicyAction.REQUIRE_VERIFICATION,
        final_state=TransactionState.VERIFICATION_REQUIRED,
        response_type=ResponseType.VERIFICATION_REQUIRED,
        customer_action_required=CustomerActionRequired.VERIFY_OTP,
        limitations=[
            "Invoice authenticity is not independently established; the ledger mismatch "
            "is a simulated signal and the document is treated as UNVERIFIED.",
        ],
    ),
)

_MULE_NETWORK = ScenarioDefinition(
    id="mule_network",
    version="1.0.0",
    title="Mule Account Velocity & Rapid Dispersal",
    description=(
        "A beneficiary flagged in consortium intelligence with abnormal fan-in/fan-out "
        "velocity. An explicit, independently verified deterministic block condition."
    ),
    transaction=ScenarioTransactionInputs(
        amount=Decimal("18000.00"),
        payment_rail="UPI",
        recipient_name="Ramesh K Mule",
        recipient_identifier="fastcash99@upi",
        purpose="Friend return",
        customer_id="cust_sim_mule_network",
    ),
    risk_evidence={
        "is_first_time_recipient": True,
        "recent_fd_liquidation": False,
        "is_flagged_mule": True,
        "fan_in_count_24h": 18,
        "fan_out_count_24h": 15,
    },
    recipient_intelligence={
        "is_flagged_mule": True,
        "fan_in_count_24h": 18,
        "fan_out_count_24h": 15,
    },
    run_investigation=True,
    expectation=ScenarioExpectation(
        policy_action=PolicyAction.BLOCK,
        final_state=TransactionState.CANCELLED_SIMULATED,
        response_type=ResponseType.BLOCK_SAFETY,
        customer_action_required=CustomerActionRequired.CONTACT_BANK,
        limitations=[
            "The consortium mule-registry hit is a simulated intelligence signal; no real "
            "registry is queried.",
        ],
    ),
)

_LEGITIMATE_HIGH_VALUE = ScenarioDefinition(
    id="legitimate_high_value",
    version="1.0.0",
    title="Legitimate High-Value Lease Payment",
    description=(
        "A routine high-value lease renewal to an established, trusted landlord with no "
        "coercive or anomaly indicators. Must not be treated as fraud."
    ),
    transaction=ScenarioTransactionInputs(
        amount=Decimal("250000.00"),
        payment_rail="RTGS",
        recipient_name="Maple Grove Properties",
        recipient_identifier="rent@maplegrove",
        purpose="Annual lease renewal",
        customer_id="cust_sim_legit_high_value",
    ),
    risk_evidence={
        "is_first_time_recipient": False,
        "is_trusted_beneficiary": True,
        "recent_fd_liquidation": False,
        "active_call_present": False,
        "screen_sharing_active": False,
        "coercive_language_detected": False,
        "guaranteed_return_claimed": False,
        "is_flagged_mule": False,
    },
    run_investigation=None,  # Low risk -> investigation skipped by the workflow.
    expectation=ScenarioExpectation(
        policy_action=PolicyAction.ALLOW,
        final_state=TransactionState.SETTLED_SIMULATED,
        response_type=ResponseType.ALLOW_SETTLED,
        customer_action_required=CustomerActionRequired.NONE,
        limitations=[
            "Trusted-beneficiary status is a simulated signal; it never overrides strong "
            "coercion evidence (see the coercion scenarios).",
        ],
    ),
)

_AMBIGUOUS_PAYMENT = ScenarioDefinition(
    id="ambiguous_payment",
    version="1.0.0",
    title="Ambiguous Payment with Missing Telemetry",
    description=(
        "A new payee with an active call but missing transcripts and unknown adverse "
        "history. Should require verification without auto-blocking."
    ),
    transaction=ScenarioTransactionInputs(
        amount=Decimal("85000.00"),
        payment_rail="UPI",
        recipient_name="Northstar Holdings",
        recipient_identifier="northstar@axis",
        purpose="Consulting deposit",
        customer_id="cust_sim_ambiguous",
    ),
    risk_evidence={
        "is_first_time_recipient": True,
        "active_call_present": True,
        # Other adverse signals explicitly unknown (omitted -> None).
    },
    telephony_telemetry={"active_call_present": True},
    # Deterministic ambiguity resolves to verification on its own; the contextual
    # investigation is intentionally skipped here to keep the demonstration focused
    # on the deterministic missing-evidence path.
    run_investigation=False,
    expectation=ScenarioExpectation(
        policy_action=PolicyAction.REQUIRE_VERIFICATION,
        final_state=TransactionState.VERIFICATION_REQUIRED,
        response_type=ResponseType.VERIFICATION_REQUIRED,
        customer_action_required=CustomerActionRequired.VERIFY_OTP,
        limitations=[
            "Several adverse signals are unknown; missing evidence is represented "
            "explicitly and never assumed safe or fraudulent.",
            "The AI investigation stage is skipped for this scenario; the outcome is "
            "driven entirely by the deterministic policy.",
        ],
    ),
)

_ORDINARY_STRESS = ScenarioDefinition(
    id="ordinary_stressed_customer",
    version="1.0.0",
    title="Ordinary Stressed Customer (No Coercion)",
    description=(
        "A customer who sounds stressed on the call but provides a legitimate, unpressured "
        "explanation. Voice stress alone must never cause a hold or block."
    ),
    transaction=ScenarioTransactionInputs(
        amount=Decimal("9000.00"),
        payment_rail="UPI",
        recipient_name="Anita Desai",
        recipient_identifier="anita.desai@upi",
        purpose="Repay borrowed money",
        customer_id="cust_sim_ordinary_stress",
    ),
    risk_evidence={
        "is_first_time_recipient": False,
        "is_trusted_beneficiary": False,
        "active_call_present": True,
        "voice_stress_detected": True,
        "coercive_language_detected": False,
    },
    call_transcript=(
        "Customer: Sorry, I'm a little out of breath after walking over. I'm simply "
        "repaying my friend Anita for the apartment deposit she covered for me last "
        "month. Nobody is pressuring me and I'm doing this of my own accord."
    ),
    voice_stress={
        "detected": True,
        "level": "ELEVATED",
        "acoustic_indicators": ["elevated_pitch"],
        "speech_rate_wpm": 150,
    },
    coercion_before_decision=True,
    run_investigation=None,  # Low risk -> investigation skipped.
    expectation=ScenarioExpectation(
        policy_action=PolicyAction.ALLOW,
        final_state=TransactionState.SETTLED_SIMULATED,
        response_type=ResponseType.ALLOW_SETTLED,
        customer_action_required=CustomerActionRequired.NONE,
        limitations=[
            "Voice stress is simulated acoustic telemetry and is advisory only; it is "
            "explicitly non-disqualifying on its own.",
        ],
    ),
)

_STRONG_COERCION_VERIFIED = ScenarioDefinition(
    id="strong_coercion_verified",
    version="1.0.0",
    title="Strong Coercion with Successful Verification",
    description=(
        "A medium-risk transfer that initially requires verification. Strong coercion "
        "intelligence then arrives. Even a successful OTP verification must NOT clear the "
        "coercion: the payment stays protectively held."
    ),
    transaction=ScenarioTransactionInputs(
        amount=Decimal("120000.00"),
        payment_rail="IMPS",
        recipient_name="Secure Holding Account",
        recipient_identifier="secure.hold@upi",
        purpose="Account verification transfer",
        customer_id="cust_sim_strong_coercion",
    ),
    risk_evidence={
        "is_first_time_recipient": True,
        "active_call_present": True,
        # Note: coercive_language is NOT set here, so the deterministic engine does
        # not escalate on its own; the coercion arrives via the coercion analysis
        # AFTER the initial verification-required decision.
    },
    telephony_telemetry={"active_call_present": True},
    run_investigation=False,
    call_transcript=(
        "Caller: This is the Enforcement Directorate. A warrant has been issued. Keep this "
        "confidential and do not disconnect. Transfer the money to the secure holding "
        "account now or your accounts will be frozen and you will be arrested."
    ),
    voice_stress={
        "detected": True,
        "level": "HIGH",
        "acoustic_indicators": ["tremor"],
        "speech_rate_wpm": 170,
    },
    coercion_before_decision=False,
    verification_behavior=VerificationBehavior.SUBMIT_CORRECT_OTP,
    expectation=ScenarioExpectation(
        policy_action=PolicyAction.HOLD_FOR_INVESTIGATION,
        final_state=TransactionState.HELD_FOR_VERIFICATION,
        response_type=ResponseType.HOLD_PROTECTIVE,
        customer_action_required=CustomerActionRequired.CONTACT_BANK,
        verification_outcome=VerificationOutcome.SUCCEEDED,
        limitations=[
            "A correct OTP only proves device/session control; it cannot prove the "
            "customer is free of coercion, so it does not release the hold.",
            "Driving the OTP submission requires the dev-mode OTP exposure setting; "
            "otherwise the verification stage is reported as unavailable in this environment.",
        ],
    ),
)


SCENARIO_CATALOG: tuple[ScenarioDefinition, ...] = (
    _DIGITAL_ARREST,
    _INVESTMENT_SCAM,
    _FAKE_INVOICE,
    _MULE_NETWORK,
    _LEGITIMATE_HIGH_VALUE,
    _AMBIGUOUS_PAYMENT,
    _ORDINARY_STRESS,
    _STRONG_COERCION_VERIFIED,
)

_SCENARIOS_BY_ID: dict[str, ScenarioDefinition] = {s.id: s for s in SCENARIO_CATALOG}


def list_scenarios() -> tuple[ScenarioDefinition, ...]:
    """Return the full, ordered scenario catalogue."""
    return SCENARIO_CATALOG


def get_scenario(scenario_id: str) -> ScenarioDefinition | None:
    """Return a scenario by its stable id, or None when unknown."""
    return _SCENARIOS_BY_ID.get(scenario_id)
