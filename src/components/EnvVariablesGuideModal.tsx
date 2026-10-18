import React from 'react';
import { X, Key, ShieldCheck, Terminal, Cpu, Info, CheckCircle2, AlertCircle } from 'lucide-react';

interface EnvVariablesGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const EnvVariablesGuideModal: React.FC<EnvVariablesGuideModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.65)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 110,
        padding: 16,
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 620,
          background: '#ffffff',
          borderRadius: 20,
          padding: 26,
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          border: '1px solid #e2e8f0',
          maxHeight: '88vh',
          overflowY: 'auto',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, borderBottom: '1px solid #f1f5f9', paddingBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                background: '#f0fdf4',
                color: '#16a34a',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <Key size={20} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: '#0f172a' }}>
                Environment Variables & API Secrets
              </h3>
              <p style={{ margin: 0, fontSize: 11, color: '#64748b' }}>
                How and where to configure environment variables for AegisPay AI
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#94a3b8' }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Section 1: AI Studio Cloud Deployment */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <Cpu size={16} color="#0284c7" />
            <h4 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: '#0f172a' }}>
              1. In Google AI Studio Build (Cloud Environment)
            </h4>
          </div>
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 12, padding: 14, fontSize: 12, color: '#334155', lineHeight: 1.6 }}>
            <p style={{ margin: '0 0 8px' }}>
              In Google AI Studio, secrets are managed securely outside the client bundle:
            </p>
            <ol style={{ margin: '0 0 10px', paddingLeft: 20 }}>
              <li>
                Click on the <strong>Settings</strong> gear or <strong>Secrets</strong> panel in the AI Studio interface.
              </li>
              <li>
                Add <strong>GEMINI_API_KEY</strong> with your Google AI Studio Gemini API key.
              </li>
              <li>
                The platform securely provisions this key to the backend runtime as <code>process.env.GEMINI_API_KEY</code>.
              </li>
            </ol>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#0369a1', background: '#e0f2fe', padding: '6px 10px', borderRadius: 6 }}>
              <ShieldCheck size={14} />
              <span>
                <strong>Zero Client Exposure:</strong> The Gemini API key is never bundled in frontend code or visible in network inspection.
              </span>
            </div>
          </div>
        </div>

        {/* Section 2: Local Development */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <Terminal size={16} color="#0f766e" />
            <h4 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: '#0f172a' }}>
              2. In Local Development (.env file)
            </h4>
          </div>
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 12, padding: 14, fontSize: 12, color: '#334155' }}>
            <p style={{ margin: '0 0 8px' }}>
              Create a <code>.env</code> file in the project root by copying <code>.env.example</code>:
            </p>
            <div
              style={{
                background: '#0f172a',
                color: '#e2e8f0',
                borderRadius: 8,
                padding: '10px 14px',
                fontFamily: 'monospace',
                fontSize: 11,
                lineHeight: 1.5,
                marginBottom: 10,
              }}
            >
              # Gemini AI Models & Credentials<br />
              GEMINI_API_KEY=AIzaSy...<br />
              <br />
              # Port Configuration<br />
              PORT=3000<br />
              <br />
              # Model Selections<br />
              GEMINI_LIVE_MODEL=gemini-3.8-live<br />
              GEMINI_TRANSCRIBE_MODEL=gemini-3.5-transcribe
            </div>
          </div>
        </div>

        {/* Section 3: Fallback & Resiliency Guardrail */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <Info size={16} color="#d97706" />
            <h4 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: '#0f172a' }}>
              3. Resilient Demo Fallback Mode
            </h4>
          </div>
          <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 12, padding: 12, fontSize: 11.5, color: '#92400e', lineHeight: 1.5 }}>
            <p style={{ margin: 0 }}>
              If no API key is attached, or if the free tier daily quota is reached (HTTP 429), the application automatically engages its <strong>evidence-aware Demo Fallback</strong> mode. The 11-rule deterministic risk engine and all 8 demo scenarios remain 100% operational.
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 14 }}>
          <button
            type="button"
            onClick={onClose}
            className="button primary"
            style={{ padding: '8px 20px', fontSize: 12 }}
          >
            Got it, thanks!
          </button>
        </div>
      </div>
    </div>
  );
};
