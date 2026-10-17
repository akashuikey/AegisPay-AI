# ADR-004: Simulated Customer Verification Lifecycle & Safe Resolution

- **Status**: Accepted
- **Date**: 2026-10-18
- **Deciders**: Senior Architect / Full-Stack Engineer (P2-A5)

---

## Context and Problem Statement

In AegisPay AI, transactions evaluated as `REQUIRE_VERIFICATION` (such as ambiguous payments or medium risk tiers) progress to the `VERIFICATION_REQUIRED` state. To complete an automated, safe resolution workflow, the system requires a simulated customer verification challenge mechanism that:
1. Issues a secure, simulated challenge bound to the customer and transaction.
2. Distinctly separates operator console authentication from the customer simulation context (an operator login must never be treated as customer verification).
3. Securely verifies submissions without plaintext secret persistence.
4. Triggers deterministic policy re-evaluation upon challenge resolution.
5. Upholds the invariant that verification is an additional signal, not an unconditional authorization to settle (e.g. strong coercion or mule indicators cannot be bypassed).

## Decision

1. **Dedicated Verification Challenge Entity**:
   - Persisted in `verification_challenges` table (Alembic migration `0008`).
   - Stores keyed HMAC-SHA256 digest (`otp_digest`), attempt count, max attempts, version (for optimistic locking), expiry, and linked decision reference (`decision_id`). Plaintext OTPs are never persisted.
   - Lifecycle: `PENDING` → `VERIFIED` → `CONSUMED`, or `FAILED` / `EXPIRED`.

2. **Distinct Customer Verification Session Token**:
   - The operator creates/retrieves challenges via operator-authenticated endpoint `POST /api/v1/transactions/{id}/verification`.
   - The response includes a short-lived, cryptographically signed customer verification token (`type: "customer_verification"`).
   - The submission endpoint `POST /api/v1/verification/{challenge_id}/submit` is guarded by this customer token, enforcing path-and-token challenge binding (`context["challenge_id"] == challenge_id`).

3. **Atomic Single-Use & Concurrency Control**:
   - Single-use consumption is enforced via optimistic concurrency version locking (`update_challenge_fields` matching current version).
   - Concurrent submissions or duplicate submissions are idempotent: once `CONSUMED` or `VERIFIED`, replaying returns the existing decision without re-transitioning or consuming twice.

4. **Policy Re-Evaluation Invariant**:
   - Verification outcome is fed into `decide(policy_input)` as `VerificationSignal(outcome)`.
   - `SUCCEEDED` satisfies `REQUIRE_VERIFICATION` and enables `ALLOW` (simulated settlement) only when residual risk is acceptable.
   - `SUCCEEDED` **never** overrides `HOLD_FOR_INVESTIGATION` or `BLOCK` when strong fraud evidence (e.g. duress/coercion, confirmed mule registry) is present.
   - `FAILED`, `EXPIRED`, or `EXHAUSTED` verification escalates the transaction to `HOLD_FOR_INVESTIGATION` (`HELD_FOR_VERIFICATION`) and never permits settlement.

5. **Simulation Boundary & Dev-Only OTP Exposure**:
   - The OTP is simulated (no real SMS/WhatsApp rails).
   - In development/testing, the plaintext OTP is surfaced via `dev_otp` when `VERIFICATION_EXPOSE_DEV_OTP=True`. In production, `dev_otp` is `None`.

## Consequences

- **Positive**: Clean separation of identity contexts, zero plaintext secrets in storage, robust replay and race-condition protection, deterministic policy re-evaluation with fraud guardrails preserved.
- **Trade-offs**: Requires client to manage the short-lived customer verification session token for submission; two-step flow (create challenge → submit response).

---

## Amendment: P2-A5.1 — Verification Security & Concurrency Hardening

- **Status**: Accepted
- **Date**: 2026-10-18
- **Remediated Findings**: SEC-01 through SEC-06

1. **ORM Session Expiration & Scalar Caching (SEC-01)**:
   - Eliminated `MissingGreenlet` crashes across concurrent submission and creation code paths by pre-caching required scalar fields (`cid`, `customer_id`, `version`, `attempt_count`) prior to any database update or potential rollback.
   - Re-queries are performed with fresh awaited queries (`await repository.get_challenge_by_id(cid)`).
   - Removed unnecessary `session.rollback()` in `update_challenge_fields` when `rowcount == 0`, avoiding premature session expiration.

2. **Concurrency Gap Elimination & Bounded In-Flight Polling (SEC-02)**:
   - Addressed the two-phase status progression window (`PENDING` -> `VERIFIED` -> `CONSUMED`) where concurrent requests could observe `status == "VERIFIED"` before `decision_id` is persisted.
   - Introduced a bounded in-flight polling wait (up to 3.0s in 100ms intervals) for both initial submissions and racing optimistic locks, guaranteeing that HTTP 200 is never returned prior to atomic decision persistence.
   - Added an optimistic claim retry loop (up to 3 attempts) in `_handle_correct` to handle races against concurrent `attempt_count` increments without spuriously dropping winning verifications.

3. **Single Pending Challenge via Partial Unique Index (SEC-03)**:
   - Added PostgreSQL partial unique index `uq_verification_challenges_pending_tx` on `verification_challenges(transaction_id)` with condition `WHERE status = 'PENDING'`.
   - Migration `0009_enforce_single_pending_challenge.py` safely deduplicates legacy pending records into `SUPERSEDED` status without data loss.
   - Caught `IntegrityError` in `create_or_get_challenge` on concurrent creation races to roll back cleanly and return the winner's pending challenge.

4. **Transaction State Machine Pre-Check & Failure Recovery (SEC-04)**:
   - Guarded challenge submission with mandatory pre-condition checks on `tx.state == VERIFICATION_REQUIRED`.
   - Rejects submissions with HTTP 409 `TRANSACTION_TERMINAL` if the transaction was cancelled or settled, and `VERIFICATION_NOT_REQUIRED` if escalated or transitioned elsewhere.
   - Added partial failure recovery in `_handle_correct`: if workflow resolution fails after status transition to `VERIFIED`, the challenge is marked `status="FAILED"`, `failure_reason="RESOLUTION_FAILED"` to prevent stranding active challenges with `decision_id=None`.

5. **Dedicated Verification HMAC Secret & Dual-Key Rotation (SEC-05)**:
   - Introduced `VERIFICATION_HMAC_SECRET` configuration decoupled from `AUTH_JWT_SECRET`.
   - Maintained fail-closed fallback to `AUTH_JWT_SECRET` when `VERIFICATION_HMAC_SECRET` is unset.
   - Implemented dual-key rotation verification in `verify_otp`: verifies against the primary secret first, and falls back to verifying against the secondary secret (`AUTH_JWT_SECRET`), preventing invalidation of in-flight challenges during secret rotation.

6. **Database-Backed Challenge Creation Abuse Bounding (SEC-06)**:
   - Enforced database-backed rate limit `count_recent_challenges_for_transaction` within `VERIFICATION_CHALLENGE_WINDOW_SECONDS` (default: max 5 challenges per hour per transaction).
   - Returns HTTP 429 `RATE_LIMIT_EXCEEDED` when exceeded, mitigating challenge flooding and SMS/OTP denial-of-wallet.