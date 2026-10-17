import pytest

from app.core.config import Settings


def test_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test default values of application settings."""
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    settings = Settings(_env_file=None)
    assert settings.APP_NAME == "AegisPay AI"
    assert settings.APP_ENV == "development"
    assert settings.POSTGRES_PORT == 5432
    assert "postgresql+psycopg://" in settings.async_database_url


def test_cors_origins_parsing() -> None:
    """Test parsing of CORS origins from lists and JSON strings."""
    # JSON list string
    settings_json = Settings(CORS_ORIGINS='["http://alpha.com", "http://beta.com"]')
    assert settings_json.CORS_ORIGINS == ["http://alpha.com", "http://beta.com"]

    # Comma-separated string
    settings_comma = Settings(CORS_ORIGINS="http://one.com, http://two.com")
    assert settings_comma.CORS_ORIGINS == ["http://one.com", "http://two.com"]

    # Direct list
    settings_list = Settings(CORS_ORIGINS=["http://direct.com"])
    assert settings_list.CORS_ORIGINS == ["http://direct.com"]


def test_database_url_driver_replacement() -> None:
    """Test database URL driver standardizes to postgresql+psycopg."""
    settings = Settings(DATABASE_URL="postgresql://user:pass@localhost:5432/testdb")
    assert settings.async_database_url == "postgresql+psycopg://user:pass@localhost:5432/testdb"
