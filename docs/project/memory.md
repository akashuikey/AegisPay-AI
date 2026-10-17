# Persistent Project Memory: AegisPay AI

## 1. Confirmed Decisions

- **Architecture**: Modular Monolith. All core domains (transactions, risk engine, investigation orchestration) exist within a single deployable backend package with strict internal boundaries.
- **Backend Tech Stack**:
  - Python 3.14 (fully verified compatible with required dependencies).
  - FastAPI + Uvicorn for asynchronous REST API.
  - Pydantic v2 + `pydantic-settings` for typed configuration and request validation.
  - SQLAlchemy 2.x asynchronous ORM with `psycopg` (v3) async driver (`postgresql+psycopg://`).
  - Alembic for database migrations.
  - `uv` for dependency and virtual environment management.
  - Ruff (linting & formatting) and mypy (typechecking).
  - pytest + pytest-asyncio + HTTPX for testing.
- **Frontend UI Prototype Preservation & Reuse**:
  - Inspected `Intent-Check-Fintech-Prototype.zip` supplied by developer.
  - Identified `artifacts/intent-check` as the exact source matching the supplied screenshot (`Aster Bank` / Live payment console with 6-metric summary strip, bank-wide payment activity queue, and interactive customer Android device preview simulator).
  - Preserved the full interactive design, mobile simulator (with voice and chat simulation), scenario switcher (`routine`, `impersonation`, `verified`, `unavailable`, `agent`), drawer inspection panels, and audit event logs.
  - Connected the frontend to the new FastAPI backend health probes (`/health/ready` and `/health/live`) without modifying the core user journeys or rewriting the UI from scratch.
  - Excluded Replit-specific plugins, Express api-server stubs, and Drizzle artifacts.

---

## 2. Repository Conventions

- **Paths**:
  - `backend/app/`: Application source code.
  - `backend/tests/`: Unit and integration test suites.
  - `frontend/src/`: React source code.
  - `docs/project/`: Persistent project governance documents (`prd.md`, `architecture.md`, `rules.md`, `task.md`, `memory.md`).
- **Configuration**:
  - Backend reads `.env` via `app.core.config.Settings`.
  - Frontend reads `VITE_API_BASE_URL` from Vite env vars.
  - Secrets are never committed; safe defaults in `.env.example`.
- **Health Check Conventions**:
  - `GET /health/live`: Fast process liveness check (HTTP 200, no external dependencies).
  - `GET /health/ready`: Database dependency readiness check (`SELECT 1`). Returns HTTP 200 on success, HTTP 503 on failure.

---

## 3. Current Milestone & Status

- **Current Milestone**: Phase 1 — Core Banking Simulator & Deterministic Risk Engine (`DONE`).
- **Active Task**: All Phase 1 tasks complete (`P1-A1`, `P1-A2`, `P1-A3`). Ready for Phase 2 kickoff.
- **Completed Tasks**:
  - **P1-A1**: Repository foundation, FastAPI backend, Aster Bank frontend prototype preservation, PostgreSQL Docker Compose, Alembic baseline, and health probes.
  - **P1-A2**: 10-state transaction workflow state machine (`INITIATED`, `ASSESSING`, `RISK_ASSESSED`, `DECISION_READY`, `VERIFICATION_REQUIRED`, `HELD_FOR_VERIFICATION`, `INVESTIGATING`, `HUMAN_REVIEW`, `SETTLED_SIMULATED`, `CANCELLED_SIMULATED`), SQLAlchemy models (`TransactionModel`, `TransactionAuditModel`), Alembic migration `0002_create_transactions_and_audits`, transaction repository with optimistic concurrency locking and customer-scoped idempotency, transaction service, Pydantic v2 schemas, REST endpoints (`/api/v1/transactions`), 63 pytest unit/integration tests, and full test isolation on `test_aegispay`.
  - **P1-A3**: Deterministic Risk Engine & Scenario-Driven Assessment. Pure domain evaluation with 11 explainable rules; mandatory guardrails (coercion overrides trusted beneficiary, voice stress is advisory only, missing evidence explicitly tagged as unknown); benchmark scenario fixtures for all 6 demo fraud scenarios; `transaction_assessments` database table with Alembic migration `0003_create_transaction_assessments`; `RiskService` with atomic lifecycle transitions (`INITIATED` -> `ASSESSING` -> `RISK_ASSESSED` -> `DECISION_READY`) and audit trail; REST endpoints `POST /api/v1/risk/evaluate`, `GET /api/v1/risk/scenarios`, `POST /api/v1/transactions/{id}/assess`, and `GET /api/v1/transactions/{id}/assessment`; frontend Aster Bank integration with risk score column, scenario switcher, and dedicated Risk Assessment drawer tab; 100% green test suite (78 backend tests, 9 Vitest frontend tests).
  - **P1-A4**: Risk Engine Verification and Demo Readiness. Verified all 6 scenario fixtures with explainable scores, rules, missing telemetry, and policy actions; confirmed active-call and voice-stress alone never block; verified coercion overrides trusted recipient; confirmed ambiguous signals remain unblocked; clearly separated live backend evaluations (`source: 'backend'`, green pill) from demo fallback (`source: 'demo_fallback'`, amber pill and warning banner); verified clean database migrations (`0001` -> `0002` -> `0003`); added tests for repeated assessments, full transition lifecycle with atomic audits, optimistic locking, and simulated-only state boundaries; 94 total tests (84 backend, 10 frontend) passing with zero failures.

---

## 4. Confirmed Decisions & Architectural Patterns

- **Task-Tracker Realignment**: In accordance with user requirements, the Deterministic Risk Engine belongs to Phase 1, and the AI Investigation Agent belongs to Phase 2.
- **State Machine Architecture**: Authoritative 10-state workflow lifecycle implemented in `app.domain.state_machine`. Pure domain logic with `validate_transition`, `can_transition`, and `is_terminal`.
- **Deterministic Risk Engine Principles**:
  - Feature evaluation from concrete transaction and evidence inputs only (zero ML / LLM in Phase 1).
  - No scenario IDs, scenario names, or keyword shortcuts in scoring logic.
  - Missing evidence is explicitly captured as unknown, never silently assumed safe or dangerous.
  - Relative risk score (0–100), risk levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and policy recommendations (`ALLOW`, `WARN_CUSTOMER`, `REQUIRE_VERIFICATION`, `HOLD_FOR_INVESTIGATION`, `BLOCK_SIMULATED`).
  - Core guardrail: Trusted recipient status CANNOT override strong coercion indicators. Voice stress alone is NOT proof of fraud.
- **Idempotency Strategy**: Scoped per `(customer_id, idempotency_key)` backed by PostgreSQL unique constraint and canonical SHA-256 payload hash.
- **Concurrency Control**: Optimistic version locking via integer `version` incremented on each state change.
- **Audit Integrity**: Append-only `transaction_audits` recorded atomically in the same database transaction.
- **Risk Assessment History**: Persisted in `transaction_assessments` table, retaining complete input snapshot, triggered rules, supporting evidence, and missing evidence.

---

## 5. Next Phase / Tasks (Awaiting User Directive)

- **Phase 2 Kickoff**: Multi-Modal AI Investigation Agent & Coercion Voice Analysis.
  - P2-A1: Gemini-powered investigation agent & evidence synthesis.
  - P2-A2: Real-time coercion detection & voice interview pipeline.
  - P2-A3: Operator console AI investigation panel & simulation controls.

