# Product Requirements Document (PRD): AegisPay AI

## 1. Executive Summary & Vision

**AegisPay AI** is an intelligent, real-time fraud and coercion prevention system designed for modern digital banking and instant payment environments. It protects retail and small-business banking customers from Authorized Push Payment (APP) fraud, social engineering scams, and coercion.

Unlike traditional fraud prevention systems that solely evaluate historical card transactions or post-facto anomaly detection, AegisPay AI combines:
1. **Pre-execution transaction feature analysis** (velocity, payee risk, amount anomalies).
2. **Deterministic decision policies** (hard velocity limits, high-risk payee quarantines, regulatory stop triggers).
3. **Conversational AI investigations** (voice and contextual inquiry powered by Google Gemini).
4. **Contextual evidence ingestion** (simulated messaging, fake invoices, customer self-reported context).
5. **Auditable transaction lifecycle management** through an explicit finite state machine.

> [!IMPORTANT]
> **Simulation Boundary**:
> All payment rails, bank accounts, UPI/NPCI infrastructure, regulatory networks, customer data, and external communication channels (e.g. WhatsApp, phone calls, SMS) are **strictly simulated**. AegisPay AI does not connect to real-world financial networks, production customer accounts, or external payment gateways.

---

## 2. Product Goals

1. **Intervene Pre-Authorization**: Catch scam-driven and coerced transactions *before* final funds transfer irrevocably leaves the sender's account.
2. **Differentiate Fraud from Coercion**: Recognize signals of duress, urgency, and psychological manipulation (e.g., impersonation of law enforcement, kidnapping/extortion, fake tech support, digital arrest scams).
3. **Enforce Deterministic Governance**: Guarantee that safety guardrails, compliance rules, and risk limits are deterministically enforced and never hallucinated or overridden by generative models.
4. **Transparent & Auditable Decisions**: Provide a full evidentiary audit trail for compliance officers and fraud operations analysts.
5. **Human-in-the-Loop Operational Console**: Give fraud investigators a comprehensive interface to review flagged payments, analyze AI-collected transcripts, inspect extracted documents, and make final determinations.

---

## 3. User Personas & Actors

| Persona | Role | Key Interactions |
| :--- | :--- | :--- |
| **Retail Banking Customer** | Payer initiating transfers | Enters simulated transfer details, answers AI risk questions, interacts with voice/text verification prompts. |
| **Fraud Operations Analyst** | Tier-1 & Tier-2 Investigator | Reviews queued flagged transactions, examines AI investigation transcripts and evidence, approves/rejects transactions. |
| **Risk & Compliance Officer** | Policy Maker & Auditor | Configures deterministic thresholds, reviews state machine audit logs, audits false-positive / false-negative rates. |
| **System / Simulation Engine** | Automated Actor | Emulates payment rail responses, simulates third-party registry lookups (e.g., mule account detection), triggers test scenarios. |

---

## 4. The Six Demo Scenarios

AegisPay AI is demonstrated across six distinct, simulated real-world fraud and coercion scenarios:

### Scenario 1: The "Digital Arrest" / Authority Impersonation Scam
- **Context**: Customer receives an urgent call from an actor posing as national law enforcement (CBI / Police / ED) claiming their identity was used in money laundering.
- **Transaction**: High-value immediate transfer to a "secure government clearance account".
- **Signals**: Extreme urgency, fear cues in voice response, brand-new payee account created minutes prior, user hesitant to speak freely.
- **Outcome**: Immediate freeze, conversational AI detects authority coercion indicators, escalated to Human Fraud Operations.

### Scenario 2: Remote Access & Fake Tech Support Scam
- **Context**: Pop-up alert claims customer's device is infected; user calls fake support hotline and allows screen-sharing software.
- **Transaction**: Attacker guides customer to transfer "temporary funds" or directly attempts multiple rapid transfers.
- **Signals**: Known remote-access signatures, device anomaly, unexpected rapid payee addition, evasive explanation.
- **Outcome**: Deterministic policy halts high-velocity transfers; customer prompted with targeted warning questions.

### Scenario 3: Urgent Coercion / Hostage / Extortion Transfer
- **Context**: Attacker actively threatens customer or family member, demanding instant fund liquidation.
- **Transaction**: Off-hours large transfer, customer attempts to override daily transaction limits.
- **Signals**: Biometric or voice stress, short staccato answers, user answers "Yes" to subtle duress inquiry questions.
- **Outcome**: Silent friction injection, delayed execution window to protect sender safety, priority silent alert dispatched to Operations Console.

### Scenario 4: High-Yield Fake Investment & Crypto Mule Scheme
- **Context**: Customer is lured into an unverified "high-yield guaranteed investment" Telegram group.
- **Transaction**: Series of escalating payments to an individual mule account flagged by consortium intelligence.
- **Signals**: Recipient account age < 14 days, rapid inflows and immediate outflows, recipient bank branch mismatch.
- **Outcome**: Risk engine scores payee intelligence; AI requests proof of invoice/prospectus; document analyzer flags fraudulent corporate documentation.

### Scenario 5: Romance / Long-Con "Emergency" Scam
- **Context**: Scammer builds romantic trust over weeks, then invents an emergency (customs clearance, hospital deposit).
- **Transaction**: Payer sends substantial personal savings to an offshore or intermediary personal account.
- **Signals**: Recipient not in payer's historical social graph, payee has multiple distinct senders across banking network, emotional manipulation narrative detected in user-provided chat exports.
- **Outcome**: Soft-block warning with educational interventions; customer is guided through cooling-off period.

### Scenario 6: Business Email Compromise (BEC) & Fake Vendor Invoice
- **Context**: Payer receives an invoice with altered bank account details claiming to be a trusted supplier.
- **Transaction**: Routine B2B payment amount, but sent to updated payee account coordinates.
- **Signals**: Historical payee name match with bank account number mismatch, invoice PDF layout altered, IBAN/IFSC routing change.
- **Outcome**: Document investigation parses uploaded invoice PDF, compares with historical vendor ledger, alerts payer to routing discrepancy.

---

## 5. Scope & Capabilities

### Phase 1: Implemented in this Foundation (P1-A1)
- Clean root-level monorepo layout with backend, frontend, docs, and infrastructure.
- FastAPI backend with asynchronous SQLAlchemy 2.x and async PostgreSQL driver.
- Typed configuration, environment loading, structured error handling, and structured logging.
- Liveness (`/health/live`) and database readiness (`/health/ready`) health checks.
- React + TypeScript frontend with Vite displaying real backend connection state.
- Docker Compose configuration for PostgreSQL.
- Alembic database migration scaffolding.
- Unit and integration tests, Ruff linting/formatting, mypy typechecking, ESLint and TypeScript checks.
- Comprehensive persistent project governance documentation (`docs/project/`).

### Future Planned Capabilities (Phases 2–5)
- **Domain Entities & State Machine**: Auditable 10-state transaction workflow finite state machine: `INITIATED`, `ASSESSING`, `RISK_ASSESSED`, `DECISION_READY`, `VERIFICATION_REQUIRED`, `HELD_FOR_VERIFICATION`, `INVESTIGATING`, `HUMAN_REVIEW`, `SETTLED_SIMULATED`, `CANCELLED_SIMULATED`. These represent transactional workflow states, separated from risk scoring and decision recommendation policies.
- **Deterministic Risk Engine**: Rule engine evaluating velocity, payee risk scores, account age, and anomaly indicators.
- **Gemini Investigation Agent**: Multi-modal reasoning over voice dialogues and submitted document images/PDFs.
- **Customer Simulation Portal**: Interactive payment creation, challenge response, and simulated customer workflows.
- **Fraud Operations Console**: Case management, transcript review, manual decision overrides, and audit trails.

---

## 6. Acceptance Criteria

1. Backend starts reliably and exposes standardized health endpoints.
2. Frontend loads and dynamically verifies backend health status.
3. Database starts in Docker Compose, runs migrations, and satisfies readiness checks.
4. All code passes linting, formatting, static type checking, and test suites with zero errors.
5. Absolute isolation: zero secrets in version control, zero real external financial service integrations.
