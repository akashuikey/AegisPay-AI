/**
 * Simulated Customer Verification Panel (P2-A5).
 *
 * Drives the simulated OTP verification flow for a verification-required
 * transaction and shows the resulting policy re-evaluation. The mechanism is a
 * SIMULATED challenge — clearly labeled, not a real bank authentication channel.
 * Verification does not guarantee approval: the deterministic policy decides.
 */

import { useCallback, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, KeyRound, RefreshCw, ShieldCheck } from 'lucide-react';
import {
  ChallengeResponse,
  SubmitVerificationResponse,
  createChallengeApi,
  submitVerificationApi,
} from '../api/verificationApi';

interface VerificationPanelProps {
  transactionId: string;
  onResolved?: () => void;
}

type Phase = 'idle' | 'creating' | 'pending' | 'submitting' | 'resolved' | 'error';

export function VerificationPanel({ transactionId, onResolved }: VerificationPanelProps) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [challenge, setChallenge] = useState<ChallengeResponse | null>(null);
  const [result, setResult] = useState<SubmitVerificationResponse | null>(null);
  const [otp, setOtp] = useState('');
  const [error, setError] = useState<string | null>(null);
  const createInFlight = useRef(false);
  const submitInFlight = useRef(false);

  const handleCreate = useCallback(async () => {
    if (createInFlight.current) return;
    createInFlight.current = true;
    setPhase('creating');
    setError(null);
    setResult(null);
    try {
      const ch = await createChallengeApi(transactionId);
      setChallenge(ch);
      setPhase('pending');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create verification challenge');
      setPhase('error');
    } finally {
      createInFlight.current = false;
    }
  }, [transactionId]);

  const handleSubmit = useCallback(async () => {
    if (submitInFlight.current || !challenge) return;
    submitInFlight.current = true;
    setPhase('submitting');
    setError(null);
    try {
      const res = await submitVerificationApi(
        challenge.challenge_id,
        challenge.customer_session_token,
        otp.trim()
      );
      setResult(res);
      setOtp('');
      if (res.result === 'FAILED' && res.status === 'PENDING') {
        // Still pending: allow another attempt.
        setChallenge({ ...challenge, attempts_remaining: res.attempts_remaining });
        setPhase('pending');
      } else {
        setPhase('resolved');
        onResolved?.();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Verification submission failed');
      setPhase('pending');
    } finally {
      submitInFlight.current = false;
    }
  }, [challenge, otp, onResolved]);

  return (
    <section className="drawer-section" data-testid="verification-panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
          <ShieldCheck size={16} color="#0284c7" />
          Customer Verification
        </h3>
        {challenge && (
          <span className="pill small mono" data-testid="verification-status">
            {result?.status ?? challenge.status}
          </span>
        )}
      </div>
      <p style={{ margin: '4px 0 12px 0', fontSize: 12, color: '#6b7280' }}>
        Simulated challenge — not a real bank authentication channel. Verification does not
        guarantee approval; the deterministic policy decides the outcome.
      </p>

      {error && (
        <div
          role="alert"
          data-testid="verification-error"
          style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#991b1b',
            borderRadius: 6,
            padding: '8px 10px',
            fontSize: 12.5,
            marginBottom: 10,
          }}
        >
          {error}
        </div>
      )}

      {phase === 'idle' && (
        <button
          className="button primary small"
          onClick={() => void handleCreate()}
          data-testid="button-create-challenge"
        >
          <KeyRound size={12} /> Start simulated verification
        </button>
      )}

      {phase === 'creating' && (
        <div data-testid="verification-creating" style={{ fontSize: 12, color: '#6b7280' }}>
          <RefreshCw size={14} className="spin" /> Creating challenge…
        </div>
      )}

      {(phase === 'pending' || phase === 'submitting') && challenge && (
        <div data-testid="verification-pending">
          {challenge.dev_otp && (
            <div
              data-testid="verification-dev-otp"
              style={{
                background: '#fffbeb',
                border: '1px dashed #fde68a',
                borderRadius: 6,
                padding: '8px 10px',
                fontSize: 12,
                color: '#92400e',
                marginBottom: 10,
              }}
            >
              <strong>DEV / SIMULATED OTP:</strong> <span className="mono">{challenge.dev_otp}</span>{' '}
              — development display only; not delivered over a real channel.
            </div>
          )}
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 6 }}>
            Attempts remaining:{' '}
            <strong data-testid="verification-attempts">{challenge.attempts_remaining}</strong>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="field-input"
              inputMode="numeric"
              placeholder="Enter OTP"
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
              disabled={phase === 'submitting'}
              data-testid="input-otp"
              style={{ flex: 1 }}
              aria-label="Verification OTP"
            />
            <button
              className="button primary small"
              onClick={() => void handleSubmit()}
              disabled={phase === 'submitting' || otp.trim().length < 4}
              data-testid="button-submit-otp"
            >
              {phase === 'submitting' ? (
                <>
                  <RefreshCw size={12} className="spin" /> Verifying…
                </>
              ) : (
                'Submit'
              )}
            </button>
          </div>
          {result?.result === 'FAILED' && (
            <p
              data-testid="verification-failed-note"
              style={{ margin: '8px 0 0 0', fontSize: 12, color: '#b45309' }}
            >
              Incorrect code. {result.attempts_remaining} attempt(s) remaining.
            </p>
          )}
        </div>
      )}

      {phase === 'resolved' && result && (
        <div data-testid="verification-resolved">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 13,
              fontWeight: 600,
              color: result.result === 'SUCCEEDED' ? '#166534' : '#991b1b',
            }}
          >
            {result.result === 'SUCCEEDED' ? (
              <CheckCircle2 size={15} />
            ) : (
              <AlertTriangle size={15} />
            )}
            Verification {result.result.toLowerCase()}
          </div>
          {result.decision && (
            <div style={{ marginTop: 8, fontSize: 12.5, color: '#334155' }}>
              <div>
                Policy outcome:{' '}
                <strong data-testid="verification-decision-action">
                  {result.decision.action}
                </strong>{' '}
                → <span className="mono">{result.transaction_state}</span>
              </div>
              <p style={{ margin: '6px 0 0 0' }}>{result.decision.explanation}</p>
              <p style={{ margin: '8px 0 0 0', fontSize: 10.5, color: '#94a3b8' }}>
                <strong>Simulated outcome.</strong> Verification does not guarantee approval; this
                is a simulated state, not a real bank transfer.
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
