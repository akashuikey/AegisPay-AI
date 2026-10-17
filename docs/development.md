# AegisPay AI Local Development Guide

This guide details how to set up, run, test, and troubleshoot AegisPay AI in a local development environment.

---

## 1. Prerequisites

Ensure you have the following installed on your host system:

- **Python**: 3.14 (or 3.12+).
- **uv**: Modern, ultra-fast Python package and project manager (`>= 0.4.0`).
- **Node.js**: `>= 20.0.0` (LTS) and **npm** (`>= 10.0.0`).
- **Docker & Docker Compose**: Docker Desktop or Docker engine for running PostgreSQL.
- **Git**: For version control.

---

## 2. Quickstart

### Step 1: Clone and Configure Environment

```bash
git clone <repo-url> aegispay-ai
cd aegispay-ai

# Create local environment file from example
cp .env.example .env
```

Review `.env` to ensure database credentials and port allocations suit your machine.

---

### Step 2: Start the Database

Start the PostgreSQL 16 container in the background:

```bash
docker compose up -d db
```

Verify that the database is healthy:

```bash
docker compose ps
```

---

### Step 3: Set Up and Run the Backend

Navigate to `backend/`, sync dependencies, run migrations, and launch the dev server:

```bash
cd backend

# Install dependencies into virtualenv managed by uv
uv sync --dev

# Run database migrations
uv run alembic upgrade head

# Start FastAPI development server with hot-reload
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify backend health in another terminal:

```bash
# Process liveness
curl -i http://127.0.0.1:8000/health/live

# Database readiness
curl -i http://127.0.0.1:8000/health/ready
```

---

### Step 4: Set Up and Run the Frontend

Open a new terminal, navigate to `frontend/`, install dependencies, and launch Vite:

```bash
cd frontend

# Install node dependencies
npm install

# Start Vite dev server
npm run dev
```

Visit [http://localhost:5173](http://localhost:5173) in your browser. The AegisPay AI dashboard will display a live indicator confirming active communication with the backend.

---

## 3. Makefile Shortcuts

For convenience, a root `Makefile` provides common operational tasks:

```bash
# Complete initial setup
make setup

# Database management
make db-up
make db-down
make db-logs

# Backend
make backend-dev
make backend-test
make backend-lint
make backend-typecheck

# Frontend
make frontend-dev
make frontend-test
make frontend-lint
make frontend-typecheck
make frontend-build

# Run all checks across both services
make check-all
```

---

## 4. Code Quality & Testing

### Backend Checks

From `backend/`:

```bash
# Run test suite
uv run pytest

# Check linting rules
uv run ruff check .

# Check formatting
uv run ruff format --check .

# Run static type checking
uv run mypy app
```

### Frontend Checks

From `frontend/`:

```bash
# Run unit tests
npm run test

# Run ESLint
npm run lint

# Run TypeScript compiler typecheck
npm run typecheck

# Build production bundle
npm run build
```

---

## 5. Troubleshooting & FAQ

### Database Connection Refused
- **Symptom**: `GET /health/ready` returns HTTP 503 `{"status": "not_ready", "database": "unavailable"}`.
- **Fix**: Check `docker compose ps`. If the `db` container is not healthy, run `docker compose logs db` to inspect PostgreSQL startup errors. Ensure port `5432` is not occupied by a host PostgreSQL instance.

### `uv` not found in PATH
- **Fix**: On macOS/Linux, `uv` is typically installed under `~/.local/bin` or `~/.cargo/bin`. Add `export PATH="$HOME/.local/bin:$PATH"` to your `~/.zshrc` or `~/.bashrc`.

### Frontend cannot connect to Backend
- **Symptom**: Frontend shows "Backend Unavailable" with an error message.
- **Fix**: Ensure the backend is running at `http://127.0.0.1:8000`. If running on a different port or host, create `frontend/.env.local` and set `VITE_API_BASE_URL=http://your-host:your-port`. Note that all `VITE_*` variables are bundled into client-side JavaScript and must never contain sensitive keys.
