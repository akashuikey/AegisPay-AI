"""Automated fraud response orchestration & customer intervention service (P2-A7).

Coordinates the deterministic decision workflow, transaction lifecycle state transitions,
customer intervention generation, and simulated customer notification dispatch.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.core.errors import ConflictError, StaleDecisionError
from app.core.logging import get_logger
from app.db.models import (
    TransactionModel,
    TransactionNotificationModel,
    TransactionResponseModel,
)
from app.domain.decision_policy import PolicyAction
from app.domain.response_orchestration import (
    ACTION_TO_RESPONSE_TYPE,
    NotificationChannel,
    NotificationDeliveryStatus,
    ResponseProcessingStatus,
    build_customer_intervention,
)
from app.domain.state_machine import ActorType, is_terminal
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.fraud_response import CustomerInterventionResponse
from app.services.decision_workflow_service import DecisionWorkflowService
from app.services.notification_service import SimulatedNotificationService
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)


class ResponseOrchestrationService:
    """Orchestrates policy-authorized automated responses and customer interventions."""

    def __init__(
        self,
        repository: TransactionRepository,
        transaction_service: TransactionService,
        workflow_service: DecisionWorkflowService,
        notification_service: SimulatedNotificationService | None = None,
    ) -> None:
        self.repository = repository
        self.transaction_service = transaction_service
        self.workflow_service = workflow_service
        self.notification_service = notification_service or SimulatedNotificationService()

    async def get_latest_response(self, transaction_id: UUID) -> TransactionResponseModel | None:
        """Fetch the latest automated response for a transaction."""
        await self.transaction_service.get_transaction(transaction_id)
        return await self.repository.get_latest_response_for_transaction(transaction_id)

    async def list_responses(self, transaction_id: UUID) -> list[TransactionResponseModel]:
        """Fetch all automated responses for a transaction in chronological order."""
        await self.transaction_service.get_transaction(transaction_id)
        return await self.repository.list_responses_for_transaction(transaction_id)

    async def orchestrate_response(
        self,
        transaction_id: UUID,
        *,
        idempotency_key: str | None = None,
        channel: NotificationChannel = NotificationChannel.IN_APP_SIMULATED,
        simulate_notification_failure: bool = False,
        actor_type: ActorType = ActorType.SYSTEM,
    ) -> tuple[TransactionResponseModel, TransactionModel, bool]:
        """Execute automated response orchestration.

        Returns (response, transaction, created).
        Idempotent: Replaying with the same idempotency key or on an already-responded
        decision returns the existing response without duplicate transitions or alerts.
        """
        # 1. Idempotency Key check
        if idempotency_key is not None:
            existing = await self.repository.get_response_by_idempotency_key(
                transaction_id, idempotency_key
            )
            if existing is not None:
                logger.info(
                    "Idempotent response replay for tx=%s with idempotency_key=%s",
                    transaction_id,
                    idempotency_key,
                )
                tx = await self.transaction_service.get_transaction(transaction_id)
                return existing, tx, False

        # 2. Transaction and decision verification
        tx = await self.transaction_service.get_transaction(transaction_id)
        decision = await self.workflow_service.get_latest_decision(transaction_id)

        if decision is None:
            if is_terminal(tx.state):
                raise ConflictError(
                    f"Transaction {transaction_id} is in terminal state '{tx.state}' and "
                    "cannot execute a new response",
                    details={"transaction_id": str(transaction_id), "state": tx.state},
                )
            decision, tx, _ = await self.workflow_service.evaluate(transaction_id)
        else:
            # Check if a response already exists for this exact decision
            existing_for_decision = await self.repository.get_response_by_decision_id(decision.id)
            if existing_for_decision is not None:
                logger.info(
                    "Response already executed for decision=%s tx=%s",
                    decision.id,
                    transaction_id,
                )
                return existing_for_decision, tx, False

            # Stale Decision validation: verify transaction has not mutated to an incompatible state
            if tx.state != decision.to_state:
                if is_terminal(tx.state):
                    raise StaleDecisionError(
                        f"Transaction state has evolved to '{tx.state}', "
                        f"decision '{decision.id}' is stale",
                        details={
                            "transaction_id": str(transaction_id),
                            "current_state": tx.state,
                            "decision_to_state": decision.to_state,
                        },
                    )

        policy_action = PolicyAction(decision.action)
        response_type = ACTION_TO_RESPONSE_TYPE[policy_action]

        # 4. Generate customer-safe intervention content
        intervention = build_customer_intervention(
            action=policy_action,
            amount=tx.amount,
            currency=tx.currency,
            recipient=tx.recipient_name,
            reference=tx.purpose,
        )

        # Cache scalar values before persistence operations that could roll back
        tx_id = transaction_id
        decision_id = decision.id
        recipient_raw = tx.recipient_identifier or tx.customer_id

        response_id = uuid4()
        response_model = TransactionResponseModel(
            id=response_id,
            transaction_id=tx_id,
            decision_id=decision_id,
            response_type=response_type.value,
            action=policy_action.value,
            processing_status=ResponseProcessingStatus.COMPLETED.value,
            from_state=decision.from_state,
            to_state=decision.to_state,
            headline=intervention.headline,
            customer_message=intervention.customer_message,
            customer_action_required=intervention.customer_action_required.value,
            next_steps=intervention.next_steps,
            idempotency_key=idempotency_key,
        )

        try:
            saved_response = await self.repository.create_response(response_model)
        except IntegrityError:
            # Racing request won the insert
            await self.repository.session.rollback()
            winner = await self.repository.get_latest_response_for_transaction(tx_id)
            if winner is not None:
                refreshed_tx = await self.transaction_service.get_transaction(tx_id)
                return winner, refreshed_tx, False
            raise

        # 5. Dispatch simulated notification
        notification_id = uuid4()
        dispatch_result = await self.notification_service.dispatch(
            transaction_id=tx_id,
            response_id=response_id,
            channel=channel,
            recipient_raw=recipient_raw,
            subject=f"Aster Bank Safety Alert: {intervention.headline}",
            message_body=intervention.customer_message,
            simulate_failure=simulate_notification_failure,
            idempotency_key=f"{response_id}:{channel.value}",
        )

        notification_model = TransactionNotificationModel(
            id=notification_id,
            response_id=response_id,
            transaction_id=tx_id,
            channel=dispatch_result.channel.value,
            recipient_masked=dispatch_result.recipient_masked,
            subject=dispatch_result.subject,
            message_body=dispatch_result.message_body,
            delivery_status=dispatch_result.delivery_status.value,
            failure_reason=dispatch_result.failure_reason,
            idempotency_key=dispatch_result.idempotency_key,
            delivered_at=dispatch_result.delivered_at,
        )

        try:
            await self.repository.create_notification(notification_model)
        except IntegrityError:
            await self.repository.session.rollback()
            logger.warning(
                "Duplicate notification suppressed for response=%s channel=%s",
                response_id,
                channel.value,
            )

        notifications = await self.repository.get_notifications_for_response(response_id)
        refreshed_response = await self.repository.get_response_by_id(response_id)
        final_response = refreshed_response or saved_response
        final_response.notifications = notifications
        refreshed_tx = await self.transaction_service.get_transaction(tx_id)

        logger.info(
            "Automated response executed for tx=%s: type=%s action=%s notification=%s",
            tx_id,
            response_type.value,
            policy_action.value,
            dispatch_result.delivery_status.value,
        )
        return final_response, refreshed_tx, True

    async def get_customer_intervention(self, transaction_id: UUID) -> CustomerInterventionResponse:
        """Return customer-safe intervention details for a transaction.

        Guarantees: Zero sensitive internal rules or risk scores are surfaced.
        """
        tx = await self.transaction_service.get_transaction(transaction_id)
        latest_response = await self.repository.get_latest_response_for_transaction(transaction_id)

        if latest_response is not None:
            notifications = latest_response.notifications or []
            delivered = any(
                n.delivery_status == NotificationDeliveryStatus.DELIVERED_SIMULATED.value
                for n in notifications
            )
            primary_channel = notifications[0].channel if notifications else "IN_APP_SIMULATED"
            return CustomerInterventionResponse(
                transaction_id=tx.id,
                response_type=latest_response.response_type,
                headline=latest_response.headline,
                customer_message=latest_response.customer_message,
                customer_action_required=latest_response.customer_action_required,
                next_steps=latest_response.next_steps,
                simulated_payment_status=tx.state,
                notification_delivered=delivered,
                notification_channel=primary_channel,
                is_simulated=True,
            )

        # Fallback when no response record exists yet: build from transaction state
        if tx.state == "SETTLED_SIMULATED":
            action = PolicyAction.ALLOW
        elif tx.state == "CANCELLED_SIMULATED":
            action = PolicyAction.BLOCK
        elif tx.state in ("VERIFICATION_REQUIRED", "HELD_FOR_VERIFICATION"):
            action = (
                PolicyAction.REQUIRE_VERIFICATION
                if tx.state == "VERIFICATION_REQUIRED"
                else PolicyAction.HOLD_FOR_INVESTIGATION
            )
        else:
            action = PolicyAction.ALLOW

        intervention = build_customer_intervention(
            action=action,
            amount=tx.amount,
            currency=tx.currency,
            recipient=tx.recipient_name,
            reference=tx.purpose,
        )
        return CustomerInterventionResponse(
            transaction_id=tx.id,
            response_type=ACTION_TO_RESPONSE_TYPE[action].value,
            headline=intervention.headline,
            customer_message=intervention.customer_message,
            customer_action_required=intervention.customer_action_required.value,
            next_steps=intervention.next_steps,
            simulated_payment_status=tx.state,
            notification_delivered=False,
            notification_channel="IN_APP_SIMULATED",
            is_simulated=True,
        )
