"""Integration tests for AI forensic investigations API endpoints.
Tests persistence in PostgreSQL, schema serialization, dependency overrides,
and state machine non-mutation invariants.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.investigations import get_default_ai_client
from app.db.models import TransactionInvestigationModel
from app.services.ai_client import MockGeminiClient


@pytest.mark.asyncio
async def test_create_and_retrieve_investigation_lifecycle(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify end-to-end investigation creation, persistence, and retrieval."""
    # 1. Create a simulated transaction
    tx_payload = {
        "customer_id": "cust_inv_test_01",
        "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
        "amount": "250000.00",
        "currency": "INR",
        "payment_rail": "RTGS",
        "recipient_name": "Govt Security Clearance Account",
        "recipient_identifier": "cbi.clearance@sbi",
        "purpose": "Urgent court identity bond",
    }
    tx_res = await client.post("/api/v1/transactions", json=tx_payload)
    assert tx_res.status_code == 201
    tx_data = tx_res.json()
    tx_id = tx_data["id"]

    # 2. Perform deterministic risk assessment
    assess_res = await client.post(
        f"/api/v1/transactions/{tx_id}/assess",
        json={
            "evidence": {
                "amount": 250000.0,
                "is_first_time_recipient": True,
                "recent_fd_liquidation": True,
                "active_call_present": True,
                "screen_sharing_active": True,
                "coercive_language_detected": True,
            }
        },
    )
    assert assess_res.status_code == 200
    assess_id = assess_res.json()["id"]

    # Record transaction state before AI investigation
    tx_before_res = await client.get(f"/api/v1/transactions/{tx_id}")
    tx_before = tx_before_res.json()

    # 3. Request AI investigation
    inv_payload = {
        "transaction_id": tx_id,
        "assessment_id": assess_id,
        "customer_statements": [
            {
                "statement_id": "stmt_01",
                "question": "Why are you making this transfer?",
                "answer": (
                    "Officer Verma from CBI said I must transfer ₹2,50,000 immediately "
                    "or I will be arrested."
                ),
                "channel": "chat",
            }
        ],
        "document_extractions": [
            {
                "doc_id": "doc_warrant_01",
                "document_type": "ARREST_WARRANT",
                "claimed_issuer": "Supreme Court / CBI Cyber Division",
                "claimed_amount": 250000.0,
                "extracted_text": (
                    "Non-bailable warrant issued. Clear payment to security account "
                    "to avoid custody."
                ),
                "verification_source": "whatsapp_download",
            }
        ],
        "telephony_telemetry": {
            "active_call_present": True,
            "screen_sharing_active": True,
            "voice_stress_detected": True,
            "call_duration_seconds": 1820,
        },
        "recipient_intelligence": {
            "is_flagged_mule": False,
            "account_age_days": 12,
            "fan_in_count_24h": 3,
            "fan_out_count_24h": 2,
        },
        "coercion_cues": ["legal intimidation", "immediate arrest threat", "secrecy demand"],
        "correlation_id": "corr_integ_test_01",
    }

    inv_res = await client.post("/api/v1/investigations", json=inv_payload)
    assert inv_res.status_code == 201

    inv_data = inv_res.json()
    assert "id" in inv_data
    investigation_id = inv_data["id"]
    assert inv_data["transaction_id"] == tx_id
    assert inv_data["assessment_id"] == assess_id
    assert inv_data["overall_risk_sentiment"] in ("COERCED", "SUSPICIOUS")
    assert inv_data["confidence"] in ("HIGH", "MEDIUM")
    assert isinstance(inv_data["confidence_score"], float)
    assert len(inv_data["findings"]) > 0
    assert inv_data["model_metadata"]["provider"] == "mock_gemini"

    # 4. Verify record in PostgreSQL database
    stmt = select(TransactionInvestigationModel).where(
        TransactionInvestigationModel.id == uuid.UUID(investigation_id)
    )
    db_record = (await db_session.execute(stmt)).scalar_one_or_none()
    assert db_record is not None
    assert str(db_record.transaction_id) == tx_id
    assert db_record.overall_risk_sentiment == inv_data["overall_risk_sentiment"]

    # 5. Fetch single investigation by ID
    get_res = await client.get(f"/api/v1/investigations/{investigation_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == investigation_id

    # 6. Fetch investigations list for transaction
    list_res = await client.get(f"/api/v1/transactions/{tx_id}/investigations")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["transaction_id"] == tx_id
    assert list_data["total_entries"] >= 1
    assert any(item["id"] == investigation_id for item in list_data["items"])

    # 7. CRITICAL STATE INVARIANT: Verify transaction state was NOT modified
    tx_after_res = await client.get(f"/api/v1/transactions/{tx_id}")
    tx_after = tx_after_res.json()
    assert tx_after["state"] == tx_before["state"]
    assert tx_after["version"] == tx_before["version"]


@pytest.mark.asyncio
async def test_investigation_nonexistent_transaction_returns_404(client: AsyncClient) -> None:
    """Verify investigating a nonexistent transaction returns 404."""
    random_id = str(uuid.uuid4())
    payload = {
        "transaction_id": random_id,
        "customer_statements": [],
    }
    response = await client.post("/api/v1/investigations", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_nonexistent_investigation_returns_404(client: AsyncClient) -> None:
    """Verify fetching nonexistent investigation ID returns 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/investigations/{random_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_list_investigations_nonexistent_transaction_returns_404(
    client: AsyncClient,
) -> None:
    """Verify listing investigations for nonexistent transaction returns 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/transactions/{random_id}/investigations")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_investigation_provider_failure_returns_502(client: AsyncClient) -> None:
    """Verify that an AI provider failure returns HTTP 502 with structured error envelope."""
    # 1. Create a transaction
    tx_res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_fail_01",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": "10000.00",
            "currency": "INR",
            "payment_rail": "UPI",
            "recipient_name": "Test Payee",
            "recipient_identifier": "payee@upi",
            "purpose": "Test",
        },
    )
    assert tx_res.status_code == 201
    tx_id = tx_res.json()["id"]

    # 2. Inject failing AI client override
    app = client._transport.app  # type: ignore[attr-defined]
    failing_client = MockGeminiClient(should_fail=True)
    app.dependency_overrides[get_default_ai_client] = lambda: failing_client

    try:
        response = await client.post(
            "/api/v1/investigations",
            json={"transaction_id": tx_id},
        )
        assert response.status_code == 502
        data = response.json()
        assert data["error"]["code"] == "AI_PROVIDER_ERROR"
    finally:
        # Restore default mock client
        app.dependency_overrides[get_default_ai_client] = lambda: MockGeminiClient()
