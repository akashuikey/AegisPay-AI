/**
 * Risk Engine API client for AegisPay AI.
 * Handles deterministic risk assessment, scenario loading, and transaction lifecycle integration.
 */

import { config } from '../config';
import { apiFetch } from './authApi';
import type {
  RiskLevel,
  RecommendedAction,
  TriggeredRuleResponse,
  RiskAssessmentResponse,
  TransactionEvidenceInput,
  DemoScenarioDefinition,
} from '../domain/riskScoring';
import {
  SCENARIO_CATALOG,
  evaluateRiskLocally,
} from '../domain/riskScoring';

export type {
  RiskLevel,
  RecommendedAction,
  TriggeredRuleResponse,
  RiskAssessmentResponse,
  TransactionEvidenceInput,
  DemoScenarioDefinition,
};

export { SCENARIO_CATALOG, evaluateRiskLocally };

/**
 * Call backend to evaluate risk deterministically.
 * Falls back to local deterministic engine if server is unreachable.
 */
export async function evaluateRiskApi(evidence: TransactionEvidenceInput): Promise<RiskAssessmentResponse> {
  const url = `${config.apiBaseUrl}/api/v1/risk/evaluate`;
  try {
    const response = await apiFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(evidence),
    });

    if (response.ok) {
      const data = (await response.json()) as RiskAssessmentResponse;
      return { ...data, source: 'backend' };
    }
    console.warn(`Backend risk API returned ${response.status}. Using local deterministic evaluation fallback.`);
    const fallback = evaluateRiskLocally(evidence);
    return { ...fallback, source: 'demo_fallback' };
  } catch (err) {
    console.warn('Backend risk API unreachable. Using local deterministic evaluation fallback.', err);
    const fallback = evaluateRiskLocally(evidence);
    return { ...fallback, source: 'demo_fallback' };
  }
}

/**
 * Fetch demo scenarios from backend or local fallback catalog.
 */
export async function fetchScenariosApi(): Promise<DemoScenarioDefinition[]> {
  const url = `${config.apiBaseUrl}/api/v1/risk/scenarios`;
  try {
    const response = await apiFetch(url);
    if (response.ok) {
      const data = await response.json();
      if (Array.isArray(data) && data.length > 0) {
        return data.map((raw: unknown) => {
          const item = raw as Record<string, unknown>;
          const key = String(item.id || item.key || '');
          const fallback = SCENARIO_CATALOG[key];
          const evidence = (item.evidence || fallback?.evidence || {}) as Record<string, unknown>;
          return {
            id: key,
            label: fallback?.label || String(item.title || key),
            category: fallback?.category || 'Fraud Scenario',
            recipient: String(evidence.recipient_name || fallback?.recipient || ''),
            recipientIdentifier: String(evidence.recipient_identifier || fallback?.recipientIdentifier || ''),
            amount: Number(evidence.amount || fallback?.amount || 0),
            purpose: String(evidence.purpose || fallback?.purpose || ''),
            reference: fallback?.reference || '',
            known: fallback?.known ?? false,
            summary: String(item.summary || fallback?.summary || ''),
            evidence: (fallback?.evidence || evidence) as TransactionEvidenceInput,
          };
        });
      }
    }
  } catch (err) {
    console.warn('Backend scenario endpoint unreachable. Using built-in scenario catalog.', err);
  }
  return Object.values(SCENARIO_CATALOG);
}
