"""Custom application exceptions and structured error handling."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class ErrorDetail(BaseModel):
    """Structured error payload definition."""

    code: str
    message: str
    details: Any | None = None


class ErrorEnvelope(BaseModel):
    """Enveloping model for structured error responses."""

    error: ErrorDetail


class AppException(Exception):
    """Base exception for all application-level errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class DatabaseConnectionError(AppException):
    """Raised when the database cannot be reached."""

    def __init__(
        self,
        message: str = "Database service unavailable",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="DATABASE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


class NotFoundError(AppException):
    """Raised when an entity or resource is not found."""

    def __init__(self, message: str = "Resource not found", details: Any | None = None) -> None:
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ConflictError(AppException):
    """Raised when an action conflicts with existing state."""

    def __init__(
        self,
        message: str = "Resource state conflict",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class InvalidStateTransitionError(AppException):
    """Raised when an attempted state transition is invalid according to the state machine."""

    def __init__(
        self,
        from_state: str,
        to_state: str,
        message: str | None = None,
        details: Any | None = None,
    ) -> None:
        msg = message or f"Transition from '{from_state}' to '{to_state}' is not permitted"
        super().__init__(
            message=msg,
            code="INVALID_STATE_TRANSITION",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details or {"from_state": from_state, "to_state": to_state},
        )


class IdempotencyConflictError(ConflictError):
    """Raised when an idempotency key is reused with mismatched payload."""

    def __init__(
        self,
        message: str = "Idempotency key reused with mismatched request payload",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message=message,
            details=details,
        )
        self.code = "IDEMPOTENCY_CONFLICT"


class ConcurrencyConflictError(ConflictError):
    """Raised when a concurrent update modifies a resource (optimistic locking failure)."""

    def __init__(
        self,
        message: str = "Resource was modified by another operation; please retry",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message=message,
            details=details,
        )
        self.code = "CONCURRENCY_CONFLICT"


class AIProviderError(AppException):
    """Raised when an external AI provider fails, times out, or returns invalid data."""

    def __init__(
        self,
        message: str = "AI investigation provider temporarily unavailable",
        code: str = "AI_PROVIDER_ERROR",
        status_code: int = status.HTTP_502_BAD_GATEWAY,
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            details=details,
        )


class AIConfigurationError(AppException):
    """Raised when AI provider settings or credentials are not configured."""

    def __init__(
        self,
        message: str = "AI provider credentials or configuration not available",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="AI_CONFIGURATION_ERROR",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


class ConversationTurnLimitError(AppException):
    """Raised when an investigation conversation exceeds the maximum configured turns."""

    def __init__(
        self,
        message: str = "Investigation conversation turn limit exceeded",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="CONVERSATION_TURN_LIMIT_EXCEEDED",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class ConversationInactiveError(AppException):
    """Raised when submitting turns to an inactive or closed conversation."""

    def __init__(
        self,
        message: str = "Investigation conversation is closed or inactive",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="CONVERSATION_INACTIVE",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


def register_error_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on the FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "Application error: code=%s message=%s",
            exc.code,
            exc.message,
            extra={"code": exc.code, "details": exc.details},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorEnvelope(
                error=ErrorDetail(
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                )
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Simplify error details to exclude sensitive internal objects
        safe_errors = [
            {"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=ErrorEnvelope(
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message="Request validation failed",
                    details=safe_errors,
                )
            ).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            404: "NOT_FOUND",
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            405: "METHOD_NOT_ALLOWED",
            500: "INTERNAL_ERROR",
            503: "SERVICE_UNAVAILABLE",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorEnvelope(
                error=ErrorDetail(
                    code=code,
                    message=str(exc.detail),
                )
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        # Log the full exception with traceback internally
        logger.exception("Unhandled server exception: %s", str(exc))
        # Return a safe, generic error response without leaking stack traces or internal details
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorEnvelope(
                error=ErrorDetail(
                    code="INTERNAL_SERVER_ERROR",
                    message="An unexpected server error occurred. Please try again later.",
                )
            ).model_dump(),
        )
