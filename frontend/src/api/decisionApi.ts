/**
 * Automated decision workflow API client (P2-A4).
 *
 * Wraps the authenticated apiFetch client. The workflow is idempotent on the
 * backend: re-running evaluation returns the existing decision rather than
 * duplicating state transitions.
 */

import { config } from '../config';
import { apiFetch } from './authApi';

export type PolicyAction = 'ALLOW' | 'REQUIRE_VERIFICATION' | 'HOLD_FOR_INVESTIGATION' | 'BLOCK';

export interface DecisionResponse {
  id: string;
  transaction_id: string;
  transaction_state: string;
  policy_version: string;
  action: PolicyAction;
  risk_score: number;
  risk_level: string;
  requires_verification: boolean;
  provider_failed: boolean;
  investigation_performed: boolean;
  from_state: string;
  to_state: string;
  workflow_status: string;
  reason_codes: string[];
  triggered_rule_ids: string[];
  investigation_finding_refs: string[];
  supporting_evidence_refs: string[];
  missing_information: string[];
  explanation: string;
  simulated: boolean;
  created_at: string;
}

export interface EvaluateTransactionRequest {
  run_investigation?: boolean | null;
  correlation_id?: string;
}

/** Run the automated decision workflow for a transaction (idempotent server-side). */
export async function evaluateTransactionApi(
  transactionId: string,
  request: EvaluateTransactionRequest = {}
): Promise<DecisionResponse> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/evaluate`;
  const response = await apiFetch(url, {
    method: 'POST',
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Automated evaluation failed (${response.status}): ${text}`);
  }
  return (await response.json()) as DecisionResponse;
}

/** Fetch the latest automated decision for a transaction, or null if none exists. */
export async function getLatestDecisionApi(
  transactionId: string
): Promise<DecisionResponse | null> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/decision`;
  const response = await apiFetch(url);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Failed to fetch decision (${response.status}): ${text}`);
  }
  return (await response.json()) as DecisionResponse;
}
