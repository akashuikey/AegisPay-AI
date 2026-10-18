"""Integration tests for the live-voice WebSocket endpoint (P2-A11).

The endpoint is driven directly with an async fake WebSocket so the real
authentication, transaction-scope, lifecycle validation, concurrency guard, and
orchestration run in-process and deterministically (no Starlette sync TestClient,
avoiding event-loop pitfalls with the async test database).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api import live_voice
from app.core.security import create_access_token, create_customer_verification_token
from app.db.models import OperatorModel, TransactionCallSessionModel, TransactionModel
from app.domain.customer_dialogue import CallSessionStatus
from app.repositories.transaction_repository import TransactionRepository
from app.services.live_voice_client import (
    LiveVoiceEvent,
    LiveVoiceEventType,
    MockLiveVoiceClient,
)
from tests.conftest import get_test_session_factory, get_test_settings


def _live_settings(enabled: bool = True):
    return get_test_settings().model_copy(
        update={
            "GEMINI_LIVE_ENABLED": enabled,
            "GEMINI_API_KEY": "test-key" if enabled else None,
            "GEMINI_LIVE_ANALYSIS_INTERVAL_SECONDS": 0.2,
            "GEMINI_LIVE_ANALYSIS_MIN_NEW_SEGMENTS": 1,
            "GEMINI_LIVE_MAX_SESSION_SECONDS": 30,
        }
    )


class FakeWebSocket:
    """Async fake WebSocket backed by an inbound queue; records outbound frames."""

    def __init__(self) -> None:
        self.accepted = False
        self.closed_code: int | None = None
        self.sent_json: list[dict] = []
        self.sent_bytes: list[bytes] = []
        self._inbound: asyncio.Queue[dict] = asyncio.Queue()

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000) -> None:
        if self.closed_code is None:
            self.closed_code = code

    async def send_json(self, data: dict) -> None:
        self.sent_json.append(data)

    async def send_bytes(self, data: bytes) -> None:
        self.sent_bytes.append(data)

    async def receive(self) -> dict:
        return await self._inbound.get()

    def feed_audio(self, data: bytes) -> None:
        self._inbound.put_nowait({"type": "websocket.receive", "bytes": data})

    def feed_control(self, control: dict) -> None:
        self._inbound.put_nowait({"type": "websocket.receive", "text": json.dumps(control)})

    def disconnect(self) -> None:
        self._inbound.put_nowait({"type": "websocket.disconnect"})


async def _wait_for(check: Callable[[], Awaitable[bool]], timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await check():
            return True
        await asyncio.sleep(0.02)
    return False


async def _seed(
    factory: async_sessionmaker[AsyncSession],
    *,
    tx_state: str = "INITIATED",
    call_status: str = CallSessionStatus.CONNECTED.value,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a transaction and a call session; return (call_id, transaction_id)."""
    tx_id = uuid.uuid4()
    call_id = uuid.uuid4()
    async with factory() as db:
        db.add(
            TransactionModel(
                id=tx_id,
                customer_id=f"CU-{uuid.uuid4().hex[:6]}",
                idempotency_key=uuid.uuid4().hex,
                payload_hash="hash",
                amount=Decimal("90000.00"),
                currency="INR",
                payment_rail="IMPS",
                recipient_name="Govt Clearance Escrow",
                recipient_identifier="govt.clearance@sbi",
                purpose="Verification deposit",
                state=tx_state,
                version=1,
            )
        )
        db.add(
            TransactionCallSessionModel(
                id=call_id,
                transaction_id=tx_id,
                channel="VOICE_SIMULATED",
                status=call_status,
                direction="OUTBOUND_SIMULATED",
                attempt_number=1,
                customer_phone_masked="masked",
                version=1,
            )
        )
        await db.commit()
    return call_id, tx_id


async def _operator_token(factory: async_sessionmaker[AsyncSession], settings) -> str:
    op_id = uuid.uuid4()
    async with factory() as db:
        db.add(
            OperatorModel(
                id=op_id, username=f"op_{op_id.hex[:6]}", password_hash="x", is_active=True
            )
        )
        await db.commit()
    token, _ = create_access_token(str(op_id), settings)
    return token


async def _call_endpoint(
    ws: FakeWebSocket, call_id: uuid.UUID, token: str | None, settings, provider
):
    await live_voice.live_voice_ws(
        websocket=ws,
        call_id=call_id,
        provider=provider,
        worker_factory=get_test_session_factory(),
        settings=settings,
        token=token,
    )


@pytest.mark.asyncio
async def test_ws_rejected_when_live_disabled() -> None:
    factory = get_test_session_factory()
    settings = _live_settings(enabled=False)
    call_id, _ = await _seed(factory)
    ws = FakeWebSocket()
    await _call_endpoint(
        ws, call_id, token="irrelevant", settings=settings, provider=MockLiveVoiceClient()
    )
    assert ws.accepted is False
    assert ws.closed_code == live_voice._WS_UNAVAILABLE


@pytest.mark.asyncio
async def test_ws_rejected_without_token() -> None:
    factory = get_test_session_factory()
    settings = _live_settings()
    call_id, _ = await _seed(factory)
    ws = FakeWebSocket()
    await _call_endpoint(ws, call_id, token=None, settings=settings, provider=MockLiveVoiceClient())
    assert ws.accepted is False
    assert ws.closed_code == live_voice._WS_UNAUTHENTICATED


@pytest.mark.asyncio
async def test_ws_rejected_for_unknown_call() -> None:
    factory = get_test_session_factory()
    settings = _live_settings()
    token = await _operator_token(factory, settings)
    ws = FakeWebSocket()
    await _call_endpoint(
        ws, uuid.uuid4(), token=token, settings=settings, provider=MockLiveVoiceClient()
    )
    assert ws.closed_code == live_voice._WS_UNAVAILABLE


@pytest.mark.asyncio
async def test_ws_customer_cross_transaction_denied() -> None:
    factory = get_test_session_factory()
    settings = _live_settings()
    call_id, _ = await _seed(factory)
    other_tx = uuid.uuid4()
    token, _ = create_customer_verification_token(
        challenge_id=str(uuid.uuid4()),
        transaction_id=str(other_tx),
        customer_id="CU-999",
        settings=settings,
    )
    ws = FakeWebSocket()
    await _call_endpoint(
        ws, call_id, token=token, settings=settings, provider=MockLiveVoiceClient()
    )
    assert ws.accepted is False
    assert ws.closed_code == live_voice._WS_FORBIDDEN


@pytest.mark.asyncio
async def test_ws_rejected_for_terminal_call() -> None:
    factory = get_test_session_factory()
    settings = _live_settings()
    token = await _operator_token(factory, settings)
    call_id, _ = await _seed(factory, call_status=CallSessionStatus.COMPLETED.value)
    ws = FakeWebSocket()
    await _call_endpoint(
        ws, call_id, token=token, settings=settings, provider=MockLiveVoiceClient()
    )
    assert ws.closed_code == live_voice._WS_CONFLICT


@pytest.mark.asyncio
async def test_ws_operator_streams_and_persists_transcript() -> None:
    factory = get_test_session_factory()
    settings = _live_settings()
    token = await _operator_token(factory, settings)
    call_id, _ = await _seed(factory)

    provider = MockLiveVoiceClient(
        script=[
            LiveVoiceEvent(
                type=LiveVoiceEventType.INPUT_TRANSCRIPT,
                text="A police officer told me to move money to a safe account.",
                finished=True,
            ),
            LiveVoiceEvent(
                type=LiveVoiceEventType.OUTPUT_TRANSCRIPT,
                text="Thanks for sharing. Who asked you to do that?",
                finished=True,
            ),
            LiveVoiceEvent(type=LiveVoiceEventType.AUDIO, audio=b"\x01\x02\x03"),
        ]
    )
    ws = FakeWebSocket()
    task = asyncio.create_task(
        _call_endpoint(ws, call_id, token=token, settings=settings, provider=provider)
    )

    async def _persisted() -> bool:
        async with factory() as db:
            repo = TransactionRepository(db)
            return len(await repo.list_transcript_segments(call_id)) >= 2

    assert await _wait_for(_persisted), "scripted transcripts were not persisted"
    ws.feed_control({"type": "end"})
    await asyncio.wait_for(task, timeout=5)

    # Outbound included a session lifecycle and relayed model audio.
    types_sent = {e.get("type") for e in ws.sent_json}
    assert "session_started" in types_sent
    assert "transcript_final" in types_sent
    assert "session_closed" in types_sent
    assert ws.sent_bytes  # model audio relayed
    assert provider.sessions[-1].closed is True

    async with factory() as db:
        repo = TransactionRepository(db)
        segs = await repo.list_transcript_segments(call_id)
        assert [s.seq for s in segs] == sorted(s.seq for s in segs)
        analysis = await repo.get_latest_live_analysis(call_id)
        assert analysis is not None  # analysis ran during/after streaming


@pytest.mark.asyncio
async def test_ws_single_session_per_call_conflict() -> None:
    factory = get_test_session_factory()
    settings = _live_settings()
    token = await _operator_token(factory, settings)
    call_id, _ = await _seed(factory)

    provider = MockLiveVoiceClient()
    ws1 = FakeWebSocket()
    task1 = asyncio.create_task(
        _call_endpoint(ws1, call_id, token=token, settings=settings, provider=provider)
    )
    assert await _wait_for(lambda: _started(ws1))

    # A second connection for the same call is rejected while the first is active.
    ws2 = FakeWebSocket()
    await _call_endpoint(
        ws2, call_id, token=token, settings=settings, provider=MockLiveVoiceClient()
    )
    assert ws2.closed_code == live_voice._WS_CONFLICT

    ws1.feed_control({"type": "end"})
    await asyncio.wait_for(task1, timeout=5)


async def _started(ws: FakeWebSocket) -> bool:
    return any(e.get("type") == "session_started" for e in ws.sent_json)
