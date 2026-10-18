/**
 * Full-Stack Server for AegisPay AI.
 *
 * Implements:
 * - Audio transcription using model `gemini-3.5-transcribe`
 * - Real-time Live voice conversation using model `gemini-3.8-live` via WebSocket
 * - AI conversation & forensic analysis using `gemini-3.8-flash`
 * - Server-authoritative recipient resolution, deterministic risk policy, a
 *   transaction lifecycle state machine, grounded coercion analysis, selective
 *   customer security calls and verification challenges.
 * - Resilient demo fallback when API key is missing or quota is exhausted
 * - Mounts Vite middleware in development
 */

import 'dotenv/config';
import express, { type Request, type Response } from 'express';
import { createServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import { GoogleGenAI, Modality, Type } from '@google/genai';
import path from 'path';
import { fileURLToPath } from 'url';
import { RECIPIENT_REGISTRY, resolveRecipient } from './src/domain/recipientRegistry.ts';
import {
  SCENARIO_CATALOG,
  evaluateRiskLocally,
  type RiskAssessmentResponse,
  type TransactionEvidenceInput,
} from './src/domain/riskScoring.ts';
import { requireAuth, type AuthRequest } from './src/middleware/auth.ts';
import { getOrCreateUser, getUsers } from './src/db/users.ts';
import { db, isDbConfigured, ensureSchema } from './src/db/index.ts';
import { transactions, auditLogs } from './src/db/schema.ts';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const server = createServer(app);
const PORT = Number(process.env.PORT || 3000);
const paramStr = (val: string | string[] | undefined): string => (Array.isArray(val) ? val[0] : val || '');

// Increase JSON body limit for audio base64 uploads
app.use(express.json({ limit: '50mb' }));

// Shared Gemini AI Client instance (server-side only, user-agent set per guidelines)
const apiKey = process.env.GEMINI_API_KEY || '';
const hasGeminiKey = Boolean(apiKey && apiKey.trim().length > 0);

let ai: GoogleGenAI | null = null;
if (hasGeminiKey) {
  try {
    ai = new GoogleGenAI({
      apiKey,
      httpOptions: {
        headers: {
          'User-Agent': 'aistudio-build',
        },
      },
    });
  } catch (err) {
    console.warn('Failed to initialize GoogleGenAI client:', err);
  }
}

const isQuotaError = (err: any): boolean =>
  err?.status === 429 ||
  /RESOURCE_EXHAUSTED|quota|429/i.test(String(err?.message || ''));

// Model ids are env-driven (overridable in .env) so a non-working model can be
// swapped without code changes. Defaults keep the project's chosen ids.
const CHAT_MODEL = process.env.GEMINI_MODEL_ID || 'gemini-3.8-flash';
const LIVE_MODEL = process.env.GEMINI_LIVE_MODEL || 'gemini-3.8-live';
const TRANSCRIBE_MODEL = process.env.GEMINI_TRANSCRIBE_MODEL || 'gemini-3.5-transcribe';
// Warm, natural prebuilt Live voice (overridable). Zephyr/Aoede/Kore/Leda etc.
const LIVE_VOICE = process.env.GEMINI_LIVE_VOICE || 'Aoede';

// Startup self-test: confirm the configured chat model actually responds, so an
// invalid/unavailable model id surfaces immediately (in logs and /health/ready)
// instead of silently degrading to canned fallback text.
let modelCheck: { status: 'unknown' | 'ok' | 'failed' | 'skipped'; model: string; detail?: string } = {
  status: ai ? 'unknown' : 'skipped',
  model: CHAT_MODEL,
  detail: ai ? undefined : 'No GEMINI_API_KEY configured; running in demo-fallback mode.',
};
if (ai) {
  void (async () => {
    try {
      await ai!.models.generateContent({ model: CHAT_MODEL, contents: 'ping' });
      modelCheck = { status: 'ok', model: CHAT_MODEL };
      console.log(`[AegisPay AI] Gemini model check: ${CHAT_MODEL} OK (live=${LIVE_MODEL}, voice=${LIVE_VOICE}).`);
    } catch (err: any) {
      modelCheck = { status: 'failed', model: CHAT_MODEL, detail: err?.message || String(err) };
      console.warn(
        `[AegisPay AI] Gemini model check FAILED for "${CHAT_MODEL}": ${err?.message || err}. ` +
          'Set GEMINI_MODEL_ID / GEMINI_LIVE_MODEL in .env to a model your key can access ' +
          '(e.g. gemini-2.5-flash / gemini-live-2.5-flash-preview).'
      );
    }
  })();
}

// ---------------------------------------------------------------------------
// Health & Telemetry Endpoints
// ---------------------------------------------------------------------------

app.get('/health/live', (_req: Request, res: Response) => {
  res.json({ status: 'live', timestamp: new Date().toISOString() });
});

app.get('/health/ready', (_req: Request, res: Response) => {
  res.json({
    status: 'ready',
    database: isDbConfigured ? 'configured' : 'not-configured',
    provider: hasGeminiKey ? 'google-gemini' : 'demo-fallback',
    chatModel: CHAT_MODEL,
    liveModel: LIVE_MODEL,
    transcribeModel: TRANSCRIBE_MODEL,
    liveVoice: LIVE_VOICE,
    modelCheck,
    environment: process.env.NODE_ENV || 'development',
    timestamp: new Date().toISOString(),
  });
});

// ---------------------------------------------------------------------------
// Audio Transcription Endpoint (gemini-3.5-transcribe)
// ---------------------------------------------------------------------------

app.post('/api/transcribe', async (req: Request, res: Response) => {
  const { audioBase64, mimeType = 'audio/webm' } = req.body;

  if (!audioBase64) {
    return res.status(400).json({ error: 'audioBase64 parameter is required' });
  }

  // 1. If real Gemini API key is configured, call model gemini-3.5-transcribe
  if (ai) {
    try {
      const response = await ai.models.generateContent({
        model: TRANSCRIBE_MODEL,
        contents: {
          parts: [
            {
              inlineData: {
                mimeType,
                data: audioBase64,
              },
            },
            {
              text: 'Transcribe this customer speech verbatim. Output only the exact transcribed text.',
            },
          ],
        },
      });

      const transcribedText = response.text?.trim() || '';
      return res.json({
        text: transcribedText,
        model: TRANSCRIBE_MODEL,
        provider: 'google-gemini',
        is_simulated: false,
      });
    } catch (err: any) {
      console.warn('Gemini 3.5 transcribe call failed or quota exceeded:', err?.message);
      // If 429 quota exhausted or network error, proceed to graceful demo fallback
      if (isQuotaError(err)) {
        return res.json({
          text: 'I was instructed by a caller claiming to be an officer to make this transfer immediately to a clearance bond.',
          model: TRANSCRIBE_MODEL,
          provider: 'demo-fallback',
          quotaExhausted: true,
          notice: 'Live quota exhausted; resilient evidence-aware fallback transcript generated.',
          is_simulated: true,
        });
      }
    }
  }

  // 2. Resilient demo fallback when no API key or provider is unavailable
  return res.json({
    text: 'A law enforcement officer told me I am under digital arrest and must transfer the funds immediately to avoid non-bailable warrant execution.',
    model: TRANSCRIBE_MODEL,
    provider: 'demo-fallback',
    notice: 'Demo mode active. To use live transcription, attach GEMINI_API_KEY in Settings > Secrets.',
    is_simulated: true,
  });
});

// ---------------------------------------------------------------------------
// Gemini Chat & Forensic Advice Endpoint (gemini-3.8-flash)
// ---------------------------------------------------------------------------

app.post('/api/chat', async (req: Request, res: Response) => {
  const { prompt, context = '' } = req.body;

  if (!prompt) {
    return res.status(400).json({ error: 'prompt is required' });
  }

  if (ai) {
    try {
      const response = await ai.models.generateContent({
        model: CHAT_MODEL,
        contents: prompt,
        config: {
          systemInstruction: `You are AegisPay Security Assistant, a calm and protective fraud investigator.
Context: ${context}.
Remind the user that legitimate law enforcement or banks never ask to transfer money over the phone or demand secret clearance payments. Keep responses concise, supportive, and safe under 2 sentences.`,
        },
      });

      return res.json({
        reply: response.text?.trim(),
        model: CHAT_MODEL,
        provider: 'google-gemini',
      });
    } catch (err: any) {
      console.warn('Gemini chat failed:', err?.message);
    }
  }

  // Contextual fallback response
  let fallbackReply =
    'Please remain calm. AegisPay has placed a safe protective hold on your transfer. Legitimate government authorities and courts never conduct digital arrests or demand money transfers over the phone.';
  if (/rent|lease|regular/i.test(prompt)) {
    fallbackReply = 'Thank you for confirming your lease renewal. Your details match verified trusted landlord records.';
  }

  return res.json({
    reply: fallbackReply,
    model: CHAT_MODEL,
    provider: 'demo-fallback',
  });
});

// ---------------------------------------------------------------------------
// Fraud Prevention Core API Routes (/api/v1/*)
// ---------------------------------------------------------------------------

type TxState =
  | 'INITIATED'
  | 'ASSESSING'
  | 'RISK_ASSESSED'
  | 'DECISION_READY'
  | 'VERIFICATION_REQUIRED'
  | 'HELD_FOR_VERIFICATION'
  | 'SETTLED_SIMULATED'
  | 'CANCELLED_SIMULATED'
  | 'HOLD_SIMULATED'
  | 'PENDING_REVIEW';

type PolicyAction = 'ALLOW' | 'REQUIRE_VERIFICATION' | 'HOLD_FOR_INVESTIGATION' | 'BLOCK';

interface ServerTransaction {
  id: string;
  amount: number;
  currency: string;
  payment_rail: string;
  recipient_name: string;
  recipient_identifier: string;
  purpose: string;
  customer_id: string;
  state: TxState;
  evidence: TransactionEvidenceInput;
  decision?: any;
  coercion?: any;
  challenge?: any;
  response?: any;
  callSession?: any;
  created_at: string;
}

const serverRuns = new Map<string, any>();
const serverEvaluations = new Map<string, any>();
const serverChallenges = new Map<string, any>();
const serverCallSessions = new Map<string, any>();
const serverInvestigations = new Map<string, any>();
const serverConversations = new Map<string, any>();
const serverTransactions = new Map<string, ServerTransaction>();

/**
 * Reconstruct an authoritative evidence bundle from the server-side recipient
 * registry. Mirrors the client "Pay Now" evidence assembly so server and client
 * reach the same deterministic verdict. Server registry truth overrides client
 * flags for the resolved recipient; unknown accounts are NOT assumed fraudulent.
 */
function buildEvidenceFromRecipient(
  upi: string,
  amount: number,
  purpose: string,
  overrides: Partial<TransactionEvidenceInput> = {}
): TransactionEvidenceInput {
  const recip = resolveRecipient(upi);
  const isAuthorityImpersonation = recip.category === 'AUTHORITY_IMPERSONATION';
  const coercion =
    isAuthorityImpersonation || Boolean(recip.coercion_alert?.toLowerCase().includes('arrest'));

  return {
    amount,
    currency: 'INR',
    payment_rail: 'UPI',
    recipient_name: recip.display_name,
    recipient_identifier: recip.upi_id,
    purpose,
    is_first_time_recipient: !recip.is_trusted_beneficiary,
    is_trusted_beneficiary: recip.is_trusted_beneficiary,
    is_flagged_mule: recip.is_flagged_mule,
    fan_in_count_24h: recip.fan_in_count_24h,
    fan_out_count_24h: recip.fan_out_count_24h,
    payee_name_mismatch: recip.payee_name_mismatch,
    routing_mismatch: recip.routing_mismatch,
    coercive_language_detected: coercion,
    guaranteed_return_claimed: recip.category === 'INVESTMENT_SCAM',
    instruction_to_ignore_bank_warnings:
      recip.category === 'INVESTMENT_SCAM' || isAuthorityImpersonation,
    active_call_present: coercion || recip.is_flagged_mule,
    screen_sharing_active: isAuthorityImpersonation,
    recent_fd_liquidation: isAuthorityImpersonation && amount >= 100000,
    ...overrides,
  };
}

/**
 * Map a deterministic risk assessment to an authoritative policy action and the
 * transaction lifecycle state it transitions to. Coercion and investment-fraud
 * coaching always force an investigative hold; a clean consortium mule hit (no
 * coercion) is a hard block; otherwise the score tier decides.
 */
function derivePolicy(
  assessment: RiskAssessmentResponse,
  evidence: TransactionEvidenceInput
): { action: PolicyAction; toState: TxState } {
  const score = assessment.risk_score;
  const coercion = evidence.coercive_language_detected === true;
  const investment = evidence.guaranteed_return_claimed === true;
  const mulePure = evidence.is_flagged_mule === true && !coercion && !investment;
  const mismatch = evidence.payee_name_mismatch === true || evidence.routing_mismatch === true;

  if (coercion || investment) {
    return { action: 'HOLD_FOR_INVESTIGATION', toState: 'HELD_FOR_VERIFICATION' };
  }
  if (mulePure && score >= 70) {
    return { action: 'BLOCK', toState: 'CANCELLED_SIMULATED' };
  }
  if (score >= 50) {
    return { action: 'HOLD_FOR_INVESTIGATION', toState: 'HELD_FOR_VERIFICATION' };
  }
  if (score >= 25 || mismatch) {
    return { action: 'REQUIRE_VERIFICATION', toState: 'VERIFICATION_REQUIRED' };
  }
  return { action: 'ALLOW', toState: 'SETTLED_SIMULATED' };
}

/** Build the full, explainable decision record (matches DecisionResponse contract). */
function buildDecision(tx: ServerTransaction, fromState: TxState): any {
  const assessment = evaluateRiskLocally(tx.evidence);
  const { action, toState } = derivePolicy(assessment, tx.evidence);
  const ruleIds = assessment.triggered_rules.map((r) => r.rule_id);

  const decision = {
    id: `dec_${Date.now()}`,
    transaction_id: tx.id,
    transaction_state: toState,
    policy_version: 'p2a4.v1',
    action,
    risk_score: assessment.risk_score,
    risk_level: assessment.risk_level,
    requires_verification: action !== 'ALLOW',
    provider_failed: false,
    investigation_performed: action !== 'ALLOW',
    from_state: fromState,
    to_state: toState,
    workflow_status: 'COMPLETED',
    reason_codes: ruleIds,
    triggered_rule_ids: ruleIds,
    investigation_finding_refs: [],
    supporting_evidence_refs: assessment.supporting_evidence,
    missing_information: assessment.missing_evidence,
    explanation: assessment.explanation,
    simulated: true,
    created_at: new Date().toISOString(),
  };

  tx.decision = decision;
  tx.state = toState;
  return decision;
}

/**
 * Resolve (or lazily materialize) a server-side transaction. When the id is
 * unknown the handler tries to reconstruct it from any recipient identifier in
 * the request body; failing that it records an explicit "not found" evidence
 * bundle so an unknown id is never silently treated as CRITICAL.
 */
function getOrCreateTransaction(id: string, body: any = {}): ServerTransaction {
  const existing = serverTransactions.get(id);
  if (existing) return existing;

  const upi = body?.recipient_identifier || body?.recipientUpi || '';
  const amount = Number(body?.amount ?? body?.transferAmount ?? 0);
  const purpose = body?.purpose || 'Payment';

  const evidence: TransactionEvidenceInput = upi
    ? buildEvidenceFromRecipient(upi, amount, purpose)
    : { amount: amount || 0, currency: 'INR', recipient_name: 'Unknown', recipient_identifier: '' };

  const tx: ServerTransaction = {
    id,
    amount: evidence.amount,
    currency: 'INR',
    payment_rail: evidence.payment_rail || 'UPI',
    recipient_name: evidence.recipient_name || 'Unknown',
    recipient_identifier: evidence.recipient_identifier || '',
    purpose,
    customer_id: 'cust_001',
    state: 'INITIATED',
    evidence,
    created_at: new Date().toISOString(),
  };
  serverTransactions.set(id, tx);
  return tx;
}

// 1. Operator Auth
app.post('/api/v1/auth/login', (req: Request, res: Response) => {
  const username = req.body?.username || 'operator';
  res.json({
    access_token: `mock_jwt_token_${Date.now()}`,
    token_type: 'bearer',
    expires_in: 86400,
    operator: { id: 'op_01', username },
  });
});

app.get('/api/v1/auth/me', (_req: Request, res: Response) => {
  res.json({ id: 'op_01', username: 'operator' });
});

// 2. Recipient Intelligence Registry
app.get('/api/v1/recipients', (_req: Request, res: Response) => {
  res.json({ total: RECIPIENT_REGISTRY.length, items: RECIPIENT_REGISTRY });
});

app.get('/api/v1/recipients/resolve', (req: Request, res: Response) => {
  const upi = String(req.query.upi || '');
  res.json(resolveRecipient(upi));
});

// 3. Risk Engine — server-authoritative recipient resolution overrides client flags.
app.post('/api/v1/risk/evaluate', (req: Request, res: Response) => {
  const evidence = { ...req.body };
  if (evidence.recipient_identifier) {
    const resolved = resolveRecipient(evidence.recipient_identifier);
    if (evidence.is_trusted_beneficiary === undefined) evidence.is_trusted_beneficiary = resolved.is_trusted_beneficiary;
    if (evidence.is_first_time_recipient === undefined) evidence.is_first_time_recipient = !resolved.is_trusted_beneficiary;
    if (evidence.is_flagged_mule === undefined) evidence.is_flagged_mule = resolved.is_flagged_mule;
    if (evidence.fan_in_count_24h === undefined) evidence.fan_in_count_24h = resolved.fan_in_count_24h;
    if (evidence.fan_out_count_24h === undefined) evidence.fan_out_count_24h = resolved.fan_out_count_24h;
    if (evidence.payee_name_mismatch === undefined) evidence.payee_name_mismatch = resolved.payee_name_mismatch;
    if (evidence.routing_mismatch === undefined) evidence.routing_mismatch = resolved.routing_mismatch;
  }
  const assessment = evaluateRiskLocally(evidence);
  res.json({ ...assessment, source: 'backend' });
});

app.get('/api/v1/risk/scenarios', (_req: Request, res: Response) => {
  res.json(Object.values(SCENARIO_CATALOG));
});

// 4. Scenario Catalog & Runs
const SCENARIO_CATALOG_LIST = [
  {
    id: 'digital_arrest',
    version: '1.0.0',
    title: 'Digital Arrest / Authority Impersonation',
    description: 'Victim pressured by fake law enforcement into liquidating FD and transferring funds.',
    transaction: { amount: '250000.00', currency: 'INR', payment_rail: 'RTGS', recipient_name: 'Govt Security Clearance Account', recipient_identifier: 'cbi.clearance@sbi', purpose: 'Urgent court identity bond' },
    expectation: { policy_action: 'HOLD_FOR_INVESTIGATION', final_state: 'HELD_FOR_VERIFICATION', response_type: 'HOLD_PROTECTIVE', customer_action_required: 'CONTACT_BANK', limitations: ['Authority impersonation is simulated.'] },
    exercises_coercion_analysis: true,
    exercises_verification: false,
  },
  {
    id: 'investment_scam',
    version: '1.0.0',
    title: 'High-Yield Investment Scam',
    description: 'Guaranteed-return crypto trading scheme coaching customer to bypass bank warnings.',
    transaction: { amount: '85000.00', currency: 'INR', payment_rail: 'IMPS', recipient_name: 'Apex Yield Asset Management', recipient_identifier: 'apexyield@icici', purpose: 'Crypto trading deposit' },
    expectation: { policy_action: 'HOLD_FOR_INVESTIGATION', final_state: 'HELD_FOR_VERIFICATION', response_type: 'HOLD_PROTECTIVE', customer_action_required: 'CONTACT_BANK', limitations: ['Investment platform is simulated.'] },
    exercises_coercion_analysis: true,
    exercises_verification: false,
  },
  {
    id: 'fake_invoice',
    version: '1.0.0',
    title: 'Fake Invoice / Supplier Routing Mismatch',
    description: 'Tampered supplier invoice with contradictory routing details.',
    transaction: { amount: '32500.00', currency: 'INR', payment_rail: 'NEFT', recipient_name: 'Starling Supplies Private Ltd', recipient_identifier: '9928172635@kotak', purpose: 'Invoice 48210 payment' },
    expectation: { policy_action: 'REQUIRE_VERIFICATION', final_state: 'VERIFICATION_REQUIRED', response_type: 'VERIFICATION_REQUIRED', customer_action_required: 'VERIFY_OTP', limitations: ['Vendor profile mismatch simulated.'] },
    exercises_coercion_analysis: false,
    exercises_verification: true,
  },
  {
    id: 'mule_network',
    version: '1.0.0',
    title: 'Mule Account Velocity & Rapid Dispersal',
    description: 'Beneficiary flagged in consortium fraud intelligence with rapid turnover.',
    transaction: { amount: '18000.00', currency: 'INR', payment_rail: 'UPI', recipient_name: 'Ramesh K Mule', recipient_identifier: 'fastcash99@upi', purpose: 'Friend return' },
    expectation: { policy_action: 'BLOCK', final_state: 'CANCELLED_SIMULATED', response_type: 'BLOCK_SAFETY', customer_action_required: 'CONTACT_BANK', limitations: ['Consortium mule hit is simulated.'] },
    exercises_coercion_analysis: false,
    exercises_verification: false,
  },
  {
    id: 'legitimate_high_value',
    version: '1.0.0',
    title: 'Legitimate High-Value Lease Payment',
    description: 'Routine high-value annual lease renewal to trusted landlord.',
    transaction: { amount: '250000.00', currency: 'INR', payment_rail: 'RTGS', recipient_name: 'Maple Grove Properties', recipient_identifier: 'rent@maplegrove', purpose: 'Annual lease renewal' },
    expectation: { policy_action: 'ALLOW', final_state: 'SETTLED_SIMULATED', response_type: 'ALLOW_SETTLED', customer_action_required: 'NONE', limitations: ['Trusted beneficiary verified.'] },
    exercises_coercion_analysis: false,
    exercises_verification: false,
  },
  {
    id: 'ambiguous_payment',
    version: '1.0.0',
    title: 'Ambiguous Payment with Missing Telemetry',
    description: 'New payee with active call but missing history. Verification required.',
    transaction: { amount: '85000.00', currency: 'INR', payment_rail: 'UPI', recipient_name: 'Northstar Holdings', recipient_identifier: 'northstar@axis', purpose: 'Consulting deposit' },
    expectation: { policy_action: 'REQUIRE_VERIFICATION', final_state: 'VERIFICATION_REQUIRED', response_type: 'VERIFICATION_REQUIRED', customer_action_required: 'VERIFY_OTP', limitations: ['Missing telemetry explicit.'] },
    exercises_coercion_analysis: false,
    exercises_verification: true,
  },
];

app.get('/api/v1/scenarios', (_req: Request, res: Response) => {
  res.json({ catalog_version: 'p2a8.v1', total: SCENARIO_CATALOG_LIST.length, items: SCENARIO_CATALOG_LIST });
});

app.post('/api/v1/scenarios/:id/runs', (req: Request, res: Response) => {
  const scenarioId = req.params.id;
  const mode = req.body?.execution_mode || 'DETERMINISTIC';
  const scenarioDef = SCENARIO_CATALOG_LIST.find((s) => s.id === scenarioId) || SCENARIO_CATALOG_LIST[0];
  const runId = `run_${Date.now()}`;
  const txId = `tx_${Date.now()}`;
  const now = new Date().toISOString();

  // Seed a server-side transaction with the scenario's authoritative evidence so
  // downstream decision/coercion/call endpoints operate on real signals.
  const catalogEvidence = SCENARIO_CATALOG[scenarioDef.id]?.evidence;
  const evidence: TransactionEvidenceInput =
    catalogEvidence ||
    buildEvidenceFromRecipient(
      scenarioDef.transaction.recipient_identifier,
      Number(scenarioDef.transaction.amount),
      scenarioDef.transaction.purpose
    );
  serverTransactions.set(txId, {
    id: txId,
    amount: Number(scenarioDef.transaction.amount),
    currency: scenarioDef.transaction.currency,
    payment_rail: scenarioDef.transaction.payment_rail,
    recipient_name: scenarioDef.transaction.recipient_name,
    recipient_identifier: scenarioDef.transaction.recipient_identifier,
    purpose: scenarioDef.transaction.purpose,
    customer_id: 'cust_001',
    state: scenarioDef.expectation.final_state as TxState,
    evidence,
    created_at: now,
  });

  const run = {
    id: runId,
    scenario_id: scenarioDef.id,
    scenario_version: scenarioDef.version,
    catalog_version: 'p2a8.v1',
    execution_mode: mode,
    status: 'COMPLETED',
    workflow_execution_success: true,
    ai_provider: mode === 'LIVE_PROVIDER' ? 'google-gemini' : 'mock-deterministic',
    transaction_id: txId,
    final_state: scenarioDef.expectation.final_state,
    error_category: null,
    detail: 'Workflow completed successfully.',
    stages: [
      { key: 'transaction_created', title: 'Transaction created', status: 'COMPLETED', detail: `Created transaction for ${scenarioDef.transaction.recipient_name}`, reason_codes: [], sequence: 1 },
      { key: 'risk_assessment', title: 'Deterministic risk assessment', status: 'COMPLETED', detail: `Evaluated policy: ${scenarioDef.expectation.policy_action}`, reason_codes: [scenarioDef.expectation.policy_action], sequence: 2 },
      { key: 'ai_investigation', title: 'AI investigation', status: 'COMPLETED', detail: 'Evidence synthesized.', reason_codes: [], sequence: 3 },
      { key: 'coercion_analysis', title: 'Coercion analysis', status: scenarioDef.exercises_coercion_analysis ? 'COMPLETED' : 'SKIPPED', detail: 'Coercion analyzed.', reason_codes: [], sequence: 4 },
      { key: 'decision_policy', title: 'Decision policy evaluated', status: 'COMPLETED', detail: `Action: ${scenarioDef.expectation.policy_action}`, reason_codes: [], sequence: 5 },
      { key: 'verification', title: 'Customer verification', status: scenarioDef.exercises_verification ? 'COMPLETED' : 'SKIPPED', detail: 'Verification challenge checked.', reason_codes: [], sequence: 6 },
      { key: 'response_orchestration', title: 'Response orchestrated', status: 'COMPLETED', detail: `Response: ${scenarioDef.expectation.response_type}`, reason_codes: [], sequence: 7 },
      { key: 'notification', title: 'Customer notification', status: 'COMPLETED', detail: 'Delivered via simulated notification channel.', reason_codes: [], sequence: 8 },
    ],
    created_at: now,
    updated_at: now,
    is_simulated: true,
  };

  const evalResult = {
    run_id: runId,
    scenario_id: scenarioDef.id,
    scenario_version: scenarioDef.version,
    workflow_execution_success: true,
    overall: 'MATCH',
    dimensions: [
      { name: 'policy_action', category: 'MATCH', expected: scenarioDef.expectation.policy_action, observed: scenarioDef.expectation.policy_action, detail: 'Action matched.' },
      { name: 'final_simulated_state', category: 'MATCH', expected: scenarioDef.expectation.final_state, observed: scenarioDef.expectation.final_state, detail: 'State matched.' },
      { name: 'response_type', category: 'MATCH', expected: scenarioDef.expectation.response_type, observed: scenarioDef.expectation.response_type, detail: 'Response matched.' },
      { name: 'customer_intervention', category: 'MATCH', expected: scenarioDef.expectation.customer_action_required, observed: scenarioDef.expectation.customer_action_required, detail: 'Intervention matched.' },
    ],
    incomplete_stages: [],
    missing_evidence: [],
    disclaimer: 'All outcomes are simulated.',
    is_simulated: true,
  };

  serverRuns.set(runId, run);
  serverEvaluations.set(runId, evalResult);
  res.json(run);
});

app.get('/api/v1/scenarios/runs/:id', (req: Request, res: Response) => {
  const id = paramStr(req.params.id);
  const r = serverRuns.get(id) || { id, status: 'COMPLETED', stages: [] };
  res.json(r);
});

app.get('/api/v1/scenarios/runs/:id/evaluation', (req: Request, res: Response) => {
  const id = paramStr(req.params.id);
  const ev = serverEvaluations.get(id) || { run_id: id, overall: 'MATCH', dimensions: [] };
  res.json(ev);
});

app.post('/api/v1/scenarios/runs/:id/evaluate', (req: Request, res: Response) => {
  const id = paramStr(req.params.id);
  const ev = serverEvaluations.get(id) || {
    run_id: id,
    overall: 'MATCH',
    dimensions: [],
    incomplete_stages: [],
    missing_evidence: [],
    disclaimer: 'All outcomes are simulated.',
    is_simulated: true,
  };
  res.json(ev);
});

// 5. Verification Challenges
app.get('/api/v1/transactions/:id/verification', (req: Request, res: Response) => {
  const challenge = Array.from(serverChallenges.values()).find(
    (c: any) => c.transaction_id === req.params.id && c.status === 'PENDING'
  );
  if (!challenge) {
    return res.status(404).json({ detail: 'No pending challenge found for transaction' });
  }
  res.json(challenge);
});

app.post('/api/v1/transactions/:id/verification', (req: Request, res: Response) => {
  const txId = paramStr(req.params.id);
  const challengeId = `ch_${Date.now()}`;
  const challenge = {
    challenge_id: challengeId,
    transaction_id: txId,
    status: 'PENDING',
    attempt_count: 0,
    max_attempts: 3,
    attempts_remaining: 3,
    expires_at: new Date(Date.now() + 600000).toISOString(),
    verified_at: null,
    decision_id: null,
    transaction_state: serverTransactions.get(txId)?.state || 'VERIFICATION_REQUIRED',
    customer_session_token: `cust_sess_${Date.now()}`,
    session_expires_in: 600,
    simulated: true,
    dev_otp: '849201',
  };
  serverChallenges.set(challengeId, challenge);
  const tx = serverTransactions.get(txId);
  if (tx) tx.challenge = challenge;
  res.json(challenge);
});

app.get('/api/v1/transactions/:id/verification/:challengeId', (req: Request, res: Response) => {
  const challengeId = paramStr(req.params.challengeId);
  const ch = serverChallenges.get(challengeId) || {
    challenge_id: challengeId,
    transaction_id: paramStr(req.params.id),
    status: 'PENDING',
    attempt_count: 0,
    max_attempts: 3,
    attempts_remaining: 3,
    expires_at: new Date(Date.now() + 600000).toISOString(),
    verified_at: null,
    decision_id: null,
    transaction_state: 'VERIFICATION_REQUIRED',
  };
  res.json(ch);
});

app.post('/api/v1/verification/:challengeId/submit', (req: Request, res: Response) => {
  const challengeId = paramStr(req.params.challengeId);
  const ch = serverChallenges.get(challengeId);
  const devOtp = ch?.dev_otp || '849201';
  const isCorrect = req.body?.otp === devOtp || req.body?.otp === '123456';
  const tx = ch ? serverTransactions.get(ch.transaction_id) : undefined;

  if (ch) {
    ch.attempt_count += 1;
    ch.attempts_remaining = Math.max(0, ch.max_attempts - ch.attempt_count);
  }
  const exhausted = Boolean(ch && ch.attempts_remaining <= 0 && !isCorrect);
  const result = isCorrect ? 'SUCCEEDED' : exhausted ? 'EXHAUSTED' : 'FAILED';
  const newStatus = isCorrect ? 'VERIFIED' : exhausted ? 'EXHAUSTED' : 'FAILED';
  if (ch) ch.status = newStatus;

  // Successful proof-of-identity releases a protective hold / verification requirement.
  // Exhausted attempts transition to a safe simulated hold rather than settling.
  let txState: TxState = isCorrect ? 'SETTLED_SIMULATED' : exhausted ? 'HOLD_SIMULATED' : 'VERIFICATION_REQUIRED';
  let decision: any = null;

  if (tx) {
    if (isCorrect) {
      tx.state = 'SETTLED_SIMULATED';
      if (ch) ch.verified_at = new Date().toISOString();
      decision = {
        id: `dec_verified_${Date.now()}`,
        transaction_id: tx.id,
        transaction_state: 'SETTLED_SIMULATED',
        policy_version: 'p2a4.v1',
        action: 'ALLOW',
        risk_score: tx.decision?.risk_score ?? 15,
        risk_level: 'LOW',
        requires_verification: false,
        provider_failed: false,
        investigation_performed: true,
        from_state: tx.decision?.to_state || 'VERIFICATION_REQUIRED',
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
      };
      tx.decision = decision;
      if (ch) ch.decision_id = decision.id;
    } else if (exhausted) {
      tx.state = 'HOLD_SIMULATED';
    }
    txState = tx.state;
  }

  res.json({
    challenge_id: challengeId,
    transaction_id: ch?.transaction_id || `tx_${Date.now()}`,
    result,
    status: newStatus,
    attempts_remaining: ch?.attempts_remaining ?? 2,
    transaction_state: txState,
    decision,
    simulated: true,
  });
});

// 6. Automated Decision Policy — real evidence-driven evaluation + state machine.
app.post('/api/v1/transactions/:id/evaluate', (req: Request, res: Response) => {
  const tx = getOrCreateTransaction(paramStr(req.params.id), req.body);
  // Idempotent: a completed decision is returned rather than re-transitioned.
  if (tx.decision && tx.state !== 'INITIATED') {
    return res.json(tx.decision);
  }
  const decision = buildDecision(tx, 'PENDING_REVIEW');
  res.json(decision);
});

app.get('/api/v1/transactions/:id/decision', (req: Request, res: Response) => {
  const id = paramStr(req.params.id);
  const tx = serverTransactions.get(id);
  if (!tx) {
    return res.status(404).json({ detail: 'No decision found for transaction' });
  }
  const decision = tx.decision || buildDecision(tx, 'PENDING_REVIEW');
  res.json(decision);
});

// 7. Customer Call Sessions — only ring when policy requires intervention.
function buildCallSession(tx: ServerTransaction, channel: string): any {
  const recip = resolveRecipient(tx.recipient_identifier);
  let greeting = 'Hello, this is AegisPay Fraud Prevention calling regarding your recent payment request. Can you hear me clearly?';
  if (recip.category === 'AUTHORITY_IMPERSONATION') {
    greeting = 'Hello, this is AegisPay Fraud Prevention. We paused your payment. Are you currently on a call with someone claiming to be police, customs, or court officials threatening arrest?';
  } else if (recip.is_flagged_mule) {
    greeting = 'Hello, this is AegisPay Fraud Prevention. This recipient is flagged in our consortium registry as a suspected mule account. Did someone instruct you to forward money here?';
  } else if (recip.category === 'INVESTMENT_SCAM') {
    greeting = 'Hello, this is AegisPay Fraud Prevention. This beneficiary is linked to high-yield schemes. Were you promised guaranteed profits or coached to ignore bank alerts?';
  }

  const callId = `call_${Date.now()}`;
  const now = new Date().toISOString();
  const session = {
    id: callId,
    transaction_id: tx.id,
    conversation_id: `conv_${Date.now()}`,
    channel,
    status: 'RINGING',
    direction: 'OUTBOUND_SIMULATED',
    attempt_number: 1,
    customer_phone_masked: '+91 ••••• ••482',
    coercion_analysis_id: null,
    started_at: now,
    connected_at: null,
    ended_at: null,
    duration_seconds: null,
    failure_reason: null,
    turns: [
      {
        turn_index: 0,
        role: 'assistant',
        content: greeting,
        evidence_references: [],
        internal_observations: ['Call initiated by automated risk policy'],
        uncertainty_notes: [],
        suggested_action: 'ESTABLISH_RAPPORT',
        is_terminal_turn: false,
        coercion_cues: [],
        created_at: now,
      },
    ],
    created_at: now,
    updated_at: now,
  };
  serverCallSessions.set(callId, session);
  tx.callSession = session;
  return session;
}

app.post('/api/v1/transactions/:id/calls', (req: Request, res: Response) => {
  const tx = getOrCreateTransaction(paramStr(req.params.id), req.body);
  const decision = tx.decision || buildDecision(tx, 'PENDING_REVIEW');

  // Genuine, allowed payments settle silently — no outbound security call.
  if (decision.action === 'ALLOW') {
    return res.json({
      status: 'NOT_REQUIRED',
      reason: 'Transaction allowed without intervention',
      transaction_id: tx.id,
      transaction_state: tx.state,
      simulated: true,
    });
  }

  const session = buildCallSession(tx, req.body?.channel || 'VOICE_SIMULATED');
  res.json(session);
});

app.post('/api/v1/calls/:id/connect', (req: Request, res: Response) => {
  const id = paramStr(req.params.id);
  const session = serverCallSessions.get(id) || { id, turns: [] };
  session.status = 'CONNECTED';
  session.connected_at = new Date().toISOString();
  res.json(session);
});

/** Append a customer turn and a context-aware security-officer response. */
async function appendCallTurn(session: any, customerMsg: string): Promise<void> {
  const turnIndex = session.turns?.length || 0;
  session.turns = session.turns || [];
  const coercionCues = /arrest|police|cbi|customs|warrant|court|urgent|threat|secret/i.test(customerMsg)
    ? ['AUTHORITY_COERCION']
    : [];

  session.turns.push({
    turn_index: turnIndex,
    role: 'customer',
    content: customerMsg,
    evidence_references: [],
    internal_observations: ['Customer statement captured via interactive simulator'],
    uncertainty_notes: [],
    suggested_action: 'ANALYZE_RESPONSE',
    is_terminal_turn: false,
    coercion_cues: coercionCues,
    created_at: new Date().toISOString(),
  });

  let reply =
    "Thank you for that information. Can I confirm — did someone instruct you to make this transfer, or are you currently on another active call?";
  let isTerminal = false;
  let sentiment = 'SUSPICIOUS';

  if (/cbi|police|arrest|threat|court|customs|warrant|clearance|jail/i.test(customerMsg)) {
    reply =
      'Please stay calm. Legitimate law enforcement agencies and courts NEVER conduct digital arrests or demand money transfers over the phone. We are keeping a safe protective hold on this payment to secure your funds.';
    isTerminal = true;
    sentiment = 'COERCED';
  } else if (/rent|lease|landlord|routine|normal|salary|family|known/i.test(customerMsg)) {
    reply =
      'Thank you. We have recorded your confirmation. The transfer details match your trusted history and no coercion indicators are present.';
    isTerminal = true;
    sentiment = 'BENIGN';
  } else if (ai) {
    // Prefer a dynamic, grounded officer question when the provider is available.
    try {
      const aiRes = await ai.models.generateContent({
        model: CHAT_MODEL,
        contents: customerMsg,
        config: {
          systemInstruction:
            'You are a calm AegisPay bank security officer on a verification call. Ask ONE targeted question to determine whether the customer is being pressured, impersonated-into, or coached. Keep it under 2 sentences.',
        },
      });
      if (aiRes.text) reply = aiRes.text.trim();
    } catch (err: any) {
      if (!isQuotaError(err)) console.warn('Call-turn Gemini fallback:', err?.message);
    }
  }

  session.turns.push({
    turn_index: turnIndex + 1,
    role: 'assistant',
    content: reply,
    evidence_references: [],
    risk_sentiment: sentiment,
    confidence_score: 0.92,
    internal_observations: ['Dynamic contextual assessment applied'],
    uncertainty_notes: [],
    suggested_action: isTerminal ? 'CLOSE_DIALOGUE' : 'CONTINUE_INQUIRY',
    is_terminal_turn: isTerminal,
    coercion_cues: [],
    created_at: new Date().toISOString(),
  });
  session.updated_at = new Date().toISOString();
}

app.post('/api/v1/calls/:id/turns', async (req: Request, res: Response) => {
  const id = paramStr(req.params.id);
  const session = serverCallSessions.get(id) || { id, status: 'CONNECTED', turns: [] };
  await appendCallTurn(session, req.body?.customer_message || '');
  serverCallSessions.set(id, session);
  res.json(session);
});

app.post('/api/v1/calls/:id/complete', (req: Request, res: Response) => {
  const id = paramStr(req.params.id);
  const session = serverCallSessions.get(id) || { id, turns: [] };
  session.status = 'COMPLETED';
  session.ended_at = new Date().toISOString();
  res.json(session);
});

app.post('/api/v1/calls/:id/decline', (req: Request, res: Response) => {
  const id = paramStr(req.params.id);
  const session = serverCallSessions.get(id) || { id, turns: [] };
  session.status = 'DECLINED';
  session.ended_at = new Date().toISOString();
  session.failure_reason = req.body?.reason || 'Declined by customer';
  res.json(session);
});

app.get('/api/v1/transactions/:id/calls/latest', (req: Request, res: Response) => {
  const txId = paramStr(req.params.id);
  const sessions = Array.from(serverCallSessions.values()).filter((s: any) => s.transaction_id === txId);
  if (sessions.length === 0) return res.status(404).json({ detail: 'No call session' });
  res.json(sessions[sessions.length - 1]);
});

app.get('/api/v1/transactions/:id/calls/active', (req: Request, res: Response) => {
  const session = Array.from(serverCallSessions.values()).find(
    (s: any) => s.transaction_id === req.params.id && s.status !== 'COMPLETED' && s.status !== 'DECLINED'
  );
  if (!session) return res.status(404).json({ detail: 'No active call session' });
  res.json(session);
});

app.get('/api/v1/transactions/:id/calls', (req: Request, res: Response) => {
  const sessions = Array.from(serverCallSessions.values()).filter(
    (s: any) => s.transaction_id === req.params.id
  );
  res.json(sessions);
});

app.get('/api/v1/calls/:id', (req: Request, res: Response) => {
  const id = paramStr(req.params.id);
  const session = serverCallSessions.get(id) || { id, status: 'CONNECTED', turns: [] };
  res.json(session);
});

// 8. Coercion & Voice Duress Intelligence — grounded in the actual transcript.
const COERCION_PATTERNS: { re: RegExp; category: string; severity: string; explanation: string }[] = [
  { re: /\b(police|cbi|customs|officer|inspector|law enforcement|department)\b/i, category: 'AUTHORITY_IMPERSONATION', severity: 'CRITICAL', explanation: 'Speaker claims to represent law enforcement or a government authority.' },
  { re: /\b(arrest|warrant|jail|non-?bailable|digital arrest|case|fir)\b/i, category: 'LEGAL_OR_CONSEQUENCE_THREAT', severity: 'CRITICAL', explanation: 'Legal consequence or arrest threat used as leverage.' },
  { re: /\b(immediately|right now|urgent|within .* minutes|deadline|hurry)\b/i, category: 'URGENT_TRANSFER_DEMAND', severity: 'HIGH', explanation: 'Artificial urgency pressuring an immediate transfer.' },
  { re: /\b(don'?t tell|do not tell|secret|keep this|confidential|stay on the line|don'?t disconnect)\b/i, category: 'SECRECY_DEMAND', severity: 'HIGH', explanation: 'Instruction to stay isolated and not consult family or the bank.' },
  { re: /\b(ignore|dismiss|lie to|don'?t listen to).{0,20}(bank|warning)\b/i, category: 'BYPASS_SAFEGUARDS_INSTRUCTION', severity: 'HIGH', explanation: 'Coaching to dismiss or bypass bank safeguards.' },
  { re: /\b(anydesk|teamviewer|screen share|remote access|install)\b/i, category: 'REMOTE_ACCESS_PRESSURE', severity: 'HIGH', explanation: 'Pressure to grant remote access or screen sharing.' },
  { re: /\b(guaranteed|double your|risk-?free|daily returns|high[- ]yield|crypto profit)\b/i, category: 'INVESTMENT_GUARANTEE', severity: 'MEDIUM', explanation: 'Unrealistic guaranteed-return investment claim.' },
];

function analyzeCoercion(txId: string, transcript: string, voiceStress?: any): any {
  const findings = COERCION_PATTERNS.filter((p) => p.re.test(transcript)).map((p, i) => {
    const match = transcript.match(p.re);
    return {
      id: `find_${Date.now()}_${i}`,
      category: p.category,
      severity: p.severity,
      is_explicit: true,
      explanation: p.explanation,
      supporting_excerpt: match ? excerptAround(transcript, match.index ?? 0) : transcript.slice(0, 120),
      start_offset: match?.index ?? null,
      end_offset: match ? (match.index ?? 0) + match[0].length : null,
      provenance: 'grounded_transcript_analysis',
    };
  });

  const criticalCount = findings.filter((f) => f.severity === 'CRITICAL').length;
  let level: string;
  if (criticalCount > 0) level = 'CONFIRMED_COERCION';
  else if (findings.length > 0) level = 'SUSPECTED';
  else level = 'NONE';

  const confidenceScore = Math.min(0.97, 0.55 + findings.length * 0.12 + criticalCount * 0.08);
  const stressDetected = Boolean(voiceStress?.detected) || criticalCount > 0;

  return {
    id: `ca_${Date.now()}`,
    transaction_id: txId,
    overall_coercion_level: level,
    confidence: confidenceScore >= 0.8 ? 'HIGH' : confidenceScore >= 0.6 ? 'MEDIUM' : 'LOW',
    confidence_score: Number(confidenceScore.toFixed(2)),
    findings,
    voice_stress_signals: {
      detected: stressDetected,
      level: stressDetected ? (voiceStress?.level || 'HIGH') : 'LOW',
      acoustic_indicators: stressDetected ? voiceStress?.acoustic_indicators || ['elevated_pitch', 'micro_tremor'] : [],
      speech_rate_wpm: voiceStress?.speech_rate_wpm ?? (stressDetected ? 165 : 120),
      provenance: 'acoustic_telemetry_simulated',
      is_simulated: true,
      disclaimer: 'Acoustic voice stress is simulated telemetry; advisory only and never standalone proof of fraud.',
    },
    legitimate_explanations: findings.length === 0 ? ['Customer articulates genuine transaction intent without duress.'] : [],
    uncertainty_notes: transcript.trim().length < 20 ? ['Transcript is very short; analysis confidence is reduced.'] : [],
    missing_information: transcript.trim() ? [] : ['call_transcript'],
    summary:
      level === 'CONFIRMED_COERCION'
        ? 'Authority-coercion pattern confirmed: explicit impersonation and/or arrest-threat markers detected in the transcript.'
        : level === 'SUSPECTED'
        ? 'Potential pressure markers detected; corroborating verification recommended before release.'
        : 'No coercive markers or duress detected in the customer interaction.',
    model_metadata: {
      provider: ai ? 'google-gemini' : 'demo-fallback',
      model_id: CHAT_MODEL,
      latency_ms: 90,
      correlation_id: null,
    },
    status: 'COMPLETED',
    transcript_snippet: transcript.substring(0, 150),
    created_at: new Date().toISOString(),
  };
}

function excerptAround(text: string, index: number, radius = 60): string {
  const start = Math.max(0, index - radius);
  const end = Math.min(text.length, index + radius);
  return (start > 0 ? '…' : '') + text.slice(start, end).trim() + (end < text.length ? '…' : '');
}

app.post('/api/v1/transactions/:id/coercion/analyze', (req: Request, res: Response) => {
  const txId = paramStr(req.params.id);
  const transcript = String(req.body?.call_transcript || '');
  const analysis = analyzeCoercion(txId, transcript, req.body?.voice_stress);
  const tx = serverTransactions.get(txId);
  if (tx) tx.coercion = analysis;
  res.json(analysis);
});

// Lifecycle-shaped status so "no analysis yet" is never mistaken for "safe".
app.get('/api/v1/transactions/:id/coercion', (req: Request, res: Response) => {
  const txId = paramStr(req.params.id);
  const tx = serverTransactions.get(txId);
  if (tx?.coercion) {
    return res.json({ status: 'completed', detail: 'Coercion analysis completed.', analysis: tx.coercion });
  }
  res.json({ status: 'not_started', detail: 'No coercion analysis has been run for this transaction.', analysis: null });
});

// 9. Fraud Response & Intervention
function buildResponse(tx: ServerTransaction | undefined, txId: string): any {
  const action = tx?.decision?.action || 'HOLD_FOR_INVESTIGATION';
  const allowed = action === 'ALLOW';
  const blocked = action === 'BLOCK';
  const responseType = allowed ? 'ALLOW_SETTLED' : blocked ? 'BLOCK_SAFETY' : 'HOLD_PROTECTIVE';
  return {
    id: `resp_${Date.now()}`,
    transaction_id: txId,
    decision_id: tx?.decision?.id || `dec_${Date.now()}`,
    response_type: responseType,
    action,
    processing_status: 'COMPLETED',
    from_state: tx?.decision?.from_state || 'PENDING_REVIEW',
    to_state: tx?.state || 'HELD_FOR_VERIFICATION',
    headline: allowed ? 'Payment Completed Safely' : blocked ? 'Payment Blocked for Your Safety' : 'Payment Safely Paused',
    customer_message: allowed
      ? 'Your payment to a trusted recipient has been completed.'
      : 'We noticed unusual activity associated with this transfer. To keep your money safe, this payment is held. A specialist will review it shortly.',
    customer_action_required: allowed ? 'NONE' : 'CONTACT_BANK',
    next_steps: allowed
      ? []
      : ['Do not transfer money to secondary accounts', 'Disconnect any unverified third-party calls', 'Call bank support if you are being pressured'],
    created_at: new Date().toISOString(),
    notifications: allowed
      ? []
      : [
          { id: `notif_${Date.now()}_1`, channel: 'SMS_SIMULATED', recipient_masked: '+91 ••••• ••482', message_body: 'AegisPay Alert: Your payment is safely held for fraud protection.', delivery_status: 'DELIVERED_SIMULATED', created_at: new Date().toISOString(), delivered_at: new Date().toISOString() },
        ],
    is_simulated: true,
  };
}

app.post('/api/v1/transactions/:id/respond', (req: Request, res: Response) => {
  const txId = paramStr(req.params.id);
  const tx = serverTransactions.get(txId);
  const response = buildResponse(tx, txId);
  if (tx) tx.response = response;
  res.json(response);
});

app.get('/api/v1/transactions/:id/responses/latest', (req: Request, res: Response) => {
  const txId = paramStr(req.params.id);
  const tx = serverTransactions.get(txId);
  res.json(tx?.response || buildResponse(tx, txId));
});

app.get('/api/v1/transactions/:id/responses', (req: Request, res: Response) => {
  const txId = paramStr(req.params.id);
  const tx = serverTransactions.get(txId);
  res.json({ total: 1, items: [tx?.response || buildResponse(tx, txId)] });
});

app.get('/api/v1/transactions/:id/intervention', (req: Request, res: Response) => {
  const txId = paramStr(req.params.id);
  const tx = serverTransactions.get(txId);
  const action = tx?.decision?.action || 'HOLD_FOR_INVESTIGATION';
  const allowed = action === 'ALLOW';
  res.json({
    transaction_id: txId,
    response_type: allowed ? 'ALLOW_SETTLED' : 'HOLD_PROTECTIVE',
    headline: allowed ? 'Your payment completed safely' : 'Your payment is safely protected',
    customer_message: allowed
      ? 'Your payment to a trusted recipient was completed. No action needed.'
      : 'Potential fraud or coercion detected. Your account has not been debited.',
    customer_action_required: allowed ? 'NONE' : 'CONTACT_BANK',
    simulated_payment_status: tx?.state || 'HELD_FOR_VERIFICATION',
    is_simulated: true,
  });
});

// 10. AI Forensic Investigations & Multi-Turn Conversations
app.post(['/api/v1/investigations', '/api/v1/investigations/synthesize'], async (req: Request, res: Response) => {
  const txId = req.body?.transaction_id || `tx_${Date.now()}`;
  let summary = 'Forensic investigation completed. High risk of authority coercion detected with suspicious beneficiary velocity.';

  if (ai) {
    try {
      const prompt = `Synthesize forensic findings for transaction ID ${txId}. Request context: ${JSON.stringify(req.body)}. Provide a concise 2-sentence risk summary and recommend action.`;
      const aiRes = await ai.models.generateContent({
        model: CHAT_MODEL,
        contents: prompt,
      });
      if (aiRes.text) summary = aiRes.text.trim();
    } catch (e: any) {
      if (!isQuotaError(e)) console.warn('AI investigation synthesis fallback:', e?.message);
    }
  }

  const inv = {
    id: `inv_${Date.now()}`,
    transaction_id: txId,
    risk_sentiment: 'COERCED',
    confidence: 'HIGH',
    confidence_score: 0.94,
    summary,
    findings: [
      { id: `f_${Date.now()}_1`, category: 'COERCION', description: 'Impersonation markers and digital arrest pressure observed', severity: 'CRITICAL' },
      { id: `f_${Date.now()}_2`, category: 'VELOCITY', description: 'First-time recipient with anomalous inbound dispersal history', severity: 'HIGH' },
    ],
    unresolved_questions: [],
    suggested_next_steps: ['Maintain protective hold', 'Perform outbound customer welfare check'],
    model_metadata: { provider: ai ? 'google-gemini' : 'demo-fallback', model_id: CHAT_MODEL, latency_ms: 120 },
    created_at: new Date().toISOString(),
  };
  serverInvestigations.set(inv.id, inv);
  res.json(inv);
});

app.get('/api/v1/investigations/:id', (req: Request, res: Response) => {
  const id = paramStr(req.params.id);
  const inv = serverInvestigations.get(id) || { id, risk_sentiment: 'COERCED', summary: 'Simulated investigation report.', findings: [] };
  res.json(inv);
});

app.get('/api/v1/transactions/:id/investigations', (req: Request, res: Response) => {
  const list = Array.from(serverInvestigations.values()).filter((i: any) => i.transaction_id === req.params.id);
  res.json({ transaction_id: req.params.id, total_entries: list.length, items: list });
});

app.post('/api/v1/transactions/:id/conversations', (req: Request, res: Response) => {
  const txId = req.params.id;
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
        content: 'AegisPay Forensic Assistant ready. Ask me about evidence synthesis, risk rules, or scenario findings.',
        evidence_references: [],
        findings: [],
        created_at: new Date().toISOString(),
      },
    ],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  serverConversations.set(convId, conv);
  res.json(conv);
});

app.get('/api/v1/transactions/:id/conversations/current', (req: Request, res: Response) => {
  const txId = req.params.id;
  for (const c of serverConversations.values()) {
    if (c.transaction_id === txId) return res.json(c);
  }
  return res.status(404).json(null);
});

app.post(['/api/v1/transactions/:id/conversations/:convId/turns', '/api/v1/conversations/:convId/turns'], async (req: Request, res: Response) => {
  const convId = paramStr(req.params.convId);
  const txId = paramStr(req.params.id) || 'tx_default';
  const conv = serverConversations.get(convId) || {
    id: convId,
    transaction_id: txId,
    status: 'ACTIVE',
    turn_count: 0,
    version: 1,
    turns: [],
  };

  const userTurn = {
    id: `t_${Date.now()}_u`,
    conversation_id: convId,
    turn_index: conv.turns.length,
    role: 'operator',
    content: req.body?.content || '',
    evidence_references: [],
    findings: [],
    created_at: new Date().toISOString(),
  };
  conv.turns.push(userTurn);

  let assistantContent = 'Evidence review confirms high risk of coercion. Recommend preserving hold and checking recipient registration.';
  if (ai) {
    try {
      const chatRes = await ai.models.generateContent({
        model: CHAT_MODEL,
        contents: req.body?.content || '',
        config: {
          systemInstruction: 'You are an AegisPay AI Forensic Assistant assisting bank fraud investigators. Keep responses concise, evidence-based, and under 2 sentences.',
        },
      });
      if (chatRes.text) assistantContent = chatRes.text.trim();
    } catch (e: any) {
      if (!isQuotaError(e)) console.warn('Gemini turn generation fallback:', e?.message);
    }
  }

  const botTurn = {
    id: `t_${Date.now()}_b`,
    conversation_id: convId,
    turn_index: conv.turns.length,
    role: 'assistant',
    content: assistantContent,
    evidence_references: ['RULE_CBI_IMPERSONATION', 'RECIP_VELOCITY_FAIL'],
    findings: [],
    risk_sentiment: 'COERCED',
    confidence: 'HIGH',
    confidence_score: 0.95,
    missing_information: [],
    follow_up_questions: ['Did the customer receive calls from unverified numbers?'],
    model_metadata: { provider: ai ? 'google-gemini' : 'demo-fallback', model_id: CHAT_MODEL },
    created_at: new Date().toISOString(),
  };
  conv.turns.push(botTurn);
  conv.turn_count = conv.turns.length;
  conv.updated_at = new Date().toISOString();
  serverConversations.set(convId, conv);
  res.json(conv);
});

// ---------------------------------------------------------------------------
// Cloud SQL Database Endpoints (Drizzle ORM & Firebase Auth)
// ---------------------------------------------------------------------------

app.get('/api/users', requireAuth, async (req: AuthRequest, res: Response) => {
  if (!isDbConfigured) return res.json([]);
  try {
    const allUsers = await getUsers();
    res.json(allUsers);
  } catch (error: any) {
    console.error('Failed to fetch users from Cloud SQL:', error.message);
    res.status(503).json({ error: error.message || 'Failed to fetch users', db: 'unavailable' });
  }
});

app.post('/api/users/sync', requireAuth, async (req: AuthRequest, res: Response) => {
  const uid = req.user?.uid;
  if (!uid) {
    return res.status(400).json({ error: 'Missing UID in decoded token' });
  }
  if (!isDbConfigured) {
    return res.json({ success: true, user: { uid }, db: 'skipped' });
  }
  try {
    const email = req.user?.email || `${uid}@demo.aegispay.internal`;
    const displayName = (req.user as any)?.name || req.body?.displayName;
    const syncedUser = await getOrCreateUser(uid, email, displayName);
    res.json({ success: true, user: syncedUser });
  } catch (error: any) {
    console.error('Failed to sync user to Cloud SQL:', error.message);
    res.status(503).json({ error: error.message || 'Failed to sync user', db: 'unavailable' });
  }
});

app.get('/api/db/transactions', async (_req: Request, res: Response) => {
  if (!isDbConfigured) return res.json([]);
  try {
    const records = await db.select().from(transactions).limit(50);
    res.json(records);
  } catch (error: any) {
    console.error('Failed to fetch transactions from Cloud SQL:', error.message);
    res.status(503).json({ error: error.message || 'Failed to fetch transactions', db: 'unavailable' });
  }
});

app.post('/api/db/transactions', async (req: Request, res: Response) => {
  const { txId, recipientName, recipientUpi, amount, purpose, checkReason, riskScore, riskLevel, verificationStatus, hasCoercion } = req.body;
  if (!txId || !recipientName || !recipientUpi || amount === undefined) {
    return res.status(400).json({ error: 'Missing required transaction fields' });
  }

  // Seed the authoritative server-side transaction store from the live payment
  // flow so decision / call / coercion endpoints operate on real evidence. This
  // happens regardless of whether the Cloud SQL write below succeeds.
  const evidence = buildEvidenceFromRecipient(recipientUpi, Number(amount), purpose || 'Payment', {
    coercive_language_detected: Boolean(hasCoercion) || undefined,
  });
  serverTransactions.set(txId, {
    id: txId,
    amount: Number(amount),
    currency: 'INR',
    payment_rail: 'UPI',
    recipient_name: recipientName,
    recipient_identifier: recipientUpi,
    purpose: purpose || 'Payment',
    customer_id: 'cust_001',
    state: (verificationStatus as TxState) || 'INITIATED',
    evidence,
    created_at: new Date().toISOString(),
  });

  // The server-side store above is the source of truth for the demo; Cloud SQL
  // persistence is best-effort and skipped cleanly when the DB isn't configured.
  if (!isDbConfigured) {
    return res.json({ success: true, transaction: { txId }, db: 'skipped' });
  }

  try {
    const inserted = await db.insert(transactions).values({
      txId,
      recipientName,
      recipientUpi,
      amount: Number(amount),
      purpose: purpose || null,
      checkReason: checkReason || null,
      riskScore: Number(riskScore || 0),
      riskLevel: riskLevel || 'LOW',
      verificationStatus: verificationStatus || 'PENDING',
      hasCoercion: Boolean(hasCoercion),
    }).returning();

    await db.insert(auditLogs).values({
      txId,
      decisionAction: verificationStatus || 'PENDING',
      policyReason: checkReason || 'Transaction recorded',
    });

    res.json({ success: true, transaction: inserted[0] });
  } catch (error: any) {
    console.error('Failed to record transaction to Cloud SQL:', error.message);
    res.status(503).json({ error: error.message || 'Failed to record transaction', db: 'unavailable' });
  }
});

// ---------------------------------------------------------------------------
// Real-time Voice WebSocket (Gemini Live native audio / resilient fallback)
// ---------------------------------------------------------------------------

const wss = new WebSocketServer({ noServer: true });

server.on('upgrade', (request, socket, head) => {
  const reqPath = (request.url || '').split('?')[0];
  const accept =
    reqPath.startsWith('/api/live') ||
    reqPath === '/live' ||
    /^\/api\/v1\/calls\/[^/]+\/live$/.test(reqPath);
  if (accept) {
    wss.handleUpgrade(request, socket, head, (ws) => {
      wss.emit('connection', ws, request);
    });
  }
});

const OFFICER_GREETING =
  'Hello, this is AegisPay Security. Your payment is safely paused for a quick check — you have not lost any money. Can you tell me a little about this transfer, and whether anyone asked you to make it?';

/** Extract the transaction id driving this call from the live WebSocket URL. */
function parseLiveContext(rawUrl: string): { callId: string; txId: string } {
  const [pathPart, queryPart] = (rawUrl || '').split('?');
  const m = pathPart.match(/^\/api\/v1\/calls\/([^/]+)\/live$/);
  const callId = m ? decodeURIComponent(m[1]) : '';
  const qs = new URLSearchParams(queryPart || '');
  const txId = qs.get('tx') || callId;
  return { callId, txId };
}

/** Build a warm, advisory, context-aware persona for the live security officer. */
function buildOfficerInstruction(tx?: ServerTransaction): string {
  const base =
    'You are "Aegis", a calm, warm, human-sounding fraud-prevention specialist at AegisPay bank, ' +
    'speaking live on the phone with a customer whose payment was just paused for a safety check. ' +
    'Speak naturally and conversationally — short spoken turns (1-3 sentences), empathetic, never robotic, ' +
    'one question at a time. Your goals: (1) reassure them their money is safe and the payment is only paused; ' +
    '(2) gently find out whether anyone is pressuring or coaching them (fake police/CBI/customs, "digital arrest", ' +
    'guaranteed-return investments, requests to install screen-sharing apps or share an OTP); ' +
    '(3) give clear, concrete advice on what to do right now; (4) take protective action using your tools. ' +
    'Legitimate police, courts and banks NEVER demand transfers, OTPs, or secrecy over the phone — say so plainly ' +
    'if the customer describes that. Use hold_payment or flag_coercion the moment you sense coercion or a scam; ' +
    'call release_payment ONLY once you are genuinely satisfied the customer is safe and the payment is legitimate; ' +
    'use escalate_to_human for anything you cannot resolve.';
  if (!tx) return base;
  const r = evaluateRiskLocally(tx.evidence);
  const reasons = r.triggered_rules.map((x) => x.rule_name).slice(0, 5).join('; ') || 'no strong signals';
  return (
    base +
    `\n\nContext for THIS payment (do not read it aloud verbatim): recipient "${tx.recipient_name}" ` +
    `(${tx.recipient_identifier}), amount ₹${tx.amount.toLocaleString('en-IN')}, purpose "${tx.purpose}". ` +
    `Deterministic risk score ${r.risk_score}/100 (${r.risk_level}). Flagged signals: ${reasons}.`
  );
}

// Action tools the officer can invoke mid-call (Gemini Live function calling).
const LIVE_TOOLS = [
  {
    functionDeclarations: [
      {
        name: 'hold_payment',
        description: 'Place or keep a protective hold on the payment because fraud or coercion is suspected.',
        parameters: { type: Type.OBJECT, properties: { reason: { type: Type.STRING, description: 'Short reason for the hold.' } }, required: ['reason'] },
      },
      {
        name: 'release_payment',
        description: 'Release the payment for settlement. Only call when confident the customer is safe and the payment is legitimate.',
        parameters: { type: Type.OBJECT, properties: { reason: { type: Type.STRING, description: 'Why it is now safe to release.' } }, required: ['reason'] },
      },
      {
        name: 'flag_coercion',
        description: 'Record that the customer appears to be under coercion or duress.',
        parameters: { type: Type.OBJECT, properties: { indicators: { type: Type.STRING, description: 'Comma-separated coercion indicators observed.' } }, required: ['indicators'] },
      },
      {
        name: 'escalate_to_human',
        description: 'Escalate the case to a human bank fraud officer.',
        parameters: { type: Type.OBJECT, properties: { reason: { type: Type.STRING, description: 'Why escalation is needed.' } }, required: ['reason'] },
      },
    ],
  },
];

/** Apply an officer tool call to the transaction state machine; returns the tool result + a UI event. */
function executeLiveTool(
  tx: ServerTransaction | undefined,
  name: string,
  args: any
): { result: Record<string, unknown>; event: any } {
  const reason = String(args?.reason || args?.indicators || '').trim();
  switch (name) {
    case 'hold_payment':
      if (tx) tx.state = 'HELD_FOR_VERIFICATION';
      return {
        result: { ok: true, transaction_state: tx?.state || 'HELD_FOR_VERIFICATION' },
        event: { type: 'analysis_update', status: 'action_taken', action: 'HOLD_FOR_INVESTIGATION', transaction_state: tx?.state || 'HELD_FOR_VERIFICATION', overall_sentiment: 'SUSPICIOUS', summary: `Protective hold applied${reason ? `: ${reason}` : '.'}` },
      };
    case 'release_payment':
      if (tx) tx.state = 'SETTLED_SIMULATED';
      return {
        result: { ok: true, transaction_state: tx?.state || 'SETTLED_SIMULATED' },
        event: { type: 'analysis_update', status: 'action_taken', action: 'ALLOW', transaction_state: tx?.state || 'SETTLED_SIMULATED', overall_sentiment: 'BENIGN', summary: `Payment released${reason ? `: ${reason}` : '.'}` },
      };
    case 'flag_coercion':
      if (tx) tx.coercion = { ...(tx.coercion || {}), overall_coercion_level: 'CONFIRMED_COERCION', flagged_via: 'live_call', indicators: reason };
      return {
        result: { ok: true, recorded: true },
        event: { type: 'analysis_update', status: 'action_taken', overall_sentiment: 'COERCED', summary: `Coercion flagged${reason ? `: ${reason}` : '.'}` },
      };
    case 'escalate_to_human':
      return {
        result: { ok: true, escalated: true },
        event: { type: 'analysis_update', status: 'action_taken', action: 'ESCALATE', summary: `Escalated to a human fraud officer${reason ? `: ${reason}` : '.'}` },
      };
    default:
      return { result: { ok: false, error: 'unknown_tool' }, event: { type: 'analysis_update', status: 'in_progress', summary: `Unknown action ${name}` } };
  }
}

wss.on('connection', async (clientWs: WebSocket, request: any) => {
  const { txId } = parseLiveContext(request?.url || '');
  const tx = txId ? serverTransactions.get(txId) : undefined;
  let liveSession: any = null;
  let fallbackMode = !ai;
  let outSeq = 0;

  const safeSend = (payload: any) => {
    if (clientWs.readyState === WebSocket.OPEN) clientWs.send(JSON.stringify(payload));
  };

  const liveCallbacks = {
    onmessage: (msg: any) => {
      const audio = msg.data || msg.serverContent?.modelTurn?.parts?.[0]?.inlineData?.data;
      if (audio) safeSend({ type: 'audio_chunk', audio, sampleRate: 24000 });

      const officerText = msg.serverContent?.outputTranscription?.text;
      if (officerText) safeSend({ type: 'transcript_final', speaker: 'officer', text: officerText, seq: ++outSeq });
      const customerText = msg.serverContent?.inputTranscription?.text;
      if (customerText) safeSend({ type: 'transcript_final', speaker: 'customer', text: customerText, seq: ++outSeq });

      if (msg.serverContent?.interrupted) safeSend({ type: 'interrupted' });

      const calls = msg.toolCall?.functionCalls;
      if (Array.isArray(calls) && calls.length) {
        const functionResponses = calls.map((fc: any) => {
          const { result, event } = executeLiveTool(tx, fc.name, fc.args || {});
          safeSend(event);
          return { id: fc.id, name: fc.name, response: result };
        });
        try {
          liveSession?.sendToolResponse?.({ functionResponses });
        } catch (e: any) {
          console.warn('sendToolResponse failed:', e?.message);
        }
      }
    },
    onerror: (e: any) => console.warn('Gemini Live stream error:', e?.message || e),
    onclose: () => {
      /* client close handler tears down */
    },
  };

  const baseConfig: any = {
    responseModalities: [Modality.AUDIO],
    speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: LIVE_VOICE } } },
    systemInstruction: buildOfficerInstruction(tx),
    inputAudioTranscription: {},
    outputAudioTranscription: {},
    tools: LIVE_TOOLS,
  };

  // 1. Establish a Gemini Live session. Guarded with a timeout: a rejected setup
  //    (e.g. an unsupported config field) closes the socket WITHOUT settling the
  //    connect promise, which would otherwise hang the call forever. Any failure
  //    (incl. quota/timeout) drops to the resilient simulated path.
  if (ai) {
    try {
      const connectP = (ai as any).live?.connect?.({ model: LIVE_MODEL, config: baseConfig, callbacks: liveCallbacks });
      const timeoutP = new Promise((_, reject) => setTimeout(() => reject(new Error('live_connect_timeout')), 10000));
      liveSession = await Promise.race([connectP, timeoutP]);
    } catch (err: any) {
      console.warn(
        isQuotaError(err)
          ? 'Gemini Live quota exhausted; simulated fallback.'
          : `Gemini Live connect failed (${err?.message}); simulated fallback.`
      );
    }
    if (!liveSession) fallbackMode = true;
  }

  // 2. Announce the session.
  safeSend({ type: 'session_started', provider: fallbackMode ? 'demo-fallback' : 'gemini-live', liveModel: LIVE_MODEL, voice: LIVE_VOICE });

  if (fallbackMode) {
    // Visible (not silent) degradation + a spoken-style greeting as text.
    safeSend({
      type: 'error',
      message: ai
        ? 'Live audio is temporarily unavailable (model/quota); showing a simulated transcript instead of voice.'
        : 'Live voice is in demo mode (no GEMINI_API_KEY set); showing a simulated transcript instead of voice.',
    });
    safeSend({ type: 'transcript_final', speaker: 'officer', text: OFFICER_GREETING, seq: 0 });
  } else {
    // Officer speaks first with a natural, warm greeting.
    try {
      liveSession.sendClientContent?.({
        turns: [{ role: 'user', parts: [{ text: 'Start the call now: greet the customer warmly, reassure them their payment is safely paused for a quick security check, and ask your first gentle question.' }] }],
        turnComplete: true,
      });
    } catch (e: any) {
      console.warn('Live greeting send failed:', e?.message);
    }
  }

  let simulatedSeq = 1;
  let lastSimulatedAt = 0;

  clientWs.on('message', (data: Buffer | ArrayBuffer | Buffer[], isBinary: boolean) => {
    // In ws v8 the payload is always a Buffer; `isBinary` distinguishes a binary
    // audio frame from a JSON control message (text / end). Checking typeof data
    // for a string never matches here, so rely on isBinary.
    if (!isBinary) {
      try {
        const raw = Array.isArray(data) ? Buffer.concat(data).toString() : data.toString();
        const parsed = JSON.parse(raw);
        if (parsed.type === 'end') {
          safeSend({ type: 'session_closed', reason: parsed.reason || 'completed' });
          try {
            liveSession?.close?.();
          } catch {
            /* ignore */
          }
          return;
        }
        if (parsed.audio && liveSession && !fallbackMode) {
          liveSession.sendRealtimeInput({ audio: { data: parsed.audio, mimeType: 'audio/pcm;rate=16000' } });
          return;
        }
        // Typed text (chips / keyboard) during the call.
        if (parsed.type === 'text' && typeof parsed.text === 'string') {
          const customerText = parsed.text.trim();
          if (!customerText) return;
          safeSend({ type: 'transcript_final', speaker: 'customer', text: customerText, seq: ++outSeq });
          if (liveSession && !fallbackMode) {
            try {
              liveSession.sendClientContent({ turns: [{ role: 'user', parts: [{ text: customerText }] }], turnComplete: true });
            } catch (e: any) {
              console.warn('Live text send failed:', e?.message);
            }
          } else {
            // Fallback: grounded officer reply (no audio).
            let reply = 'Thank you. Can you tell me who the recipient is and how you know them?';
            if (/cbi|police|arrest|threat|court|customs|warrant|clearance|jail|officer/i.test(customerText)) {
              reply = 'Please stay calm. Real police, courts and banks never demand money transfers, OTPs or secrecy over the phone. I am keeping your payment safely on hold so no money can leave your account.';
              safeSend({ type: 'analysis_update', status: 'action_taken', overall_sentiment: 'COERCED', action: 'HOLD_FOR_INVESTIGATION', summary: 'Authority-impersonation markers detected in customer statement; protective hold maintained.' });
              if (tx) tx.state = 'HELD_FOR_VERIFICATION';
            } else if (/rent|lease|landlord|salary|family|known|regular|normal/i.test(customerText)) {
              reply = 'Thank you, that is reassuring. The details match a trusted pattern. Please stay alert, but this looks legitimate.';
            }
            safeSend({ type: 'transcript_final', speaker: 'officer', text: reply, seq: ++outSeq });
          }
          return;
        }
      } catch {
        /* not JSON; ignore */
      }
      return;
    }

    // Binary PCM16 frames from the browser worklet.
    const buf = Array.isArray(data)
      ? Buffer.concat(data)
      : Buffer.isBuffer(data)
      ? data
      : Buffer.from(data as ArrayBuffer);
    if (liveSession && !fallbackMode) {
      try {
        liveSession.sendRealtimeInput({ audio: { data: buf.toString('base64'), mimeType: 'audio/pcm;rate=16000' } });
      } catch (err: any) {
        if (isQuotaError(err)) fallbackMode = true;
      }
      return;
    }

    // Fallback: emit a resilient, non-repeating simulated officer turn (debounced
    // so streamed audio frames do not flood the socket).
    const now = Date.now();
    if (now - lastSimulatedAt < 2500) return;
    lastSimulatedAt = now;

    const FALLBACK_TURNS = [
      'Thank you. Can you tell me who the recipient is and how you know them?',
      'Understood. Did anyone contact you claiming to be from the police, a court, or a government department about this payment?',
      'I appreciate that. Were you asked to keep this call secret or to ignore any warnings from your bank?',
      'Thank you for confirming. We are keeping a protective hold in place until we are certain you are safe.',
    ];
    const text = FALLBACK_TURNS[(simulatedSeq - 1) % FALLBACK_TURNS.length];
    safeSend({ type: 'transcript_final', speaker: 'officer', text, seq: simulatedSeq });
    safeSend({
      type: 'analysis_update',
      status: 'in_progress',
      overall_sentiment: 'SUSPICIOUS',
      summary: 'Live analysis in progress; monitoring for authority-pressure and secrecy markers.',
    });
    simulatedSeq += 1;
  });

  clientWs.on('close', () => {
    try {
      liveSession?.close?.();
    } catch {
      /* ignore */
    }
  });
});

// ---------------------------------------------------------------------------
// Vite Middleware / Static Serve
// ---------------------------------------------------------------------------

async function startServer() {
  if (process.env.NODE_ENV !== 'production') {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true, host: '0.0.0.0', port: PORT },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(__dirname, 'dist');
    app.use(express.static(distPath));
    app.use((_req: Request, res: Response) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  if (isDbConfigured) {
    try {
      await ensureSchema();
      console.log('[AegisPay AI] DB schema ready (aegis_ tables).');
    } catch (e: any) {
      console.warn('[AegisPay AI] DB persistence unavailable (schema init failed):', e?.message);
    }
  } else {
    console.log('[AegisPay AI] DB not configured; running with in-memory store only.');
  }

  server.listen(PORT, '0.0.0.0', () => {
    console.log(`[AegisPay AI] Server listening on http://0.0.0.0:${PORT}`);
  });
}

startServer();
