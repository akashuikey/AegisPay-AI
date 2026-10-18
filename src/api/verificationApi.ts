/**
 * Simulated customer verification API client (P2-A5).
 *
 * Challenge creation and status are operator-console calls and go through the
 * authenticated apiFetch (operator bearer). Submission is a DISTINCT customer
 * verification session: it is authorized by the server-issued customer session
 * token (not the operator token), so it uses a dedicated request that carries
 * that token on the Authorization header and does not trigger operator logout.
 */

import { config } from '../config';
import { apiFetch } from './authApi';
import type { DecisionResponse } from './decisionApi';

export interface ChallengeResponse {
  challenge_id: string;
  transaction_id: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  attempts_remaining: number;
  expires_at: string;
  customer_session_token: string;
  session_expires_in: number;
  simulated: boolean;
  dev_otp?: string | null;
}

export interface SubmitVerificationResponse {
  challenge_id: string;
  transaction_id: string;
  result: 'SUCCEEDED' | 'FAILED' | 'EXHAUSTED';
  status: string;
  attempts_remaining: number;
  transaction_state: string;
  decision: DecisionResponse | null;
  simulated: boolean;
}

export interface VerificationStatusResponse {
  challenge_id: string;
  transaction_id: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  attempts_remaining: number;
  expires_at: string;
  verified_at?: string | null;
  decision_id?: string | null;
  transaction_state: string;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data?.error?.message ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

/** Operator: create or retrieve the active simulated verification challenge. */
export async function createChallengeApi(transactionId: string): Promise<ChallengeResponse> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/verification`;
  const response = await apiFetch(url, { method: 'POST', body: JSON.stringify({}) });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as ChallengeResponse;
}

/** Operator: fetch challenge status. */
export async function getChallengeStatusApi(
  transactionId: string,
  challengeId: string
): Promise<VerificationStatusResponse> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/verification/${challengeId}`;
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as VerificationStatusResponse;
}

/**
 * Customer verification session: submit the simulated OTP using the session token
 * issued at challenge creation. This is a distinct identity context from the
 * operator session and intentionally does not use the operator bearer token.
 */
export async function submitVerificationApi(
  challengeId: string,
  customerSessionToken: string,
  otp: string
): Promise<SubmitVerificationResponse> {
  const url = `${config.apiBaseUrl}/api/v1/verification/${challengeId}/submit`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${customerSessionToken}`,
    },
    body: JSON.stringify({ otp }),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as SubmitVerificationResponse;
}
