"""Integration tests for the automated decision workflow API (P2-A4)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.investigations import get_default_ai_client
from app.db.models import TransactionAuditModel, TransactionDecisionModel
from app.services.ai_client import MockGeminiClient


async def _create_tx(client: AsyncClient, amount: str, recipient: str = "Payee") -> str:
    res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_wf",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": amount,
            "currency": "INR",
            "payment_rail": "IMPS",
            "recipient_name": recipient,
            "recipient_identifier": "payee@upi",
            "purpose": "Test",
        },
    )
    assert res.status_code == 201
    return res.json()["id"]


@pytest.mark.asyncio
async def test_low_risk_reaches_simulated_settlement(client: AsyncClient) -> None:
    tx_id = await _create_tx(client, "20000.00")
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_trusted_beneficiary": True, "is_first_time_recipient": False}},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["action"] == "ALLOW"
    assert body["to_state"] == "SETTLED_SIMULATED"
    assert body["transaction_state"] == "SETTLED_SIMULATED"
    assert body["simulated"] is True
    # Low risk skips the LLM investigation.
    assert body["investigation_performed"] is False

    tx = (await client.get(f"/api/v1/transactions/{tx_id}")).json()
    assert tx["state"] == "SETTLED_SIMULATED"


@pytest.mark.asyncio
async def test_high_risk_cannot_reach_settlement(client: AsyncClient) -> None:
    tx_id = await _create_tx(client, "250000.00", "Govt Clearance Account")
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={
            "evidence": {
                "is_first_time_recipient": True,
                "recent_fd_liquidation": True,
                "active_call_present": True,
                "screen_sharing_active": True,
                "coercive_language_detected": True,
            }
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["action"] == "HOLD_FOR_INVESTIGATION"
    assert body["to_state"] == "HELD_FOR_VERIFICATION"
    assert body["risk_level"] == "CRITICAL"
    # Never settled.
    tx = (await client.get(f"/api/v1/transactions/{tx_id}")).json()
    assert tx["state"] == "HELD_FOR_VERIFICATION"
    assert tx["state"] != "SETTLED_SIMULATED"

    # Automated outbound verification call session was initiated for the hold
    call_res = await client.get(f"/api/v1/transactions/{tx_id}/calls/latest")
    assert call_res.status_code == 200
    call_body = call_res.json()
    assert call_body["status"] in ("RINGING", "INITIATED")


@pytest.mark.asyncio
async def test_ambiguous_requires_verification(client: AsyncClient) -> None:
    tx_id = await _create_tx(client, "60000.00")
    # Deterministic MEDIUM tier (elevated amount + new recipient + active call), investigation
    # disabled to isolate the verification mapping (the run_investigation override is exercised).
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={
            "evidence": {"is_first_time_recipient": True, "active_call_present": True},
            "run_investigation": False,
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["action"] == "REQUIRE_VERIFICATION"
    assert body["to_state"] == "VERIFICATION_REQUIRED"
    assert body["requires_verification"] is True
    assert body["investigation_performed"] is False


@pytest.mark.asyncio
async def test_verified_mule_is_blocked_and_cancelled(client: AsyncClient) -> None:
    tx_id = await _create_tx(client, "250000.00", "Mule Beneficiary")
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={
            "evidence": {
                "is_first_time_recipient": True,
                "is_flagged_mule": True,
                "fan_in_count_24h": 12,
                "fan_out_count_24h": 11,
            }
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["action"] == "BLOCK"
    assert body["to_state"] == "CANCELLED_SIMULATED"
    assert "CONFIRMED_MULE_BENEFICIARY_BLOCK" in body["reason_codes"]


@pytest.mark.asyncio
async def test_workflow_is_idempotent(client: AsyncClient, db_session: AsyncSession) -> None:
    tx_id = await _create_tx(client, "20000.00")
    payload = {"evidence": {"is_trusted_beneficiary": True, "is_first_time_recipient": False}}

    first = await client.post(f"/api/v1/transactions/{tx_id}/evaluate", json=payload)
    assert first.status_code == 201
    first_id = first.json()["id"]

    audit_stmt = select(func.count(TransactionAuditModel.id)).where(
        TransactionAuditModel.transaction_id == uuid.UUID(tx_id)
    )
    audit_after_first = (await db_session.execute(audit_stmt)).scalar_one()

    # Repeat: returns the SAME decision, does not duplicate transitions/audits/decisions.
    second = await client.post(f"/api/v1/transactions/{tx_id}/evaluate", json=payload)
    assert second.status_code == 200  # idempotent replay
    assert second.json()["id"] == first_id

    audit_after_second = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit_after_second == audit_after_first

    dec_count = (
        await db_session.execute(
            select(func.count(TransactionDecisionModel.id)).where(
                TransactionDecisionModel.transaction_id == uuid.UUID(tx_id)
            )
        )
    ).scalar_one()
    assert dec_count == 1


@pytest.mark.asyncio
async def test_held_transaction_cannot_settle_via_retry(client: AsyncClient) -> None:
    tx_id = await _create_tx(client, "250000.00")
    payload = {
        "evidence": {
            "is_first_time_recipient": True,
            "recent_fd_liquidation": True,
            "active_call_present": True,
            "screen_sharing_active": True,
            "coercive_language_detected": True,
        }
    }
    first = await client.post(f"/api/v1/transactions/{tx_id}/evaluate", json=payload)
    assert first.json()["to_state"] == "HELD_FOR_VERIFICATION"

    # A retry (even with benign evidence) must not settle the held transaction.
    retry = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_trusted_beneficiary": True}},
    )
    assert retry.status_code == 200
    assert retry.json()["to_state"] == "HELD_FOR_VERIFICATION"
    tx = (await client.get(f"/api/v1/transactions/{tx_id}")).json()
    assert tx["state"] == "HELD_FOR_VERIFICATION"


@pytest.mark.asyncio
async def test_provider_failure_does_not_bypass_risk_rules(client: AsyncClient) -> None:
    tx_id = await _create_tx(client, "250000.00")
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_default_ai_client] = lambda: MockGeminiClient(should_fail=True)
    try:
        res = await client.post(
            f"/api/v1/transactions/{tx_id}/evaluate",
            json={
                "evidence": {
                    "is_first_time_recipient": True,
                    "recent_fd_liquidation": True,
                    "active_call_present": True,
                    "screen_sharing_active": True,
                    "coercive_language_detected": True,
                }
            },
        )
        assert res.status_code == 201
        body = res.json()
        # AI failed, but the high-risk transaction is still held, not allowed.
        assert body["action"] == "HOLD_FOR_INVESTIGATION"
        assert body["provider_failed"] is True
        assert "AI_UNAVAILABLE_DETERMINISTIC_FALLBACK" in body["reason_codes"]
    finally:
        app.dependency_overrides[get_default_ai_client] = lambda: MockGeminiClient()


@pytest.mark.asyncio
async def test_decision_and_transition_are_traceable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tx_id = await _create_tx(client, "250000.00")
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={
            "evidence": {
                "is_first_time_recipient": True,
                "recent_fd_liquidation": True,
                "active_call_present": True,
                "screen_sharing_active": True,
                "coercive_language_detected": True,
            }
        },
    )
    body = res.json()
    assert body["from_state"] == "DECISION_READY"
    assert body["to_state"] == body["transaction_state"]

    # The final transition is attributed to the policy engine and matches the decision.
    audits = (await client.get(f"/api/v1/transactions/{tx_id}/audit")).json()["items"]
    last = audits[-1]
    assert last["to_state"] == body["to_state"]
    assert last["actor_type"] == "POLICY_ENGINE"

    # The decision record references the assessment it considered.
    dec = (
        await db_session.execute(
            select(TransactionDecisionModel).where(
                TransactionDecisionModel.transaction_id == uuid.UUID(tx_id)
            )
        )
    ).scalar_one()
    assert dec.assessment_id is not None
    assert dec.to_state == body["to_state"]


@pytest.mark.asyncio
async def test_get_decision_endpoint(client: AsyncClient) -> None:
    tx_id = await _create_tx(client, "20000.00")
    # No decision yet -> 404
    missing = await client.get(f"/api/v1/transactions/{tx_id}/decision")
    assert missing.status_code == 404

    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_trusted_beneficiary": True}},
    )
    got = await client.get(f"/api/v1/transactions/{tx_id}/decision")
    assert got.status_code == 200
    assert got.json()["action"] == "ALLOW"


@pytest.mark.asyncio
async def test_evaluate_requires_authentication(unauth_client: AsyncClient) -> None:
    res = await unauth_client.post(f"/api/v1/transactions/{uuid.uuid4()}/evaluate", json={})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_decision_endpoint_requires_authentication(unauth_client: AsyncClient) -> None:
    res = await unauth_client.get(f"/api/v1/transactions/{uuid.uuid4()}/decision")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_evaluate_nonexistent_transaction_returns_404(client: AsyncClient) -> None:
    res = await client.post(f"/api/v1/transactions/{uuid.uuid4()}/evaluate", json={})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_evaluate_rejects_unknown_fields(client: AsyncClient) -> None:
    tx_id = await _create_tx(client, "20000.00")
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"not_a_real_field": True}},
    )
    assert res.status_code == 422
