"""Unit tests for security-relevant settings constraints (P2-A9)."""

from app.core.config import Settings

_SECRET = "unit-test-secret-not-for-production-use-only"


def test_dev_otp_exposure_forced_off_in_production() -> None:
    settings = Settings(
        APP_ENV="production",
        AUTH_JWT_SECRET=_SECRET,
        VERIFICATION_EXPOSE_DEV_OTP=True,
    )
    assert settings.VERIFICATION_EXPOSE_DEV_OTP is False


def test_dev_otp_exposure_allowed_in_development() -> None:
    settings = Settings(
        APP_ENV="development",
        AUTH_JWT_SECRET=_SECRET,
        VERIFICATION_EXPOSE_DEV_OTP=True,
    )
    assert settings.VERIFICATION_EXPOSE_DEV_OTP is True


def test_dev_otp_exposure_allowed_in_test_env() -> None:
    settings = Settings(
        APP_ENV="test",
        AUTH_JWT_SECRET=_SECRET,
        VERIFICATION_EXPOSE_DEV_OTP=True,
    )
    assert settings.VERIFICATION_EXPOSE_DEV_OTP is True


def test_unknown_env_is_treated_as_production_for_dev_otp() -> None:
    settings = Settings(
        APP_ENV="staging",
        AUTH_JWT_SECRET=_SECRET,
        VERIFICATION_EXPOSE_DEV_OTP=True,
    )
    assert settings.VERIFICATION_EXPOSE_DEV_OTP is False
