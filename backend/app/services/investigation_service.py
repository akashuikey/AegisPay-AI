"""Application service orchestrating AI-driven forensic fraud investigations."""

import uuid
from typing import Any
from uuid import UUID

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import TransactionInvestigationModel
from app.domain.investigation_prompts import (
    INVESTIGATION_SYSTEM_INSTRUCTION,
    build_investigation_prompt,
)
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.investigation import InvestigateTransactionRequest
from app.services.ai_client import AIInvestigationClient
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)


class InvestigationService:
    """Coordinates evidence preparation, AI model analysis, and investigation persistence.

    Strict Architectural Boundaries:
    - This service produces intelligence and forensic findings.
    - It NEVER mutates transaction state or modifies the deterministic state machine.
    """

    def __init__(
        self,
        repository: TransactionRepository,
        transaction_service: TransactionService,
        ai_client: AIInvestigationClient,
    ) -> None:
        self.repository = repository
        self.transaction_service = transaction_service
        self.ai_client = ai_client

    async def investigate_transaction(
        self, request: InvestigateTransactionRequest
    ) -> TransactionInvestigationModel:
        """Execute forensic AI investigation over transaction and contextual evidence."""
        # 1. Verify transaction existence
        tx = await self.transaction_service.get_transaction(request.transaction_id)

        # 2. Retrieve corresponding deterministic assessment if available
        assessment = None
        if request.assessment_id:
            assessment = await self.repository.get_latest_assessment(request.transaction_id)
            if assessment and assessment.id != request.assessment_id:
                # If specific ID was requested but doesn't match latest, search or keep latest
                pass
        else:
            assessment = await self.repository.get_latest_assessment(request.transaction_id)

        # 3. Assemble structured context dictionary
        context: dict[str, Any] = {
            "transaction": {
                "id": str(tx.id),
                "customer_id": tx.customer_id,
                "amount": str(tx.amount),
                "currency": tx.currency,
                "payment_rail": tx.payment_rail,
                "recipient_name": tx.recipient_name,
                "recipient_identifier": tx.recipient_identifier,
                "purpose": tx.purpose,
                "state": tx.state,
            },
            "deterministic_assessment": (
                {
                    "id": str(assessment.id),
                    "risk_score": assessment.risk_score,
                    "risk_level": assessment.risk_level,
                    "recommended_action": assessment.recommended_action,
                    "triggered_rules": assessment.triggered_rules,
                    "missing_evidence": assessment.missing_evidence,
                }
                if assessment
                else {}
            ),
            "customer_statements": [s.model_dump() for s in request.customer_statements],
            "document_extractions": [
                {
                    "doc_id": d.doc_id,
                    "document_type": d.document_type,
                    "claimed_issuer": d.claimed_issuer,
                    "claimed_amount": str(d.claimed_amount) if d.claimed_amount else None,
                    "extracted_text": d.extracted_text,
                    "verification_source": d.verification_source,
                }
                for d in request.document_extractions
            ],
            "telephony_telemetry": (
                request.telephony_telemetry.model_dump() if request.telephony_telemetry else {}
            ),
            "recipient_intelligence": (
                request.recipient_intelligence.model_dump()
                if request.recipient_intelligence
                else {}
            ),
            "coercion_cues": request.coercion_cues,
        }

        # 4. Build hardened forensic prompt
        prompt = build_investigation_prompt(context)

        # 5. Execute Gemini model call with retry and structured JSON parsing
        logger.info(
            "Initiating AI investigation for tx=%s (statements=%d, documents=%d)",
            tx.id,
            len(request.customer_statements),
            len(request.document_extractions),
        )
        output, metadata = await self.ai_client.generate_investigation(
            prompt=prompt,
            system_instruction=INVESTIGATION_SYSTEM_INSTRUCTION,
            correlation_id=request.correlation_id,
        )

        # 6. Persist investigation record
        investigation_model = TransactionInvestigationModel(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            assessment_id=assessment.id if assessment else None,
            summary=output.summary,
            overall_risk_sentiment=output.overall_risk_sentiment.value,
            confidence=output.confidence.value,
            confidence_score=output.confidence_score,
            findings=[f.model_dump() for f in output.findings],
            contradictory_evidence=output.contradictory_or_mitigating_evidence,
            missing_information=output.missing_information,
            unresolved_questions=output.unresolved_questions,
            suggested_next_steps=output.suggested_next_steps,
            model_metadata={
                "provider": metadata.provider,
                "model_id": metadata.model_id,
                "latency_ms": metadata.latency_ms,
                "correlation_id": metadata.correlation_id,
            },
            input_snapshot={
                "statements_count": len(request.customer_statements),
                "documents_count": len(request.document_extractions),
                "has_telephony": bool(request.telephony_telemetry),
                "has_recipient_intel": bool(request.recipient_intelligence),
            },
        )

        saved = await self.repository.create_investigation(investigation_model)
        logger.info(
            "Saved investigation %s for tx=%s: sentiment=%s confidence=%s (%d findings)",
            saved.id,
            tx.id,
            saved.overall_risk_sentiment,
            saved.confidence,
            len(saved.findings),
        )
        return saved

    async def get_investigation(self, investigation_id: UUID) -> TransactionInvestigationModel:
        """Fetch an investigation by primary key or raise NotFoundError."""
        record = await self.repository.get_investigation_by_id(investigation_id)
        if record is None:
            raise NotFoundError(f"Investigation with ID '{investigation_id}' was not found")
        return record

    async def list_investigations_for_transaction(
        self, transaction_id: UUID
    ) -> list[TransactionInvestigationModel]:
        """Fetch all investigations associated with a transaction."""
        # Ensure transaction exists
        await self.transaction_service.get_transaction(transaction_id)
        return await self.repository.list_investigations_for_transaction(transaction_id)
