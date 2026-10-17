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
from app.domain.investigation import (
    ConfidenceLevel,
    EvidenceProvenance,
    FindingCategory,
    InvestigationModelMetadata,
    RiskSentiment,
)
from app.schemas.investigation import (
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


class MockGeminiClient:
    """Configurable mock AI client for unit/integration tests and offline development."""

    def __init__(
        self,
        default_output: InvestigationStructuredOutput | None = None,
        should_fail: bool = False,
        failure_exception: Exception | None = None,
        latency_ms: int = 45,
    ) -> None:
        self.default_output = default_output
        self.should_fail = should_fail
        self.failure_exception = failure_exception
        self.latency_ms = latency_ms

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
