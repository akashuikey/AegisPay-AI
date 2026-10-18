/**
 * Automated Fraud Response Orchestration & Customer Intervention API client (P2-A7).
 *
 * Provides typed methods for executing policy-authorized responses,
 * retrieving response audit history, and accessing customer intervention status.
 */

import { config } from '../config';
import { apiFetch } from './authApi';

export type ResponseType =
  | 'ALLOW_SETTLED'
  | 'VERIFICATION_REQUIRED'
  | 'HOLD_PROTECTIVE'
  | 'BLOCK_SAFETY';

export type CustomerActionRequired = 'NONE' | 'VERIFY_OTP' | 'CONTACT_BANK';

export type NotificationChannel =
  | 'IN_APP_SIMULATED'
  | 'SMS_SIMULATED'
  | 'WHATSAPP_SIMULATED'
  | 'EMAIL_SIMULATED';

export type NotificationDeliveryStatus =
  | 'DELIVERED_SIMULATED'
  | 'FAILED_SIMULATED'
  | 'SUPPRESSED_SIMULATED';

export interface NotificationResponse {
  id: string;
  channel: string;
  recipient_masked: string;
  subject?: string | null;
  message_body: string;
  delivery_status: string;
  failure_reason?: string | null;
  created_at: string;
  delivered_at?: string | null;
}

export interface CustomerInterventionResponse {
  transaction_id: string;
  response_type: ResponseType;
  headline: string;
  customer_message: string;
  customer_action_required: CustomerActionRequired;
  next_steps: string[];
  simulated_payment_status: string;
  notification_delivered: boolean;
  notification_channel: string;
  is_simulated: boolean;
}

export interface FraudResponseDetails {
  id: string;
  transaction_id: string;
  decision_id?: string | null;
  response_type: ResponseType;
  action: string;
  processing_status: string;
  from_state: string;
  to_state: string;
  headline: string;
  customer_message: string;
  customer_action_required: CustomerActionRequired;
  next_steps: string[];
  idempotency_key?: string | null;
  created_at: string;
  notifications: NotificationResponse[];
  is_simulated: boolean;
}

export interface ExecuteResponseRequest {
  idempotency_key?: string;
  channel?: NotificationChannel;
  simulate_notification_failure?: boolean;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data?.error?.message ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

/** Execute automated response orchestration for a transaction (Operator authenticated). */
export async function executeResponseApi(
  transactionId: string,
  request?: ExecuteResponseRequest
): Promise<FraudResponseDetails> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/respond`;
  const response = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request ?? {}),
  });

  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

/** Fetch latest automated response details for a transaction. */
export async function getLatestResponseApi(
  transactionId: string
): Promise<FraudResponseDetails | null> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/responses/latest`;
  const response = await apiFetch(url);

  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

/** List all automated responses executed for a transaction in chronological order. */
export async function listResponsesApi(
  transactionId: string
): Promise<FraudResponseDetails[]> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/responses`;
  const response = await apiFetch(url);

  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

/** Fetch customer-safe intervention status for a transaction. */
export async function getCustomerInterventionApi(
  transactionId: string,
  customerToken?: string
): Promise<CustomerInterventionResponse> {
  const url = `${config.apiBaseUrl}/api/v1/transactions/${transactionId}/intervention`;
  const headers: Record<string, string> = {};
  if (customerToken) {
    headers['Authorization'] = `Bearer ${customerToken}`;
  }
  const response = await apiFetch(url, { headers });

  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

