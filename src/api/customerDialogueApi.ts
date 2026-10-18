/**
 * Dynamic Gemini-Powered Simulated Voice and Chat API Client (Option A).
 *
 * Exposes typed request/response bindings for simulated call session lifecycle,
 * dynamic multi-turn forensic inquiry, and speech/chat turns.
 */

import { config } from '../config';
import { apiFetch } from './authApi';

export type DialogueChannel = 'VOICE_SIMULATED' | 'CHAT_SIMULATED';

export type CallSessionStatus =
  | 'INITIATED'
  | 'RINGING'
  | 'CONNECTED'
  | 'COMPLETED'
  | 'DECLINED'
  | 'TIMED_OUT'
  | 'FAILED'
  | 'CANCELLED';

export type CallSessionDirection = 'OUTBOUND_SIMULATED' | 'INBOUND_SIMULATED';

export interface CustomerDialogueTurnResponse {
  turn_index: number;
  role: string;
  content: string;
  evidence_references: string[];
  risk_sentiment?: string | null;
  confidence_score?: number | null;
  internal_observations: string[];
  uncertainty_notes: string[];
  suggested_action: string;
  is_terminal_turn: boolean;
  coercion_cues: string[];
  created_at?: string | null;
}

export interface CallSessionResponse {
  id: string;
  transaction_id: string;
  conversation_id: string;
  channel: DialogueChannel;
  status: CallSessionStatus;
  direction: CallSessionDirection;
  attempt_number: number;
  customer_phone_masked?: string | null;
  coercion_analysis_id?: string | null;
  started_at: string;
  connected_at?: string | null;
  ended_at?: string | null;
  duration_seconds?: number | null;
  failure_reason?: string | null;
  turns: CustomerDialogueTurnResponse[];
  created_at: string;
  updated_at: string;
}

export interface InitiateCallSessionRequest {
  channel?: DialogueChannel;
  idempotency_key?: string;
  correlation_id?: string;
}

export interface SubmitDialogueTurnRequest {
  customer_message: string;
  source?: 'speech' | 'typed';
  client_turn_id?: string;
  correlation_id?: string;
}

export interface DeclineCallSessionRequest {
  reason?: string;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data?.error?.message ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

/** Initiate an outbound simulated phone call or chat session for a transaction. */
export async function initiateCallSessionApi(
  transactionId: string,
  payload: InitiateCallSessionRequest = {}
): Promise<CallSessionResponse> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/calls`;
  const response = await apiFetch(url, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as CallSessionResponse;
}

/** Answer an incoming simulated call, moving status from RINGING to CONNECTED. */
export async function connectCallSessionApi(callId: string): Promise<CallSessionResponse> {
  const url = `${config.apiBaseUrl}/api/v1/calls/${callId}/connect`;
  const response = await apiFetch(url, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as CallSessionResponse;
}

/** Submit a customer voice or typed turn to Gemini, receiving dynamic inquiry response. */
export async function submitDialogueTurnApi(
  callId: string,
  payload: SubmitDialogueTurnRequest
): Promise<CallSessionResponse> {
  const url = `${config.apiBaseUrl}/api/v1/calls/${callId}/turns`;
  const response = await apiFetch(url, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as CallSessionResponse;
}

/** Complete a call session when verification inquiry is finished. */
export async function completeCallSessionApi(callId: string): Promise<CallSessionResponse> {
  const url = `${config.apiBaseUrl}/api/v1/calls/${callId}/complete`;
  const response = await apiFetch(url, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as CallSessionResponse;
}

/** Decline or reject an incoming simulated call. */
export async function declineCallSessionApi(
  callId: string,
  payload?: DeclineCallSessionRequest
): Promise<CallSessionResponse> {
  const url = `${config.apiBaseUrl}/api/v1/calls/${callId}/decline`;
  const response = await apiFetch(url, {
    method: 'POST',
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as CallSessionResponse;
}

/** Retrieve the most recent call session for a transaction (returns null if none). */
export async function getLatestCallSessionApi(
  transactionId: string
): Promise<CallSessionResponse | null> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/calls/latest`;
  const response = await apiFetch(url);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as CallSessionResponse;
}

/** Retrieve all call sessions for a transaction in chronological order. */
export async function listCallSessionsApi(
  transactionId: string
): Promise<CallSessionResponse[]> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/calls`;
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as CallSessionResponse[];
}

/** Retrieve details of a specific call session by ID. */
export async function getCallSessionApi(callId: string): Promise<CallSessionResponse> {
  const url = `${config.apiBaseUrl}/api/v1/calls/${callId}`;
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as CallSessionResponse;
}

