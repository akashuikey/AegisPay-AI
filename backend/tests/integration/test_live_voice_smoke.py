"""Optional real-provider smoke test for Gemini Live (P2-A11).

Skipped by default. It runs ONLY when ``GEMINI_LIVE_SMOKE=1`` and a Gemini API key
(or Vertex project) are present in the environment, so automated CI never depends
on the live provider. This exercises a real ``connect`` handshake and a single
audio frame against the configured Live model.
"""

from __future__ import annotations

import os

import pytest

from app.core.config import Settings
from app.services.live_voice_client import GeminiLiveVoiceClient, LiveVoiceEventType

_SMOKE_ENABLED = os.getenv("GEMINI_LIVE_SMOKE") == "1" and bool(
    os.getenv("GEMINI_API_KEY") or os.getenv("GCP_PROJECT_ID")
)

pytestmark = pytest.mark.skipif(
    not _SMOKE_ENABLED,
    reason="Set GEMINI_LIVE_SMOKE=1 with Gemini/Vertex credentials to run the live smoke test.",
)


@pytest.mark.asyncio
async def test_real_gemini_live_handshake() -> None:
    """Open a real Live session, send one silent frame, and read at least one event."""
    settings = Settings(GEMINI_LIVE_ENABLED=True)
    client = GeminiLiveVoiceClient(settings)
    async with client.connect(system_instruction="You are a test agent. Say hello.") as session:
        # 20 ms of silence at 16 kHz PCM16.
        await session.send_audio(b"\x00\x00" * 320)
        received = False
        async for event in session.receive():
            assert event.type in set(LiveVoiceEventType)
            received = True
            break
        assert received, "No event received from the live provider."
