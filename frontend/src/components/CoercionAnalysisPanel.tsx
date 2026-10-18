/**
 * Voice Duress & Coercion Intelligence Panel (P2-A6).
 *
 * Displays evidence-backed forensic analysis of simulated call transcripts,
 * verbatim supporting citations, and simulated acoustic voice-stress telemetry.
 *
 * Guardrails enforced in UI:
 * - Voice stress is explicitly marked as simulated acoustic telemetry and advisory only.
 * - Model confidence is presented as qualitative certainty, not a fraud probability.
 * - Grounded verbatim citations are highlighted with exact excerpt quotes.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  PhoneCall,
  RefreshCw,
  Send,
  Volume2,
} from 'lucide-react';
import {
  AnalyzeCoercionRequest,
  CoercionAnalysisResponse,
  CoercionLifecycleStatus,
  analyzeCoercionApi,
  getCoercionLifecycleApi,
} from '../api/coercionApi';

interface CoercionAnalysisPanelProps {
  transactionId: string;
  onAnalyzed?: () => void;
}

const SAMPLE_TRANSCRIPTS: Record<string, { label: string; transcript: string; stress: string }> = {
  digital_arrest: {
    label: 'Digital Arrest Threat',
    transcript:
      'Caller: "This is Inspector Sharma from Cyber Crime CBI Headquarters. Your Aadhaar is linked ' +
      'to 24 illegal accounts used for money laundering. You are placed under digital arrest right now. ' +
      'Do not disconnect this call or talk to your family, or local police will reach your home in 15 minutes. ' +
      'Liquidate your deposit and transfer 450000 rupees to the RBI security verification account immediately. ' +
      'If the bank asks, tell them this is for medical expenses of your sister."',
    stress: 'HIGH',
  },
  routine_travel: {
    label: 'Legitimate Transfer',
    transcript:
      'Customer: "Hi, I am booking an apartment in Bangalore for my daughter\'s college. ' +
      'The landlord requested a token advance before sending the lease agreement. ' +
      'I spoke with the property agent yesterday and verified the flat. Sending 150000 from my savings."',
    stress: 'NONE',
  },
  ordinary_urgency: {
    label: 'Urgent Without Duress',
    transcript:
      'Customer: "Please expedite this transfer right away, the auction deadline closes in 20 minutes! ' +
      'I need this processed quickly so I don\'t forfeit the property deposit."',
    stress: 'ELEVATED',
  },
};

const LIFECYCLE_STYLE: Record<
  CoercionLifecycleStatus,
  { label: string; bg: string; fg: string; border: string }
> = {
  not_started: { label: 'Not started', bg: '#f1f5f9', fg: '#475569', border: '#cbd5e1' },
  in_progress: { label: 'In progress', bg: '#eff6ff', fg: '#1d4ed8', border: '#bfdbfe' },
  completed: { label: 'Completed', bg: '#f0fdf4', fg: '#166534', border: '#bbf7d0' },
  failed: { label: 'Analysis failed', bg: '#fef3c7', fg: '#92400e', border: '#fde68a' },
};

export function CoercionAnalysisPanel({ transactionId, onAnalyzed }: CoercionAnalysisPanelProps) {
  const [analysis, setAnalysis] = useState<CoercionAnalysisResponse | null>(null);
  const [lifecycleStatus, setLifecycleStatus] = useState<CoercionLifecycleStatus | null>(null);
  const [lifecycleDetail, setLifecycleDetail] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form input state
  const [transcript, setTranscript] = useState('');
  const [stressLevel, setStressLevel] = useState<string>('NONE');
  const [speechWpm, setSpeechWpm] = useState<number>(140);
  const [includeStress, setIncludeStress] = useState(false);

  const isMounted = useRef(true);

  const fetchLatest = useCallback(async () => {
    if (!transactionId || transactionId.startsWith('AST-')) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getCoercionLifecycleApi(transactionId);
      if (isMounted.current) {
        setAnalysis(data.analysis);
        setLifecycleStatus(data.status);
        setLifecycleDetail(data.detail);
      }
    } catch (err: unknown) {
      if (isMounted.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch coercion analysis');
      }
    } finally {
      if (isMounted.current) {
        setLoading(false);
      }
    }
  }, [transactionId]);

  useEffect(() => {
    isMounted.current = true;
    void fetchLatest();
    return () => {
      isMounted.current = false;
    };
  }, [fetchLatest]);

  const handleAnalyze = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!transcript.trim() || analyzing) return;

    setAnalyzing(true);
    setError(null);

    const payload: AnalyzeCoercionRequest = {
      call_transcript: transcript.trim(),
    };

    if (includeStress) {
      payload.voice_stress = {
        detected: stressLevel !== 'NONE',
        level: stressLevel,
        speech_rate_wpm: speechWpm > 0 ? speechWpm : undefined,
        acoustic_indicators:
          stressLevel === 'HIGH'
            ? ['micro-tremors', 'frequency modulation', 'pitch compression']
            : stressLevel === 'ELEVATED'
              ? ['mild jitter', 'elevated pitch']
              : [],
      };
    }

    try {
      const result = await analyzeCoercionApi(transactionId, payload);
      if (isMounted.current) {
        setAnalysis(result);
        setLifecycleStatus(result.status === 'UNAVAILABLE' ? 'failed' : 'completed');
        setLifecycleDetail('');
        onAnalyzed?.();
      }
    } catch (err: unknown) {
      if (isMounted.current) {
        setError(err instanceof Error ? err.message : 'Coercion analysis failed');
      }
    } finally {
      if (isMounted.current) {
        setAnalyzing(false);
      }
    }
  };

  const loadSample = (key: string) => {
    const sample = SAMPLE_TRANSCRIPTS[key];
    if (!sample) return;
    setTranscript(sample.transcript);
    setStressLevel(sample.stress);
    setIncludeStress(sample.stress !== 'NONE');
  };

  const getCoercionBadgeColor = (level: string) => {
    switch (level) {
      case 'CONFIRMED_COERCION':
        return '#dc2626'; // red
      case 'SUSPECTED':
        return '#ea580c'; // orange
      case 'NONE':
        return '#16a34a'; // green
      default:
        return '#6b7280'; // gray
    }
  };

  const getSeverityBadgeColor = (severity: string) => {
    switch (severity) {
      case 'CRITICAL':
        return '#b91c1c';
      case 'HIGH':
        return '#dc2626';
      case 'MEDIUM':
        return '#d97706';
      case 'LOW':
        return '#2563eb';
      default:
        return '#6b7280';
    }
  };

  return (
    <section className="drawer-section" data-testid="coercion-analysis-panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
          <PhoneCall size={16} color="#7c3aed" />
          Voice Duress & Coercion Intelligence
        </h3>
        <button
          type="button"
          onClick={() => void fetchLatest()}
          disabled={loading || analyzing}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 4,
            display: 'flex',
            alignItems: 'center',
            color: '#6b7280',
          }}
          title="Refresh analysis"
        >
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
        </button>
      </div>

      <p style={{ margin: '4px 0 12px 0', fontSize: 12, color: '#6b7280' }}>
        Analyzes call transcripts and simulated voice telemetry for psychological manipulation,
        duress, and social engineering coercion. Voice stress is advisory only and never proof of
        fraud.
      </p>

      {lifecycleStatus && (
        <div
          data-testid="coercion-lifecycle-status"
          data-status={lifecycleStatus}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 10px',
            borderRadius: 6,
            fontSize: 12,
            marginBottom: 12,
            background: LIFECYCLE_STYLE[lifecycleStatus].bg,
            color: LIFECYCLE_STYLE[lifecycleStatus].fg,
            border: `1px solid ${LIFECYCLE_STYLE[lifecycleStatus].border}`,
          }}
        >
          <strong style={{ letterSpacing: '0.03em' }}>
            {LIFECYCLE_STYLE[lifecycleStatus].label}
          </strong>
          {lifecycleDetail && <span style={{ opacity: 0.9 }}>{lifecycleDetail}</span>}
        </div>
      )}

      {error && (
        <div
          data-testid="coercion-error-banner"
          style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#b91c1c',
            padding: '8px 12px',
            borderRadius: 6,
            fontSize: 12,
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
      )}

      {/* Analysis Result Display */}
      {analysis && (
        <div
          data-testid="coercion-result-card"
          style={{
            background: '#fafafa',
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            padding: 12,
            marginBottom: 16,
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 8,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span
                data-testid="coercion-level-badge"
                style={{
                  background: getCoercionBadgeColor(analysis.overall_coercion_level),
                  color: '#ffffff',
                  fontSize: 11,
                  fontWeight: 600,
                  padding: '2px 8px',
                  borderRadius: 12,
                  letterSpacing: '0.04em',
                }}
              >
                {analysis.overall_coercion_level}
              </span>
              {analysis.status === 'UNAVAILABLE' && (
                <span
                  style={{
                    background: '#fef3c7',
                    color: '#92400e',
                    fontSize: 11,
                    padding: '2px 6px',
                    borderRadius: 4,
                  }}
                >
                  Provider Fallback
                </span>
              )}
            </div>
            <span style={{ fontSize: 11, color: '#6b7280' }}>
              Certainty: <strong>{analysis.confidence}</strong> (
              {(analysis.confidence_score * 100).toFixed(0)}%)
            </span>
          </div>

          <p style={{ fontSize: 13, color: '#1f2937', margin: '4px 0 10px 0', lineHeight: 1.4 }}>
            {analysis.summary}
          </p>

          <div
            style={{
              fontSize: 11,
              color: '#6b7280',
              fontStyle: 'italic',
              marginBottom: 12,
              padding: '4px 8px',
              background: '#f3f4f6',
              borderRadius: 4,
            }}
          >
            Notice: Model certainty reflects qualitative assessment confidence, NOT a calibrated
            fraud probability.
          </div>

          {/* Simulated Voice Stress Card */}
          {analysis.voice_stress_signals && (
            <div
              data-testid="voice-stress-card"
              style={{
                background: '#f8fafc',
                border: '1px solid #cbd5e1',
                borderRadius: 6,
                padding: 10,
                marginBottom: 12,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 12,
                  fontWeight: 600,
                  color: '#334155',
                  marginBottom: 4,
                }}
              >
                <Volume2 size={14} color="#64748b" />
                Simulated Acoustic Telemetry
                <span
                  style={{
                    marginLeft: 'auto',
                    fontSize: 10,
                    fontWeight: 700,
                    padding: '1px 6px',
                    borderRadius: 4,
                    background:
                      analysis.voice_stress_signals.level === 'HIGH'
                        ? '#fee2e2'
                        : analysis.voice_stress_signals.level === 'ELEVATED'
                          ? '#fef3c7'
                          : '#f1f5f9',
                    color:
                      analysis.voice_stress_signals.level === 'HIGH'
                        ? '#991b1b'
                        : analysis.voice_stress_signals.level === 'ELEVATED'
                          ? '#92400e'
                          : '#475569',
                  }}
                >
                  STRESS: {analysis.voice_stress_signals.level}
                </span>
              </div>
              <div style={{ fontSize: 11, color: '#475569', marginBottom: 4 }}>
                Speech Rate: {analysis.voice_stress_signals.speech_rate_wpm ?? 'N/A'} WPM
                {analysis.voice_stress_signals.acoustic_indicators.length > 0 &&
                  ` · Cues: ${analysis.voice_stress_signals.acoustic_indicators.join(', ')}`}
              </div>
              <p
                style={{
                  fontSize: 10,
                  color: '#64748b',
                  margin: '4px 0 0 0',
                  lineHeight: 1.3,
                  borderTop: '1px dashed #e2e8f0',
                  paddingTop: 4,
                }}
              >
                {analysis.voice_stress_signals.disclaimer}
              </p>
            </div>
          )}

          {/* Grounded Coercion Findings */}
          {analysis.findings.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: '#374151',
                  marginBottom: 6,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                <AlertTriangle size={13} color="#dc2626" />
                Forensic Findings ({analysis.findings.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {analysis.findings.map((f) => (
                  <div
                    key={f.id}
                    data-testid={`coercion-finding-${f.id}`}
                    style={{
                      background: '#ffffff',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      padding: 8,
                      fontSize: 12,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 4,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span
                          style={{
                            background: getSeverityBadgeColor(f.severity),
                            color: '#ffffff',
                            fontSize: 10,
                            fontWeight: 700,
                            padding: '1px 5px',
                            borderRadius: 4,
                          }}
                        >
                          {f.severity}
                        </span>
                        <strong style={{ color: '#111827' }}>{f.category}</strong>
                      </div>
                      <span
                        style={{
                          fontSize: 10,
                          color: f.is_explicit ? '#b91c1c' : '#6b7280',
                          fontWeight: f.is_explicit ? 600 : 400,
                        }}
                      >
                        {f.is_explicit ? '● Explicit Threat/Demand' : '○ Inferred Context'}
                      </span>
                    </div>
                    <div style={{ color: '#374151', marginBottom: 6 }}>{f.explanation}</div>
                    <blockquote
                      style={{
                        margin: 0,
                        padding: '4px 8px',
                        background: '#f9fafb',
                        borderLeft: '3px solid #7c3aed',
                        fontSize: 11,
                        color: '#4b5563',
                        fontStyle: 'italic',
                      }}
                    >
                      "{f.supporting_excerpt}"
                    </blockquote>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Legitimate Explanations (Contradictory / Mitigating evidence) */}
          {analysis.legitimate_explanations.length > 0 && (
            <div
              style={{
                background: '#f0fdf4',
                border: '1px solid #bbf7d0',
                borderRadius: 6,
                padding: 8,
                marginBottom: 8,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: '#166534',
                  marginBottom: 4,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                <CheckCircle2 size={13} color="#16a34a" />
                Mitigating Evidence & Legitimate Explanations
              </div>
              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11, color: '#14532d' }}>
                {analysis.legitimate_explanations.map((note, idx) => (
                  <li key={idx}>{note}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Uncertainty & Limitations */}
          {analysis.uncertainty_notes.length > 0 && (
            <div
              style={{
                fontSize: 11,
                color: '#6b7280',
                borderTop: '1px solid #e5e7eb',
                paddingTop: 6,
              }}
            >
              <div
                style={{
                  fontWeight: 600,
                  marginBottom: 2,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                <HelpCircle size={12} />
                Uncertainty & Notes
              </div>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {analysis.uncertainty_notes.map((note, idx) => (
                  <li key={idx}>{note}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Transcript Input & Real-Time Analysis Form */}
      <form onSubmit={handleAnalyze} style={{ marginTop: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <label
            htmlFor="coercion-transcript-input"
            style={{ fontSize: 12, fontWeight: 600, color: '#374151' }}
          >
            Supply Simulated Call Transcript:
          </label>
          <div style={{ display: 'flex', gap: 4 }}>
            {Object.entries(SAMPLE_TRANSCRIPTS).map(([key, item]) => (
              <button
                key={key}
                type="button"
                onClick={() => loadSample(key)}
                style={{
                  background: '#f3f4f6',
                  border: '1px solid #d1d5db',
                  borderRadius: 4,
                  fontSize: 10,
                  padding: '2px 6px',
                  cursor: 'pointer',
                  color: '#374151',
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <textarea
          id="coercion-transcript-input"
          data-testid="coercion-transcript-input"
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          placeholder="Paste simulated phone conversation or interview dialogue..."
          rows={4}
          style={{
            width: '100%',
            boxSizing: 'border-box',
            marginTop: 6,
            marginBottom: 8,
            padding: 8,
            borderRadius: 6,
            border: '1px solid #d1d5db',
            fontSize: 12,
            fontFamily: 'inherit',
          }}
        />

        {/* Optional Voice Stress Configuration */}
        <div
          style={{
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: 6,
            padding: 8,
            marginBottom: 10,
            fontSize: 11,
          }}
        >
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={includeStress}
              onChange={(e) => setIncludeStress(e.target.checked)}
            />
            <span>Include simulated acoustic telemetry (advisory only)</span>
          </label>

          {includeStress && (
            <div style={{ display: 'flex', gap: 12, marginTop: 8, alignItems: 'center' }}>
              <div>
                <span style={{ marginRight: 4, color: '#64748b' }}>Stress level:</span>
                <select
                  value={stressLevel}
                  onChange={(e) => setStressLevel(e.target.value)}
                  style={{ fontSize: 11, padding: '2px 4px', borderRadius: 4 }}
                >
                  <option value="NONE">NONE</option>
                  <option value="LOW">LOW</option>
                  <option value="ELEVATED">ELEVATED</option>
                  <option value="HIGH">HIGH</option>
                </select>
              </div>
              <div>
                <span style={{ marginRight: 4, color: '#64748b' }}>Speech WPM:</span>
                <input
                  type="number"
                  value={speechWpm}
                  onChange={(e) => setSpeechWpm(Number(e.target.value))}
                  min={60}
                  max={300}
                  style={{ width: 50, fontSize: 11, padding: '2px 4px', borderRadius: 4 }}
                />
              </div>
            </div>
          )}
        </div>

        <button
          type="submit"
          data-testid="coercion-analyze-button"
          disabled={!transcript.trim() || analyzing}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            background: '#7c3aed',
            color: '#ffffff',
            border: 'none',
            borderRadius: 6,
            padding: '6px 12px',
            fontSize: 12,
            fontWeight: 600,
            cursor: !transcript.trim() || analyzing ? 'not-allowed' : 'pointer',
            opacity: !transcript.trim() || analyzing ? 0.6 : 1,
          }}
        >
          {analyzing ? (
            <>
              <RefreshCw size={12} className="spin" />
              Evaluating Duress & Coercion...
            </>
          ) : (
            <>
              <Send size={12} />
              Analyze Call Transcript
            </>
          )}
        </button>
      </form>
    </section>
  );
}
