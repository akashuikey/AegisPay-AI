"""Authenticated WebSocket endpoint for real-time Gemini Live voice calls (P2-A11).

The Gemini API key never leaves the server: the browser authenticates to this
endpoint with its existing operator/customer token and streams PCM audio; the
backend relays to Gemini Live. Payments and calls remain simulated.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.security import decode_access_token, decode_customer_verification_token
from app.db.session import get_session_factory
from app.domain.customer_dialogue import TERMINAL_CALL_STATUSES
from app.domain.state_machine import is_terminal
from app.repositories.operator_repository import OperatorRepository
from app.repositories.recipient_repository import RecipientRepository
from app.repositories.transaction_repository import TransactionRepository
from app.services.live_voice_client import GeminiLiveVoiceClient, LiveVoiceClient
from app.services.live_voice_service import (
    BrowserTransport,
    InboundMessage,
    LiveVoiceOrchestrator,
)

logger = get_logger(__name__)

router = APIRouter(tags=["Live Voice (Simulated)"])

# WebSocket close codes (application range).
_WS_UNAUTHENTICATED = 4401
_WS_FORBIDDEN = 4403
_WS_UNAVAILABLE = 4404
_WS_CONFLICT = 4409
_WS_CAPACITY = 4429

# Process-local registry of active live sessions (prototype-scoped resource guard).
_active_sessions: set[UUID] = set()
_active_lock = asyncio.Lock()


def get_live_voice_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LiveVoiceClient:
    """Provide the real Gemini Live client. Overridden with a mock in tests."""
    return GeminiLiveVoiceClient(settings)


def get_live_session_factory() -> async_sessionmaker[AsyncSession]:
    """Provide the session factory used by orchestrator worker tasks.

    Overridden in tests to point at the test database factory.
    """
    return get_session_factory()


class _WebSocketTransport(BrowserTransport):
    """Bridges the orchestrator to a FastAPI WebSocket."""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket

    async def send_event(self, event: dict[str, object]) -> None:
        await self._ws.send_json(event)

    async def send_audio(self, data: bytes) -> None:
        await self._ws.send_bytes(data)

    async def receive(self) -> AsyncIterator[InboundMessage]:
        while True:
            try:
                message = await self._ws.receive()
            except (WebSocketDisconnect, RuntimeError):
                yield InboundMessage(kind="close")
                return
            if message.get("type") == "websocket.disconnect":
                yield InboundMessage(kind="close")
                return
            raw_bytes = message.get("bytes")
            raw_text = message.get("text")
            if raw_bytes is not None:
                yield InboundMessage(kind="audio", audio=raw_bytes)
            elif raw_text is not None:
                try:
                    control = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(control, dict):
                    yield InboundMessage(kind="control", control=control)


def _authorize(token: str | None, settings: Settings) -> dict[str, str] | None:
    """Resolve a token to an auth context, or None if invalid.

    Operator access tokens grant console-wide access; customer verification tokens
    are scoped to their bound transaction.
    """
    if not token:
        return None
    # Operator access token first.
    with contextlib.suppress(Exception):
        operator_id = decode_access_token(token, settings)
        return {"role": "operator", "sub": operator_id}
    # Customer verification session token.
    with contextlib.suppress(Exception):
        claims = decode_customer_verification_token(token, settings)
        return {
            "role": "customer",
            "sub": claims.get("customer_id", "unknown"),
            "transaction_id": claims.get("transaction_id", ""),
        }
    return None


@router.websocket("/calls/{call_id}/live")
async def live_voice_ws(
    websocket: WebSocket,
    call_id: UUID,
    provider: Annotated[LiveVoiceClient, Depends(get_live_voice_client)],
    worker_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_live_session_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
    token: Annotated[str | None, Query()] = None,
) -> None:
    """Stream real-time simulated voice between the browser and Gemini Live."""
    if not settings.GEMINI_LIVE_ENABLED:
        await websocket.close(code=_WS_UNAVAILABLE)
        return

    auth_ctx = _authorize(token, settings)
    if auth_ctx is None:
        await websocket.close(code=_WS_UNAUTHENTICATED)
        return

    # Validate the call session, transaction scope, and lifecycle on a short-lived
    # session created from the worker factory (so tests and prod agree on the DB).
    async with worker_factory() as db:
        repo = TransactionRepository(db)
        if auth_ctx["role"] == "operator":
            op_repo = OperatorRepository(db)
            with contextlib.suppress(Exception):
                operator = await op_repo.get_by_id(UUID(auth_ctx["sub"]))
                if operator is None or not operator.is_active:
                    await websocket.close(code=_WS_UNAUTHENTICATED)
                    return

        call = await repo.get_call_session_by_id(call_id)
        if call is None:
            await websocket.close(code=_WS_UNAVAILABLE)
            return

        if auth_ctx["role"] == "customer" and auth_ctx.get("transaction_id") != str(
            call.transaction_id
        ):
            await websocket.close(code=_WS_FORBIDDEN)
            return

        if call.status in {s.value for s in TERMINAL_CALL_STATUSES}:
            await websocket.close(code=_WS_CONFLICT)
            return

        transaction = await repo.get_by_id(call.transaction_id)
        if transaction is None or is_terminal(transaction.state):
            await websocket.close(code=_WS_CONFLICT)
            return

        recipient_repo = RecipientRepository(db)
        rec_record = None
        if transaction.recipient_identifier:
            rec_record = await recipient_repo.get_by_upi_id(transaction.recipient_identifier)

        latest_assessment = await repo.get_latest_assessment(transaction.id)

        transaction_id = call.transaction_id
        conversation_id = call.conversation_id
        context = {
            "transaction": {
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "recipient_name": transaction.recipient_name,
                "recipient_identifier": transaction.recipient_identifier,
                "purpose": transaction.purpose,
                "payment_rail": transaction.payment_rail,
            },
            "recipient": (
                {
                    "display_name": rec_record.display_name,
                    "bank_name": rec_record.bank_name,
                    "branch_region": rec_record.branch_region,
                    "account_age_days": rec_record.account_age_days,
                    "is_trusted": rec_record.is_trusted_beneficiary,
                    "category": (
                        rec_record.category.value
                        if hasattr(rec_record.category, "value")
                        else str(rec_record.category)
                    ),
                }
                if rec_record is not None
                else None
            ),
            "risk_signals": (
                [
                    r["description"]
                    for r in (latest_assessment.triggered_rules or [])
                    if isinstance(r, dict) and "description" in r
                ]
                if latest_assessment is not None
                else []
            ),
        }

    # Enforce one live session per call and a process-wide concurrency cap.
    async with _active_lock:
        if call_id in _active_sessions:
            await websocket.close(code=_WS_CONFLICT)
            return
        if len(_active_sessions) >= settings.GEMINI_LIVE_MAX_CONCURRENT_SESSIONS:
            await websocket.close(code=_WS_CAPACITY)
            return
        _active_sessions.add(call_id)

    await websocket.accept()
    transport = _WebSocketTransport(websocket)
    orchestrator = LiveVoiceOrchestrator(
        provider=provider,
        transport=transport,
        session_factory=worker_factory,
        settings=settings,
        call_id=call_id,
        transaction_id=transaction_id,
        conversation_id=conversation_id,
        context=context,
    )
    try:
        await orchestrator.run()
    except WebSocketDisconnect:
        logger.info("Live voice WebSocket disconnected for call %s", call_id)
    except Exception as exc:  # noqa: BLE001 - connection boundary
        logger.warning("Live voice session error for call %s: %s", call_id, exc)
    finally:
        async with _active_lock:
            _active_sessions.discard(call_id)
        with contextlib.suppress(Exception):
            await websocket.close()
