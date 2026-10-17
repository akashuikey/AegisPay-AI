# ADR-001: Initial Architecture Baseline & Technology Stack

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Senior Software Architect / Full-Stack Engineer

---

## Context and Problem Statement

AegisPay AI requires a robust, testable, and secure software foundation to simulate real-time banking fraud and coercion detection. The system must support future conversational AI investigations, deterministic rule evaluations, and auditable transaction state transitions without incurring unnecessary distributed systems complexity early in development.

We need to establish:
1. Architectural style (monolith vs. microservices).
2. Backend runtime, framework, ORM, and dependency tooling.
3. Frontend framework and build tooling.
4. Database engine, driver, and migration strategy.
5. Containerization and continuous integration baseline.

---

## Decision Drivers

- **Simplicity & Velocity**: Minimize operational friction; avoid premature microservices, message queues, and API gateways.
- **Type Safety & Maintainability**: End-to-end static typing across both backend (Python type annotations, mypy) and frontend (TypeScript).
- **Asynchronous Performance**: Modern async I/O for API handling and database queries to support future concurrent voice and chat streaming.
- **Auditable & Deterministic Execution**: Clear boundaries between deterministic safety rules and AI-generated investigative signals.
- **Security & Secret Hygiene**: Absolute zero leakage of credentials, tracebacks, or production tokens.

---

## Considered Options

1. **Option 1: Microservices architecture** (Separate Auth, Transaction, Risk, and AI services using Kafka/RabbitMQ).
2. **Option 2: Modular Monolith** (Single deployable codebase with strict internal module boundaries, domain isolation, and shared relational database).
3. **Option 3: Serverless / Cloud Functions** (Dispersed cloud functions triggered by events).

---

## Decision Outcome

**Chosen Option: Option 2 — Modular Monolith**

### Key Selections:

1. **Backend**:
   - **Language**: Python 3.14 (newest supported release, verified compatible with dependency matrix).
   - **Framework**: FastAPI with Uvicorn (async ASGI, native OpenAPI schema generation).
   - **Validation & Settings**: Pydantic v2 + `pydantic-settings`.
   - **ORM & Driver**: SQLAlchemy 2.x (asyncio) with `psycopg` (v3) async driver (`postgresql+psycopg://`).
   - **Migrations**: Alembic with async migration runner.
   - **Package Management**: `uv` for ultra-fast, deterministic virtual environments.
   - **Quality**: Ruff (linter/formatter), mypy (strict typechecker), pytest + pytest-asyncio + HTTPX.

2. **Frontend**:
   - **Framework**: React 19 + TypeScript.
   - **Bundler & Tooling**: Vite with npm, ESLint, and Vitest.

3. **Infrastructure**:
   - **Database**: PostgreSQL 16 Alpine running in Docker Compose with a health check and named volume.
   - **Host Execution**: Backend and frontend run directly on the host during local development for rapid hot-reloading.
   - **CI**: GitHub Actions workflow running linting, typechecking, and test suites.

---

## Positive Consequences

- Clean modular structure eliminates network latency and distributed failure modes between internal domains.
- Fully typed data contracts from database models to API schemas and frontend components.
- Instant development server feedback with Vite and Uvicorn hot-reloading.
- Reproducible, hermetic dependency resolution via `uv` lockfiles.
- Standardized health probes (`/health/live` and `/health/ready`) enable zero-downtime orchestration when deployed.

---

## Negative Consequences & Mitigation

- **Risk of tight coupling**: Engineers might inadvertently import across modular boundaries.
  - *Mitigation*: Enforced strict layer boundaries documented in `rules.md` and verified during code reviews.
- **Single database bottleneck**: Potential contention under massive multi-tenant scale.
  - *Mitigation*: Proper connection pooling (`pool_size`, `max_overflow`), connection recycling (`pool_pre_ping`), and indexed domain schemas.
