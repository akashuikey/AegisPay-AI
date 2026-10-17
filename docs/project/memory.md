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

- **Current Milestone**: Phase 1 — Repository Foundation & Transaction Domain Core.
- **Current Task**: P1-A1 — AegisPay AI Repository Foundation (`DONE`).
- **Completed Work**:
  - Established root monorepo architecture with clean layer separation (`backend/`, `frontend/`, `docs/`, `compose.yaml`, `Makefile`).
  - Verified Python 3.14.7 compatibility across FastAPI, Pydantic v2, SQLAlchemy 2, psycopg 3, Alembic, Ruff, mypy, and Pytest.
  - Implemented typed settings (`app/core/config.py`), structured logging (`app/core/logging.py`), and safe error handling (`app/core/errors.py`).
  - Configured async SQLAlchemy session factory, connection pooling, and Alembic migrations (`0001_initial_baseline`).
  - Implemented and verified `/health/live` (process liveness) and `/health/ready` (database dependency readiness).
  - Preserved the existing prototype UI (`artifacts/intent-check`), integrating the Aster Bank live payment console, payment queue, and interactive customer mobile simulator into `frontend/src/App.tsx`.
  - Added live `BackendHealthBadge` connecting the frontend to the FastAPI health API.
  - Configured Docker Compose for PostgreSQL 16 Alpine with health check.
  - Configured GitHub Actions CI workflow (`.github/workflows/ci.yml`).
  - Verified 100% passing tests (12 backend, 7 frontend), 0 lint/format issues, and successful production build.
  - Initialized all mandatory project governance files (`docs/project/`).

---

## 4. Proposals & Unresolved Questions

- *None. All P1-A1 requirements and acceptance criteria have been satisfied.*

---

## 5. Next Immediate Actions (Recommended for Phase 1, Agent 2)

- **Assigned Task**: Task P1-A2 — Transaction Domain Models & State Machine.
- **Scope**:
  1. Define the Transaction domain entity and auditable 7-state finite state machine (`PENDING_EVALUATION`, `EVALUATING`, `APPROVED`, `FLAGGED`, `IN_INVESTIGATION`, `BLOCKED`, `SETTLED`).
  2. Implement transition validation rules and state machine history ledger.
  3. Map SQLAlchemy models and generate versioned Alembic migration `0002_create_transactions_table.py`.
  4. Implement repository layer for atomic state transitions.
  5. Add unit and integration tests for all valid/invalid state transitions.
- *Note: Agent 1 stops here. Do not begin Agent 2 automatically.*
