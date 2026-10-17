/**
 * Operator authentication client and the shared authenticated fetch wrapper.
 *
 * The access token is a short-lived bearer JWT issued by the backend. It is
 * held in localStorage so a page refresh keeps the operator signed in; this is
 * a deliberate prototype trade-off (localStorage is XSS-readable) paired with a
 * short token lifetime. Never place any longer-lived secret here.
 */

import { config } from '../config';

const TOKEN_STORAGE_KEY = 'aegis_access_token';
const UNAUTHORIZED_EVENT = 'aegis:unauthorized';

export interface OperatorIdentity {
  id: string;
  username: string;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  operator: OperatorIdentity;
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    /* ignore storage failures (private mode); session stays in-memory only */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** Subscribe to forced-logout events (fired when the server rejects the token). */
export function onUnauthorized(handler: () => void): () => void {
  window.addEventListener(UNAUTHORIZED_EVENT, handler);
  return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
}

/**
 * Authenticated fetch: injects the bearer token and, on a 401, clears the
 * stored token and broadcasts an unauthorized event so the UI returns to login.
 */
export async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers ?? {});
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, { ...init, headers });
  if (response.status === 401) {
    clearToken();
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  return response;
}

/** Authenticate an operator; on success the token is stored for subsequent calls. */
export async function loginApi(username: string, password: string): Promise<OperatorIdentity> {
  const url = `${config.apiBaseUrl}/api/v1/auth/login`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('Invalid username or password.');
    }
    const text = await response.text();
    throw new Error(`Login failed (${response.status}): ${text}`);
  }

  const data = (await response.json()) as TokenResponse;
  setToken(data.access_token);
  return data.operator;
}

/** Fetch the currently authenticated operator, or null if not signed in. */
export async function fetchCurrentOperatorApi(): Promise<OperatorIdentity | null> {
  if (!getToken()) {
    return null;
  }
  const url = `${config.apiBaseUrl}/api/v1/auth/me`;
  const response = await apiFetch(url);
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as OperatorIdentity;
}

export function logout(): void {
  clearToken();
}
