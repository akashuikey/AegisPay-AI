"""Integration tests for transactions API, idempotency, state machine transitions,
and audit logs.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TransactionAuditModel


@pytest.mark.asyncio
async def test_create_transaction_success(client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify transaction creation persists record with INITIATED state and atomic audit entry."""
    payload = {
        "customer_id": "cust_101",
        "idempotency_key": "idemp_key_001",
        "amount": "12500.50",
        "currency": "INR",
        "payment_rail": "UPI",
        "recipient_name": "Sharma Electronics",
        "recipient_identifier": "sharma@okhdfcbank",
        "purpose": "Laptop purchase",
    }

    response = await client.post("/api/v1/transactions", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["customer_id"] == "cust_101"
    assert data["idempotency_key"] == "idemp_key_001"
    assert Decimal(data["amount"]) == Decimal("12500.50")
    assert data["currency"] == "INR"
    assert data["payment_rail"] == "UPI"
    assert data["recipient_name"] == "Sharma Electronics"
    assert data["state"] == "INITIATED"
    assert data["version"] == 1

    tx_id = uuid.UUID(data["id"])

    # Verify audit entry was atomically written
    audit_stmt = select(TransactionAuditModel).where(TransactionAuditModel.transaction_id == tx_id)
    audits = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(audits) == 1
    assert audits[0].from_state is None
    assert audits[0].to_state == "INITIATED"
    assert audits[0].actor_type == "CUSTOMER"


@pytest.mark.asyncio
async def test_idempotent_replay_returns_http_200(client: AsyncClient) -> None:
    """Verify exact duplicate request replays existing transaction with HTTP 200."""
    payload = {
        "customer_id": "cust_102",
        "idempotency_key": "idemp_key_002",
        "amount": "5000.00",
        "currency": "INR",
        "payment_rail": "IMPS",
        "recipient_name": "Priya Singh",
        "recipient_identifier": "9876543210@paytm",
    }

    # First request: 201 Created
    first_resp = await client.post("/api/v1/transactions", json=payload)
    assert first_resp.status_code == 201
    first_data = first_resp.json()

    # Second identical request: 200 OK with same ID
    second_resp = await client.post("/api/v1/transactions", json=payload)
    assert second_resp.status_code == 200
    second_data = second_resp.json()

    assert first_data["id"] == second_data["id"]
    assert first_data["idempotency_key"] == second_data["idempotency_key"]


@pytest.mark.asyncio
async def test_idempotency_conflict_returns_http_409(client: AsyncClient) -> None:
    """Verify reusing an idempotency key with different payload returns HTTP 409 Conflict."""
    payload_original = {
        "customer_id": "cust_103",
        "idempotency_key": "idemp_key_003",
        "amount": "1000.00",
        "currency": "INR",
        "payment_rail": "UPI",
        "recipient_name": "Target Recipient",
        "recipient_identifier": "target@upi",
    }

    first_resp = await client.post("/api/v1/transactions", json=payload_original)
    assert first_resp.status_code == 201

    # Conflict payload with different amount
    payload_conflict = {
        **payload_original,
        "amount": "9999.00",
    }
    conflict_resp = await client.post("/api/v1/transactions", json=payload_conflict)
    assert conflict_resp.status_code == 409

    data = conflict_resp.json()
    assert data["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_get_transaction_by_id(client: AsyncClient) -> None:
    """Verify fetching transaction by ID works and unknown ID returns 404."""
    payload = {
        "customer_id": "cust_104",
        "idempotency_key": "idemp_key_004",
        "amount": "250.00",
        "currency": "INR",
        "payment_rail": "UPI",
        "recipient_name": "Chai Point",
        "recipient_identifier": "chaipoint@upi",
    }
    create_resp = await client.post("/api/v1/transactions", json=payload)
    assert create_resp.status_code == 201
    tx_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/v1/transactions/{tx_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == tx_id

    # Non-existent ID
    random_id = uuid.uuid4()
    not_found_resp = await client.get(f"/api/v1/transactions/{random_id}")
    assert not_found_resp.status_code == 404
    assert not_found_resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_list_transactions_pagination(client: AsyncClient) -> None:
    """Verify listing transactions with pagination and customer filter."""
    for i in range(5):
        await client.post(
            "/api/v1/transactions",
            json={
                "customer_id": f"cust_{i % 2}",
                "idempotency_key": f"key_{i}",
                "amount": f"{(i + 1) * 100}.00",
                "payment_rail": "UPI",
                "recipient_name": f"Recipient {i}",
                "recipient_identifier": f"recip_{i}@upi",
            },
        )

    # Test limit and offset
    list_resp = await client.get("/api/v1/transactions?limit=2&offset=0")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0

    # Test customer filtering
    filter_resp = await client.get("/api/v1/transactions?customer_id=cust_0")
    assert filter_resp.status_code == 200
    filtered_data = filter_resp.json()
    assert filtered_data["total"] == 3
    assert all(item["customer_id"] == "cust_0" for item in filtered_data["items"])


@pytest.mark.asyncio
async def test_full_state_transition_workflow_and_audit(client: AsyncClient) -> None:
    """Verify progressive state transitions from INITIATED to SETTLED_SIMULATED
    with audit history.
    """
    create_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_201",
            "idempotency_key": "tx_trans_01",
            "amount": "8500.00",
            "payment_rail": "UPI",
            "recipient_name": "Verified Store",
            "recipient_identifier": "store@upi",
        },
    )
    assert create_resp.status_code == 201
    tx_id = create_resp.json()["id"]

    transitions = [
        ("ASSESSING", "SYSTEM", "Automated risk assessment started"),
        ("RISK_ASSESSED", "POLICY_ENGINE", "ML and rule engines evaluated"),
        ("DECISION_READY", "POLICY_ENGINE", "Score: 12 (LOW_RISK)"),
        ("SETTLED_SIMULATED", "SYSTEM", "Payment simulation settled"),
    ]

    expected_version = 1
    for target_state, actor, reason in transitions:
        expected_version += 1
        trans_resp = await client.post(
            f"/api/v1/transactions/{tx_id}/transitions",
            json={
                "target_state": target_state,
                "actor_type": actor,
                "reason": reason,
                "correlation_id": "test_corr_123",
            },
        )
        assert trans_resp.status_code == 200
        data = trans_resp.json()
        assert data["state"] == target_state
        assert data["version"] == expected_version

    # Verify complete audit history endpoint
    audit_resp = await client.get(f"/api/v1/transactions/{tx_id}/audit")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["total_entries"] == 5  # 1 initial + 4 transitions

    history = audit_data["items"]
    assert history[0]["to_state"] == "INITIATED"
    assert history[1]["to_state"] == "ASSESSING"
    assert history[2]["to_state"] == "RISK_ASSESSED"
    assert history[3]["to_state"] == "DECISION_READY"
    assert history[4]["to_state"] == "SETTLED_SIMULATED"


@pytest.mark.asyncio
async def test_invalid_state_transition_rejected(client: AsyncClient) -> None:
    """Verify invalid transition directly from INITIATED to SETTLED_SIMULATED is rejected."""
    create_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_301",
            "idempotency_key": "tx_trans_invalid",
            "amount": "3000.00",
            "payment_rail": "UPI",
            "recipient_name": "Test Recipient",
            "recipient_identifier": "test@upi",
        },
    )
    assert create_resp.status_code == 201
    tx_id = create_resp.json()["id"]

    # Attempt forbidden jump straight to SETTLED_SIMULATED
    invalid_resp = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={"target_state": "SETTLED_SIMULATED"},
    )
    assert invalid_resp.status_code == 400
    err = invalid_resp.json()
    assert err["error"]["code"] == "INVALID_STATE_TRANSITION"

    # State must remain INITIATED
    get_resp = await client.get(f"/api/v1/transactions/{tx_id}")
    assert get_resp.json()["state"] == "INITIATED"
    assert get_resp.json()["version"] == 1


@pytest.mark.asyncio
async def test_terminal_state_cannot_transition(client: AsyncClient) -> None:
    """Verify terminal state CANCELLED_SIMULATED cannot be transitioned."""
    create_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_401",
            "idempotency_key": "tx_trans_cancel",
            "amount": "1000.00",
            "payment_rail": "UPI",
            "recipient_name": "Merchant",
            "recipient_identifier": "m@upi",
        },
    )
    tx_id = create_resp.json()["id"]

    # INITIATED -> CANCELLED_SIMULATED is allowed
    cancel_resp = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={
            "target_state": "CANCELLED_SIMULATED",
            "reason": "Cancelled by user before assessment",
        },
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["state"] == "CANCELLED_SIMULATED"

    # Attempting to move away from CANCELLED_SIMULATED must fail
    retry_resp = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={"target_state": "INITIATED"},
    )
    assert retry_resp.status_code == 400
    assert retry_resp.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_validation_errors_for_invalid_amounts(client: AsyncClient) -> None:
    """Verify zero or negative amounts return 422 Unprocessable Entity."""
    # Zero amount
    zero_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_err",
            "idempotency_key": "zero_key",
            "amount": "0.00",
            "payment_rail": "UPI",
            "recipient_name": "Test",
            "recipient_identifier": "test@upi",
        },
    )
    assert zero_resp.status_code == 422
    assert zero_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # Negative amount
    neg_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_err",
            "idempotency_key": "neg_key",
            "amount": "-50.00",
            "payment_rail": "UPI",
            "recipient_name": "Test",
            "recipient_identifier": "test@upi",
        },
    )
    assert neg_resp.status_code == 422


@pytest.mark.asyncio
async def test_concurrent_transition_optimistic_lock_failure(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify that attempting to update a stale version raises ConcurrencyConflictError."""
    from app.core.errors import ConcurrencyConflictError
    from app.repositories.transaction_repository import TransactionRepository

    create_resp = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_lock",
            "idempotency_key": "tx_lock_01",
            "amount": "4000.00",
            "payment_rail": "UPI",
            "recipient_name": "Test",
            "recipient_identifier": "test@upi",
        },
    )
    tx_id = create_resp.json()["id"]

    # Transition to ASSESSING (version becomes 2)
    t1 = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={"target_state": "ASSESSING"},
    )
    assert t1.status_code == 200
    assert t1.json()["version"] == 2

    # Now attempt an update expecting version 1 (which is now stale)
    repo = TransactionRepository(db_session)
    audit = TransactionAuditModel(
        id=uuid.uuid4(),
        transaction_id=uuid.UUID(tx_id),
        from_state="INITIATED",
        to_state="ASSESSING",
        actor_type="SYSTEM",
    )
    with pytest.raises(ConcurrencyConflictError) as exc_info:
        await repo.update_state(
            transaction_id=uuid.UUID(tx_id),
            expected_version=1,  # Stale version
            new_state="ASSESSING",
            audit_entry=audit,
        )
    assert exc_info.value.code == "CONCURRENCY_CONFLICT"
    assert exc_info.value.status_code == 409
