"""Integration tests for dynamic simulated customer calls and dialogue turns (Option A)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_customer_verification_token
from app.db.models import InvestigationConversationTurnModel, TransactionCallSessionModel
from app.domain.customer_dialogue import CallSessionStatus, DialogueChannel
from app.domain.investigation import ConversationRole, EvidenceProvenance
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


async def _create_test_transaction(client: AsyncClient, amount: str = "75000.00") -> str:
    """Helper to create a fresh simulated transaction."""
    tx_payload = {
        "customer_id": f"cust_{uuid.uuid4().hex[:8]}",
        "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
        "amount": amount,
        "currency": "INR",
        "payment_rail": "IMPS",
        "recipient_name": "Govt Clearance Escrow",
        "recipient_identifier": "govt.clearance@sbi",
        "purpose": "Verification deposit",
    }
    res = await client.post("/api/v1/transactions", json=tx_payload)
    assert res.status_code == 201
    return str(res.json()["id"])


@pytest.mark.asyncio
async def test_initiate_call_session_success(client: AsyncClient) -> None:
    """Initiating a call generates session, sets RINGING, and produces Gemini initial question."""
    tx_id = await _create_test_transaction(client)

    res = await client.post(
        f"/api/v1/transactions/{tx_id}/calls",
        json={"channel": "VOICE_SIMULATED", "idempotency_key": f"key_{uuid.uuid4().hex[:8]}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["transaction_id"] == tx_id
    assert data["status"] == CallSessionStatus.RINGING.value
    assert data["channel"] == DialogueChannel.VOICE_SIMULATED.value
    assert data["direction"] == "OUTBOUND_SIMULATED"
    assert data["attempt_number"] == 1
    assert len(data["turns"]) == 1
    initial_turn = data["turns"][0]
    assert initial_turn["turn_index"] == 0
    assert initial_turn["role"] == "assistant"
    assert "75000.00" in initial_turn["content"]
    assert "Govt Clearance Escrow" in initial_turn["content"]


@pytest.mark.asyncio
async def test_initiate_call_session_idempotent(client: AsyncClient) -> None:
    """Replaying initiation with the same idempotency key returns HTTP 200 and existing session."""
    tx_id = await _create_test_transaction(client)
    idemp_key = f"key_{uuid.uuid4().hex[:8]}"

    res1 = await client.post(
        f"/api/v1/transactions/{tx_id}/calls",
        json={"channel": "VOICE_SIMULATED", "idempotency_key": idemp_key},
    )
    assert res1.status_code == 201
    call_id = res1.json()["id"]

    res2 = await client.post(
        f"/api/v1/transactions/{tx_id}/calls",
        json={"channel": "VOICE_SIMULATED", "idempotency_key": idemp_key},
    )
    assert res2.status_code == 200
    assert res2.json()["id"] == call_id


@pytest.mark.asyncio
async def test_initiate_call_active_session_guard(client: AsyncClient) -> None:
    """If an active session already exists, new initiation returns the active session."""
    tx_id = await _create_test_transaction(client)

    res1 = await client.post(
        f"/api/v1/transactions/{tx_id}/calls",
        json={"channel": "VOICE_SIMULATED"},
    )
    assert res1.status_code == 201
    call_id = res1.json()["id"]

    res2 = await client.post(
        f"/api/v1/transactions/{tx_id}/calls",
        json={"channel": "VOICE_SIMULATED"},
    )
    assert res2.status_code == 200
    assert res2.json()["id"] == call_id


@pytest.mark.asyncio
async def test_initiate_call_terminal_transaction_rejected(client: AsyncClient) -> None:
    """Cannot initiate a call for a transaction in terminal settled/cancelled state."""
    tx_id = await _create_test_transaction(client)

    # Transition to assessing -> risk_assessed -> decision_ready -> cancelled
    t1 = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={"target_state": "ASSESSING", "actor_type": "SYSTEM", "reason": "test"},
    )
    assert t1.status_code == 200
    t2 = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={"target_state": "RISK_ASSESSED", "actor_type": "SYSTEM", "reason": "test"},
    )
    assert t2.status_code == 200
    t3 = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={"target_state": "DECISION_READY", "actor_type": "SYSTEM", "reason": "test"},
    )
    assert t3.status_code == 200
    t4 = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={
            "target_state": "CANCELLED_SIMULATED",
            "actor_type": "SYSTEM",
            "reason": "test cancel",
        },
    )
    assert t4.status_code == 200

    res = await client.post(
        f"/api/v1/transactions/{tx_id}/calls",
        json={"channel": "VOICE_SIMULATED"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_connect_call_session(client: AsyncClient) -> None:
    """Connecting transitions session from RINGING to CONNECTED and records timestamp."""
    tx_id = await _create_test_transaction(client)
    init_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    call_id = init_res.json()["id"]

    res = await client.post(f"/api/v1/calls/{call_id}/connect")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == CallSessionStatus.CONNECTED.value
    assert data["connected_at"] is not None

    # Idempotent connect
    res_repeat = await client.post(f"/api/v1/calls/{call_id}/connect")
    assert res_repeat.status_code == 200
    assert res_repeat.json()["status"] == CallSessionStatus.CONNECTED.value


@pytest.mark.asyncio
async def test_submit_turn_flow(client: AsyncClient) -> None:
    """Customer answers verbally; Gemini generates evidence-grounded next question."""
    tx_id = await _create_test_transaction(client)
    init_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    call_id = init_res.json()["id"]

    # Connect call
    await client.post(f"/api/v1/calls/{call_id}/connect")

    # Submit turn 1
    turn_res = await client.post(
        f"/api/v1/calls/{call_id}/turns",
        json={
            "customer_message": (
                "A customs officer contacted me saying my package has illegal substances."
            ),
            "source": "speech",
            "client_turn_id": "turn_token_1",
        },
    )
    assert turn_res.status_code == 200
    data = turn_res.json()
    assert len(data["turns"]) == 3  # Initial assistant + customer turn 1 + assistant turn 2

    cust_turn = data["turns"][1]
    assert cust_turn["role"] == "customer"
    assert "customs officer" in cust_turn["content"]

    asst_turn = data["turns"][2]
    assert asst_turn["role"] == "assistant"
    assert asst_turn["risk_sentiment"] == "COERCED"
    assert "confidential" in asst_turn["content"] or "legal" in asst_turn["content"]


@pytest.mark.asyncio
async def test_submit_turn_idempotency(client: AsyncClient) -> None:
    """Repeated turn submission with same client_turn_id returns existing state."""
    tx_id = await _create_test_transaction(client)
    init_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    call_id = init_res.json()["id"]
    await client.post(f"/api/v1/calls/{call_id}/connect")

    token = "unique_client_token_123"
    payload = {
        "customer_message": "This is for office rent payment.",
        "source": "typed",
        "client_turn_id": token,
    }

    res1 = await client.post(f"/api/v1/calls/{call_id}/turns", json=payload)
    assert res1.status_code == 200
    turn_count_1 = len(res1.json()["turns"])

    res2 = await client.post(f"/api/v1/calls/{call_id}/turns", json=payload)
    assert res2.status_code == 200
    assert len(res2.json()["turns"]) == turn_count_1


@pytest.mark.asyncio
async def test_duress_leads_to_terminal_turn_and_coercion_analysis(client: AsyncClient) -> None:
    """Urgent safe-account directive confirmation completes call and triggers coercion analysis."""
    tx_id = await _create_test_transaction(client)
    init_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    call_id = init_res.json()["id"]
    await client.post(f"/api/v1/calls/{call_id}/connect")

    turn_res = await client.post(
        f"/api/v1/calls/{call_id}/turns",
        json={
            "customer_message": (
                "CBI officer Sharma told me to move money to a safe account "
                "urgently and not tell anyone."
            ),
            "source": "speech",
        },
    )
    assert turn_res.status_code == 200
    data = turn_res.json()
    assert data["status"] == CallSessionStatus.COMPLETED.value
    assert data["ended_at"] is not None
    assert data["duration_seconds"] >= 0
    assert data["coercion_analysis_id"] is not None


@pytest.mark.asyncio
async def test_decline_call_session(client: AsyncClient) -> None:
    """Customer declines call, transitioning it to DECLINED."""
    tx_id = await _create_test_transaction(client)
    init_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    call_id = init_res.json()["id"]

    res = await client.post(
        f"/api/v1/calls/{call_id}/decline",
        json={"reason": "Customer busy"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == CallSessionStatus.DECLINED.value
    assert data["failure_reason"] == "Customer busy"


@pytest.mark.asyncio
async def test_chat_simulated_channel(client: AsyncClient) -> None:
    """Initiating with CHAT_SIMULATED sets channel accordingly."""
    tx_id = await _create_test_transaction(client)
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/calls",
        json={"channel": "CHAT_SIMULATED"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["channel"] == DialogueChannel.CHAT_SIMULATED.value


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected(unauth_client: AsyncClient) -> None:
    """Unauthenticated requests without valid operator/customer token return HTTP 401."""
    random_id = uuid.uuid4()
    res = await unauth_client.post(
        f"/api/v1/transactions/{random_id}/calls",
        json={"channel": "VOICE_SIMULATED"},
    )
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Regression tests for P2-A10 reliability audit fixes
# ---------------------------------------------------------------------------


@pytest.fixture
async def failing_client() -> AsyncGenerator[AsyncClient, None]:
    """Operator-authenticated client whose AI provider always fails.

    Exercises the recoverable-failure path for initial dialogue generation.
    """
    import uuid as _uuid

    from app.api.auth import get_current_operator
    from app.api.customer_dialogue import (
        get_current_operator_optional as dialogue_operator_optional,
    )
    from app.api.investigations import get_default_ai_client
    from app.core.config import get_settings
    from app.db.models import OperatorModel
    from app.db.session import get_db_session
    from app.main import create_app
    from app.services.ai_client import MockGeminiClient
    from tests.conftest import get_test_session_factory, get_test_settings

    app = create_app()

    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        session_factory = get_test_session_factory()
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    stub_operator = OperatorModel(
        id=_uuid.uuid4(), username="test_operator", password_hash="unused", is_active=True
    )
    app.dependency_overrides[get_settings] = get_test_settings
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_default_ai_client] = lambda: MockGeminiClient(should_fail=True)
    app.dependency_overrides[get_current_operator] = lambda: stub_operator
    app.dependency_overrides[dialogue_operator_optional] = lambda: stub_operator

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_complete_cannot_resurrect_declined_session(client: AsyncClient) -> None:
    """Completing a DECLINED session must fail, never flip it to COMPLETED (A1)."""
    tx_id = await _create_test_transaction(client)
    init_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    call_id = init_res.json()["id"]

    decline_res = await client.post(f"/api/v1/calls/{call_id}/decline", json={})
    assert decline_res.status_code == 200
    assert decline_res.json()["status"] == CallSessionStatus.DECLINED.value

    complete_res = await client.post(f"/api/v1/calls/{call_id}/complete")
    assert complete_res.status_code == 409

    # The session remains DECLINED — the terminal state was not overwritten.
    get_res = await client.get(f"/api/v1/calls/{call_id}")
    assert get_res.json()["status"] == CallSessionStatus.DECLINED.value


@pytest.mark.asyncio
async def test_initiation_ai_failure_marks_failed_and_allows_retry(
    failing_client: AsyncClient, client: AsyncClient
) -> None:
    """A failed initial Gemini call leaves a terminal FAILED session, not an active one (A2)."""
    tx_id = await _create_test_transaction(client)

    res = await failing_client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    # The AI failure surfaces as a provider error, not a silent success.
    assert res.status_code >= 500

    # The failed session is terminal (FAILED), so it does not block a fresh attempt:
    # a subsequent successful initiation (working AI client) creates a new session.
    retry_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    assert retry_res.status_code == 201
    data = retry_res.json()
    assert data["status"] == CallSessionStatus.RINGING.value
    assert len(data["turns"]) == 1

    # Exactly one FAILED session plus the new RINGING one are recorded.
    all_sessions = await client.get(f"/api/v1/transactions/{tx_id}/calls")
    statuses = sorted(s["status"] for s in all_sessions.json())
    assert statuses == [CallSessionStatus.FAILED.value, CallSessionStatus.RINGING.value]


@pytest.mark.asyncio
async def test_active_session_unique_constraint(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The DB enforces at most one active session per transaction (B1)."""
    tx_id = await _create_test_transaction(client)
    tx_uuid = uuid.UUID(tx_id)

    first = TransactionCallSessionModel(
        id=uuid.uuid4(),
        transaction_id=tx_uuid,
        channel=DialogueChannel.VOICE_SIMULATED.value,
        status=CallSessionStatus.RINGING.value,
        direction="OUTBOUND_SIMULATED",
        attempt_number=1,
        customer_phone_masked="masked",
        version=1,
    )
    db_session.add(first)
    await db_session.commit()

    second = TransactionCallSessionModel(
        id=uuid.uuid4(),
        transaction_id=tx_uuid,
        channel=DialogueChannel.VOICE_SIMULATED.value,
        status=CallSessionStatus.CONNECTED.value,
        direction="OUTBOUND_SIMULATED",
        attempt_number=2,
        customer_phone_masked="masked",
        version=1,
    )
    db_session.add(second)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_duplicate_turn_index_returns_conflict(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A racing turn at an already-used index is a safe 409, not an unhandled 500 (B2)."""
    tx_id = await _create_test_transaction(client)
    init_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    call_id = init_res.json()["id"]
    conv_id = uuid.UUID(init_res.json()["conversation_id"])
    await client.post(f"/api/v1/calls/{call_id}/connect")

    # Simulate a concurrent writer that already claimed the next turn index. After
    # connect there is one turn (index 0); the service will compute the new customer
    # turn index from the turn count, so squatting that index forces the conflict.
    squatter = InvestigationConversationTurnModel(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        turn_index=2,
        role=ConversationRole.CUSTOMER.value,
        content="racing turn",
        evidence_provenance=EvidenceProvenance.CUSTOMER_STATEMENT.value,
    )
    db_session.add(squatter)
    await db_session.commit()

    res = await client.post(
        f"/api/v1/calls/{call_id}/turns",
        json={"customer_message": "This is for office rent payment."},
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_coercion_evidence_before_final_turn_triggers_analysis(client: AsyncClient) -> None:
    """Coercion raised in an earlier turn still triggers analysis at completion (C1/C2).

    The first customer turn surfaces coercion cues but is not terminal; a later
    benign turn ends the call. Accumulated-evidence analysis must still run.
    """
    tx_id = await _create_test_transaction(client)
    init_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    call_id = init_res.json()["id"]
    await client.post(f"/api/v1/calls/{call_id}/connect")

    # Turn 1: authority mention WITHOUT urgency/safe-account -> COERCED but not terminal.
    t1 = await client.post(
        f"/api/v1/calls/{call_id}/turns",
        json={"customer_message": "A police officer called me about a case."},
    )
    assert t1.status_code == 200
    assert t1.json()["status"] == CallSessionStatus.CONNECTED.value

    # Manually complete the call; accumulated coercion evidence must drive analysis.
    done = await client.post(f"/api/v1/calls/{call_id}/complete")
    assert done.status_code == 200
    data = done.json()
    assert data["status"] == CallSessionStatus.COMPLETED.value
    assert data["coercion_analysis_id"] is not None


@pytest.mark.asyncio
async def test_turn_idempotent_replay_returns_same_assistant(client: AsyncClient) -> None:
    """Replaying a client_turn_id does not append new turns (idempotent)."""
    tx_id = await _create_test_transaction(client)
    init_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    call_id = init_res.json()["id"]
    await client.post(f"/api/v1/calls/{call_id}/connect")

    payload = {
        "customer_message": "This is for office rent payment.",
        "client_turn_id": "tok-abc",
    }
    first = await client.post(f"/api/v1/calls/{call_id}/turns", json=payload)
    assert first.status_code == 200
    first_turns = first.json()["turns"]

    replay = await client.post(f"/api/v1/calls/{call_id}/turns", json=payload)
    assert replay.status_code == 200
    assert len(replay.json()["turns"]) == len(first_turns)


@pytest.mark.asyncio
async def test_customer_token_cannot_access_other_transaction(
    client: AsyncClient, unauth_client: AsyncClient
) -> None:
    """A customer token bound to tx A cannot drive tx B's call session (D2)."""
    tx_a = await _create_test_transaction(client)
    tx_b = await _create_test_transaction(client)
    init_b = await client.post(f"/api/v1/transactions/{tx_b}/calls", json={})
    call_b = init_b.json()["id"]

    token_a = _customer_token(tx_a)
    headers = {"Authorization": f"Bearer {token_a}"}

    # Reading tx B's session with tx A's token is forbidden.
    res = await unauth_client.get(f"/api/v1/calls/{call_b}", headers=headers)
    assert res.status_code == 403

    # The transaction-scoped listing for tx B is also forbidden.
    res_list = await unauth_client.get(f"/api/v1/transactions/{tx_b}/calls", headers=headers)
    assert res_list.status_code == 403


@pytest.mark.asyncio
async def test_customer_token_internal_fields_redacted(
    client: AsyncClient, unauth_client: AsyncClient
) -> None:
    """Customer sessions never receive internal forensic fields (D1)."""
    tx_id = await _create_test_transaction(client)
    init_res = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    call_id = init_res.json()["id"]

    # Operator sees internal observations on the opening assistant turn.
    op_turn = init_res.json()["turns"][0]
    assert op_turn["internal_observations"]

    token = _customer_token(tx_id)
    headers = {"Authorization": f"Bearer {token}"}
    cust_res = await unauth_client.get(f"/api/v1/calls/{call_id}", headers=headers)
    assert cust_res.status_code == 200
    cust_turn = cust_res.json()["turns"][0]
    assert cust_turn["internal_observations"] == []
    assert cust_turn["uncertainty_notes"] == []
    assert cust_turn["coercion_cues"] == []
    assert cust_turn["suggested_action"] is None
    assert cust_turn["risk_sentiment"] is None
    # The customer still sees the conversational content addressed to them.
    assert cust_turn["content"] == op_turn["content"]
