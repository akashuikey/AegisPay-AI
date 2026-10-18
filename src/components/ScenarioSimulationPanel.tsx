/**
 * End-to-End Fraud Simulation & Explainability Dashboard (P2-A8).
 *
 * Lets an operator pick a predefined scenario, run it through the existing
 * fraud-prevention workflow, inspect the evidence-to-decision-to-intervention
 * timeline, and compare the observed outcome with the scenario's expectation.
 * Every payment outcome is simulated.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  FlaskConical,
  Loader2,
  MinusCircle,
  Play,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import {
  type EvaluationDimension,
  type ExecutionMode,
  type ScenarioEvaluationResponse,
  type ScenarioRunResponse,
  type ScenarioSummary,
  type StageStatus,
  type StageView,
  getScenarioEvaluationApi,
  listScenariosApi,
  retryScenarioRunApi,
  startScenarioRunApi,
} from '../api/scenarioApi';

type StageTone = 'green' | 'amber' | 'red' | 'blue' | 'muted';

function stageTone(status: StageStatus): StageTone {
  switch (status) {
    case 'COMPLETED':
      return 'green';
    case 'UNAVAILABLE':
    case 'SKIPPED':
      return 'amber';
    case 'FAILED':
      return 'red';
    case 'RUNNING':
      return 'blue';
    default:
      return 'muted';
  }
}

function toneClass(tone: StageTone): string {
  return tone === 'muted' ? 'pill' : `pill ${tone}`;
}

function categoryTone(category: EvaluationDimension['category']): StageTone {
  if (category === 'MATCH') return 'green';
  if (category === 'MISMATCH') return 'red';
  return 'amber';
}

function statusLabel(status: string): string {
  return status.replaceAll('_', ' ').toLowerCase();
}

function formatDuration(ms?: number | null): string | null {
  if (ms === null || ms === undefined) return null;
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function StageRow({ stage }: { stage: StageView }): React.ReactElement {
  const tone = stageTone(stage.status);
  const duration = formatDuration(stage.duration_ms);
  return (
    <div className="timeline-row" data-testid={`stage-${stage.key}`}>
      <span className="timeline-dot" aria-hidden />
      <div>
        <div className="timeline-title">
          {stage.sequence}. {stage.title}{' '}
          <span className={toneClass(tone)} style={{ marginLeft: 6 }}>
            {statusLabel(stage.status)}
          </span>
        </div>
        {stage.detail && <div className="timeline-copy">{stage.detail}</div>}
        {stage.reason_codes.length > 0 && (
          <div className="timeline-copy" style={{ marginTop: 3 }}>
            <span className="mono">reasons:</span> {stage.reason_codes.join(', ')}
          </div>
        )}
        {stage.entity_id && (
          <div className="timeline-copy mono" style={{ marginTop: 3, opacity: 0.75 }}>
            {stage.entity_type}: {stage.entity_id}
          </div>
        )}
        {stage.error_category && (
          <div className="timeline-copy" style={{ marginTop: 3, color: '#a43c37' }}>
            {stage.error_category}
          </div>
        )}
      </div>
      <div className="timeline-time">{duration ?? ''}</div>
    </div>
  );
}

function EvaluationIcon({ category }: { category: EvaluationDimension['category'] }) {
  if (category === 'MATCH') return <CheckCircle2 size={14} color="#187154" />;
  if (category === 'MISMATCH') return <XCircle size={14} color="#a43c37" />;
  return <MinusCircle size={14} color="#8b6410" />;
}

export default function ScenarioSimulationPanel(): React.ReactElement {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [catalogVersion, setCatalogVersion] = useState<string>('');
  const [mode, setMode] = useState<ExecutionMode>('DETERMINISTIC');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [run, setRun] = useState<ScenarioRunResponse | null>(null);
  const [evaluation, setEvaluation] = useState<ScenarioEvaluationResponse | null>(null);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoadingCatalog(true);
    listScenariosApi()
      .then((data) => {
        if (!active) return;
        setScenarios(data.items);
        setCatalogVersion(data.catalog_version);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : 'Failed to load scenarios.');
      })
      .finally(() => {
        if (active) setLoadingCatalog(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const runScenario = useCallback(
    async (scenarioId: string) => {
      if (busy) return;
      setBusy(true);
      setError(null);
      setSelectedId(scenarioId);
      setRun(null);
      setEvaluation(null);
      try {
        const started = await startScenarioRunApi(scenarioId, mode);
        setRun(started);
        const ev = await getScenarioEvaluationApi(started.id);
        setEvaluation(ev);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to run scenario.');
      } finally {
        setBusy(false);
      }
    },
    [busy, mode]
  );

  const retry = useCallback(async () => {
    if (busy || !run) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await retryScenarioRunApi(run.id);
      setRun(updated);
      const ev = await getScenarioEvaluationApi(updated.id);
      setEvaluation(ev);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to retry scenario.');
    } finally {
      setBusy(false);
    }
  }, [busy, run]);

  const selectedScenario = scenarios.find((s) => s.id === selectedId) ?? null;

  return (
    <div className="stack" style={{ display: 'grid', gap: 16 }}>
      <div className="card card-pad">
        <div className="card-head">
          <div>
            <div className="eyebrow">
              <FlaskConical size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
              Scenario Lab
            </div>
            <h2 className="card-title">End-to-End Fraud Simulation &amp; Explainability</h2>
          </div>
          <span className="card-kicker">{catalogVersion}</span>
        </div>
        <p className="timeline-copy" style={{ fontSize: 11, marginBottom: 12 }}>
          Run a predefined scenario through the real risk, investigation, coercion, decision,
          verification, and response services, then compare the observed outcome with the
          scenario's declared expectation.
        </p>
        <div className="notice info" role="note">
          <ShieldAlert />
          <span>
            Sandbox: all payments, holds, blocks, OTPs, and notifications are simulated. Scenario
            comparison reflects agreement with a small set of hand-authored expectations only — it
            is not a measure of real-world fraud-detection accuracy.
          </span>
        </div>
        <div className="field-row" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <label className="field-label" htmlFor="scn-mode">
            Execution mode
          </label>
          <select
            id="scn-mode"
            className="select"
            style={{ maxWidth: 260 }}
            value={mode}
            onChange={(e) => setMode(e.target.value as ExecutionMode)}
            disabled={busy}
          >
            <option value="DETERMINISTIC">Deterministic (offline mock AI)</option>
            <option value="LIVE_PROVIDER">Live provider (configured AI)</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="notice" role="alert">
          <AlertTriangle />
          <span>{error}</span>
        </div>
      )}

      <div className="scenario-grid">
        <div className="card card-pad">
          <div className="card-head">
            <h3 className="card-title" style={{ fontSize: 13 }}>
              Scenario catalogue
            </h3>
          </div>
          {loadingCatalog ? (
            <div className="timeline-copy">
              <Loader2 size={13} className="spin" style={{ verticalAlign: '-2px' }} /> Loading
              scenarios…
            </div>
          ) : (
            <div className="stack" style={{ display: 'grid', gap: 10 }}>
              {scenarios.map((s) => (
                <div
                  key={s.id}
                  className="card card-pad"
                  data-testid={`scenario-${s.id}`}
                  style={{
                    boxShadow: 'none',
                    borderColor: selectedId === s.id ? '#11745f' : undefined,
                  }}
                >
                  <div className="card-head" style={{ marginBottom: 8 }}>
                    <div className="card-title" style={{ fontSize: 12 }}>
                      {s.title}
                    </div>
                    <span className="card-kicker">v{s.version}</span>
                  </div>
                  <p className="timeline-copy" style={{ marginBottom: 8 }}>
                    {s.description}
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                    <span className="pill blue">expect: {s.expectation.policy_action}</span>
                    <span className="pill">{s.expectation.final_state}</span>
                    {s.exercises_coercion_analysis && <span className="pill amber">coercion</span>}
                    {s.exercises_verification && <span className="pill amber">verification</span>}
                  </div>
                  <button
                    className="button primary small"
                    onClick={() => runScenario(s.id)}
                    disabled={busy}
                    data-testid={`run-${s.id}`}
                  >
                    {busy && selectedId === s.id ? (
                      <Loader2 size={13} className="spin" />
                    ) : (
                      <Play size={13} />
                    )}
                    Run scenario
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card card-pad">
          <div className="card-head">
            <h3 className="card-title" style={{ fontSize: 13 }}>
              Run timeline &amp; evaluation
            </h3>
            {run && run.status === 'FAILED' && (
              <button className="button danger small" onClick={retry} disabled={busy}>
                <RefreshCw size={13} /> Retry
              </button>
            )}
          </div>

          {!run ? (
            <div className="timeline-copy" data-testid="run-empty">
              <CircleSlash size={13} style={{ verticalAlign: '-2px', marginRight: 4 }} />
              Select a scenario and run it to see the explainability timeline.
            </div>
          ) : (
            <div className="stack" style={{ display: 'grid', gap: 14 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }} data-testid="run-summary">
                <span className="pill">{selectedScenario?.title ?? run.scenario_id}</span>
                <span className={toneClass(run.status === 'COMPLETED' ? 'green' : 'red')}>
                  workflow: {statusLabel(run.status)}
                </span>
                <span className="pill">{run.execution_mode === 'DETERMINISTIC' ? 'deterministic' : 'live provider'}</span>
                {run.ai_provider && <span className="pill">AI: {run.ai_provider}</span>}
                {run.final_state && <span className="pill blue">state: {run.final_state}</span>}
              </div>

              <div className="timeline">
                {[...run.stages]
                  .sort((a, b) => a.sequence - b.sequence)
                  .map((stage) => (
                    <StageRow key={stage.key} stage={stage} />
                  ))}
              </div>

              {evaluation && (
                <div className="card card-pad" style={{ boxShadow: 'none' }}>
                  <div className="card-head" style={{ marginBottom: 8 }}>
                    <div className="card-kicker">Expected vs. actual</div>
                    <span className={toneClass(categoryTone(evaluation.overall))}>
                      {evaluation.overall}
                    </span>
                  </div>
                  <div className="timeline-copy" style={{ marginBottom: 10 }}>
                    Workflow executed:{' '}
                    <strong>{evaluation.workflow_execution_success ? 'yes' : 'no'}</strong>. This is
                    separate from whether the fraud decision matches the declared expectation.
                  </div>
                  <div className="stack" style={{ display: 'grid', gap: 7 }}>
                    {evaluation.dimensions.map((d) => (
                      <div
                        key={d.name}
                        data-testid={`dim-${d.name}`}
                        style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}
                      >
                        <EvaluationIcon category={d.category} />
                        <div>
                          <div className="timeline-title">
                            {d.name.replaceAll('_', ' ')}: {d.category}
                          </div>
                          <div className="timeline-copy">
                            expected <span className="mono">{d.expected ?? '—'}</span> · observed{' '}
                            <span className="mono">{d.observed ?? '—'}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  {evaluation.incomplete_stages.length > 0 && (
                    <div className="timeline-copy" style={{ marginTop: 10 }}>
                      Incomplete stages: {evaluation.incomplete_stages.join(', ')}
                    </div>
                  )}
                  <div className="timeline-copy" style={{ marginTop: 10, opacity: 0.8 }}>
                    {evaluation.disclaimer}
                  </div>
                </div>
              )}

              {selectedScenario && selectedScenario.expectation.limitations.length > 0 && (
                <div className="notice info">
                  <AlertTriangle />
                  <span>
                    Assumptions &amp; limitations: {selectedScenario.expectation.limitations.join(' ')}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
