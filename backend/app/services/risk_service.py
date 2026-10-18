"""Application service coordinating deterministic risk evaluation and workflow integration."""

import uuid
from dataclasses import replace
from uuid import UUID

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import TransactionAssessmentModel, TransactionModel
from app.domain.risk_engine import (
    RiskAssessmentResult,
    TransactionEvidence,
    evaluate_risk,
)
from app.domain.state_machine import ActorType, TransactionState
from app.repositories.recipient_repository import RecipientRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.transaction import TransitionTransactionRequest
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)


class RiskService:
    """Orchestrates deterministic risk evaluation, lifecycle state changes, and persistence."""

    def __init__(
        self,
        repository: TransactionRepository,
        transaction_service: TransactionService,
        recipient_repository: RecipientRepository | None = None,
    ) -> None:
        self.repository = repository
        self.transaction_service = transaction_service
        self.recipient_repository = recipient_repository or (
            RecipientRepository(repository.session) if hasattr(repository, "session") else None
        )

    def evaluate_pure(self, evidence: TransactionEvidence) -> RiskAssessmentResult:
        """Execute pure deterministic feature evaluation without side-effects or persistence."""
        return evaluate_risk(evidence)

    async def assess_transaction(
        self,
        transaction_id: UUID,
        evidence: TransactionEvidence | None = None,
        actor_type: ActorType = ActorType.SYSTEM,
        reason: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[TransactionModel, TransactionAssessmentModel]:
        """Assess transaction risk and advance state through assessment lifecycle.

        Raises:
            NotFoundError: If transaction does not exist.
            InvalidStateTransitionError: If transaction cannot transition to assessment states.
        """
        tx = await self.transaction_service.get_transaction(transaction_id)

        # Ensure transaction is transitioned to ASSESSING
        if tx.state != TransactionState.ASSESSING.value:
            tx = await self.transaction_service.transition_transaction(
                transaction_id=tx.id,
                request=TransitionTransactionRequest(
                    target_state=TransactionState.ASSESSING,
                    actor_type=actor_type,
                    reason=reason or "Automated deterministic risk evaluation initiated",
                    correlation_id=correlation_id,
                ),
            )

        # Resolve recipient against authoritative database-backed registry if identifier present
        rec_record = None
        if self.recipient_repository is not None and tx.recipient_identifier:
            rec_record = await self.recipient_repository.get_by_upi_id(tx.recipient_identifier)

        # Merge transaction parameters into evidence
        if evidence is None:
            eval_evidence = TransactionEvidence(
                amount=tx.amount,
                currency=tx.currency,
                payment_rail=tx.payment_rail,
                recipient_name=tx.recipient_name,
                recipient_identifier=tx.recipient_identifier,
                purpose=tx.purpose,
                customer_id=tx.customer_id,
            )
        else:
            eval_evidence = replace(
                evidence,
                amount=tx.amount,
                currency=tx.currency,
                payment_rail=tx.payment_rail,
                recipient_name=evidence.recipient_name or tx.recipient_name,
                recipient_identifier=evidence.recipient_identifier or tx.recipient_identifier,
                purpose=evidence.purpose or tx.purpose,
                customer_id=evidence.customer_id or tx.customer_id,
            )

        if rec_record is not None:
            # Authoritative server-controlled signals take precedence over untrusted
            # client parameters
            is_first_time = not rec_record.is_trusted_beneficiary
            eval_evidence = replace(
                eval_evidence,
                is_trusted_beneficiary=rec_record.is_trusted_beneficiary,
                is_flagged_mule=rec_record.is_flagged_mule,
                recipient_account_age_days=rec_record.account_age_days,
                fan_in_count_24h=rec_record.fan_in_count_24h,
                fan_out_count_24h=rec_record.fan_out_count_24h,
                is_first_time_recipient=is_first_time,
            )

        # Execute deterministic risk engine evaluation
        result = evaluate_risk(eval_evidence)

        # Transition ASSESSING -> RISK_ASSESSED
        if tx.state == TransactionState.ASSESSING.value:
            tx = await self.transaction_service.transition_transaction(
                transaction_id=tx.id,
                request=TransitionTransactionRequest(
                    target_state=TransactionState.RISK_ASSESSED,
                    actor_type=actor_type,
                    reason=(
                        f"Risk evaluated: Score {result.risk_score} ({result.risk_level.value}). "
                        f"Rules triggered: {len(result.triggered_rules)}."
                    ),
                    correlation_id=correlation_id,
                ),
            )

        # Transition RISK_ASSESSED -> DECISION_READY
        if tx.state == TransactionState.RISK_ASSESSED.value:
            tx = await self.transaction_service.transition_transaction(
                transaction_id=tx.id,
                request=TransitionTransactionRequest(
                    target_state=TransactionState.DECISION_READY,
                    actor_type=actor_type,
                    reason=(
                        f"Decision policy synthesized: Recommended action is "
                        f"{result.recommended_action.value}."
                    ),
                    correlation_id=correlation_id,
                ),
            )

        # Persist assessment record atomically with enriched input snapshot
        snapshot = dict(result.input_snapshot)
        if rec_record is not None:
            snapshot["recipient_registry_hit"] = True
            snapshot["recipient_registry_id"] = str(rec_record.id)
            snapshot["recipient_category"] = (
                rec_record.category.value
                if hasattr(rec_record.category, "value")
                else str(rec_record.category)
            )
            snapshot["recipient_bank"] = rec_record.bank_name
            snapshot["recipient_branch"] = rec_record.branch_region
        else:
            snapshot["recipient_registry_hit"] = False

        assessment_model = TransactionAssessmentModel(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            risk_score=result.risk_score,
            risk_level=result.risk_level.value,
            recommended_action=result.recommended_action.value,
            explanation=result.explanation,
            triggered_rules=[
                {
                    "rule_id": r.rule_id,
                    "rule_name": r.rule_name,
                    "description": r.description,
                    "weight": r.weight,
                    "severity": r.severity.value,
                    "evidence": r.evidence,
                }
                for r in result.triggered_rules
            ],
            supporting_evidence=result.supporting_evidence,
            missing_evidence=result.missing_evidence,
            input_snapshot=snapshot,
        )
        saved_assessment = await self.repository.create_assessment(assessment_model)

        logger.info(
            "Completed risk assessment for tx=%s: score=%s level=%s action=%s",
            tx.id,
            result.risk_score,
            result.risk_level.value,
            result.recommended_action.value,
        )
        return tx, saved_assessment

    async def get_latest_assessment(self, transaction_id: UUID) -> TransactionAssessmentModel:
        """Fetch the latest assessment record for a transaction."""
        # Ensure transaction exists
        await self.transaction_service.get_transaction(transaction_id)
        assessment = await self.repository.get_latest_assessment(transaction_id)
        if assessment is None:
            raise NotFoundError(
                f"No risk assessment found for transaction with ID '{transaction_id}'"
            )
        return assessment
