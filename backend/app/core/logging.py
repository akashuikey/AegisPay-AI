"""Structured logging configuration with sensitive data sanitization."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings

SENSITIVE_KEYWORDS = {
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "cookie",
    "private_key",
}


def sanitize_data(data: Any) -> Any:
    """Recursively scrub sensitive keys from data structures."""
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYWORDS):
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = sanitize_data(value)
        return cleaned
    if isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            log_payload["exception"] = record.exc_text

        # Include custom extra attributes
        for key, val in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "taskName",
            }:
                log_payload[key] = sanitize_data(val)

        return json.dumps(log_payload)


def setup_logging() -> None:
    """Initialize application logging configuration."""
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)

    # Lower noise on noisy external libraries
    logging.getLogger("uvicorn.access").setLevel(log_level)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with structured output."""
    return logging.getLogger(name)
