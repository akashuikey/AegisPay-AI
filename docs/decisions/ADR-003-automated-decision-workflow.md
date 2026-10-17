# ADR-003: Automated Decision Workflow & Deterministic Policy Engine

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Senior Architect / Full-Stack Engineer (P2-A4)

---

## Context and Problem Statement

AegisPay AI needed an automated, end-to-end decision workflow so a simulated
payment can be evaluated and resolved without an operator inspecting every
transaction. The pieces already existed — the 10-state machine, the
deterministic risk engine, the P2-A1 investigation service — but nothing tied
them together into an automated action, and no component selected a permitted
action and executed the corresponding transition with an auditable record.

## Decision

1. **Separation of policy from execution.** A new pure-domain **policy engine**
   (`app/domain/decision_policy.py`, `POLICY_VERSION = "p2a4.v1"`) maps validated
   structured inputs to a typed `PolicyDecision`. A new **orchestration service**
   (`DecisionWorkflowService`) runs risk → optional investigation → policy →
   transition → decision persistence. The policy engine never performs I/O and
   never mutates state; the orchestrator validates and applies the transition
   through the existing `TransactionService`.

2. **The LLM never chooses the action.** Investigation findings can only
   ESCALATE the conservative deterministic baseline (take the strictly more
   severe action); they never downgrade it. The model's numeric confidence is
   never read (not a calibrated fraud probability) — only categorical sentiment
   influences escalation.

3. **Action → state mapping** (all reachable from `DECISION_READY`):
   `ALLOW → SETTLED_SIMULATED`, `REQUIRE_VERIFICATION → VERIFICATION_REQUIRED`,
   `HOLD_FOR_INVESTIGATION → HELD_FOR_VERIFICATION`, `BLOCK → CANCELLED_SIMULATED`.
   No new states were added; `PolicyAction` is a distinct enum (the risk engine's
   `RecommendedAction` has no BLOCK).

4. **BLOCK is reserved** for one explicit, independently verified deterministic
   condition: a consortium mule-registry hit (`RULE_FLAGGED_MULE_ACCOUNT`) at
   CRITICAL risk. All other high-risk outcomes HOLD rather than cancel.

5. **Safe fallback on provider failure.** Investigation provider failures are
   caught; the workflow continues on the deterministic baseline and never
   downgrades a high-risk transaction. Low-risk transactions skip the LLM.

6. **Persistence & auditability.** A new `transaction_decisions` table
   (migration `0007`) stores the structured decision (action, policy version,
   assessment/investigation references, rule ids, evidence refs, reason codes,
   from/to state, workflow status). The authoritative, atomic record is the
   existing `transaction_audits` entry written with the state transition; the
   decision row is a traceable companion persisted in a **separate commit** after
   the transition (atomicity across the transition and the decision row is **not**
   claimed).

7. **Idempotency & concurrency.** One automated decision per transaction: a
   repeat `evaluate` returns the existing decision (HTTP 200) without
   re-transitioning, so held/verification outcomes cannot settle via retry. The
   final transition uses the existing optimistic-concurrency version check; a
   losing concurrent workflow returns the winner's decision instead of a
   conflicting outcome.

8. **API & auth.** Two authenticated routes on the existing transactions router:
   `POST /api/v1/transactions/{id}/evaluate` and `GET /api/v1/transactions/{id}/decision`.
   They inherit the P2-A2.1 operator authentication boundary.

## Alternatives Considered

- **Distributed event system / async queue** for the investigation stage —
  rejected as unjustified complexity; the workflow runs synchronously, bounded by
  the existing provider timeout/retries.
- **Letting the risk engine's `RecommendedAction` be the final action** —
  rejected: it has no BLOCK and does not incorporate investigation evidence or
  map to a transition.
- **Atomic single-transaction decision+transition** — the repository commits per
  operation; rather than claim false atomicity, the audit entry remains the
  authoritative atomic record and the decision row is a companion.

## Consequences

- A simulated payment can be evaluated and resolved automatically with an
  auditable, versioned, idempotent decision.
- All settlement/cancellation outcomes remain simulated states; no real transfer.
- **Out of scope / future:** a human adjudication workflow to advance HELD/
  VERIFICATION_REQUIRED transactions; richer async processing; calibrated scoring
  (needs labeled data); rate limiting on the workflow endpoints.
