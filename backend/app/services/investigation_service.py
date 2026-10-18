"""Application service orchestrating AI-driven forensic fraud investigations."""

import uuid
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.core.errors import (
    ConversationInactiveError,
    ConversationTurnLimitError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.db.models import (
    InvestigationConversationModel,
    InvestigationConversationTurnModel,
    TransactionAssessmentModel,
    TransactionInvestigationModel,
    TransactionModel,
)
from app.domain.investigation import (
    ConversationRole,
    ConversationStatus,
    EvidenceProvenance,
    FindingCategory,
    RiskSentiment,
)
from app.domain.investigation_prompts import (
    CONVERSATION_INVESTIGATION_SYSTEM_INSTRUCTION,
    INVESTIGATION_SYSTEM_INSTRUCTION,
    build_conversation_investigation_prompt,
    build_investigation_prompt,
)
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.investigation import (
    AddConversationTurnRequest,
    ConversationTurnStructuredOutput,
    InvestigateTransactionRequest,
    InvestigationStructuredOutput,
    StartConversationRequest,
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
        self.settings = get_settings()

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
        if tx.recipient_name:
            rname = tx.recipient_name.strip().lower()
            valid_refs.add(rname)
            valid_refs.add(f"recipient name: {rname}")
            valid_refs.add(f"recipient_name: {rname}")
        if tx.recipient_identifier:
            rident = tx.recipient_identifier.strip().lower()
            valid_refs.add(rident)
            valid_refs.add(f"recipient identifier: {rident}")
            valid_refs.add(f"recipient_identifier: {rident}")

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
                if isinstance(rule, dict):
                    rid = str(rule.get("rule_id", "")).strip().lower()
                    rname = str(rule.get("rule_name", "")).strip().lower()
                    if rid:
                        valid_refs.add(rid)
                        valid_refs.add(f"rule:{rid}")
                    if rname:
                        valid_refs.add(rname)
                        valid_refs.add(f"rule:{rname}")
                else:
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

    def _build_base_transaction_context(
        self, tx: TransactionModel, assessment: TransactionAssessmentModel | None
    ) -> dict[str, Any]:
        """Format baseline transaction context dictionary for AI forensic prompts."""
        return {
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
        }

    async def start_or_get_conversation(
        self, transaction_id: UUID, request: StartConversationRequest
    ) -> InvestigationConversationModel:
        """Start a new multi-turn investigation conversation or return/resume existing active one.

        Architectural Guardrails:
        - Strict Transaction Isolation: Conversations are strictly bound to their transaction.
        - Non-Mutation Invariant: Starting or updating an investigation conversation produces
          forensic intelligence and NEVER mutates transaction state or audit log.
        """
        # 1. Verify transaction existence
        tx = await self.transaction_service.get_transaction(transaction_id)

        # 2. Check for active existing conversation
        existing = await self.repository.get_active_conversation_for_transaction(transaction_id)
        if existing and existing.status == ConversationStatus.ACTIVE.value:
            if request.initial_message:
                return await self.submit_conversation_turn(
                    conversation_id=existing.id,
                    request=AddConversationTurnRequest(
                        content=request.initial_message,
                        evidence_provenance=request.evidence_provenance,
                        correlation_id=request.correlation_id,
                    ),
                    transaction_id=transaction_id,
                )
            return existing

        # 3. Create new conversation record
        conv_id = uuid.uuid4()
        conv = InvestigationConversationModel(
            id=conv_id,
            transaction_id=transaction_id,
            status=ConversationStatus.ACTIVE.value,
            turn_count=0,
            version=1,
        )
        saved_conv = await self.repository.create_conversation(conv)

        # 4. Initialize first turn(s)
        if request.initial_message:
            # Operator provided initial customer statement or message: submit as turn 0
            return await self.submit_conversation_turn(
                conversation_id=saved_conv.id,
                request=AddConversationTurnRequest(
                    content=request.initial_message,
                    evidence_provenance=request.evidence_provenance,
                    correlation_id=request.correlation_id,
                ),
                transaction_id=transaction_id,
            )

        # 5. Otherwise, generate initial assistant case assessment and targeted inquiries
        assessment = await self.repository.get_latest_assessment(transaction_id)
        context = self._build_base_transaction_context(tx=tx, assessment=assessment)
        initial_system_turn = {
            "turn_index": 0,
            "role": ConversationRole.SYSTEM.value,
            "evidence_provenance": EvidenceProvenance.RISK_ENGINE.value,
            "content": (
                "Case opened by operator. Analyze transaction context and deterministic "
                "risk profile. Provide preliminary forensic observations and targeted questions."
            ),
        }
        prompt = build_conversation_investigation_prompt(
            context, history=[], new_turn=initial_system_turn
        )
        output, metadata = await self.ai_client.generate_conversation_turn(
            prompt=prompt,
            system_instruction=CONVERSATION_INVESTIGATION_SYSTEM_INSTRUCTION,
            correlation_id=request.correlation_id,
        )

        self._validate_and_sanitize_turn_integrity(output, tx=tx, conversation_history=[])

        assistant_turn = InvestigationConversationTurnModel(
            id=uuid.uuid4(),
            conversation_id=saved_conv.id,
            turn_index=0,
            role=ConversationRole.ASSISTANT.value,
            content=output.reply,
            evidence_provenance=EvidenceProvenance.AI_ASSISTANT.value,
            evidence_references=[
                ref for f in output.findings for ref in f.supporting_evidence_references
            ],
            findings=[f.model_dump() for f in output.findings],
            risk_sentiment=output.overall_risk_sentiment.value,
            confidence=output.confidence.value,
            confidence_score=output.confidence_score,
            missing_information=output.missing_information,
            follow_up_questions=output.follow_up_questions,
            model_metadata={
                "provider": metadata.provider,
                "model_id": metadata.model_id,
                "latency_ms": metadata.latency_ms,
                "correlation_id": metadata.correlation_id,
            },
        )
        await self.repository.create_conversation_turn(assistant_turn)
        updated = await self.repository.update_conversation(
            conversation_id=saved_conv.id,
            turn_count=1,
            current_version=saved_conv.version,
        )
        return updated

    async def get_conversation(
        self, conversation_id: UUID, transaction_id: UUID | None = None
    ) -> InvestigationConversationModel:
        """Fetch conversation by ID, enforcing cross-transaction boundary isolation."""
        conv = await self.repository.get_conversation_by_id(conversation_id)
        if not conv:
            raise NotFoundError(
                f"Investigation conversation with ID '{conversation_id}' was not found"
            )

        if transaction_id and conv.transaction_id != transaction_id:
            logger.warning(
                "Cross-transaction access rejected: conv=%s belongs to tx=%s, not %s",
                conversation_id,
                conv.transaction_id,
                transaction_id,
            )
            raise NotFoundError(
                f"Investigation conversation with ID '{conversation_id}' was not found "
                f"for transaction '{transaction_id}'"
            )
        return conv

    async def list_conversations_for_transaction(
        self, transaction_id: UUID
    ) -> list[InvestigationConversationModel]:
        """Fetch all conversation sessions for a transaction."""
        await self.transaction_service.get_transaction(transaction_id)
        return await self.repository.list_conversations_for_transaction(transaction_id)

    async def submit_conversation_turn(
        self,
        conversation_id: UUID,
        request: AddConversationTurnRequest,
        transaction_id: UUID | None = None,
    ) -> InvestigationConversationModel:
        """Submit an operator message or customer evidence turn into active conversation."""
        # 1. Fetch conversation and enforce transaction isolation
        conv = await self.get_conversation(conversation_id, transaction_id=transaction_id)

        # 1.5 Idempotent replay: if this client_turn_id was already recorded on an operator
        # turn, return the current conversation state without creating duplicate turns. This
        # honors the documented idempotency contract for retried/duplicate submissions.
        if request.client_turn_id:
            for existing_turn in conv.turns:
                if (
                    existing_turn.role == ConversationRole.OPERATOR.value
                    and (existing_turn.model_metadata or {}).get("client_turn_id")
                    == request.client_turn_id
                ):
                    logger.info(
                        "Idempotent turn replay for conversation=%s client_turn_id=%s; "
                        "returning existing state without creating duplicate turns.",
                        conversation_id,
                        request.client_turn_id,
                    )
                    return conv

        # 2. Check conversation active status
        if conv.status != ConversationStatus.ACTIVE.value:
            raise ConversationInactiveError(
                f"Conversation '{conversation_id}' is {conv.status} and cannot accept new turns."
            )

        # 3. Check bounded turn limit
        max_turns = self.settings.INVESTIGATION_MAX_CONVERSATION_TURNS
        if conv.turn_count >= max_turns:
            raise ConversationTurnLimitError(
                f"Conversation '{conversation_id}' reached maximum turn limit of {max_turns}."
            )

        # 4. Fetch context
        tx = await self.transaction_service.get_transaction(conv.transaction_id)
        assessment = await self.repository.get_latest_assessment(conv.transaction_id)
        context = self._build_base_transaction_context(tx=tx, assessment=assessment)

        # 5. Format history for prompt
        history_list = [
            {
                "turn_index": t.turn_index,
                "role": t.role,
                "evidence_provenance": (
                    t.evidence_provenance or EvidenceProvenance.CUSTOMER_STATEMENT.value
                ),
                "content": t.content,
            }
            for t in sorted(conv.turns, key=lambda t: t.turn_index)
        ]

        operator_turn_dict = {
            "turn_index": conv.turn_count,
            "role": ConversationRole.OPERATOR.value,
            "evidence_provenance": request.evidence_provenance.value,
            "content": request.content,
        }

        prompt = build_conversation_investigation_prompt(
            context=context,
            history=history_list,
            new_turn=operator_turn_dict,
        )

        # 6. Execute AI model call
        output, metadata = await self.ai_client.generate_conversation_turn(
            prompt=prompt,
            system_instruction=CONVERSATION_INVESTIGATION_SYSTEM_INSTRUCTION,
            correlation_id=request.correlation_id,
        )

        # 7. Validate and sanitize evidence integrity
        self._validate_and_sanitize_turn_integrity(
            output=output,
            tx=tx,
            conversation_history=conv.turns,
            current_content=request.content,
        )

        # 8. Determine turn indexes
        operator_turn_index = conv.turn_count
        assistant_turn_index = operator_turn_index + 1
        new_turn_count = assistant_turn_index + 1

        # 9. Persist operator turn
        operator_model_metadata: dict[str, Any] = {}
        if request.client_turn_id:
            operator_model_metadata["client_turn_id"] = request.client_turn_id

        operator_turn = InvestigationConversationTurnModel(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            turn_index=operator_turn_index,
            role=ConversationRole.OPERATOR.value,
            content=request.content,
            evidence_provenance=request.evidence_provenance.value,
            evidence_references=[],
            findings=[],
            risk_sentiment=None,
            confidence=None,
            confidence_score=None,
            missing_information=[],
            follow_up_questions=[],
            model_metadata=operator_model_metadata,
        )
        await self.repository.create_conversation_turn(operator_turn)

        # 10. Persist assistant turn
        assistant_turn = InvestigationConversationTurnModel(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            turn_index=assistant_turn_index,
            role=ConversationRole.ASSISTANT.value,
            content=output.reply,
            evidence_provenance=EvidenceProvenance.AI_ASSISTANT.value,
            evidence_references=[
                ref for f in output.findings for ref in f.supporting_evidence_references
            ],
            findings=[f.model_dump() for f in output.findings],
            risk_sentiment=output.overall_risk_sentiment.value,
            confidence=output.confidence.value,
            confidence_score=output.confidence_score,
            missing_information=output.missing_information,
            follow_up_questions=output.follow_up_questions,
            model_metadata={
                "provider": metadata.provider,
                "model_id": metadata.model_id,
                "latency_ms": metadata.latency_ms,
                "correlation_id": metadata.correlation_id,
            },
        )
        await self.repository.create_conversation_turn(assistant_turn)

        # 11. Update conversation status and turn count
        new_status = ConversationStatus.COMPLETED.value if new_turn_count >= max_turns else None
        updated_conv = await self.repository.update_conversation(
            conversation_id=conv.id,
            turn_count=new_turn_count,
            current_version=conv.version,
            status=new_status,
        )
        return updated_conv

    def _validate_and_sanitize_turn_integrity(
        self,
        output: ConversationTurnStructuredOutput,
        tx: TransactionModel,
        conversation_history: list[InvestigationConversationTurnModel],
        current_content: str | None = None,
    ) -> None:
        """Validate multi-turn evidence references, provenance, and anti-injection non-malice."""
        # 1. Compile allowlist of verified evidence references
        valid_refs: set[str] = {
            "transaction",
            "transaction_id",
            str(tx.id).lower(),
            "amount",
            "purpose",
            "historical_ledger",
            "ledger",
            "conversation_context",
            "customer_statement",
            "telephony:screen_sharing_active",
            "telephony:active_call_present",
            "consortium_registry",
            "untrusted_turn",
        }

        for turn in conversation_history:
            valid_refs.add(f"turn_{turn.turn_index}")
            valid_refs.add(str(turn.id).lower())

        # 2. Validate finding references
        for finding in output.findings:
            sanitized_refs: list[str] = []
            for ref in finding.supporting_evidence_references:
                cleaned_ref = ref.strip().lower()
                if (
                    cleaned_ref in valid_refs
                    or cleaned_ref.startswith("stmt_")
                    or cleaned_ref.startswith("doc_")
                ):
                    sanitized_refs.append(ref)
                else:
                    msg = (
                        f"Evidence reference '{ref}' in finding {finding.id} "
                        "was not present in conversation input."
                    )
                    if msg not in output.missing_information:
                        output.missing_information.append(msg)

            finding.supporting_evidence_references = sanitized_refs

            # Provenance validation
            try:
                provenance = EvidenceProvenance(finding.source_provenance)
            except (ValueError, TypeError):
                provenance = EvidenceProvenance.MODEL_INFERENCE

            if (
                not finding.supporting_evidence_references
                and provenance != EvidenceProvenance.MODEL_INFERENCE
            ):
                provenance = EvidenceProvenance.MODEL_INFERENCE

            finding.source_provenance = provenance

        # 3. Anti-Prompt-Injection Non-Malice Invariant
        has_injection_in_finding = any(
            f.category == FindingCategory.SOCIAL_ENGINEERING
            and any(
                term in f.explanation.lower()
                for term in ("injection", "override", "adversarial", "jailbreak")
            )
            for f in output.findings
        )
        has_injection_in_content = bool(
            current_content
            and any(
                phrase in current_content.lower()
                for phrase in (
                    "ignore previous instructions",
                    "ignore all instructions",
                    "system override",
                    "override all instructions",
                )
            )
        )

        if (
            has_injection_in_finding or has_injection_in_content
        ) and output.overall_risk_sentiment == RiskSentiment.MALICIOUS:
            has_coercion = any(
                f.category == FindingCategory.AUTHORITY_COERCION for f in output.findings
            )
            output.overall_risk_sentiment = (
                RiskSentiment.COERCED if has_coercion else RiskSentiment.SUSPICIOUS
            )
            output.missing_information.append(
                "Adversarial prompt injection pattern detected in untrusted turn; "
                "neutralized as manipulation rather than proof of customer malice."
            )
            logger.info(
                "Neutralized turn sentiment to %s for tx=%s due to prompt injection.",
                output.overall_risk_sentiment,
                tx.id,
            )
