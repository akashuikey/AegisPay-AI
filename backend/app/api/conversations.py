"""API routes for bounded multi-turn investigation conversations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.investigations import get_investigation_service
from app.db.models import InvestigationConversationModel
from app.domain.investigation import (
    ConfidenceLevel,
    ConversationRole,
    EvidenceProvenance,
    FindingCategory,
    RiskSentiment,
)
from app.schemas.investigation import (
    AddConversationTurnRequest,
    ConversationTurnResponse,
    InvestigationConversationResponse,
    InvestigationFindingResponse,
)
from app.services.investigation_service import InvestigationService

router = APIRouter(prefix="/conversations", tags=["Investigation Conversations"])


def serialize_conversation_response(
    record: InvestigationConversationModel,
) -> InvestigationConversationResponse:
    """Convert persistent SQLAlchemy conversation model and turns to API schema."""
    return InvestigationConversationResponse(
        id=record.id,
        transaction_id=record.transaction_id,
        status=record.status,
        turn_count=record.turn_count,
        version=record.version,
        turns=[
            ConversationTurnResponse(
                id=turn.id,
                conversation_id=turn.conversation_id,
                turn_index=turn.turn_index,
                role=ConversationRole(turn.role),
                content=turn.content,
                evidence_provenance=(
                    EvidenceProvenance(turn.evidence_provenance)
                    if turn.evidence_provenance
                    else None
                ),
                evidence_references=turn.evidence_references or [],
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
                    for f in turn.findings
                ],
                risk_sentiment=(
                    RiskSentiment(turn.risk_sentiment) if turn.risk_sentiment else None
                ),
                confidence=(ConfidenceLevel(turn.confidence) if turn.confidence else None),
                confidence_score=turn.confidence_score,
                missing_information=turn.missing_information or [],
                follow_up_questions=turn.follow_up_questions or [],
                model_metadata=turn.model_metadata or {},
                created_at=turn.created_at,
            )
            for turn in sorted(record.turns, key=lambda t: t.turn_index)
        ],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get(
    "/{conversation_id}",
    response_model=InvestigationConversationResponse,
    summary="Get investigation conversation by ID",
    description=(
        "Retrieve a multi-turn investigation conversation session and all its recorded turns."
    ),
)
async def get_conversation(
    conversation_id: UUID,
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationConversationResponse:
    """Fetch an investigation conversation by primary key."""
    record = await service.get_conversation(conversation_id)
    return serialize_conversation_response(record)


@router.post(
    "/{conversation_id}/turns",
    response_model=InvestigationConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit conversation turn",
    description=(
        "Submit an operator message, customer statement, or follow-up answer into an active "
        "investigation conversation. Generates structured forensic findings and targeted questions."
    ),
)
async def submit_conversation_turn(
    conversation_id: UUID,
    request: AddConversationTurnRequest,
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationConversationResponse:
    """Submit a new turn into the conversation session."""
    record = await service.submit_conversation_turn(
        conversation_id=conversation_id,
        request=request,
    )
    return serialize_conversation_response(record)
