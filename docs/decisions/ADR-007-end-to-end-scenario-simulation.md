# ADR-007: End-to-End Fraud Simulation & Explainability Dashboard

- **Status**: Accepted
- **Date**: 2026-10-18
- **Deciders**: Senior Architect / Full-Stack Engineer (P2-A8)

---

## Context and Problem Statement

AegisPay AI already implements the full automated pipeline: deterministic risk
assessment (P1-A3), AI investigation (P2-A1/A2), the deterministic decision policy
engine (P2-A4), customer verification (P2-A5), coercion intelligence (P2-A6), and
automated response orchestration (P2-A7). What was missing was a way for an
operator to **demonstrate and evaluate** the whole pipeline end-to-end: select a
predefined fraud scenario, run it through the real workflow, inspect the
evidence-to-decision-to-intervention timeline, and compare the observed outcome
with the scenario's expected outcome.

Constraints:
1. This is a simulation and explainability milestone, not a new fraud engine. No
   parallel risk engine or duplicated business logic may be introduced.
2. A scenario's declared expectation must never influence the pipeline and must
   never override the authoritative policy result; the observed outcome is
   whatever the real services produce.
3. Runs must be reproducible for demos/tests (deterministic/mock mode) while
   still allowing explicit, non-silent use of a real AI provider.
4. Timelines must reflect only real persisted outcomes — no fabricated stage,
   timestamp, evidence item, or notification result; unavailable/skipped stages
   must be explicit.
5. Runs must be idempotent and safely retryable without duplicating
   transactions, decisions, responses, or notifications.

---

## Decision

1. **Versioned scenario catalogue as pure data** (`app/domain/scenario_catalog.py`,
   `CATALOG_VERSION = p2a8.v1`). Each `ScenarioDefinition` declares simulated
   transaction inputs, deterministic risk-evidence signals, optional
   investigation evidence, an optional simulated call transcript + voice stress,
   verification behaviour, and a separate `ScenarioExpectation`. The eight
   catalogue entries cover digital-arrest coercion, investment scam, fake invoice,
   mule network, legitimate high-value, ambiguous/insufficient-evidence, an
   ordinary stressed (non-coerced) customer, and strong coercion with successful
   verification. Expectations are documentation only.

2. **Orchestration reuses the real services** (`app/services/scenario_orchestration_service.py`).
   It drives `TransactionService`, `RiskService`, `InvestigationService`,
   `CoercionService`, `DecisionWorkflowService`, `VerificationService`, and
   `ResponseOrchestrationService` in order. The decision stage delegates to
   `DecisionWorkflowService.evaluate`, so risk assessment, investigation, and the
   policy decision remain exactly as the live product computes them; the timeline
   stages for those are then **derived from the persisted artifacts** (assessment,
   investigation id / `provider_failed`, decision). Coercion analysis is persisted
   before the decision when the scenario requires the policy to consider it, or
   after the decision when strong coercion intelligence arrives during a
   verification window (the `strong_coercion_verified` scenario).

3. **Execution modes are explicit.** `DETERMINISTIC` injects a fresh offline
   `MockGeminiClient`; `LIVE_PROVIDER` uses the configured provider. A real
   provider is never silently replaced by a mock. When a provider is unavailable,
   the existing services degrade gracefully (coercion → `UNAVAILABLE`, investigation
   → `provider_failed`) and the deterministic baseline stands without downgrade.

4. **Single `scenario_runs` table** (migration `0012`) stores run metadata plus an
   ordered JSON `stages` timeline. The timeline references authoritative records by
   id rather than copying their content, keeping the store minimal and avoiding
   duplication of transcripts, OTPs, or tokens. Run `status` reports *workflow
   execution* progress and is deliberately distinct from decision correctness.

5. **Evaluation is pure and non-authoritative** (`app/domain/scenario_evaluation.py`).
   It compares the declared expectation with the observed outcome recomputed from
   live persisted artifacts (transaction state, latest decision, latest response,
   verification outcome) and reports `MATCH` / `MISMATCH` / `INCOMPLETE` per
   dimension. The observed value is always preserved; a mismatch never alters a
   decision. A standing disclaimer states that scenario agreement is not a measure
   of real-world fraud-detection accuracy.

6. **Idempotency & retry.** Runs are keyed by an idempotency key (unique
   constraint); concurrent duplicates resolve to the single winning run. Retry
   re-invokes the pipeline reusing the existing transaction; because transaction
   creation, coercion dedup, the one-decision-per-transaction rule, and the
   per-decision/idempotency-keyed response are all idempotent, no duplicate
   transaction, decision, response, or notification is produced.

7. **Operator-authenticated API** (`app/api/scenarios.py`, mounted behind the
   operator boundary): list catalogue, start run, get run + timeline, get
   evaluation, retry. **Frontend**: a new "Scenario Lab" surface
   (`ScenarioSimulationPanel`) added to the existing console without redesigning
   other screens.

---

## Alternatives Considered

- **Decomposing the decision into separate risk/investigation/policy calls** to
  time each stage independently. Rejected: it would either double-run the
  investigation or lose the investigation→policy linkage, and would duplicate the
  workflow service's private orchestration. Deriving the stages from persisted
  artifacts preserves fidelity with zero duplication.
- **Separate `scenario_run_stages` table.** Rejected for now: stages are always
  read/written together with their run and reference other authoritative tables,
  so a JSON timeline column (consistent with the project's existing JSON columns)
  is simpler and sufficient.
- **Letting the scenario force its expected outcome** for a clean demo. Rejected
  outright: it would violate the integrity and truthful-verification rules.

---

## Consequences

- Operators can run any catalogue scenario end-to-end, inspect the real timeline,
  and see expected-vs-actual results, with partial failures visible and retries
  safe.
- Deterministic mode depends on the offline mock AI client, whose keyword matching
  is coarse (e.g. it keys on the substring `liquidat`, which appears in the
  `recent_fd_liquidation` missing-evidence label). Scenario inputs are tuned so the
  deterministic outcome is stable and pedagogically correct; a live provider may
  classify the same evidence differently. This is documented per-scenario under
  `limitations` and is not a property of the authoritative deterministic policy.
- The `strong_coercion_verified` scenario drives a real OTP submission, which
  requires `VERIFICATION_EXPOSE_DEV_OTP`; without it the verification stage is
  reported as `UNAVAILABLE` rather than fabricated.
- No production readiness is claimed. The catalogue is a small hand-authored set
  for demonstration and regression, not a calibrated evaluation dataset.
