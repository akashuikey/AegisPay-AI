"""API routes for voice duress and coercion intelligence (P2-A6)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.investigations import get_default_ai_client
from app.db.models import TransactionCoercionAnalysisModel
from app.db.session import get_db_session
from app.domain.coercion import CoercionCategory, CoercionSeverity
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.coercion import (
    AnalyzeCoercionRequest,
    CoercionAnalysisLifecycleResponse,
    CoercionAnalysisResponse,
    CoercionFindingResponse,
    VoiceStressResponse,
)
from app.schemas.investigation import InvestigationModelMetadataResponse
from app.services.ai_client import AIInvestigationClient
from app.services.coercion_service import CoercionService
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/transactions", tags=["Voice Duress & Coercion"])


def get_coercion_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
) -> CoercionService:
    """Dependency provider for CoercionService with request-scoped DB session."""
    repository = TransactionRepository(session)
    transaction_service = TransactionService(repository)
    return CoercionService(repository, transaction_service, ai_client)


def serialize_coercion_analysis(
    record: TransactionCoercionAnalysisModel,
) -> CoercionAnalysisResponse:
    """Convert persistent SQLAlchemy coercion analysis model to typed API response."""
    findings = [
        CoercionFindingResponse(
            id=str(f.get("id")),
            category=CoercionCategory(str(f.get("category", "AUTHORITY_IMPERSONATION"))),
            severity=CoercionSeverity(str(f.get("severity", "LOW"))),
            is_explicit=bool(f.get("is_explicit")),
            explanation=str(f.get("explanation")),
            supporting_excerpt=str(f.get("supporting_excerpt")),
            start_offset=f.get("start_offset"),
            end_offset=f.get("end_offset"),
            provenance=str(f.get("provenance", "simulated_call_transcript")),
        )
        for f in (record.findings or [])
    ]
    voice_stress = None
    if record.voice_stress_signals:
        vs = record.voice_stress_signals
        voice_stress = VoiceStressResponse(
            detected=vs.get("detected"),
            level=str(vs.get("level", "NONE")),
            acoustic_indicators=list(vs.get("acoustic_indicators", [])),
            speech_rate_wpm=vs.get("speech_rate_wpm"),
            provenance=str(vs.get("provenance", "simulated_acoustic_telemetry")),
            is_simulated=bool(vs.get("is_simulated", True)),
            disclaimer=str(
                vs.get(
                    "disclaimer",
                    (
                        "Simulated acoustic indicator; voice stress is advisory only and "
                        "not proof of deception or fraud."
                    ),
                )
            ),
        )

    meta = record.model_metadata or {}
    metadata = InvestigationModelMetadataResponse(
        provider=str(meta.get("provider", "unknown")),
        model_id=str(meta.get("model_id", "unknown")),
        latency_ms=int(meta.get("latency_ms", 0)),
        correlation_id=meta.get("correlation_id"),
    )

    return CoercionAnalysisResponse(
        id=record.id,
        transaction_id=record.transaction_id,
        overall_coercion_level=record.overall_coercion_level,
        confidence=record.confidence,
        confidence_score=record.confidence_score,
        findings=findings,
        voice_stress_signals=voice_stress,
        legitimate_explanations=list(record.legitimate_explanations or []),
        uncertainty_notes=list(record.uncertainty_notes or []),
        missing_information=list(record.missing_information or []),
        summary=record.summary,
        model_metadata=metadata,
        status=record.status,
        transcript_snippet=record.transcript_snippet,
        created_at=record.created_at,
    )


@router.post(
    "/{transaction_id}/coercion/analyze",
    response_model=CoercionAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze simulated call transcript for duress and coercion",
    description=(
        "Analyzes a supplied simulated phone call dialogue transcript and optional "
        "simulated voice-stress telemetry for indicators of psychological coercion, "
        "threats, secrecy demands, and social engineering pressure."
    ),
)
async def analyze_transaction_coercion(
    transaction_id: UUID,
    request: AnalyzeCoercionRequest,
    service: Annotated[CoercionService, Depends(get_coercion_service)],
) -> CoercionAnalysisResponse:
    """Analyze a call transcript for duress and coercion (operator console)."""
    analysis = await service.analyze_transaction_coercion(transaction_id, request)
    return serialize_coercion_analysis(analysis)


@router.get(
    "/{transaction_id}/coercion",
    response_model=CoercionAnalysisLifecycleResponse,
    summary="Get coercion-analysis lifecycle state for a transaction",
    description=(
        "Returns the coercion-analysis lifecycle for a transaction: not_started, "
        "in_progress, completed, or failed, with the analysis payload when available. "
        "A missing transaction returns 404; a missing analysis is reported explicitly "
        "and never misrepresented as proof of safety."
    ),
)
async def get_latest_coercion_analysis(
    transaction_id: UUID,
    service: Annotated[CoercionService, Depends(get_coercion_service)],
) -> CoercionAnalysisLifecycleResponse:
    """Fetch the coercion-analysis lifecycle state for a transaction."""
    lifecycle_status, detail, analysis = await service.get_analysis_lifecycle(transaction_id)
    return CoercionAnalysisLifecycleResponse(
        status=lifecycle_status,
        detail=detail,
        analysis=serialize_coercion_analysis(analysis) if analysis is not None else None,
    )
