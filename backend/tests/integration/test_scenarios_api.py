"""Integration tests for the end-to-end scenario simulation dashboard (P2-A8)."""

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScenarioRunModel, TransactionDecisionModel, TransactionModel
from app.domain.scenario_catalog import SCENARIO_CATALOG

ALL_SCENARIO_IDS = [s.id for s in SCENARIO_CATALOG]


async def _start_run(
    client: AsyncClient, scenario_id: str, *, mode: str = "DETERMINISTIC", idem: str | None = None
) -> tuple[int, dict]:
    body: dict = {"execution_mode": mode}
    if idem is not None:
        body["idempotency_key"] = idem
    res = await client.post(f"/api/v1/scenarios/{scenario_id}/runs", json=body)
    return res.status_code, res.json()


# --------------------------------------------------------------------------- catalogue


@pytest.mark.asyncio
async def test_list_catalog(client: AsyncClient) -> None:
    res = await client.get("/api/v1/scenarios")
    assert res.status_code == 200
    body = res.json()
    assert body["catalog_version"]
    assert body["total"] == len(SCENARIO_CATALOG)
    ids = {item["id"] for item in body["items"]}
    assert {"digital_arrest", "mule_network", "strong_coercion_verified"}.issubset(ids)
    for item in body["items"]:
        assert item["expectation"]["policy_action"]
        assert item["expectation"]["final_state"]
        assert isinstance(item["expectation"]["limitations"], list)


# --------------------------------------------------------------- end-to-end per scenario


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_id", ALL_SCENARIO_IDS)
async def test_run_matches_declared_expectation(client: AsyncClient, scenario_id: str) -> None:
    """2 & 8. Each scenario executes end-to-end and its evaluation is MATCH."""
    code, run = await _start_run(client, scenario_id)
    assert code == 201, run
    assert run["status"] == "COMPLETED", run
    assert run["workflow_execution_success"] is True
    assert run["is_simulated"] is True
    # Timeline present with all canonical stages, ordered.
    seqs = [s["sequence"] for s in run["stages"]]
    assert seqs == sorted(seqs)
    assert {s["key"] for s in run["stages"]} == {
        "transaction_created",
        "risk_assessment",
        "ai_investigation",
        "coercion_analysis",
        "decision_policy",
        "verification",
        "response_orchestration",
        "notification",
    }

    ev = await client.get(f"/api/v1/scenarios/runs/{run['id']}/evaluation")
    assert ev.status_code == 200
    ev_body = ev.json()
    assert ev_body["overall"] == "MATCH", (scenario_id, ev_body["dimensions"])
    assert ev_body["workflow_execution_success"] is True
    assert "not a measure of real-world" in ev_body["disclaimer"].lower()


@pytest.mark.asyncio
async def test_digital_arrest_holds(client: AsyncClient) -> None:
    """3. Digital-arrest coercion leads to the documented protective hold."""
    code, run = await _start_run(client, "digital_arrest")
    assert code == 201
    assert run["final_state"] == "HELD_FOR_VERIFICATION"
    decision_stage = next(s for s in run["stages"] if s["key"] == "decision_policy")
    assert decision_stage["status"] == "COMPLETED"
    assert decision_stage["entity_id"] is not None
    coercion_stage = next(s for s in run["stages"] if s["key"] == "coercion_analysis")
    assert coercion_stage["status"] == "COMPLETED"
    response_stage = next(s for s in run["stages"] if s["key"] == "response_orchestration")
    assert "HOLD_PROTECTIVE" in response_stage["detail"]


@pytest.mark.asyncio
async def test_legitimate_high_value_not_treated_as_fraud(client: AsyncClient) -> None:
    """4. A legitimate high-value transfer settles and is not held or blocked."""
    code, run = await _start_run(client, "legitimate_high_value")
    assert code == 201
    assert run["final_state"] == "SETTLED_SIMULATED"
    ai_stage = next(s for s in run["stages"] if s["key"] == "ai_investigation")
    # Low risk: investigation is skipped (not fabricated as completed).
    assert ai_stage["status"] == "SKIPPED"
    assert ai_stage["entity_id"] is None


@pytest.mark.asyncio
async def test_ordinary_voice_stress_does_not_hold_or_block(client: AsyncClient) -> None:
    """5. Ordinary voice stress alone never causes a hold or block."""
    code, run = await _start_run(client, "ordinary_stressed_customer")
    assert code == 201
    assert run["final_state"] not in ("HELD_FOR_VERIFICATION", "CANCELLED_SIMULATED")
    decision_stage = next(s for s in run["stages"] if s["key"] == "decision_policy")
    assert "HOLD_FOR_INVESTIGATION" not in decision_stage["detail"]
    assert "BLOCK" not in decision_stage["detail"]


@pytest.mark.asyncio
async def test_strong_coercion_survives_successful_verification(client: AsyncClient) -> None:
    """6. Successful verification with persistent coercion still holds the payment."""
    code, run = await _start_run(client, "strong_coercion_verified")
    assert code == 201
    verification_stage = next(s for s in run["stages"] if s["key"] == "verification")
    assert verification_stage["status"] == "COMPLETED"
    assert "SUCCEEDED" in verification_stage["reason_codes"]
    # Verification succeeded, yet the transaction remains protectively held.
    assert run["final_state"] == "HELD_FOR_VERIFICATION"

    ev = (await client.get(f"/api/v1/scenarios/runs/{run['id']}/evaluation")).json()
    assert ev["overall"] == "MATCH"
    vdim = next(d for d in ev["dimensions"] if d["name"] == "verification_outcome")
    assert vdim["observed"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_no_fabricated_stage_results(client: AsyncClient) -> None:
    """9. Skipped/unavailable stages are explicit and carry no fabricated success data."""
    code, run = await _start_run(client, "legitimate_high_value")
    assert code == 201
    for stage in run["stages"]:
        if stage["status"] == "SKIPPED":
            assert stage["entity_id"] is None
            assert stage["completed_at"] is not None  # explicit terminal marker
        if stage["status"] == "COMPLETED":
            # A completed stage must reference a real persisted entity.
            assert stage["entity_id"] is not None


# ------------------------------------------------------------------- idempotency & retry


@pytest.mark.asyncio
async def test_idempotent_run(client: AsyncClient, db_session: AsyncSession) -> None:
    """10. A repeated idempotency key returns the same run and creates no duplicate."""
    key = f"idem-{uuid.uuid4().hex}"
    code1, run1 = await _start_run(client, "fake_invoice", idem=key)
    code2, run2 = await _start_run(client, "fake_invoice", idem=key)
    assert code1 == 201
    assert code2 == 200
    assert run1["id"] == run2["id"]

    total = (await db_session.execute(select(func.count(ScenarioRunModel.id)))).scalar_one()
    assert total == 1


@pytest.mark.asyncio
async def test_concurrent_same_idempotency_key(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """11. Concurrent starts with the same key never create duplicate runs."""
    key = f"idem-{uuid.uuid4().hex}"
    results = await asyncio.gather(
        _start_run(client, "ambiguous_payment", idem=key),
        _start_run(client, "ambiguous_payment", idem=key),
    )
    run_ids = {body["id"] for _code, body in results}
    assert len(run_ids) == 1

    total = (await db_session.execute(select(func.count(ScenarioRunModel.id)))).scalar_one()
    assert total == 1


@pytest.mark.asyncio
async def test_retry_non_failed_run_is_rejected(client: AsyncClient) -> None:
    """A completed run is not retryable."""
    code, run = await _start_run(client, "fake_invoice")
    assert code == 201
    res = await client.post(f"/api/v1/scenarios/runs/{run['id']}/retry")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_retry_failed_run_does_not_duplicate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """12. Retrying reuses the existing transaction/decision/response (no duplicates)."""
    code, run = await _start_run(client, "digital_arrest")
    assert code == 201
    tx_id = uuid.UUID(run["transaction_id"])

    # Simulate a prior partial failure by flipping the run to FAILED.
    await db_session.execute(
        ScenarioRunModel.__table__.update()
        .where(ScenarioRunModel.id == uuid.UUID(run["id"]))
        .values(status="FAILED")
    )
    await db_session.commit()

    decisions_before = (
        await db_session.execute(
            select(func.count(TransactionDecisionModel.id)).where(
                TransactionDecisionModel.transaction_id == tx_id
            )
        )
    ).scalar_one()
    tx_before = (await db_session.execute(select(func.count(TransactionModel.id)))).scalar_one()

    res = await client.post(f"/api/v1/scenarios/runs/{run['id']}/retry")
    assert res.status_code == 200
    assert res.json()["status"] == "COMPLETED"

    decisions_after = (
        await db_session.execute(
            select(func.count(TransactionDecisionModel.id)).where(
                TransactionDecisionModel.transaction_id == tx_id
            )
        )
    ).scalar_one()
    tx_after = (await db_session.execute(select(func.count(TransactionModel.id)))).scalar_one()
    assert decisions_after == decisions_before
    assert tx_after == tx_before


# ------------------------------------------------------------------- provider / failure


@pytest.mark.asyncio
async def test_ai_unavailable_degrades_gracefully() -> None:
    """7. AI/provider unavailable degrades gracefully without failing the workflow."""
    from app.api.auth import get_current_operator
    from app.api.fraud_responses import get_current_operator_optional
    from app.api.investigations import get_default_ai_client
    from app.core.errors import AIProviderError
    from app.db.models import OperatorModel
    from app.services.ai_client import MockGeminiClient
    from tests.conftest import _build_test_app

    app = _build_test_app()
    failing = MockGeminiClient(
        should_fail=True,
        failure_exception=AIProviderError(message="down", code="AI_PROVIDER_ERROR"),
    )
    app.dependency_overrides[get_default_ai_client] = lambda: failing
    stub = OperatorModel(id=uuid.uuid4(), username="op", password_hash="x", is_active=True)
    app.dependency_overrides[get_current_operator] = lambda: stub
    app.dependency_overrides[get_current_operator_optional] = lambda: stub

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        res = await ac.post(
            "/api/v1/scenarios/digital_arrest/runs",
            json={"execution_mode": "LIVE_PROVIDER"},
        )
        assert res.status_code == 201, res.json()
        run = res.json()
        # Despite provider failure, the deterministic workflow completes and still holds.
        assert run["status"] == "COMPLETED"
        assert run["final_state"] == "HELD_FOR_VERIFICATION"
        ai_stage = next(s for s in run["stages"] if s["key"] == "ai_investigation")
        assert ai_stage["status"] == "UNAVAILABLE"
        coercion_stage = next(s for s in run["stages"] if s["key"] == "coercion_analysis")
        assert coercion_stage["status"] == "UNAVAILABLE"
    app.dependency_overrides.clear()


# ------------------------------------------------------------------------ authorization


@pytest.mark.asyncio
async def test_scenarios_require_authentication(unauth_client: AsyncClient) -> None:
    """13. Scenario routes are behind the operator authentication boundary."""
    assert (await unauth_client.get("/api/v1/scenarios")).status_code == 401
    assert (
        await unauth_client.post(
            "/api/v1/scenarios/digital_arrest/runs", json={"execution_mode": "DETERMINISTIC"}
        )
    ).status_code == 401
