/**
 * Operator Investigation Review Panel (P2-A3).
 *
 * A read-oriented decision-support surface that presents EXISTING AI investigation
 * results for a transaction: an overview, prioritized key findings, an evidence
 * provenance index, and an uncertainty / missing-information section. It reuses the
 * existing investigation APIs (authenticated via the shared apiFetch client) and
 * never launches investigations automatically, mutates transaction state, or makes
 * the AI the authority for any transaction action.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  FileSearch,
  HelpCircle,
  Info,
  RefreshCw,
  ShieldQuestion,
} from 'lucide-react';
import {
  EvidenceProvenance,
  InvestigationFindingResponse,
  InvestigationResponse,
  fetchInvestigationsForTransactionApi,
} from '../api/investigationApi';

interface InvestigationReviewPanelProps {
  transactionId: string;
  transactionReference: string;
  transactionStatus: string;
  riskScore?: number | null;
  riskLevel?: string | null;
}

type LoadState = 'loading' | 'loaded' | 'empty' | 'error';

const SEVERITY_ORDER: Record<string, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
};

// Classify a finding/evidence provenance into trust buckets the operator can reason
// about. Uses only the existing EvidenceProvenance enum; it does not assert the AI
// independently verified anything.
function classifyProvenance(provenance: EvidenceProvenance): { label: string; tone: string } {
  switch (provenance) {
    case 'consortium_registry':
    case 'historical_ledger':
      return { label: 'Independently verified source', tone: 'green' };
    case 'risk_engine':
      return { label: 'Deterministic engine signal', tone: 'blue' };
    case 'device_telephony':
      return { label: 'Observed device signal (simulated)', tone: 'blue' };
    case 'customer_statement':
    case 'document_extraction':
    case 'operator_note':
      return { label: 'Customer-reported / unverified', tone: 'amber' };
    case 'model_inference':
    case 'ai_assistant':
      return { label: 'Model inference (not evidence)', tone: 'rose' };
    default:
      return { label: 'Unspecified provenance', tone: 'slate' };
  }
}

function severityTone(severity: string): string {
  if (severity === 'CRITICAL') return 'red';
  if (severity === 'HIGH') return 'amber';
  if (severity === 'MEDIUM') return 'blue';
  return 'slate';
}

interface EvidenceIndexEntry {
  reference: string;
  provenances: Set<EvidenceProvenance>;
  citedBy: string[];
}

function buildEvidenceIndex(findings: InvestigationFindingResponse[]): EvidenceIndexEntry[] {
  const map = new Map<string, EvidenceIndexEntry>();
  for (const f of findings) {
    for (const ref of f.supporting_evidence_references) {
      const existing = map.get(ref) ?? {
        reference: ref,
        provenances: new Set<EvidenceProvenance>(),
        citedBy: [],
      };
      existing.provenances.add(f.source_provenance);
      existing.citedBy.push(f.id);
      map.set(ref, existing);
    }
  }
  return Array.from(map.values());
}

export function InvestigationReviewPanel({
  transactionId,
  transactionReference,
  transactionStatus,
  riskScore,
  riskLevel,
}: InvestigationReviewPanelProps) {
  const [investigation, setInvestigation] = useState<InvestigationResponse | null>(null);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [state, setState] = useState<LoadState>('loading');
  const [error, setError] = useState<string | null>(null);
  // Guard against overlapping/duplicate fetches from rapid repeated clicks.
  const inFlight = useRef<boolean>(false);

  const loadInvestigations = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setState((prev) => (prev === 'loaded' ? 'loaded' : 'loading'));
    setError(null);
    try {
      const list = await fetchInvestigationsForTransactionApi(transactionId);
      setTotalCount(list.total_entries);
      if (list.items.length === 0) {
        setInvestigation(null);
        setState('empty');
      } else {
        // Backend returns investigations newest-first; present the latest.
        setInvestigation(list.items[0]);
        setState('loaded');
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load investigation data';
      // A 404 means the backend has no such transaction (e.g. a demo-only record);
      // present that as an empty state rather than a hard error.
      if (/\(404\)/.test(message) || /not found/i.test(message)) {
        setInvestigation(null);
        setTotalCount(0);
        setState('empty');
      } else {
        setError(message);
        setState('error');
      }
    } finally {
      inFlight.current = false;
    }
  }, [transactionId]);

  useEffect(() => {
    void loadInvestigations();
  }, [loadInvestigations]);

  const sortedFindings = investigation
    ? [...investigation.findings].sort(
        (a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
      )
    : [];
  const evidenceIndex = investigation ? buildEvidenceIndex(investigation.findings) : [];
  const refreshing = state === 'loading' && investigation !== null;

  return (
    <section className="drawer-section" data-testid="investigation-review-panel">
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 12,
        }}
      >
        <div>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
            <FileSearch size={16} color="#2563eb" />
            Investigation Review
          </h3>
          <p style={{ margin: '4px 0 0 0', fontSize: 12, color: '#6b7280' }}>
            Review AI forensic findings, evidence provenance, and open questions
          </p>
        </div>
        <button
          className="button small"
          onClick={() => void loadInvestigations()}
          disabled={state === 'loading'}
          title="Refresh investigation data"
          aria-label="Refresh investigation data"
          data-testid="button-refresh-investigation"
        >
          <RefreshCw size={12} className={state === 'loading' ? 'spin' : ''} />
        </button>
      </div>

      {/* Advisory: decision-support only */}
      <div
        style={{
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: 6,
          padding: '8px 12px',
          fontSize: 12,
          color: '#475569',
          marginBottom: 14,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <Info size={14} color="#0284c7" style={{ flexShrink: 0 }} />
        <span>
          <strong>Decision support only.</strong> AI findings are advisory intelligence. The
          deterministic policy and transaction state machine remain authoritative; this panel does
          not change transaction state.
        </span>
      </div>

      {/* Error state */}
      {state === 'error' && (
        <div
          role="alert"
          data-testid="review-error-alert"
          style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#991b1b',
            borderRadius: 6,
            padding: '10px 12px',
            fontSize: 13,
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Loading state (initial) */}
      {state === 'loading' && !investigation && (
        <div
          data-testid="review-loading"
          style={{ padding: '24px 0', textAlign: 'center', color: '#6b7280' }}
        >
          <RefreshCw
            size={18}
            className="spin"
            style={{ margin: '0 auto 8px auto', display: 'block' }}
          />
          Loading investigation data…
        </div>
      )}

      {/* Empty state */}
      {state === 'empty' && (
        <div
          data-testid="review-empty-state"
          style={{
            background: '#fafafa',
            border: '1px dashed #cbd5e1',
            borderRadius: 8,
            padding: 20,
            textAlign: 'center',
          }}
        >
          <ShieldQuestion
            size={28}
            color="#64748b"
            style={{ margin: '0 auto 8px auto', display: 'block' }}
          />
          <h4 style={{ margin: '0 0 6px 0', fontSize: 14 }}>No AI investigation recorded</h4>
          <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>
            No forensic investigation has been stored for this transaction yet. Use the
            investigation conversation below to begin examining supplied evidence.
          </p>
        </div>
      )}

      {/* Error state shows nothing further; loaded/refreshing shows content */}
      {investigation && (state === 'loaded' || refreshing) && (
        <div style={{ opacity: refreshing ? 0.6 : 1 }} data-testid="review-content">
          {/* A. Overview */}
          <div
            style={{
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              padding: 12,
              marginBottom: 14,
            }}
            data-testid="review-overview"
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                gap: 10,
              }}
            >
              <OverviewCell label="Transaction" value={transactionReference} />
              <OverviewCell label="Simulated status" value={transactionStatus} />
              <OverviewCell
                label="Deterministic risk"
                value={
                  riskScore != null && riskLevel
                    ? `${riskLevel} (${riskScore}/100)`
                    : 'Not available'
                }
              />
              <OverviewCell
                label="Investigation recorded"
                value={new Date(investigation.created_at).toLocaleString('en-IN')}
              />
              <OverviewCell
                label="AI risk sentiment"
                value={investigation.overall_risk_sentiment}
              />
              <OverviewCell
                label="AI confidence"
                value={`${investigation.confidence} (${Math.round(
                  investigation.confidence_score * 100
                )}%)`}
              />
              <OverviewCell
                label="Model attribution"
                value={`${investigation.model_metadata.provider} · ${investigation.model_metadata.model_id}`}
              />
              <OverviewCell
                label="Investigations on file"
                value={String(totalCount)}
              />
            </div>

            <p
              style={{
                margin: '10px 0 0 0',
                fontSize: 11,
                color: '#64748b',
                lineHeight: 1.5,
              }}
            >
              <strong>Risk assessment vs investigation:</strong> the deterministic risk score is a
              policy-driven relative rating, and the AI sentiment/confidence is a qualitative
              forensic assessment of supplied evidence — <em>not</em> a calibrated statistical fraud
              probability. They are distinct inputs to a human decision.
            </p>
          </div>

          {/* Summary */}
          {investigation.summary && (
            <div style={{ marginBottom: 14 }}>
              <SectionLabel icon={<Info size={12} color="#0284c7" />} text="INVESTIGATION SUMMARY" />
              <p
                style={{ margin: '6px 0 0 0', fontSize: 13, color: '#334155', whiteSpace: 'pre-wrap' }}
                data-testid="review-summary"
              >
                {investigation.summary}
              </p>
            </div>
          )}

          {/* B. Key findings */}
          <div style={{ marginBottom: 14 }} data-testid="review-findings">
            <SectionLabel
              icon={<AlertTriangle size={12} color="#d97706" />}
              text={`KEY FINDINGS (${sortedFindings.length})`}
            />
            {sortedFindings.length === 0 ? (
              <p style={{ margin: '6px 0 0 0', fontSize: 12, color: '#64748b' }}>
                The investigation recorded no discrete findings.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 6 }}>
                {sortedFindings.map((f) => {
                  const prov = classifyProvenance(f.source_provenance);
                  return (
                    <div
                      key={f.id}
                      data-testid={`review-finding-${f.id}`}
                      style={{
                        background: '#ffffff',
                        border: '1px solid #e2e8f0',
                        borderRadius: 6,
                        padding: '8px 10px',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          gap: 6,
                        }}
                      >
                        <strong style={{ color: '#0f172a', fontSize: 13 }}>{f.category}</strong>
                        <span className={`pill small ${severityTone(f.severity)}`}>
                          {f.severity}
                        </span>
                      </div>
                      <p style={{ margin: '4px 0 6px 0', fontSize: 12.5, color: '#334155' }}>
                        {f.explanation}
                      </p>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                        <span
                          className={`pill small ${prov.tone}`}
                          data-testid={`finding-provenance-${f.id}`}
                        >
                          {prov.label}
                        </span>
                        {f.supporting_evidence_references.length > 0 ? (
                          <span style={{ fontSize: 10, color: '#64748b' }}>
                            Evidence: {f.supporting_evidence_references.join(', ')}
                          </span>
                        ) : (
                          <span style={{ fontSize: 10, color: '#94a3b8' }}>
                            No evidence citation
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* C. Evidence inspection */}
          <div style={{ marginBottom: 14 }} data-testid="review-evidence">
            <SectionLabel
              icon={<FileSearch size={12} color="#2563eb" />}
              text={`EVIDENCE & PROVENANCE (${evidenceIndex.length})`}
            />
            {evidenceIndex.length === 0 ? (
              <p style={{ margin: '6px 0 0 0', fontSize: 12, color: '#64748b' }}>
                No evidence references were cited by the recorded findings.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                {evidenceIndex.map((entry) => {
                  const provList = Array.from(entry.provenances);
                  return (
                    <div
                      key={entry.reference}
                      data-testid={`evidence-item-${entry.reference}`}
                      style={{
                        border: '1px solid #e2e8f0',
                        borderRadius: 6,
                        padding: '8px 10px',
                        fontSize: 12,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          gap: 6,
                        }}
                      >
                        <strong className="mono" style={{ color: '#0f172a' }}>
                          {entry.reference}
                        </strong>
                        <span style={{ fontSize: 10, color: '#64748b' }}>
                          Cited by {entry.citedBy.length} finding
                          {entry.citedBy.length === 1 ? '' : 's'}
                        </span>
                      </div>
                      <div
                        style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 5 }}
                      >
                        {provList.map((p) => {
                          const c = classifyProvenance(p);
                          return (
                            <span key={p} className={`pill small ${c.tone}`}>
                              {c.label}
                            </span>
                          );
                        })}
                      </div>
                      <p style={{ margin: '6px 0 0 0', fontSize: 10.5, color: '#94a3b8' }}>
                        Source content is not retained in the investigation record. Review the
                        investigation conversation below for the underlying statements, and treat
                        customer-reported content as unverified.
                      </p>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* D. Uncertainty & missing information */}
          <div data-testid="review-uncertainty">
            <SectionLabel
              icon={<HelpCircle size={12} color="#0284c7" />}
              text="UNCERTAINTY & MISSING INFORMATION"
            />
            <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <UncertaintyBlock
                testid="review-missing-information"
                title="Missing / unverified information"
                items={investigation.missing_information}
                emptyText="No missing information was flagged."
                tone="amber"
              />
              <UncertaintyBlock
                testid="review-unresolved-questions"
                title="Unresolved questions"
                items={investigation.unresolved_questions}
                emptyText="No unresolved questions were recorded."
                tone="blue"
              />
              <UncertaintyBlock
                testid="review-contradictory-evidence"
                title="Contradictory / mitigating evidence"
                items={investigation.contradictory_or_mitigating_evidence}
                emptyText="No contradictory or mitigating evidence was recorded."
                tone="slate"
              />
              <UncertaintyBlock
                testid="review-next-steps"
                title="Suggested next investigative steps"
                items={investigation.suggested_next_steps}
                emptyText="No further steps were suggested."
                tone="green"
                icon={<CheckCircle2 size={12} color="#16a34a" />}
              />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function OverviewCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <small style={{ color: '#94a3b8', textTransform: 'uppercase', fontSize: 10 }}>{label}</small>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a', wordBreak: 'break-word' }}>
        {value}
      </div>
    </div>
  );
}

function SectionLabel({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div
      style={{
        fontSize: 11,
        fontWeight: 700,
        color: '#475569',
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        letterSpacing: 0.3,
      }}
    >
      {icon}
      {text}
    </div>
  );
}

function UncertaintyBlock({
  title,
  items,
  emptyText,
  tone,
  testid,
  icon,
}: {
  title: string;
  items: string[];
  emptyText: string;
  tone: string;
  testid: string;
  icon?: React.ReactNode;
}) {
  return (
    <div data-testid={testid}>
      <div style={{ fontSize: 12, fontWeight: 600, color: '#334155', marginBottom: 4 }}>
        {icon && <span style={{ marginRight: 4, verticalAlign: 'middle' }}>{icon}</span>}
        {title}
      </div>
      {items.length === 0 ? (
        <p style={{ margin: 0, fontSize: 11.5, color: '#94a3b8' }}>{emptyText}</p>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {items.map((item, idx) => (
            <li key={idx} style={{ fontSize: 12, color: '#334155', marginBottom: 2 }}>
              <span className={`pill small ${tone}`} style={{ marginRight: 6 }}>
                !
              </span>
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
