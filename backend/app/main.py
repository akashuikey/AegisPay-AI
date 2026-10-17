"""FastAPI application factory and main entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.router import router as api_v1_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import get_logger, setup_logging
from app.db.session import close_database_engine

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    # Startup: Initialize logging and verify configuration
    setup_logging()
    settings = get_settings()
    logger.info(
        "Starting %s [env=%s, log_level=%s]",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.LOG_LEVEL,
    )

    # Provision the configured bootstrap operator so the demo has a login.
    from app.db.session import get_session_factory
    from app.services.auth_bootstrap import ensure_bootstrap_operator

    try:
        await ensure_bootstrap_operator(get_session_factory(), settings)
    except Exception:  # noqa: BLE001 - startup bootstrap must not crash the app boundary
        logger.exception("Bootstrap operator provisioning failed; continuing startup.")

    yield

    # Shutdown: Clean up database connection pools and resources
    logger.info("Initiating graceful shutdown for %s...", settings.APP_NAME)
    await close_database_engine()
    logger.info("Application shutdown complete.")


def create_app() -> FastAPI:
    """Application factory for AegisPay AI backend."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="AegisPay AI: Simulated Banking Fraud & Coercion Prevention System",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register structured error handlers
    register_error_handlers(app)

    # Register routers
    app.include_router(health_router)
    app.include_router(api_v1_router)

    return app


app = create_app()
