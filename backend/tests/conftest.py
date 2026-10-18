"""Shared test configuration, fixtures, and HTTP client setup."""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.db.models  # noqa: F401
from app.api.investigations import get_default_ai_client
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.services.ai_client import MockGeminiClient


def get_test_settings() -> Settings:
    """Return isolated test settings."""
    return Settings(
        APP_NAME="AegisPay AI Test",
        APP_ENV="test",
        DEBUG=True,
        LOG_LEVEL="DEBUG",
        POSTGRES_DB="test_aegispay",
        CORS_ORIGINS=["http://testserver"],
        AUTH_JWT_SECRET="test-jwt-secret-not-for-production",
        AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=60,
        VERIFICATION_EXPOSE_DEV_OTP=True,
        GEMINI_API_KEY=None,
        GCP_PROJECT_ID=None,
        # Keep tests hermetic and independent of a developer .env that may enable
        # Live voice; individual tests opt in via model_copy(update=...).
        GEMINI_LIVE_ENABLED=False,
    )


_test_engine: AsyncEngine | None = None
_test_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_test_engine() -> AsyncEngine:
    """Provide a singleton async engine for test database interactions."""
    global _test_engine
    if _test_engine is None:
        settings = get_test_settings()
        _test_engine = create_async_engine(
            settings.async_database_url,
            pool_pre_ping=True,
        )
    return _test_engine


def get_test_session_factory() -> async_sessionmaker[AsyncSession]:
    """Provide a sessionmaker for test database sessions."""
    global _test_sessionmaker
    if _test_sessionmaker is None:
        _test_sessionmaker = async_sessionmaker(
            bind=get_test_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _test_sessionmaker


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db() -> AsyncGenerator[None, None]:
    """Prepare database tables in test database once per test session."""
    engine = get_test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Seed fictional recipient registry for tests
    from app.repositories.recipient_repository import RecipientRepository

    session_factory = get_test_session_factory()
    async with session_factory() as session:
        await RecipientRepository(session).seed_if_needed()

    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a direct database session for integration assertions."""
    session_factory = get_test_session_factory()
    async with session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
def reset_login_rate_limiter() -> None:
    """Clear the in-process login throttle so its state never leaks across tests."""
    from app.core.rate_limit import login_rate_limiter

    login_rate_limiter.reset()


@pytest.fixture(autouse=True)
async def clean_database_after_test() -> AsyncGenerator[None, None]:
    """Clean all table rows after each test run to ensure strict isolation."""
    yield
    session_factory = get_test_session_factory()
    async with session_factory() as session:
        try:
            await session.execute(
                text(
                    "TRUNCATE TABLE scenario_runs, transaction_notifications, "
                    "transaction_responses, transaction_coercion_analyses, "
                    "verification_challenges, transaction_decisions, transaction_investigations, "
                    "transaction_assessments, transaction_audits, transactions, operators "
                    "RESTART IDENTITY CASCADE;"
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()


@pytest.fixture
def test_settings() -> Settings:
    """Fixture providing isolated test settings."""
    return get_test_settings()


def _build_test_app() -> FastAPI:
    """Construct the app with test DB session and mock AI client overrides."""
    app = create_app()

    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        session_factory = get_test_session_factory()
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_settings] = get_test_settings
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_default_ai_client] = lambda: MockGeminiClient()
    return app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Authenticated HTTP client: a stub operator is injected for console routes.

    The real authentication pipeline is exercised separately in the auth test
    suite; here we inject an operator so existing business-logic tests continue
    to verify behavior behind the auth boundary without logging in each time.
    """
    import uuid as _uuid

    from app.api.auth import get_current_operator
    from app.api.customer_dialogue import (
        get_current_operator_optional as get_current_operator_optional_dialogue,
    )
    from app.api.fraud_responses import get_current_operator_optional
    from app.db.models import OperatorModel

    app = _build_test_app()
    stub_operator = OperatorModel(
        id=_uuid.uuid4(),
        username="test_operator",
        password_hash="unused",
        is_active=True,
    )
    app.dependency_overrides[get_current_operator] = lambda: stub_operator
    app.dependency_overrides[get_current_operator_optional] = lambda: stub_operator
    app.dependency_overrides[get_current_operator_optional_dialogue] = lambda: stub_operator

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client

    app.dependency_overrides.clear()


@pytest.fixture
async def unauth_client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client with the real authentication boundary intact (no operator injected)."""
    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client

    app.dependency_overrides.clear()
