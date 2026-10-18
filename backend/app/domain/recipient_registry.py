"""Fictional recipient registry domain model and deterministic demo dataset (P2-A12).

Contains 20 completely fictional UPI identities with varied banking metadata, account ages,
and risk indicators for simulated fraud evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID


class RecipientCategory(StrEnum):
    """Categorical risk tier of a fictional recipient."""

    TRUSTED = "TRUSTED"
    UNKNOWN = "UNKNOWN"
    HIGH_RISK = "HIGH_RISK"


@dataclass(frozen=True)
class FictionalRecipientRecord:
    """A persistent fictional recipient record."""

    id: UUID
    upi_id: str
    display_name: str
    bank_name: str
    branch_region: str
    account_age_days: int
    category: RecipientCategory
    is_trusted_beneficiary: bool
    is_flagged_mule: bool
    complaint_count: int
    fan_in_count_24h: int
    fan_out_count_24h: int
    typical_amount: Decimal | None
    typical_frequency: str | None
    history_summary: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    seed_version: int = 1


# ---------------------------------------------------------------------------
# Exactly 20 Deterministic Fictional Recipient Records:
# 8 Established Legitimate Recipients
# 5 Newly Introduced / Insufficiently Known Recipients
# 7 High-Risk Simulated Scam / Mule-Network Recipients
# ---------------------------------------------------------------------------

FICTIONAL_RECIPIENTS_SEED_DATA: list[dict[str, Any]] = [
    # 1-8: Established Legitimate Recipients (TRUSTED)
    {
        "id": "20000000-0000-0000-0000-000000000001",
        "upi_id": "ananya.sharma@okaxis",
        "display_name": "Ananya Sharma",
        "bank_name": "Axis Bank (Simulated)",
        "branch_region": "Mumbai Metro",
        "account_age_days": 850,
        "category": "TRUSTED",
        "is_trusted_beneficiary": True,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 2,
        "fan_out_count_24h": 1,
        "typical_amount": Decimal("3500.00"),
        "typical_frequency": "MONTHLY",
        "history_summary": {
            "transfers_count": 18,
            "avg_amount": 3200.0,
            "relationship": "Friend/Family",
            "first_transfer_date": "2024-03-10",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000002",
        "upi_id": "delhi.power.corp@icici",
        "display_name": "BSES Delhi Power Distribution",
        "bank_name": "ICICI Bank (Simulated)",
        "branch_region": "Delhi North",
        "account_age_days": 1820,
        "category": "TRUSTED",
        "is_trusted_beneficiary": True,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 45,
        "fan_out_count_24h": 2,
        "typical_amount": Decimal("2450.00"),
        "typical_frequency": "MONTHLY",
        "history_summary": {
            "transfers_count": 24,
            "avg_amount": 2300.0,
            "merchant_type": "Utility",
            "first_transfer_date": "2023-01-15",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000003",
        "upi_id": "techflow.solutions@hdfc",
        "display_name": "TechFlow IT Solutions Pvt Ltd",
        "bank_name": "HDFC Bank (Simulated)",
        "branch_region": "Bengaluru Tech Park",
        "account_age_days": 1200,
        "category": "TRUSTED",
        "is_trusted_beneficiary": True,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 12,
        "fan_out_count_24h": 5,
        "typical_amount": Decimal("45000.00"),
        "typical_frequency": "MONTHLY",
        "history_summary": {
            "transfers_count": 8,
            "avg_amount": 42000.0,
            "merchant_type": "Vendor B2B",
            "first_transfer_date": "2024-01-20",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000004",
        "upi_id": "prime.groceries.retail@sbi",
        "display_name": "Prime Supermarket Retail",
        "bank_name": "SBI (Simulated)",
        "branch_region": "Pune Central",
        "account_age_days": 650,
        "category": "TRUSTED",
        "is_trusted_beneficiary": True,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 120,
        "fan_out_count_24h": 4,
        "typical_amount": Decimal("1800.00"),
        "typical_frequency": "WEEKLY",
        "history_summary": {
            "transfers_count": 45,
            "avg_amount": 1650.0,
            "merchant_type": "Retail Groceries",
            "first_transfer_date": "2024-05-01",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000005",
        "upi_id": "rohit.verma.rent@kotak",
        "display_name": "Rohit Verma Landlord",
        "bank_name": "Kotak Mahindra (Simulated)",
        "branch_region": "Bengaluru East",
        "account_age_days": 980,
        "category": "TRUSTED",
        "is_trusted_beneficiary": True,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 1,
        "fan_out_count_24h": 1,
        "typical_amount": Decimal("28000.00"),
        "typical_frequency": "MONTHLY",
        "history_summary": {
            "transfers_count": 11,
            "avg_amount": 28000.0,
            "relationship": "Landlord",
            "first_transfer_date": "2023-11-01",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000006",
        "upi_id": "apollo.pharmacy.direct@yesbank",
        "display_name": "Apollo Meds Direct",
        "bank_name": "Yes Bank (Simulated)",
        "branch_region": "Hyderabad Jubilee",
        "account_age_days": 1450,
        "category": "TRUSTED",
        "is_trusted_beneficiary": True,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 80,
        "fan_out_count_24h": 3,
        "typical_amount": Decimal("1200.00"),
        "typical_frequency": "MONTHLY",
        "history_summary": {
            "transfers_count": 15,
            "avg_amount": 1150.0,
            "merchant_type": "Pharmacy",
            "first_transfer_date": "2023-08-14",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000007",
        "upi_id": "cult.fitness.centre@indusind",
        "display_name": "Cult Fitness Club",
        "bank_name": "IndusInd Bank (Simulated)",
        "branch_region": "Chennai South",
        "account_age_days": 700,
        "category": "TRUSTED",
        "is_trusted_beneficiary": True,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 60,
        "fan_out_count_24h": 2,
        "typical_amount": Decimal("3500.00"),
        "typical_frequency": "QUARTERLY",
        "history_summary": {
            "transfers_count": 6,
            "avg_amount": 3500.0,
            "merchant_type": "Fitness Gym",
            "first_transfer_date": "2024-04-10",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000008",
        "upi_id": "radhika.patel@okhdfcbank",
        "display_name": "Radhika Patel",
        "bank_name": "HDFC Bank (Simulated)",
        "branch_region": "Ahmedabad West",
        "account_age_days": 510,
        "category": "TRUSTED",
        "is_trusted_beneficiary": True,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 3,
        "fan_out_count_24h": 1,
        "typical_amount": Decimal("5000.00"),
        "typical_frequency": "OCCASIONAL",
        "history_summary": {
            "transfers_count": 9,
            "avg_amount": 4800.0,
            "relationship": "Colleague",
            "first_transfer_date": "2024-06-18",
        },
    },
    # 9-13: Newly Introduced or Insufficiently Known Recipients (UNKNOWN)
    {
        "id": "20000000-0000-0000-0000-000000000009",
        "upi_id": "karan.consulting.freelance@pnb",
        "display_name": "Karan Mehta Consulting",
        "bank_name": "PNB (Simulated)",
        "branch_region": "Chandigarh Sector 17",
        "account_age_days": 45,
        "category": "UNKNOWN",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 4,
        "fan_out_count_24h": 2,
        "typical_amount": Decimal("15000.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "note": "New contractor; no established history with customer",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000010",
        "upi_id": "shree.ganesh.hardware@bob",
        "display_name": "Shree Ganesh Hardware Supplies",
        "bank_name": "Bank of Baroda (Simulated)",
        "branch_region": "Surat Ring Road",
        "account_age_days": 90,
        "category": "UNKNOWN",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 8,
        "fan_out_count_24h": 3,
        "typical_amount": Decimal("8500.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "note": "Local hardware retail; first transaction from this customer",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000011",
        "upi_id": "metro.interiors.decor@axis",
        "display_name": "Metro Home Decor",
        "bank_name": "Axis Bank (Simulated)",
        "branch_region": "Kolkata Park Street",
        "account_age_days": 35,
        "category": "UNKNOWN",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": False,
        "complaint_count": 1,
        "fan_in_count_24h": 6,
        "fan_out_count_24h": 1,
        "typical_amount": Decimal("12000.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "note": "Small business decor payee; single minor delivery dispute",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000012",
        "upi_id": "quickfix.plumbing.services@canara",
        "display_name": "QuickFix Plumbing Services",
        "bank_name": "Canara Bank (Simulated)",
        "branch_region": "Lucknow Gomti Nagar",
        "account_age_days": 20,
        "category": "UNKNOWN",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 3,
        "fan_out_count_24h": 0,
        "typical_amount": Decimal("1500.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "note": "Recently registered trade services account",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000013",
        "upi_id": "vikram.advisory.tax@federal",
        "display_name": "Vikram Tax Consulting",
        "bank_name": "Federal Bank (Simulated)",
        "branch_region": "Kochi Marine Drive",
        "account_age_days": 60,
        "category": "UNKNOWN",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": False,
        "complaint_count": 0,
        "fan_in_count_24h": 5,
        "fan_out_count_24h": 2,
        "typical_amount": Decimal("4000.00"),
        "typical_frequency": "ANNUAL",
        "history_summary": {
            "note": "Independent tax filing consultant",
        },
    },
    # 14-20: High-Risk Simulated Recipients (HIGH_RISK)
    {
        "id": "20000000-0000-0000-0000-000000000014",
        "upi_id": "cbi.cybercell.escrow@sbi-dept.sim",
        "display_name": "Central Cyber Crime Police Escrow",
        "bank_name": "SBI (Simulated)",
        "branch_region": "New Delhi Central",
        "account_age_days": 4,
        "category": "HIGH_RISK",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": True,
        "complaint_count": 14,
        "fan_in_count_24h": 42,
        "fan_out_count_24h": 38,
        "typical_amount": Decimal("85000.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "mule_cluster_id": "MULE-CBI-091",
            "risk_flags": ["FAKE_POLICE_IMPERSONATION", "RAPID_DRAIN", "HIGH_FAN_IN"],
            "warning": "Confirmed law-enforcement impersonation account",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000015",
        "upi_id": "quick.wealth.telegram@crypto-pay.sim",
        "display_name": "VIP Wealth Quantum Returns",
        "bank_name": "PNB (Simulated)",
        "branch_region": "Gurugram Cyber City",
        "account_age_days": 8,
        "category": "HIGH_RISK",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": True,
        "complaint_count": 9,
        "fan_in_count_24h": 35,
        "fan_out_count_24h": 33,
        "typical_amount": Decimal("50000.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "mule_cluster_id": "MULE-CRYPTO-102",
            "risk_flags": ["INVESTMENT_SCAM_LURE", "TELEGRAM_RECRUITED", "GUARANTEED_RETURNS"],
            "warning": "Ponzi and fraudulent crypto deposit collector",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000016",
        "upi_id": "customs.clearance.penalty@escrow-gov.sim",
        "display_name": "National Customs Cargo Escrow",
        "bank_name": "Axis Bank (Simulated)",
        "branch_region": "Mumbai Airport Cargo",
        "account_age_days": 2,
        "category": "HIGH_RISK",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": True,
        "complaint_count": 21,
        "fan_in_count_24h": 58,
        "fan_out_count_24h": 55,
        "typical_amount": Decimal("75000.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "mule_cluster_id": "MULE-CUSTOMS-404",
            "risk_flags": ["AUTHORITY_IMPERSONATION", "PACKAGE_BLACKMAIL", "EXTORTION"],
            "warning": "Simulated parcel extortion mule account",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000017",
        "upi_id": "fastcash.urgent.loan@fintech-mule.sim",
        "display_name": "FastCash Instant Approvals",
        "bank_name": "Yes Bank (Simulated)",
        "branch_region": "Jaipur MI Road",
        "account_age_days": 12,
        "category": "HIGH_RISK",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": True,
        "complaint_count": 11,
        "fan_in_count_24h": 27,
        "fan_out_count_24h": 25,
        "typical_amount": Decimal("25000.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "mule_cluster_id": "MULE-LOAN-88",
            "risk_flags": ["UPFRONT_FEE_FRAUD", "UNLICENSED_FINTECH", "MULE_DRAIN"],
            "warning": "Simulated predatory loan processing fee scam",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000018",
        "upi_id": "mule.layer.network7@micro-bank.sim",
        "display_name": "Rapid Transfer Pooling Hub",
        "bank_name": "IndusInd Bank (Simulated)",
        "branch_region": "Noida Sector 62",
        "account_age_days": 6,
        "category": "HIGH_RISK",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": True,
        "complaint_count": 16,
        "fan_in_count_24h": 64,
        "fan_out_count_24h": 60,
        "typical_amount": Decimal("95000.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "mule_cluster_id": "MULE-POOL-777",
            "risk_flags": ["CONSORTIUM_MULE_CONFIRMED", "HIGH_FAN_VELOCITY", "LAYERING_NODE"],
            "warning": "High-velocity syndicate layering account",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000019",
        "upi_id": "telecom.verification.dept@trai-hold.sim",
        "display_name": "TRAI Regulatory Verification Cell",
        "bank_name": "HDFC Bank (Simulated)",
        "branch_region": "Bhopal MP Nagar",
        "account_age_days": 3,
        "category": "HIGH_RISK",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": True,
        "complaint_count": 18,
        "fan_in_count_24h": 49,
        "fan_out_count_24h": 47,
        "typical_amount": Decimal("60000.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "mule_cluster_id": "MULE-TRAI-012",
            "risk_flags": ["DIGITAL_ARREST_COERCION", "SIM_BLOCK_THREAT", "IMPERSONATION"],
            "warning": "Simulated telecom disconnection coercion account",
        },
    },
    {
        "id": "20000000-0000-0000-0000-000000000020",
        "upi_id": "digital.arrest.bail.escrow@court-dep.sim",
        "display_name": "Supreme Court Digital Bail Clearance",
        "bank_name": "Kotak Mahindra (Simulated)",
        "branch_region": "Patna Fraser Road",
        "account_age_days": 1,
        "category": "HIGH_RISK",
        "is_trusted_beneficiary": False,
        "is_flagged_mule": True,
        "complaint_count": 25,
        "fan_in_count_24h": 73,
        "fan_out_count_24h": 71,
        "typical_amount": Decimal("120000.00"),
        "typical_frequency": "IRREGULAR",
        "history_summary": {
            "mule_cluster_id": "MULE-BAIL-001",
            "risk_flags": ["LEGAL_EXTORTION", "HIGH_VALUE_DRAIN", "DIGITAL_ARREST"],
            "warning": "Simulated judicial bail extortion mule account",
        },
    },
]
