"""Unit tests for Gemini Live configuration validation (P2-A11)."""

from __future__ import annotations

import pytest

from app.core.config import Settings


def test_live_disabled_requires_no_credentials() -> None:
    """Live disabled is valid regardless of credentials."""
    settings = Settings(GEMINI_LIVE_ENABLED=False, GEMINI_API_KEY=None, GCP_PROJECT_ID=None)
    assert settings.GEMINI_LIVE_ENABLED is False


def test_live_enabled_without_credentials_fails() -> None:
    """Enabling Live without any provider credential is a clear misconfiguration."""
    with pytest.raises(ValueError, match="GEMINI_LIVE_ENABLED"):
        Settings(GEMINI_LIVE_ENABLED=True, GEMINI_API_KEY=None, GCP_PROJECT_ID=None)


def test_live_enabled_with_api_key_ok() -> None:
    """A Gemini API key satisfies the Live credential requirement."""
    settings = Settings(GEMINI_LIVE_ENABLED=True, GEMINI_API_KEY="test-key")
    assert settings.GEMINI_LIVE_ENABLED is True
    assert settings.GEMINI_LIVE_MODEL  # configurable, non-empty default


def test_live_enabled_with_vertex_project_ok() -> None:
    """A Vertex project also satisfies the Live credential requirement."""
    settings = Settings(GEMINI_LIVE_ENABLED=True, GCP_PROJECT_ID="proj-123")
    assert settings.GEMINI_LIVE_ENABLED is True
