"""Automated transaction decision workflow orchestration (P2-A4).

Ties together the existing deterministic risk engine, the P2-A1 investigation
service, and the deterministic policy engine, then executes the resulting
action through the existing transaction state machine and persists an auditable
decision record. The policy engine selects the action; this service only
validates and applies the corresponding permitted transition. It never mutates
state directly and never lets the LLM choose the action.
"""

from uuid import UUID, uuid4

from app.core.errors import AIConfigurationError, AIProviderError, ConcurrencyConflictError
from app.core.logging import get_logger
from app.db.models import (
    TransactionAssessmentModel,
    TransactionCoercionAnalysisModel,
    TransactionDecisionModel,
    TransactionInvestigationModel,
    TransactionModel,
)
from app.domain.decision_policy import (
    CoercionSignal,
    InvestigationSignal,
    PolicyAction,
    PolicyDecision,
    PolicyInput,
    VerificationOutcome,
    VerificationSignal,
    decide,
)
from app.domain.investigation import RiskSentiment
from app.domain.risk_engine import RecommendedAction, RiskLevel, TransactionEvidence
from app.domain.state_machine import ActorType, TransactionState
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.investigation import InvestigateTransactionRequest
from app.schemas.transaction import TransitionTransactionRequest
from app.services.investigation_service import InvestigationService
from app.services.risk_service import RiskService
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)

# Action -> permitted target state (all reachable from DECISION_READY).
_ACTION_TARGET_STATE: dict[PolicyAction, TransactionState] = {
    PolicyAction.ALLOW: TransactionState.SETTLED_SIMULATED,
    PolicyAction.REQUIRE_VERIFICATION: TransactionState.VERIFICATION_REQUIRED,
    PolicyAction.HOLD_FOR_INVESTIGATION: TransactionState.HELD_FOR_VERIFICATION,
    PolicyAction.BLOCK: TransactionState.CANCELLED_SIMULATED,
}

_ACTION_WORKFLOW_STATUS: dict[PolicyAction, str] = {
    PolicyAction.ALLOW: "ALLOWED_SETTLED",
    PolicyAction.REQUIRE_VERIFICATION: "VERIFICATION_REQUIRED",
    PolicyAction.HOLD_FOR_INVESTIGATION: "HELD_FOR_INVESTIGATION",
    PolicyAction.BLOCK: "BLOCKED_CANCELLED",
}

# States at or beyond a decision: a fresh automated evaluation is not re-run.
_PRE_DECISION_STATES = frozenset(
    {
        TransactionState.INITIATED.value,
        TransactionState.ASSESSING.value,
        TransactionState.RISK_ASSESSED.value,
    }
)


class DecisionWorkflowService:
    """Coordinates the end-to-end automated evaluation and decision workflow."""

    def __init__(
        self,
        repository: TransactionRepository,
        transaction_service: TransactionService,
        risk_service: RiskService,
        investigation_service: InvestigationService,
    ) -> None:
        self.repository = repository
        self.transaction_service = transaction_service
        self.risk_service = risk_service
        self.investigation_service = investigation_service

    async def get_latest_decision(self, transaction_id: UUID) -> TransactionDecisionModel | None:
        """Return the latest decision for a transaction (ensures the transaction exists)."""
        await self.transaction_service.get_transaction(transaction_id)
        return await self.repository.get_latest_decision_for_transaction(transaction_id)

    async def evaluate(
        self,
        transaction_id: UUID,
        evidence: TransactionEvidence | None = None,
        investigation_request: InvestigateTransactionRequest | None = None,
        run_investigation: bool | None = None,
        correlation_id: str | None = None,
    ) -> tuple[TransactionDecisionModel, TransactionModel, bool]:
        """Run the automated workflow and return (decision, transaction, created).

        Idempotent: if a decision already exists for the transaction, it is returned
        unchanged (created=False) without re-running the workflow or re-transitioning.
        """
        tx = await self.transaction_service.get_transaction(transaction_id)

        # Idempotency: one automated decision per transaction. A repeat request
        # (including a retry of a held/verification outcome) returns the existing
        # decision rather than duplicating transitions or audit events.
        existing = await self.repository.get_latest_decision_for_transaction(transaction_id)
        if existing is not None:
            logger.info(
                "Idempotent workflow replay for tx=%s; returning existing decision %s",
                transaction_id,
                existing.id,
            )
            return existing, tx, False

        # 1. Deterministic risk assessment -> DECISION_READY (reuse existing service).
        assessment = await self._ensure_assessment(tx, evidence, correlation_id)
        tx = await self.transaction_service.get_transaction(transaction_id)

        risk_level = RiskLevel(assessment.risk_level)

        # 2. Decide whether contextual investigation is warranted. Deterministic
        #    low-risk transactions skip the LLM entirely.
        should_investigate = (
            run_investigation if run_investigation is not None else risk_level != RiskLevel.LOW
        )

        investigation: TransactionInvestigationModel | None = None
        provider_failed = False
        if should_investigate:
            investigation, provider_failed = await self._run_investigation_safely(
                transaction_id, investigation_request, correlation_id
            )

        # 3. Deterministic policy decision (LLM never selects the action).
        coercion_analysis = await self.repository.get_latest_coercion_analysis(transaction_id)
        policy_input = self._build_policy_input(
            assessment,
            investigation,
            provider_failed,
            coercion_analysis=coercion_analysis,
        )
        decision = decide(policy_input)

        # 4. Execute the corresponding permitted transition and persist the decision.
        return await self._apply_decision(tx, assessment, investigation, decision, provider_failed)

    async def _ensure_assessment(
        self,
        tx: TransactionModel,
        evidence: TransactionEvidence | None,
        correlation_id: str | None,
    ) -> TransactionAssessmentModel:
        """Ensure a risk assessment exists and the transaction is in DECISION_READY."""
        if tx.state in _PRE_DECISION_STATES:
            _, assessment = await self.risk_service.assess_transaction(
                transaction_id=tx.id,
                evidence=evidence,
                actor_type=ActorType.SYSTEM,
                reason="Automated decision workflow: deterministic risk evaluation",
                correlation_id=correlation_id,
            )
            return assessment

        # Already at/after DECISION_READY: reuse the latest assessment if present.
        latest = await self.repository.get_latest_assessment(tx.id)
        if latest is not None:
            return latest
        _, assessment = await self.risk_service.assess_transaction(
            transaction_id=tx.id,
            evidence=evidence,
            actor_type=ActorType.SYSTEM,
            reason="Automated decision workflow: deterministic risk evaluation",
            correlation_id=correlation_id,
        )
        return assessment

    async def _run_investigation_safely(
        self,
        transaction_id: UUID,
        investigation_request: InvestigateTransactionRequest | None,
        correlation_id: str | None,
    ) -> tuple[TransactionInvestigationModel | None, bool]:
        """Run the investigation, returning (record, provider_failed).

        A provider failure is caught and reported as a safe fallback signal; it
        never aborts the workflow and never downgrades risk.
        """
        request = investigation_request or InvestigateTransactionRequest(
            transaction_id=transaction_id,
            correlation_id=correlation_id,
        )
        # Force the request's transaction id to the path transaction (never trust
        # a caller-supplied mismatch) and carry the workflow correlation id.
        request = request.model_copy(
            update={"transaction_id": transaction_id, "correlation_id": correlation_id}
        )
        try:
            record = await self.investigation_service.investigate_transaction(request)
            return record, False
        except (AIProviderError, AIConfigurationError) as exc:
            logger.warning(
                "Investigation provider unavailable for tx=%s (%s); applying deterministic "
                "fallback without downgrading risk.",
                transaction_id,
                exc.code,
            )
            return None, True

    async def resolve_after_verification(
        self,
        transaction_id: UUID,
        verification_outcome: VerificationOutcome,
        correlation_id: str | None = None,
    ) -> tuple[TransactionDecisionModel, TransactionModel, bool]:
        """Re-evaluate a verification-required transaction after a verification outcome.

        Reuses the existing assessment and investigation (no re-assessment, no
        unnecessary new LLM call). Verification is an additional policy signal; it
        never settles on its own and never overrides strong fraud evidence. Moves
        the transaction VERIFICATION_REQUIRED -> INVESTIGATING -> DECISION_READY ->
        the policy-permitted terminal/hold state, all via the existing state machine.
        """
        tx = await self.transaction_service.get_transaction(transaction_id)

        assessment = await self.repository.get_latest_assessment(transaction_id)
        if assessment is None:
            # Should not happen: P2-A4 always persists an assessment before this state.
            _, assessment = await self.risk_service.assess_transaction(
                transaction_id=transaction_id,
                actor_type=ActorType.SYSTEM,
                reason="Verification re-evaluation: missing assessment recovery",
                correlation_id=correlation_id,
            )
            tx = await self.transaction_service.get_transaction(transaction_id)

        investigations = await self.repository.list_investigations_for_transaction(transaction_id)
        investigation = investigations[0] if investigations else None

        reason = f"Customer verification outcome: {verification_outcome.value}"
        if tx.state == TransactionState.VERIFICATION_REQUIRED.value:
            tx = await self.transaction_service.transition_transaction(
                transaction_id=tx.id,
                request=TransitionTransactionRequest(
                    target_state=TransactionState.INVESTIGATING,
                    actor_type=ActorType.CUSTOMER,
                    reason=reason,
                    correlation_id=correlation_id,
                ),
            )
        if tx.state == TransactionState.INVESTIGATING.value:
            tx = await self.transaction_service.transition_transaction(
                transaction_id=tx.id,
                request=TransitionTransactionRequest(
                    target_state=TransactionState.DECISION_READY,
                    actor_type=ActorType.POLICY_ENGINE,
                    reason="Deterministic policy re-evaluation after verification",
                    correlation_id=correlation_id,
                ),
            )

        coercion_analysis = await self.repository.get_latest_coercion_analysis(transaction_id)
        policy_input = self._build_policy_input(
            assessment,
            investigation,
            provider_failed=False,
            verification_outcome=verification_outcome,
            coercion_analysis=coercion_analysis,
        )
        decision = decide(policy_input)
        return await self._apply_decision(tx, assessment, investigation, decision, False)

    def _build_coercion_signal(
        self,
        coercion: TransactionCoercionAnalysisModel | None,
    ) -> CoercionSignal:
        if coercion is None:
            return CoercionSignal(available=False)

        if coercion.status == "UNAVAILABLE":
            return CoercionSignal(available=False, provider_failed=True)

        findings = coercion.findings or []
        explicit_findings = [
            f
            for f in findings
            if f.get("is_explicit") and f.get("category") != "LEGITIMATE_EXPLANATION"
        ]
        has_explicit = len(explicit_findings) > 0

        severities = [str(f.get("severity", "LOW")) for f in explicit_findings]
        highest_severity: str | None = None
        for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            if s in severities:
                highest_severity = s
                break

        has_legit = bool(coercion.legitimate_explanations)
        voice_signals = coercion.voice_stress_signals or {}
        voice_detected = bool(
            voice_signals.get("detected") or voice_signals.get("level") in ("ELEVATED", "HIGH")
        )
        voice_stress_only = voice_detected and not has_explicit

        finding_refs = [str(f.get("id")) for f in findings if f.get("id")]
        supporting_excerpts = [
            str(f.get("supporting_excerpt")) for f in findings if f.get("supporting_excerpt")
        ]

        return CoercionSignal(
            available=True,
            provider_failed=False,
            has_explicit_coercion=has_explicit,
            coercion_severity=highest_severity,
            has_legitimate_explanation=has_legit,
            voice_stress_only=voice_stress_only,
            finding_refs=finding_refs,
            supporting_excerpts=supporting_excerpts,
        )

    def _build_policy_input(
        self,
        assessment: TransactionAssessmentModel,
        investigation: TransactionInvestigationModel | None,
        provider_failed: bool,
        verification_outcome: VerificationOutcome | None = None,
        coercion_analysis: TransactionCoercionAnalysisModel | None = None,
    ) -> PolicyInput:
        triggered_rule_ids = [
            str(r.get("rule_id")) for r in assessment.triggered_rules if r.get("rule_id")
        ]

        if investigation is not None:
            finding_refs = [str(f.get("id")) for f in investigation.findings if f.get("id")]
            evidence_refs = sorted(
                {
                    str(ref)
                    for f in investigation.findings
                    for ref in f.get("supporting_evidence_references", [])
                }
            )
            signal = InvestigationSignal(
                available=True,
                provider_failed=False,
                sentiment=RiskSentiment(investigation.overall_risk_sentiment),
                finding_refs=finding_refs,
                evidence_refs=evidence_refs,
                missing_information=list(investigation.missing_information),
            )
        else:
            signal = InvestigationSignal(available=False, provider_failed=provider_failed)

        coercion_signal = self._build_coercion_signal(coercion_analysis)

        return PolicyInput(
            risk_score=assessment.risk_score,
            risk_level=RiskLevel(assessment.risk_level),
            recommended_action=RecommendedAction(assessment.recommended_action),
            triggered_rule_ids=triggered_rule_ids,
            missing_evidence=list(assessment.missing_evidence),
            investigation=signal,
            verification=VerificationSignal(outcome=verification_outcome),
            coercion=coercion_signal,
        )

    async def _apply_decision(
        self,
        tx: TransactionModel,
        assessment: TransactionAssessmentModel,
        investigation: TransactionInvestigationModel | None,
        decision: PolicyDecision,
        provider_failed: bool,
    ) -> tuple[TransactionDecisionModel, TransactionModel, bool]:
        target_state = _ACTION_TARGET_STATE[decision.action]
        from_state = tx.state

        reason = (
            f"[policy {decision.policy_version}] action={decision.action.value}; "
            f"reasons={', '.join(decision.reason_codes)}"
        )
        try:
            updated_tx = await self.transaction_service.transition_transaction(
                transaction_id=tx.id,
                request=TransitionTransactionRequest(
                    target_state=target_state,
                    actor_type=ActorType.POLICY_ENGINE,
                    reason=reason,
                    correlation_id=None,
                ),
            )
        except ConcurrencyConflictError:
            # A concurrent workflow won the race. Return its decision rather than
            # producing a conflicting outcome.
            existing = await self.repository.get_latest_decision_for_transaction(tx.id)
            if existing is not None:
                refreshed = await self.transaction_service.get_transaction(tx.id)
                return existing, refreshed, False
            raise

        decision_model = TransactionDecisionModel(
            id=uuid4(),
            transaction_id=tx.id,
            assessment_id=assessment.id,
            investigation_id=investigation.id if investigation is not None else None,
            policy_version=decision.policy_version,
            action=decision.action.value,
            risk_score=decision.risk_score,
            risk_level=decision.risk_level.value,
            requires_verification=decision.requires_verification,
            provider_failed=provider_failed,
            from_state=from_state,
            to_state=target_state.value,
            workflow_status=_ACTION_WORKFLOW_STATUS[decision.action],
            reason_codes=decision.reason_codes,
            triggered_rule_ids=decision.triggered_rule_ids,
            investigation_finding_refs=decision.investigation_finding_refs,
            supporting_evidence_refs=decision.supporting_evidence_refs,
            missing_information=decision.missing_information,
            explanation=decision.explanation,
        )
        saved = await self.repository.create_decision(decision_model)
        logger.info(
            "Automated decision for tx=%s: action=%s %s->%s (provider_failed=%s)",
            tx.id,
            decision.action.value,
            from_state,
            target_state.value,
            provider_failed,
        )
        return saved, updated_tx, True
