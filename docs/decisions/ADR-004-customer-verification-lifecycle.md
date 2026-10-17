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

