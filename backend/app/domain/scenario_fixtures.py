"""Scenario test fixtures providing concrete feature inputs for the 6 demo scenarios."""

from decimal import Decimal
from typing import Any

from app.domain.risk_engine import TransactionEvidence

SCENARIO_FIXTURES: dict[str, dict[str, Any]] = {
    "digital_arrest": {
        "id": "digital_arrest",
        "title": "Digital Arrest / Authority Impersonation",
        "summary": (
            "Victim pressured by fake law enforcement into liquidating FD and transferring "
            "funds while on active call and screen share."
        ),
        "evidence": TransactionEvidence(
            amount=Decimal("250000.00"),
            currency="INR",
            payment_rail="RTGS",
            recipient_name="Govt Security Clearance Account",
            recipient_identifier="cbi.clearance@sbi",
            purpose="Urgent court identity bond",
            customer_id="cust_da_01",
            is_first_time_recipient=True,
            is_trusted_beneficiary=False,
            recent_fd_liquidation=True,
            recent_fd_liquidation_amount=Decimal("250000.00"),
            active_call_present=True,
            screen_sharing_active=True,
            coercive_language_detected=True,
            urgency_pressure_detected=True,
            voice_stress_detected=True,
        ),
    },
    "investment_scam": {
        "id": "investment_scam",
        "title": "High-Yield Investment Fraud",
        "summary": (
            "Victim lured into high-yield scheme promising guaranteed daily returns, urged to "
            "transfer immediately and bypass warnings."
        ),
        "evidence": TransactionEvidence(
            amount=Decimal("85000.00"),
            currency="INR",
            payment_rail="IMPS",
            recipient_name="Apex Yield Asset Management",
            recipient_identifier="apexyield@icici",
            purpose="Crypto trading deposit",
            customer_id="cust_inv_01",
            is_first_time_recipient=True,
            is_trusted_beneficiary=False,
            guaranteed_return_claimed=True,
            urgency_pressure_detected=True,
            instruction_to_ignore_bank_warnings=True,
        ),
    },
    "fake_invoice": {
        "id": "fake_invoice",
        "title": "Fake Invoice / Supplier Routing Mismatch",
        "summary": (
            "Interception or alteration of supplier invoice where payment details "
            "contradict trusted vendor ledger."
        ),
        "evidence": TransactionEvidence(
            amount=Decimal("32500.00"),
            currency="INR",
            payment_rail="NEFT",
            recipient_name="Starling Supplies Private Ltd",
            recipient_identifier="9928172635@kotak",
            purpose="Invoice 48210 payment",
            customer_id="cust_inv_02",
            is_first_time_recipient=True,
            payee_name_mismatch=True,
            routing_mismatch=True,
            invoice_verified=False,
        ),
    },
    "mule_network": {
        "id": "mule_network",
        "title": "Mule Account Velocity & Rapid Dispersal",
        "summary": (
            "Recipient account flagged in consortium intelligence exhibiting abnormal "
            "fan-in and fan-out velocity."
        ),
        "evidence": TransactionEvidence(
            amount=Decimal("18000.00"),
            currency="INR",
            payment_rail="UPI",
            recipient_name="Ramesh K Mule",
            recipient_identifier="fastcash99@upi",
            purpose="Friend return",
            customer_id="cust_mule_01",
            is_first_time_recipient=True,
            is_flagged_mule=True,
            fan_in_count_24h=18,
            fan_out_count_24h=15,
        ),
    },
    "legitimate_high_value": {
        "id": "legitimate_high_value",
        "title": "Legitimate High-Value Lease Payment",
        "summary": (
            "Routine high-value lease renewal to an established, trusted landlord "
            "with zero coercive or anomaly indicators."
        ),
        "evidence": TransactionEvidence(
            amount=Decimal("250000.00"),
            currency="INR",
            payment_rail="RTGS",
            recipient_name="Maple Grove Properties",
            recipient_identifier="rent@maplegrove",
            purpose="Annual lease renewal",
            customer_id="cust_legit_01",
            is_first_time_recipient=False,
            is_trusted_beneficiary=True,
            recent_fd_liquidation=False,
            active_call_present=False,
            screen_sharing_active=False,
            coercive_language_detected=False,
            guaranteed_return_claimed=False,
            is_flagged_mule=False,
        ),
    },
    "ambiguous_payment": {
        "id": "ambiguous_payment",
        "title": "Ambiguous Payment with Missing Telemetry",
        "summary": (
            "New payee with active call, but missing transcripts and unknown adverse history. "
            "Must require verification without auto-blocking."
        ),
        "evidence": TransactionEvidence(
            amount=Decimal("85000.00"),
            currency="INR",
            payment_rail="UPI",
            recipient_name="Northstar Holdings",
            recipient_identifier="northstar@axis",
            purpose="Consulting deposit",
            customer_id="cust_ambi_01",
            is_first_time_recipient=True,
            active_call_present=True,
            # Explicitly unknown evidence fields (None)
            screen_sharing_active=None,
            recent_fd_liquidation=None,
            coercive_language_detected=None,
            guaranteed_return_claimed=None,
            is_flagged_mule=None,
        ),
    },
}
