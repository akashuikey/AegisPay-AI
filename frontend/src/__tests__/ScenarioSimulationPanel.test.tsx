import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import ScenarioSimulationPanel from '../components/ScenarioSimulationPanel';
import * as scenarioApi from '../api/scenarioApi';
import type {
  ScenarioEvaluationResponse,
  ScenarioListResponse,
  ScenarioRunResponse,
} from '../api/scenarioApi';

function makeCatalog(): ScenarioListResponse {
  return {
    catalog_version: 'p2a8.v1',
    total: 1,
    items: [
      {
        id: 'digital_arrest',
        version: '1.0.0',
        title: 'Digital Arrest / Authority Impersonation',
        description: 'A victim pressured by a fake law-enforcement caller.',
        transaction: {
          amount: '250000.00',
          currency: 'INR',
          payment_rail: 'RTGS',
          recipient_name: 'Govt Security Clearance Account',
          recipient_identifier: 'cbi.clearance@sbi',
          purpose: 'Urgent court identity bond',
        },
        expectation: {
          policy_action: 'HOLD_FOR_INVESTIGATION',
          final_state: 'HELD_FOR_VERIFICATION',
          response_type: 'HOLD_PROTECTIVE',
          customer_action_required: 'CONTACT_BANK',
          verification_outcome: null,
          limitations: ['Authority signals are simulated inputs.'],
        },
        exercises_coercion_analysis: true,
        exercises_verification: false,
      },
    ],
  };
}

function makeRun(overrides: Partial<ScenarioRunResponse> = {}): ScenarioRunResponse {
  return {
    id: 'run-1',
    scenario_id: 'digital_arrest',
    scenario_version: '1.0.0',
    catalog_version: 'p2a8.v1',
    execution_mode: 'DETERMINISTIC',
    status: 'COMPLETED',
    workflow_execution_success: true,
    ai_provider: 'mock_gemini',
    transaction_id: 'tx-1',
    final_state: 'HELD_FOR_VERIFICATION',
    error_category: null,
    detail: null,
    stages: [
      {
        key: 'transaction_created',
        title: 'Transaction created',
        status: 'COMPLETED',
        detail: 'Simulated payment created.',
        entity_type: 'transaction',
        entity_id: 'tx-1',
        reason_codes: [],
        started_at: null,
        completed_at: '2026-10-18T10:00:00Z',
        duration_ms: 5,
        error_category: null,
        sequence: 1,
      },
      {
        key: 'decision_policy',
        title: 'Decision policy evaluated',
        status: 'COMPLETED',
        detail: 'Policy selected action HOLD_FOR_INVESTIGATION.',
        entity_type: 'decision',
        entity_id: 'dec-1',
        reason_codes: ['EXPLICIT_COERCION_HOLD'],
        started_at: null,
        completed_at: '2026-10-18T10:00:00Z',
        duration_ms: 20,
        error_category: null,
        sequence: 5,
      },
    ],
    created_at: '2026-10-18T10:00:00Z',
    updated_at: '2026-10-18T10:00:00Z',
    is_simulated: true,
    ...overrides,
  };
}

function makeEvaluation(
  overrides: Partial<ScenarioEvaluationResponse> = {}
): ScenarioEvaluationResponse {
  return {
    run_id: 'run-1',
    scenario_id: 'digital_arrest',
    scenario_version: '1.0.0',
    workflow_execution_success: true,
    overall: 'MATCH',
    dimensions: [
      {
        name: 'policy_action',
        category: 'MATCH',
        expected: 'HOLD_FOR_INVESTIGATION',
        observed: 'HOLD_FOR_INVESTIGATION',
        detail: 'matched',
      },
    ],
    incomplete_stages: [],
    missing_evidence: [],
    disclaimer: 'Not a measure of real-world fraud-detection accuracy. All outcomes are simulated.',
    is_simulated: true,
    ...overrides,
  };
}

describe('ScenarioSimulationPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('loads and renders the scenario catalogue', async () => {
    vi.spyOn(scenarioApi, 'listScenariosApi').mockResolvedValue(makeCatalog());
    render(<ScenarioSimulationPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('scenario-digital_arrest')).toBeInTheDocument();
    });
    expect(screen.getByText('p2a8.v1')).toBeInTheDocument();
    expect(screen.getByTestId('run-empty')).toBeInTheDocument();
  });

  it('runs a scenario and renders the timeline and a MATCH evaluation', async () => {
    vi.spyOn(scenarioApi, 'listScenariosApi').mockResolvedValue(makeCatalog());
    vi.spyOn(scenarioApi, 'startScenarioRunApi').mockResolvedValue(makeRun());
    vi.spyOn(scenarioApi, 'getScenarioEvaluationApi').mockResolvedValue(makeEvaluation());

    render(<ScenarioSimulationPanel />);
    await waitFor(() => screen.getByTestId('run-digital_arrest'));
    fireEvent.click(screen.getByTestId('run-digital_arrest'));

    await waitFor(() => {
      expect(screen.getByTestId('run-summary')).toBeInTheDocument();
    });
    expect(screen.getByTestId('stage-transaction_created')).toBeInTheDocument();
    expect(screen.getByTestId('stage-decision_policy')).toBeInTheDocument();
    expect(screen.getByTestId('dim-policy_action')).toHaveTextContent('MATCH');
    // The simulated disclaimer is always shown.
    expect(screen.getByText(/All outcomes are simulated/i)).toBeInTheDocument();
  });

  it('shows a retry control for a failed run and retries it', async () => {
    vi.spyOn(scenarioApi, 'listScenariosApi').mockResolvedValue(makeCatalog());
    vi.spyOn(scenarioApi, 'startScenarioRunApi').mockResolvedValue(
      makeRun({ status: 'FAILED', workflow_execution_success: false, error_category: 'BOOM' })
    );
    vi.spyOn(scenarioApi, 'getScenarioEvaluationApi').mockResolvedValue(
      makeEvaluation({ overall: 'INCOMPLETE', workflow_execution_success: false })
    );
    const retrySpy = vi
      .spyOn(scenarioApi, 'retryScenarioRunApi')
      .mockResolvedValue(makeRun());

    render(<ScenarioSimulationPanel />);
    await waitFor(() => screen.getByTestId('run-digital_arrest'));
    fireEvent.click(screen.getByTestId('run-digital_arrest'));

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Retry'));
    await waitFor(() => {
      expect(retrySpy).toHaveBeenCalledWith('run-1');
    });
  });
});
