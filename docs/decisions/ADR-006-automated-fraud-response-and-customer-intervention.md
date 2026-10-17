# ADR-006: Automated Fraud Response Orchestration & Customer Intervention

- **Status**: Accepted
- **Date**: 2026-10-18
- **Deciders**: Senior Architect / Full-Stack Engineer (P2-A7)

---

## Context and Problem Statement

AegisPay AI already implements deterministic risk assessment, AI investigation, coercion intelligence, deterministic policy decisions, and customer verification challenges. However, decisions must be automatically executed and clearly communicated to customers without requiring human operators to manually intervene on every transaction.

Key requirements and constraints for automated response orchestration:
1. **Automated Autonomous Execution**: Decisions must translate directly into simulated lifecycle actions without mandatory employee sign-off.
2. **Customer-Safe Communication**: Customer messages must be clear, non-accusatory, understandable, and empathetic. They must never accuse the customer of fraud or assert fraud is definitively proven when uncertain.
3. **No Internal Vocabulary or Rule Leakage**: Internal rule IDs (`RULE_FLAGGED_MULE_ACCOUNT`), risk scores, model sentiments, or consortium registry terminology must never be surfaced in customer-facing messages.
4. **Safety from Malicious Instruction**: Guidance must warn customers never to call phone numbers or visit links provided by unsolicited callers. Advice directs customers only to official bank channels (e.g. number on the back of their bank card).
5. **Notification Failure Isolation**: Notification delivery failures (e.g., carrier timeouts, undelivered SMS) must never invalidate, downgrade, or silently reverse an authoritative protective hold or block decision.
6. **Credential & Telemetry Hygiene**: Notification bodies and recipient fields must contain only masked contact info (`p***a@upi`) and zero OTPs, customer session tokens, bearer tokens, or sensitive transcripts.
7. **Strict Simulation**: All payment outcomes, holds, cancellations, and notifications remain strictly simulated in sandbox mode without invoking real banking rails or real telecommunication carriers.

---

## Decision

1. **Response Domain & Policy Mapping**:
   - `ResponseType` enum maps 1:1 with authoritative policy actions:
     - `ALLOW` → `ALLOW_SETTLED` (`SETTLED_SIMULATED`)
     - `REQUIRE_VERIFICATION` → `VERIFICATION_REQUIRED` (`VERIFICATION_REQUIRED`)
     - `HOLD_FOR_INVESTIGATION` → `HOLD_PROTECTIVE` (`INVESTIGATING` / held)
     - `BLOCK` → `BLOCK_SAFETY` (`CANCELLED_SIMULATED`)
   - `CustomerActionRequired` enum defines action paths: `NONE`, `VERIFY_OTP`, `CONTACT_BANK`.
   - `build_customer_intervention()` generates customer-safe headlines, messages, and actionable safety steps.

2. **Simulated Notification Service & Channel Decoupling**:
   - `SimulatedNotificationService` supports `IN_APP_SIMULATED`, `SMS_SIMULATED`, `WHATSAPP_SIMULATED`, and `EMAIL_SIMULATED`.
   - Masks contact identifiers using `mask_recipient_contact()` (`u***e@domain.com`, `+91 ***-***-1234`, `p***a@upi`).
   - Automatically redacts accidental secrets (OTPs, JWT tokens, API keys) from notification content.
   - Supports `simulate_failure=True` resulting in `FAILED_SIMULATED` with `SIMULATED_CARRIER_TIMEOUT`.
   - **Isolation**: Delivery failures are logged and recorded in `transaction_notifications`, but the response status remains `COMPLETED` and the underlying transaction state transition is preserved.

3. **Data Model & Persistence**:
   - PostgreSQL table `transaction_responses`:
     - Tracks response ID, transaction ID, decision ID, response type, action, processing status, from/to states, headline, customer message, action required, next steps (JSON), idempotency key, and timestamps.
     - Unique constraint on `(transaction_id, idempotency_key)` guarantees idempotent replays.
   - PostgreSQL table `transaction_notifications`:
     - Tracks notification ID, response ID, transaction ID, channel, masked recipient, subject, message body, delivery status, failure reason, idempotency key, and delivery timestamps.
     - Unique constraint on `(response_id, channel)`.
   - Alembic migration `0011_create_fraud_responses_and_notifications.py` applies schema changes with full rollback capability.

4. **REST API & Security**:
   - `POST /api/v1/transactions/{id}/respond`: Operator-only endpoint. Orchestrates response and notification dispatch. Returns HTTP 201 on create and HTTP 200 on replay.
   - `GET /api/v1/transactions/{id}/responses`: Operator-only chronological response history.
   - `GET /api/v1/transactions/{id}/responses/latest`: Operator-only latest executed response.
   - `GET /api/v1/transactions/{id}/intervention`: Accessible by operators or customers possessing a valid verification token scoped to the specific transaction ID. Returns customer-safe data with zero internal risk metrics.

5. **Frontend UI Integration**:
   - `responseApi.ts`: Typed TypeScript client for response orchestration and intervention queries.
   - `CustomerInterventionPanel.tsx`:
     - Step progression pipeline (Assess → Policy → Response → Alert).
     - Response type badge with distinct color-coding (`ALLOW_SETTLED`, `VERIFICATION_REQUIRED`, `HOLD_PROTECTIVE`, `BLOCK_SAFETY`).
     - Customer message card, action badge, and next steps list.
     - Simulated notification dispatch details with masked recipient, delivery pill, and failure callouts.
     - Operator dispatch controls (channel selector, simulated timeout checkbox, execute/replay button).
     - Prominent sandbox simulation disclaimer.
   - Integrated into `App.tsx` within `TransactionDrawer` under both `'Decision & history'` and `'AI Investigation'` tabs.

---

## Consequences

### Positive
- Fully closes the automated loop: transactions progress through risk assessment, policy decision, lifecycle state change, and customer communication autonomously.
- Customers receive protective, non-accusatory advice that discourages compliance with scammers while providing safe official bank channels.
- Guaranteed safety isolation: simulated carrier or communication network timeouts cannot compromise or reverse fraud holds or blocks.
- Full idempotency prevents duplicate alerts or conflicting state transitions on concurrent or replayed operator requests.
- Zero sensitive credentials or internal detection logic leaked to customers or notification logs.

### Negative / Trade-offs
- Additional database tables and relationships require session expiration discipline (`MissingGreenlet` prevention) when handling asynchronous ORM commits and rollbacks.
- Replaying responses on terminal transactions requires handling stale decisions gracefully.

