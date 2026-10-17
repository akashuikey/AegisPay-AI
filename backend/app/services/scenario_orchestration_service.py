"""End-to-end fraud simulation orchestration service (P2-A8).

Runs a predefined scenario through the SAME application services the live product
uses (risk assessment, AI investigation, coercion analysis, decision workflow,
customer verification, response orchestration, notification) and records an
explainability timeline built from the real persisted artifacts.

Guardrails:
- No parallel risk engine or duplicated business logic: every stage delegates to
  an existing service.
- A scenario's declared expectation is never consulted here; the authoritative
  policy result is whatever the real pipeline produces.
- Deterministic mode injects the offline mock AI provider for reproducible demos;
  live-provider mode is explicit and never silently replaced by a mock.
- Stage results are derived from persisted records only — no fabricated stage,
  timestamp, evidence item, or notification result.
"""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import ScenarioRunModel
from app.domain.response_orchestration import NotificationChannel
from app.domain.risk_engine import TransactionEvidence
from app.domain.scenario_catalog import (
    CATALOG_VERSION,
    ScenarioDefinition,
    VerificationBehavior,
)
from app.domain.scenario_evaluation import ObservedOutcome
from app.domain.state_machine import TransactionState
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.coercion import AnalyzeCoercionRequest, VoiceStressInput
from app.schemas.investigation import (
    CustomerStatementEvidence,
    InvestigateTransactionRequest,
    RecipientIntelligenceEvidence,
    TelephonyTelemetryEvidence,
)
from app.schemas.scenario import ScenarioExecutionMode
from app.schemas.transaction import CreateTransactionRequest
from app.services.ai_client import AIInvestigationClient
from app.services.coercion_service import CoercionService
from app.services.decision_workflow_service import DecisionWorkflowService
from app.services.investigation_service import InvestigationService
from app.services.notification_service import SimulatedNotificationService
from app.services.response_orchestration_service import ResponseOrchestrationService
from app.services.risk_service import RiskService
from app.services.transaction_service import TransactionService
from app.services.verification_service import VerificationService

logger = get_logger(__name__)

# Canonical explainability-timeline stages (fixed display order, per P2-A8 §4).
_STAGE_ORDER: tuple[tuple[str, str], ...] = (
    ("transaction_created", "Transaction created"),
    ("risk_assessment", "Deterministic risk assessment"),
    ("ai_investigation", "AI investigation"),
    ("coercion_analysis", "Coercion analysis"),
    ("decision_policy", "Decision policy evaluated"),
    ("verification", "Customer verification"),
    ("response_orchestration", "Response orchestrated"),
    ("notification", "Customer notification"),
)
_STAGE_SEQUENCE: dict[str, int] = {key: i + 1 for i, (key, _) in enumerate(_STAGE_ORDER)}

# Stages that must be COMPLETED for the run to count as a successful workflow
# execution. (AI/coercion may be UNAVAILABLE and notification may FAIL in
# isolation without failing the overall execution.)
_REQUIRED_COMPLETE = frozenset(
    {"transaction_created", "risk_assessment", "decision_policy", "response_orchestration"}
)


class _StageAborted(Exception):
    """Internal sentinel: a stage failed unexpectedly and the run must stop."""


class ScenarioOrchestrationService:
    """Executes scenarios through the real application workflow and records a timeline."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        ai_client: AIInvestigationClient,
        execution_mode: ScenarioExecutionMode,
    ) -> None:
        self.session = session
        self.settings = settings
        self.execution_mode = execution_mode
        self.repository = TransactionRepository(session)
        self.transaction_service = TransactionService(self.repository)
        self.risk_service = RiskService(self.repository, self.transaction_service)
        self.investigation_service = InvestigationService(
            self.repository, self.transaction_service, ai_client
        )
        self.coercion_service = CoercionService(
            self.repository, self.transaction_service, ai_client, settings
        )
        self.workflow_service = DecisionWorkflowService(
            self.repository,
            self.transaction_service,
            self.risk_service,
            self.investigation_service,
        )
        self.verification_service = VerificationService(
            self.repository, self.transaction_service, self.workflow_service, settings
        )
        self.response_service = ResponseOrchestrationService(
            self.repository,
            self.transaction_service,
            self.workflow_service,
            SimulatedNotificationService(),
        )

    # ----------------------------------------------------------------- queries

    async def get_run(self, run_id: UUID) -> ScenarioRunModel | None:
        return await self.repository.get_scenario_run_by_id(run_id)

    async def list_runs(
        self, limit: int, offset: int, scenario_id: str | None
    ) -> tuple[list[ScenarioRunModel], int]:
        return await self.repository.list_scenario_runs(limit, offset, scenario_id)

    # ------------------------------------------------------------- run lifecycle

    async def start_run(
        self, scenario: ScenarioDefinition, idempotency_key: str
    ) -> tuple[ScenarioRunModel, bool]:
        """Start a scenario run, or return the existing run for the idempotency key."""
        existing = await self.repository.get_scenario_run_by_idempotency_key(idempotency_key)
        if existing is not None:
            logger.info(
                "Idempotent scenario-run replay for key=%s (run=%s)", idempotency_key, existing.id
            )
            return existing, False

        run = ScenarioRunModel(
            id=uuid4(),
            scenario_id=scenario.id,
            scenario_version=scenario.version,
            catalog_version=CATALOG_VERSION,
            idempotency_key=idempotency_key,
            execution_mode=self.execution_mode.value,
            status="RUNNING",
            stages=self._initial_stages(scenario),
        )
        try:
            run = await self.repository.create_scenario_run(run)
        except IntegrityError:
            # Concurrent duplicate for the same idempotency key: return the winner.
            existing = await self.repository.get_scenario_run_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing, False
            raise

        executed = await self._execute(run, scenario)
        return executed, True

    async def retry_run(
        self, run: ScenarioRunModel, scenario: ScenarioDefinition
    ) -> ScenarioRunModel:
        """Re-run a failed scenario run. All sub-steps are idempotent, so no
        transaction, decision, response, or notification is duplicated."""
        return await self._execute(run, scenario)

    # ------------------------------------------------------------- execution

    async def _execute(
        self, run: ScenarioRunModel, scenario: ScenarioDefinition
    ) -> ScenarioRunModel:
        stages: dict[str, dict[str, Any]] = {s["key"]: s for s in self._initial_stages(scenario)}
        tx_id: UUID | None = run.transaction_id
        ai_provider = (
            "mock_gemini"
            if self.execution_mode == ScenarioExecutionMode.DETERMINISTIC
            else self.settings.AI_PROVIDER
        )
        error_category: str | None = None
        detail: str | None = None
        status = "FAILED"

        try:
            tx_id = await self._stage_transaction(stages, run, scenario)

            if not scenario.call_transcript:
                self._set(
                    stages,
                    "coercion_analysis",
                    "SKIPPED",
                    detail="No simulated call transcript is supplied for this scenario.",
                )
            elif scenario.coercion_before_decision:
                await self._stage_coercion(stages, tx_id, scenario)

            await self._stage_decision(stages, tx_id, scenario)

            if scenario.call_transcript and not scenario.coercion_before_decision:
                await self._stage_coercion(stages, tx_id, scenario)

            await self._stage_verification(stages, tx_id, scenario)
            await self._stage_response(stages, run, tx_id, scenario)

            status = self._derive_status(stages)
        except _StageAborted as exc:
            error_category = str(exc) or "STAGE_FAILED"
            detail = "A pipeline stage failed unexpectedly; the run can be retried."
            status = "FAILED"
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.exception("Unexpected scenario-run failure for run=%s", run.id)
            error_category = type(exc).__name__
            detail = "An unexpected error occurred while running the scenario; it can be retried."
            status = "FAILED"

        return await self.repository.update_scenario_run(
            run.id,
            status=status,
            stages=[stages[key] for key, _ in _STAGE_ORDER],
            transaction_id=tx_id,
            ai_provider=ai_provider,
            error_category=error_category,
            detail=detail,
        )

    # --------------------------------------------------------------- stages

    async def _stage_transaction(
        self, stages: dict[str, dict[str, Any]], run: ScenarioRunModel, scenario: ScenarioDefinition
    ) -> UUID:
        key = "transaction_created"
        started = self._begin(stages, key)
        try:
            request = CreateTransactionRequest(
                customer_id=scenario.transaction.customer_id,
                idempotency_key=f"scenario-{run.id}",
                amount=scenario.transaction.amount,
                currency=scenario.transaction.currency,
                payment_rail=scenario.transaction.payment_rail,
                recipient_name=scenario.transaction.recipient_name,
                recipient_identifier=scenario.transaction.recipient_identifier,
                purpose=scenario.transaction.purpose,
            )
            tx, _created = await self.transaction_service.create_transaction(request)
        except Exception as exc:
            self._fail(stages, key, started, exc)
            raise _StageAborted("TRANSACTION_CREATE_FAILED") from exc
        self._complete(
            stages,
            key,
            started,
            detail=(
                f"Simulated {tx.currency} {tx.amount} payment to {tx.recipient_name} created "
                f"in state {tx.state}."
            ),
            entity_type="transaction",
            entity_id=str(tx.id),
        )
        return tx.id

    async def _stage_coercion(
        self, stages: dict[str, dict[str, Any]], tx_id: UUID, scenario: ScenarioDefinition
    ) -> None:
        key = "coercion_analysis"
        if not scenario.call_transcript:
            return
        started = self._begin(stages, key)
        try:
            voice = (
                VoiceStressInput.model_validate(scenario.voice_stress)
                if scenario.voice_stress
                else None
            )
            request = AnalyzeCoercionRequest(
                call_transcript=scenario.call_transcript, voice_stress=voice
            )
            analysis = await self.coercion_service.analyze_transaction_coercion(tx_id, request)
        except Exception as exc:
            self._fail(stages, key, started, exc)
            raise _StageAborted("COERCION_ANALYSIS_FAILED") from exc

        provider = (analysis.model_metadata or {}).get("provider", "unknown")
        if analysis.status == "UNAVAILABLE":
            self._set(
                stages,
                key,
                "UNAVAILABLE",
                started=started,
                detail="Coercion analysis provider was unavailable; deterministic controls apply.",
                entity_type="coercion_analysis",
                entity_id=str(analysis.id),
                error_category="AI_PROVIDER_UNAVAILABLE",
            )
            return
        self._complete(
            stages,
            key,
            started,
            detail=(
                f"Coercion level {analysis.overall_coercion_level} "
                f"({len(analysis.findings)} finding(s), provider {provider})."
            ),
            entity_type="coercion_analysis",
            entity_id=str(analysis.id),
        )

    async def _stage_decision(
        self, stages: dict[str, dict[str, Any]], tx_id: UUID, scenario: ScenarioDefinition
    ) -> None:
        started_risk = self._begin(stages, "risk_assessment")
        self._begin(stages, "ai_investigation")
        started_decision = self._begin(stages, "decision_policy")
        clock = time.monotonic()
        try:
            evidence = self._build_evidence(scenario)
            inv_request = self._build_investigation_request(scenario, tx_id)
            decision, _tx, _created = await self.workflow_service.evaluate(
                transaction_id=tx_id,
                evidence=evidence,
                investigation_request=inv_request,
                run_investigation=scenario.run_investigation,
            )
        except Exception as exc:
            self._fail(stages, "risk_assessment", started_risk, exc)
            self._fail(stages, "ai_investigation", started_risk, exc)
            self._fail(stages, "decision_policy", started_decision, exc)
            raise _StageAborted("DECISION_WORKFLOW_FAILED") from exc

        duration_ms = int((time.monotonic() - clock) * 1000)
        assessment = await self.repository.get_latest_assessment(tx_id)

        # Risk assessment stage (derived from the persisted assessment record).
        if assessment is not None:
            self._set(
                stages,
                "risk_assessment",
                "COMPLETED",
                started=started_risk,
                completed_override=assessment.created_at,
                detail=(
                    f"Risk score {assessment.risk_score}/100 ({assessment.risk_level}); "
                    f"{len(assessment.triggered_rules)} rule(s) triggered."
                ),
                entity_type="assessment",
                entity_id=str(assessment.id),
            )
        else:  # pragma: no cover - evaluate always persists an assessment
            self._set(stages, "risk_assessment", "COMPLETED", started=started_risk, detail="")

        # AI investigation stage (derived from the decision record).
        if decision.investigation_id is not None:
            self._set(
                stages,
                "ai_investigation",
                "COMPLETED",
                started=started_risk,
                detail="AI contextual investigation completed and fed the policy as a signal.",
                entity_type="investigation",
                entity_id=str(decision.investigation_id),
            )
        elif decision.provider_failed:
            self._set(
                stages,
                "ai_investigation",
                "UNAVAILABLE",
                started=started_risk,
                detail=(
                    "AI provider was unavailable; the deterministic baseline stood "
                    "without downgrade."
                ),
                error_category="AI_PROVIDER_UNAVAILABLE",
            )
        else:
            self._set(
                stages,
                "ai_investigation",
                "SKIPPED",
                started=started_risk,
                detail=(
                    "Investigation not warranted (low deterministic risk or explicitly skipped)."
                ),
            )

        # Decision policy stage.
        self._set(
            stages,
            "decision_policy",
            "COMPLETED",
            started=started_decision,
            duration_ms=duration_ms,
            detail=(
                f"Policy {decision.policy_version} selected action {decision.action} "
                f"({decision.from_state} -> {decision.to_state})."
            ),
            entity_type="decision",
            entity_id=str(decision.id),
            reason_codes=list(decision.reason_codes),
        )

    async def _stage_verification(
        self, stages: dict[str, dict[str, Any]], tx_id: UUID, scenario: ScenarioDefinition
    ) -> None:
        key = "verification"
        if scenario.verification_behavior == VerificationBehavior.NONE:
            self._set(
                stages,
                key,
                "SKIPPED",
                detail="Scenario does not drive a customer verification challenge.",
            )
            return

        tx = await self.transaction_service.get_transaction(tx_id)
        if tx.state != TransactionState.VERIFICATION_REQUIRED.value:
            self._set(
                stages,
                key,
                "SKIPPED",
                detail=f"Decision did not require verification (state {tx.state}).",
            )
            return

        started = self._begin(stages, key)
        try:
            (
                challenge,
                dev_otp,
                _token,
                _expires,
            ) = await self.verification_service.create_or_get_challenge(tx_id)
            if dev_otp is None:
                self._set(
                    stages,
                    key,
                    "UNAVAILABLE",
                    started=started,
                    detail=(
                        "Verification challenge created, but dev-mode OTP exposure is disabled, "
                        "so the simulation cannot auto-submit the code in this environment."
                    ),
                    entity_type="verification_challenge",
                    entity_id=str(challenge.id),
                    error_category="DEV_OTP_DISABLED",
                )
                return

            if scenario.verification_behavior == VerificationBehavior.SUBMIT_INCORRECT_OTP:
                otp = "".join(str((int(c) + 1) % 10) for c in dev_otp)
            else:
                otp = dev_otp

            result = await self.verification_service.submit(
                challenge_id=challenge.id,
                transaction_id=tx_id,
                customer_id=tx.customer_id,
                otp=otp,
            )
        except Exception as exc:
            self._fail(stages, key, started, exc)
            raise _StageAborted("VERIFICATION_FAILED") from exc

        self._complete(
            stages,
            key,
            started,
            detail=(
                f"Customer verification resolved: {result.result} "
                f"(transaction now {result.transaction_state})."
            ),
            entity_type="verification_challenge",
            entity_id=str(result.challenge.id),
            reason_codes=[result.result.value],
        )

    async def _stage_response(
        self,
        stages: dict[str, dict[str, Any]],
        run: ScenarioRunModel,
        tx_id: UUID,
        scenario: ScenarioDefinition,
    ) -> None:
        key = "response_orchestration"
        started = self._begin(stages, key)
        self._begin(stages, "notification")
        try:
            response, _tx, _created = await self.response_service.orchestrate_response(
                tx_id,
                idempotency_key=f"scenario-resp-{run.id}",
                channel=NotificationChannel.IN_APP_SIMULATED,
                simulate_notification_failure=scenario.simulate_notification_failure,
            )
        except Exception as exc:
            self._fail(stages, key, started, exc)
            self._fail(stages, "notification", started, exc)
            raise _StageAborted("RESPONSE_ORCHESTRATION_FAILED") from exc

        self._complete(
            stages,
            key,
            started,
            detail=(
                f"Response {response.response_type} orchestrated for action {response.action} "
                f"({response.from_state} -> {response.to_state})."
            ),
            entity_type="response",
            entity_id=str(response.id),
        )

        notifications = response.notifications or []
        if not notifications:
            self._set(
                stages,
                "notification",
                "SKIPPED",
                started=started,
                detail="No customer notification was dispatched for this response.",
            )
            return
        notif = notifications[0]
        if notif.delivery_status == "DELIVERED_SIMULATED":
            self._complete(
                stages,
                "notification",
                started,
                detail=(
                    f"Simulated notification delivered via {notif.channel} to "
                    f"{notif.recipient_masked}."
                ),
                entity_type="notification",
                entity_id=str(notif.id),
            )
        else:
            # A simulated delivery failure is recorded but strictly isolated from the
            # authoritative safety decision (it never downgrades a hold or block).
            self._set(
                stages,
                "notification",
                "FAILED",
                started=started,
                detail=(
                    f"Simulated notification delivery failed ({notif.failure_reason}); the "
                    "safety decision is unaffected."
                ),
                entity_type="notification",
                entity_id=str(notif.id),
                error_category=notif.failure_reason,
            )

    # --------------------------------------------------------------- evaluation

    async def build_observed_outcome(self, run: ScenarioRunModel) -> ObservedOutcome:
        """Derive the authoritative observed outcome from persisted artifacts."""
        incomplete = [
            s["key"] for s in run.stages if s.get("status") in ("PENDING", "RUNNING", "FAILED")
        ]
        verification_outcome = None
        for s in run.stages:
            if s.get("key") == "verification" and s.get("status") == "COMPLETED":
                codes = s.get("reason_codes") or []
                verification_outcome = codes[0] if codes else None

        if run.transaction_id is None:
            return ObservedOutcome(workflow_status=run.status, incomplete_stages=incomplete)

        tx = await self.repository.get_by_id(run.transaction_id)
        decision = await self.repository.get_latest_decision_for_transaction(run.transaction_id)
        response = await self.repository.get_latest_response_for_transaction(run.transaction_id)
        assessment = await self.repository.get_latest_assessment(run.transaction_id)

        missing: list[str] = []
        if assessment is not None:
            missing.extend(assessment.missing_evidence)
        if decision is not None:
            for item in decision.missing_information:
                if item not in missing:
                    missing.append(item)

        return ObservedOutcome(
            workflow_status=run.status,
            final_state=tx.state if tx is not None else None,
            policy_action=decision.action if decision is not None else None,
            response_type=response.response_type if response is not None else None,
            customer_action_required=(
                response.customer_action_required if response is not None else None
            ),
            verification_outcome=verification_outcome,
            incomplete_stages=incomplete,
            missing_evidence=missing,
        )

    # --------------------------------------------------------------- helpers

    def _build_evidence(self, scenario: ScenarioDefinition) -> TransactionEvidence:
        base = TransactionEvidence(
            amount=scenario.transaction.amount,
            currency=scenario.transaction.currency,
            payment_rail=scenario.transaction.payment_rail,
            recipient_name=scenario.transaction.recipient_name,
            recipient_identifier=scenario.transaction.recipient_identifier,
            purpose=scenario.transaction.purpose,
            customer_id=scenario.transaction.customer_id,
        )
        if scenario.risk_evidence:
            return replace(base, **scenario.risk_evidence)
        return base

    def _build_investigation_request(
        self, scenario: ScenarioDefinition, tx_id: UUID
    ) -> InvestigateTransactionRequest | None:
        has_context = bool(
            scenario.customer_statements
            or scenario.telephony_telemetry
            or scenario.recipient_intelligence
            or scenario.coercion_cues
        )
        if not has_context:
            return None
        return InvestigateTransactionRequest(
            transaction_id=tx_id,
            customer_statements=[
                CustomerStatementEvidence.model_validate(s) for s in scenario.customer_statements
            ],
            telephony_telemetry=(
                TelephonyTelemetryEvidence.model_validate(scenario.telephony_telemetry)
                if scenario.telephony_telemetry
                else None
            ),
            recipient_intelligence=(
                RecipientIntelligenceEvidence.model_validate(scenario.recipient_intelligence)
                if scenario.recipient_intelligence
                else None
            ),
            coercion_cues=list(scenario.coercion_cues),
        )

    def _initial_stages(self, scenario: ScenarioDefinition) -> list[dict[str, Any]]:
        stages: list[dict[str, Any]] = []
        for key, title in _STAGE_ORDER:
            stages.append(
                {
                    "key": key,
                    "title": title,
                    "status": "PENDING",
                    "detail": "",
                    "entity_type": None,
                    "entity_id": None,
                    "reason_codes": [],
                    "started_at": None,
                    "completed_at": None,
                    "duration_ms": None,
                    "error_category": None,
                    "sequence": _STAGE_SEQUENCE[key],
                }
            )
        return stages

    def _begin(self, stages: dict[str, dict[str, Any]], key: str) -> float:
        now = datetime.now(UTC)
        stages[key]["status"] = "RUNNING"
        stages[key]["started_at"] = now.isoformat()
        return time.monotonic()

    def _complete(
        self,
        stages: dict[str, dict[str, Any]],
        key: str,
        started: float,
        *,
        detail: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        reason_codes: list[str] | None = None,
    ) -> None:
        self._set(
            stages,
            key,
            "COMPLETED",
            started=started,
            detail=detail,
            entity_type=entity_type,
            entity_id=entity_id,
            reason_codes=reason_codes,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def _fail(
        self, stages: dict[str, dict[str, Any]], key: str, started: float, exc: Exception
    ) -> None:
        self._set(
            stages,
            key,
            "FAILED",
            started=started,
            detail="Stage failed unexpectedly.",
            error_category=type(exc).__name__,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def _set(
        self,
        stages: dict[str, dict[str, Any]],
        key: str,
        status: str,
        *,
        started: float | None = None,
        detail: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        reason_codes: list[str] | None = None,
        duration_ms: int | None = None,
        error_category: str | None = None,
        completed_override: datetime | None = None,
    ) -> None:
        stage = stages[key]
        stage["status"] = status
        if detail is not None:
            stage["detail"] = detail
        if entity_type is not None:
            stage["entity_type"] = entity_type
        if entity_id is not None:
            stage["entity_id"] = entity_id
        if reason_codes is not None:
            stage["reason_codes"] = reason_codes
        if error_category is not None:
            stage["error_category"] = error_category
        if status in ("COMPLETED", "FAILED", "UNAVAILABLE", "SKIPPED"):
            completed = completed_override or datetime.now(UTC)
            stage["completed_at"] = completed.isoformat()
        if duration_ms is not None:
            stage["duration_ms"] = duration_ms

    def _derive_status(self, stages: dict[str, dict[str, Any]]) -> str:
        for key in _REQUIRED_COMPLETE:
            if stages[key]["status"] != "COMPLETED":
                return "FAILED"
        if stages["verification"]["status"] not in ("COMPLETED", "SKIPPED", "UNAVAILABLE"):
            return "FAILED"
        return "COMPLETED"
