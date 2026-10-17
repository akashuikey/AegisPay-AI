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

## 5. Security & Sensitive Data Guidelines

- All backend secrets and database passwords are loaded exclusively through environment variables.
- Raw exception traces and internal details are never leaked in API error responses.
- All frontend variables prefixed with `VITE_` (such as `VITE_API_BASE_URL`) are public to the browser bundle. Never put confidential tokens or keys in `VITE_*` variables.
- Strict operational rules and simulation boundaries are enforced per [docs/project/rules.md](docs/project/rules.md).
