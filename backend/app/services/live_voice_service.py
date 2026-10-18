"""Real-time live-voice orchestration (P2-A11).

Coordinates a single live voice call: forwarding microphone audio to Gemini Live,
streaming model audio/events back to the browser, persisting final transcript
segments on an independent writer, and running incremental evidence analysis in
parallel — all with bounded queues, explicit backpressure, and deterministic
cleanup.

Design guarantees:
- Audio forwarding and playback are never blocked by slow DB writes or analysis.
- Transcript persistence is the single writer and assigns a monotonic ``seq``;
  duplicates (reconnect/replay) are deduplicated and the DB unique constraint is
  the backstop.
- Analysis runs on its own cadence from persisted segments; it never overlaps
  itself and never mutates transaction state.
- Every task is cancelled and drained on termination; the provider session is closed.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import CallLiveAnalysisModel, CallTranscriptSegmentModel
from app.domain.customer_dialogue import TERMINAL_CALL_STATUSES, CallSessionStatus
from app.domain.live_voice import (
    LIVE_VOICE_SYSTEM_INSTRUCTION,
    LiveAnalysisStatus,
    TranscriptSegmentKind,
    TranscriptSpeaker,
    build_live_session_context_preamble,
)
from app.repositories.transaction_repository import TransactionRepository
from app.services.live_voice_analysis import LiveEvidenceAnalyzer, TranscriptView
from app.services.live_voice_client import (
    LiveVoiceClient,
    LiveVoiceEvent,
    LiveVoiceEventType,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class InboundMessage:
    """A message arriving from the browser transport."""

    kind: str  # "audio" | "control" | "close"
    audio: bytes | None = None
    control: dict[str, Any] | None = None


class BrowserTransport:
    """Duplex transport between the orchestrator and the browser (implemented by the
    WebSocket endpoint; a fake is used in tests)."""

    async def send_event(self, event: dict[str, Any]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def send_audio(self, data: bytes) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def receive(self) -> AsyncIterator[InboundMessage]:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(slots=True)
class _FinalSegment:
    speaker: str
    text: str


@dataclass
class _SessionMetrics:
    first_audio_latency_ms: int | None = None
    audio_chunks_in: int = 0
    audio_chunks_out: int = 0
    segments_persisted: int = 0
    segments_dropped: int = 0
    analyses_run: int = 0
    errors: int = 0


class LiveVoiceOrchestrator:
    """Runs one live voice session end-to-end with bounded, independent tasks."""

    def __init__(
        self,
        *,
        provider: LiveVoiceClient,
        transport: BrowserTransport,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        call_id: UUID,
        transaction_id: UUID,
        conversation_id: UUID | None,
        context: dict[str, Any],
        analyzer: LiveEvidenceAnalyzer | None = None,
    ) -> None:
        self.provider = provider
        self.transport = transport
        self.session_factory = session_factory
        self.settings = settings
        self.call_id = call_id
        self.transaction_id = transaction_id
        self.conversation_id = conversation_id
        self.context = context
        self.analyzer = analyzer or LiveEvidenceAnalyzer()

        self._transcript_queue: asyncio.Queue[_FinalSegment] = asyncio.Queue(
            maxsize=max(1, settings.GEMINI_LIVE_TRANSCRIPT_QUEUE_MAXSIZE)
        )
        self._stop = asyncio.Event()
        self._interim: dict[str, str] = {
            TranscriptSpeaker.CUSTOMER.value: "",
            TranscriptSpeaker.ASSISTANT.value: "",
        }
        self._resumption_handle: str | None = None
        self._metrics = _SessionMetrics()
        self._start_monotonic = time.monotonic()
        self._end_reason = "completed"

    # -- public entrypoint --------------------------------------------------

    async def run(self) -> _SessionMetrics:
        """Open the provider session and drive all tasks until termination."""
        system_instruction = (
            LIVE_VOICE_SYSTEM_INSTRUCTION
            + "\n\n"
            + build_live_session_context_preamble(self.context)
        )
        try:
            async with self.provider.connect(
                system_instruction=system_instruction,
                resumption_handle=self._resumption_handle,
            ) as session:
                await self.transport.send_event(
                    {"type": "session_started", "call_id": str(self.call_id), "simulated": True}
                )
                tasks = [
                    asyncio.create_task(self._ingest_task(session), name="live-ingest"),
                    asyncio.create_task(self._egress_task(session), name="live-egress"),
                    asyncio.create_task(self._persistence_task(), name="live-persist"),
                    asyncio.create_task(self._analysis_task(), name="live-analysis"),
                    asyncio.create_task(self._watchdog_task(), name="live-watchdog"),
                ]
                try:
                    await self._stop.wait()
                finally:
                    await self._shutdown(tasks)
        except Exception as exc:  # noqa: BLE001 - provider/connect boundary
            self._metrics.errors += 1
            self._end_reason = "failed"
            logger.warning("Live session %s failed to run: %s", self.call_id, exc)
            with contextlib.suppress(Exception):
                await self.transport.send_event(
                    {
                        "type": "error",
                        "message": "Live voice session could not be established.",
                        "reason": "LIVE_CONNECT_FAILED",
                    }
                )
            # Persist the lifecycle fact that the call could not connect so the
            # operator dashboard shows the failure instead of a stuck session. This
            # only records a *call-session* status; it never touches transaction
            # state or the deterministic fraud decision (that stays with policy).
            await self._mark_call_failed("LIVE_CONNECT_FAILED")
        await self._finalize()
        return self._metrics

    async def _mark_call_failed(self, reason: str) -> None:
        """Mark the call session FAILED after a provider/connect failure.

        Idempotent and conservative: never overwrites an existing terminal status
        (e.g. a call the customer already declined), and swallows its own errors so
        cleanup can never mask the original failure.
        """
        with contextlib.suppress(Exception):
            async with self.session_factory() as db:
                repo = TransactionRepository(db)
                session = await repo.get_call_session_by_id(self.call_id)
                if session is None or session.status in TERMINAL_CALL_STATUSES:
                    return
                session.status = CallSessionStatus.FAILED.value
                session.failure_reason = reason
                session.ended_at = datetime.now(UTC)
                await repo.update_call_session(session)

    # -- tasks --------------------------------------------------------------

    async def _ingest_task(self, session: Any) -> None:
        """Forward inbound browser audio to the provider; honor control messages."""
        try:
            async for msg in self.transport.receive():
                if msg.kind == "close":
                    self._end_reason = "client_closed"
                    break
                if msg.kind == "control":
                    ctrl = msg.control or {}
                    if ctrl.get("type") == "end":
                        self._end_reason = "ended_by_user"
                        break
                    continue
                if msg.kind == "audio" and msg.audio is not None:
                    if len(msg.audio) > self.settings.GEMINI_LIVE_MAX_AUDIO_FRAME_BYTES:
                        logger.warning(
                            "Dropping oversized audio frame (%d bytes) on call %s",
                            len(msg.audio),
                            self.call_id,
                        )
                        continue
                    self._metrics.audio_chunks_in += 1
                    with contextlib.suppress(Exception):
                        await session.send_audio(msg.audio)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - transport boundary
            logger.info("Live ingest ended for call %s: %s", self.call_id, exc)
        finally:
            self._stop.set()

    async def _egress_task(self, session: Any) -> None:
        """Stream provider events back to the browser and feed the transcript queue."""
        try:
            async for event in session.receive():
                await self._handle_provider_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider boundary
            self._metrics.errors += 1
            logger.info("Live egress ended for call %s: %s", self.call_id, exc)
            with contextlib.suppress(Exception):
                await self.transport.send_event(
                    {"type": "error", "message": "Live audio stream interrupted."}
                )
        finally:
            self._stop.set()

    async def _handle_provider_event(self, event: LiveVoiceEvent) -> None:
        if event.type == LiveVoiceEventType.AUDIO and event.audio is not None:
            if self._metrics.first_audio_latency_ms is None:
                self._metrics.first_audio_latency_ms = int(
                    (time.monotonic() - self._start_monotonic) * 1000
                )
            self._metrics.audio_chunks_out += 1
            await self.transport.send_audio(event.audio)
        elif event.type == LiveVoiceEventType.INPUT_TRANSCRIPT:
            await self._on_transcript(TranscriptSpeaker.CUSTOMER.value, event)
        elif event.type == LiveVoiceEventType.OUTPUT_TRANSCRIPT:
            await self._on_transcript(TranscriptSpeaker.ASSISTANT.value, event)
        elif event.type == LiveVoiceEventType.INTERRUPTED:
            await self.transport.send_event({"type": "interrupted"})
        elif event.type == LiveVoiceEventType.TURN_COMPLETE:
            await self.transport.send_event({"type": "turn_complete"})
        elif event.type == LiveVoiceEventType.GO_AWAY:
            await self.transport.send_event({"type": "go_away", "time_left_ms": event.time_left_ms})
        elif event.type == LiveVoiceEventType.RESUMPTION_UPDATE:
            if event.resumable and event.handle:
                self._resumption_handle = event.handle
        elif event.type == LiveVoiceEventType.ERROR:
            self._metrics.errors += 1
            await self.transport.send_event(
                {"type": "error", "message": "Model reported an error."}
            )

    async def _on_transcript(self, speaker: str, event: LiveVoiceEvent) -> None:
        """Accumulate interim transcription; enqueue a final segment on completion."""
        text = event.text or ""
        # Accumulate raw deltas (provider includes its own spacing); strip only for
        # display and final persistence so inter-delta spacing is preserved.
        self._interim[speaker] = self._interim[speaker] + text
        # Interim partials stream to the UI but are never persisted.
        await self.transport.send_event(
            {
                "type": "transcript_interim",
                "speaker": speaker,
                "text": self._interim[speaker].strip(),
            }
        )
        if event.finished:
            final_text = self._interim[speaker].strip()
            self._interim[speaker] = ""
            if final_text:
                await self._enqueue_final(_FinalSegment(speaker=speaker, text=final_text))

    async def _enqueue_final(self, segment: _FinalSegment) -> None:
        """Hand a finalized segment to the persistence writer with bounded backpressure.

        Audio is never blocked for more than a short bound; if the writer is far
        behind we drop the segment and record it rather than stall playback.
        """
        try:
            await asyncio.wait_for(self._transcript_queue.put(segment), timeout=0.1)
        except (TimeoutError, asyncio.QueueFull):
            self._metrics.segments_dropped += 1
            logger.warning(
                "Transcript queue saturated on call %s; dropping a final segment", self.call_id
            )

    async def _persistence_task(self) -> None:
        """Single writer: assign monotonic seq, dedup, persist final segments."""
        try:
            async with self.session_factory() as db:
                repo = TransactionRepository(db)
                max_seq = await repo.get_max_transcript_seq(self.call_id)
                next_seq = (max_seq + 1) if max_seq is not None else 0
                last_text: dict[str, str] = {}
                while True:
                    segment = await self._transcript_queue.get()
                    # Deduplicate an identical consecutive final for the same speaker.
                    if last_text.get(segment.speaker) == segment.text:
                        continue
                    row = CallTranscriptSegmentModel(
                        id=uuid4(),
                        call_session_id=self.call_id,
                        conversation_id=self.conversation_id,
                        transaction_id=self.transaction_id,
                        speaker=segment.speaker,
                        seq=next_seq,
                        kind=TranscriptSegmentKind.FINAL.value,
                        content=segment.text,
                    )
                    try:
                        await repo.create_transcript_segment(row)
                    except IntegrityError:
                        # Duplicate (call_session_id, seq) from a reconnect/race: skip.
                        logger.info(
                            "Skipping duplicate transcript seq=%d on call %s",
                            next_seq,
                            self.call_id,
                        )
                        continue
                    last_text[segment.speaker] = segment.text
                    self._metrics.segments_persisted += 1
                    await self.transport.send_event(
                        {
                            "type": "transcript_final",
                            "speaker": segment.speaker,
                            "seq": next_seq,
                            "text": segment.text,
                        }
                    )
                    next_seq += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - persistence boundary
            self._metrics.errors += 1
            logger.warning("Transcript persistence failed on call %s: %s", self.call_id, exc)

    async def _analysis_task(self) -> None:
        """Run bounded, non-overlapping incremental analysis from persisted segments."""
        interval = max(0.5, self.settings.GEMINI_LIVE_ANALYSIS_INTERVAL_SECONDS)
        min_new = max(1, self.settings.GEMINI_LIVE_ANALYSIS_MIN_NEW_SEGMENTS)
        context_window = max(1, self.settings.GEMINI_LIVE_ANALYSIS_CONTEXT_SEGMENTS)
        analyzed_through = -1
        try:
            while not self._stop.is_set():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=interval)
                analyzed_through = await self._run_one_analysis(
                    analyzed_through, min_new, context_window
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - analysis boundary
            self._metrics.errors += 1
            logger.warning("Live analysis loop failed on call %s: %s", self.call_id, exc)

    async def _run_one_analysis(
        self, analyzed_through: int, min_new: int, context_window: int, *, force: bool = False
    ) -> int:
        """Analyze new segments if enough have accrued. Returns new high-water seq."""
        try:
            async with self.session_factory() as db:
                repo = TransactionRepository(db)
                segments = await repo.list_transcript_segments(self.call_id)
                if not segments:
                    return analyzed_through
                highest = segments[-1].seq
                new_count = sum(1 for s in segments if s.seq > analyzed_through)
                if not force and new_count < min_new:
                    return analyzed_through
                recent = segments[-context_window:]
                views = [
                    TranscriptView(seq=s.seq, speaker=s.speaker, content=s.content) for s in recent
                ]
                snapshot = self.analyzer.analyze(views, self.context)
                analysis = CallLiveAnalysisModel(
                    id=uuid4(),
                    call_session_id=self.call_id,
                    transaction_id=self.transaction_id,
                    contract_version=snapshot.contract_version,
                    status=LiveAnalysisStatus.COMPLETED.value,
                    overall_sentiment=snapshot.overall_sentiment.value,
                    findings=[f.model_dump(mode="json") for f in snapshot.findings],
                    uncertainty_notes=list(snapshot.uncertainty_notes),
                    summary=snapshot.summary,
                    analyzed_through_seq=highest,
                    model_metadata={"analyzer": "heuristic_grounded_v1"},
                )
                await repo.create_live_analysis(analysis)
                self._metrics.analyses_run += 1
                await self.transport.send_event(
                    {
                        "type": "analysis_update",
                        "status": LiveAnalysisStatus.COMPLETED.value,
                        "overall_sentiment": snapshot.overall_sentiment.value,
                        "summary": snapshot.summary,
                        "analyzed_through_seq": highest,
                        "findings": [f.model_dump(mode="json") for f in snapshot.findings],
                    }
                )
                return highest
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep voice alive if analysis fails
            self._metrics.errors += 1
            logger.warning("Incremental analysis failed on call %s: %s", self.call_id, exc)
            with contextlib.suppress(Exception):
                await self.transport.send_event(
                    {"type": "analysis_update", "status": LiveAnalysisStatus.UNAVAILABLE.value}
                )
            return analyzed_through

    async def _watchdog_task(self) -> None:
        """Enforce the maximum bounded session duration."""
        try:
            await asyncio.wait_for(
                self._stop.wait(), timeout=self.settings.GEMINI_LIVE_MAX_SESSION_SECONDS
            )
        except TimeoutError:
            self._end_reason = "max_duration_reached"
            self._stop.set()
        except asyncio.CancelledError:
            raise

    # -- shutdown / finalize ------------------------------------------------

    async def _shutdown(self, tasks: list[asyncio.Task[Any]]) -> None:
        self._stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _finalize(self) -> None:
        """Flush any trailing interim text, drain the queue, and run a final analysis."""
        # Flush un-finalized interim accumulations as final segments (best effort).
        trailing = [
            _FinalSegment(speaker=sp, text=txt.strip())
            for sp, txt in self._interim.items()
            if txt.strip()
        ]
        drained: list[_FinalSegment] = []
        while not self._transcript_queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                drained.append(self._transcript_queue.get_nowait())
        pending = drained + trailing
        if pending:
            with contextlib.suppress(Exception):
                async with self.session_factory() as db:
                    repo = TransactionRepository(db)
                    max_seq = await repo.get_max_transcript_seq(self.call_id)
                    next_seq = (max_seq + 1) if max_seq is not None else 0
                    last_text: dict[str, str] = {}
                    for seg in pending:
                        if last_text.get(seg.speaker) == seg.text:
                            continue
                        row = CallTranscriptSegmentModel(
                            id=uuid4(),
                            call_session_id=self.call_id,
                            conversation_id=self.conversation_id,
                            transaction_id=self.transaction_id,
                            speaker=seg.speaker,
                            seq=next_seq,
                            kind=TranscriptSegmentKind.FINAL.value,
                            content=seg.text,
                        )
                        with contextlib.suppress(IntegrityError):
                            await repo.create_transcript_segment(row)
                            last_text[seg.speaker] = seg.text
                            self._metrics.segments_persisted += 1
                            next_seq += 1

        # Ensure a final analysis exists, or explicitly mark it incomplete.
        final_seq = await self._run_one_analysis(
            analyzed_through=-1,
            min_new=1,
            context_window=self.settings.GEMINI_LIVE_ANALYSIS_CONTEXT_SEGMENTS,
            force=True,
        )
        analysis_complete = final_seq >= 0
        with contextlib.suppress(Exception):
            await self.transport.send_event(
                {
                    "type": "session_closed",
                    "reason": self._end_reason,
                    "analysis_complete": analysis_complete,
                    "metrics": {
                        "first_audio_latency_ms": self._metrics.first_audio_latency_ms,
                        "audio_chunks_in": self._metrics.audio_chunks_in,
                        "audio_chunks_out": self._metrics.audio_chunks_out,
                        "segments_persisted": self._metrics.segments_persisted,
                        "segments_dropped": self._metrics.segments_dropped,
                        "analyses_run": self._metrics.analyses_run,
                        "errors": self._metrics.errors,
                    },
                }
            )
        logger.info(
            "Live session %s closed reason=%s metrics=%s",
            self.call_id,
            self._end_reason,
            self._metrics,
        )
        # The orchestrator never changes transaction/call state; that stays with the
        # deterministic lifecycle endpoints.
        now = datetime.now(UTC)
        logger.debug("Live session %s finalized at %s", self.call_id, now.isoformat())
