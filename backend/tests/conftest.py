"""Shared test configuration, fixtures, and HTTP client setup."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.db.models  # noqa: F401
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app


def get_test_settings() -> Settings:
    """Return isolated test settings."""
    return Settings(
        APP_NAME="AegisPay AI Test",
        APP_ENV="test",
        DEBUG=True,
        LOG_LEVEL="DEBUG",
        POSTGRES_DB="test_aegispay",
        CORS_ORIGINS=["http://testserver"],
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
async def clean_database_after_test() -> AsyncGenerator[None, None]:
    """Clean all table rows after each test run to ensure strict isolation."""
    yield
    session_factory = get_test_session_factory()
    async with session_factory() as session:
        try:
            await session.execute(
                text(
                    "TRUNCATE TABLE transaction_assessments, transaction_audits, "
                    "transactions RESTART IDENTITY CASCADE;"
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()


@pytest.fixture
def test_settings() -> Settings:
    """Fixture providing isolated test settings."""
    return get_test_settings()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an asynchronous HTTP client bound to the test application."""
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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client

    app.dependency_overrides.clear()
