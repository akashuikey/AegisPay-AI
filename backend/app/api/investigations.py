"""API routes for AI-driven fraud investigation and forensic analysis."""

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import TransactionInvestigationModel
from app.db.session import get_db_session
from app.domain.investigation import (
    ConfidenceLevel,
    EvidenceProvenance,
    FindingCategory,
    RiskSentiment,
)
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.investigation import (
    InvestigateTransactionRequest,
    InvestigationFindingResponse,
    InvestigationModelMetadataResponse,
    InvestigationResponse,
)
from app.services.ai_client import AIInvestigationClient, VertexGeminiClient
from app.services.investigation_service import InvestigationService
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/investigations", tags=["AI Investigation"])


@lru_cache
def get_default_ai_client() -> AIInvestigationClient:
    """Provide singleton Google Cloud Vertex AI Gemini client."""

    settings = Settings()
    return VertexGeminiClient(settings)


def get_investigation_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    ai_client: Annotated[AIInvestigationClient, Depends(get_default_ai_client)],
) -> InvestigationService:
    """Dependency provider for InvestigationService with request-scoped DB session."""
    repository = TransactionRepository(session)
    transaction_service = TransactionService(repository)
    return InvestigationService(repository, transaction_service, ai_client)


def _serialize_investigation_response(
    record: TransactionInvestigationModel,
) -> InvestigationResponse:
    """Convert persistent SQLAlchemy investigation model to typed API response."""
    return InvestigationResponse(
        id=record.id,
        transaction_id=record.transaction_id,
        assessment_id=record.assessment_id,
        summary=record.summary,
        overall_risk_sentiment=RiskSentiment(record.overall_risk_sentiment),
        confidence=ConfidenceLevel(record.confidence),
        confidence_score=record.confidence_score,
        findings=[
            InvestigationFindingResponse(
                id=f["id"],
                category=FindingCategory(f["category"]),
                explanation=f["explanation"],
                severity=f["severity"],
                supporting_evidence_references=f.get("supporting_evidence_references", []),
                source_provenance=EvidenceProvenance(
                    f.get("source_provenance", "customer_statement")
                ),
            )
            for f in record.findings
        ],
        contradictory_or_mitigating_evidence=record.contradictory_evidence,
        missing_information=record.missing_information,
        unresolved_questions=record.unresolved_questions,
        suggested_next_steps=record.suggested_next_steps,
        model_metadata=InvestigationModelMetadataResponse(
            provider=record.model_metadata.get("provider", "unknown"),
            model_id=record.model_metadata.get("model_id", "unknown"),
            latency_ms=record.model_metadata.get("latency_ms"),
            correlation_id=record.model_metadata.get("correlation_id"),
        ),
        created_at=record.created_at,
    )


@router.post(
    "",
    response_model=InvestigationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Conduct AI investigation",
    description=(
        "Analyzes contextual transaction evidence using Gemini and returns structured "
        "forensic findings."
    ),
)
async def create_investigation(
    request: InvestigateTransactionRequest,
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationResponse:
    """Execute AI investigation over transaction context and persist findings."""
    record = await service.investigate_transaction(request)
    return _serialize_investigation_response(record)


@router.get(
    "/{investigation_id}",
    response_model=InvestigationResponse,
    summary="Get investigation by ID",
    description="Retrieve a previously conducted AI forensic investigation record.",
)
async def get_investigation(
    investigation_id: UUID,
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationResponse:
    """Fetch an investigation record by primary key."""
    record = await service.get_investigation(investigation_id)
    return _serialize_investigation_response(record)
