/**
 * In-Browser Deterministic Mock Backend for AegisPay AI.
 *
 * Implements the full suite of fraud prevention backend endpoints locally in the client:
 * - Health check telemetry (/health/ready, /health/live)
 * - Operator authentication (/api/v1/auth/*)
 * - Risk Engine evaluation (/api/v1/risk/*)
 * - End-to-end Scenario Simulation lifecycle & evaluation (/api/v1/scenarios/*)
 * - Transaction lifecycle & Decision workflow (/api/v1/transactions/*)
 * - Customer Verification Challenge & Dev OTP (/api/v1/verification/*)
 * - Voice Duress & Coercion Intelligence (/api/v1/transactions/* /coercion)
 * - Customer Dialogue & Call Session lifecycle (/api/v1/calls/*)
 * - Fraud Response Orchestration & Notifications (/api/v1/transactions/* /respond)
 * - AI Forensic Investigations & Conversation notes (/api/v1/investigations/*)
 */

import { SCENARIO_CATALOG, evaluateRiskLocally } from '../api/riskApi';
import { RECIPIENT_REGISTRY, resolveRecipient } from '../domain/recipientRegistry';

// ---------------------------------------------------------------------------
// Types & Interfaces
// ---------------------------------------------------------------------------

interface ScenarioRunRecord {
  id: string;
  scenario_id: string;
  scenario_version: string;
  catalog_version: string;
  execution_mode: string;
  status: string;
  workflow_execution_success: boolean;
  ai_provider: string | null;
  transaction_id: string;
  final_state: string;
  error_category: string | null;
  detail: string | null;
  stages: any[];
  created_at: string;
  updated_at: string;
  is_simulated: boolean;
}

interface EvaluationRecord {
  run_id: string;
  scenario_id: string;
  scenario_version: string;
  workflow_execution_success: boolean;
  overall: 'MATCH' | 'MISMATCH' | 'INCOMPLETE';
  dimensions: any[];
  incomplete_stages: string[];
  missing_evidence: string[];
  disclaimer: string;
  is_simulated: boolean;
}

interface StoredTransaction {
  id: string;
  amount: number;
  currency: string;
  payment_rail: string;
  recipient_name: string;
  recipient_identifier: string;
  purpose: string;
  customer_id: string;
  state: string;
  created_at: string;
  decision?: any;
  coercion?: any;
  challenge?: any;
  response?: any;
  callSession?: any;
}

// ---------------------------------------------------------------------------
// In-Memory Database
// ---------------------------------------------------------------------------

const runs = new Map<string, ScenarioRunRecord>();
const evaluations = new Map<string, EvaluationRecord>();
const transactions = new Map<string, StoredTransaction>();
const callSessions = new Map<string, any>();
const challenges = new Map<string, any>();
const investigations = new Map<string, any>();
const conversations = new Map<string, any>();

// ---------------------------------------------------------------------------
// Scenario Catalog Metadata & Expectations
// ---------------------------------------------------------------------------

export const SCENARIO_LIST = [
  {
    id: 'digital_arrest',
    version: '1.0.0',
    title: 'Digital Arrest / Authority Impersonation',
    description:
      'Victim pressured by fake law enforcement into liquidating FD and transferring ₹2,50,000 while on active phone call and screen share.',
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
      limitations: [
        'Authority impersonation and screen-sharing signals are simulated inputs, not live device telemetry.',
      ],
    },
    exercises_coercion_analysis: true,
    exercises_verification: false,
  },
  {
    id: 'investment_scam',
    version: '1.0.0',
    title: 'High-Yield Investment Scam',
    description:
      'A victim lured into a guaranteed-return crypto scheme is urged to transfer immediately and to dismiss any bank warnings.',
    transaction: {
      amount: '85000.00',
      currency: 'INR',
      payment_rail: 'IMPS',
      recipient_name: 'Apex Yield Asset Management',
      recipient_identifier: 'apexyield@icici',
      purpose: 'Crypto trading deposit',
    },
    expectation: {
      policy_action: 'HOLD_FOR_INVESTIGATION',
      final_state: 'HELD_FOR_VERIFICATION',
      response_type: 'HOLD_PROTECTIVE',
      customer_action_required: 'CONTACT_BANK',
      limitations: [
        'No independent verification of the investment platform is performed; the guaranteed-return claim is a simulated contextual signal.',
      ],
    },
    exercises_coercion_analysis: true,
    exercises_verification: false,
  },
  {
    id: 'fake_invoice',
    version: '1.0.0',
    title: 'Fake Invoice / Supplier Routing Mismatch',
    description:
      'A routine supplier payment where the invoice bank details contradict the trusted vendor ledger (possible business email compromise).',
    transaction: {
      amount: '32500.00',
      currency: 'INR',
      payment_rail: 'NEFT',
      recipient_name: 'Starling Supplies Private Ltd',
      recipient_identifier: '9928172635@kotak',
      purpose: 'Invoice 48210 payment',
    },
    expectation: {
      policy_action: 'REQUIRE_VERIFICATION',
      final_state: 'VERIFICATION_REQUIRED',
      response_type: 'VERIFICATION_REQUIRED',
      customer_action_required: 'VERIFY_OTP',
      limitations: [
        'Invoice authenticity is not independently established; the ledger mismatch is a simulated signal and the document is treated as UNVERIFIED.',
      ],
    },
    exercises_coercion_analysis: false,
    exercises_verification: true,
  },
  {
    id: 'mule_network',
    version: '1.0.0',
    title: 'Mule Account Velocity & Rapid Dispersal',
    description:
      'A beneficiary flagged in consortium intelligence with abnormal fan-in/fan-out velocity. An explicit, independently verified deterministic block condition.',
    transaction: {
      amount: '18000.00',
      currency: 'INR',
      payment_rail: 'UPI',
      recipient_name: 'Ramesh K Mule',
      recipient_identifier: 'fastcash99@upi',
      purpose: 'Friend return',
    },
    expectation: {
      policy_action: 'BLOCK',
      final_state: 'CANCELLED_SIMULATED',
      response_type: 'BLOCK_SAFETY',
      customer_action_required: 'CONTACT_BANK',
      limitations: [
        'The consortium mule-registry hit is a simulated intelligence signal; no real registry is queried.',
      ],
    },
    exercises_coercion_analysis: false,
    exercises_verification: false,
  },
  {
    id: 'legitimate_high_value',
    version: '1.0.0',
    title: 'Legitimate High-Value Lease Payment',
    description:
      'A routine high-value lease renewal to an established, trusted landlord with no coercive or anomaly indicators. Must not be treated as fraud.',
    transaction: {
      amount: '250000.00',
      currency: 'INR',
      payment_rail: 'RTGS',
      recipient_name: 'Maple Grove Properties',
      recipient_identifier: 'rent@maplegrove',
      purpose: 'Annual lease renewal',
    },
    expectation: {
      policy_action: 'ALLOW',
      final_state: 'SETTLED_SIMULATED',
      response_type: 'ALLOW_SETTLED',
      customer_action_required: 'NONE',
      limitations: [
        'Trusted-beneficiary status is a simulated signal; it never overrides strong coercion evidence.',
      ],
    },
    exercises_coercion_analysis: false,
    exercises_verification: false,
  },
  {
    id: 'ambiguous_payment',
    version: '1.0.0',
    title: 'Ambiguous Payment with Missing Telemetry',
    description:
      'A new payee with an active call but missing transcripts and unknown adverse history. Should require verification without auto-blocking.',
    transaction: {
      amount: '85000.00',
      currency: 'INR',
      payment_rail: 'UPI',
      recipient_name: 'Northstar Holdings',
      recipient_identifier: 'northstar@axis',
      purpose: 'Consulting deposit',
    },
    expectation: {
      policy_action: 'REQUIRE_VERIFICATION',
      final_state: 'VERIFICATION_REQUIRED',
      response_type: 'VERIFICATION_REQUIRED',
      customer_action_required: 'VERIFY_OTP',
      limitations: [
        'Several adverse signals are unknown; missing evidence is represented explicitly and never assumed safe or fraudulent.',
      ],
    },
    exercises_coercion_analysis: false,
    exercises_verification: true,
  },
  {
    id: 'ordinary_stressed_customer',
    version: '1.0.0',
    title: 'Ordinary Stressed Customer (No Coercion)',
    description:
      'A customer who sounds stressed on the phone call but provides a legitimate, unpressured explanation. Voice stress alone must not trigger protective hold.',
    transaction: {
      amount: '45000.00',
      currency: 'INR',
      payment_rail: 'IMPS',
      recipient_name: 'Apollo Healthcare Supplies',
      recipient_identifier: 'apollo.pharmacy@axis',
      purpose: 'Urgent medical supplies',
    },
    expectation: {
      policy_action: 'REQUIRE_VERIFICATION',
      final_state: 'VERIFICATION_REQUIRED',
      response_type: 'VERIFICATION_REQUIRED',
      customer_action_required: 'VERIFY_OTP',
      limitations: [
        'Acoustic voice stress is an advisory indicator only; it does not constitute standalone proof of coercion or fraud.',
      ],
    },
    exercises_coercion_analysis: true,
    exercises_verification: true,
  },
  {
    id: 'strong_coercion_after_verification',
    version: '1.0.0',
    title: 'Strong Coercion After Verification',
    description:
      'Customer passed OTP verification, but severe real-time duress cues and authority threats emerge during the security officer call. Safe hold maintained.',
    transaction: {
      amount: '180000.00',
      currency: 'INR',
      payment_rail: 'RTGS',
      recipient_name: 'Cyber Police Verification Escrow',
      recipient_identifier: 'cyber.police.escrow@pnb',
      purpose: 'Verification bond deposit',
    },
    expectation: {
      policy_action: 'HOLD_FOR_INVESTIGATION',
      final_state: 'HELD_FOR_VERIFICATION',
      response_type: 'HOLD_PROTECTIVE',
      customer_action_required: 'CONTACT_BANK',
      limitations: [
        'Passing 2FA does not release funds when active duress and extortion markers are independently established.',
      ],
    },
    exercises_coercion_analysis: true,
    exercises_verification: true,
  },
];

// ---------------------------------------------------------------------------
// Run Execution & Evaluation Generator
// ---------------------------------------------------------------------------

function buildScenarioRun(scenarioId: string, executionMode: string): { run: ScenarioRunRecord; evalResult: EvaluationRecord } {
  const scenarioDef = SCENARIO_LIST.find((s) => s.id === scenarioId) || SCENARIO_LIST[0];
  const runId = `run_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
  const txId = `tx_sim_${Date.now()}`;
  const now = new Date().toISOString();

  const expectation = scenarioDef.expectation;
  const isCoercion = scenarioDef.exercises_coercion_analysis;
  const isVerification = scenarioDef.exercises_verification;

  const stages = [
    {
      key: 'transaction_created',
      title: 'Transaction created',
      status: 'COMPLETED',
      detail: `Created simulated payment of ₹${Number(scenarioDef.transaction.amount).toLocaleString('en-IN')} to ${scenarioDef.transaction.recipient_name}.`,
      entity_type: 'transaction',
      entity_id: txId,
      reason_codes: [],
      started_at: now,
      completed_at: now,
      duration_ms: 12,
      sequence: 1,
    },
    {
      key: 'risk_assessment',
      title: 'Deterministic risk assessment',
      status: 'COMPLETED',
      detail: `Evaluated deterministic policy rules: action ${expectation.policy_action}.`,
      entity_type: 'assessment',
      entity_id: `asm_${Date.now()}`,
      reason_codes: [expectation.policy_action],
      started_at: now,
      completed_at: now,
      duration_ms: 24,
      sequence: 2,
    },
    {
      key: 'ai_investigation',
      title: 'AI investigation',
      status: scenarioId === 'legitimate_high_value' ? 'SKIPPED' : 'COMPLETED',
      detail:
        scenarioId === 'legitimate_high_value'
          ? 'Risk tier below threshold; AI forensic investigation skipped.'
          : 'Gemini forensic reasoning synthesized multi-source evidence and intent indicators.',
      entity_type: 'investigation',
      entity_id: `inv_${Date.now()}`,
      reason_codes: [],
      started_at: now,
      completed_at: now,
      duration_ms: 45,
      sequence: 3,
    },
    {
      key: 'coercion_analysis',
      title: 'Coercion analysis',
      status: isCoercion ? 'COMPLETED' : 'SKIPPED',
      detail: isCoercion
        ? 'Voice stress telemetry & transcript analyzed. Confirmed high-pressure duress cues.'
        : 'No adverse voice coercion signals present or required for scenario.',
      entity_type: 'coercion_analysis',
      entity_id: `ca_${Date.now()}`,
      reason_codes: isCoercion ? ['COERCION_DETECTED', 'AUTHORITY_PRESSURE'] : [],
      started_at: now,
      completed_at: now,
      duration_ms: 38,
      sequence: 4,
    },
    {
      key: 'decision_policy',
      title: 'Decision policy evaluated',
      status: 'COMPLETED',
      detail: `Authoritative decision policy resolved to ${expectation.policy_action} -> ${expectation.final_state}.`,
      entity_type: 'decision',
      entity_id: `dec_${Date.now()}`,
      reason_codes: [expectation.policy_action],
      started_at: now,
      completed_at: now,
      duration_ms: 18,
      sequence: 5,
    },
    {
      key: 'verification',
      title: 'Customer verification',
      status: isVerification ? 'COMPLETED' : 'SKIPPED',
      detail: isVerification
        ? 'Customer OTP verification challenge initiated and evaluated.'
        : 'Outbound verification challenge not triggered for current decision tier.',
      entity_type: 'challenge',
      entity_id: isVerification ? `ch_${Date.now()}` : null,
      reason_codes: [],
      started_at: now,
      completed_at: now,
      duration_ms: 15,
      sequence: 6,
    },
    {
      key: 'response_orchestration',
      title: 'Response orchestrated',
      status: 'COMPLETED',
      detail: `Orchestrated ${expectation.response_type} with intervention action ${expectation.customer_action_required}.`,
      entity_type: 'fraud_response',
      entity_id: `resp_${Date.now()}`,
      reason_codes: [expectation.response_type],
      started_at: now,
      completed_at: now,
      duration_ms: 22,
      sequence: 7,
    },
    {
      key: 'notification',
      title: 'Customer notification',
      status: 'COMPLETED',
      detail: `Simulated customer intervention delivered via SMS/In-App to payer.`,
      entity_type: 'notification',
      entity_id: `notif_${Date.now()}`,
      reason_codes: ['DELIVERED_SIMULATED'],
      started_at: now,
      completed_at: now,
      duration_ms: 14,
      sequence: 8,
    },
  ];

  const run: ScenarioRunRecord = {
    id: runId,
    scenario_id: scenarioDef.id,
    scenario_version: scenarioDef.version,
    catalog_version: 'p2a8.v1',
    execution_mode: executionMode,
    status: 'COMPLETED',
    workflow_execution_success: true,
    ai_provider: executionMode === 'LIVE_PROVIDER' ? 'google-gemini' : 'mock-deterministic',
    transaction_id: txId,
    final_state: expectation.final_state,
    error_category: null,
    detail: 'Workflow completed successfully with all policy stages executed.',
    stages,
    created_at: now,
    updated_at: now,
    is_simulated: true,
  };

  const dimensions = [
    {
      name: 'policy_action',
      category: 'MATCH',
      expected: expectation.policy_action,
      observed: expectation.policy_action,
      detail: 'The authoritative policy action matched the expectation.',
    },
    {
      name: 'final_simulated_state',
      category: 'MATCH',
      expected: expectation.final_state,
      observed: expectation.final_state,
      detail: 'The final simulated transaction state matched the expectation.',
    },
    {
      name: 'response_type',
      category: 'MATCH',
      expected: expectation.response_type,
      observed: expectation.response_type,
      detail: 'The orchestrated response type matched the expectation.',
    },
    {
      name: 'customer_intervention',
      category: 'MATCH',
      expected: expectation.customer_action_required,
      observed: expectation.customer_action_required,
      detail: 'The customer-facing intervention matched the expectation.',
    },
  ];

  const evalResult: EvaluationRecord = {
    run_id: runId,
    scenario_id: scenarioDef.id,
    scenario_version: scenarioDef.version,
    workflow_execution_success: true,
    overall: 'MATCH',
    dimensions,
    incomplete_stages: [],
    missing_evidence: [],
    disclaimer:
      'Scenario comparison reflects agreement with a small set of hand-authored expectations only. All outcomes are simulated.',
    is_simulated: true,
  };

  runs.set(runId, run);
  evaluations.set(runId, evalResult);

  // Also seed a transaction into store
  transactions.set(txId, {
    id: txId,
    amount: Number(scenarioDef.transaction.amount),
    currency: scenarioDef.transaction.currency,
    payment_rail: scenarioDef.transaction.payment_rail,
    recipient_name: scenarioDef.transaction.recipient_name,
    recipient_identifier: scenarioDef.transaction.recipient_identifier,
    purpose: scenarioDef.transaction.purpose,
    customer_id: 'cust_001',
    state: expectation.final_state,
    created_at: now,
  });

  return { run, evalResult };
}

// ---------------------------------------------------------------------------
// Mock Request Handler & Dispatcher
// ---------------------------------------------------------------------------

export async function handleMockApiRequest(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const rawUrl = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000';
  const url = new URL(rawUrl, origin);
  const pathname = url.pathname;
  const method = (init?.method || 'GET').toUpperCase();

  // Check if this is an API call intended for the backend
  const isBackendCall =
    pathname.startsWith('/api/v1/') ||
    pathname.startsWith('/health/') ||
    pathname.startsWith('/api/') ||
    rawUrl.includes(':8000/api/v1/') ||
    rawUrl.includes(':8000/health/');

  if (!isBackendCall && typeof window !== 'undefined' && typeof window.fetch === 'function') {
    return window.fetch(input, init);
  }

  try {
    let bodyData: any = {};
    if (init?.body) {
      try {
        bodyData = typeof init.body === 'string' ? JSON.parse(init.body) : {};
      } catch {
        // ignore non-json
      }
    }

    const jsonResponse = (data: any, status = 200): Response => {
      return new Response(JSON.stringify(data), {
        status,
        headers: { 'Content-Type': 'application/json' },
      });
    };

    // 1. Health checks
    if (pathname === '/health/ready' || pathname === '/health/live') {
      return jsonResponse({
        status: 'ready',
        database: 'connected',
        timestamp: new Date().toISOString(),
        environment: 'browser-simulated',
      });
    }

    // 2. Auth: login & me
    if (pathname === '/api/v1/auth/login' && method === 'POST') {
      const username = bodyData.username || 'operator';
      return jsonResponse({
        access_token: `mock_jwt_token_${Date.now()}`,
        token_type: 'bearer',
        expires_in: 86400,
        operator: {
          id: 'op_01',
          username,
        },
      });
    }

    if (pathname === '/api/v1/auth/me') {
      return jsonResponse({
        id: 'op_01',
        username: 'operator',
      });
    }

    // 3. Recipient Intelligence Registry (20 seeded accounts)
    if (pathname === '/api/v1/recipients' && method === 'GET') {
      return jsonResponse({
        total: RECIPIENT_REGISTRY.length,
        items: RECIPIENT_REGISTRY,
      });
    }

    if (pathname === '/api/v1/recipients/resolve') {
      const upi = url.searchParams.get('upi') || bodyData.upi_id || '';
      return jsonResponse(resolveRecipient(upi));
    }

    // 4. Risk Engine (Wired with Recipient Intelligence)
    if (pathname === '/api/v1/risk/evaluate' && method === 'POST') {
      const evidence = { ...bodyData };
      if (evidence.recipient_identifier) {
        const resolved = resolveRecipient(evidence.recipient_identifier);
        if (evidence.is_trusted_beneficiary === undefined) {
          evidence.is_trusted_beneficiary = resolved.is_trusted_beneficiary;
        }
        if (evidence.is_first_time_recipient === undefined) {
          evidence.is_first_time_recipient = !resolved.is_trusted_beneficiary;
        }
        if (evidence.is_flagged_mule === undefined) {
          evidence.is_flagged_mule = resolved.is_flagged_mule;
        }
        if (evidence.fan_in_count_24h === undefined) {
          evidence.fan_in_count_24h = resolved.fan_in_count_24h;
        }
        if (evidence.fan_out_count_24h === undefined) {
          evidence.fan_out_count_24h = resolved.fan_out_count_24h;
        }
        if (evidence.payee_name_mismatch === undefined) {
          evidence.payee_name_mismatch = resolved.payee_name_mismatch;
        }
        if (evidence.routing_mismatch === undefined) {
          evidence.routing_mismatch = resolved.routing_mismatch;
        }
      }
      const assessment = evaluateRiskLocally(evidence);
      return jsonResponse(assessment);
    }

    if (pathname === '/api/v1/risk/scenarios') {
      return jsonResponse(Object.values(SCENARIO_CATALOG));
    }

    // 4. Scenario Lab Catalogue & Runs
    if (pathname === '/api/v1/scenarios' && method === 'GET') {
      return jsonResponse({
        catalog_version: 'p2a8.v1',
        total: SCENARIO_LIST.length,
        items: SCENARIO_LIST,
      });
    }

    // Scenario Run start
    const scenarioRunMatch = pathname.match(/^\/api\/v1\/scenarios\/([^/]+)\/runs$/);
    if (scenarioRunMatch && method === 'POST') {
      const scenarioId = scenarioRunMatch[1];
      const mode = bodyData.execution_mode || 'DETERMINISTIC';
      const { run } = buildScenarioRun(scenarioId, mode);
      return jsonResponse(run);
    }

    // Scenario Run details
    const runGetMatch = pathname.match(/^\/api\/v1\/scenarios\/runs\/([^/]+)$/);
    if (runGetMatch && method === 'GET') {
      const runId = runGetMatch[1];
      const run = runs.get(runId);
      if (run) return jsonResponse(run);
      // Auto-generate if not found
      const { run: newRun } = buildScenarioRun('digital_arrest', 'DETERMINISTIC');
      return jsonResponse(newRun);
    }

    // Scenario Run evaluation
    const runEvalMatch = pathname.match(/^\/api\/v1\/scenarios\/runs\/([^/]+)\/evaluation$/);
    if (runEvalMatch && method === 'GET') {
      const runId = runEvalMatch[1];
      const ev = evaluations.get(runId);
      if (ev) return jsonResponse(ev);
      const { evalResult } = buildScenarioRun('digital_arrest', 'DETERMINISTIC');
      return jsonResponse(evalResult);
    }

    // Scenario Run retry
    const runRetryMatch = pathname.match(/^\/api\/v1\/scenarios\/runs\/([^/]+)\/retry$/);
    if (runRetryMatch && method === 'POST') {
      const runId = runRetryMatch[1];
      const existing = runs.get(runId);
      const scenarioId = existing?.scenario_id || 'digital_arrest';
      const { run } = buildScenarioRun(scenarioId, 'DETERMINISTIC');
      return jsonResponse(run);
    }

    // 5. Verification Challenges
    const verifyCreateMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/verification$/);
    if (verifyCreateMatch && method === 'POST') {
      const txId = verifyCreateMatch[1];
      const challengeId = `ch_${Date.now()}`;
      const devOtp = '849201';
      const challenge = {
        challenge_id: challengeId,
        transaction_id: txId,
        status: 'PENDING',
        attempt_count: 0,
        max_attempts: 3,
        attempts_remaining: 3,
        expires_at: new Date(Date.now() + 600000).toISOString(),
        customer_session_token: `cust_sess_${Date.now()}`,
        session_expires_in: 600,
        simulated: true,
        dev_otp: devOtp,
      };
      challenges.set(challengeId, challenge);
      return jsonResponse(challenge);
    }

    const verifyStatusMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/verification\/([^/]+)$/);
    if (verifyStatusMatch && method === 'GET') {
      const challengeId = verifyStatusMatch[2];
      const ch = challenges.get(challengeId) || {
        challenge_id: challengeId,
        transaction_id: verifyStatusMatch[1],
        status: 'PENDING',
        attempt_count: 0,
        max_attempts: 3,
        attempts_remaining: 3,
        expires_at: new Date(Date.now() + 600000).toISOString(),
        transaction_state: 'VERIFICATION_REQUIRED',
      };
      return jsonResponse(ch);
    }

    const verifySubmitMatch = pathname.match(/^\/api\/v1\/verification\/([^/]+)\/submit$/);
    if (verifySubmitMatch && method === 'POST') {
      const challengeId = verifySubmitMatch[1];
      const submittedOtp = bodyData.otp;
      const ch = challenges.get(challengeId);
      const isCorrect = submittedOtp === (ch?.dev_otp || '849201') || submittedOtp === '123456';

      const result = isCorrect ? 'SUCCEEDED' : 'FAILED';
      const newStatus = isCorrect ? 'VERIFIED' : 'FAILED';
      const txState = isCorrect ? 'SETTLED_SIMULATED' : 'VERIFICATION_REQUIRED';

      if (ch) {
        ch.attempt_count += 1;
        ch.attempts_remaining = Math.max(0, ch.max_attempts - ch.attempt_count);
        ch.status = newStatus;
      }

      return jsonResponse({
        challenge_id: challengeId,
        transaction_id: ch?.transaction_id || `tx_${Date.now()}`,
        result,
        status: newStatus,
        attempts_remaining: ch?.attempts_remaining ?? 2,
        transaction_state: txState,
        decision: isCorrect
          ? {
              id: `dec_verified_${Date.now()}`,
              transaction_id: ch?.transaction_id || 'tx_01',
              transaction_state: 'SETTLED_SIMULATED',
              policy_version: 'p2a4.v1',
              action: 'ALLOW',
              risk_score: 15,
              risk_level: 'LOW',
              requires_verification: false,
              provider_failed: false,
              investigation_performed: true,
              from_state: 'VERIFICATION_REQUIRED',
              to_state: 'SETTLED_SIMULATED',
              workflow_status: 'COMPLETED',
              reason_codes: ['OTP_VERIFICATION_SUCCEEDED'],
              triggered_rule_ids: [],
              investigation_finding_refs: [],
              supporting_evidence_refs: ['OTP verified by customer'],
              missing_information: [],
              explanation: 'Customer successfully proved identity via 2FA challenge. Simulated settlement released.',
              simulated: true,
              created_at: new Date().toISOString(),
            }
          : null,
        simulated: true,
      });
    }

    // 6. Automated Decision Policy
    const evalTxMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/evaluate$/);
    if (evalTxMatch && method === 'POST') {
      const txId = evalTxMatch[1];
      const decision = {
        id: `dec_${Date.now()}`,
        transaction_id: txId,
        transaction_state: 'HELD_FOR_VERIFICATION',
        policy_version: 'p2a4.v1',
        action: 'HOLD_FOR_INVESTIGATION',
        risk_score: 85,
        risk_level: 'CRITICAL',
        requires_verification: true,
        provider_failed: false,
        investigation_performed: true,
        from_state: 'PENDING_REVIEW',
        to_state: 'HELD_FOR_VERIFICATION',
        workflow_status: 'COMPLETED',
        reason_codes: ['RULE_COERCION_AUTHORITY_PRESSURE', 'RULE_CALL_AND_SCREEN_SHARE'],
        triggered_rule_ids: ['RULE_COERCION_AUTHORITY_PRESSURE', 'RULE_CALL_AND_SCREEN_SHARE'],
        investigation_finding_refs: ['find_01'],
        supporting_evidence_refs: ['Coercive language detected', 'Screen sharing active during phone call'],
        missing_information: [],
        explanation: 'Critical duress & coercion detected. Transaction held for customer protection.',
        simulated: true,
        created_at: new Date().toISOString(),
      };
      return jsonResponse(decision);
    }

    const getDecisionMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/decision$/);
    if (getDecisionMatch && method === 'GET') {
      const txId = getDecisionMatch[1];
      return jsonResponse({
        id: `dec_${Date.now()}`,
        transaction_id: txId,
        transaction_state: 'HELD_FOR_VERIFICATION',
        policy_version: 'p2a4.v1',
        action: 'HOLD_FOR_INVESTIGATION',
        risk_score: 85,
        risk_level: 'CRITICAL',
        requires_verification: true,
        provider_failed: false,
        investigation_performed: true,
        from_state: 'PENDING_REVIEW',
        to_state: 'HELD_FOR_VERIFICATION',
        workflow_status: 'COMPLETED',
        reason_codes: ['RULE_COERCION_AUTHORITY_PRESSURE'],
        triggered_rule_ids: ['RULE_COERCION_AUTHORITY_PRESSURE'],
        investigation_finding_refs: [],
        supporting_evidence_refs: [],
        missing_information: [],
        explanation: 'Simulated protective hold active pending investigation.',
        simulated: true,
        created_at: new Date().toISOString(),
      });
    }

    // 7. Coercion Intelligence
    const coercionAnalyzeMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/coercion\/analyze$/);
    if (coercionAnalyzeMatch && method === 'POST') {
      const txId = coercionAnalyzeMatch[1];
      const transcript = bodyData.call_transcript || '';
      const isCoerced = /cbi|arrest|police|warrant|urgent|clearance|jail/i.test(transcript);

      const analysis = {
        id: `ca_${Date.now()}`,
        transaction_id: txId,
        overall_coercion_level: isCoerced ? 'CONFIRMED_COERCION' : 'NONE',
        confidence: 'HIGH',
        confidence_score: isCoerced ? 0.94 : 0.88,
        findings: isCoerced
          ? [
              {
                id: `find_${Date.now()}_1`,
                category: 'AUTHORITY_IMPERSONATION',
                severity: 'CRITICAL',
                is_explicit: true,
                explanation: 'Speaker claims to be law enforcement officer issuing threats of arrest.',
                supporting_excerpt: 'This is Inspector Sharma from the CBI cyber crime division. There is a non-bailable warrant.',
                provenance: 'gemini_forensic_agent',
              },
              {
                id: `find_${Date.now()}_2`,
                category: 'SECRECY_DEMAND',
                severity: 'HIGH',
                is_explicit: true,
                explanation: 'Explicit instruction to remain isolated and not consult family or bank officials.',
                supporting_excerpt: 'Do not disconnect this call and do not tell anyone.',
                provenance: 'gemini_forensic_agent',
              },
            ]
          : [],
        voice_stress_signals: {
          detected: isCoerced,
          level: isCoerced ? 'HIGH' : 'LOW',
          acoustic_indicators: isCoerced ? ['elevated_pitch', 'micro_tremor'] : [],
          speech_rate_wpm: isCoerced ? 165 : 120,
          provenance: 'acoustic_telemetry_simulated',
          is_simulated: true,
          disclaimer: 'Acoustic voice stress is simulated telemetry for training and demonstration.',
        },
        legitimate_explanations: isCoerced ? [] : ['Customer articulates genuine transaction intent without duress.'],
        uncertainty_notes: [],
        missing_information: [],
        summary: isCoerced
          ? 'Digital arrest authority coercion confirmed. Victim subjected to active non-bailable warrant threat.'
          : 'No coercive markers or duress detected in customer interaction.',
        model_metadata: {
          provider: 'google-gemini',
          model_id: 'gemini-1.5-flash',
          latency_ms: 120,
        },
        status: 'COMPLETED',
        transcript_snippet: transcript.substring(0, 150),
        created_at: new Date().toISOString(),
      };
      return jsonResponse(analysis);
    }

    const coercionGetMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/coercion$/);
    if (coercionGetMatch && method === 'GET') {
      const txId = coercionGetMatch[1];
      return jsonResponse({
        status: 'completed',
        detail: 'Coercion analysis completed with high confidence.',
        analysis: {
          id: `ca_${Date.now()}`,
          transaction_id: txId,
          overall_coercion_level: 'CONFIRMED_COERCION',
          confidence: 'HIGH',
          confidence_score: 0.94,
          findings: [
            {
              id: `f_1`,
              category: 'AUTHORITY_IMPERSONATION',
              severity: 'CRITICAL',
              is_explicit: true,
              explanation: 'Caller impersonates law enforcement authority with imminent arrest threat.',
              supporting_excerpt: 'Under digital arrest and must transfer to secure clearance account immediately.',
              provenance: 'simulated_transcript',
            },
          ],
          voice_stress_signals: {
            detected: true,
            level: 'HIGH',
            acoustic_indicators: ['tremor', 'pitch_anomaly'],
            provenance: 'telephony',
            is_simulated: true,
            disclaimer: 'Simulated voice telemetry',
          },
          legitimate_explanations: [],
          uncertainty_notes: [],
          missing_information: [],
          summary: 'Authority coercion pattern identified with active call and liquidation pressure.',
          model_metadata: { provider: 'google-gemini', model_id: 'gemini-1.5-flash', latency_ms: 80 },
          status: 'completed',
          transcript_snippet: 'CBI clearance order...',
          created_at: new Date().toISOString(),
        },
      });
    }

    // 8. Customer Calls & Dialogue
    const callCreateMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/calls$/);
    if (callCreateMatch && method === 'POST') {
      const txId = callCreateMatch[1];
      const callId = `call_${Date.now()}`;
      const session = {
        id: callId,
        transaction_id: txId,
        conversation_id: `conv_${Date.now()}`,
        channel: bodyData.channel || 'VOICE_SIMULATED',
        status: 'RINGING',
        direction: 'OUTBOUND_SIMULATED',
        attempt_number: 1,
        customer_phone_masked: '+91 ••••• ••482',
        coercion_analysis_id: null,
        started_at: new Date().toISOString(),
        connected_at: null,
        ended_at: null,
        duration_seconds: null,
        failure_reason: null,
        turns: [
          {
            turn_index: 0,
            role: 'assistant',
            content: 'Hello, this is AegisPay Fraud Prevention calling regarding your recent payment request. Can you hear me clearly?',
            evidence_references: [],
            internal_observations: ['Call initiated by automated risk policy'],
            uncertainty_notes: [],
            suggested_action: 'ESTABLISH_RAPPORT',
            is_terminal_turn: false,
            coercion_cues: [],
            created_at: new Date().toISOString(),
          },
        ],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      callSessions.set(callId, session);
      return jsonResponse(session);
    }

    const callConnectMatch = pathname.match(/^\/api\/v1\/calls\/([^/]+)\/connect$/);
    if (callConnectMatch && method === 'POST') {
      const callId = callConnectMatch[1];
      const session = callSessions.get(callId) || {
        id: callId,
        status: 'RINGING',
        turns: [],
      };
      session.status = 'CONNECTED';
      session.connected_at = new Date().toISOString();
      return jsonResponse(session);
    }

    const callTurnMatch = pathname.match(/^\/api\/v1\/calls\/([^/]+)\/turns$/);
    if (callTurnMatch && method === 'POST') {
      const callId = callTurnMatch[1];
      const customerMsg = bodyData.customer_message || '';
      const session = callSessions.get(callId) || {
        id: callId,
        status: 'CONNECTED',
        turns: [],
      };

      const turnIndex = session.turns?.length || 0;
      session.turns = session.turns || [];

      // Append customer turn
      session.turns.push({
        turn_index: turnIndex,
        role: 'customer',
        content: customerMsg,
        evidence_references: [],
        internal_observations: ['Customer statement captured via interactive simulator'],
        uncertainty_notes: [],
        suggested_action: 'ANALYZE_RESPONSE',
        is_terminal_turn: false,
        coercion_cues: /arrest|police|cbi|urgent|threat/i.test(customerMsg) ? ['AUTHORITY_COERCION'] : [],
        created_at: new Date().toISOString(),
      });

      // Generate intelligent response turn
      let assistantReply =
        "Thank you for that information. I'd like to verify: did someone instruct you to make this transfer, or are you currently on another active call?";
      let isTerminal = false;

      if (/cbi|police|arrest|threat|court/i.test(customerMsg)) {
        assistantReply =
          'Please stay calm. Legitimate law enforcement agencies and courts NEVER conduct digital arrests or demand money transfers over the phone. We are placing a safe protective hold on this payment to secure your funds.';
        isTerminal = true;
      } else if (/rent|lease|landlord|routine|normal/i.test(customerMsg)) {
        assistantReply =
          'Thank you. We have recorded your confirmation regarding the lease renewal. The transfer details match your trusted history.';
        isTerminal = true;
      }

      session.turns.push({
        turn_index: turnIndex + 1,
        role: 'assistant',
        content: assistantReply,
        evidence_references: [],
        risk_sentiment: isTerminal ? 'BENIGN' : 'SUSPICIOUS',
        confidence_score: 0.92,
        internal_observations: ['Dynamic contextual assessment applied'],
        uncertainty_notes: [],
        suggested_action: isTerminal ? 'CLOSE_DIALOGUE' : 'CONTINUE_INQUIRY',
        is_terminal_turn: isTerminal,
        coercion_cues: [],
        created_at: new Date().toISOString(),
      });

      return jsonResponse(session);
    }

    const callCompleteMatch = pathname.match(/^\/api\/v1\/calls\/([^/]+)\/complete$/);
    if (callCompleteMatch && method === 'POST') {
      const callId = callCompleteMatch[1];
      const session = callSessions.get(callId) || { id: callId };
      session.status = 'COMPLETED';
      session.ended_at = new Date().toISOString();
      return jsonResponse(session);
    }

    const callDeclineMatch = pathname.match(/^\/api\/v1\/calls\/([^/]+)\/decline$/);
    if (callDeclineMatch && method === 'POST') {
      const callId = callDeclineMatch[1];
      const session = callSessions.get(callId) || { id: callId };
      session.status = 'DECLINED';
      session.ended_at = new Date().toISOString();
      return jsonResponse(session);
    }

    const callLatestMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/calls\/latest$/);
    if (callLatestMatch && method === 'GET') {
      const txId = callLatestMatch[1];
      for (const s of callSessions.values()) {
        if (s.transaction_id === txId) return jsonResponse(s);
      }
      return jsonResponse(null, 404);
    }

    // 9. Fraud Responses & Interventions
    const respondMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/respond$/);
    if (respondMatch && method === 'POST') {
      const txId = respondMatch[1];
      const responseData = {
        id: `resp_${Date.now()}`,
        transaction_id: txId,
        decision_id: `dec_${Date.now()}`,
        response_type: 'HOLD_PROTECTIVE',
        action: 'HOLD_FOR_INVESTIGATION',
        processing_status: 'COMPLETED',
        from_state: 'PENDING_REVIEW',
        to_state: 'HELD_FOR_VERIFICATION',
        headline: 'Protective Payment Pause Active',
        customer_message:
          'We noticed unusual activity associated with this transfer request. To keep your money safe, this payment is temporarily held. A bank fraud specialist will review it shortly.',
        customer_action_required: 'CONTACT_BANK',
        next_steps: [
          'Do not transfer money to secondary accounts',
          'Disconnect any unverified third-party phone calls',
          'Call bank support at 1800-AEGIS-SAFE if you are being pressured',
        ],
        created_at: new Date().toISOString(),
        notifications: [
          {
            id: `notif_${Date.now()}_1`,
            channel: 'SMS_SIMULATED',
            recipient_masked: '+91 ••••• ••482',
            subject: null,
            message_body: 'AegisPay Alert: Your payment is safely held for fraud protection. Please contact your branch.',
            delivery_status: 'DELIVERED_SIMULATED',
            created_at: new Date().toISOString(),
            delivered_at: new Date().toISOString(),
          },
          {
            id: `notif_${Date.now()}_2`,
            channel: 'IN_APP_SIMULATED',
            recipient_masked: 'cust_001',
            subject: 'Protective Hold Notification',
            message_body: 'A protective hold has been placed on your transaction.',
            delivery_status: 'DELIVERED_SIMULATED',
            created_at: new Date().toISOString(),
            delivered_at: new Date().toISOString(),
          },
        ],
        is_simulated: true,
      };
      return jsonResponse(responseData);
    }

    const latestRespMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/responses\/latest$/);
    if (latestRespMatch && method === 'GET') {
      const txId = latestRespMatch[1];
      return jsonResponse({
        id: `resp_${Date.now()}`,
        transaction_id: txId,
        response_type: 'HOLD_PROTECTIVE',
        action: 'HOLD_FOR_INVESTIGATION',
        processing_status: 'COMPLETED',
        from_state: 'PENDING_REVIEW',
        to_state: 'HELD_FOR_VERIFICATION',
        headline: 'Protective Hold Imposed',
        customer_message: 'Payment on protective hold.',
        customer_action_required: 'CONTACT_BANK',
        next_steps: ['Verify recipient identity'],
        created_at: new Date().toISOString(),
        notifications: [],
        is_simulated: true,
      });
    }

    const interventionMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/intervention$/);
    if (interventionMatch && method === 'GET') {
      const txId = interventionMatch[1];
      return jsonResponse({
        transaction_id: txId,
        response_type: 'HOLD_PROTECTIVE',
        headline: 'Your payment is safely protected',
        customer_message:
          'We have detected indicators of potential fraud or coercion. Your account has not been debited. Please contact bank support before proceeding.',
        customer_action_required: 'CONTACT_BANK',
        next_steps: ['Do not accept remote control requests', 'Visit your nearest branch if asked to move funds'],
        simulated_payment_status: 'HELD_FOR_VERIFICATION',
        notification_delivered: true,
        notification_channel: 'IN_APP_SIMULATED',
        is_simulated: true,
      });
    }

    // 10. AI Forensic Investigations
    if (pathname === '/api/v1/investigations' && method === 'POST') {
      const txId = bodyData.transaction_id || `tx_${Date.now()}`;
      const inv = {
        id: `inv_${Date.now()}`,
        transaction_id: txId,
        summary:
          'AI multi-source forensic synthesis identified authority coercion indicators consistent with a Digital Arrest scheme. Payer acted under active remote guidance.',
        overall_risk_sentiment: 'COERCED',
        confidence: 'HIGH',
        confidence_score: 0.95,
        findings: [
          {
            id: `f_${Date.now()}_1`,
            category: 'AUTHORITY_COERCION',
            explanation: 'Subject was coerced through falsified law-enforcement authority threats.',
            severity: 'CRITICAL',
            supporting_evidence_references: ['cbi_impersonation', 'court_bond_purpose'],
            source_provenance: 'customer_statement',
          },
          {
            id: `f_${Date.now()}_2`,
            category: 'SOCIAL_ENGINEERING',
            explanation: 'Urgency tactics employed to bypass standard banking safeguards.',
            severity: 'HIGH',
            supporting_evidence_references: ['call_telemetry'],
            source_provenance: 'device_telephony',
          },
        ],
        contradictory_or_mitigating_evidence: [],
        missing_information: [],
        unresolved_questions: [],
        suggested_next_steps: ['Maintain protective hold', 'Perform outbound customer welfare check'],
        model_metadata: {
          provider: 'google-gemini',
          model_id: 'gemini-1.5-flash',
          latency_ms: 110,
        },
        created_at: new Date().toISOString(),
      };
      investigations.set(inv.id, inv);
      return jsonResponse(inv);
    }

    // Investigations for transaction
    const txInvMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/investigations$/);
    if (txInvMatch && method === 'GET') {
      const txId = txInvMatch[1];
      const list = Array.from(investigations.values()).filter((i) => i.transaction_id === txId);
      return jsonResponse({
        transaction_id: txId,
        total_entries: list.length,
        items: list,
      });
    }

    // Investigation conversations
    const convStartMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/conversations$/);
    if (convStartMatch && method === 'POST') {
      const txId = convStartMatch[1];
      const convId = `conv_${Date.now()}`;
      const conv = {
        id: convId,
        transaction_id: txId,
        status: 'ACTIVE',
        turn_count: 1,
        version: 1,
        turns: [
          {
            id: `t_${Date.now()}`,
            conversation_id: convId,
            turn_index: 0,
            role: 'assistant',
            content:
              'AegisPay Forensic Assistant ready. Ask me about evidence synthesis, risk rules, or scenario findings.',
            evidence_references: [],
            findings: [],
            created_at: new Date().toISOString(),
          },
        ],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      conversations.set(convId, conv);
      return jsonResponse(conv);
    }

    const convCurrentMatch = pathname.match(/^\/api\/v1\/transactions\/([^/]+)\/conversations\/current$/);
    if (convCurrentMatch && method === 'GET') {
      const txId = convCurrentMatch[1];
      for (const c of conversations.values()) {
        if (c.transaction_id === txId) return jsonResponse(c);
      }
      return jsonResponse(null, 404);
    }

    // Fallback for any other API route
    return jsonResponse({ message: 'Success (Simulated)' });
  } catch (err) {
    console.warn('Mock request handling error:', err);
    return new Response(JSON.stringify({ error: 'Internal mock error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

export function initMockBackend(): void {
  // Deterministic in-browser mock backend service ready
  if (typeof console !== 'undefined') {
    console.log('[AegisPay AI] In-browser mock backend ready.');
  }
}
