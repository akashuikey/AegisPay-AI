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

- **Current Milestone**: Phase 1 — Repository Foundation & Transaction Domain Core (`DONE`).
- **Completed Tasks**:
  - **P1-A1**: Repository foundation, FastAPI backend, Aster Bank frontend prototype preservation, PostgreSQL Docker Compose, Alembic baseline, and health probes.
  - **P1-A2**: 10-state transaction workflow state machine (`INITIATED`, `ASSESSING`, `RISK_ASSESSED`, `DECISION_READY`, `VERIFICATION_REQUIRED`, `HELD_FOR_VERIFICATION`, `INVESTIGATING`, `HUMAN_REVIEW`, `SETTLED_SIMULATED`, `CANCELLED_SIMULATED`), SQLAlchemy models (`TransactionModel`, `TransactionAuditModel`), Alembic migration `0002_create_transactions_and_audits`, transaction repository with optimistic concurrency locking and customer-scoped idempotency, transaction service, Pydantic v2 schemas, REST endpoints (`/api/v1/transactions`), 63 pytest unit/integration tests, and full test isolation on `test_aegispay`.
- **Next Milestone**: Phase 2 — Simulation Ingestion & Deterministic Risk Engine.
  - Next task: **P2-A1**: Simulated Payment Ingestion API & Recipient Intelligence Registry.

---

## 4. Confirmed Decisions & Architectural Patterns

- **State Machine Architecture**: Authoritative 10-state workflow lifecycle implemented in `app.domain.state_machine`. Pure domain logic with `validate_transition`, `can_transition`, and `is_terminal`. Raises `InvalidStateTransitionError` (HTTP 400).
- **Idempotency Strategy**: Scoped per `(customer_id, idempotency_key)` backed by PostgreSQL unique constraint. Canonical SHA-256 payload hash is recorded. Re-execution with exact payload returns HTTP 200 OK; re-execution with conflicting payload returns HTTP 409 Conflict (`IdempotencyConflictError`).
- **Concurrency Control**: Optimistic version locking via integer `version` incremented on each state change. Raises `ConcurrencyConflictError` (HTTP 409) if version is stale.
- **Audit Integrity**: Append-only `transaction_audits` recorded atomically in the same database transaction as transaction creation and updates.
- **Testing Strategy**: Isolated test database `test_aegispay` on PostgreSQL container with automatic table teardown and truncation per test run.

---

## 5. Next Immediate Actions (Phase 2 Initiation)

1. Review requirements for Task P2-A1 (Simulated Payment Ingestion API & Recipient Intelligence Registry).
2. Design recipient intelligence models (reputation, account age, scam report count, risk flags).
3. Implement ingestion schemas and recipient validation pipelines.
