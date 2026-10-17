"""Unit tests for the scenario catalogue (P2-A8)."""

from app.domain.scenario_catalog import (
    CATALOG_VERSION,
    SCENARIO_CATALOG,
    VerificationBehavior,
    get_scenario,
    list_scenarios,
)


def test_catalog_has_the_required_scenarios() -> None:
    ids = {s.id for s in SCENARIO_CATALOG}
    required = {
        "digital_arrest",
        "investment_scam",
        "fake_invoice",
        "mule_network",
        "legitimate_high_value",
        "ambiguous_payment",
        "ordinary_stressed_customer",
        "strong_coercion_verified",
    }
    assert required.issubset(ids)


def test_catalog_ids_are_unique_and_stable() -> None:
    ids = [s.id for s in SCENARIO_CATALOG]
    assert len(ids) == len(set(ids)), "scenario ids must be unique"
    # Spot-check a couple of stable ids resolve.
    assert get_scenario("digital_arrest") is not None
    assert get_scenario("mule_network") is not None
    assert get_scenario("does_not_exist") is None


def test_every_scenario_is_versioned() -> None:
    assert CATALOG_VERSION
    for s in SCENARIO_CATALOG:
        assert s.version, f"{s.id} must declare a version"
        assert s.title and s.description
        assert s.transaction.amount > 0
        assert s.expectation.policy_action is not None
        assert s.expectation.final_state is not None


def test_list_scenarios_returns_full_catalog() -> None:
    assert list_scenarios() == SCENARIO_CATALOG


def test_only_verification_scenarios_declare_submission_behavior() -> None:
    strong = get_scenario("strong_coercion_verified")
    assert strong is not None
    assert strong.verification_behavior == VerificationBehavior.SUBMIT_CORRECT_OTP
    assert strong.coercion_before_decision is False

    legit = get_scenario("legitimate_high_value")
    assert legit is not None
    assert legit.verification_behavior == VerificationBehavior.NONE
