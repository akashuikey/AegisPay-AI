"""Startup provisioning of the bootstrap operator identity.

Provides a documented login/bootstrap path for local development and the demo:
when ``AUTH_BOOTSTRAP_OPERATOR_USERNAME`` and ``AUTH_BOOTSTRAP_OPERATOR_PASSWORD``
are configured, an operator with those credentials is created on startup if it
does not already exist. The plaintext bootstrap password is only read from
environment configuration and is stored solely as a bcrypt hash.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.models import OperatorModel
from app.repositories.operator_repository import OperatorRepository

logger = get_logger(__name__)


async def ensure_bootstrap_operator(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Create the configured bootstrap operator if it is absent.

    This is idempotent: an existing operator with the configured username is
    left untouched (its password is never silently reset).
    """
    username = settings.AUTH_BOOTSTRAP_OPERATOR_USERNAME
    password = settings.AUTH_BOOTSTRAP_OPERATOR_PASSWORD
    if not username or not password:
        logger.info(
            "No bootstrap operator configured; skipping operator provisioning. "
            "Set AUTH_BOOTSTRAP_OPERATOR_USERNAME/_PASSWORD to enable demo login."
        )
        return

    async with session_factory() as session:
        repository = OperatorRepository(session)
        existing = await repository.get_by_username(username)
        if existing is not None:
            logger.info("Bootstrap operator '%s' already exists; leaving unchanged.", username)
            return

        operator = OperatorModel(
            username=username,
            password_hash=hash_password(password),
            is_active=True,
        )
        await repository.create(operator)
        logger.info("Provisioned bootstrap operator '%s'.", username)
