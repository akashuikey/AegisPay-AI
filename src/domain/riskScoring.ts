/**
 * Authoritative Risk Engine & Scenario Catalog for AegisPay AI.
 * Pure domain logic without browser or network dependencies, safely importable
 * by both backend (Node.js/Cloud Run) and client.
 */

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type RecommendedAction =
  | 'ALLOW'
  | 'WARN_CUSTOMER'
  | 'REQUIRE_VERIFICATION'
  | 'HOLD_FOR_INVESTIGATION';

export interface TriggeredRuleResponse {
  rule_id: string;
  rule_name: string;
  description: string;
  weight: number;
  severity: RiskLevel;
  evidence: string;
}

export interface RiskAssessmentResponse {
  id?: string | null;
  transaction_id?: string | null;
  risk_score: number;
  risk_level: RiskLevel;
  recommended_action: RecommendedAction;
  explanation: string;
  triggered_rules: TriggeredRuleResponse[];
  supporting_evidence: string[];
  missing_evidence: string[];
  created_at?: string | null;
  source?: 'backend' | 'demo_fallback';
}

export interface TransactionEvidenceInput {
  amount: number;
  currency?: string;
  payment_rail?: string;
  recipient_name?: string;
  recipient_identifier?: string;
  purpose?: string | null;
  customer_id?: string | null;
  historical_transaction_count?: number | null;
  avg_monthly_transfer_amount?: number | null;
  recent_fd_liquidation?: boolean | null;
  recent_fd_liquidation_amount?: number | null;
  is_first_time_recipient?: boolean | null;
  is_trusted_beneficiary?: boolean | null;
  recipient_account_age_days?: number | null;
  fan_in_count_24h?: number | null;
  fan_out_count_24h?: number | null;
  is_flagged_mule?: boolean | null;
  payee_name_mismatch?: boolean | null;
  routing_mismatch?: boolean | null;
  active_call_present?: boolean | null;
  screen_sharing_active?: boolean | null;
  voice_stress_detected?: boolean | null;
  coercive_language_detected?: boolean | null;
  guaranteed_return_claimed?: boolean | null;
  urgency_pressure_detected?: boolean | null;
  instruction_to_ignore_bank_warnings?: boolean | null;
  invoice_verified?: boolean | null;
}

export interface DemoScenarioDefinition {
  id: string;
  label: string;
  category: string;
  recipient: string;
  recipientIdentifier: string;
  amount: number;
  purpose: string;
  reference: string;
  known: boolean;
  summary: string;
  evidence: TransactionEvidenceInput;
}

/**
 * Authoritative demo fraud scenarios aligned with PRD & Risk Engine specifications.
 */
export const SCENARIO_CATALOG: Record<string, DemoScenarioDefinition> = {
  digital_arrest: {
    id: 'digital_arrest',
    label: '1. Digital Arrest / Authority Coercion',
    category: 'Coercion & Impersonation',
    recipient: 'Govt Security Clearance Account',
    recipientIdentifier: 'cbi.clearance@sbi',
    amount: 250000,
    purpose: 'Urgent court identity bond',
    reference: 'CBI-84920',
    known: false,
    summary:
      'Victim pressured by fake law enforcement into liquidating FD and transferring ₹2,50,000 while on active phone call and screen share.',
    evidence: {
      amount: 250000,
      currency: 'INR',
      payment_rail: 'RTGS',
      recipient_name: 'Govt Security Clearance Account',
      recipient_identifier: 'cbi.clearance@sbi',
      purpose: 'Urgent court identity bond',
      customer_id: 'cust_da_01',
      is_first_time_recipient: true,
      is_trusted_beneficiary: false,
      recent_fd_liquidation: true,
      recent_fd_liquidation_amount: 250000,
      active_call_present: true,
      screen_sharing_active: true,
      coercive_language_detected: true,
      urgency_pressure_detected: true,
      voice_stress_detected: true,
    },
  },
  investment_scam: {
    id: 'investment_scam',
    label: '2. High-Yield Investment Fraud',
    category: 'Investment Fraud',
    recipient: 'Apex Yield Asset Management',
    recipientIdentifier: 'apexyield@icici',
    amount: 85000,
    purpose: 'Crypto trading deposit',
    reference: 'INV-39210',
    known: false,
    summary:
      'Victim lured into high-yield scheme promising guaranteed returns, coached to dismiss bank warnings and act urgently.',
    evidence: {
      amount: 85000,
      currency: 'INR',
      payment_rail: 'IMPS',
      recipient_name: 'Apex Yield Asset Management',
      recipient_identifier: 'apexyield@icici',
      purpose: 'Crypto trading deposit',
      customer_id: 'cust_inv_01',
      is_first_time_recipient: true,
      is_trusted_beneficiary: false,
      guaranteed_return_claimed: true,
      urgency_pressure_detected: true,
      instruction_to_ignore_bank_warnings: true,
    },
  },
  fake_invoice: {
    id: 'fake_invoice',
    label: '3. Fake Invoice / Supplier Routing Mismatch',
    category: 'Invoice Scam',
    recipient: 'Starling Supplies Private Ltd',
    recipientIdentifier: '9928172635@kotak',
    amount: 32500,
    purpose: 'Invoice 48210 payment',
    reference: 'INV-48210',
    known: false,
    summary:
      'Tampered vendor invoice where beneficiary name or IFSC routing contradicts the established supplier profile ledger.',
    evidence: {
      amount: 32500,
      currency: 'INR',
      payment_rail: 'NEFT',
      recipient_name: 'Starling Supplies Private Ltd',
      recipient_identifier: '9928172635@kotak',
      purpose: 'Invoice 48210 payment',
      customer_id: 'cust_inv_02',
      is_first_time_recipient: true,
      payee_name_mismatch: true,
      routing_mismatch: true,
      invoice_verified: false,
    },
  },
  mule_network: {
    id: 'mule_network',
    label: '4. Mule Account Dispersal Velocity',
    category: 'Mule Detection',
    recipient: 'Ramesh K Mule',
    recipientIdentifier: 'fastcash99@upi',
    amount: 18000,
    purpose: 'Urgent cash transfer',
    reference: '',
    known: false,
    summary:
      'Beneficiary account matches consortium mule registry and exhibits extreme 24h rapid fan-in and fan-out turnover.',
    evidence: {
      amount: 18000,
      currency: 'INR',
      payment_rail: 'UPI',
      recipient_name: 'Ramesh K Mule',
      recipient_identifier: 'fastcash99@upi',
      purpose: 'Urgent cash transfer',
      customer_id: 'cust_mule_01',
      is_first_time_recipient: true,
      is_flagged_mule: true,
      fan_in_count_24h: 18,
      fan_out_count_24h: 15,
    },
  },
  legitimate_high_value: {
    id: 'legitimate_high_value',
    label: '5. Legitimate High-Value Lease Renewal',
    category: 'Normal Activity',
    recipient: 'Maple Grove Properties',
    recipientIdentifier: 'rent@maplegrove',
    amount: 250000,
    purpose: 'Annual lease renewal',
    reference: 'LEASE-2026',
    known: true,
    summary:
      'Routine high-value annual lease renewal to an established, trusted landlord with zero coercive or anomaly indicators.',
    evidence: {
      amount: 250000,
      currency: 'INR',
      payment_rail: 'RTGS',
      recipient_name: 'Maple Grove Properties',
      recipient_identifier: 'rent@maplegrove',
      purpose: 'Annual lease renewal',
      customer_id: 'cust_legit_01',
      is_first_time_recipient: false,
      is_trusted_beneficiary: true,
      recent_fd_liquidation: false,
      active_call_present: false,
      screen_sharing_active: false,
      coercive_language_detected: false,
      guaranteed_return_claimed: false,
      is_flagged_mule: false,
    },
  },
  ambiguous_payment: {
    id: 'ambiguous_payment',
    label: '6. Ambiguous / Missing Telemetry',
    category: 'Incomplete Context',
    recipient: 'Northstar Holdings',
    recipientIdentifier: 'northstar@axis',
    amount: 85000,
    purpose: 'Consulting deposit',
    reference: '',
    known: false,
    summary:
      'New payee with active phone call but unknown adverse history and missing transcripts. Verification required without auto-blocking.',
    evidence: {
      amount: 85000,
      currency: 'INR',
      payment_rail: 'UPI',
      recipient_name: 'Northstar Holdings',
      recipient_identifier: 'northstar@axis',
      purpose: 'Consulting deposit',
      customer_id: 'cust_ambi_01',
      is_first_time_recipient: true,
      active_call_present: true,
      screen_sharing_active: null,
      recent_fd_liquidation: null,
      coercive_language_detected: null,
      guaranteed_return_claimed: null,
      is_flagged_mule: null,
    },
  },
};

/**
 * Pure deterministic risk evaluation function matching backend risk rules.
 */
export function evaluateRiskLocally(evidence: TransactionEvidenceInput): RiskAssessmentResponse {
  const rules: TriggeredRuleResponse[] = [];
  const supporting: string[] = [];
  const missing: string[] = [];

  // Track missing evidence
  if (evidence.recent_fd_liquidation == null) missing.push('recent_fd_liquidation');
  if (evidence.is_first_time_recipient == null) missing.push('is_first_time_recipient');
  if (evidence.is_trusted_beneficiary == null) missing.push('is_trusted_beneficiary');
  if (evidence.is_flagged_mule == null) missing.push('mule_registry_record');
  if (evidence.fan_in_count_24h == null) missing.push('payee_fan_in_velocity');
  if (evidence.active_call_present == null) missing.push('active_call_telemetry');
  if (evidence.screen_sharing_active == null) missing.push('screen_sharing_telemetry');
  if (evidence.coercive_language_detected == null) missing.push('contextual_transcript_analysis');
  if (evidence.guaranteed_return_claimed == null) missing.push('investment_prospectus_claims');

  // Rule 1: High/Elevated Amount
  if (evidence.amount >= 100000) {
    rules.push({
      rule_id: 'RULE_HIGH_VALUE_ANOMALY',
      rule_name: 'High-Value Transfer Anomaly',
      description: 'Transfer amount meets or exceeds the elevated review threshold of ₹1,00,000.',
      weight: 15,
      severity: 'MEDIUM',
      evidence: `Transfer amount of ₹${evidence.amount.toLocaleString()} exceeds threshold of ₹1,00,000`,
    });
    supporting.push(`High-value payment amount: ₹${evidence.amount.toLocaleString()}`);
  } else if (evidence.amount >= 50000) {
    rules.push({
      rule_id: 'RULE_ELEVATED_AMOUNT',
      rule_name: 'Elevated Transfer Amount',
      description: 'Transfer amount meets or exceeds the monitoring threshold of ₹50,000.',
      weight: 10,
      severity: 'LOW',
      evidence: `Transfer amount of ₹${evidence.amount.toLocaleString()} meets monitoring threshold of ₹50,000`,
    });
    supporting.push(`Elevated payment amount: ₹${evidence.amount.toLocaleString()}`);
  }

  // Rule 2: First-time recipient
  if (evidence.is_first_time_recipient === true) {
    rules.push({
      rule_id: 'RULE_NEW_RECIPIENT',
      rule_name: 'First-Time Recipient',
      description: 'Payment is directed to a recipient with no prior payment history.',
      weight: 10,
      severity: 'LOW',
      evidence: `New payee '${evidence.recipient_name || 'Payee'}' has no previous payment history.`,
    });
    supporting.push(`Recipient '${evidence.recipient_name || 'Payee'}' is an unestablished beneficiary.`);
  }

  // Rule 3: Recent FD liquidation
  if (evidence.recent_fd_liquidation === true) {
    rules.push({
      rule_id: 'RULE_RECENT_FD_LIQUIDATION',
      rule_name: 'Recent Term Deposit Liquidation',
      description: 'Premature or sudden fixed deposit liquidation observed prior to transfer.',
      weight: 20,
      severity: 'HIGH',
      evidence: 'Customer liquidated fixed deposits shortly before initiating transfer.',
    });
    supporting.push('Unusual pre-transfer liquidity creation: recent FD liquidation.');
  }

  // Rule 4: Active call & screen sharing
  if (evidence.active_call_present === true && evidence.screen_sharing_active === true) {
    rules.push({
      rule_id: 'RULE_CALL_AND_SCREEN_SHARE',
      rule_name: 'Concurrent Active Call and Screen Sharing',
      description: 'Device telemetry indicates remote access or screen sharing concurrently with an active call.',
      weight: 25,
      severity: 'CRITICAL',
      evidence: 'Active phone call and remote screen sharing detected simultaneously.',
    });
    supporting.push('Concurrent active phone call and screen sharing detected on payer device.');
  } else if (evidence.active_call_present === true) {
    rules.push({
      rule_id: 'RULE_ACTIVE_CALL_PRESENT',
      rule_name: 'Active Phone Call Telemetry',
      description: 'Payer device is engaged in an active voice call while completing transaction.',
      weight: 10,
      severity: 'MEDIUM',
      evidence: 'Active voice call in progress during transaction form submission.',
    });
    supporting.push('Active phone call present during transaction (amber behavioral indicator).');
  }

  // Rule 5: Coercion / Authority pressure
  if (evidence.coercive_language_detected === true) {
    rules.push({
      rule_id: 'RULE_COERCION_AUTHORITY_PRESSURE',
      rule_name: 'Authority Impersonation / Coercive Language',
      description: 'Contextual indicators detect arrest threats, legal authority claims, or duress.',
      weight: 30,
      severity: 'CRITICAL',
      evidence: 'Law enforcement / regulatory authority impersonation and legal duress markers detected.',
    });
    supporting.push('Severe coercion marker: legal intimidation / digital arrest narrative detected.');
  }

  // Rule 6: Guaranteed return scheme
  if (evidence.guaranteed_return_claimed === true) {
    rules.push({
      rule_id: 'RULE_GUARANTEED_RETURN_SCHEME',
      rule_name: 'Guaranteed Return / High-Yield Claim',
      description: 'Contextual indicators detect unrealistic guaranteed financial returns.',
      weight: 25,
      severity: 'HIGH',
      evidence: 'Unrealistic guaranteed investment return or risk-free profit claim.',
    });
    supporting.push('High-yield investment fraud marker: promise of guaranteed or unrealistic returns.');
  }

  // Rule 7: Coached to ignore warnings
  if (evidence.instruction_to_ignore_bank_warnings === true) {
    rules.push({
      rule_id: 'RULE_COACHED_IGNORE_WARNINGS',
      rule_name: 'Instructions to Bypass Bank Safeguards',
      description: 'Customer was explicitly coached by a third party to dismiss bank warnings.',
      weight: 20,
      severity: 'HIGH',
      evidence: 'Third-party instruction to ignore bank warnings or provide false payment narrative.',
    });
    supporting.push('Adversarial coaching marker: sender instructed to dismiss bank warnings.');
  }

  // Rule 8: Payee mismatch
  if (evidence.payee_name_mismatch === true || evidence.routing_mismatch === true) {
    rules.push({
      rule_id: 'RULE_INVOICE_BENEFICIARY_MISMATCH',
      rule_name: 'Beneficiary Identity / Routing Mismatch',
      description: 'Beneficiary account details contradict historical vendor records or invoice.',
      weight: 35,
      severity: 'HIGH',
      evidence: 'Discrepancy detected in vendor ledger / routing profile.',
    });
    supporting.push('Invoice tampering / discrepancy detected.');
  }

  // Rule 9: Flagged mule & velocity
  if (evidence.is_flagged_mule === true) {
    rules.push({
      rule_id: 'RULE_FLAGGED_MULE_ACCOUNT',
      rule_name: 'Known Mule Account Registry Hit',
      description: 'Beneficiary account identifier is flagged in consortium fraud registry.',
      weight: 40,
      severity: 'CRITICAL',
      evidence: `Recipient identifier '${evidence.recipient_identifier || 'Unknown'}' flagged as mule account.`,
    });
    supporting.push('Consortium intelligence match: payee identified as mule.');
  }
  if ((evidence.fan_in_count_24h ?? 0) >= 10 || (evidence.fan_out_count_24h ?? 0) >= 10) {
    rules.push({
      rule_id: 'RULE_MULE_VELOCITY_FAN_IN_OUT',
      rule_name: 'Abnormal Payee Fan-In/Fan-Out Velocity',
      description: 'Beneficiary exhibits high multi-source rapid inflows followed by rapid dispersal.',
      weight: 30,
      severity: 'HIGH',
      evidence: `High 24h velocity: ${evidence.fan_in_count_24h || 0} unique senders, ${evidence.fan_out_count_24h || 0} withdrawals.`,
    });
    supporting.push(`Mule velocity pattern: ${evidence.fan_in_count_24h || 0} senders, ${evidence.fan_out_count_24h || 0} withdrawals in 24h.`);
  }

  // Rule 10: Voice stress (advisory)
  if (evidence.voice_stress_detected === true) {
    rules.push({
      rule_id: 'RULE_VOICE_STRESS_ADVISORY',
      rule_name: 'Acoustic Voice Stress Indicator',
      description: 'Vocal tension or stress markers detected during customer interaction.',
      weight: 5,
      severity: 'LOW',
      evidence: 'Vocal acoustic analysis indicates elevated stress (advisory signal only, not standalone fraud).',
    });
    supporting.push('Vocal stress telemetry detected (advisory only; not proof of fraud).');
  }

  // Rule 11: Trusted recipient mitigation
  const hasCoercion = evidence.coercive_language_detected === true;
  if (evidence.is_trusted_beneficiary === true && evidence.is_first_time_recipient === false && !hasCoercion) {
    rules.push({
      rule_id: 'RULE_ESTABLISHED_BENEFICIARY_MITIGATION',
      rule_name: 'Established Trusted Beneficiary Mitigation',
      description: 'Recipient is an established, trusted beneficiary with consistent historical interaction.',
      weight: -25,
      severity: 'LOW',
      evidence: `Beneficiary '${evidence.recipient_name || 'Payee'}' is in customer trusted list with confirmed history.`,
    });
    supporting.push(`Trusted relationship: '${evidence.recipient_name || 'Payee'}' is an established beneficiary with no coercive indicators.`);
  } else if (evidence.is_trusted_beneficiary === true && hasCoercion) {
    supporting.push('Policy Guardrail Enforced: Trusted-recipient status bypassed due to presence of active coercion indicators.');
  }

  const rawScore = rules.reduce((acc, r) => acc + r.weight, 0);
  const boundedScore = Math.max(0, Math.min(100, rawScore));

  let riskLevel: RiskLevel = 'LOW';
  let recommendedAction: RecommendedAction = 'ALLOW';
  let explanation = `Transaction evaluated within normal parameters (Score ${boundedScore}/100). Simulated settlement permitted.`;

  if (boundedScore >= 80) {
    riskLevel = 'CRITICAL';
    recommendedAction = 'HOLD_FOR_INVESTIGATION';
    explanation = `Critical fraud/coercion risk detected (Score ${boundedScore}/100). Simulated pre-settlement hold recommended pending formal investigation.`;
  } else if (boundedScore >= 50) {
    riskLevel = 'HIGH';
    recommendedAction = 'HOLD_FOR_INVESTIGATION';
    explanation = `High fraud risk identified (Score ${boundedScore}/100). Simulated hold recommended pending verification of beneficiary or payment legitimacy.`;
  } else if (boundedScore >= 25) {
    riskLevel = 'MEDIUM';
    recommendedAction = 'REQUIRE_VERIFICATION';
    explanation = `Elevated risk signals detected (Score ${boundedScore}/100). Customer interaction or targeted confirmation required before simulated release.`;
  }

  return {
    risk_score: boundedScore,
    risk_level: riskLevel,
    recommended_action: recommendedAction,
    explanation,
    triggered_rules: rules,
    supporting_evidence: supporting,
    missing_evidence: missing,
    source: 'demo_fallback',
  };
}
