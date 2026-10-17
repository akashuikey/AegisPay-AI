"""Pydantic schemas for the automated decision workflow (P2-A4)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.decision_policy import PolicyAction
from app.domain.risk_engine import RiskLevel
from app.domain.state_machine import ActorType
from app.schemas.investigation import (
    CustomerStatementEvidence,
    DocumentExtractionEvidence,
    RecipientIntelligenceEvidence,
    TelephonyTelemetryEvidence,
)
from app.schemas.risk import TransactionEvidenceRequest


class WorkflowRiskEvidence(TransactionEvidenceRequest):
    """Risk evidence for the workflow, reusing all signal fields from the risk schema.

    ``amount``/currency/rail/recipient are taken from the authoritative transaction
    and overridden server-side, so they are optional here; a client value is ignored.
    """

    amount: Decimal = Field(default=Decimal("0.01"), gt=0, decimal_places=2)


class WorkflowInvestigationEvidence(BaseModel):
    """Optional contextual evidence passed to the investigation stage."""

    model_config = ConfigDict(extra="forbid")

    customer_statements: list[CustomerStatementEvidence] = Field(
        default_factory=list, max_length=50
    )
    document_extractions: list[DocumentExtractionEvidence] = Field(
        default_factory=list, max_length=20
    )
    telephony_telemetry: TelephonyTelemetryEvidence | None = None
    recipient_intelligence: RecipientIntelligenceEvidence | None = None
    coercion_cues: list[str] = Field(default_factory=list, max_length=20)


class EvaluateTransactionRequest(BaseModel):
    """Request to run the automated risk + policy decision workflow for a transaction."""

    model_config = ConfigDict(extra="forbid")

    evidence: WorkflowRiskEvidence | None = Field(
        default=None, description="Deterministic risk evidence inputs"
    )
    investigation: WorkflowInvestigationEvidence | None = Field(
        default=None, description="Optional contextual evidence for the investigation stage"
    )
    run_investigation: bool | None = Field(
        default=None,
        description=(
            "Override investigation gating: True forces it, False skips it, null auto-decides "
            "from deterministic risk."
        ),
    )
    actor_type: ActorType = ActorType.POLICY_ENGINE
    correlation_id: str | None = Field(default=None, max_length=64)


class DecisionResponse(BaseModel):
    """Automated decision record and the resulting (simulated) transaction state."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    transaction_state: str = Field(description="Current authoritative transaction state")
    policy_version: str
    action: PolicyAction
    risk_score: int
    risk_level: RiskLevel
    requires_verification: bool
    provider_failed: bool
    investigation_performed: bool
    from_state: str
    to_state: str
    workflow_status: str
    reason_codes: list[str]
    triggered_rule_ids: list[str]
    investigation_finding_refs: list[str]
    supporting_evidence_refs: list[str]
    missing_information: list[str]
    explanation: str
    simulated: bool = Field(
        default=True,
        description="Always true: all settlement/cancellation outcomes are simulated, not real.",
    )
    created_at: datetime
