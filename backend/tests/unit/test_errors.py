"""Unit tests for structured error handling and security."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.errors import AppException, NotFoundError, register_error_handlers


class DummyModel(BaseModel):
    amount: float
    account_number: str


@pytest.fixture
def error_test_app() -> FastAPI:
    """Create a minimal FastAPI app with error handlers and test routes."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/trigger-app-exception")
    def trigger_app_exception() -> None:
        raise AppException(
            message="Domain violation occurred",
            code="DOMAIN_RULE_VIOLATION",
            status_code=400,
            details={"field": "amount"},
        )

    @app.get("/trigger-not-found")
    def trigger_not_found() -> None:
        raise NotFoundError("Transaction TX-999 not found")

    @app.post("/trigger-validation")
    def trigger_validation(payload: DummyModel) -> DummyModel:
        return payload

    @app.get("/trigger-unexpected")
    def trigger_unexpected() -> None:
        raise RuntimeError("Internal secret database password failure!")

    return app


@pytest.mark.asyncio
async def test_app_exception_envelope(error_test_app: FastAPI) -> None:
    """Verify AppException returns structured envelope with custom code and status."""
    transport = ASGITransport(app=error_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/trigger-app-exception")
        assert response.status_code == 400

        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "DOMAIN_RULE_VIOLATION"
        assert data["error"]["message"] == "Domain violation occurred"
        assert data["error"]["details"] == {"field": "amount"}


@pytest.mark.asyncio
async def test_not_found_envelope(error_test_app: FastAPI) -> None:
    """Verify NotFoundError returns 404 with structured envelope."""
    transport = ASGITransport(app=error_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/trigger-not-found")
        assert response.status_code == 404

        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"
        assert data["error"]["message"] == "Transaction TX-999 not found"


@pytest.mark.asyncio
async def test_validation_error_envelope(error_test_app: FastAPI) -> None:
    """Verify RequestValidationError returns structured 422 without leaking internals."""
    transport = ASGITransport(app=error_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/trigger-validation", json={"amount": "invalid"})
        assert response.status_code == 422

        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert isinstance(data["error"]["details"], list)


@pytest.mark.asyncio
async def test_unexpected_exception_does_not_leak_details(error_test_app: FastAPI) -> None:
    """Verify unhandled exceptions return 500 without leaking stack traces or internal secrets."""
    transport = ASGITransport(app=error_test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/trigger-unexpected")
        assert response.status_code == 500

        data = response.json()
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        # The internal exception message containing "password" must NOT be returned to the client
        assert "password" not in response.text
        assert "Traceback" not in response.text
