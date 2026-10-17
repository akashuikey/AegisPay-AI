/**
 * Voice Duress and Coercion Intelligence API client (P2-A6).
 *
 * Provides typed requests and responses for analyzing simulated call transcripts
 * and retrieving persisted coercion analysis records.
 */

import { config } from '../config';
import { apiFetch } from './authApi';

export type CoercionLevel = 'NONE' | 'SUSPECTED' | 'CONFIRMED_COERCION' | 'UNKNOWN';

export type CoercionCategory =
  | 'AUTHORITY_IMPERSONATION'
  | 'LEGAL_OR_CONSEQUENCE_THREAT'
  | 'URGENT_TRANSFER_DEMAND'
  | 'SECRECY_DEMAND'
  | 'BYPASS_SAFEGUARDS_INSTRUCTION'
  | 'REMOTE_ACCESS_PRESSURE'
  | 'INVESTMENT_GUARANTEE'
  | 'LEGITIMATE_EXPLANATION';

export type CoercionSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

export interface VoiceStressInput {
  detected?: boolean | null;
  level?: string;
  acoustic_indicators?: string[];
  speech_rate_wpm?: number | null;
}

export interface VoiceStressResponse {
  detected?: boolean | null;
  level: string;
  acoustic_indicators: string[];
  speech_rate_wpm?: number | null;
  provenance: string;
  is_simulated: boolean;
  disclaimer: string;
}

export interface CoercionFindingResponse {
  id: string;
  category: CoercionCategory;
  severity: CoercionSeverity;
  is_explicit: boolean;
  explanation: string;
  supporting_excerpt: string;
  start_offset?: number | null;
  end_offset?: number | null;
  provenance: string;
}

export interface CoercionModelMetadataResponse {
  provider: string;
  model_id: string;
  latency_ms: number;
  correlation_id?: string | null;
}

export interface CoercionAnalysisResponse {
  id: string;
  transaction_id: string;
  overall_coercion_level: CoercionLevel;
  confidence: string;
  confidence_score: number;
  findings: CoercionFindingResponse[];
  voice_stress_signals?: VoiceStressResponse | null;
  legitimate_explanations: string[];
  uncertainty_notes: string[];
  missing_information: string[];
  summary: string;
  model_metadata: CoercionModelMetadataResponse;
  status: string;
  transcript_snippet: string;
  created_at: string;
}

export interface AnalyzeCoercionRequest {
  call_transcript: string;
  voice_stress?: VoiceStressInput;
  correlation_id?: string;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data?.error?.message ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

/** Submit a simulated call transcript and optional voice stress signals for coercion analysis. */
export async function analyzeCoercionApi(
  transactionId: string,
  request: AnalyzeCoercionRequest
): Promise<CoercionAnalysisResponse> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/coercion/analyze`;
  const response = await apiFetch(url, {
    method: 'POST',
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as CoercionAnalysisResponse;
}

/** Retrieve the latest coercion analysis for a transaction (returns null if none exists). */
export async function getLatestCoercionApi(
  transactionId: string
): Promise<CoercionAnalysisResponse | null> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/coercion`;
  const response = await apiFetch(url);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as CoercionAnalysisResponse;
}

