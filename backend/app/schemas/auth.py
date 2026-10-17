"""Pydantic schemas for operator authentication."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Operator login credentials."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class OperatorResponse(BaseModel):
    """Public representation of an authenticated operator identity."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str


class TokenResponse(BaseModel):
    """Access token issued on successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token lifetime in seconds")
    operator: OperatorResponse
