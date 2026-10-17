"""SQLAlchemy declarative base model registry."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    pass


__all__ = ["Base"]
