"""Gemini Live API provider abstraction for real-time bidirectional voice (P2-A11).

Defines a provider-agnostic ``LiveVoiceClient`` / ``LiveVoiceSession`` interface, a
real implementation over the official ``google-genai`` Live API, and a deterministic
in-memory mock for tests and offline development.

The Gemini API key is read from settings server-side and is NEVER exposed to the
browser. All audio is simulated inside the app; no real telephony is used.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.core.config import Settings
from app.core.errors import AIConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)


class LiveVoiceEventType(StrEnum):
    """Normalized event kinds emitted by a live voice session."""

    SETUP_COMPLETE = "setup_complete"
    AUDIO = "audio"
    INPUT_TRANSCRIPT = "input_transcript"
    OUTPUT_TRANSCRIPT = "output_transcript"
    INTERRUPTED = "interrupted"
    TURN_COMPLETE = "turn_complete"
    GO_AWAY = "go_away"
    RESUMPTION_UPDATE = "resumption_update"
    ERROR = "error"


@dataclass(slots=True)
class LiveVoiceEvent:
    """A provider-agnostic event flowing from the model back toward the orchestrator."""

    type: LiveVoiceEventType
    audio: bytes | None = None
    text: str | None = None
    finished: bool = False
    handle: str | None = None
    resumable: bool = False
    time_left_ms: int | None = None
    error: str | None = None


class LiveVoiceSession(Protocol):
    """A single bidirectional live voice session."""

    async def send_audio(self, data: bytes) -> None:
        """Forward a chunk of PCM16 input audio to the model."""
        ...

    def receive(self) -> AsyncIterator[LiveVoiceEvent]:
        """Yield normalized events from the model until the session closes."""
        ...

    async def aclose(self) -> None:
        """Close the underlying provider session and release resources."""
        ...


class LiveVoiceClient(Protocol):
    """Factory for live voice sessions."""

    def connect(
        self,
        *,
        system_instruction: str,
        resumption_handle: str | None = None,
    ) -> contextlib.AbstractAsyncContextManager[LiveVoiceSession]:
        """Open a live session as an async context manager."""
        ...


# ---------------------------------------------------------------------------
# Real Gemini Live implementation
# ---------------------------------------------------------------------------


class _GeminiLiveSession:
    """Adapts a google-genai live ``AsyncSession`` to ``LiveVoiceSession``."""

    def __init__(self, session: object, input_sample_rate: int) -> None:
        self._session = session
        self._mime = f"audio/pcm;rate={input_sample_rate}"

    async def send_audio(self, data: bytes) -> None:
        from google.genai import types

        await self._session.send_realtime_input(  # type: ignore[attr-defined]
            audio=types.Blob(data=data, mime_type=self._mime)
        )

    async def receive(self) -> AsyncIterator[LiveVoiceEvent]:
        async for message in self._session.receive():  # type: ignore[attr-defined]
            for event in _map_server_message(message):
                yield event

    async def aclose(self) -> None:
        with contextlib.suppress(Exception):
            await self._session.close()  # type: ignore[attr-defined]


def _map_server_message(message: object) -> list[LiveVoiceEvent]:
    """Translate a google-genai ``LiveServerMessage`` into normalized events."""
    events: list[LiveVoiceEvent] = []

    setup_complete = getattr(message, "setup_complete", None)
    if setup_complete is not None:
        events.append(LiveVoiceEvent(type=LiveVoiceEventType.SETUP_COMPLETE))

    content = getattr(message, "server_content", None)
    if content is not None:
        model_turn = getattr(content, "model_turn", None)
        if model_turn is not None:
            for part in getattr(model_turn, "parts", None) or []:
                inline = getattr(part, "inline_data", None)
                audio = getattr(inline, "data", None) if inline is not None else None
                if audio:
                    events.append(LiveVoiceEvent(type=LiveVoiceEventType.AUDIO, audio=audio))

        in_tx = getattr(content, "input_transcription", None)
        if in_tx is not None and getattr(in_tx, "text", None):
            events.append(
                LiveVoiceEvent(
                    type=LiveVoiceEventType.INPUT_TRANSCRIPT,
                    text=in_tx.text,
                    finished=bool(getattr(in_tx, "finished", False)),
                )
            )
        out_tx = getattr(content, "output_transcription", None)
        if out_tx is not None and getattr(out_tx, "text", None):
            events.append(
                LiveVoiceEvent(
                    type=LiveVoiceEventType.OUTPUT_TRANSCRIPT,
                    text=out_tx.text,
                    finished=bool(getattr(out_tx, "finished", False)),
                )
            )
        if getattr(content, "interrupted", False):
            events.append(LiveVoiceEvent(type=LiveVoiceEventType.INTERRUPTED))
        if getattr(content, "turn_complete", False):
            events.append(LiveVoiceEvent(type=LiveVoiceEventType.TURN_COMPLETE))

    go_away = getattr(message, "go_away", None)
    if go_away is not None:
        time_left = getattr(go_away, "time_left", None)
        ms = int(time_left.total_seconds() * 1000) if time_left is not None else None
        events.append(LiveVoiceEvent(type=LiveVoiceEventType.GO_AWAY, time_left_ms=ms))

    resumption = getattr(message, "session_resumption_update", None)
    if resumption is not None:
        events.append(
            LiveVoiceEvent(
                type=LiveVoiceEventType.RESUMPTION_UPDATE,
                handle=getattr(resumption, "new_handle", None),
                resumable=bool(getattr(resumption, "resumable", False)),
            )
        )

    return events


class GeminiLiveVoiceClient:
    """Live voice client backed by the official google-genai Live API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: object | None = None

    def _get_client(self) -> object:
        if self._client is not None:
            return self._client
        from google import genai

        if self.settings.GCP_PROJECT_ID:
            self._client = genai.Client(
                vertexai=True,
                project=self.settings.GCP_PROJECT_ID,
                location=self.settings.GCP_LOCATION,
            )
        elif self.settings.GEMINI_API_KEY:
            self._client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        else:
            raise AIConfigurationError(
                "Neither GEMINI_API_KEY nor GCP_PROJECT_ID is configured in the environment. "
                "Set GEMINI_API_KEY in .env or configure AI_PROVIDER=mock for offline testing."
            )
        return self._client

    def _build_config(self, system_instruction: str, resumption_handle: str | None) -> object:
        from google.genai import types

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=system_instruction,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.settings.GEMINI_LIVE_VOICE
                    )
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            session_resumption=types.SessionResumptionConfig(handle=resumption_handle),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            ),
        )

    @contextlib.asynccontextmanager
    async def connect(
        self,
        *,
        system_instruction: str,
        resumption_handle: str | None = None,
    ) -> AsyncIterator[LiveVoiceSession]:
        client = self._get_client()
        config = self._build_config(system_instruction, resumption_handle)
        logger.info(
            "Opening Gemini Live session model=%s voice=%s resumed=%s",
            self.settings.GEMINI_LIVE_MODEL,
            self.settings.GEMINI_LIVE_VOICE,
            resumption_handle is not None,
        )
        async with client.aio.live.connect(  # type: ignore[attr-defined]
            model=self.settings.GEMINI_LIVE_MODEL, config=config
        ) as session:
            wrapper = _GeminiLiveSession(session, self.settings.GEMINI_LIVE_INPUT_SAMPLE_RATE)
            yield wrapper


# ---------------------------------------------------------------------------
# Deterministic mock implementation (tests / offline)
# ---------------------------------------------------------------------------


class MockLiveVoiceSession:
    """In-memory live session driven explicitly by tests.

    ``sent_audio`` records forwarded input chunks (to assert forwarding). Tests push
    model events with ``push``/``push_many`` and call ``finish`` to end ``receive``.
    """

    def __init__(self) -> None:
        import asyncio

        self.sent_audio: list[bytes] = []
        self.closed: bool = False
        self._queue: asyncio.Queue[LiveVoiceEvent | None] = asyncio.Queue()

    async def send_audio(self, data: bytes) -> None:
        self.sent_audio.append(data)

    def push(self, event: LiveVoiceEvent) -> None:
        self._queue.put_nowait(event)

    def push_many(self, events: list[LiveVoiceEvent]) -> None:
        for event in events:
            self.push(event)

    def finish(self) -> None:
        """Signal end of stream for ``receive``."""
        self._queue.put_nowait(None)

    async def receive(self) -> AsyncIterator[LiveVoiceEvent]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item

    async def aclose(self) -> None:
        self.closed = True
        self.finish()


class MockLiveVoiceClient:
    """Mock live client yielding a controllable in-memory session.

    When ``script`` is provided, each opened session auto-emits those events (useful
    for self-driving end-to-end tests); the session is then left open until the
    orchestrator stops and cancels its receive loop. Without a script, tests push
    events manually via ``sessions[-1].push(...)``.
    """

    def __init__(
        self,
        connect_error: Exception | None = None,
        script: list[LiveVoiceEvent] | None = None,
    ) -> None:
        self.connect_error = connect_error
        self.script = script
        self.sessions: list[MockLiveVoiceSession] = []
        self.last_system_instruction: str | None = None
        self.last_resumption_handle: str | None = None

    @contextlib.asynccontextmanager
    async def connect(
        self,
        *,
        system_instruction: str,
        resumption_handle: str | None = None,
    ) -> AsyncIterator[LiveVoiceSession]:
        if self.connect_error is not None:
            raise self.connect_error
        self.last_system_instruction = system_instruction
        self.last_resumption_handle = resumption_handle
        session = MockLiveVoiceSession()
        if self.script:
            session.push_many(self.script)
        self.sessions.append(session)
        try:
            yield session
        finally:
            session.closed = True
