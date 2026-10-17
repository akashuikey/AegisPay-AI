# AegisPay AI

[![CI](https://github.com/aegispay/aegispay-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/aegispay/aegispay-ai/actions)
![Python](https://img.shields.io/badge/Python-3.14-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688)
![React](https://img.shields.io/badge/React-19.0-61DAFB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6)
![Vite](https://img.shields.io/badge/Vite-6.0-646CFF)

**AegisPay AI** is a simulated real-time banking fraud and coercion prevention platform. It safeguards authorized push payments (APP) and instant transfers through pre-authorization risk scoring, deterministic decision policies, and contextual multi-modal investigations.

> [!IMPORTANT]
> **Safety & Simulation Guardrail**:
> All payment rails, accounts, UPI/NPCI interfaces, identity registries, and external messaging channels are **strictly simulated**. AegisPay AI does not connect to real financial networks, real customer bank accounts, or external payment gateways.

---

## 1. Architecture Overview

AegisPay AI is implemented as a **Modular Monolith** designed for high auditability, rigorous type safety, and clean separation between deterministic rules and heuristic AI investigations:

```text
aegispay-ai/
├── backend/                  # Asynchronous FastAPI backend
│   ├── app/
│   │   ├── api/              # HTTP routers (/health, /api/v1)
│   │   ├── core/             # Typed config, structured logging & errors
│   │   ├── db/               # Async SQLAlchemy 2.x session & Alembic migrations
│   │   ├── domain/           # Pure domain entities & finite state machine (Phase 1-A2)
│   │   ├── repositories/     # Data access layer (Phase 1-A2)
│   │   ├── schemas/          # Pydantic schemas (Phase 1-A2)
│   │   ├── services/         # Application workflow services (Phase 1-A2)
│   │   └── main.py           # Application entrypoint & lifespan
│   ├── tests/                # Async unit and integration test suite
│   ├── pyproject.toml        # Backend dependencies & tool configs (uv)
│   └── alembic.ini           # Database migration settings
├── frontend/                 # React 19 + TypeScript frontend
│   ├── src/
│   │   ├── components/       # UI components (HealthStatus probe)
│   │   ├── App.tsx           # Foundation page layout
│   │   └── config.ts         # Public client configuration
│   ├── package.json          # Node dependencies & npm scripts
│   └── vite.config.ts        # Vite & Vitest configuration
├── docs/                     # Documentation & Decision Records
│   ├── architecture.md       # High-level architecture summary
│   ├── development.md        # Local development setup & troubleshooting
│   ├── decisions/            # Architecture Decision Records (ADR-001)
│   └── project/              # Authoritative persistent project context
│       ├── prd.md            # Vision, scope & 6 demo fraud scenarios
│       ├── architecture.md   # Architectural boundaries & component details
│       ├── rules.md          # Agent operational rules & prohibitions
│       ├── task.md           # Implementation phase tracker & verification results
│       └── memory.md         # Confirmed decisions & active state
├── .github/workflows/ci.yml  # GitHub Actions CI workflow
├── compose.yaml              # Docker Compose for PostgreSQL 16 Alpine
├── Makefile                  # Developer workflow automation
├── .env.example              # Safe environment variable template
└── .gitignore                # Comprehensive Git exclusion rules
```

---

## 2. Prerequisites

Ensure you have the following installed:

- **Python**: 3.14 (or 3.12+)
- **uv**: `>= 0.4.0` (Fast Python package manager)
- **Node.js**: `>= 20.0.0` (LTS) & **npm**
- **Docker & Docker Compose**: For local PostgreSQL container

---

## 3. Quickstart

### 1. Environment Setup

```bash
# Clone the repository
git clone <repo-url> aegispay-ai
cd aegispay-ai

# Copy safe default environment configuration
cp .env.example .env
```

### 2. Start PostgreSQL Database

```bash
docker compose up -d db
```

Verify that the database container is healthy:

```bash
docker compose ps
```

### 3. Run Backend Service

```bash
cd backend

# Install dependencies into virtualenv managed by uv
uv sync --dev

# Run database migrations
uv run alembic upgrade head

# Start FastAPI dev server with hot reload
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify endpoints in your browser or terminal:
- Liveness: [http://127.0.0.1:8000/health/live](http://127.0.0.1:8000/health/live)
- Readiness: [http://127.0.0.1:8000/health/ready](http://127.0.0.1:8000/health/ready)
- Interactive Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 4. Run Frontend Client

```bash
cd frontend

# Install npm dependencies
npm install

# Start Vite development server
npm run dev
```

Visit [http://localhost:5173](http://localhost:5173). The dashboard will display a live status card verifying active backend and database connectivity.

---

## 4. Verification & Testing

### Using the Root Makefile

```bash
# Run all quality checks across backend and frontend
make check-all

# Or run individual targets:
make backend-test        # Run pytest suite
make backend-lint        # Run Ruff check & format
make backend-typecheck   # Run mypy on backend
make frontend-test       # Run Vitest suite
make frontend-lint       # Run ESLint on frontend
make frontend-typecheck  # Run tsc on frontend
make frontend-build      # Build production frontend bundle
```

---

## 5. Demo Runbook (Scenario Lab)

This reproduces the end-to-end demo on a clean machine. All outcomes are simulated.

### 5.1 One-time setup

```bash
cp .env.example .env
# For the local demo, enable the dev-only OTP display so the verification flow is
# completable. This is automatically ignored outside development/test environments.
#   APP_ENV=development
#   VERIFICATION_EXPOSE_DEV_OTP=true
#   AUTH_BOOTSTRAP_OPERATOR_USERNAME=operator
#   AUTH_BOOTSTRAP_OPERATOR_PASSWORD=<choose-a-local-password>
```

> The default `POSTGRES_PORT` is `5432`. If `5432` is already in use locally, set
> `POSTGRES_PORT=5433` in `.env` (Docker Compose and the backend both read it).

### 5.2 Start everything

```bash
docker compose up -d db                 # PostgreSQL 16 (bound to 127.0.0.1 only)
cd backend && uv sync --dev
uv run alembic upgrade head             # apply migrations
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# in a second terminal:
cd frontend && npm install && npm run dev
```

On startup the backend provisions the bootstrap operator from
`AUTH_BOOTSTRAP_OPERATOR_USERNAME` / `_PASSWORD`. Log in at
[http://localhost:5173](http://localhost:5173) with those credentials.

### 5.3 Smoke test (validates health + essential demo endpoints)

```bash
# backend must be running; reads operator creds from AUTH_BOOTSTRAP_OPERATOR_* or SMOKE_OPERATOR_*
make smoke
```

It checks liveness/readiness, logs in, lists the scenario catalogue, and runs one
fraud scenario (expects a protective hold) and one legitimate scenario (expects a
simulated settlement). It never prints secrets or OTP values.

### 5.4 Mock/deterministic vs live-provider mode

- **Deterministic (mock)** — the default for the Scenario Lab. Uses an offline mock
  AI provider so runs are reproducible and need no credentials. Recommended for demos.
- **Live provider** — explicitly selected per run. Uses the configured Google
  Gemini / Vertex AI provider (`AI_PROVIDER`, `GCP_PROJECT_ID` or `GEMINI_API_KEY`).
  If credentials are missing, the AI stages are reported `UNAVAILABLE` and the
  deterministic policy still applies — the system never silently falls back to mock.

### 5.5 Scenario Lab walkthrough

1. Sign in, then open the **Scenario Lab** tab in the console.
2. Keep **Execution mode = Deterministic** and run **Digital Arrest / Authority
   Impersonation**. Expected: a protective hold (`HELD_FOR_VERIFICATION`,
   `HOLD_PROTECTIVE`), coercion analysis completed, and an expected-vs-actual
   **MATCH**.
3. Run **Legitimate High-Value Lease Payment**. Expected: simulated settlement
   (`SETTLED_SIMULATED`, `ALLOW_SETTLED`) and a **MATCH** — a legitimate transfer is
   not treated as fraud.
4. Inspect the timeline for stage states, evidence references, and the clear
   distinction between *workflow executed successfully* and *decision matched the
   expectation*.

### 5.6 Verify database migration integrity (disposable DB)

```bash
# Creates aegispay_migcheck, runs upgrade -> downgrade -> re-upgrade, then drops it.
make db-verify-migrations
```

This never touches your development database.

### 5.7 Troubleshooting

| Symptom | Likely cause & fix |
| :--- | :--- |
| `/health/ready` returns 503 | Database not up or wrong port. `docker compose ps`; ensure `POSTGRES_PORT` in `.env` matches the mapped port. |
| `AUTH_CONFIGURATION_ERROR` / cannot log in | `AUTH_JWT_SECRET` is empty. Set a long random value in `.env`. |
| Login succeeds but console is empty / 401 loops | Token expired; log in again. Check the browser points `VITE_API_BASE_URL` at the backend. |
| `alembic upgrade` fails | Confirm the DB is reachable and `POSTGRES_*` are correct; run `make db-verify-migrations` on a disposable DB to isolate schema issues. |
| OTP not shown in the verification demo | Set `APP_ENV=development` and `VERIFICATION_EXPOSE_DEV_OTP=true`. It is force-disabled in non-dev environments. |
| Live-provider scenario shows AI stages `UNAVAILABLE` | No Gemini/Vertex credentials configured. Use Deterministic mode or set `GCP_PROJECT_ID`/`GEMINI_API_KEY`. |
| Frontend cannot reach backend | Set `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`) and confirm CORS `CORS_ORIGINS` includes the frontend origin. |

---

## 6. Security & Sensitive Data Guidelines

- All backend secrets and database passwords are loaded exclusively through environment variables.
- Raw exception traces and internal details are never leaked in API error responses.
- All frontend variables prefixed with `VITE_` (such as `VITE_API_BASE_URL`) are public to the browser bundle. Never put confidential tokens or keys in `VITE_*` variables.
- Strict operational rules and simulation boundaries are enforced per [docs/project/rules.md](docs/project/rules.md).
