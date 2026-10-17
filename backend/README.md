# AegisPay AI Backend

Asynchronous backend service for AegisPay AI built with FastAPI, SQLAlchemy 2.x, psycopg3, and Pydantic v2.

## Quickstart

```bash
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```
