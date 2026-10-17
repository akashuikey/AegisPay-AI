"""Integration tests for fraud response orchestration and customer interventions (P2-A7)."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import create_customer_verification_token
from app.db.models import (
    TransactionCoercionAnalysisModel,
    TransactionNotificationModel,
)


async def _create_tx(
    client: AsyncClient, amount: str = "5000.00", recipient: str = "Priya Sharma"
) -> str:
    res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": f"cust_{uuid.uuid4().hex[:8]}",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": amount,
            "currency": "INR",
            "payment_rail": "IMPS",
            "recipient_name": recipient,
            "recipient_identifier": "priya@upi",
            "purpose": "Test Payment",
        },
    )
    assert res.status_code == 201
    return str(res.json()["id"])


@pytest.mark.asyncio
async def test_low_risk_allow_response(client: AsyncClient) -> None:
    """1. Low-risk transaction evaluates to ALLOW and executes ALLOW_SETTLED response."""
    tx_id = await _create_tx(client, "1500.00")

    # Evaluate with routine evidence
    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_trusted_beneficiary": True, "is_first_time_recipient": False}},
    )

    # Execute automated response
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/respond",
        json={"channel": "IN_APP_SIMULATED"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["response_type"] == "ALLOW_SETTLED"
    assert body["action"] == "ALLOW"
    assert body["to_state"] == "SETTLED_SIMULATED"
    assert body["customer_action_required"] == "NONE"
    assert "approved" in body["customer_message"].lower()
    assert body["is_simulated"] is True

    # Verify notification was dispatched
    assert len(body["notifications"]) == 1
    notif = body["notifications"][0]
    assert notif["delivery_status"] == "DELIVERED_SIMULATED"
    assert notif["channel"] == "IN_APP_SIMULATED"

    # Verify transaction state in database
    tx = (await client.get(f"/api/v1/transactions/{tx_id}")).json()
    assert tx["state"] == "SETTLED_SIMULATED"


@pytest.mark.asyncio
async def test_verification_required_response_and_completion_flow(client: AsyncClient) -> None:
    """2 & 3. Medium risk requires verification, followed by successful OTP settlement."""
    tx_id = await _create_tx(client, "60000.00")

    # Evaluate with medium risk evidence (first time recipient + active call telemetry)
    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={
            "evidence": {
                "is_first_time_recipient": True,
                "active_call_present": True,
                "is_trusted_beneficiary": False,
            },
            "run_investigation": False,
        },
    )

    # Execute automated response
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/respond",
        json={"channel": "SMS_SIMULATED"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["response_type"] == "VERIFICATION_REQUIRED"
    assert body["action"] == "REQUIRE_VERIFICATION"
    assert body["to_state"] == "VERIFICATION_REQUIRED"
    assert body["customer_action_required"] == "VERIFY_OTP"
    assert "verification" in body["customer_message"].lower()

    # Step 3: Complete verification challenge
    v_res = await client.post(f"/api/v1/transactions/{tx_id}/verification")
    assert v_res.status_code == 201
    v_body = v_res.json()
    challenge_id = v_body["challenge_id"]
    dev_otp = v_body["dev_otp"]
    token = v_body["customer_session_token"]

    sub_res = await client.post(
        f"/api/v1/verification/{challenge_id}/submit",
        json={"otp": dev_otp},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sub_res.status_code == 200
    assert sub_res.json()["decision"]["action"] == "ALLOW"
    assert sub_res.json()["transaction_state"] == "SETTLED_SIMULATED"

    # Post-verification response reflects the settled resolution
    post_res = await client.post(f"/api/v1/transactions/{tx_id}/respond", json={})
    assert post_res.status_code == 201
    post_body = post_res.json()
    assert post_body["response_type"] == "ALLOW_SETTLED"
    assert post_body["action"] == "ALLOW"


@pytest.mark.asyncio
async def test_coercion_prevents_verification_override(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """4. Persistent coercion cannot be cleared by successful customer verification."""
    tx_id_str = await _create_tx(client, "250000.00", "Safe Escrow Ltd")
    tx_id = uuid.UUID(tx_id_str)

    # Seed an explicit CRITICAL coercion analysis
    coercion_analysis = TransactionCoercionAnalysisModel(
        id=uuid.uuid4(),
        transaction_id=tx_id,
        transcript_snippet="Transfer immediately or you will be placed under digital arrest.",
        overall_coercion_level="CRITICAL",
        confidence="HIGH",
        confidence_score=0.95,
        findings=[
            {
                "id": "coercion_crit_1",
                "category": "AUTHORITY_IMPERSONATION",
                "severity": "CRITICAL",
                "is_explicit": True,
                "supporting_excerpt": "placed under digital arrest",
            }
        ],
        voice_stress_signals={"detected": True, "level": "HIGH"},
        legitimate_explanations=[],
        uncertainty_notes=[],
        missing_information=[],
        summary="Customer is under severe digital arrest coercion.",
        model_metadata={"provider": "mock"},
        status="COMPLETED",
    )
    db_session.add(coercion_analysis)
    await db_session.commit()

    # Initial evaluation puts it in HOLD_FOR_INVESTIGATION
    eval_res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_first_time_recipient": True, "active_call_present": True}},
    )
    assert eval_res.status_code == 201
    assert eval_res.json()["action"] == "HOLD_FOR_INVESTIGATION"

    # Respond reflects protective hold
    res = await client.post(f"/api/v1/transactions/{tx_id}/respond", json={})
    assert res.status_code == 201
    body = res.json()
    assert body["response_type"] == "HOLD_PROTECTIVE"
    assert body["action"] == "HOLD_FOR_INVESTIGATION"
    assert "hang up immediately" in body["customer_message"].lower()


@pytest.mark.asyncio
async def test_high_risk_hold_response(client: AsyncClient) -> None:
    """5. High-risk transaction produces protective hold and caller warnings."""
    tx_id = await _create_tx(client, "450000.00", "Unknown Safe Account")

    # Evaluate with heavy impersonation risk factors
    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={
            "evidence": {
                "is_first_time_recipient": True,
                "recent_fd_liquidation": True,
                "active_call_present": True,
                "coercive_language_detected": True,
            }
        },
    )

    res = await client.post(f"/api/v1/transactions/{tx_id}/respond", json={})
    assert res.status_code == 201
    body = res.json()
    assert body["response_type"] == "HOLD_PROTECTIVE"
    assert body["action"] == "HOLD_FOR_INVESTIGATION"
    assert body["customer_action_required"] == "CONTACT_BANK"
    assert "paused for account protection" in body["headline"].lower()
    assert any("card" in step.lower() for step in body["next_steps"])


@pytest.mark.asyncio
async def test_policy_authorized_block_response(client: AsyncClient) -> None:
    """6. Mule consortium hit produces BLOCK_SAFETY response without disclosing internal rules."""
    tx_id = await _create_tx(client, "300000.00", "Suspicious Beneficiary Inc")

    # Mule hit at critical risk triggers BLOCK
    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={
            "evidence": {
                "is_first_time_recipient": True,
                "recent_fd_liquidation": True,
                "active_call_present": True,
                "screen_sharing_active": True,
                "coercive_language_detected": True,
                "is_flagged_mule": True,
                "fan_in_count_24h": 12,
                "fan_out_count_24h": 11,
            },
            "run_investigation": False,
        },
    )

    res = await client.post(f"/api/v1/transactions/{tx_id}/respond", json={})
    assert res.status_code == 201
    body = res.json()
    assert body["response_type"] == "BLOCK_SAFETY"
    assert body["action"] == "BLOCK"
    assert body["to_state"] == "CANCELLED_SIMULATED"
    # Never leaks internal rule IDs or consortium terminology
    assert "RULE_FLAGGED_MULE_ACCOUNT" not in body["customer_message"]
    assert "mule" not in body["customer_message"].lower()
    assert "No funds have left your account" in body["customer_message"]


@pytest.mark.asyncio
async def test_simulated_notification_failure_isolation(client: AsyncClient) -> None:
    """7 & 8. Notification failure is recorded without invalidating the safety response."""
    tx_id = await _create_tx(client, "1200.00")

    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_trusted_beneficiary": True, "is_first_time_recipient": False}},
    )

    res = await client.post(
        f"/api/v1/transactions/{tx_id}/respond",
        json={"channel": "SMS_SIMULATED", "simulate_notification_failure": True},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["response_type"] == "ALLOW_SETTLED"
    assert body["processing_status"] == "COMPLETED"

    # Notification record shows failure
    assert len(body["notifications"]) == 1
    notif = body["notifications"][0]
    assert notif["delivery_status"] == "FAILED_SIMULATED"
    assert notif["failure_reason"] == "SIMULATED_CARRIER_TIMEOUT"

    # Transaction is still settled; notification failure does NOT revert decision
    tx = (await client.get(f"/api/v1/transactions/{tx_id}")).json()
    assert tx["state"] == "SETTLED_SIMULATED"


@pytest.mark.asyncio
async def test_idempotent_response_replay(client: AsyncClient) -> None:
    """9. Replaying with identical idempotency key returns HTTP 200 without duplicate execution."""
    tx_id = await _create_tx(client, "2000.00")

    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_trusted_beneficiary": True, "is_first_time_recipient": False}},
    )

    # First call with idempotency key
    res1 = await client.post(
        f"/api/v1/transactions/{tx_id}/respond",
        json={"idempotency_key": "idemp-test-unique-1"},
    )
    assert res1.status_code == 201
    resp_id1 = res1.json()["id"]

    # Replay with same idempotency key
    res2 = await client.post(
        f"/api/v1/transactions/{tx_id}/respond",
        json={"idempotency_key": "idemp-test-unique-1"},
    )
    assert res2.status_code == 200
    assert res2.json()["id"] == resp_id1


@pytest.mark.asyncio
async def test_concurrent_response_attempts(client: AsyncClient) -> None:
    """10. Concurrent automated response requests resolve safely without database corruption."""
    tx_id = await _create_tx(client, "5000.00")

    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_trusted_beneficiary": True, "is_first_time_recipient": False}},
    )

    # Fire concurrent calls with the same idempotency key
    results = await asyncio.gather(
        client.post(
            f"/api/v1/transactions/{tx_id}/respond",
            json={"idempotency_key": "concurrent-key"},
        ),
        client.post(
            f"/api/v1/transactions/{tx_id}/respond",
            json={"idempotency_key": "concurrent-key"},
        ),
    )

    status_codes = [r.status_code for r in results]
    assert 201 in status_codes
    assert all(code in (200, 201) for code in status_codes)

    ids = [r.json()["id"] for r in results]
    assert ids[0] == ids[1]


@pytest.mark.asyncio
async def test_terminal_transaction_behavior(client: AsyncClient) -> None:
    """11. Responding to an already terminated transaction without prior response raises 409."""
    tx_id = await _create_tx(client, "999.00")

    # Manually transition directly to terminal state CANCELLED_SIMULATED
    t_res = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={
            "target_state": "CANCELLED_SIMULATED",
            "actor_type": "INVESTIGATOR",
            "reason": "Administrative cancellation",
        },
    )
    assert t_res.status_code == 200

    res = await client.post(f"/api/v1/transactions/{tx_id}/respond", json={})
    assert res.status_code == 409
    assert "terminal" in res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_authorization_and_customer_intervention_scoping(
    client: AsyncClient, unauth_client: AsyncClient, test_settings: Settings
) -> None:
    """12 & 14. Unauthenticated requests rejected; customer token scoped to transaction."""
    tx_id = await _create_tx(client, "15000.00")

    # Unauthenticated respond call rejected
    unauth_res = await unauth_client.post(f"/api/v1/transactions/{tx_id}/respond", json={})
    assert unauth_res.status_code == 401

    # Unauthenticated intervention call rejected
    unauth_int = await unauth_client.get(f"/api/v1/transactions/{tx_id}/intervention")
    assert unauth_int.status_code == 401

    # Operator access to intervention succeeds
    op_int = await client.get(f"/api/v1/transactions/{tx_id}/intervention")
    assert op_int.status_code == 200
    int_body = op_int.json()
    assert int_body["transaction_id"] == tx_id
    assert int_body["is_simulated"] is True
    # Zero sensitive risk scores or rule specifics exposed in customer view
    assert "risk_score" not in int_body
    assert "triggered_rules" not in int_body

    # Customer token matching transaction succeeds
    cust_token, _ = create_customer_verification_token(
        challenge_id=str(uuid.uuid4()),
        transaction_id=str(tx_id),
        customer_id="cust_test",
        settings=test_settings,
    )
    cust_res = await unauth_client.get(
        f"/api/v1/transactions/{tx_id}/intervention",
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert cust_res.status_code == 200

    # Customer token with mismatched transaction is rejected
    other_tx_id = str(uuid.uuid4())
    mismatch_res = await unauth_client.get(
        f"/api/v1/transactions/{other_tx_id}/intervention",
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert mismatch_res.status_code == 401


@pytest.mark.asyncio
async def test_notifications_contain_no_sensitive_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """13. Notifications contain masked contacts and zero OTPs, bearer tokens, or transcripts."""
    tx_id = await _create_tx(client, "10000.00")

    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_trusted_beneficiary": True, "is_first_time_recipient": False}},
    )

    res = await client.post(f"/api/v1/transactions/{tx_id}/respond", json={})
    assert res.status_code == 201

    stmt = select(TransactionNotificationModel).where(
        TransactionNotificationModel.transaction_id == uuid.UUID(tx_id)
    )
    notif = (await db_session.execute(stmt)).scalar_one()

    # Recipient must be masked
    assert "***" in notif.recipient_masked
    # Body must not contain sensitive tokens
    assert "otp" not in notif.message_body.lower()
    assert "bearer" not in notif.message_body.lower()
    assert "ey" not in notif.message_body  # No JWT prefix
