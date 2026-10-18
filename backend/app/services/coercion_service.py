"""Application service orchestrating call transcript coercion and duress analysis (P2-A6)."""

from dataclasses import asdict
from uuid import UUID, uuid4

from app.core.config import Settings, get_settings
from app.core.errors import AIConfigurationError, AIProviderError
from app.core.logging import get_logger
from app.db.models import TransactionCoercionAnalysisModel
from app.domain.coercion import (
    CoercionLevel,
    VoiceStressEvidence,
    validate_transcript_excerpt,
)
from app.domain.coercion_prompts import (
    COERCION_ANALYSIS_SYSTEM_INSTRUCTION,
    build_coercion_prompt,
)
from app.domain.investigation import ConfidenceLevel, InvestigationModelMetadata
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.coercion import AnalyzeCoercionRequest, CoercionStructuredOutput
from app.services.ai_client import AIInvestigationClient
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)


class CoercionService:
    """Orchestrates forensic coercion intelligence and simulated voice duress evaluation.

    Boundaries & Guardrails:
    - AI provides forensic evidence, classifications, and exact quotes.
    - Deterministic policy and transaction state machine control all transaction outcomes.
    - Citations must be grounded: findings citing fabricated text are rejected.
    - Voice stress is advisory acoustic telemetry only, never proof of deception or fraud.
    """

    def __init__(
        self,
        repository: TransactionRepository,
        transaction_service: TransactionService,
        ai_client: AIInvestigationClient,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.transaction_service = transaction_service
        self.ai_client = ai_client
        self.settings = settings or get_settings()

    async def get_latest_analysis(
        self, transaction_id: UUID
    ) -> TransactionCoercionAnalysisModel | None:
        """Fetch the latest coercion analysis for a transaction (verifies transaction exists)."""
        await self.transaction_service.get_transaction(transaction_id)
        return await self.repository.get_latest_coercion_analysis(transaction_id)

    async def get_analysis_lifecycle(
        self, transaction_id: UUID
    ) -> tuple[str, str, TransactionCoercionAnalysisModel | None]:
        """Resolve the coercion-analysis lifecycle for a transaction.

        Returns ``(status, detail, analysis_or_none)`` where status is one of
        ``not_started`` / ``in_progress`` / ``completed`` / ``failed``. Raises
        ``NotFoundError`` only when the *transaction itself* does not exist, so a
        missing analysis is reported explicitly rather than as a bare 404 (which the
        dashboard must never read as proof of safety).
        """
        # Verifies the transaction exists (raises NotFoundError -> 404 if missing).
        await self.transaction_service.get_transaction(transaction_id)
        analysis = await self.repository.get_latest_coercion_analysis(transaction_id)

        if analysis is not None:
            if analysis.status == "UNAVAILABLE":
                return (
                    "failed",
                    "Automated coercion analysis ran but the AI provider was "
                    "unavailable; deterministic controls still apply.",
                    analysis,
                )
            return ("completed", "Coercion analysis is available.", analysis)

        # No analysis yet: distinguish an active call (in progress) from not started.
        active_call = await self.repository.get_active_call_session_for_transaction(transaction_id)
        if active_call is not None:
            return (
                "in_progress",
                "A call is active; coercion analysis runs from the accumulated "
                "transcript and will be available after the call.",
                None,
            )
        return (
            "not_started",
            "No coercion analysis has been performed for this transaction yet. "
            "This is not evidence that the transaction is safe.",
            None,
        )

    async def analyze_transaction_coercion(
        self, transaction_id: UUID, request: AnalyzeCoercionRequest
    ) -> TransactionCoercionAnalysisModel:
        """Analyze a simulated call transcript for duress and coercion with forensic validation."""
        # 1. Verify transaction existence
        tx = await self.transaction_service.get_transaction(transaction_id)

        # 2. Check for matching recent analysis to avoid duplicate expensive AI calls
        existing = await self.repository.get_latest_coercion_analysis(transaction_id)
        if (
            existing is not None
            and existing.transcript_snippet == request.call_transcript
            and existing.status == "COMPLETED"
        ):
            logger.info(
                "Returning existing coercion analysis %s for tx=%s (identical transcript)",
                existing.id,
                transaction_id,
            )
            return existing

        # 3. Assemble simulated acoustic voice stress evidence if supplied
        voice_stress: VoiceStressEvidence | None = None
        if request.voice_stress is not None:
            voice_stress = VoiceStressEvidence(
                detected=request.voice_stress.detected,
                level=request.voice_stress.level,
                acoustic_indicators=list(request.voice_stress.acoustic_indicators),
                speech_rate_wpm=request.voice_stress.speech_rate_wpm,
                provenance="simulated_acoustic_telemetry",
                is_simulated=True,
            )

        # 4. Build injection-hardened forensic prompt
        context = {
            "amount": str(tx.amount),
            "currency": tx.currency,
            "recipient_name": tx.recipient_name,
            "purpose": tx.purpose,
        }
        prompt = build_coercion_prompt(
            transcript=request.call_transcript,
            voice_stress=voice_stress,
            context=context,
        )

        # 5. Call AI provider with safe fallback
        status = "COMPLETED"
        try:
            output, metadata = await self.ai_client.generate_coercion_analysis(
                prompt=prompt,
                system_instruction=COERCION_ANALYSIS_SYSTEM_INSTRUCTION,
                correlation_id=request.correlation_id,
            )
        except (AIProviderError, AIConfigurationError) as exc:
            logger.warning(
                "Coercion analysis provider failed for tx=%s: %s (recording UNAVAILABLE)",
                transaction_id,
                exc,
            )
            status = "UNAVAILABLE"
            output = CoercionStructuredOutput(
                overall_coercion_level=CoercionLevel.UNKNOWN,
                confidence=ConfidenceLevel.LOW,
                confidence_score=0.0,
                findings=[],
                legitimate_explanations=[],
                uncertainty_notes=[f"Coercion analysis provider unavailable: {exc}"],
                missing_information=["Automated call transcript analysis unavailable"],
                summary=(
                    "Automated coercion analysis was unavailable due to an AI provider issue. "
                    "Deterministic controls apply."
                ),
            )
            metadata = InvestigationModelMetadata(
                provider="unavailable",
                model_id="none",
                latency_ms=0,
                correlation_id=request.correlation_id,
            )

        # 6. Validate and sanitize evidence citations (Grounding Invariant)
        validated_findings: list[dict] = []
        uncertainty_notes = list(output.uncertainty_notes)
        for finding in output.findings:
            is_valid, start, end = validate_transcript_excerpt(
                finding.supporting_excerpt, request.call_transcript
            )
            if is_valid:
                finding_dict = finding.model_dump()
                finding_dict["start_offset"] = start
                finding_dict["end_offset"] = end
                validated_findings.append(finding_dict)
            else:
                logger.warning(
                    "Dropping ungrounded finding %s: excerpt not found in transcript: %s",
                    finding.id,
                    finding.supporting_excerpt,
                )
                uncertainty_notes.append(
                    f"Finding '{finding.id}' was dropped because its cited excerpt "
                    "was not found verbatim in the supplied transcript."
                )

        # 7. Persist analysis record
        analysis_model = TransactionCoercionAnalysisModel(
            id=uuid4(),
            transaction_id=tx.id,
            transcript_snippet=request.call_transcript,
            overall_coercion_level=output.overall_coercion_level.value,
            confidence=output.confidence.value,
            confidence_score=output.confidence_score,
            findings=validated_findings,
            voice_stress_signals=asdict(voice_stress) if voice_stress else None,
            legitimate_explanations=list(output.legitimate_explanations),
            uncertainty_notes=uncertainty_notes,
            missing_information=list(output.missing_information),
            summary=output.summary,
            model_metadata={
                "provider": metadata.provider,
                "model_id": metadata.model_id,
                "latency_ms": metadata.latency_ms,
                "correlation_id": metadata.correlation_id,
            },
            status=status,
        )

        saved = await self.repository.create_coercion_analysis(analysis_model)
        logger.info(
            "Saved coercion analysis %s for tx=%s: level=%s status=%s (%d findings)",
            saved.id,
            tx.id,
            saved.overall_coercion_level,
            saved.status,
            len(saved.findings),
        )
        return saved
