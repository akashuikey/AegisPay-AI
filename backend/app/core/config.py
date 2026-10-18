import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments where development-only conveniences (e.g. OTP display) are allowed.
_NON_PRODUCTION_ENVS = frozenset({"development", "dev", "local", "test", "testing", "ci"})

# Canonical paths to backend and project root for robust .env loading across execution contexts
_CONFIG_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _CONFIG_DIR.parents[1]
_REPO_ROOT = _CONFIG_DIR.parents[2]
_ENV_FILES = (
    str(_REPO_ROOT / ".env"),
    str(_BACKEND_DIR / ".env"),
    ".env",
    "../.env",
)


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
    GEMINI_MODEL_ID: str = "gemini-3.8-flash"
    GCP_PROJECT_ID: str | None = None
    GCP_LOCATION: str = "us-central1"
    GEMINI_API_KEY: str | None = None
    GEMINI_REQUEST_TIMEOUT_SECONDS: float = 30.0
    GEMINI_MAX_RETRIES: int = 2
    INVESTIGATION_MAX_CONVERSATION_TURNS: int = 20

    # Gemini Live API (real-time bidirectional voice) - P2-A11.
    # Disabled by default; the simulated text/speech dialogue (P2-OptA/A10) is used
    # until this is explicitly enabled with valid credentials.
    GEMINI_LIVE_ENABLED: bool = False
    # Audio-capable Live model identifier. Configurable; never hardcode in logic.
    # NOTE: model availability changes over time. Verify against the live provider
    # (``client.models.list()`` -> entries whose ``supported_actions`` include
    # ``bidiGenerateContent``) before changing this. The legacy
    # ``gemini-2.0-flash-live-001`` id was retired; current audio-capable Live models
    # include ``gemini-3.8-live`` and ``gemini-3.1-flash-live-preview`` (P2-A13).
    GEMINI_LIVE_MODEL: str = "gemini-3.8-live"
    # Supported prebuilt voice name for spoken responses.
    GEMINI_LIVE_VOICE: str = "Aoede"
    # Bounded live session duration (safety / resource cap).
    GEMINI_LIVE_MAX_SESSION_SECONDS: int = 300
    # Audio formats required by the Live API: 16 kHz PCM16 in, 24 kHz PCM16 out.
    GEMINI_LIVE_INPUT_SAMPLE_RATE: int = 16000
    GEMINI_LIVE_OUTPUT_SAMPLE_RATE: int = 24000
    # Per-frame inbound audio cap (bytes) and bounded queue depths (backpressure).
    GEMINI_LIVE_MAX_AUDIO_FRAME_BYTES: int = 32768
    GEMINI_LIVE_AUDIO_QUEUE_MAXSIZE: int = 256
    GEMINI_LIVE_TRANSCRIPT_QUEUE_MAXSIZE: int = 512
    # Concurrent live sessions allowed process-wide (resource cap).
    GEMINI_LIVE_MAX_CONCURRENT_SESSIONS: int = 8
    # Incremental analysis cadence: run when this many new final segments accrue
    # or this many seconds elapse, whichever comes first (bounded LLM usage).
    GEMINI_LIVE_ANALYSIS_MIN_NEW_SEGMENTS: int = 2
    GEMINI_LIVE_ANALYSIS_INTERVAL_SECONDS: float = 6.0
    # Bounded recent-context window (transcript segments) fed to incremental analysis.
    GEMINI_LIVE_ANALYSIS_CONTEXT_SEGMENTS: int = 12

    # Authentication & Authorization (operator identity boundary)
    # AUTH_JWT_SECRET has no insecure default: auth fails closed until it is configured.
    AUTH_JWT_SECRET: str | None = None
    AUTH_JWT_ALGORITHM: str = "HS256"
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # Optional bootstrap operator provisioned on startup for local dev / demo login.
    AUTH_BOOTSTRAP_OPERATOR_USERNAME: str | None = None
    AUTH_BOOTSTRAP_OPERATOR_PASSWORD: str | None = None
    # Bounded, per-client (IP) sliding-window throttle on /auth/login. Keyed by IP
    # (never by username) so it cannot be abused to lock a specific account. Set
    # the max to 0 to disable. This is an in-process speed bump, not an edge limiter.
    AUTH_LOGIN_MAX_ATTEMPTS_PER_WINDOW: int = 10
    AUTH_LOGIN_WINDOW_SECONDS: int = 60

    # Dedicated secret for HMAC-SHA256 OTP hashing (SEC-05 key separation).
    # If None, securely falls back to AUTH_JWT_SECRET with fail-closed behavior.
    VERIFICATION_HMAC_SECRET: str | None = None
    VERIFICATION_OTP_LENGTH: int = 6
    VERIFICATION_CHALLENGE_TTL_SECONDS: int = 300
    VERIFICATION_MAX_ATTEMPTS: int = 5
    VERIFICATION_SESSION_TTL_SECONDS: int = 600
    # Dev-only: expose the simulated OTP in the challenge-creation response so the
    # demo can complete the flow. MUST be false in production. Defaults to false.
    VERIFICATION_EXPOSE_DEV_OTP: bool = False
    # Abuse controls (SEC-06): bounded database-enforced window limits on challenge creation.
    VERIFICATION_MAX_CHALLENGES_PER_WINDOW: int = 5
    VERIFICATION_CHALLENGE_WINDOW_SECONDS: int = 3600

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("GEMINI_API_KEY", mode="before")
    @classmethod
    def assemble_gemini_api_key(cls, value: Any) -> str | None:
        """Sanitize GEMINI_API_KEY and check common aliases if unset."""
        if isinstance(value, str):
            cleaned = value.strip().strip("'\"")
            if cleaned:
                return cleaned
        # Check environment variable fallbacks
        for alias in ("GOOGLE_API_KEY", "AI_STUDIO_API_KEY"):
            alias_val = os.environ.get(alias)
            if alias_val:
                cleaned_alias = alias_val.strip().strip("'\"")
                if cleaned_alias:
                    return cleaned_alias
        return None

    @model_validator(mode="after")
    def constrain_dev_only_flags(self) -> "Settings":
        """Force development-only conveniences off outside dev/test environments.

        ``VERIFICATION_EXPOSE_DEV_OTP`` reveals the simulated OTP in API responses
        purely to make the local demo completable. It must never be on in a
        production-like environment, so it is coerced to False there (fail safe)
        regardless of the supplied value.
        """
        if (
            self.VERIFICATION_EXPOSE_DEV_OTP
            and self.APP_ENV.strip().lower() not in _NON_PRODUCTION_ENVS
        ):
            object.__setattr__(self, "VERIFICATION_EXPOSE_DEV_OTP", False)
        return self

    @model_validator(mode="after")
    def validate_live_voice_credentials(self) -> "Settings":
        """Fail clearly if Gemini Live is enabled without usable credentials.

        The Live API needs either a Gemini API key or a Vertex AI project. Enabling
        the feature flag without one is a misconfiguration we surface at startup
        rather than failing opaquely on the first WebSocket connection.
        """
        if self.GEMINI_LIVE_ENABLED and not (self.GEMINI_API_KEY or self.GCP_PROJECT_ID):
            raise ValueError(
                "GEMINI_LIVE_ENABLED is true but neither GEMINI_API_KEY nor GCP_PROJECT_ID "
                "is configured; real-time voice cannot authenticate to Gemini Live."
            )
        return self

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
