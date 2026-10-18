"""Data access repositories."""

from app.repositories.recipient_repository import RecipientRepository
from app.repositories.transaction_repository import TransactionRepository

__all__ = ["RecipientRepository", "TransactionRepository"]
