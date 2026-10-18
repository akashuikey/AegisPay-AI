"""Unit tests for fictional recipient registry domain model, seed catalog (P2-A12)."""

from uuid import UUID

from app.domain.recipient_registry import (
    FICTIONAL_RECIPIENTS_SEED_DATA,
    RecipientCategory,
)


def test_seed_catalog_exact_count_and_distribution() -> None:
    """Verify registry seed data contains exactly 20 records distributed across 3 tiers."""
    assert len(FICTIONAL_RECIPIENTS_SEED_DATA) == 20

    trusted = [
        r
        for r in FICTIONAL_RECIPIENTS_SEED_DATA
        if r["category"] == RecipientCategory.TRUSTED.value
    ]
    unknown = [
        r
        for r in FICTIONAL_RECIPIENTS_SEED_DATA
        if r["category"] == RecipientCategory.UNKNOWN.value
    ]
    high_risk = [
        r
        for r in FICTIONAL_RECIPIENTS_SEED_DATA
        if r["category"] == RecipientCategory.HIGH_RISK.value
    ]

    assert len(trusted) == 8, f"Expected 8 trusted recipients, got {len(trusted)}"
    assert len(unknown) == 5, f"Expected 5 unknown recipients, got {len(unknown)}"
    assert len(high_risk) == 7, f"Expected 7 high-risk recipients, got {len(high_risk)}"


def test_seed_catalog_upi_ids_unique() -> None:
    """Verify all 20 recipient UPI IDs are unique."""
    upi_ids = [r["upi_id"].lower().strip() for r in FICTIONAL_RECIPIENTS_SEED_DATA]
    assert len(upi_ids) == len(set(upi_ids))


def test_seed_catalog_all_required_fields_populated() -> None:
    """Verify all recipients have complete, typed metadata and valid categories."""
    for r in FICTIONAL_RECIPIENTS_SEED_DATA:
        assert UUID(r["id"]), "ID must be a valid UUID string"
        assert r["display_name"], "Display name must be present"
        assert "@" in r["upi_id"], f"Invalid UPI format: {r['upi_id']}"
        assert r["bank_name"], "Bank name must be present"
        assert r["branch_region"], "Branch region must be present"
        assert r["account_age_days"] >= 0, "Account age must be non-negative"
        assert r["fan_in_count_24h"] >= 0, "Fan-in count must be non-negative"
        assert r["fan_out_count_24h"] >= 0, "Fan-out count must be non-negative"
        assert r["category"] in [c.value for c in RecipientCategory]

        if r["category"] == RecipientCategory.TRUSTED.value:
            assert r["is_trusted_beneficiary"] is True
            assert r["is_flagged_mule"] is False
            assert r["complaint_count"] == 0
        elif r["category"] == RecipientCategory.HIGH_RISK.value:
            assert r["is_flagged_mule"] is True
            assert r["is_trusted_beneficiary"] is False
            assert r["complaint_count"] > 0
        elif r["category"] == RecipientCategory.UNKNOWN.value:
            assert r["is_trusted_beneficiary"] is False
            assert r["is_flagged_mule"] is False


def test_known_high_risk_recipients_include_scam_scenarios() -> None:
    """Verify key scam scenario recipients exist in seed catalog."""
    cbi = next(
        (r for r in FICTIONAL_RECIPIENTS_SEED_DATA if "cbi" in r["upi_id"]),
        None,
    )
    assert cbi is not None
    assert cbi["is_flagged_mule"] is True
    assert cbi["fan_in_count_24h"] >= 10
    assert "Cyber Crime" in cbi["display_name"] or "Escrow" in cbi["display_name"]

    crypto = next(
        (
            r
            for r in FICTIONAL_RECIPIENTS_SEED_DATA
            if "telegram" in r["upi_id"] or "crypto" in r["upi_id"]
        ),
        None,
    )
    assert crypto is not None
    assert crypto["is_flagged_mule"] is True
