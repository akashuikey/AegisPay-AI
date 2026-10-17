# Project Task Tracker: AegisPay AI

## Implementation Roadmap Overview

| Phase | Description | Status |
| :--- | :--- | :--- |
| **Phase 1** | **Core Banking Simulator & Deterministic Risk Engine** | `DONE` |
| **Phase 2** | **AI Investigation Agent & Multi-Modal Context Analysis** | `NOT_STARTED` |
| **Phase 3** | **Customer Portal & Dynamic Intervention UI** | `NOT_STARTED` |
| **Phase 4** | **Fraud Operations Case Management & Audit Console** | `NOT_STARTED` |
| **Phase 5** | **End-to-End Scenarios, Hardening & Demonstration** | `NOT_STARTED` |

---

## Detailed Task Breakdown

### Phase 1: Repository Foundation & Transaction Domain Core

#### Task P1-A1: AegisPay AI Repository Foundation
- **Owner / Agent**: Senior Architect / Full-Stack Engineer (Agent 1)
- **Status**: `DONE`
- **Objective**: Establish the production-grade monorepo foundation, FastAPI backend, React/Vite frontend, PostgreSQL container setup, typed settings, Alembic migrations, health checks, testing baseline, persistent documentation, and preserved prototype UI.
- **Deliverables**:
  1. Monorepo folder layout (`backend/`, `frontend/`, `docs/`, `compose.yaml`, `Makefile`, `.github/`).
  2. FastAPI async backend with `/health/live` and `/health/ready` endpoints.
  3. React + TypeScript frontend with live backend connectivity indicator and full Aster Bank operations console + mobile simulator.
  4. Docker Compose with PostgreSQL 16 Alpine container and health check.
  5. Alembic async migration configuration (`0001_initial_baseline`).
  6. Unit and integration tests for backend (12 tests) and frontend (7 tests).
  7. Automated linting (Ruff, ESLint), formatting, and type checks (mypy, tsc).
  8. CI workflow in `.github/workflows/ci.yml`.
  9. Project governance docs (`prd.md`, `architecture.md`, `rules.md`, `task.md`, `memory.md`).
- **Acceptance Criteria**:
  - [x] Repository structure created matching specification.
  - [x] Backend starts cleanly and passes all tests (12/12 pytest passed).
  - [x] Frontend starts cleanly and connects to backend health check (verified via live probe badge & test).
  - [x] PostgreSQL runs in Docker Compose with health check (`aegispay_postgres` healthy).
  - [x] Alembic migration executes without error (`0001_initial_baseline` applied).
  - [x] Backend tests pass (`pytest` 12 passed in 0.04s).
  - [x] Backend linters and typecheck pass (`ruff check`, `ruff format`, `mypy` 0 errors).
  - [x] Frontend linters and typecheck pass (`eslint`, `tsc`, `vitest` 0 errors, 7 tests passed).
  - [x] Zero committed secrets, zero real external banking dependencies.
- **Verification Commands & Results**:
  ```bash
  # Docker
  docker compose up -d db                    # Status: Healthy on 127.0.0.1:5433

  # Backend
  cd backend
  uv sync --dev                              # Resolved 46 packages
  uv run alembic upgrade head                # Applied 0001_initial_baseline
  uv run pytest                              # 12 passed in 0.04s
  uv run ruff check .                        # All checks passed
  uv run ruff format --check .               # 23 files already formatted
  uv run mypy app                            # Success: no issues found in 15 source files

  # Frontend
  cd ../frontend
  npm run lint                               # 0 errors, 0 warnings
  npm run typecheck                          # 0 errors
  npm run test                               # 7 passed in 2 test files
  npm run build                              # Built in 530ms
  ```
- **Execution Log & Blocker Notes**:
  - Fully verified Python 3.14.7 compatibility.
  - Extracted and integrated `artifacts/intent-check` from developer prototype archive matching the user screenshot.
  - Resolved port conflict on host by making PostgreSQL port configurable via `POSTGRES_PORT` (configured to 5433 in local `.env`).
  - All acceptance criteria satisfied. Blockers: None.

---

#### Task P1-A2: Transaction Domain Models & State Machine
- **Owner / Agent**: Senior Software Architect / Backend Engineer (Agent 2)
- **Status**: `DONE`
- **Objective**: Implement the transaction domain entity, auditable 10-state workflow finite state machine (`INITIATED`, `ASSESSING`, `RISK_ASSESSED`, `DECISION_READY`, `VERIFICATION_REQUIRED`, `HELD_FOR_VERIFICATION`, `INVESTIGATING`, `HUMAN_REVIEW`, `SETTLED_SIMULATED`, `CANCELLED_SIMULATED`), transition validation rules, SQLAlchemy transaction and audit models, Alembic migration, repository persistence with customer-scoped idempotency and optimistic locking, transaction application service, API request/response schemas, and thin endpoints at `/api/v1/transactions` with unit, database integration, and API tests.
- **Dependencies**: Task P1-A1 completion.
- **Acceptance Criteria**:
  - [x] 10-state transaction lifecycle defined and enforced with domain policy.
  - [x] Decimal-safe monetary arithmetic, customer ID, idempotency key, currency, rail, recipient details.
  - [x] Append-only transaction state transition audit model (`transaction_audits`).
  - [x] SQLAlchemy 2.x async models with indices, unique constraints, and optimistic versioning.
  - [x] Versioned Alembic migration `0002_create_transactions_and_audits.py` created and applied.
  - [x] Repository with customer-scoped idempotency and payload conflict detection.
  - [x] Thin FastAPI endpoints: create, retrieve, bounded list, transition, audit history.
  - [x] Comprehensive unit tests (transitions, invariants, terminal states).
  - [x] Database integration tests with isolated PostgreSQL transactions.
  - [x] API tests covering 201/200 idempotent replay, 404, 409 conflict, and 400 invalid transitions.
  - [x] All linting (Ruff), type checking (mypy), and test suites pass.
  - [x] Existing frontend builds and passes all tests.
- **Verification Commands & Results**:
  ```bash
  cd backend
  uv run alembic upgrade head                # Applied 0002_transactions
  uv run pytest                              # 63 passed in 0.99s
  uv run ruff check .                        # All checks passed!
  uv run ruff format --check .               # 33 files already formatted
  uv run mypy app                            # Success: no issues found in 22 source files
  make check-all                             # All backend and frontend checks passed
  ```
- **Execution Log & Blocker Notes**:
  - Authoritative 10-state lifecycle implemented in `app.domain.state_machine` with `validate_transition()`, `can_transition()`, and `is_terminal()`.
  - Concurrency protected via `(customer_id, idempotency_key)` uniqueness and integer optimistic version locking.
  - Created isolated PostgreSQL `test_aegispay` database for integration tests.
  - All 63 backend tests passed; all frontend unit tests (7 passed) and production build passed without regression. Blockers: None.

---

#### Task P1-A3: Deterministic Risk Engine & Scenario-Driven Assessment
- **Owner / Agent**: Senior Software Architect / Backend Engineer (Agent 3)
- **Status**: `DONE`
- **Objective**: Implement an explainable, deterministic transaction risk engine and integrate it with the existing transaction backend and frontend. Evaluates actual transaction and evidence inputs without ML/LLM dependencies or scenario branching. Differentiates risk levels (LOW, MEDIUM, HIGH, CRITICAL) and recommends policy actions (ALLOW, WARN_CUSTOMER, REQUIRE_VERIFICATION, HOLD_FOR_INVESTIGATION) while explicitly recording missing evidence and preserving state machine lifecycle transitions and audit trails.
- **Dependencies**: Tasks P1-A1 and P1-A2 completion.
- **Acceptance Criteria**:
  - [x] Deterministic feature evaluation: amount/history, first-time vs established recipient, recipient fan-in/fan-out and risk flags, recent financial activity (FD liquidation), behavioral signals (active call, screen sharing), structured context (coercion cues, guaranteed returns, invoice mismatch).
  - [x] Missing evidence explicitly identified and retained as unknown, not silently assumed safe or suspicious.
  - [x] Explainable assessment schema: relative risk score (0-100), risk level, triggered rules with weights/evidence, missing evidence list, recommended action, concise explanation.
  - [x] No scenario IDs, hardcoded scenario scores, or keyword-to-score shortcuts in the engine.
  - [x] State machine integration: transitions from `INITIATED` through `ASSESSING` to `RISK_ASSESSED` and `DECISION_READY` with atomic audit logging.
  - [x] Policy rules enforced: trusted recipient cannot override coercion; voice stress alone is not proof of fraud; all holds/cancellations explicitly simulated.
  - [x] All six demo scenarios evaluated purely on their supplied feature inputs with explainable outcomes.
  - [x] API endpoints exposed and documented: `/api/v1/transactions/{id}/assess` and `/api/v1/risk/evaluate`.
  - [x] Persistence of assessments with Alembic migration (`0003_create_transaction_assessments.py`).
  - [x] React frontend connected to backend assessment endpoints, displaying score, level, evidence, rules, missing fields, and actions in the console and simulator.
  - [x] Full unit and integration test suite covering rules, boundaries, missing evidence, all 6 scenarios, and concurrency.
  - [x] Quality gates (Ruff, mypy, pytest, ESLint, tsc, Vitest, make check-all) pass with zero errors.
- **Verification Commands & Results**:
  ```bash
  cd backend
  uv run alembic upgrade head                # Applied 0003_transaction_assessments
  uv run pytest                              # 78 passed in 1.29s
  uv run ruff check .                        # All checks passed!
  uv run ruff format --check .               # 41 files already formatted
  uv run mypy app                            # Success: no issues found in 28 source files
  cd ../frontend
  npm run lint                               # 0 errors, 0 warnings
  npm run typecheck                          # 0 errors
  npm test                                   # 9 passed in 2 test files
  npm run build                              # Built in 560ms
  make check-all                             # 100% passed across both services
  ```
- **Execution Log & Blocker Notes**:
  - Implemented `RiskEngine` with 11 explainable deterministic rules covering high-value anomaly, elevated amount monitoring, new payee, sudden term deposit liquidation, telephony telemetry (active call + screen share), authority duress / coercion, guaranteed returns investment scheme, coaching to bypass bank warnings, vendor ledger / routing mismatch, consortium mule account hit, mule fan-in / fan-out velocity, vocal stress advisory, and trusted recipient mitigation.
  - Preserved critical policy guardrails: trusted-recipient mitigation is strictly bypassed when active coercion is detected; voice stress alone has a low weight (+5) and cannot block transactions; missing telemetry signals are explicitly surfaced in `missing_evidence` without safe/suspicious assumptions.
  - Built `TransactionAssessmentModel` with JSON columns and linked to `TransactionModel`. Applied Alembic migration `0003_create_transaction_assessments.py`.
  - Created `RiskService` orchestrating the atomic transition flow (`INITIATED` -> `ASSESSING` -> `RISK_ASSESSED` -> `DECISION_READY`) with audit logging.
  - Exposed `POST /api/v1/risk/evaluate`, `GET /api/v1/risk/scenarios`, `POST /api/v1/transactions/{id}/assess`, and `GET /api/v1/transactions/{id}/assessment`.
  - Built frontend `riskApi.ts` client with concrete fixtures for all 6 demo fraud scenarios (`digital_arrest`, `investment_scam`, `fake_invoice`, `mule_network`, `legitimate_high_value`, `ambiguous_payment`).
  - Added dedicated "Risk assessment" drawer tab displaying relative risk score (0-100), severity level pill, recommended action, triggered rules with weights/evidence, supporting findings, and missing telemetry warnings.
  - Added Risk score column to the bank-wide payment activity table.
  - Total tests: 78 backend tests + 9 frontend tests (87 tests total, 100% passing). Blockers: None. Phase 1 complete.

---

### Phase 2: AI Investigation Agent & Multi-Modal Context Analysis
- **Task P2-A1**: Gemini Multimodal Contextual Ingestion & Document Verification (`NOT_STARTED`)
- **Task P2-A2**: Gemini Real-Time Voice Duress & Psychological Analysis Agent (`NOT_STARTED`)

### Phase 3: Customer Portal & Dynamic Intervention UI
- **Task P3-A1**: Simulated Banking Customer Payment Flow & Dynamic Intervention UI (`NOT_STARTED`)

### Phase 4: Fraud Operations Case Management & Audit Console
- **Task P4-A1**: Fraud Operations Case Management & Investigation Console (`NOT_STARTED`)

### Phase 5: End-to-End Scenarios, Hardening & Demonstration
- **Task P5-A1**: End-to-End Integration of the Six Fraud Demo Scenarios (`NOT_STARTED`)
- **Task P5-A2**: Final Security Hardening, Audit Trail Verification & Demo Runbook (`NOT_STARTED`)
