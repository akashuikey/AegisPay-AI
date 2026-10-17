"""Integration tests for operator authentication and the authorization boundary.

Exercises the real authentication pipeline (no injected operator) via the
``unauth_client`` fixture: login, token issuance, and that every operations
console route rejects unauthenticated access.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.db.models import OperatorModel
from tests.conftest import get_test_settings

TEST_USERNAME = "analyst_jordan"
TEST_PASSWORD = "correct horse battery staple"


async def _seed_operator(
    db_session: AsyncSession,
    username: str = TEST_USERNAME,
    password: str = TEST_PASSWORD,
    is_active: bool = True,
) -> OperatorModel:
    operator = OperatorModel(
        id=uuid.uuid4(),
        username=username,
        password_hash=hash_password(password),
        is_active=is_active,
    )
    db_session.add(operator)
    await db_session.commit()
    await db_session.refresh(operator)
    return operator


# A representative sample across all four gated routers.
_PROTECTED_GET_ROUTES = [
    "/api/v1/transactions",
    f"/api/v1/transactions/{uuid.uuid4()}",
    f"/api/v1/transactions/{uuid.uuid4()}/investigations",
    f"/api/v1/transactions/{uuid.uuid4()}/conversations/current",
    f"/api/v1/conversations/{uuid.uuid4()}",
    "/api/v1/risk/scenarios",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", _PROTECTED_GET_ROUTES)
async def test_protected_routes_reject_unauthenticated(
    unauth_client: AsyncClient, route: str
) -> None:
    """Every console route returns 401 without a bearer token (authN before authZ)."""
    response = await unauth_client.get(route)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_protected_write_route_rejects_unauthenticated(unauth_client: AsyncClient) -> None:
    """A write route (direct conversation turn) is also gated; identity is checked first."""
    response = await unauth_client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/turns",
        json={"content": "unauthorized attempt"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_login_success_issues_working_token(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Valid credentials return a bearer token that authorizes console access."""
    await _seed_operator(db_session)

    login = await unauth_client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["operator"]["username"] == TEST_USERNAME
    assert "password_hash" not in body["operator"]
    token = body["access_token"]

    # Token authorizes a previously protected route.
    authed = await unauth_client.get(
        "/api/v1/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert authed.status_code == 200

    # And /auth/me reflects the identity.
    me = await unauth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == TEST_USERNAME


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """An incorrect password returns 401 without revealing which field was wrong."""
    await _seed_operator(db_session)
    response = await unauth_client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USERNAME, "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert "username or password" in response.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_login_unknown_user_rejected(unauth_client: AsyncClient) -> None:
    """An unknown username returns the same generic 401 (no account enumeration)."""
    response = await unauth_client.post(
        "/api/v1/auth/login",
        json={"username": "ghost", "password": "whatever"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_inactive_operator_cannot_login_or_authorize(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """A deactivated operator is refused at login and via a pre-issued token."""
    operator = await _seed_operator(db_session, username="retired_op", is_active=False)

    login = await unauth_client.post(
        "/api/v1/auth/login",
        json={"username": "retired_op", "password": TEST_PASSWORD},
    )
    assert login.status_code == 401

    # Even a validly signed token for the id must be rejected while inactive.
    token, _ = create_access_token(str(operator.id), get_test_settings())
    authed = await unauth_client.get(
        "/api/v1/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert authed.status_code == 401


@pytest.mark.asyncio
async def test_malformed_and_unknown_tokens_rejected(unauth_client: AsyncClient) -> None:
    """Garbage tokens and tokens for nonexistent operators are rejected with 401."""
    garbage = await unauth_client.get(
        "/api/v1/transactions",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert garbage.status_code == 401

    # Validly signed token, but the operator id does not exist in the database.
    token, _ = create_access_token(str(uuid.uuid4()), get_test_settings())
    unknown = await unauth_client.get(
        "/api/v1/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unknown.status_code == 401


@pytest.mark.asyncio
async def test_login_is_public(unauth_client: AsyncClient) -> None:
    """The login endpoint itself must be reachable without authentication."""
    response = await unauth_client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "x"},
    )
    # Reachable (not blocked by the auth dependency); returns 401 for bad creds, not a 403 gate.
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_bootstrap_operator_provisions_and_is_idempotent(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """ensure_bootstrap_operator creates the configured operator once and can then log in."""
    from app.services.auth_bootstrap import ensure_bootstrap_operator
    from tests.conftest import get_test_session_factory

    settings = get_test_settings()
    object.__setattr__(settings, "AUTH_BOOTSTRAP_OPERATOR_USERNAME", "boot_op")
    object.__setattr__(settings, "AUTH_BOOTSTRAP_OPERATOR_PASSWORD", "bootstrap-pass-123")

    factory = get_test_session_factory()
    await ensure_bootstrap_operator(factory, settings)
    # Second call must not raise or duplicate the operator.
    await ensure_bootstrap_operator(factory, settings)

    login = await unauth_client.post(
        "/api/v1/auth/login",
        json={"username": "boot_op", "password": "bootstrap-pass-123"},
    )
    assert login.status_code == 200
    assert login.json()["operator"]["username"] == "boot_op"
