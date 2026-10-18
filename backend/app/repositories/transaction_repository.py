"""Repository for persistent transaction and audit operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConcurrencyConflictError
from app.core.logging import get_logger
from app.db.models import (
    CallLiveAnalysisModel,
    CallTranscriptSegmentModel,
    InvestigationConversationModel,
    InvestigationConversationTurnModel,
    ScenarioRunModel,
    TransactionAssessmentModel,
    TransactionAuditModel,
    TransactionCallSessionModel,
    TransactionCoercionAnalysisModel,
    TransactionDecisionModel,
    TransactionInvestigationModel,
    TransactionModel,
    TransactionNotificationModel,
    TransactionResponseModel,
    VerificationChallengeModel,
)

logger = get_logger(__name__)


class TransactionRepository:
    """Handles database persistence and queries for transactions and their audit trail."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, transaction_id: UUID) -> TransactionModel | None:
        """Fetch a transaction by primary key."""
        stmt = select(TransactionModel).where(TransactionModel.id == transaction_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_customer_and_idempotency_key(
        self, customer_id: str, idempotency_key: str
    ) -> TransactionModel | None:
        """Fetch a transaction by customer_id and idempotency_key."""
        stmt = select(TransactionModel).where(
            TransactionModel.customer_id == customer_id,
            TransactionModel.idempotency_key == idempotency_key,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        transaction: TransactionModel,
        initial_audit: TransactionAuditModel,
    ) -> TransactionModel:
        """Atomically persist a new transaction and its initial audit entry.

        Raises:
            IntegrityError: If unique constraint on (customer_id, idempotency_key) is violated.
        """
        self.session.add(transaction)
        self.session.add(initial_audit)
        try:
            await self.session.commit()
            await self.session.refresh(transaction)
            return transaction
        except IntegrityError:
            await self.session.rollback()
            raise

    async def list_transactions(
        self,
        limit: int = 50,
        offset: int = 0,
        customer_id: str | None = None,
        state: str | None = None,
    ) -> tuple[list[TransactionModel], int]:
        """Fetch paginated transactions ordered by creation date descending, with total count."""
        # Base count statement
        count_stmt = select(func.count(TransactionModel.id))
        query_stmt = select(TransactionModel).order_by(TransactionModel.created_at.desc())

        if customer_id is not None:
            count_stmt = count_stmt.where(TransactionModel.customer_id == customer_id)
            query_stmt = query_stmt.where(TransactionModel.customer_id == customer_id)

        if state is not None:
            count_stmt = count_stmt.where(TransactionModel.state == state)
            query_stmt = query_stmt.where(TransactionModel.state == state)

        # Execute total count
        count_result = await self.session.execute(count_stmt)
        total: int = count_result.scalar_one() or 0

        # Execute paginated query
        query_stmt = query_stmt.limit(limit).offset(offset)
        result = await self.session.execute(query_stmt)
        items = list(result.scalars().all())

        return items, total

    async def update_state(
        self,
        transaction_id: UUID,
        expected_version: int,
        new_state: str,
        audit_entry: TransactionAuditModel,
    ) -> TransactionModel:
        """Execute an atomic state transition with optimistic concurrency locking and audit logging.

        Raises:
            ConcurrencyConflictError: If the transaction version does not match expected_version.
        """
        stmt = (
            update(TransactionModel)
            .where(
                TransactionModel.id == transaction_id,
                TransactionModel.version == expected_version,
            )
            .values(
                state=new_state,
                version=expected_version + 1,
            )
            .execution_options(synchronize_session="fetch")
        )

        result = await self.session.execute(stmt)
        if isinstance(result, CursorResult) and result.rowcount == 0:
            await self.session.rollback()
            raise ConcurrencyConflictError(
                f"Transaction {transaction_id} was updated concurrently (version mismatch); "
                "please reload and retry"
            )

        self.session.add(audit_entry)
        await self.session.commit()

        updated_tx = await self.get_by_id(transaction_id)
        if updated_tx is None:
            raise ConcurrencyConflictError(f"Transaction {transaction_id} no longer exists")
        return updated_tx

    async def get_audit_history(self, transaction_id: UUID) -> list[TransactionAuditModel]:
        """Fetch complete audit history for a given transaction ordered chronologically."""
        stmt = (
            select(TransactionAuditModel)
            .where(TransactionAuditModel.transaction_id == transaction_id)
            .order_by(TransactionAuditModel.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_assessment(
        self, assessment: TransactionAssessmentModel
    ) -> TransactionAssessmentModel:
        """Persist a deterministic risk assessment record."""
        self.session.add(assessment)
        await self.session.commit()
        await self.session.refresh(assessment)
        return assessment

    async def get_latest_assessment(
        self, transaction_id: UUID
    ) -> TransactionAssessmentModel | None:
        """Retrieve the most recent risk assessment for a transaction."""
        stmt = (
            select(TransactionAssessmentModel)
            .where(TransactionAssessmentModel.transaction_id == transaction_id)
            .order_by(TransactionAssessmentModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_investigation(
        self, investigation: TransactionInvestigationModel
    ) -> TransactionInvestigationModel:
        """Persist an AI investigation record."""
        self.session.add(investigation)
        await self.session.commit()
        await self.session.refresh(investigation)
        return investigation

    async def get_investigation_by_id(
        self, investigation_id: UUID
    ) -> TransactionInvestigationModel | None:
        """Retrieve an investigation by primary key."""
        stmt = select(TransactionInvestigationModel).where(
            TransactionInvestigationModel.id == investigation_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_investigations_for_transaction(
        self, transaction_id: UUID
    ) -> list[TransactionInvestigationModel]:
        """Fetch all investigations associated with a transaction ordered chronologically desc."""
        stmt = (
            select(TransactionInvestigationModel)
            .where(TransactionInvestigationModel.transaction_id == transaction_id)
            .order_by(TransactionInvestigationModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_challenge(
        self, challenge: VerificationChallengeModel
    ) -> VerificationChallengeModel:
        """Persist a new verification challenge.

        Rolls back on IntegrityError (e.g. concurrent creation).
        """
        self.session.add(challenge)
        try:
            await self.session.commit()
            await self.session.refresh(challenge)
            return challenge
        except IntegrityError:
            await self.session.rollback()
            raise

    async def get_challenge_by_id(self, challenge_id: UUID) -> VerificationChallengeModel | None:
        """Fetch a verification challenge by primary key."""
        stmt = select(VerificationChallengeModel).where(
            VerificationChallengeModel.id == challenge_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_pending_challenge(
        self, transaction_id: UUID
    ) -> VerificationChallengeModel | None:
        """Fetch the latest PENDING challenge for a transaction, if any."""
        stmt = (
            select(VerificationChallengeModel)
            .where(
                VerificationChallengeModel.transaction_id == transaction_id,
                VerificationChallengeModel.status == "PENDING",
            )
            .order_by(VerificationChallengeModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_recent_challenges_for_transaction(
        self, transaction_id: UUID, window_seconds: int
    ) -> int:
        """Count challenges created for a transaction within a recent time window."""
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(seconds=window_seconds)
        stmt = (
            select(func.count())
            .select_from(VerificationChallengeModel)
            .where(
                VerificationChallengeModel.transaction_id == transaction_id,
                VerificationChallengeModel.created_at >= cutoff,
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def update_challenge_fields(
        self, challenge_id: UUID, expected_version: int, values: dict[str, Any]
    ) -> bool:
        """Atomically update a challenge guarded by its version (optimistic lock).

        Returns True iff exactly one row was updated (the caller won the race).
        Always bumps the version. Commits on success.
        """
        payload = dict(values)
        payload["version"] = expected_version + 1
        stmt = (
            update(VerificationChallengeModel)
            .where(
                VerificationChallengeModel.id == challenge_id,
                VerificationChallengeModel.version == expected_version,
            )
            .values(**payload)
        )
        result = await self.session.execute(stmt)
        won = isinstance(result, CursorResult) and result.rowcount == 1
        if won:
            await self.session.commit()
        return won

    async def set_challenge_decision(
        self, challenge_id: UUID, decision_id: UUID, status: str
    ) -> None:
        """Link a resolved decision to the challenge and set its terminal status."""
        stmt = (
            update(VerificationChallengeModel)
            .where(VerificationChallengeModel.id == challenge_id)
            .values(decision_id=decision_id, status=status, consumed_at=func.now())
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def create_decision(self, decision: TransactionDecisionModel) -> TransactionDecisionModel:
        """Persist an automated workflow decision record."""
        self.session.add(decision)
        await self.session.commit()
        await self.session.refresh(decision)
        return decision

    async def get_latest_decision_for_transaction(
        self, transaction_id: UUID
    ) -> TransactionDecisionModel | None:
        """Retrieve the most recent decision record for a transaction."""
        stmt = (
            select(TransactionDecisionModel)
            .where(TransactionDecisionModel.transaction_id == transaction_id)
            .order_by(TransactionDecisionModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_conversation(
        self, conversation: InvestigationConversationModel
    ) -> InvestigationConversationModel:
        """Persist a new investigation conversation."""
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_conversation_by_id(
        self, conversation_id: UUID
    ) -> InvestigationConversationModel | None:
        """Fetch an investigation conversation by ID with turns loaded."""
        stmt = (
            select(InvestigationConversationModel)
            .where(InvestigationConversationModel.id == conversation_id)
            .options(selectinload(InvestigationConversationModel.turns))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_conversation_for_transaction(
        self, transaction_id: UUID, conversation_type: str = "OPERATOR_INVESTIGATION"
    ) -> InvestigationConversationModel | None:
        """Fetch active (or latest) conversation for a transaction and conversation_type."""
        stmt = (
            select(InvestigationConversationModel)
            .where(
                InvestigationConversationModel.transaction_id == transaction_id,
                InvestigationConversationModel.conversation_type == conversation_type,
                InvestigationConversationModel.status == "ACTIVE",
            )
            .order_by(InvestigationConversationModel.created_at.desc())
            .options(selectinload(InvestigationConversationModel.turns))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        conv = result.scalar_one_or_none()
        if conv:
            return conv

        stmt_latest = (
            select(InvestigationConversationModel)
            .where(
                InvestigationConversationModel.transaction_id == transaction_id,
                InvestigationConversationModel.conversation_type == conversation_type,
            )
            .order_by(InvestigationConversationModel.created_at.desc())
            .options(selectinload(InvestigationConversationModel.turns))
            .limit(1)
        )
        result_latest = await self.session.execute(stmt_latest)
        return result_latest.scalar_one_or_none()

    async def list_conversations_for_transaction(
        self, transaction_id: UUID
    ) -> list[InvestigationConversationModel]:
        """Fetch all conversations for a transaction ordered by created_at desc."""
        stmt = (
            select(InvestigationConversationModel)
            .where(InvestigationConversationModel.transaction_id == transaction_id)
            .order_by(InvestigationConversationModel.created_at.desc())
            .options(selectinload(InvestigationConversationModel.turns))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_conversation_turn(
        self, turn: InvestigationConversationTurnModel
    ) -> InvestigationConversationTurnModel:
        """Persist a new turn for an investigation conversation.

        Rolls back on IntegrityError (e.g. a concurrent submission racing for the
        same ``(conversation_id, turn_index)``) and re-raises so callers can map it
        to a safe conflict response.
        """
        self.session.add(turn)
        try:
            await self.session.commit()
            await self.session.refresh(turn)
            return turn
        except IntegrityError:
            await self.session.rollback()
            raise

    async def update_conversation(
        self,
        conversation_id: UUID,
        turn_count: int,
        current_version: int,
        status: str | None = None,
    ) -> InvestigationConversationModel:
        """Update conversation turn count, status, and version with optimistic locking."""
        values: dict[str, Any] = {
            "turn_count": turn_count,
            "version": current_version + 1,
            "updated_at": func.now(),
        }
        if status is not None:
            values["status"] = status

        stmt = (
            update(InvestigationConversationModel)
            .where(
                InvestigationConversationModel.id == conversation_id,
                InvestigationConversationModel.version == current_version,
            )
            .values(**values)
        )
        result = await self.session.execute(stmt)
        if isinstance(result, CursorResult) and result.rowcount == 0:
            raise ConcurrencyConflictError(
                f"Conversation {conversation_id} was modified concurrently. Please reload."
            )
        await self.session.commit()
        self.session.expire_all()
        conv = await self.get_conversation_by_id(conversation_id)
        assert conv is not None
        return conv

    async def create_coercion_analysis(
        self, analysis: TransactionCoercionAnalysisModel
    ) -> TransactionCoercionAnalysisModel:
        """Persist a new transaction coercion analysis record."""
        self.session.add(analysis)
        await self.session.commit()
        await self.session.refresh(analysis)
        return analysis

    async def get_latest_coercion_analysis(
        self, transaction_id: UUID
    ) -> TransactionCoercionAnalysisModel | None:
        """Fetch the most recent coercion analysis for a transaction."""
        stmt = (
            select(TransactionCoercionAnalysisModel)
            .where(TransactionCoercionAnalysisModel.transaction_id == transaction_id)
            .order_by(TransactionCoercionAnalysisModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_coercion_analysis_by_id(
        self, analysis_id: UUID
    ) -> TransactionCoercionAnalysisModel | None:
        """Fetch a coercion analysis by its primary key."""
        stmt = select(TransactionCoercionAnalysisModel).where(
            TransactionCoercionAnalysisModel.id == analysis_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # --- P2-A7: Automated Fraud Response & Notification Persistence ---

    async def create_response(self, response: TransactionResponseModel) -> TransactionResponseModel:
        """Persist a new transaction response record."""
        self.session.add(response)
        await self.session.commit()
        await self.session.refresh(response, ["notifications"])
        return response

    async def get_response_by_id(self, response_id: UUID) -> TransactionResponseModel | None:
        """Fetch a transaction response with notifications loaded eagerly."""
        stmt = (
            select(TransactionResponseModel)
            .where(TransactionResponseModel.id == response_id)
            .options(selectinload(TransactionResponseModel.notifications))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_response_by_decision_id(
        self, decision_id: UUID
    ) -> TransactionResponseModel | None:
        """Fetch the response associated with a specific decision."""
        stmt = (
            select(TransactionResponseModel)
            .where(TransactionResponseModel.decision_id == decision_id)
            .options(selectinload(TransactionResponseModel.notifications))
            .order_by(TransactionResponseModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_response_for_transaction(
        self, transaction_id: UUID
    ) -> TransactionResponseModel | None:
        """Fetch the latest response for a transaction."""
        stmt = (
            select(TransactionResponseModel)
            .where(TransactionResponseModel.transaction_id == transaction_id)
            .options(selectinload(TransactionResponseModel.notifications))
            .order_by(TransactionResponseModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_responses_for_transaction(
        self, transaction_id: UUID
    ) -> list[TransactionResponseModel]:
        """List all responses for a transaction in chronological order."""
        stmt = (
            select(TransactionResponseModel)
            .where(TransactionResponseModel.transaction_id == transaction_id)
            .options(selectinload(TransactionResponseModel.notifications))
            .order_by(TransactionResponseModel.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_response_by_idempotency_key(
        self, transaction_id: UUID, idempotency_key: str
    ) -> TransactionResponseModel | None:
        """Fetch a response by transaction and idempotency key."""
        stmt = (
            select(TransactionResponseModel)
            .where(
                TransactionResponseModel.transaction_id == transaction_id,
                TransactionResponseModel.idempotency_key == idempotency_key,
            )
            .options(selectinload(TransactionResponseModel.notifications))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_notification(
        self, notification: TransactionNotificationModel
    ) -> TransactionNotificationModel:
        """Persist a new transaction notification record."""
        self.session.add(notification)
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def get_notifications_for_response(
        self, response_id: UUID
    ) -> list[TransactionNotificationModel]:
        """List notifications belonging to a response."""
        stmt = (
            select(TransactionNotificationModel)
            .where(TransactionNotificationModel.response_id == response_id)
            .order_by(TransactionNotificationModel.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_notification_by_channel(
        self, response_id: UUID, channel: str
    ) -> TransactionNotificationModel | None:
        """Fetch an existing notification for a response on a specific channel."""
        stmt = select(TransactionNotificationModel).where(
            TransactionNotificationModel.response_id == response_id,
            TransactionNotificationModel.channel == channel,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # --- P2-A8: End-to-End Scenario Simulation Run Persistence ---

    async def create_scenario_run(self, run: ScenarioRunModel) -> ScenarioRunModel:
        """Persist a new scenario run. Rolls back on IntegrityError (duplicate key)."""
        self.session.add(run)
        try:
            await self.session.commit()
            await self.session.refresh(run)
            return run
        except IntegrityError:
            await self.session.rollback()
            raise

    async def get_scenario_run_by_id(self, run_id: UUID) -> ScenarioRunModel | None:
        """Fetch a scenario run by primary key."""
        stmt = select(ScenarioRunModel).where(ScenarioRunModel.id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_scenario_run_by_idempotency_key(
        self, idempotency_key: str
    ) -> ScenarioRunModel | None:
        """Fetch a scenario run by its idempotency key."""
        stmt = select(ScenarioRunModel).where(ScenarioRunModel.idempotency_key == idempotency_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_scenario_runs(
        self, limit: int = 50, offset: int = 0, scenario_id: str | None = None
    ) -> tuple[list[ScenarioRunModel], int]:
        """List scenario runs (most recent first) with a total count."""
        count_stmt = select(func.count(ScenarioRunModel.id))
        query_stmt = select(ScenarioRunModel).order_by(ScenarioRunModel.created_at.desc())
        if scenario_id is not None:
            count_stmt = count_stmt.where(ScenarioRunModel.scenario_id == scenario_id)
            query_stmt = query_stmt.where(ScenarioRunModel.scenario_id == scenario_id)
        total = (await self.session.execute(count_stmt)).scalar_one() or 0
        query_stmt = query_stmt.limit(limit).offset(offset)
        result = await self.session.execute(query_stmt)
        return list(result.scalars().all()), int(total)

    async def update_scenario_run(
        self,
        run_id: UUID,
        *,
        status: str,
        stages: list[dict[str, Any]],
        transaction_id: UUID | None = None,
        ai_provider: str | None = None,
        error_category: str | None = None,
        detail: str | None = None,
    ) -> ScenarioRunModel:
        """Persist the run's status, stage timeline, and references."""
        values: dict[str, Any] = {
            "status": status,
            "stages": stages,
            "updated_at": func.now(),
        }
        if transaction_id is not None:
            values["transaction_id"] = transaction_id
        values["ai_provider"] = ai_provider
        values["error_category"] = error_category
        values["detail"] = detail

        stmt = update(ScenarioRunModel).where(ScenarioRunModel.id == run_id).values(**values)
        await self.session.execute(stmt)
        await self.session.commit()
        refreshed = await self.get_scenario_run_by_id(run_id)
        if refreshed is None:
            raise ConcurrencyConflictError(f"Scenario run {run_id} no longer exists")
        return refreshed

    async def create_call_session(
        self, session: TransactionCallSessionModel
    ) -> TransactionCallSessionModel:
        """Persist a new simulated customer call session.

        Rolls back on IntegrityError (duplicate idempotency key or a concurrent
        initiation racing for the single active-session slot) and re-raises so the
        caller can resolve the conflict safely.
        """
        session_id = session.id
        self.session.add(session)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise
        refreshed = await self.get_call_session_by_id(session_id)
        return refreshed or session

    async def get_call_session_by_id(self, call_id: UUID) -> TransactionCallSessionModel | None:
        """Fetch a call session by ID with its conversation, turns, and coercion analysis loaded."""
        stmt = (
            select(TransactionCallSessionModel)
            .where(TransactionCallSessionModel.id == call_id)
            .options(
                selectinload(TransactionCallSessionModel.conversation).selectinload(
                    InvestigationConversationModel.turns
                ),
                selectinload(TransactionCallSessionModel.coercion_analysis),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_call_session_by_idempotency_key(
        self, transaction_id: UUID, idempotency_key: str
    ) -> TransactionCallSessionModel | None:
        """Fetch a call session by transaction_id and idempotency_key."""
        stmt = (
            select(TransactionCallSessionModel)
            .where(
                TransactionCallSessionModel.transaction_id == transaction_id,
                TransactionCallSessionModel.idempotency_key == idempotency_key,
            )
            .options(
                selectinload(TransactionCallSessionModel.conversation).selectinload(
                    InvestigationConversationModel.turns
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_call_session_for_transaction(
        self, transaction_id: UUID
    ) -> TransactionCallSessionModel | None:
        """Fetch an active (INITIATED, RINGING, or CONNECTED) call session for a transaction."""
        from app.domain.customer_dialogue import CallSessionStatus

        active_statuses = [
            CallSessionStatus.INITIATED.value,
            CallSessionStatus.RINGING.value,
            CallSessionStatus.CONNECTED.value,
        ]
        stmt = (
            select(TransactionCallSessionModel)
            .where(
                TransactionCallSessionModel.transaction_id == transaction_id,
                TransactionCallSessionModel.status.in_(active_statuses),
            )
            .order_by(TransactionCallSessionModel.created_at.desc())
            .options(
                selectinload(TransactionCallSessionModel.conversation).selectinload(
                    InvestigationConversationModel.turns
                )
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_call_session_for_transaction(
        self, transaction_id: UUID
    ) -> TransactionCallSessionModel | None:
        """Fetch the most recent call session for a transaction."""
        stmt = (
            select(TransactionCallSessionModel)
            .where(TransactionCallSessionModel.transaction_id == transaction_id)
            .order_by(TransactionCallSessionModel.created_at.desc())
            .options(
                selectinload(TransactionCallSessionModel.conversation).selectinload(
                    InvestigationConversationModel.turns
                ),
                selectinload(TransactionCallSessionModel.coercion_analysis),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_call_sessions_for_transaction(
        self, transaction_id: UUID
    ) -> list[TransactionCallSessionModel]:
        """Fetch all call sessions for a transaction in chronological order."""
        stmt = (
            select(TransactionCallSessionModel)
            .where(TransactionCallSessionModel.transaction_id == transaction_id)
            .order_by(TransactionCallSessionModel.created_at.asc())
            .options(
                selectinload(TransactionCallSessionModel.conversation).selectinload(
                    InvestigationConversationModel.turns
                )
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_call_session(
        self, session: TransactionCallSessionModel
    ) -> TransactionCallSessionModel:
        """Persist updates to an existing call session."""
        session_id = session.id
        session.version += 1
        await self.session.commit()
        refreshed = await self.get_call_session_by_id(session_id)
        return refreshed or session

    # --- P2-A11: Live voice transcript segments & incremental analysis ---

    async def create_transcript_segment(
        self, segment: CallTranscriptSegmentModel
    ) -> CallTranscriptSegmentModel:
        """Persist a final transcript segment.

        Rolls back and re-raises on IntegrityError (duplicate ``(call_session_id, seq)``
        from a reconnect/duplicate delivery) so the caller can skip it safely.
        """
        self.session.add(segment)
        try:
            await self.session.commit()
            await self.session.refresh(segment)
            return segment
        except IntegrityError:
            await self.session.rollback()
            raise

    async def get_max_transcript_seq(self, call_session_id: UUID) -> int | None:
        """Return the highest persisted transcript sequence for a call session, if any."""
        stmt = select(func.max(CallTranscriptSegmentModel.seq)).where(
            CallTranscriptSegmentModel.call_session_id == call_session_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_transcript_segments(
        self, call_session_id: UUID, after_seq: int | None = None
    ) -> list[CallTranscriptSegmentModel]:
        """List transcript segments for a call session ordered by sequence ascending."""
        stmt = select(CallTranscriptSegmentModel).where(
            CallTranscriptSegmentModel.call_session_id == call_session_id
        )
        if after_seq is not None:
            stmt = stmt.where(CallTranscriptSegmentModel.seq > after_seq)
        stmt = stmt.order_by(CallTranscriptSegmentModel.seq.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_live_analysis(self, analysis: CallLiveAnalysisModel) -> CallLiveAnalysisModel:
        """Persist an incremental live evidence-analysis snapshot."""
        self.session.add(analysis)
        await self.session.commit()
        await self.session.refresh(analysis)
        return analysis

    async def get_latest_live_analysis(self, call_session_id: UUID) -> CallLiveAnalysisModel | None:
        """Fetch the most recent live analysis snapshot for a call session."""
        stmt = (
            select(CallLiveAnalysisModel)
            .where(CallLiveAnalysisModel.call_session_id == call_session_id)
            .order_by(CallLiveAnalysisModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_live_analyses(self, call_session_id: UUID) -> list[CallLiveAnalysisModel]:
        """List all live analysis snapshots for a call session (chronological)."""
        stmt = (
            select(CallLiveAnalysisModel)
            .where(CallLiveAnalysisModel.call_session_id == call_session_id)
            .order_by(CallLiveAnalysisModel.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
