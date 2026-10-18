"""Integration tests for the live-voice orchestrator (P2-A11).

Drives the orchestrator with a deterministic mock Live provider and an in-memory
browser transport against the real test database, verifying audio forwarding,
transcript persistence, partial/final dedup and ordering, parallel analysis
(including analysis failure isolation), termination/cleanup, and seq resumption.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.services.live_voice_analysis import LiveEvidenceAnalyzer
from app.services.live_voice_client import (
    LiveVoiceEvent,
    LiveVoiceEventType,
    MockLiveVoiceClient,
    MockLiveVoiceSession,
)
from app.services.live_voice_service import (
    BrowserTransport,
    InboundMessage,
    LiveVoiceOrchestrator,
)
from tests.conftest import get_test_session_factory, get_test_settings


class QueueTransport(BrowserTransport):
    """In-memory browser transport: records outbound, feeds inbound from a queue."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.audio_out: list[bytes] = []
        self._inbound: asyncio.Queue[InboundMessage | None] = asyncio.Queue()

    async def send_event(self, event: dict) -> None:
        self.events.append(event)

    async def send_audio(self, data: bytes) -> None:
        self.audio_out.append(data)

    def feed(self, message: InboundMessage) -> None:
        self._inbound.put_nowait(message)

    def end(self) -> None:
        self._inbound.put_nowait(InboundMessage(kind="control", control={"type": "end"}))

    async def receive(self) -> AsyncIterator[InboundMessage]:
        while True:
            msg = await self._inbound.get()
            if msg is None:
                return
            yield msg


def _live_settings(**overrides: object) -> Settings:
    base = get_test_settings()
    return base.model_copy(
        update={
            "GEMINI_LIVE_ANALYSIS_INTERVAL_SECONDS": 0.2,
            "GEMINI_LIVE_ANALYSIS_MIN_NEW_SEGMENTS": 1,
            "GEMINI_LIVE_MAX_SESSION_SECONDS": 30,
            **overrides,
        }
    )


async def _wait_for(check: Callable[[], Awaitable[bool]], timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await check():
            return True
        await asyncio.sleep(0.02)
    return False


async def _wait_session(provider: MockLiveVoiceClient) -> MockLiveVoiceSession:
    assert await _wait_for(lambda: _truthy(len(provider.sessions) > 0))
    return provider.sessions[-1]


async def _truthy(value: bool) -> bool:
    return value


async def _segment_count(call_id: uuid.UUID) -> int:
    from app.repositories.transaction_repository import TransactionRepository

    factory = get_test_session_factory()
    async with factory() as db:
        repo = TransactionRepository(db)
        return len(await repo.list_transcript_segments(call_id))


async def _segments(call_id: uuid.UUID) -> list:
    from app.repositories.transaction_repository import TransactionRepository

    factory = get_test_session_factory()
    async with factory() as db:
        repo = TransactionRepository(db)
        return await repo.list_transcript_segments(call_id)


async def _latest_analysis(call_id: uuid.UUID) -> object:
    from app.repositories.transaction_repository import TransactionRepository

    factory = get_test_session_factory()
    async with factory() as db:
        repo = TransactionRepository(db)
        return await repo.get_latest_live_analysis(call_id)


async def _setup_call(client: AsyncClient) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a transaction + connected call session; return (call_id, tx_id, conv_id)."""
    tx_payload = {
        "customer_id": f"cust_{uuid.uuid4().hex[:8]}",
        "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
        "amount": "90000.00",
        "currency": "INR",
        "payment_rail": "IMPS",
        "recipient_name": "Govt Clearance Escrow",
        "recipient_identifier": "govt.clearance@sbi",
        "purpose": "Verification deposit",
    }
    res = await client.post("/api/v1/transactions", json=tx_payload)
    assert res.status_code == 201
    tx_id = res.json()["id"]
    init = await client.post(f"/api/v1/transactions/{tx_id}/calls", json={})
    assert init.status_code == 201
    data = init.json()
    return uuid.UUID(data["id"]), uuid.UUID(tx_id), uuid.UUID(data["conversation_id"])


def _make_orchestrator(
    provider: MockLiveVoiceClient,
    transport: QueueTransport,
    call_id: uuid.UUID,
    tx_id: uuid.UUID,
    conv_id: uuid.UUID,
    *,
    analyzer: LiveEvidenceAnalyzer | None = None,
    settings: Settings | None = None,
) -> LiveVoiceOrchestrator:
    return LiveVoiceOrchestrator(
        provider=provider,
        transport=transport,
        session_factory=get_test_session_factory(),
        settings=settings or _live_settings(),
        call_id=call_id,
        transaction_id=tx_id,
        conversation_id=conv_id,
        context={"transaction": {"amount": "90000.00", "recipient_name": "Govt Clearance Escrow"}},
        analyzer=analyzer,
    )


@pytest.mark.asyncio
async def test_forwards_audio_and_persists_final_transcripts(client: AsyncClient) -> None:
    call_id, tx_id, conv_id = await _setup_call(client)
    provider = MockLiveVoiceClient()
    transport = QueueTransport()
    orch = _make_orchestrator(provider, transport, call_id, tx_id, conv_id)

    run_task = asyncio.create_task(orch.run())
    session = await _wait_session(provider)

    # Browser audio is forwarded to the provider.
    transport.feed(InboundMessage(kind="audio", audio=b"\x01\x02\x03\x04"))
    assert await _wait_for(lambda: _truthy(len(session.sent_audio) >= 1))

    # Provider emits transcription + audio; final segments are persisted in order.
    session.push(
        LiveVoiceEvent(type=LiveVoiceEventType.INPUT_TRANSCRIPT, text="Hello there", finished=True)
    )
    session.push(
        LiveVoiceEvent(
            type=LiveVoiceEventType.OUTPUT_TRANSCRIPT,
            text="Hi, I'm checking a payment.",
            finished=True,
        )
    )
    session.push(LiveVoiceEvent(type=LiveVoiceEventType.AUDIO, audio=b"\x10\x11"))

    assert await _wait_for(lambda: _gte(call_id, 2))

    transport.end()
    await asyncio.wait_for(run_task, timeout=5)

    segs = await _segments(call_id)
    assert [s.seq for s in segs] == sorted(s.seq for s in segs)  # monotonic
    assert segs[0].seq == 0
    speakers = [s.speaker for s in segs]
    assert "customer" in speakers and "assistant" in speakers
    assert transport.audio_out  # model audio relayed to browser
    assert any(e.get("type") == "session_closed" for e in transport.events)


async def _gte(call_id: uuid.UUID, n: int) -> bool:
    return (await _segment_count(call_id)) >= n


@pytest.mark.asyncio
async def test_interim_partials_not_persisted_and_duplicates_deduped(client: AsyncClient) -> None:
    call_id, tx_id, conv_id = await _setup_call(client)
    provider = MockLiveVoiceClient()
    transport = QueueTransport()
    orch = _make_orchestrator(provider, transport, call_id, tx_id, conv_id)
    run_task = asyncio.create_task(orch.run())
    session = await _wait_session(provider)

    # Interim (not finished) must not persist.
    session.push(
        LiveVoiceEvent(type=LiveVoiceEventType.INPUT_TRANSCRIPT, text="part one ", finished=False)
    )
    session.push(
        LiveVoiceEvent(type=LiveVoiceEventType.INPUT_TRANSCRIPT, text="part two", finished=True)
    )
    # Duplicate identical final for the same speaker is deduped.
    session.push(
        LiveVoiceEvent(type=LiveVoiceEventType.OUTPUT_TRANSCRIPT, text="same reply", finished=True)
    )
    session.push(
        LiveVoiceEvent(type=LiveVoiceEventType.OUTPUT_TRANSCRIPT, text="same reply", finished=True)
    )
    assert await _wait_for(lambda: _gte(call_id, 2))
    await asyncio.sleep(0.2)
    transport.end()
    await asyncio.wait_for(run_task, timeout=5)

    segs = await _segments(call_id)
    contents = [s.content for s in segs]
    customer_contents = [s.content for s in segs if s.speaker == "customer"]
    # Interim delta + final collapse into ONE persisted customer segment.
    assert customer_contents == ["part one part two"]
    assert contents.count("same reply") == 1  # duplicate final deduped


@pytest.mark.asyncio
async def test_analysis_runs_in_parallel_with_streaming(client: AsyncClient) -> None:
    call_id, tx_id, conv_id = await _setup_call(client)
    provider = MockLiveVoiceClient()
    transport = QueueTransport()
    orch = _make_orchestrator(provider, transport, call_id, tx_id, conv_id)
    run_task = asyncio.create_task(orch.run())
    session = await _wait_session(provider)

    session.push(
        LiveVoiceEvent(
            type=LiveVoiceEventType.INPUT_TRANSCRIPT,
            text="A police officer told me to move money to a safe account and keep it secret.",
            finished=True,
        )
    )
    # Analysis should run while the session is still open (before we end it).
    assert await _wait_for(lambda: _analysis_present(call_id), timeout=5), (
        "analysis snapshot not produced during streaming"
    )
    analysis = await _latest_analysis(call_id)
    assert analysis is not None
    assert any(e.get("type") == "analysis_update" for e in transport.events)

    transport.end()
    await asyncio.wait_for(run_task, timeout=5)


async def _analysis_present(call_id: uuid.UUID) -> bool:
    return (await _latest_analysis(call_id)) is not None


@pytest.mark.asyncio
async def test_analysis_failure_does_not_block_voice(client: AsyncClient) -> None:
    class ExplodingAnalyzer(LiveEvidenceAnalyzer):
        def analyze(self, segments, context=None):
            raise RuntimeError("analysis boom")

    call_id, tx_id, conv_id = await _setup_call(client)
    provider = MockLiveVoiceClient()
    transport = QueueTransport()
    orch = _make_orchestrator(
        provider, transport, call_id, tx_id, conv_id, analyzer=ExplodingAnalyzer()
    )
    run_task = asyncio.create_task(orch.run())
    session = await _wait_session(provider)

    session.push(
        LiveVoiceEvent(
            type=LiveVoiceEventType.INPUT_TRANSCRIPT, text="Just a payment", finished=True
        )
    )
    session.push(LiveVoiceEvent(type=LiveVoiceEventType.AUDIO, audio=b"\x20\x21"))

    # Voice path keeps working: segment persists and audio relays despite analysis errors.
    assert await _wait_for(lambda: _gte(call_id, 1))
    assert await _wait_for(lambda: _truthy(len(transport.audio_out) >= 1))
    assert await _wait_for(
        lambda: _truthy(
            any(
                e.get("type") == "analysis_update" and e.get("status") == "unavailable"
                for e in transport.events
            )
        )
    )
    transport.end()
    await asyncio.wait_for(run_task, timeout=5)


async def _call_status(call_id: uuid.UUID) -> str | None:
    from app.repositories.transaction_repository import TransactionRepository

    factory = get_test_session_factory()
    async with factory() as db:
        repo = TransactionRepository(db)
        session = await repo.get_call_session_by_id(call_id)
        return session.status if session else None


@pytest.mark.asyncio
async def test_provider_connect_failure_marks_call_failed(client: AsyncClient) -> None:
    """A Gemini Live connect failure surfaces an error event AND persists FAILED.

    The deterministic transaction decision is never touched by the orchestrator;
    only the call-session lifecycle records the connection failure so the operator
    dashboard shows the intervention failed instead of a stuck session.
    """
    call_id, tx_id, conv_id = await _setup_call(client)
    # Capture the transaction state before the failed Live attempt.
    tx_before = await client.get(f"/api/v1/transactions/{tx_id}")
    state_before = tx_before.json()["state"]

    provider = MockLiveVoiceClient(connect_error=RuntimeError("model not found"))
    transport = QueueTransport()
    orch = _make_orchestrator(provider, transport, call_id, tx_id, conv_id)

    await asyncio.wait_for(orch.run(), timeout=5)

    # Error surfaced to the browser with an actionable reason.
    error_events = [e for e in transport.events if e.get("type") == "error"]
    assert error_events and error_events[0].get("reason") == "LIVE_CONNECT_FAILED"
    # session_closed reports failure, not a clean completion.
    closed = [e for e in transport.events if e.get("type") == "session_closed"]
    assert closed and closed[0].get("reason") == "failed"
    # Call session persisted as FAILED with the reason.
    assert await _call_status(call_id) == "FAILED"
    # Transaction state is unchanged by the Live failure.
    tx_after = await client.get(f"/api/v1/transactions/{tx_id}")
    assert tx_after.json()["state"] == state_before


@pytest.mark.asyncio
async def test_connect_failure_never_overwrites_terminal_call(client: AsyncClient) -> None:
    """A connect failure must not resurrect/rewrite an already-terminal call."""
    call_id, tx_id, conv_id = await _setup_call(client)
    # Decline the call first (terminal DECLINED).
    decline = await client.post(f"/api/v1/calls/{call_id}/decline", json={"reason": "no answer"})
    assert decline.status_code == 200

    provider = MockLiveVoiceClient(connect_error=RuntimeError("model not found"))
    transport = QueueTransport()
    orch = _make_orchestrator(provider, transport, call_id, tx_id, conv_id)
    await asyncio.wait_for(orch.run(), timeout=5)

    # Still DECLINED — not overwritten to FAILED.
    assert await _call_status(call_id) == "DECLINED"


@pytest.mark.asyncio
async def test_termination_closes_provider_session(client: AsyncClient) -> None:
    call_id, tx_id, conv_id = await _setup_call(client)
    provider = MockLiveVoiceClient()
    transport = QueueTransport()
    orch = _make_orchestrator(provider, transport, call_id, tx_id, conv_id)
    run_task = asyncio.create_task(orch.run())
    session = await _wait_session(provider)
    transport.end()
    await asyncio.wait_for(run_task, timeout=5)
    assert session.closed is True


@pytest.mark.asyncio
async def test_seq_resumes_across_reconnect_without_duplicates(client: AsyncClient) -> None:
    call_id, tx_id, conv_id = await _setup_call(client)

    # First connection: two final segments (seq 0, 1).
    provider1 = MockLiveVoiceClient()
    transport1 = QueueTransport()
    orch1 = _make_orchestrator(provider1, transport1, call_id, tx_id, conv_id)
    run1 = asyncio.create_task(orch1.run())
    s1 = await _wait_session(provider1)
    s1.push(LiveVoiceEvent(type=LiveVoiceEventType.INPUT_TRANSCRIPT, text="first", finished=True))
    s1.push(
        LiveVoiceEvent(type=LiveVoiceEventType.OUTPUT_TRANSCRIPT, text="reply one", finished=True)
    )
    assert await _wait_for(lambda: _gte(call_id, 2))
    await asyncio.sleep(0.1)
    transport1.end()
    await asyncio.wait_for(run1, timeout=5)

    # Reconnect: new segment must continue the sequence at 2 (no restart, no dup).
    provider2 = MockLiveVoiceClient()
    transport2 = QueueTransport()
    orch2 = _make_orchestrator(provider2, transport2, call_id, tx_id, conv_id)
    run2 = asyncio.create_task(orch2.run())
    s2 = await _wait_session(provider2)
    s2.push(LiveVoiceEvent(type=LiveVoiceEventType.INPUT_TRANSCRIPT, text="second", finished=True))
    assert await _wait_for(lambda: _gte(call_id, 3))
    transport2.end()
    await asyncio.wait_for(run2, timeout=5)

    segs = await _segments(call_id)
    seqs = [s.seq for s in segs]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))  # no duplicate seq
    assert max(seqs) >= 2
