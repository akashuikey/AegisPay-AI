"""Gemini / Vertex AI client abstraction, Google GenAI client, and mock provider."""

import asyncio
import json
import re
import time
from typing import Protocol

from google import genai
from google.genai import errors, types

from app.core.config import Settings
from app.core.errors import AIConfigurationError, AIProviderError
from app.core.logging import get_logger
from app.domain.coercion import (
    CoercionCategory,
    CoercionLevel,
    CoercionSeverity,
)
from app.domain.investigation import (
    ConfidenceLevel,
    EvidenceProvenance,
    FindingCategory,
    InvestigationModelMetadata,
    RiskSentiment,
)
from app.schemas.coercion import (
    CoercionFindingSchema,
    CoercionStructuredOutput,
)
from app.schemas.investigation import (
    ConversationTurnStructuredOutput,
    InvestigationFindingSchema,
    InvestigationStructuredOutput,
)

logger = get_logger(__name__)


class AIInvestigationClient(Protocol):
    """Protocol defining interface for AI fraud investigation models."""

    async def generate_investigation(
        self,
        prompt: str,
        system_instruction: str,
        correlation_id: str | None = None,
    ) -> tuple[InvestigationStructuredOutput, InvestigationModelMetadata]:
        """Generate structured forensic findings from context."""
        ...

    async def generate_conversation_turn(
        self,
        prompt: str,
        system_instruction: str,
        correlation_id: str | None = None,
    ) -> tuple[ConversationTurnStructuredOutput, InvestigationModelMetadata]:
        """Generate structured forensic response and findings for a multi-turn conversation."""
        ...

    async def generate_coercion_analysis(
        self,
        prompt: str,
        system_instruction: str,
        correlation_id: str | None = None,
    ) -> tuple[CoercionStructuredOutput, InvestigationModelMetadata]:
        """Generate structured forensic coercion findings from call transcript."""
        ...


class VertexGeminiClient:
    """Client for Google Cloud Vertex AI Gemini using the official google-genai SDK."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model_id = settings.GEMINI_MODEL_ID
        self.timeout = settings.GEMINI_REQUEST_TIMEOUT_SECONDS
        self.max_retries = settings.GEMINI_MAX_RETRIES
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        """Lazily initialize shared Google GenAI Client with Vertex AI or API key."""
        if self._client is not None:
            return self._client

        if self.settings.GCP_PROJECT_ID:
            logger.info(
                "Initializing Vertex AI Gemini client for project=%s location=%s model=%s",
                self.settings.GCP_PROJECT_ID,
                self.settings.GCP_LOCATION,
                self.model_id,
            )
            self._client = genai.Client(
                vertexai=True,
                project=self.settings.GCP_PROJECT_ID,
                location=self.settings.GCP_LOCATION,
            )
        elif self.settings.GEMINI_API_KEY:
            logger.info("Initializing Gemini Developer API client with API key")
            self._client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        else:
            raise AIConfigurationError(
                "Neither GCP_PROJECT_ID nor GEMINI_API_KEY is configured. "
                "Set Vertex AI credentials or GEMINI_API_KEY to enable live model investigation."
            )
        return self._client

    async def generate_investigation(
        self,
        prompt: str,
        system_instruction: str,
        correlation_id: str | None = None,
    ) -> tuple[InvestigationStructuredOutput, InvestigationModelMetadata]:
        """Execute Gemini model generation with structured JSON schema and retry logic."""
        client = self._get_client()
        start_time = time.monotonic()

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=InvestigationStructuredOutput,
            temperature=0.1,
        )

        attempts = 0
        last_error: Exception | None = None

        while attempts <= self.max_retries:
            attempts += 1
            try:
                logger.info(
                    "Calling Gemini model=%s (attempt %d/%d, correlation_id=%s)",
                    self.model_id,
                    attempts,
                    self.max_retries + 1,
                    correlation_id,
                )
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=self.model_id,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=self.timeout,
                )

                latency_ms = int((time.monotonic() - start_time) * 1000)
                raw_text = response.text
                if not raw_text:
                    raise AIProviderError(
                        message="Gemini model returned empty response",
                        code="AI_EMPTY_RESPONSE",
                        status_code=502,
                    )

                try:
                    parsed_json = json.loads(raw_text)
                    structured_output = InvestigationStructuredOutput.model_validate(parsed_json)
                except Exception as parse_err:
                    logger.error(
                        "Failed to parse Gemini output into structured schema: %s", parse_err
                    )
                    raise AIProviderError(
                        message=(
                            "Model output did not match expected structured investigation schema"
                        ),
                        code="AI_PARSE_ERROR",
                        status_code=502,
                        details={"raw_output_snippet": raw_text[:500]},
                    ) from parse_err

                metadata = InvestigationModelMetadata(
                    provider="vertex_ai" if self.settings.GCP_PROJECT_ID else "gemini_api",
                    model_id=self.model_id,
                    latency_ms=latency_ms,
                    correlation_id=correlation_id,
                )
                return structured_output, metadata

            except TimeoutError:
                logger.warning("Gemini generation timed out after %.1fs", self.timeout)
                last_error = AIProviderError(
                    message=f"AI investigation timed out after {self.timeout}s",
                    code="AI_PROVIDER_TIMEOUT",
                    status_code=504,
                )
            except errors.APIError as api_err:
                err_code = getattr(api_err, "code", None)
                err_msg = str(api_err)
                logger.warning("Gemini API error (code=%s): %s", err_code, err_msg)

                if err_code == 429:
                    raise AIProviderError(
                        message="AI investigation rate limit or quota exceeded",
                        code="AI_RATE_LIMIT_EXCEEDED",
                        status_code=429,
                    ) from api_err

                if err_code == 403:
                    raise AIProviderError(
                        message=(
                            "AI investigation permission denied or authentication failure "
                            "with provider"
                        ),
                        code="AI_PERMISSION_DENIED",
                        status_code=502,
                    ) from api_err

                # Retry on transient server errors (500, 502, 503, 504)
                if err_code in (500, 502, 503, 504) and attempts <= self.max_retries:
                    backoff = 0.5 * (2 ** (attempts - 1))
                    await asyncio.sleep(backoff)
                    continue

                last_error = AIProviderError(
                    message="AI investigation provider encountered an error",
                    code="AI_PROVIDER_ERROR",
                    status_code=502,
                )
                break
            except Exception as general_err:
                if isinstance(general_err, (AIProviderError, AIConfigurationError)):
                    raise
                logger.error("Unexpected error during Gemini execution: %s", general_err)
                last_error = AIProviderError(
                    message="Unexpected error communicating with AI investigation provider",
                    code="AI_PROVIDER_ERROR",
                    status_code=502,
                )
                break

        if last_error:
            raise last_error

        raise AIProviderError(
            message="AI investigation failed after retries",
            code="AI_PROVIDER_UNAVAILABLE",
            status_code=503,
        )

    async def generate_conversation_turn(
        self,
        prompt: str,
        system_instruction: str,
        correlation_id: str | None = None,
    ) -> tuple[ConversationTurnStructuredOutput, InvestigationModelMetadata]:
        """Execute Gemini model generation for conversation turn with structured JSON schema."""
        client = self._get_client()
        start_time = time.monotonic()

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=ConversationTurnStructuredOutput,
            temperature=0.1,
        )

        attempts = 0
        last_error: Exception | None = None

        while attempts <= self.max_retries:
            attempts += 1
            try:
                logger.info(
                    "Calling Gemini for turn model=%s (attempt %d/%d, correlation_id=%s)",
                    self.model_id,
                    attempts,
                    self.max_retries + 1,
                    correlation_id,
                )
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=self.model_id,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=self.timeout,
                )

                latency_ms = int((time.monotonic() - start_time) * 1000)
                raw_text = response.text
                if not raw_text:
                    raise AIProviderError(
                        message="Gemini model returned empty response for conversation turn",
                        code="AI_EMPTY_RESPONSE",
                        status_code=502,
                    )

                try:
                    parsed_json = json.loads(raw_text)
                    structured_output = ConversationTurnStructuredOutput.model_validate(parsed_json)
                except Exception as parse_err:
                    logger.error(
                        "Failed to parse Gemini output into structured turn schema: %s",
                        parse_err,
                    )
                    raise AIProviderError(
                        message=("Model output did not match expected structured turn schema"),
                        code="AI_PARSE_ERROR",
                        status_code=502,
                        details={"raw_output_snippet": raw_text[:500]},
                    ) from parse_err

                metadata = InvestigationModelMetadata(
                    provider="vertex_ai" if self.settings.GCP_PROJECT_ID else "gemini_api",
                    model_id=self.model_id,
                    latency_ms=latency_ms,
                    correlation_id=correlation_id,
                )
                return structured_output, metadata

            except TimeoutError:
                logger.warning("Gemini conversation turn timed out after %.1fs", self.timeout)
                last_error = AIProviderError(
                    message=f"AI investigation timed out after {self.timeout}s",
                    code="AI_PROVIDER_TIMEOUT",
                    status_code=504,
                )
            except errors.APIError as api_err:
                err_code = getattr(api_err, "code", None)
                err_msg = str(api_err)
                logger.warning("Gemini API error during turn (code=%s): %s", err_code, err_msg)

                if err_code == 429:
                    raise AIProviderError(
                        message="AI investigation rate limit or quota exceeded",
                        code="AI_RATE_LIMIT_EXCEEDED",
                        status_code=429,
                    ) from api_err

                if err_code == 403:
                    raise AIProviderError(
                        message=(
                            "AI investigation permission denied or authentication failure "
                            "with provider"
                        ),
                        code="AI_PERMISSION_DENIED",
                        status_code=502,
                    ) from api_err

                if err_code in (500, 502, 503, 504) and attempts <= self.max_retries:
                    backoff = 0.5 * (2 ** (attempts - 1))
                    await asyncio.sleep(backoff)
                    continue

                last_error = AIProviderError(
                    message="AI investigation provider encountered an error",
                    code="AI_PROVIDER_ERROR",
                    status_code=502,
                )
                break
            except Exception as general_err:
                if isinstance(general_err, (AIProviderError, AIConfigurationError)):
                    raise
                logger.error("Unexpected error during Gemini turn execution: %s", general_err)
                last_error = AIProviderError(
                    message="Unexpected error communicating with AI investigation provider",
                    code="AI_PROVIDER_ERROR",
                    status_code=502,
                )
                break

        if last_error:
            raise last_error

        raise AIProviderError(
            message="AI investigation failed after retries",
            code="AI_PROVIDER_UNAVAILABLE",
            status_code=503,
        )

    async def generate_coercion_analysis(
        self,
        prompt: str,
        system_instruction: str,
        correlation_id: str | None = None,
    ) -> tuple[CoercionStructuredOutput, InvestigationModelMetadata]:
        """Execute Gemini model generation for call transcript coercion analysis."""
        client = self._get_client()
        start_time = time.monotonic()

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=CoercionStructuredOutput,
            temperature=0.1,
        )

        attempts = 0
        last_error: Exception | None = None

        while attempts <= self.max_retries:
            attempts += 1
            try:
                logger.info(
                    "Calling Gemini coercion model=%s (attempt %d/%d, correlation_id=%s)",
                    self.model_id,
                    attempts,
                    self.max_retries + 1,
                    correlation_id,
                )
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=self.model_id,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=self.timeout,
                )

                latency_ms = int((time.monotonic() - start_time) * 1000)
                raw_text = response.text
                if not raw_text:
                    raise AIProviderError(
                        message="Gemini model returned empty response for coercion analysis",
                        code="AI_EMPTY_RESPONSE",
                        status_code=502,
                    )

                try:
                    parsed_json = json.loads(raw_text)
                    structured_output = CoercionStructuredOutput.model_validate(parsed_json)
                except Exception as parse_err:
                    logger.error(
                        "Failed to parse Gemini coercion output into structured schema: %s",
                        parse_err,
                    )
                    raise AIProviderError(
                        message=("Model output did not match expected structured coercion schema"),
                        code="AI_PARSE_ERROR",
                        status_code=502,
                        details={"raw_output_snippet": raw_text[:500]},
                    ) from parse_err

                metadata = InvestigationModelMetadata(
                    provider="vertex_ai" if self.settings.GCP_PROJECT_ID else "gemini_api",
                    model_id=self.model_id,
                    latency_ms=latency_ms,
                    correlation_id=correlation_id,
                )
                return structured_output, metadata

            except TimeoutError:
                logger.warning("Gemini coercion analysis timed out after %.1fs", self.timeout)
                last_error = AIProviderError(
                    message=f"AI coercion analysis timed out after {self.timeout}s",
                    code="AI_PROVIDER_TIMEOUT",
                    status_code=504,
                )
            except errors.APIError as api_err:
                err_code = getattr(api_err, "code", None)
                err_msg = str(api_err)
                logger.warning("Gemini API error (code=%s): %s", err_code, err_msg)
                if err_code == 429:
                    raise AIProviderError(
                        message="AI coercion analysis rate limit or quota exceeded",
                        code="AI_RATE_LIMIT_EXCEEDED",
                        status_code=429,
                    ) from api_err
                last_error = AIProviderError(
                    message=f"AI provider returned error: {err_msg}",
                    code="AI_PROVIDER_ERROR",
                    status_code=502,
                )
                break
            except Exception as general_err:
                if isinstance(general_err, (AIProviderError, AIConfigurationError)):
                    raise
                logger.error("Unexpected error during Gemini coercion execution: %s", general_err)
                last_error = AIProviderError(
                    message="Unexpected error communicating with AI investigation provider",
                    code="AI_PROVIDER_ERROR",
                    status_code=502,
                )
                break

        if last_error:
            raise last_error

        raise AIProviderError(
            message="AI coercion analysis failed after retries",
            code="AI_PROVIDER_UNAVAILABLE",
            status_code=503,
        )


class MockGeminiClient:
    """Configurable mock AI client for unit/integration tests and offline development."""

    def __init__(
        self,
        default_output: InvestigationStructuredOutput | None = None,
        default_conversation_output: ConversationTurnStructuredOutput | None = None,
        default_coercion_output: CoercionStructuredOutput | None = None,
        should_fail: bool = False,
        failure_exception: Exception | None = None,
        latency_ms: int = 45,
    ) -> None:
        self.default_output = default_output
        self.default_conversation_output = default_conversation_output
        self.default_coercion_output = default_coercion_output
        self.should_fail = should_fail
        self.failure_exception = failure_exception
        self.latency_ms = latency_ms

    async def generate_coercion_analysis(
        self,
        prompt: str,
        system_instruction: str,
        correlation_id: str | None = None,
    ) -> tuple[CoercionStructuredOutput, InvestigationModelMetadata]:
        """Return predefined or dynamically synthesized coercion analysis output."""
        if self.should_fail:
            if self.failure_exception:
                raise self.failure_exception
            raise AIProviderError(
                message="Mocked AI provider failure",
                code="AI_PROVIDER_ERROR",
                status_code=502,
            )

        if self.default_coercion_output is not None:
            output = self.default_coercion_output
        else:
            output = self._synthesize_mock_coercion(prompt)

        metadata = InvestigationModelMetadata(
            provider="mock_gemini",
            model_id="gemini-2.5-flash-mock",
            latency_ms=self.latency_ms,
            correlation_id=correlation_id,
        )
        return output, metadata

    async def generate_investigation(
        self,
        prompt: str,
        system_instruction: str,
        correlation_id: str | None = None,
    ) -> tuple[InvestigationStructuredOutput, InvestigationModelMetadata]:
        """Return predefined or dynamically generated forensic investigation output."""
        if self.should_fail:
            if self.failure_exception:
                raise self.failure_exception
            raise AIProviderError(
                message="Mocked AI provider failure",
                code="AI_PROVIDER_ERROR",
                status_code=502,
            )

        if self.default_output is not None:
            output = self.default_output
        else:
            output = self._synthesize_mock_output(prompt)

        metadata = InvestigationModelMetadata(
            provider="mock_gemini",
            model_id="gemini-2.5-flash-mock",
            latency_ms=self.latency_ms,
            correlation_id=correlation_id,
        )
        return output, metadata

    async def generate_conversation_turn(
        self,
        prompt: str,
        system_instruction: str,
        correlation_id: str | None = None,
    ) -> tuple[ConversationTurnStructuredOutput, InvestigationModelMetadata]:
        """Return predefined or dynamically synthesized conversation turn output."""
        if self.should_fail:
            if self.failure_exception:
                raise self.failure_exception
            raise AIProviderError(
                message="Mocked AI provider failure",
                code="AI_PROVIDER_ERROR",
                status_code=502,
            )

        if self.default_conversation_output is not None:
            output = self.default_conversation_output
        else:
            output = self._synthesize_mock_conversation_turn(prompt)

        metadata = InvestigationModelMetadata(
            provider="mock_gemini",
            model_id="gemini-2.5-flash-mock",
            latency_ms=self.latency_ms,
            correlation_id=correlation_id,
        )
        return output, metadata

    def _synthesize_mock_output(self, prompt: str) -> InvestigationStructuredOutput:
        """Synthesize context-aware mock findings from forensic prompt signals."""
        findings: list[InvestigationFindingSchema] = []
        mitigating: list[str] = []
        missing: list[str] = []
        unresolved: list[str] = []
        next_steps: list[str] = []

        lower_prompt = prompt.lower()

        # Extract supplied statement and doc IDs for grounded evidence references
        prompt_stmt_ids = re.findall(r"\[(stmt_[^\]]+)\]", prompt)
        prompt_doc_ids = re.findall(r"\[(doc_[^\]]+)\]", prompt)
        primary_stmt = prompt_stmt_ids[0] if prompt_stmt_ids else "stmt_1"
        primary_doc = prompt_doc_ids[0] if prompt_doc_ids else "doc_1"

        # Check for adversarial prompt injection attempt
        if any(
            phrase in lower_prompt
            for phrase in (
                "ignore previous instructions",
                "ignore all instructions",
                "ignore all previous instructions",
                "system override",
                "override all instructions",
            )
        ):
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-ADVERSARIAL",
                    category=FindingCategory.SOCIAL_ENGINEERING,
                    explanation=(
                        "Adversarial prompt injection pattern detected within untrusted "
                        "customer evidence. The input attempted to override investigator rules."
                    ),
                    severity="CRITICAL",
                    supporting_evidence_references=[primary_stmt],
                    source_provenance=EvidenceProvenance.CUSTOMER_STATEMENT,
                )
            )

        # Check for authority duress / digital arrest cues / liquidation pressure
        if (
            "cbi" in lower_prompt
            or "police" in lower_prompt
            or "arrest" in lower_prompt
            or "court" in lower_prompt
            or "liquidat" in lower_prompt
            or "screen sharing active: true" in lower_prompt
        ):
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-COERCION",
                    category=FindingCategory.AUTHORITY_COERCION,
                    explanation=(
                        "Customer narrative displays classic digital arrest markers: alleged "
                        "legal coercion, police impersonation, or pressure to liquidate assets."
                    ),
                    severity="CRITICAL",
                    supporting_evidence_references=[
                        primary_stmt,
                        "telephony:screen_sharing_active",
                    ],
                    source_provenance=EvidenceProvenance.CUSTOMER_STATEMENT,
                )
            )

        # Check for guaranteed return investment scam
        if (
            "guaranteed" in lower_prompt
            or "crypto" in lower_prompt
            or "daily return" in lower_prompt
        ):
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-INVESTMENT-SCAM",
                    category=FindingCategory.SOCIAL_ENGINEERING,
                    explanation=(
                        "Customer was lured with promises of unrealistic guaranteed returns "
                        "and instructed to dismiss bank warnings."
                    ),
                    severity="HIGH",
                    supporting_evidence_references=[primary_stmt],
                    source_provenance=EvidenceProvenance.CUSTOMER_STATEMENT,
                )
            )

        # Check for invoice routing discrepancy
        if (
            "routing mismatch: true" in lower_prompt
            or "payee name mismatch: true" in lower_prompt
            or "routing / ifsc mismatch: true" in lower_prompt
            or ("invoice" in lower_prompt and "mismatch" in lower_prompt)
        ):
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-INVOICE-DISCREPANCY",
                    category=FindingCategory.BENEFICIARY_INCONSISTENCY,
                    explanation=(
                        "Submitted invoice routing details contradict historical vendor ledger."
                    ),
                    severity="HIGH",
                    supporting_evidence_references=[primary_doc],
                    source_provenance=EvidenceProvenance.DOCUMENT_EXTRACTION,
                )
            )

        # Check for mule accounts (avoid false matching "flagged as known mule: false")
        if (
            "flagged as known mule: true" in lower_prompt
            or "known mule account" in lower_prompt
            or "confirmed mule" in lower_prompt
        ):
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-MULE-REGISTRY",
                    category=FindingCategory.MULE_VELOCITY,
                    explanation=(
                        "Beneficiary account matches consortium mule registry and rapid turnover."
                    ),
                    severity="CRITICAL",
                    supporting_evidence_references=["consortium_registry"],
                    source_provenance=EvidenceProvenance.CONSORTIUM_REGISTRY,
                )
            )

        # Check for legitimate transfer
        if "routine payment" in lower_prompt or "annual lease" in lower_prompt:
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-LEGITIMATE",
                    category=FindingCategory.LEGITIMATE_CONTEXT,
                    explanation=(
                        "Payment matches routine verified profile with trusted beneficiary."
                    ),
                    severity="LOW",
                    supporting_evidence_references=["historical_ledger"],
                    source_provenance=EvidenceProvenance.HISTORICAL_LEDGER,
                )
            )
            mitigating.append(
                "Established payee relationship with prior verified transaction history."
            )

        # Default fallback finding if empty
        if not findings:
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-INSUFFICIENT-DATA",
                    category=FindingCategory.INSUFFICIENT_EVIDENCE,
                    explanation=(
                        "Limited contextual evidence provided. Unable to establish deception."
                    ),
                    severity="LOW",
                    supporting_evidence_references=[],
                    source_provenance=EvidenceProvenance.RISK_ENGINE,
                )
            )
            missing.append("Customer statement transcript")
            unresolved.append("Source of payee introduction")

        # Determine overall sentiment
        severities = {f.severity for f in findings}
        categories = {f.category for f in findings}

        if any(f.id == "FINDING-ADVERSARIAL" for f in findings):
            # Adversarial prompt injection is social engineering, not proof of customer malice
            sentiment = (
                RiskSentiment.COERCED
                if FindingCategory.AUTHORITY_COERCION in categories
                else RiskSentiment.SUSPICIOUS
            )
            summary = (
                "Adversarial prompt injection attempt detected within untrusted context; "
                "treated as manipulation rather than proof of customer malice."
            )
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.90
            next_steps.append(
                "Isolate untrusted directive and conduct manual fraud analyst review."
            )
        elif FindingCategory.MULE_VELOCITY in categories and any(
            f.id == "FINDING-MULE-REGISTRY" for f in findings
        ):
            sentiment = RiskSentiment.MALICIOUS
            summary = "Confirmed mule registry match and rapid fan-out dispersal detected."
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.96
            next_steps.append("Block payment and report beneficiary to consortium registry.")
        elif FindingCategory.AUTHORITY_COERCION in categories:
            sentiment = RiskSentiment.COERCED
            summary = "High-confidence authority impersonation and psychological duress detected."
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.94
            next_steps.append(
                "Initiate simulated emergency voice duress intervention with customer."
            )
        elif "CRITICAL" in severities or "HIGH" in severities:
            sentiment = RiskSentiment.SUSPICIOUS
            summary = (
                "Elevated indicators of fraud or social engineering discovered during analysis."
            )
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.88
            next_steps.append("Escalate case to senior fraud investigator for manual verification.")
        elif FindingCategory.LEGITIMATE_CONTEXT in categories:
            sentiment = RiskSentiment.BENIGN
            summary = (
                "Contextual evidence indicates legitimate routine transaction "
                "with established payee."
            )
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.92
            next_steps.append("Allow simulated settlement in accordance with deterministic policy.")
        else:
            sentiment = RiskSentiment.UNKNOWN
            summary = "Ambiguous evidence profile. Further customer context required."
            confidence = ConfidenceLevel.MEDIUM
            confidence_score = 0.50
            next_steps.append(
                "Request secondary confirmation and invoice verification from customer."
            )

        return InvestigationStructuredOutput(
            summary=summary,
            overall_risk_sentiment=sentiment,
            confidence=confidence,
            confidence_score=confidence_score,
            findings=findings,
            contradictory_or_mitigating_evidence=mitigating,
            missing_information=missing,
            unresolved_questions=unresolved,
            suggested_next_steps=next_steps,
        )

    def _synthesize_mock_conversation_turn(self, prompt: str) -> ConversationTurnStructuredOutput:
        """Synthesize dynamic multi-turn conversational findings and targeted questions."""
        findings: list[InvestigationFindingSchema] = []
        mitigating: list[str] = []
        missing: list[str] = []
        follow_up: list[str] = []

        lower_prompt = prompt.lower()

        # Extract statement and doc IDs for grounded evidence references
        prompt_stmt_ids = re.findall(r"\[(stmt_[^\]]+)\]", prompt)
        prompt_doc_ids = re.findall(r"\[(doc_[^\]]+)\]", prompt)
        primary_stmt = prompt_stmt_ids[0] if prompt_stmt_ids else None
        primary_doc = prompt_doc_ids[0] if prompt_doc_ids else None

        # Check for adversarial prompt injection attempt in untrusted turn
        if any(
            phrase in lower_prompt
            for phrase in (
                "ignore previous instructions",
                "ignore all instructions",
                "ignore all previous instructions",
                "system override",
                "override all instructions",
            )
        ):
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-ADVERSARIAL",
                    category=FindingCategory.SOCIAL_ENGINEERING,
                    explanation=(
                        "Adversarial prompt injection pattern detected within untrusted "
                        "conversation input. The input attempted to override investigator rules "
                        "or transaction policies."
                    ),
                    severity="CRITICAL",
                    supporting_evidence_references=[primary_stmt]
                    if primary_stmt
                    else ["untrusted_turn"],
                    source_provenance=EvidenceProvenance.CUSTOMER_STATEMENT,
                )
            )

        # Check for authority coercion / digital arrest cues
        if (
            "cbi" in lower_prompt
            or "police" in lower_prompt
            or "arrest" in lower_prompt
            or "court" in lower_prompt
            or "liquidat" in lower_prompt
            or "screen sharing active: true" in lower_prompt
            or "screen_sharing" in lower_prompt
            or "digital arrest" in lower_prompt
        ):
            supporting_refs = []
            if primary_stmt:
                supporting_refs.append(primary_stmt)
            if "screen sharing active: true" in lower_prompt:
                supporting_refs.append("telephony:screen_sharing_active")
            if not supporting_refs:
                supporting_refs.append("conversation_context")

            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-COERCION",
                    category=FindingCategory.AUTHORITY_COERCION,
                    explanation=(
                        "Customer narrative displays digital arrest markers: alleged legal "
                        "coercion, law enforcement impersonation, or pressure to liquidate assets."
                    ),
                    severity="CRITICAL",
                    supporting_evidence_references=supporting_refs,
                    source_provenance=EvidenceProvenance.CUSTOMER_STATEMENT,
                )
            )

        # Check for guaranteed return investment scam
        if (
            "guaranteed" in lower_prompt
            or "crypto" in lower_prompt
            or "daily return" in lower_prompt
            or "investment" in lower_prompt
        ):
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-INVESTMENT-SCAM",
                    category=FindingCategory.SOCIAL_ENGINEERING,
                    explanation=(
                        "Customer was lured with promises of unrealistic guaranteed investment "
                        "returns and instructed to dismiss banking warnings."
                    ),
                    severity="HIGH",
                    supporting_evidence_references=[primary_stmt]
                    if primary_stmt
                    else ["conversation_context"],
                    source_provenance=EvidenceProvenance.CUSTOMER_STATEMENT,
                )
            )

        # Check for invoice routing discrepancy
        if (
            "routing mismatch: true" in lower_prompt
            or "payee name mismatch: true" in lower_prompt
            or "routing / ifsc mismatch: true" in lower_prompt
            or ("invoice" in lower_prompt and "mismatch" in lower_prompt)
        ):
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-INVOICE-DISCREPANCY",
                    category=FindingCategory.BENEFICIARY_INCONSISTENCY,
                    explanation=(
                        "Submitted invoice routing details contradict historical "
                        "vendor ledger records."
                    ),
                    severity="HIGH",
                    supporting_evidence_references=[primary_doc]
                    if primary_doc
                    else ["conversation_context"],
                    source_provenance=EvidenceProvenance.DOCUMENT_EXTRACTION,
                )
            )

        # Check for mule accounts
        if (
            "flagged as known mule: true" in lower_prompt
            or "known mule account" in lower_prompt
            or "confirmed mule" in lower_prompt
        ):
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-MULE-REGISTRY",
                    category=FindingCategory.MULE_VELOCITY,
                    explanation=(
                        "Beneficiary account matches consortium mule registry and "
                        "rapid turnover profile."
                    ),
                    severity="CRITICAL",
                    supporting_evidence_references=["consortium_registry"],
                    source_provenance=EvidenceProvenance.CONSORTIUM_REGISTRY,
                )
            )

        # Check for legitimate transfer
        if "routine payment" in lower_prompt or "annual lease" in lower_prompt:
            findings.append(
                InvestigationFindingSchema(
                    id="FINDING-LEGITIMATE",
                    category=FindingCategory.LEGITIMATE_CONTEXT,
                    explanation=(
                        "Payment matches routine verified profile with "
                        "established beneficiary relationship."
                    ),
                    severity="LOW",
                    supporting_evidence_references=["historical_ledger"],
                    source_provenance=EvidenceProvenance.HISTORICAL_LEDGER,
                )
            )
            mitigating.append(
                "Established payee relationship with prior verified transaction history."
            )

        # Determine sentiment, reply, and targeted follow-up questions
        categories = {f.category for f in findings}

        if any(f.id == "FINDING-ADVERSARIAL" for f in findings):
            sentiment = (
                RiskSentiment.COERCED
                if FindingCategory.AUTHORITY_COERCION in categories
                else RiskSentiment.SUSPICIOUS
            )
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.90
            reply = (
                "Adversarial prompt injection attempt detected and safely quarantined. "
                "The untrusted directive was neutralized into social engineering context "
                "rather than customer malice."
            )
            follow_up.append(
                "Did an external caller or message instruct the customer to type or paste "
                "these specific phrases?"
            )

        elif FindingCategory.AUTHORITY_COERCION in categories:
            sentiment = RiskSentiment.COERCED
            # Multi-turn adaptation: check if operator/customer confirmed key coercion details
            has_answered_disconnect = (
                "do not disconnect" in lower_prompt
                or "active call" in lower_prompt
                or "kept on call" in lower_prompt
            )
            has_answered_safe_account = (
                "safe reserve" in lower_prompt
                or "safe account" in lower_prompt
                or "police account" in lower_prompt
            )

            if has_answered_disconnect or has_answered_safe_account:
                confidence = ConfidenceLevel.HIGH
                confidence_score = 0.96
                reply = (
                    "Forensic analysis confirms high-probability authority coercion and "
                    "digital arrest scam. Customer testimony verifies instructions to stay "
                    "on continuous call and transfer funds under legal intimidation."
                )
                follow_up.append(
                    "Has the customer been instructed to install remote desktop tools "
                    "(e.g. AnyDesk, RustDesk)?"
                )
                follow_up.append(
                    "Can the branch or anti-fraud desk initiate an immediate simulated "
                    "voice duress intervention?"
                )
            else:
                confidence = ConfidenceLevel.MEDIUM
                confidence_score = 0.84
                reply = (
                    "Initial forensic analysis indicates strong signals of authority "
                    "impersonation duress. Key coercive markers require follow-up verification."
                )
                follow_up.append(
                    "Did the caller demand the customer maintain continuous audio/video connection?"
                )
                follow_up.append(
                    "Did the caller state that funds must be transferred to a 'safe reserve "
                    "account' for verification?"
                )
                follow_up.append(
                    "Is the customer currently on an active call while attempting this transaction?"
                )

        elif FindingCategory.MULE_VELOCITY in categories:
            sentiment = RiskSentiment.MALICIOUS
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.96
            reply = (
                "Forensic match: Beneficiary account appears on consortium mule registry with "
                "high turnover velocity. High confidence malicious beneficiary."
            )
            follow_up.append(
                "Has the beneficiary account been flagged across other partner institutions "
                "in the last 24 hours?"
            )

        elif FindingCategory.BENEFICIARY_INCONSISTENCY in categories:
            sentiment = RiskSentiment.SUSPICIOUS
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.86
            reply = (
                "Analysis indicates beneficiary routing discrepancy or potential business email "
                "compromise (BEC). Account details do not align with known supplier history."
            )
            follow_up.append(
                "Was the revised invoice received via an altered or lookalike email domain?"
            )
            follow_up.append(
                "Has the operator verified the beneficiary bank details with the vendor via "
                "an out-of-band phone call?"
            )

        elif FindingCategory.SOCIAL_ENGINEERING in categories:
            sentiment = RiskSentiment.SUSPICIOUS
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.88
            reply = (
                "Forensic indicators point toward social engineering through an investment or "
                "task scam with false promises."
            )
            follow_up.append(
                "Where did the customer first encounter this investment opportunity "
                "(e.g., WhatsApp, Telegram)?"
            )
            follow_up.append(
                "Has the customer previously received any small withdrawal or refund to "
                "build credibility?"
            )

        elif FindingCategory.LEGITIMATE_CONTEXT in categories:
            sentiment = RiskSentiment.BENIGN
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.92
            reply = (
                "Forensic context is consistent with legitimate routine transaction behavior. "
                "Established beneficiary profile verified."
            )

        else:
            sentiment = RiskSentiment.UNKNOWN
            confidence = ConfidenceLevel.MEDIUM
            confidence_score = 0.50
            reply = (
                "Forensic context updated with operator inquiry. Evidence profile remains "
                "ambiguous; additional verification recommended."
            )
            missing.append("Customer statement transcript")
            follow_up.append("Can the customer confirm if they personally know the beneficiary?")
            follow_up.append(
                "Was the customer asked to keep this transaction confidential from family or "
                "bank staff?"
            )

        # Filter out questions if their answer or key words were already mentioned in the prompt
        filtered_questions = [
            q
            for q in follow_up
            if not any(
                keyword in lower_prompt
                for keyword in ["do not disconnect", "remote desktop"]
                if keyword in q.lower()
            )
        ]
        if not filtered_questions and follow_up:
            filtered_questions = follow_up[:1]

        return ConversationTurnStructuredOutput(
            reply=reply,
            overall_risk_sentiment=sentiment,
            confidence=confidence,
            confidence_score=confidence_score,
            findings=findings,
            missing_information=missing,
            follow_up_questions=filtered_questions,
            contradictory_or_mitigating_evidence=mitigating,
        )

    def _synthesize_mock_coercion(self, prompt: str) -> CoercionStructuredOutput:
        """Synthesize context-aware mock coercion findings from call transcript."""
        # 1. Extract transcript from untrusted tags
        match = re.search(
            r"<untrusted_simulated_call_transcript>(.*?)</untrusted_simulated_call_transcript>",
            prompt,
            re.DOTALL,
        )
        transcript = match.group(1).strip() if match else prompt.strip()
        lower_transcript = transcript.lower()

        findings: list[CoercionFindingSchema] = []
        legitimate_explanations: list[str] = []
        uncertainty_notes: list[str] = []
        missing_information: list[str] = []

        def _get_exact_excerpt(text: str, target: str) -> str:
            idx = text.lower().find(target.lower())
            if idx == -1:
                return text[:50]
            start = max(
                text.rfind(".", 0, idx),
                text.rfind("\n", 0, idx),
                text.rfind("?", 0, idx),
                text.rfind("!", 0, idx),
                text.rfind(":", 0, idx),
            )
            start = 0 if start == -1 else start + 1
            end = len(text)
            for p in (".", "\n", "?", "!"):
                pos = text.find(p, idx)
                if pos != -1 and pos < end:
                    end = pos
            snippet = text[start:end].strip()
            return snippet if snippet else text[idx : idx + len(target)]

        # 2. Check for adversarial prompt injection
        injection_phrases = [
            "ignore previous instructions",
            "ignore all instructions",
            "system override",
            "safe transaction",
            "no coercion here",
            "mark safe",
            "bypass all checks",
        ]
        for phrase in injection_phrases:
            if phrase in lower_transcript:
                exc = _get_exact_excerpt(transcript, phrase)
                findings.append(
                    CoercionFindingSchema(
                        id=f"COERCION-{len(findings) + 1}",
                        category=CoercionCategory.BYPASS_SAFEGUARDS_INSTRUCTION,
                        severity=CoercionSeverity.HIGH,
                        is_explicit=True,
                        explanation=(
                            "Adversarial prompt injection attempt detected embedded in "
                            "call transcript."
                        ),
                        supporting_excerpt=exc,
                        provenance="simulated_call_transcript",
                    )
                )
                uncertainty_notes.append(
                    "Adversarial text injection detected in dialogue; instruction neutralized."
                )
                break

        # 3. Check for authority impersonation
        auth_terms = [
            "cbi",
            "police",
            "customs",
            "inspector",
            "narcotics",
            "enforcement directorate",
            "cyber crime",
            "trai",
            "court order",
            "magistrate",
        ]
        for term in auth_terms:
            if term in lower_transcript:
                exc = _get_exact_excerpt(transcript, term)
                findings.append(
                    CoercionFindingSchema(
                        id=f"COERCION-{len(findings) + 1}",
                        category=CoercionCategory.AUTHORITY_IMPERSONATION,
                        severity=CoercionSeverity.CRITICAL,
                        is_explicit=True,
                        explanation=(
                            "Caller claims authority as law enforcement or regulatory official "
                            "demanding compliance."
                        ),
                        supporting_excerpt=exc,
                        provenance="simulated_call_transcript",
                    )
                )
                break

        # 4. Check for legal or consequence threat ("digital arrest")
        threat_terms = [
            "digital arrest",
            "arrest",
            "warrant",
            "jail",
            "fir",
            "non-bailable",
            "confiscate",
            "seize your account",
            "freeze your account",
            "face criminal charges",
        ]
        for term in threat_terms:
            if term in lower_transcript:
                exc = _get_exact_excerpt(transcript, term)
                findings.append(
                    CoercionFindingSchema(
                        id=f"COERCION-{len(findings) + 1}",
                        category=CoercionCategory.LEGAL_OR_CONSEQUENCE_THREAT,
                        severity=CoercionSeverity.CRITICAL,
                        is_explicit=True,
                        explanation=(
                            "Caller threatens arrest, prosecution, or asset confiscation if "
                            "funds are not moved."
                        ),
                        supporting_excerpt=exc,
                        provenance="simulated_call_transcript",
                    )
                )
                break

        # 5. Check for secrecy demand
        secrecy_terms = [
            "don't tell anyone",
            "do not tell",
            "stay on the line",
            "keep this secret",
            "closed room",
            "do not disconnect",
            "confidential investigation",
            "national security",
            "do not speak to your family",
            "cannot tell anyone",
        ]
        for term in secrecy_terms:
            if term in lower_transcript:
                exc = _get_exact_excerpt(transcript, term)
                findings.append(
                    CoercionFindingSchema(
                        id=f"COERCION-{len(findings) + 1}",
                        category=CoercionCategory.SECRECY_DEMAND,
                        severity=CoercionSeverity.HIGH,
                        is_explicit=True,
                        explanation=(
                            "Caller demands victim maintain absolute secrecy and stay isolated."
                        ),
                        supporting_excerpt=exc,
                        provenance="simulated_call_transcript",
                    )
                )
                break

        # 6. Check for bypass safeguards instructions
        bypass_terms = [
            "tell the bank",
            "if the bank asks",
            "say it's for a relative",
            "personal transfer",
            "ignore bank warnings",
            "don't say anything to the teller",
            "bypass",
            "say medical emergency",
            "say it is for family",
        ]
        for term in bypass_terms:
            if term in lower_transcript:
                exc = _get_exact_excerpt(transcript, term)
                findings.append(
                    CoercionFindingSchema(
                        id=f"COERCION-{len(findings) + 1}",
                        category=CoercionCategory.BYPASS_SAFEGUARDS_INSTRUCTION,
                        severity=CoercionSeverity.HIGH,
                        is_explicit=True,
                        explanation=(
                            "Caller instructs victim to mislead bank staff or bypass safety "
                            "verification questions."
                        ),
                        supporting_excerpt=exc,
                        provenance="simulated_call_transcript",
                    )
                )
                break

        # 7. Check for remote access pressure
        remote_terms = [
            "anydesk",
            "teamviewer",
            "rustdesk",
            "screen share",
            "remote access",
            "install this app",
            "download apk",
            "quicksupport",
        ]
        for term in remote_terms:
            if term in lower_transcript:
                exc = _get_exact_excerpt(transcript, term)
                findings.append(
                    CoercionFindingSchema(
                        id=f"COERCION-{len(findings) + 1}",
                        category=CoercionCategory.REMOTE_ACCESS_PRESSURE,
                        severity=CoercionSeverity.HIGH,
                        is_explicit=True,
                        explanation=(
                            "Pressure to install screen sharing or remote management tools."
                        ),
                        supporting_excerpt=exc,
                        provenance="simulated_call_transcript",
                    )
                )
                break

        # 8. Check for investment guarantee
        invest_terms = [
            "guaranteed return",
            "100% profit",
            "risk-free",
            "double your money",
            "trading returns",
            "secret platform",
            "cryptocurrency profit",
        ]
        for term in invest_terms:
            if term in lower_transcript:
                exc = _get_exact_excerpt(transcript, term)
                findings.append(
                    CoercionFindingSchema(
                        id=f"COERCION-{len(findings) + 1}",
                        category=CoercionCategory.INVESTMENT_GUARANTEE,
                        severity=CoercionSeverity.HIGH,
                        is_explicit=True,
                        explanation=(
                            "Fraudulent claims of guaranteed investment profit and "
                            "risk-free returns."
                        ),
                        supporting_excerpt=exc,
                        provenance="simulated_call_transcript",
                    )
                )
                break

        # 9. Check for urgent transfer demand
        urgent_terms = [
            "within 15 minutes",
            "immediately",
            "right now",
            "urgently",
            "hurry",
            "urgent deadline",
            "transfer now",
            "before the timer runs out",
        ]
        for term in urgent_terms:
            if term in lower_transcript:
                exc = _get_exact_excerpt(transcript, term)
                findings.append(
                    CoercionFindingSchema(
                        id=f"COERCION-{len(findings) + 1}",
                        category=CoercionCategory.URGENT_TRANSFER_DEMAND,
                        severity=CoercionSeverity.MEDIUM,
                        is_explicit=True,
                        explanation=(
                            "Caller applies intense urgency pressure to force immediate transfer."
                        ),
                        supporting_excerpt=exc,
                        provenance="simulated_call_transcript",
                    )
                )
                break

        # 10. Check for legitimate explanation / mitigating context
        legit_terms = [
            "medical emergency",
            "hospital bill",
            "buying a car",
            "apartment deposit",
            "booking an apartment",
            "apartment",
            "landlord",
            "college",
            "real estate",
            "renovation",
            "vendor invoice",
            "paying my brother",
            "paying my sister",
            "school fee",
            "college tuition",
            "down payment",
            "verified vendor",
            "purchasing equipment",
            "contractor payment",
        ]
        for term in legit_terms:
            if term in lower_transcript:
                exc = _get_exact_excerpt(transcript, term)
                findings.append(
                    CoercionFindingSchema(
                        id=f"COERCION-{len(findings) + 1}",
                        category=CoercionCategory.LEGITIMATE_EXPLANATION,
                        severity=CoercionSeverity.INFO,
                        is_explicit=True,
                        explanation=(
                            "Dialogue provides legitimate commercial or personal context "
                            "without coercion."
                        ),
                        supporting_excerpt=exc,
                        provenance="simulated_call_transcript",
                    )
                )
                legitimate_explanations.append(
                    f"Customer stated legitimate transfer purpose: '{exc}'"
                )
                break

        # 11. Acoustic telemetry note
        lower_prompt = prompt.lower()
        has_acoustic_stress = any(
            phrase in lower_prompt
            for phrase in [
                "voice stress detected: true",
                "acoustic stress level: elevated",
                "acoustic stress level: high",
            ]
        )
        if has_acoustic_stress:
            if not any(
                f.severity in (CoercionSeverity.CRITICAL, CoercionSeverity.HIGH) for f in findings
            ):
                uncertainty_notes.append(
                    "Acoustic voice stress detected in telemetry; no verbal coercion, authority "
                    "threats, or duress indicators present in transcript."
                )
            else:
                uncertainty_notes.append(
                    "Acoustic voice stress correlates with verbal coercion cues in dialogue."
                )

        # 12. Evaluate overall coercion level and confidence
        has_critical = any(
            f.severity == CoercionSeverity.CRITICAL
            or f.category
            in (
                CoercionCategory.AUTHORITY_IMPERSONATION,
                CoercionCategory.LEGAL_OR_CONSEQUENCE_THREAT,
                CoercionCategory.SECRECY_DEMAND,
                CoercionCategory.BYPASS_SAFEGUARDS_INSTRUCTION,
            )
            for f in findings
        )
        has_suspected = any(
            f.category
            in (
                CoercionCategory.REMOTE_ACCESS_PRESSURE,
                CoercionCategory.INVESTMENT_GUARANTEE,
                CoercionCategory.URGENT_TRANSFER_DEMAND,
            )
            for f in findings
        )

        if has_critical:
            overall_level = CoercionLevel.CONFIRMED_COERCION
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.95
            summary = (
                "Critical coercion detected: dialogue contains explicit authority impersonation, "
                "consequence threats, or secrecy demands."
            )
        elif has_suspected:
            overall_level = CoercionLevel.SUSPECTED
            confidence = ConfidenceLevel.MEDIUM
            confidence_score = 0.75
            summary = (
                "Suspected coercion or social engineering pressure: dialogue contains urgency "
                "demands or manipulative inducement without confirmed authority impersonation."
            )
        elif legitimate_explanations and not findings:
            overall_level = CoercionLevel.NONE
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.90
            summary = (
                "No coercion detected: dialogue provides legitimate context and unpressured "
                "customer explanations."
            )
        else:
            overall_level = CoercionLevel.NONE
            confidence = ConfidenceLevel.HIGH
            confidence_score = 0.85
            summary = "No coercion or duress indicators detected in supplied call transcript."

        if not transcript or len(transcript) < 30:
            missing_information.append("Transcript duration and complete dialogue context")

        return CoercionStructuredOutput(
            overall_coercion_level=overall_level,
            confidence=confidence,
            confidence_score=confidence_score,
            findings=findings,
            legitimate_explanations=legitimate_explanations,
            uncertainty_notes=uncertainty_notes,
            missing_information=missing_information,
            summary=summary,
        )
