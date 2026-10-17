"""Application configuration and typed settings."""

import json
from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central typed settings for AegisPay AI backend."""

    # Application
    APP_NAME: str = "AegisPay AI"
    APP_ENV: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # PostgreSQL Database Configuration
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "aegispay"
    POSTGRES_USER: str = "aegispay_user"
    POSTGRES_PASSWORD: str = "aegispay_dev_pw"
    POSTGRES_POOL_SIZE: int = 5
    POSTGRES_MAX_OVERFLOW: int = 10
    DATABASE_URL: str | None = None

    # CORS configuration
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Gemini & Google Cloud Vertex AI Configuration
    AI_PROVIDER: str = "auto"
    GEMINI_MODEL_ID: str = "gemini-2.5-flash"
    GCP_PROJECT_ID: str | None = None
    GCP_LOCATION: str = "us-central1"
    GEMINI_API_KEY: str | None = None
    GEMINI_REQUEST_TIMEOUT_SECONDS: float = 30.0
    GEMINI_MAX_RETRIES: int = 2
    INVESTIGATION_MAX_CONVERSATION_TURNS: int = 20

    # Authentication & Authorization (operator identity boundary)
    # AUTH_JWT_SECRET has no insecure default: auth fails closed until it is configured.
    AUTH_JWT_SECRET: str | None = None
    AUTH_JWT_ALGORITHM: str = "HS256"
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # Optional bootstrap operator provisioned on startup for local dev / demo login.
    AUTH_BOOTSTRAP_OPERATOR_USERNAME: str | None = None
    AUTH_BOOTSTRAP_OPERATOR_PASSWORD: str | None = None

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Any) -> list[str]:
        """Parse CORS_ORIGINS from list, JSON string, or comma-separated string."""
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(origin).strip() for origin in parsed]
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value]
        return ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def async_database_url(self) -> str:
        """Return the asynchronous PostgreSQL connection URL."""
        if self.DATABASE_URL:
            # Ensure the driver is postgresql+psycopg
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
