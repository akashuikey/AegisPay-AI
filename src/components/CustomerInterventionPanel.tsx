/**
 * Automated Fraud Response & Customer Intervention Panel (P2-A7).
 *
 * Orchestrates policy-authorized simulated responses, displays customer-safe
 * intervention headlines and non-accusatory advice, and monitors simulated
 * notification delivery across in-app, SMS, WhatsApp, and email channels.
 *
 * ALL RESPONSES AND NOTIFICATIONS REMAIN STRICTLY SIMULATED.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  BellRing,
  CheckCircle2,
  Info,
  KeyRound,
  RefreshCw,
  Send,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import {
  CustomerActionRequired,
  ExecuteResponseRequest,
  FraudResponseDetails,
  NotificationChannel,
  ResponseType,
  executeResponseApi,
  getLatestResponseApi,
} from '../api/responseApi';

interface CustomerInterventionPanelProps {
  transactionId: string;
  transactionRecipient?: string;
  transactionAmount?: number;
  onResponseExecuted?: () => void;
}

const RESPONSE_STYLES: Record<
  ResponseType,
  { label: string; tone: string; icon: typeof CheckCircle2; bg: string; border: string; color: string }
> = {
  ALLOW_SETTLED: {
    label: 'ALLOW & SETTLE (SIMULATED)',
    tone: 'green',
    icon: CheckCircle2,
    bg: '#ecfdf5',
    border: '#a7f3d0',
    color: '#065f46',
  },
  VERIFICATION_REQUIRED: {
    label: 'VERIFICATION REQUIRED',
    tone: 'amber',
    icon: KeyRound,
    bg: '#fffbeb',
    border: '#fde68a',
    color: '#92400e',
  },
  HOLD_PROTECTIVE: {
    label: 'PROTECTIVE HOLD',
    tone: 'orange',
    icon: ShieldAlert,
    bg: '#fff7ed',
    border: '#fed7aa',
    color: '#9a3412',
  },
  BLOCK_SAFETY: {
    label: 'SAFETY BLOCK (CANCELLED)',
    tone: 'red',
    icon: AlertOctagon,
    bg: '#fef2f2',
    border: '#fecaca',
    color: '#991b1b',
  },
};

const ACTION_LABELS: Record<CustomerActionRequired, { label: string; color: string }> = {
  NONE: { label: 'None Required', color: '#059669' },
  VERIFY_OTP: { label: 'OTP Verification Required', color: '#d97706' },
  CONTACT_BANK: { label: 'Contact Bank Official Channels', color: '#dc2626' },
};

export function CustomerInterventionPanel({
  transactionId,
  onResponseExecuted,
}: CustomerInterventionPanelProps) {
  const [response, setResponse] = useState<FraudResponseDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [channel, setChannel] = useState<NotificationChannel>('IN_APP_SIMULATED');
  const [simulateFailure, setSimulateFailure] = useState(false);
  const isMounted = useRef(true);

  const loadLatest = useCallback(async () => {
    if (!transactionId || transactionId.startsWith('AST-')) return;
    setLoading(true);
    setError(null);
    try {
      const latest = await getLatestResponseApi(transactionId);
      if (isMounted.current) {
        setResponse(latest);
      }
    } catch (err: unknown) {
      if (isMounted.current) {
        setError(err instanceof Error ? err.message : 'Failed to load response status');
      }
    } finally {
      if (isMounted.current) {
        setLoading(false);
      }
    }
  }, [transactionId]);

  useEffect(() => {
    isMounted.current = true;
    void loadLatest();
    return () => {
      isMounted.current = false;
    };
  }, [loadLatest]);

  const handleExecute = useCallback(async () => {
    if (!transactionId || transactionId.startsWith('AST-') || executing) return;
    setExecuting(true);
    setError(null);
    try {
      const payload: ExecuteResponseRequest = {
        channel,
        simulate_notification_failure: simulateFailure,
      };
      const result = await executeResponseApi(transactionId, payload);
      setResponse(result);
      onResponseExecuted?.();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to execute response');
    } finally {
      setExecuting(false);
    }
  }, [transactionId, channel, simulateFailure, executing, onResponseExecuted]);

  const styleConfig = response ? RESPONSE_STYLES[response.response_type] : null;
  const StyleIcon = styleConfig ? styleConfig.icon : BellRing;

  return (
    <section className="drawer-section" data-testid="customer-intervention-panel">
      {/* Panel Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0, fontSize: 14 }}>
          <BellRing size={17} color="#2563eb" />
          Automated Response & Customer Intervention
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {response && (
            <span
              className="pill mono small"
              style={{
                backgroundColor: styleConfig?.bg,
                borderColor: styleConfig?.border,
                color: styleConfig?.color,
                fontWeight: 600,
              }}
              data-testid="response-type-pill"
            >
              {styleConfig?.label}
            </span>
          )}
          <button
            className="button small"
            onClick={loadLatest}
            disabled={loading}
            title="Refresh response status"
            aria-label="Refresh"
            style={{ padding: '4px 8px' }}
          >
            <RefreshCw size={12} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      <p style={{ margin: '0 0 14px 0', fontSize: 12, color: '#64748b', lineHeight: 1.5 }}>
        Coordinates deterministic policy enforcement with automated, customer-safe communication.
        All payment outcomes and customer alerts are strictly simulated.
      </p>

      {/* Error Message */}
      {error && (
        <div
          className="notice"
          style={{ backgroundColor: '#fef2f2', borderColor: '#fca5a5', color: '#991b1b', marginBottom: 14 }}
          data-testid="response-error-notice"
        >
          <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
          <div>
            <strong>Error: </strong>
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Lifecycle & Progression Timeline */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 6,
          backgroundColor: '#f8fafc',
          padding: '10px 12px',
          borderRadius: 8,
          border: '1px solid #e2e8f0',
          marginBottom: 16,
        }}
        data-testid="progression-timeline"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>1. Assess</span>
          <span style={{ fontSize: 11, color: '#0f172a', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
            <CheckCircle2 size={12} color="#059669" /> Risk Done
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>2. Policy</span>
          <span style={{ fontSize: 11, color: '#0f172a', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
            <CheckCircle2 size={12} color="#059669" /> Decided
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>3. Response</span>
          <span style={{ fontSize: 11, color: '#0f172a', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
            {response ? (
              <CheckCircle2 size={12} color="#059669" />
            ) : (
              <span style={{ width: 12, height: 12, borderRadius: '50%', border: '2px solid #94a3b8' }} />
            )}
            {response ? 'Executed' : 'Pending'}
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>4. Alert</span>
          <span style={{ fontSize: 11, color: '#0f172a', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
            {response?.notifications?.some((n) => n.delivery_status === 'DELIVERED_SIMULATED') ? (
              <CheckCircle2 size={12} color="#059669" />
            ) : response?.notifications?.some((n) => n.delivery_status === 'FAILED_SIMULATED') ? (
              <AlertTriangle size={12} color="#dc2626" />
            ) : (
              <span style={{ width: 12, height: 12, borderRadius: '50%', border: '2px solid #94a3b8' }} />
            )}
            {response?.notifications?.length ? (response.notifications[0].delivery_status === 'FAILED_SIMULATED' ? 'Failed' : 'Dispatched') : 'Queued'}
          </span>
        </div>
      </div>

      {/* Response Details View */}
      {response ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Headline Banner */}
          <div
            style={{
              padding: 12,
              borderRadius: 8,
              border: `1px solid ${styleConfig?.border}`,
              backgroundColor: styleConfig?.bg,
            }}
            data-testid="customer-intervention-card"
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <StyleIcon size={18} color={styleConfig?.color} />
              <strong style={{ fontSize: 13, color: styleConfig?.color }}>{response.headline}</strong>
            </div>

            <p style={{ margin: '0 0 10px 0', fontSize: 12, color: '#1e293b', lineHeight: 1.5 }} data-testid="customer-message-text">
              {response.customer_message}
            </p>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', fontSize: 11 }}>
              <div>
                <span style={{ color: '#64748b' }}>Action Required: </span>
                <strong style={{ color: ACTION_LABELS[response.customer_action_required]?.color || '#0f172a' }} data-testid="customer-action-badge">
                  {ACTION_LABELS[response.customer_action_required]?.label || response.customer_action_required}
                </strong>
              </div>
              <div>
                <span style={{ color: '#64748b' }}>State Transition: </span>
                <code style={{ fontSize: 10, padding: '1px 5px', borderRadius: 4, backgroundColor: '#ffffff', border: '1px solid #cbd5e1' }}>
                  {response.from_state} → {response.to_state}
                </code>
              </div>
            </div>
          </div>

          {/* Customer Recommended Next Steps */}
          {response.next_steps && response.next_steps.length > 0 && (
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: 8,
                padding: '10px 14px',
              }}
              data-testid="customer-next-steps"
            >
              <div style={{ fontSize: 11, fontWeight: 700, color: '#334155', marginBottom: 6, textTransform: 'uppercase' }}>
                Customer Next Steps & Safety Guidance
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: '#475569', lineHeight: 1.6 }}>
                {response.next_steps.map((step, idx) => (
                  <li key={idx}>{step}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Simulated Notification Record */}
          <div
            style={{
              backgroundColor: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              padding: '10px 14px',
            }}
            data-testid="notification-delivery-card"
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#334155', textTransform: 'uppercase' }}>
                Simulated Notification Dispatch
              </span>
              {response.notifications && response.notifications.length > 0 && (
                <span
                  className="pill small mono"
                  style={{
                    backgroundColor:
                      response.notifications[0].delivery_status === 'DELIVERED_SIMULATED' ? '#ecfdf5' : '#fef2f2',
                    color:
                      response.notifications[0].delivery_status === 'DELIVERED_SIMULATED' ? '#065f46' : '#991b1b',
                    borderColor:
                      response.notifications[0].delivery_status === 'DELIVERED_SIMULATED' ? '#a7f3d0' : '#fecaca',
                  }}
                  data-testid="notification-status-badge"
                >
                  {response.notifications[0].delivery_status}
                </span>
              )}
            </div>

            {response.notifications && response.notifications.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#64748b' }}>Channel</span>
                  <strong className="mono">{response.notifications[0].channel}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#64748b' }}>Recipient</span>
                  <span className="mono" data-testid="notification-recipient">{response.notifications[0].recipient_masked}</span>
                </div>
                {response.notifications[0].delivered_at && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#64748b' }}>Delivered At</span>
                    <span className="mono" style={{ fontSize: 11 }}>{new Date(response.notifications[0].delivered_at).toLocaleTimeString()}</span>
                  </div>
                )}
                {response.notifications[0].failure_reason && (
                  <div
                    style={{
                      marginTop: 4,
                      padding: '4px 8px',
                      backgroundColor: '#fee2e2',
                      borderRadius: 4,
                      color: '#b91c1c',
                      fontSize: 11,
                    }}
                    data-testid="notification-failure-reason"
                  >
                    Failure Reason: {response.notifications[0].failure_reason}
                  </div>
                )}
              </div>
            ) : (
              <p style={{ margin: 0, fontSize: 12, color: '#94a3b8' }}>No notification records attached.</p>
            )}

            <div style={{ marginTop: 8, fontSize: 11, color: '#64748b', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Info size={13} style={{ flex: 'none' }} />
              <span>Safety isolation active: Notification status does not compromise hold or block decisions.</span>
            </div>
          </div>
        </div>
      ) : (
        <div
          style={{
            padding: 16,
            textAlign: 'center',
            backgroundColor: '#f8fafc',
            border: '1px dashed #cbd5e1',
            borderRadius: 8,
            marginBottom: 14,
          }}
          data-testid="no-response-placeholder"
        >
          <Send size={24} color="#94a3b8" style={{ margin: '0 auto 8px' }} />
          <p style={{ margin: 0, fontSize: 13, fontWeight: 500, color: '#334155' }}>
            No automated response executed yet
          </p>
          <p style={{ margin: '4px 0 0', fontSize: 11, color: '#64748b' }}>
            Click below to execute the policy-authorized automated response and dispatch simulated customer alert.
          </p>
        </div>
      )}

      {/* Operator Execution Controls */}
      <div
        style={{
          marginTop: 14,
          padding: 12,
          backgroundColor: '#ffffff',
          border: '1px solid #e2e8f0',
          borderRadius: 8,
        }}
        data-testid="operator-response-controls"
      >
        <div style={{ fontSize: 11, fontWeight: 700, color: '#334155', marginBottom: 8, textTransform: 'uppercase' }}>
          Response Dispatch Controls
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
          <div>
            <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>
              Dispatch Channel
            </label>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value as NotificationChannel)}
              style={{
                width: '100%',
                padding: '6px 8px',
                fontSize: 12,
                borderRadius: 6,
                border: '1px solid #cbd5e1',
              }}
              data-testid="select-notification-channel"
            >
              <option value="IN_APP_SIMULATED">In-App Banner (Simulated)</option>
              <option value="SMS_SIMULATED">SMS Alert (Simulated)</option>
              <option value="WHATSAPP_SIMULATED">WhatsApp Alert (Simulated)</option>
              <option value="EMAIL_SIMULATED">Email Advisory (Simulated)</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', paddingTop: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer', color: '#475569' }}>
              <input
                type="checkbox"
                checked={simulateFailure}
                onChange={(e) => setSimulateFailure(e.target.checked)}
                data-testid="checkbox-simulate-failure"
              />
              <span>Simulate Delivery Timeout</span>
            </label>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="button primary"
            onClick={handleExecute}
            disabled={executing || loading}
            style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, justifyContent: 'center' }}
            data-testid="button-execute-response"
          >
            {executing ? (
              <>
                <RefreshCw size={14} className="spin" />
                <span>Executing Response…</span>
              </>
            ) : response ? (
              <>
                <RefreshCw size={14} />
                <span>Re-evaluate / Replay Response</span>
              </>
            ) : (
              <>
                <Send size={14} />
                <span>Execute Automated Response</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Disclaimer */}
      <div
        style={{
          marginTop: 12,
          padding: '8px 10px',
          backgroundColor: '#eff6ff',
          borderRadius: 6,
          border: '1px solid #bfdbfe',
          fontSize: 11,
          color: '#1e40af',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
        data-testid="simulated-response-disclaimer"
      >
        <ShieldCheck size={14} style={{ flex: 'none' }} />
        <span>
          <strong>Simulated Environment:</strong> Payment states, customer communications, and safety actions are executed in simulated sandbox mode.
        </span>
      </div>
    </section>
  );
}
