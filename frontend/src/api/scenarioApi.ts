/**
 * End-to-end fraud simulation & explainability dashboard API client (P2-A8).
 *
 * Typed fetchers for the scenario catalogue, run execution, explainability
 * timeline, and expected-versus-actual evaluation. All outcomes are simulated.
 */

import { config } from '../config';
import { apiFetch } from './authApi';

export type ExecutionMode = 'DETERMINISTIC' | 'LIVE_PROVIDER';

export type StageStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'SKIPPED'
  | 'FAILED'
  | 'UNAVAILABLE';

export interface ScenarioTransactionSummary {
  amount: string;
  currency: string;
  payment_rail: string;
  recipient_name: string;
  recipient_identifier: string;
  purpose: string;
}

export interface ScenarioExpectationSummary {
  policy_action: string;
  final_state: string;
  response_type: string;
  customer_action_required: string;
  verification_outcome?: string | null;
  limitations: string[];
}

export interface ScenarioSummary {
  id: string;
  version: string;
  title: string;
  description: string;
  transaction: ScenarioTransactionSummary;
  expectation: ScenarioExpectationSummary;
  exercises_coercion_analysis: boolean;
  exercises_verification: boolean;
}

export interface ScenarioListResponse {
  catalog_version: string;
  total: number;
  items: ScenarioSummary[];
}

export interface StageView {
  key: string;
  title: string;
  status: StageStatus;
  detail: string;
  entity_type?: string | null;
  entity_id?: string | null;
  reason_codes: string[];
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  error_category?: string | null;
  sequence: number;
}

export interface ScenarioRunResponse {
  id: string;
  scenario_id: string;
  scenario_version: string;
  catalog_version: string;
  execution_mode: string;
  status: string;
  workflow_execution_success: boolean;
  ai_provider?: string | null;
  transaction_id?: string | null;
  final_state?: string | null;
  error_category?: string | null;
  detail?: string | null;
  stages: StageView[];
  created_at: string;
  updated_at: string;
  is_simulated: boolean;
}

export interface EvaluationDimension {
  name: string;
  category: 'MATCH' | 'MISMATCH' | 'INCOMPLETE';
  expected?: string | null;
  observed?: string | null;
  detail: string;
}

export interface ScenarioEvaluationResponse {
  run_id: string;
  scenario_id: string;
  scenario_version: string;
  workflow_execution_success: boolean;
  overall: 'MATCH' | 'MISMATCH' | 'INCOMPLETE';
  dimensions: EvaluationDimension[];
  incomplete_stages: string[];
  missing_evidence: string[];
  disclaimer: string;
  is_simulated: boolean;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data?.error?.message ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

/** Fetch the versioned scenario catalogue with declared expectations. */
export async function listScenariosApi(): Promise<ScenarioListResponse> {
  const response = await apiFetch(`${config.apiBaseUrl}/api/v1/scenarios`);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

/** Start a scenario run through the real fraud-prevention workflow. */
export async function startScenarioRunApi(
  scenarioId: string,
  executionMode: ExecutionMode,
  idempotencyKey?: string
): Promise<ScenarioRunResponse> {
  const body: Record<string, unknown> = { execution_mode: executionMode };
  if (idempotencyKey) {
    body.idempotency_key = idempotencyKey;
  }
  const response = await apiFetch(`${config.apiBaseUrl}/api/v1/scenarios/${scenarioId}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

/** Retrieve a run and its explainability timeline. */
export async function getScenarioRunApi(runId: string): Promise<ScenarioRunResponse> {
  const response = await apiFetch(`${config.apiBaseUrl}/api/v1/scenarios/runs/${runId}`);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

/** Retrieve the expected-versus-actual evaluation for a run. */
export async function getScenarioEvaluationApi(
  runId: string
): Promise<ScenarioEvaluationResponse> {
  const response = await apiFetch(
    `${config.apiBaseUrl}/api/v1/scenarios/runs/${runId}/evaluation`
  );
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

/** Retry a failed scenario run (idempotent; no duplicate transactions/responses). */
export async function retryScenarioRunApi(runId: string): Promise<ScenarioRunResponse> {
  const response = await apiFetch(
    `${config.apiBaseUrl}/api/v1/scenarios/runs/${runId}/retry`,
    { method: 'POST' }
  );
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}
