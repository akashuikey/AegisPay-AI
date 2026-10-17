export PATH := $(HOME)/.local/bin:$(PATH)

.PHONY: help setup db-up db-down db-logs backend-install backend-migrate backend-dev backend-test backend-lint backend-format backend-typecheck frontend-install frontend-dev frontend-test frontend-lint frontend-typecheck frontend-build check-all smoke db-verify-migrations

help:
	@echo "AegisPay AI - Development Commands"
	@echo "=================================="
	@echo "  setup               Initialize .env, install backend and frontend dependencies"
	@echo "  db-up               Start PostgreSQL database container"
	@echo "  db-down             Stop PostgreSQL database container"
	@echo "  db-logs             Follow PostgreSQL container logs"
	@echo "  backend-install     Install backend dependencies via uv"
	@echo "  backend-migrate     Run Alembic migrations to upgrade database schema"
	@echo "  backend-dev         Start FastAPI backend dev server with hot reload"
	@echo "  backend-test        Run backend pytest suite"
	@echo "  backend-lint        Run Ruff lint and formatting checks"
	@echo "  backend-format      Auto-format backend code with Ruff"
	@echo "  backend-typecheck   Run mypy static type analysis"
	@echo "  frontend-install    Install frontend node modules"
	@echo "  frontend-dev        Start Vite frontend dev server"
	@echo "  frontend-test       Run frontend tests"
	@echo "  frontend-lint       Run ESLint on frontend"
	@echo "  frontend-typecheck  Run TypeScript compiler check"
	@echo "  frontend-build      Build production frontend bundle"
	@echo "  check-all           Run all linting, typechecking, and tests"
	@echo "  smoke               Run the demo smoke test against a running backend"
	@echo "  db-verify-migrations Verify upgrade/downgrade/re-upgrade on a disposable DB"

setup:
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example"; fi
	cd backend && uv sync --dev
	cd frontend && npm install

db-up:
	docker compose up -d db

db-down:
	docker compose down

db-logs:
	docker compose logs -f db

backend-install:
	cd backend && uv sync --dev

backend-migrate:
	cd backend && uv run alembic upgrade head

backend-dev:
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

backend-test:
	cd backend && uv run pytest

backend-lint:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .

backend-format:
	cd backend && uv run ruff format .
	cd backend && uv run ruff check --fix .

backend-typecheck:
	cd backend && uv run mypy app

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-test:
	cd frontend && npm run test

frontend-lint:
	cd frontend && npm run lint

frontend-typecheck:
	cd frontend && npm run typecheck

frontend-build:
	cd frontend && npm run build

check-all: backend-lint backend-typecheck backend-test frontend-lint frontend-typecheck frontend-test frontend-build

smoke:
	cd backend && uv run python -I scripts/smoke_test.py

db-verify-migrations:
	@echo "Verifying migrations on a DISPOSABLE database (aegispay_migcheck)..."
	-docker compose exec -T db dropdb --if-exists -U $${POSTGRES_USER:-aegispay_user} aegispay_migcheck
	docker compose exec -T db createdb -U $${POSTGRES_USER:-aegispay_user} aegispay_migcheck
	cd backend && POSTGRES_DB=aegispay_migcheck uv run alembic upgrade head
	cd backend && POSTGRES_DB=aegispay_migcheck uv run alembic downgrade base
	cd backend && POSTGRES_DB=aegispay_migcheck uv run alembic upgrade head
	docker compose exec -T db dropdb -U $${POSTGRES_USER:-aegispay_user} aegispay_migcheck
	@echo "Migration verification complete (disposable DB dropped)."
