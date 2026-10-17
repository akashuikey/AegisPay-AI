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
