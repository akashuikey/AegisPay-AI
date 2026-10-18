"""Integration tests for P2-A12: Transaction Intelligence and Selective Calls."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_customer_verification_token
from app.domain.customer_dialogue import CallSessionStatus
from app.domain.decision_policy import PolicyAction
from tests.conftest import get_test_settings


def _customer_token(transaction_id: str, customer_id: str = "CU-1042") -> str:
    """Mint a customer verification session token bound to a transaction."""
    token, _ = create_customer_verification_token(
        challenge_id=str(uuid.uuid4()),
        transaction_id=transaction_id,
        customer_id=customer_id,
        settings=get_test_settings(),
    )
    return token


async def _create_tx(
    client: AsyncClient,
    amount: str = "50000.00",
    recipient_identifier: str = "user@upi",
    recipient_name: str = "Test Recipient",
) -> str:
    payload = {
        "customer_id": f"cust_{uuid.uuid4().hex[:8]}",
        "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
        "amount": amount,
        "currency": "INR",
        "payment_rail": "UPI",
        "recipient_name": recipient_name,
        "recipient_identifier": recipient_identifier,
        "purpose": "Simulated payment",
    }
    res = await client.post("/api/v1/transactions", json=payload)
    assert res.status_code == 201
    return str(res.json()["id"])


@pytest.mark.asyncio
async def test_customer_token_cannot_initiate_call(
    client: AsyncClient, unauth_client: AsyncClient
) -> None:
    """Product Gap 1: Customer-scoped tokens are forbidden from initiating calls (403)."""
    tx_id = await _create_tx(client, "15000.00")
    cust_token = _customer_token(tx_id)

    res = await unauth_client.post(
        f"/api/v1/transactions/{tx_id}/calls",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={"channel": "VOICE_SIMULATED"},
    )
    assert res.status_code == 403
    body = res.json()
    assert body["error"]["code"] == "FORBIDDEN"
    assert "Customer tokens are not permitted" in body["error"]["message"]


@pytest.mark.asyncio
async def test_operator_token_can_initiate_call(client: AsyncClient) -> None:
    """Operator-scoped tokens are permitted to initiate calls (201)."""
    tx_id = await _create_tx(client, "15000.00")

    res = await client.post(
        f"/api/v1/transactions/{tx_id}/calls",
        json={"channel": "VOICE_SIMULATED"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == CallSessionStatus.RINGING.value
    assert body["transaction_id"] == tx_id


@pytest.mark.asyncio
async def test_recipient_intelligence_authoritative_mule_override(client: AsyncClient) -> None:
    """Client cannot bypass mule detection by sending falsified evidence parameters."""
    # Fictional high-risk recipient from registry
    tx_id = await _create_tx(
        client,
        amount="85000.00",
        recipient_identifier="cbi.cybercell.escrow@sbi-dept.sim",
        recipient_name="Central Cyber Crime Police Escrow",
    )

    # Client tries to claim recipient is trusted and not a mule
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={
            "evidence": {
                "is_trusted_beneficiary": True,
                "is_flagged_mule": False,
                "fan_in_count_24h": 0,
                "fan_out_count_24h": 0,
            },
            "run_investigation": False,
        },
    )
    assert res.status_code == 201
    body = res.json()
    # Server registry authoritative data overrides client tampering -> BLOCK
    assert body["action"] == PolicyAction.BLOCK.value
    assert body["to_state"] == "CANCELLED_SIMULATED"
    assert any("MULE" in reason for reason in body["reason_codes"])


@pytest.mark.asyncio
async def test_recipient_intelligence_trusted_beneficiary(client: AsyncClient) -> None:
    """Trusted recipient in registry automatically receives trusted beneficiary status."""
    tx_id = await _create_tx(
        client,
        amount="3500.00",
        recipient_identifier="ananya.sharma@okaxis",
        recipient_name="Ananya Sharma",
    )

    # No evidence supplied by client; server resolves trusted status
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"run_investigation": False},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["action"] == PolicyAction.ALLOW.value
    assert body["to_state"] == "SETTLED_SIMULATED"


@pytest.mark.asyncio
async def test_recipient_intelligence_unknown_recipient_not_prejudged(client: AsyncClient) -> None:
    """Unknown recipient is not automatically assumed to be fraudulent."""
    tx_id = await _create_tx(
        client,
        amount="4000.00",
        recipient_identifier="karan.consulting.freelance@pnb",
        recipient_name="Karan Consulting Freelance",
    )

    res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"run_investigation": False},
    )
    assert res.status_code == 201
    body = res.json()
    # Moderate amount, low risk -> ALLOW
    assert body["action"] == PolicyAction.ALLOW.value
    assert body["to_state"] == "SETTLED_SIMULATED"


@pytest.mark.asyncio
async def test_live_mode_call_initiation_decoupled_from_text_model(client: AsyncClient) -> None:
    """Call creation succeeds in RINGING without requiring text-model availability."""
    tx_id = await _create_tx(client, "25000.00")
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/calls",
        json={"channel": "VOICE_SIMULATED"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == CallSessionStatus.RINGING.value
    assert len(body["turns"]) == 1
    assert "Aster Bank Fraud Prevention" in body["turns"][0]["content"]
