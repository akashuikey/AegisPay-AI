"""Application service orchestrating AI-driven forensic fraud investigations."""

import uuid
from typing import Any
from uuid import UUID

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import TransactionInvestigationModel, TransactionModel
from app.domain.investigation import EvidenceProvenance, FindingCategory, RiskSentiment
from app.domain.investigation_prompts import (
    INVESTIGATION_SYSTEM_INSTRUCTION,
    build_investigation_prompt,
)
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.investigation import (
    InvestigateTransactionRequest,
    InvestigationStructuredOutput,
)
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

        # 5.5 Validate and sanitize evidence integrity, provenance, and anti-injection guardrails
        self._validate_and_sanitize_evidence_integrity(
            output=output,
            request=request,
            tx=tx,
            assessment=assessment,
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

    def _validate_and_sanitize_evidence_integrity(
        self,
        output: InvestigationStructuredOutput,
        request: InvestigateTransactionRequest,
        tx: TransactionModel,
        assessment: Any,
    ) -> None:
        """Validate evidence references and provenance against supplied input allowlist.

        Forensic Integrity Guarantees:
        1. Reference Integrity: Every cited evidence reference must map to actual input.
           Fabricated or unsupplied references are rejected and recorded in missing_information.
        2. Provenance Grounding: Distinguishes customer statements, extracted document text,
           sensor telemetry, consortium intelligence, and purely synthetic model inferences.
           Findings lacking grounded empirical evidence default to MODEL_INFERENCE.
        3. Anti-Prompt-Injection Non-Malice Invariant: Adversarial prompt injection attempts
           in untrusted customer statements or documents are treated as untrusted manipulation,
           never as proof of customer malice (MALICIOUS).
        """
        # 1. Compile allowlist of verified inputs
        valid_refs: set[str] = {
            "transaction",
            "transaction_id",
            str(tx.id).lower(),
            "amount",
            "historical_ledger",
            "ledger",
            "purpose",
        }

        # Customer statements
        for stmt in request.customer_statements:
            sid = stmt.statement_id.strip().lower()
            valid_refs.add(sid)
            valid_refs.add(f"stmt:{sid}")
            valid_refs.add(f"statement:{sid}")
        if request.customer_statements:
            valid_refs.update(
                {
                    "customer_statement",
                    "customer_statements",
                    "untrusted_customer_statements",
                }
            )

        # Documents
        for doc in request.document_extractions:
            did = doc.doc_id.strip().lower()
            valid_refs.add(did)
            valid_refs.add(f"doc:{did}")
            valid_refs.add(f"document:{did}")
        if request.document_extractions:
            valid_refs.update(
                {
                    "document",
                    "documents",
                    "document_extraction",
                    "document_extractions",
                    "untrusted_extracted_documents",
                }
            )

        # Telephony
        if request.telephony_telemetry:
            valid_refs.update(
                {
                    "telephony",
                    "telephony_telemetry",
                    "telephony:active_call_present",
                    "telephony:screen_sharing_active",
                    "telephony:voice_stress_detected",
                    "telephony:call_duration_seconds",
                    "active_call",
                    "screen_sharing",
                    "voice_stress",
                }
            )

        # Recipient Intelligence
        if request.recipient_intelligence:
            valid_refs.update(
                {
                    "recipient",
                    "recipient_intelligence",
                    "consortium",
                    "consortium_registry",
                    "mule",
                    "is_flagged_mule",
                    "fan_in",
                    "fan_out",
                    "payee_name_mismatch",
                    "routing_mismatch",
                }
            )

        # Coercion cues
        if request.coercion_cues:
            valid_refs.update({"coercion_cues", "coercion"})

        # Risk Engine & Deterministic Assessment
        valid_refs.update({"risk_engine", "deterministic_assessment"})
        if assessment:
            valid_refs.add(str(assessment.id).lower())
            for rule in getattr(assessment, "triggered_rules", []) or []:
                rule_str = str(rule).strip().lower()
                valid_refs.add(rule_str)
                valid_refs.add(f"rule:{rule_str}")

        # 2. Validate and filter each finding's supporting evidence references
        for finding in output.findings:
            sanitized_refs: list[str] = []
            for ref in finding.supporting_evidence_references:
                cleaned_ref = ref.strip().strip("[]").strip().lower()
                is_valid = cleaned_ref in valid_refs
                if not is_valid and ":" in cleaned_ref:
                    prefix, suffix = cleaned_ref.split(":", 1)
                    if prefix in ("stmt", "doc", "rule", "telephony") and suffix in valid_refs:
                        is_valid = True

                if is_valid:
                    sanitized_refs.append(ref)
                else:
                    msg = (
                        f"Unverified evidence reference '{ref}' in finding '{finding.id}' "
                        "rejected: reference does not map to any supplied input."
                    )
                    logger.warning(msg)
                    if msg not in output.missing_information:
                        output.missing_information.append(msg)

            finding.supporting_evidence_references = sanitized_refs

            # 3. Provenance validation: ensure valid enum and ground findings
            try:
                provenance = EvidenceProvenance(finding.source_provenance)
            except (ValueError, TypeError):
                provenance = EvidenceProvenance.MODEL_INFERENCE

            if (
                not finding.supporting_evidence_references
                and provenance != EvidenceProvenance.MODEL_INFERENCE
            ):
                # If finding has no grounded evidence references, mark as MODEL_INFERENCE
                provenance = EvidenceProvenance.MODEL_INFERENCE

            finding.source_provenance = provenance

        # 4. Anti-Prompt-Injection Non-Malice Invariant
        if output.overall_risk_sentiment == RiskSentiment.MALICIOUS:
            has_injection = any(
                f.category == FindingCategory.SOCIAL_ENGINEERING
                and any(
                    term in f.explanation.lower()
                    for term in ("injection", "override", "adversarial", "jailbreak")
                )
                for f in output.findings
            )
            has_confirmed_mule = bool(
                request.recipient_intelligence
                and request.recipient_intelligence.is_flagged_mule is True
            )
            if has_injection and not has_confirmed_mule:
                has_coercion = any(
                    f.category == FindingCategory.AUTHORITY_COERCION for f in output.findings
                ) or bool(request.coercion_cues)
                output.overall_risk_sentiment = (
                    RiskSentiment.COERCED if has_coercion else RiskSentiment.SUSPICIOUS
                )
                output.unresolved_questions.append(
                    "Adversarial prompt injection pattern detected in untrusted customer input; "
                    "neutralized as manipulation rather than proof of customer malice."
                )
                logger.info(
                    "Neutralized MALICIOUS sentiment to %s for tx=%s due to prompt injection.",
                    output.overall_risk_sentiment,
                    tx.id,
                )

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
