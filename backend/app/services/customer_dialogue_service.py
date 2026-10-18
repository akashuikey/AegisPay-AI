"""Application service orchestrating dynamic simulated customer calls and chat dialogue.

Coordinates:
- Call session lifecycle (INITIATED -> RINGING -> CONNECTED -> COMPLETED / DECLINED / etc.)
- Gemini dynamic turn generation for conversational forensic inquiry
- Idempotency and concurrency safety
- Linking collected statements to coercion analysis and deterministic workflow
- Non-mutation invariant: AI dialogue generates forensic intelligence and does NOT directly
  alter transaction state
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.errors import (
    AIConfigurationError,
    AIProviderError,
    ConflictError,
    InvalidStateTransitionError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.db.models import (
    InvestigationConversationModel,
    InvestigationConversationTurnModel,
    TransactionCallSessionModel,
)
from app.domain.customer_dialogue import (
    CUSTOMER_DIALOGUE_SYSTEM_INSTRUCTION,
    MAX_DIALOGUE_TURNS,
    TERMINAL_CALL_STATUSES,
    CallSessionDirection,
    CallSessionStatus,
    CustomerDialogueTurnResult,
    DialogueChannel,
    SuggestedAction,
    build_customer_dialogue_prompt,
)
from app.domain.investigation import (
    ConversationRole,
    ConversationStatus,
    EvidenceProvenance,
    InvestigationModelMetadata,
    RiskSentiment,
)
from app.domain.state_machine import is_terminal
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.coercion import AnalyzeCoercionRequest
from app.services.ai_client import AIInvestigationClient
from app.services.coercion_service import CoercionService
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)


def _turn_signal_snapshot(
    *,
    role: str,
    content: str,
    risk_sentiment: str | None,
    coercion_cues: list[str] | None,
    internal_observations: list[str] | None,
) -> dict[str, Any]:
    """Build a plain-dict snapshot of a turn's coercion-relevant signals.

    Snapshots are taken from in-memory values so coercion evaluation never relies
    on lazily loading expired ORM attributes after a commit (SEC-01).
    """
    return {
        "role": role,
        "content": content,
        "risk_sentiment": risk_sentiment,
        "coercion_cues": list(coercion_cues or []),
        "internal_observations": list(internal_observations or []),
    }


def _snapshot_turns(turns: list[InvestigationConversationTurnModel]) -> list[dict[str, Any]]:
    """Snapshot persisted turns into coercion-signal dicts."""
    snapshots: list[dict[str, Any]] = []
    for turn in turns:
        meta = turn.model_metadata or {}
        snapshots.append(
            _turn_signal_snapshot(
                role=turn.role,
                content=turn.content,
                risk_sentiment=turn.risk_sentiment,
                coercion_cues=meta.get("coercion_cues"),
                internal_observations=meta.get("internal_observations"),
            )
        )
    return snapshots


def _has_accumulated_coercion_signal(snapshots: list[dict[str, Any]]) -> bool:
    """Return True if any turn in the conversation surfaced a coercion signal.

    Evaluates the *entire* accumulated transcript rather than only the final
    assistant turn, so coercion evidence raised earlier in the dialogue still
    triggers forensic analysis even when the closing turn looks benign.
    """
    coerced = RiskSentiment.COERCED.value
    for snap in snapshots:
        if snap["coercion_cues"]:
            return True
        if snap["risk_sentiment"] == coerced:
            return True
        if any(
            "coercion" in str(obs).lower() or "duress" in str(obs).lower()
            for obs in snap["internal_observations"]
        ):
            return True
    return False


class CustomerDialogueService:
    """Orchestrates dynamic customer voice and chat inquiry sessions."""

    def __init__(
        self,
        repository: TransactionRepository,
        transaction_service: TransactionService,
        ai_client: AIInvestigationClient,
        settings: Settings,
        coercion_service: CoercionService | None = None,
    ) -> None:
        self.repository = repository
        self.transaction_service = transaction_service
        self.ai_client = ai_client
        self.settings = settings
        self.coercion_service = coercion_service

    async def initiate_call_session(
        self,
        transaction_id: UUID,
        channel: DialogueChannel = DialogueChannel.VOICE_SIMULATED,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[TransactionCallSessionModel, bool]:
        """Initiate a simulated customer call or chat session for a transaction.

        Returns (session, created).
        Idempotent: Replaying the same idempotency_key returns the existing session.
        If an active session is already ongoing, it is returned without duplicating.
        """
        # 1. Verify transaction exists and is not in terminal state
        tx = await self.transaction_service.get_transaction(transaction_id)
        if is_terminal(tx.state):
            raise InvalidStateTransitionError(
                from_state=tx.state,
                to_state="CALL_INITIATED",
                message=(
                    f"Cannot initiate call session for transaction in terminal state '{tx.state}'"
                ),
            )

        tx_id_str = str(tx.id)
        tx_customer_id = tx.customer_id
        tx_amount = tx.amount
        tx_currency = tx.currency
        tx_recipient_name = tx.recipient_name
        tx_recipient_identifier = tx.recipient_identifier
        tx_purpose = tx.purpose
        tx_payment_rail = tx.payment_rail

        # 2. Check idempotency key if supplied
        if idempotency_key:
            existing = await self.repository.get_call_session_by_idempotency_key(
                transaction_id=transaction_id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                logger.info(
                    "Idempotent replay for call session tx=%s key=%s; returning %s",
                    transaction_id,
                    idempotency_key,
                    existing.id,
                )
                return existing, False

        # 3. Check for existing active session (INITIATED, RINGING, or CONNECTED)
        active = await self.repository.get_active_call_session_for_transaction(transaction_id)
        if active is not None:
            logger.info(
                "Active call session already exists for tx=%s (session=%s, status=%s)",
                transaction_id,
                active.id,
                active.status,
            )
            return active, False

        # 4. Determine attempt count from historical sessions
        historical = await self.repository.list_call_sessions_for_transaction(transaction_id)
        attempt_number = len(historical) + 1

        # 5. Create the call session FIRST, in RINGING status. The partial unique
        #    index on active sessions makes "one active session per transaction"
        #    atomic: a concurrent initiation that lost the race raises IntegrityError
        #    here, which we resolve by returning the winner's session.
        session_id = uuid4()
        now = datetime.now(UTC)
        session = TransactionCallSessionModel(
            id=session_id,
            transaction_id=transaction_id,
            conversation_id=None,
            channel=channel.value,
            status=CallSessionStatus.RINGING.value,
            direction=CallSessionDirection.OUTBOUND_SIMULATED.value,
            attempt_number=attempt_number,
            idempotency_key=idempotency_key,
            started_at=now,
            customer_phone_masked="+91 ••••• ••890",
            version=1,
        )
        try:
            await self.repository.create_call_session(session)
        except IntegrityError:
            logger.info(
                "Concurrent call initiation conflict for tx=%s; returning existing session",
                transaction_id,
            )
            if idempotency_key:
                existing = await self.repository.get_call_session_by_idempotency_key(
                    transaction_id=transaction_id,
                    idempotency_key=idempotency_key,
                )
                if existing is not None:
                    return existing, False
            active = await self.repository.get_active_call_session_for_transaction(transaction_id)
            if active is not None:
                return active, False
            raise

        # 6. Create the linked conversation record and attach it to the session.
        conv_type = (
            "CUSTOMER_CALL" if channel == DialogueChannel.VOICE_SIMULATED else "CUSTOMER_CHAT"
        )
        conv = InvestigationConversationModel(
            id=uuid4(),
            transaction_id=transaction_id,
            status=ConversationStatus.ACTIVE.value,
            conversation_type=conv_type,
            turn_count=0,
            version=1,
        )
        saved_conv = await self.repository.create_conversation(conv)
        conv_id = saved_conv.id
        conv_version = saved_conv.version

        session.conversation_id = conv_id
        await self.repository.update_call_session(session)

        # 7. Generate initial assistant question (turn 0) via Gemini
        assessment = await self.repository.get_latest_assessment(transaction_id)
        context: dict[str, Any] = {
            "transaction": {
                "id": tx_id_str,
                "customer_id": tx_customer_id,
                "amount": str(tx_amount),
                "currency": tx_currency,
                "recipient_name": tx_recipient_name,
                "recipient_identifier": tx_recipient_identifier,
                "purpose": tx_purpose,
                "payment_rail": tx_payment_rail,
            },
            "deterministic_assessment": (
                {
                    "risk_level": assessment.risk_level,
                    "triggered_rules": assessment.triggered_rules,
                }
                if assessment
                else {}
            ),
        }

        prompt = build_customer_dialogue_prompt(
            context=context,
            history=[],
            latest_customer_message=None,
            channel=channel,
        )

        output: CustomerDialogueTurnResult
        metadata: InvestigationModelMetadata

        if self.settings.GEMINI_LIVE_ENABLED and channel == DialogueChannel.VOICE_SIMULATED:
            logger.info(
                "Gemini Live mode enabled for tx=%s session=%s; bypassing text model generation "
                "for opening turn; opening utterance will be generated over Live WebSocket.",
                transaction_id,
                session_id,
            )
            output = CustomerDialogueTurnResult(
                assistant_message=(
                    f"Hello, this is Aster Bank Fraud Prevention calling to verify a "
                    f"pending payment of {tx_currency} {tx_amount} to {tx_recipient_name}. "
                    "Can you confirm if you authorized this transfer?"
                ),
                internal_observations=[
                    "Live voice call session initialized; ready for real-time Live connection."
                ],
                uncertainty_notes=["Gemini Live audio session initialized."],
                suggested_action=SuggestedAction.CONTINUE_INQUIRY,
                is_terminal_turn=False,
                risk_sentiment=RiskSentiment.UNKNOWN,
                evidence_references=["tx:amount", "tx:recipient_name"],
                coercion_cues=[],
            )
            metadata = InvestigationModelMetadata(
                provider="gemini_live",
                model_id=self.settings.GEMINI_LIVE_MODEL,
                correlation_id=correlation_id,
            )
        else:
            try:
                output, metadata = await self.ai_client.generate_customer_dialogue_turn(
                    prompt=prompt,
                    system_instruction=CUSTOMER_DIALOGUE_SYSTEM_INSTRUCTION,
                    correlation_id=correlation_id,
                )
            except (AIProviderError, AIConfigurationError):
                logger.warning(
                    "Initial dialogue generation failed for tx=%s session=%s; marking FAILED",
                    transaction_id,
                    session_id,
                )
                session.status = CallSessionStatus.FAILED.value
                session.failure_reason = "INITIAL_DIALOGUE_GENERATION_FAILED"
                session.ended_at = datetime.now(UTC)
                await self.repository.update_call_session(session)
                try:
                    await self.repository.update_conversation(
                        conversation_id=conv_id,
                        turn_count=0,
                        current_version=conv_version,
                        status=ConversationStatus.COMPLETED.value,
                    )
                except Exception as conv_err:  # pragma: no cover - defensive cleanup
                    logger.warning("Failed to close conversation after init failure: %s", conv_err)
                raise

        initial_turn = InvestigationConversationTurnModel(
            id=uuid4(),
            conversation_id=conv_id,
            turn_index=0,
            role=ConversationRole.ASSISTANT.value,
            content=output.assistant_message,
            evidence_provenance=EvidenceProvenance.AI_ASSISTANT.value,
            evidence_references=output.evidence_references,
            findings=[],
            risk_sentiment=output.risk_sentiment.value if output.risk_sentiment else None,
            confidence=None,
            confidence_score=None,
            missing_information=output.uncertainty_notes,
            follow_up_questions=[],
            model_metadata={
                "internal_observations": output.internal_observations,
                "uncertainty_notes": output.uncertainty_notes,
                "suggested_action": (
                    output.suggested_action.value
                    if hasattr(output.suggested_action, "value")
                    else str(output.suggested_action)
                ),
                "is_terminal_turn": output.is_terminal_turn,
                "coercion_cues": output.coercion_cues,
                "ai_metadata": asdict(metadata),
            },
        )
        await self.repository.create_conversation_turn(initial_turn)

        await self.repository.update_conversation(
            conversation_id=conv_id,
            turn_count=1,
            current_version=conv_version,
        )

        # Re-fetch session with turns loaded
        refreshed = await self.repository.get_call_session_by_id(session_id)
        if refreshed is None:
            raise NotFoundError(f"Call session with ID '{session_id}' not found")
        return refreshed, True

    async def connect_call_session(self, call_id: UUID) -> TransactionCallSessionModel:
        """Transition call session to CONNECTED when answered by customer."""
        session = await self.repository.get_call_session_by_id(call_id)
        if session is None:
            raise NotFoundError(f"Call session with ID '{call_id}' not found")

        if session.status == CallSessionStatus.CONNECTED.value:
            return session

        if session.status in TERMINAL_CALL_STATUSES:
            raise ConflictError(
                f"Cannot connect call session in terminal status '{session.status}'"
            )

        if session.status not in (
            CallSessionStatus.INITIATED.value,
            CallSessionStatus.RINGING.value,
        ):
            raise InvalidStateTransitionError(
                from_state=session.status,
                to_state=CallSessionStatus.CONNECTED.value,
                message=f"Cannot connect call session from status '{session.status}'",
            )

        session.status = CallSessionStatus.CONNECTED.value
        session.connected_at = datetime.now(UTC)
        return await self.repository.update_call_session(session)

    async def submit_turn(
        self,
        call_id: UUID,
        customer_message: str,
        source: str = "typed",
        client_turn_id: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[TransactionCallSessionModel, InvestigationConversationTurnModel]:
        """Submit a customer response turn, invoke Gemini, and update session."""
        session = await self.repository.get_call_session_by_id(call_id)
        if session is None:
            raise NotFoundError(f"Call session with ID '{call_id}' not found")

        conv = session.conversation
        if conv is None:
            raise NotFoundError(f"Conversation not associated with call session '{call_id}'")

        # Extract values before committing to avoid post-commit attribute expiration
        session_id = session.id
        transaction_id = session.transaction_id
        session_channel = session.channel
        conv_id = conv.id
        conv_version = conv.version
        turns = list(conv.turns or [])

        # Check client_turn_id idempotency token first (supports replaying completed turns)
        if client_turn_id:
            for t in reversed(turns):
                meta = t.model_metadata or {}
                if meta.get("client_turn_id") == client_turn_id:
                    logger.info(
                        "Idempotent turn replay for call=%s token=%s", call_id, client_turn_id
                    )
                    # Find following assistant turn if present
                    assistant_turn = next(
                        (at for at in turns if at.turn_index == t.turn_index + 1), t
                    )
                    return session, assistant_turn

        if session.status != CallSessionStatus.CONNECTED.value:
            raise ConflictError(
                f"Cannot submit customer turn for call session in status '{session.status}'. "
                "Call must be in CONNECTED status."
            )

        # 1. Fetch transaction and risk context before committing
        tx = await self.transaction_service.get_transaction(transaction_id)
        assessment = await self.repository.get_latest_assessment(transaction_id)
        context: dict[str, Any] = {
            "transaction": {
                "id": str(tx.id),
                "customer_id": tx.customer_id,
                "amount": str(tx.amount),
                "currency": tx.currency,
                "recipient_name": tx.recipient_name,
                "recipient_identifier": tx.recipient_identifier,
                "purpose": tx.purpose,
                "payment_rail": tx.payment_rail,
            },
            "deterministic_assessment": (
                {
                    "risk_level": assessment.risk_level,
                    "triggered_rules": assessment.triggered_rules,
                }
                if assessment
                else {}
            ),
        }

        # 2. Record customer turn
        customer_turn_index = len(turns)
        customer_turn = InvestigationConversationTurnModel(
            id=uuid4(),
            conversation_id=conv_id,
            turn_index=customer_turn_index,
            role=ConversationRole.CUSTOMER.value,
            content=customer_message,
            evidence_provenance=EvidenceProvenance.CUSTOMER_STATEMENT.value,
            evidence_references=[],
            findings=[],
            risk_sentiment=None,
            confidence=None,
            confidence_score=None,
            missing_information=[],
            follow_up_questions=[],
            model_metadata={
                "source": source,
                "client_turn_id": client_turn_id,
            },
        )

        history_dicts = [
            {
                "turn_index": t.turn_index,
                "role": t.role,
                "content": t.content,
            }
            for t in turns
        ]

        prompt = build_customer_dialogue_prompt(
            context=context,
            history=history_dicts,
            latest_customer_message=customer_message,
            channel=DialogueChannel(session_channel),
        )

        output, metadata = await self.ai_client.generate_customer_dialogue_turn(
            prompt=prompt,
            system_instruction=CUSTOMER_DIALOGUE_SYSTEM_INSTRUCTION,
            correlation_id=correlation_id,
        )

        # 3. Record assistant response turn
        assistant_turn_index = customer_turn_index + 1
        assistant_turn = InvestigationConversationTurnModel(
            id=uuid4(),
            conversation_id=conv_id,
            turn_index=assistant_turn_index,
            role=ConversationRole.ASSISTANT.value,
            content=output.assistant_message,
            evidence_provenance=EvidenceProvenance.AI_ASSISTANT.value,
            evidence_references=output.evidence_references,
            findings=[],
            risk_sentiment=output.risk_sentiment.value if output.risk_sentiment else None,
            confidence=None,
            confidence_score=None,
            missing_information=output.uncertainty_notes,
            follow_up_questions=[],
            model_metadata={
                "internal_observations": output.internal_observations,
                "uncertainty_notes": output.uncertainty_notes,
                "suggested_action": (
                    output.suggested_action.value
                    if hasattr(output.suggested_action, "value")
                    else str(output.suggested_action)
                ),
                "is_terminal_turn": output.is_terminal_turn,
                "coercion_cues": output.coercion_cues,
                "ai_metadata": asdict(metadata),
            },
        )

        # Persist both turns. A concurrent submission racing for the same turn
        # index is rejected by the (conversation_id, turn_index) unique constraint;
        # surface it as a safe conflict rather than an unhandled 500.
        try:
            await self.repository.create_conversation_turn(customer_turn)
            await self.repository.create_conversation_turn(assistant_turn)
        except IntegrityError as exc:
            raise ConflictError(
                "A concurrent turn was submitted for this call session; "
                "please reload the conversation and retry."
            ) from exc

        # Snapshot coercion signals across the whole conversation (not just the
        # final assistant turn) before any further commit expires attributes.
        accumulated_snapshots = _snapshot_turns(turns)
        accumulated_snapshots.append(
            _turn_signal_snapshot(
                role=ConversationRole.CUSTOMER.value,
                content=customer_message,
                risk_sentiment=None,
                coercion_cues=[],
                internal_observations=[],
            )
        )
        accumulated_snapshots.append(
            _turn_signal_snapshot(
                role=ConversationRole.ASSISTANT.value,
                content=output.assistant_message,
                risk_sentiment=output.risk_sentiment.value if output.risk_sentiment else None,
                coercion_cues=list(output.coercion_cues),
                internal_observations=list(output.internal_observations),
            )
        )

        is_terminal = output.is_terminal_turn or assistant_turn_index >= MAX_DIALOGUE_TURNS
        conv_status = ConversationStatus.COMPLETED.value if is_terminal else None
        await self.repository.update_conversation(
            conversation_id=conv_id,
            turn_count=assistant_turn_index + 1,
            current_version=conv_version,
            status=conv_status,
        )

        # Check terminal turn criteria (model signaled terminal or turn budget reached)
        if is_terminal:
            sess_to_update = await self.repository.get_call_session_by_id(session_id)
            if sess_to_update:
                now = datetime.now(UTC)
                sess_to_update.status = CallSessionStatus.COMPLETED.value
                sess_to_update.ended_at = now
                if sess_to_update.connected_at:
                    diff_sec = (
                        sess_to_update.ended_at - sess_to_update.connected_at
                    ).total_seconds()
                    sess_to_update.duration_seconds = max(1, int(diff_sec))

                await self._maybe_link_coercion_analysis(
                    session=sess_to_update,
                    snapshots=accumulated_snapshots,
                    transaction_id=transaction_id,
                    correlation_id=correlation_id,
                )
                await self.repository.update_call_session(sess_to_update)

        refreshed = await self.repository.get_call_session_by_id(session_id)
        if refreshed is None:
            raise NotFoundError(f"Call session with ID '{session_id}' not found")
        return refreshed, assistant_turn

    async def _maybe_link_coercion_analysis(
        self,
        *,
        session: TransactionCallSessionModel,
        snapshots: list[dict[str, Any]],
        transaction_id: UUID,
        correlation_id: str | None,
    ) -> None:
        """Run coercion analysis from accumulated evidence and link it to the session.

        Shared by automatic (turn-driven) and manual completion so both follow the
        same policy. The AI analysis is advisory forensic intelligence only; it never
        mutates transaction state. A failure here is logged and swallowed so it cannot
        corrupt the call lifecycle.
        """
        if self.coercion_service is None:
            return
        if session.coercion_analysis_id is not None:
            return
        if not _has_accumulated_coercion_signal(snapshots):
            return
        try:
            transcript = "\n".join(
                f"{snap['role'].upper()}: {snap['content']}" for snap in snapshots
            )
            coercion_res = await self.coercion_service.analyze_transaction_coercion(
                transaction_id=transaction_id,
                request=AnalyzeCoercionRequest(
                    call_transcript=transcript,
                    correlation_id=correlation_id,
                ),
            )
            session.coercion_analysis_id = coercion_res.id
        except Exception as coercion_err:
            logger.warning(
                "Failed to trigger coercion analysis on completed dialogue: %s",
                coercion_err,
            )

    async def complete_call_session(
        self, call_id: UUID, correlation_id: str | None = None
    ) -> TransactionCallSessionModel:
        """Mark a call session as completed by the customer or operator.

        Completion is idempotent on an already-completed session, but it must never
        resurrect a different terminal state (DECLINED, TIMED_OUT, FAILED, CANCELLED)
        into COMPLETED — doing so would corrupt the lifecycle audit trail.
        Manual completion runs the same accumulated-evidence coercion analysis as
        automatic completion so both paths stay consistent.
        """
        session = await self.repository.get_call_session_by_id(call_id)
        if session is None:
            raise NotFoundError(f"Call session with ID '{call_id}' not found")

        if session.status == CallSessionStatus.COMPLETED.value:
            return session

        if session.status in TERMINAL_CALL_STATUSES:
            raise ConflictError(
                f"Cannot complete call session in terminal status '{session.status}'"
            )

        # Snapshot coercion signals from the recorded turns before mutating/committing.
        turns = list(session.conversation.turns) if session.conversation else []
        snapshots = _snapshot_turns(turns)
        transaction_id = session.transaction_id

        now = datetime.now(UTC)
        session.status = CallSessionStatus.COMPLETED.value
        session.ended_at = now
        if session.connected_at:
            session.duration_seconds = max(
                1, int((session.ended_at - session.connected_at).total_seconds())
            )

        await self._maybe_link_coercion_analysis(
            session=session,
            snapshots=snapshots,
            transaction_id=transaction_id,
            correlation_id=correlation_id,
        )
        return await self.repository.update_call_session(session)

    async def decline_call_session(
        self, call_id: UUID, reason: str | None = None
    ) -> TransactionCallSessionModel:
        """Record customer decline of an incoming simulated call."""
        session = await self.repository.get_call_session_by_id(call_id)
        if session is None:
            raise NotFoundError(f"Call session with ID '{call_id}' not found")

        if session.status == CallSessionStatus.DECLINED.value:
            return session

        if session.status in TERMINAL_CALL_STATUSES:
            raise ConflictError(
                f"Cannot decline call session in terminal status '{session.status}'"
            )

        session.status = CallSessionStatus.DECLINED.value
        session.ended_at = datetime.now(UTC)
        session.failure_reason = reason or "DECLINED_BY_CUSTOMER"
        return await self.repository.update_call_session(session)

    async def get_call_session(self, call_id: UUID) -> TransactionCallSessionModel:
        """Retrieve full details of a call session."""
        session = await self.repository.get_call_session_by_id(call_id)
        if session is None:
            raise NotFoundError(f"Call session with ID '{call_id}' not found")
        return session

    async def get_latest_session_for_transaction(
        self, transaction_id: UUID
    ) -> TransactionCallSessionModel | None:
        """Retrieve the most recent call session for a transaction."""
        await self.transaction_service.get_transaction(transaction_id)
        return await self.repository.get_latest_call_session_for_transaction(transaction_id)

    async def list_sessions_for_transaction(
        self, transaction_id: UUID
    ) -> list[TransactionCallSessionModel]:
        """List all call sessions for a transaction."""
        await self.transaction_service.get_transaction(transaction_id)
        return await self.repository.list_call_sessions_for_transaction(transaction_id)
