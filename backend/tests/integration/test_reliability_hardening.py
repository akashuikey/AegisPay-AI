"""Reliability, security & failure-injection regression tests (P2-A9).

These exercise real endpoints and verify persisted state after failures, not just
HTTP codes. They complement the per-milestone suites with focused coverage of the
P2-A9 invariants (auth boundaries, throttling, stale decisions, idempotency,
explicit live-provider failure, and scenario partial-failure integrity).
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_operator
from app.api.fraud_responses import get_current_operator_optional
from app.api.investigations import get_default_ai_client
from app.core.security import create_access_token, create_customer_verification_token
from app.db.models import (
    OperatorModel,
    TransactionNotificationModel,
    TransactionResponseModel,
)
from app.services.ai_client import MockGeminiClient, VertexGeminiClient
from tests.conftest import _build_test_app, get_test_settings


def _authed_app(ai_client: object | None = None):
    app = _build_test_app()
    stub = OperatorModel(id=uuid.uuid4(), username="op", password_hash="x", is_active=True)
    app.dependency_overrides[get_current_operator] = lambda: stub
    app.dependency_overrides[get_current_operator_optional] = lambda: stub
    if ai_client is not None:
        app.dependency_overrides[get_default_ai_client] = lambda: ai_client
    return app


async def _create_tx(client: AsyncClient, amount: str = "60000.00") -> str:
    res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": f"cust_{uuid.uuid4().hex[:8]}",
            "idempotency_key": f"idem_{uuid.uuid4().hex[:12]}",
            "amount": amount,
            "currency": "INR",
            "payment_rail": "IMPS",
            "recipient_name": "Test Payee",
            "recipient_identifier": "payee@upi",
            "purpose": "Test Payment",
        },
    )
    assert res.status_code == 201
    return str(res.json()["id"])


# --------------------------------------------------------------------- auth boundaries


@pytest.mark.asyncio
async def test_login_throttle_returns_429_after_limit(unauth_client: AsyncClient) -> None:
    """12/§2. Login is throttled per client after a bounded number of attempts."""
    limit = get_test_settings().AUTH_LOGIN_MAX_ATTEMPTS_PER_WINDOW
    # The allowed window of attempts returns ordinary auth failures.
    for _ in range(limit):
        res = await unauth_client.post(
            "/api/v1/auth/login", json={"username": "nobody", "password": "wrong"}
        )
        assert res.status_code == 401
    # The next attempt is throttled, not evaluated.
    throttled = await unauth_client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": "wrong"}
    )
    assert throttled.status_code == 429
    assert throttled.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_customer_token_cannot_access_other_transaction(
    unauth_client: AsyncClient,
) -> None:
    """8. A customer token bound to transaction A cannot read transaction B."""
    tx_a = uuid.uuid4()
    tx_b = uuid.uuid4()
    token, _ = create_customer_verification_token(
        challenge_id=str(uuid.uuid4()),
        transaction_id=str(tx_a),
        customer_id="cust_a",
        settings=get_test_settings(),
    )
    res = await unauth_client.get(
        f"/api/v1/transactions/{tx_b}/intervention",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_operator_token_rejected_on_customer_submit(unauth_client: AsyncClient) -> None:
    """§2. An operator access token cannot be substituted for a customer session token."""
    operator_token, _ = create_access_token(str(uuid.uuid4()), get_test_settings())
    res = await unauth_client.post(
        f"/api/v1/verification/{uuid.uuid4()}/submit",
        json={"otp": "123456"},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_customer_token_rejected_on_operator_route(unauth_client: AsyncClient) -> None:
    """§2. A customer verification token cannot authorize an operator-only route."""
    token, _ = create_customer_verification_token(
        challenge_id=str(uuid.uuid4()),
        transaction_id=str(uuid.uuid4()),
        customer_id="cust_a",
        settings=get_test_settings(),
    )
    res = await unauth_client.get(
        "/api/v1/transactions", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 401


# ---------------------------------------------------------- provider / failure injection


@pytest.mark.asyncio
async def test_live_provider_missing_credentials_does_not_fall_back_to_mock() -> None:
    """12. Explicit live-provider mode with missing credentials degrades, never silently mocks."""
    app = _authed_app(ai_client=VertexGeminiClient(get_test_settings()))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        res = await ac.post(
            "/api/v1/scenarios/digital_arrest/runs",
            json={"execution_mode": "LIVE_PROVIDER"},
        )
        assert res.status_code == 201
        run = res.json()
        # No GCP/Gemini credentials in test settings -> provider unavailable, not mock.
        assert run["ai_provider"] != "mock_gemini"
        ai_stage = next(s for s in run["stages"] if s["key"] == "ai_investigation")
        coercion_stage = next(s for s in run["stages"] if s["key"] == "coercion_analysis")
        assert ai_stage["status"] == "UNAVAILABLE"
        assert coercion_stage["status"] == "UNAVAILABLE"
        # Deterministic policy still holds the coercive transfer (never downgraded to allow).
        assert run["final_state"] == "HELD_FOR_VERIFICATION"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_scenario_failure_after_transaction_creation_is_not_reported_complete() -> None:
    """6 & §3. An unexpected stage failure leaves an auditable partial state, not success."""
    failing = MockGeminiClient(should_fail=True, failure_exception=ValueError("boom"))
    app = _authed_app(ai_client=failing)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        res = await ac.post(
            "/api/v1/scenarios/digital_arrest/runs",
            json={"execution_mode": "LIVE_PROVIDER"},
        )
        assert res.status_code == 201
        run = res.json()
        assert run["status"] == "FAILED"
        assert run["workflow_execution_success"] is False
        # The transaction was created before the failing stage: partial state is auditable.
        assert run["transaction_id"] is not None
        coercion_stage = next(s for s in run["stages"] if s["key"] == "coercion_analysis")
        assert coercion_stage["status"] == "FAILED"
        decision_stage = next(s for s in run["stages"] if s["key"] == "decision_policy")
        assert decision_stage["status"] == "PENDING"

        # The evaluation reports INCOMPLETE and never claims workflow success.
        ev = await ac.get(f"/api/v1/scenarios/runs/{run['id']}/evaluation")
        assert ev.status_code == 200
        assert ev.json()["overall"] == "INCOMPLETE"
        assert ev.json()["workflow_execution_success"] is False
    app.dependency_overrides.clear()


# ----------------------------------------------------------- idempotency & state integrity


@pytest.mark.asyncio
async def test_duplicate_response_requests_persist_single_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """4 & 14. Duplicate response requests create exactly one response and one notification."""
    tx_id = await _create_tx(client, "1500.00")
    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_trusted_beneficiary": True, "is_first_time_recipient": False}},
    )
    key = f"resp-{uuid.uuid4().hex}"
    r1 = await client.post(
        f"/api/v1/transactions/{tx_id}/respond",
        json={"channel": "IN_APP_SIMULATED", "idempotency_key": key},
    )
    r2 = await client.post(
        f"/api/v1/transactions/{tx_id}/respond",
        json={"channel": "IN_APP_SIMULATED", "idempotency_key": key},
    )
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]

    tx_uuid = uuid.UUID(tx_id)
    resp_count = (
        await db_session.execute(
            select(func.count(TransactionResponseModel.id)).where(
                TransactionResponseModel.transaction_id == tx_uuid
            )
        )
    ).scalar_one()
    notif_count = (
        await db_session.execute(
            select(func.count(TransactionNotificationModel.id)).where(
                TransactionNotificationModel.transaction_id == tx_uuid
            )
        )
    ).scalar_one()
    assert resp_count == 1
    assert notif_count == 1


@pytest.mark.asyncio
async def test_stale_decision_is_rejected_on_response(client: AsyncClient) -> None:
    """9. A stale decision does not override a newer terminal transaction state."""
    tx_id = await _create_tx(client, "60000.00")
    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={
            "evidence": {"is_first_time_recipient": True, "active_call_present": True},
            "run_investigation": False,
        },
    )
    # Move the transaction to a terminal state out-of-band, making the decision stale.
    cancel = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={"target_state": "CANCELLED_SIMULATED", "actor_type": "SYSTEM", "reason": "test"},
    )
    assert cancel.status_code == 200
    res = await client.post(f"/api/v1/transactions/{tx_id}/respond", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "STALE_DECISION"


@pytest.mark.asyncio
async def test_scenario_expectation_never_overrides_observed(client: AsyncClient) -> None:
    """13. The evaluation's observed outcome is the authoritative decision, not the expectation."""
    run = (
        await client.post(
            "/api/v1/scenarios/legitimate_high_value/runs",
            json={"execution_mode": "DETERMINISTIC"},
        )
    ).json()
    tx_id = run["transaction_id"]
    decision = (await client.get(f"/api/v1/transactions/{tx_id}/decision")).json()
    ev = (await client.get(f"/api/v1/scenarios/runs/{run['id']}/evaluation")).json()
    observed = next(d for d in ev["dimensions"] if d["name"] == "policy_action")["observed"]
    assert observed == decision["action"]
