/**
 * AI Investigation API client for AegisPay AI.
 * Handles Gemini-powered forensic analysis, evidence ingestion, and report retrieval.
 */

import { config } from '../config';

export type FindingCategory =
  | 'AUTHORITY_COERCION'
  | 'SOCIAL_ENGINEERING'
  | 'BENEFICIARY_INCONSISTENCY'
  | 'URGENCY_MANIPULATION'
  | 'DOCUMENT_FABRICATION'
  | 'MULE_VELOCITY'
  | 'LEGITIMATE_CONTEXT'
  | 'INSUFFICIENT_EVIDENCE';

export type RiskSentiment =
  | 'BENIGN'
  | 'SUSPICIOUS'
  | 'COERCED'
  | 'MALICIOUS'
  | 'UNKNOWN';

export type ConfidenceLevel = 'LOW' | 'MEDIUM' | 'HIGH';

export type EvidenceProvenance =
  | 'customer_statement'
  | 'document_extraction'
  | 'device_telephony'
  | 'consortium_registry'
  | 'risk_engine'
  | 'historical_ledger';

export interface CustomerStatementEvidence {
  statement_id: string;
  question: string;
  answer: string;
  channel?: string;
  timestamp?: string;
}

export interface DocumentExtractionEvidence {
  doc_id: string;
  document_type?: string;
  claimed_issuer?: string;
  claimed_amount?: number;
  extracted_text: string;
  verification_source?: string;
}

export interface TelephonyTelemetryEvidence {
  active_call_present?: boolean;
  screen_sharing_active?: boolean;
  voice_stress_detected?: boolean;
  call_duration_seconds?: number;
}

export interface RecipientIntelligenceEvidence {
  is_flagged_mule?: boolean;
  account_age_days?: number;
  fan_in_count_24h?: number;
  fan_out_count_24h?: number;
  payee_name_mismatch?: boolean;
  routing_mismatch?: boolean;
}

export interface InvestigateTransactionRequest {
  transaction_id: string;
  assessment_id?: string;
  customer_statements?: CustomerStatementEvidence[];
  document_extractions?: DocumentExtractionEvidence[];
  telephony_telemetry?: TelephonyTelemetryEvidence;
  recipient_intelligence?: RecipientIntelligenceEvidence;
  coercion_cues?: string[];
  correlation_id?: string;
}

export interface InvestigationFindingResponse {
  id: string;
  category: FindingCategory;
  explanation: string;
  severity: string;
  supporting_evidence_references: string[];
  source_provenance: EvidenceProvenance;
}

export interface InvestigationModelMetadataResponse {
  provider: string;
  model_id: string;
  latency_ms?: number;
  correlation_id?: string;
}

export interface InvestigationResponse {
  id: string;
  transaction_id: string;
  assessment_id?: string | null;
  summary: string;
  overall_risk_sentiment: RiskSentiment;
  confidence: ConfidenceLevel;
  confidence_score: number;
  findings: InvestigationFindingResponse[];
  contradictory_or_mitigating_evidence: string[];
  missing_information: string[];
  unresolved_questions: string[];
  suggested_next_steps: string[];
  model_metadata: InvestigationModelMetadataResponse;
  created_at: string;
}

export interface InvestigationListResponse {
  transaction_id: string;
  total_entries: number;
  items: InvestigationResponse[];
}

/**
 * Initiates an AI forensic investigation for a transaction using Gemini.
 */
export async function investigateTransactionApi(
  request: InvestigateTransactionRequest
): Promise<InvestigationResponse> {
  const url = `${config.apiBaseUrl}/api/v1/investigations`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`AI investigation failed (${response.status}): ${errorText}`);
  }

  return (await response.json()) as InvestigationResponse;
}

/**
 * Fetches a single investigation report by its UUID.
 */
export async function getInvestigationApi(
  investigationId: string
): Promise<InvestigationResponse> {
  const url = `${config.apiBaseUrl}/api/v1/investigations/${investigationId}`;
  const response = await fetch(url);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch investigation ${investigationId} (${response.status}): ${errorText}`);
  }

  return (await response.json()) as InvestigationResponse;
}

/**
 * Retrieves all AI investigations conducted for a transaction in chronological order.
 */
export async function fetchInvestigationsForTransactionApi(
  transactionId: string
): Promise<InvestigationListResponse> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/investigations`;
  const response = await fetch(url);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch investigations for transaction ${transactionId} (${response.status}): ${errorText}`);
  }

  return (await response.json()) as InvestigationListResponse;
}
