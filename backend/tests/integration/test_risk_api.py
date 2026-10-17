"""Integration tests for deterministic risk evaluation and transaction assessment API."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TransactionAssessmentModel, TransactionAuditModel
from app.domain.scenario_fixtures import SCENARIO_FIXTURES


@pytest.mark.asyncio
async def test_pure_risk_evaluation_endpoint(client: AsyncClient) -> None:
    """Verify stateless risk evaluation endpoint evaluates features without persisting records."""
    fixture = SCENARIO_FIXTURES["digital_arrest"]["evidence"]
    payload = {
        "amount": str(fixture.amount),
        "currency": fixture.currency,
        "payment_rail": fixture.payment_rail,
        "recipient_name": fixture.recipient_name,
        "recipient_identifier": fixture.recipient_identifier,
        "purpose": fixture.purpose,
        "customer_id": fixture.customer_id,
        "is_first_time_recipient": fixture.is_first_time_recipient,
        "is_trusted_beneficiary": fixture.is_trusted_beneficiary,
        "recent_fd_liquidation": fixture.recent_fd_liquidation,
        "recent_fd_liquidation_amount": (
            str(fixture.recent_fd_liquidation_amount)
            if fixture.recent_fd_liquidation_amount
            else None
        ),
        "active_call_present": fixture.active_call_present,
        "screen_sharing_active": fixture.screen_sharing_active,
        "coercive_language_detected": fixture.coercive_language_detected,
        "guaranteed_return_claimed": fixture.guaranteed_return_claimed,
        "is_flagged_mule": fixture.is_flagged_mule,
    }

    response = await client.post("/api/v1/risk/evaluate", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["risk_score"] >= 80
    assert data["risk_level"] == "CRITICAL"
    assert data["recommended_action"] == "HOLD_FOR_INVESTIGATION"
    assert len(data["triggered_rules"]) >= 4
    rule_ids = [r["rule_id"] for r in data["triggered_rules"]]
    assert "RULE_COERCION_AUTHORITY_PRESSURE" in rule_ids
    assert "RULE_CALL_AND_SCREEN_SHARE" in rule_ids


@pytest.mark.asyncio
async def test_get_scenario_fixtures_endpoint(client: AsyncClient) -> None:
    """Verify scenarios discovery endpoint returns all 6 benchmark scenarios."""
    response = await client.get("/api/v1/risk/scenarios")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 6

    scenario_ids = [s["id"] for s in data]
    expected_ids = [
        "digital_arrest",
        "investment_scam",
        "fake_invoice",
        "mule_network",
        "legitimate_high_value",
        "ambiguous_payment",
    ]
    for expected_id in expected_ids:
        assert expected_id in scenario_ids


@pytest.mark.asyncio
async def test_assess_transaction_lifecycle_and_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify assessing transaction triggers state transitions, saves assessment, and audits."""
    # 1. Create a transaction
    tx_payload = {
        "customer_id": "cust_test_assess",
        "idempotency_key": "idemp_assess_001",
        "amount": "250000.00",
        "currency": "INR",
        "payment_rail": "RTGS",
        "recipient_name": "Unknown Payee",
        "recipient_identifier": "unknown@upi",
        "purpose": "Emergency legal clearance",
    }
    tx_resp = await client.post("/api/v1/transactions", json=tx_payload)
    assert tx_resp.status_code == 201
    tx_data = tx_resp.json()
    tx_id_str = tx_data["id"]
    tx_id = uuid.UUID(tx_id_str)

    # 2. Assess the transaction with digital arrest evidence
    assess_payload = {
        "evidence": {
            "amount": "250000.00",
            "recipient_name": "Unknown Payee",
            "recipient_identifier": "unknown@upi",
            "is_first_time_recipient": True,
            "recent_fd_liquidation": True,
            "recent_fd_liquidation_amount": "250000.00",
            "active_call_present": True,
            "screen_sharing_active": True,
            "coercive_language_detected": True,
        }
    }
    assess_resp = await client.post(f"/api/v1/transactions/{tx_id_str}/assess", json=assess_payload)
    assert assess_resp.status_code == 200
    assess_data = assess_resp.json()

    assert assess_data["transaction_id"] == tx_id_str
    assert assess_data["risk_score"] >= 80
    assert assess_data["risk_level"] == "CRITICAL"
    assert assess_data["recommended_action"] == "HOLD_FOR_INVESTIGATION"

    # 3. Check transaction state transitioned to DECISION_READY
    get_tx_resp = await client.get(f"/api/v1/transactions/{tx_id_str}")
    assert get_tx_resp.status_code == 200
    updated_tx = get_tx_resp.json()
    assert updated_tx["state"] == "DECISION_READY"

    # 4. Check assessment persistence in DB
    assessment_stmt = select(TransactionAssessmentModel).where(
        TransactionAssessmentModel.transaction_id == tx_id
    )
    assessments = (await db_session.execute(assessment_stmt)).scalars().all()
    assert len(assessments) == 1
    assert assessments[0].risk_score >= 80
    assert assessments[0].risk_level == "CRITICAL"
    assert assessments[0].recommended_action == "HOLD_FOR_INVESTIGATION"

    # 5. Check audit trail transitions: INITIATED -> ASSESSING -> RISK_ASSESSED -> DECISION_READY
    audit_stmt = (
        select(TransactionAuditModel)
        .where(TransactionAuditModel.transaction_id == tx_id)
        .order_by(TransactionAuditModel.created_at)
    )
    audits = (await db_session.execute(audit_stmt)).scalars().all()
    # 1 creation audit + 3 state transition audits = 4 total
    assert len(audits) == 4
    assert audits[0].to_state == "INITIATED"
    assert audits[1].from_state == "INITIATED"
    assert audits[1].to_state == "ASSESSING"
    assert audits[2].from_state == "ASSESSING"
    assert audits[2].to_state == "RISK_ASSESSED"
    assert audits[3].from_state == "RISK_ASSESSED"
    assert audits[3].to_state == "DECISION_READY"


@pytest.mark.asyncio
async def test_get_transaction_assessment(client: AsyncClient) -> None:
    """Verify retrieving assessment for assessed, unassessed, and nonexistent transactions."""
    # Create and assess transaction
    tx_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_fetch_assess",
            "idempotency_key": "idemp_fetch_001",
            "amount": "85000.00",
            "currency": "INR",
            "payment_rail": "UPI",
            "recipient_name": "Northstar Holdings",
            "recipient_identifier": "northstar@axis",
        },
    )
    tx_id = tx_resp.json()["id"]

    # Before assessment: returns 404 NOT_FOUND
    unassessed_resp = await client.get(f"/api/v1/transactions/{tx_id}/assessment")
    assert unassessed_resp.status_code == 404
    assert unassessed_resp.json()["error"]["code"] == "NOT_FOUND"

    # Assess it
    await client.post(
        f"/api/v1/transactions/{tx_id}/assess",
        json={
            "evidence": {
                "amount": "85000.00",
                "recipient_name": "Northstar Holdings",
                "recipient_identifier": "northstar@axis",
                "is_first_time_recipient": True,
                "active_call_present": True,
            }
        },
    )

    # After assessment: returns 200
    assessed_resp = await client.get(f"/api/v1/transactions/{tx_id}/assessment")
    assert assessed_resp.status_code == 200
    data = assessed_resp.json()
    assert data["transaction_id"] == tx_id
    assert data["risk_level"] == "MEDIUM"
    assert data["recommended_action"] == "REQUIRE_VERIFICATION"

    # Nonexistent transaction: returns 404 NOT_FOUND
    nonexistent_id = str(uuid.uuid4())
    not_found_resp = await client.get(f"/api/v1/transactions/{nonexistent_id}/assessment")
    assert not_found_resp.status_code == 404
    assert not_found_resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_assess_terminal_transaction_rejected(client: AsyncClient) -> None:
    """Verify assessing transaction in terminal state returns HTTP 400 INVALID_STATE_TRANSITION."""
    # Create transaction
    tx_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_term_assess",
            "idempotency_key": "idemp_term_001",
            "amount": "1000.00",
            "currency": "INR",
            "payment_rail": "UPI",
            "recipient_name": "Cancelled Payee",
            "recipient_identifier": "cancel@upi",
        },
    )
    tx_id = tx_resp.json()["id"]

    # Transition to CANCELLED_SIMULATED
    cancel_resp = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={
            "target_state": "CANCELLED_SIMULATED",
            "reason": "Cancelled by user before assessment",
            "actor_type": "CUSTOMER",
        },
    )
    assert cancel_resp.status_code == 200

    # Try to assess the cancelled transaction
    assess_resp = await client.post(
        f"/api/v1/transactions/{tx_id}/assess",
        json={
            "evidence": {
                "amount": "1000.00",
                "recipient_name": "Cancelled Payee",
                "recipient_identifier": "cancel@upi",
            }
        },
    )
    assert assess_resp.status_code == 400
    assert assess_resp.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_repeated_assessment_rejected_on_already_assessed_transaction(
    client: AsyncClient,
) -> None:
    """Verify repeated assessment attempt on DECISION_READY transaction is rejected with 400."""
    tx_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_repeat_assess",
            "idempotency_key": "idemp_repeat_001",
            "amount": "30000.00",
            "currency": "INR",
            "payment_rail": "UPI",
            "recipient_name": "Test Payee",
            "recipient_identifier": "test@upi",
        },
    )
    assert tx_resp.status_code == 201
    tx_id = tx_resp.json()["id"]

    # First assessment: transitions INITIATED -> ASSESSING -> RISK_ASSESSED -> DECISION_READY
    first_assess = await client.post(
        f"/api/v1/transactions/{tx_id}/assess",
        json={
            "evidence": {
                "amount": "30000.00",
                "recipient_name": "Test Payee",
                "recipient_identifier": "test@upi",
                "is_first_time_recipient": True,
            }
        },
    )
    assert first_assess.status_code == 200
    assert first_assess.json()["source"] == "backend"

    # Second assessment: attempt to re-assess DECISION_READY transaction fails
    second_assess = await client.post(
        f"/api/v1/transactions/{tx_id}/assess",
        json={
            "evidence": {
                "amount": "30000.00",
                "recipient_name": "Test Payee",
                "recipient_identifier": "test@upi",
            }
        },
    )
    assert second_assess.status_code == 400
    assert second_assess.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    # But GET /assessment remains idempotent and retrieves the valid persisted result
    get_assess = await client.get(f"/api/v1/transactions/{tx_id}/assessment")
    assert get_assess.status_code == 200
    assert get_assess.json()["id"] == first_assess.json()["id"]
    assert get_assess.json()["source"] == "backend"


@pytest.mark.asyncio
async def test_complete_valid_workflow_lifecycle_and_audits(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify complete journey from INITIATED to CANCELLED_SIMULATED with atomic audits."""
    # 1. Create transaction
    tx_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_lifecycle_001",
            "idempotency_key": "idemp_life_001",
            "amount": "75000.00",
            "payment_rail": "IMPS",
            "recipient_name": "Suspect Payee",
            "recipient_identifier": "suspect@upi",
        },
    )
    tx_id_str = tx_resp.json()["id"]

    # 2. Assess -> DECISION_READY
    assess_resp = await client.post(
        f"/api/v1/transactions/{tx_id_str}/assess",
        json={
            "evidence": {
                "amount": "75000.00",
                "recipient_name": "Suspect Payee",
                "recipient_identifier": "suspect@upi",
                "is_first_time_recipient": True,
                "guaranteed_return_claimed": True,
                "instruction_to_ignore_bank_warnings": True,
            }
        },
    )
    assert assess_resp.status_code == 200

    # 3. Decision -> HELD_FOR_VERIFICATION
    hold_resp = await client.post(
        f"/api/v1/transactions/{tx_id_str}/transitions",
        json={
            "target_state": "HELD_FOR_VERIFICATION",
            "reason": "Simulated hold enforced based on risk recommendation",
            "actor_type": "SYSTEM",
        },
    )
    assert hold_resp.status_code == 200
    assert hold_resp.json()["state"] == "HELD_FOR_VERIFICATION"

    # 4. HELD_FOR_VERIFICATION -> CANCELLED_SIMULATED
    cancel_resp = await client.post(
        f"/api/v1/transactions/{tx_id_str}/transitions",
        json={
            "target_state": "CANCELLED_SIMULATED",
            "reason": "Customer cancelled transfer after high-yield scam warning",
            "actor_type": "CUSTOMER",
        },
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["state"] == "CANCELLED_SIMULATED"

    # 5. Attempting to transition from terminal state fails
    terminal_resp = await client.post(
        f"/api/v1/transactions/{tx_id_str}/transitions",
        json={
            "target_state": "SETTLED_SIMULATED",
            "reason": "Illegal transition from terminal",
            "actor_type": "INVESTIGATOR",
        },
    )
    assert terminal_resp.status_code == 400
    assert terminal_resp.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    # 6. Verify audit history contains complete transition chain
    audits_resp = await client.get(f"/api/v1/transactions/{tx_id_str}/audit")
    assert audits_resp.status_code == 200
    audits = audits_resp.json()["items"]
    # Creation (INITIATED) + 3 assess transitions (ASSESSING, RISK_ASSESSED,
    # DECISION_READY) + HELD + CANCELLED = 6 total
    assert len(audits) == 6
    expected_to_states = [
        "INITIATED",
        "ASSESSING",
        "RISK_ASSESSED",
        "DECISION_READY",
        "HELD_FOR_VERIFICATION",
        "CANCELLED_SIMULATED",
    ]
    for i, expected_state in enumerate(expected_to_states):
        assert audits[i]["to_state"] == expected_state


@pytest.mark.asyncio
async def test_simulated_action_guardrails_reject_real_banking_actions(
    client: AsyncClient,
) -> None:
    """Verify API schema strictly enforces _SIMULATED suffix and rejects real state names."""
    tx_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_sim_guard",
            "idempotency_key": "idemp_sim_001",
            "amount": "5000.00",
            "payment_rail": "UPI",
            "recipient_name": "Test Payee",
            "recipient_identifier": "test@upi",
        },
    )
    tx_id = tx_resp.json()["id"]

    # Attempt to transition to un-simulated "SETTLED"
    bad_settle = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={"target_state": "SETTLED", "actor_type": "SYSTEM"},
    )
    assert bad_settle.status_code == 422  # Pydantic enum validation failure

    # Attempt to transition to un-simulated "CANCELLED"
    bad_cancel = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={"target_state": "CANCELLED", "actor_type": "CUSTOMER"},
    )
    assert bad_cancel.status_code == 422
