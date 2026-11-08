"""Shared domain value objects and base entities.

Pure Python and immutable models only. Zero external dependencies.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, NewType, TypeVar
from uuid import UUID, uuid4

TenantId = NewType("TenantId", UUID)
UserId = NewType("UserId", UUID)


def new_tenant_id() -> TenantId:
    """Generate a strongly typed TenantId."""
    return TenantId(uuid4())


def new_user_id() -> UserId:
    """Generate a strongly typed UserId."""
    return UserId(uuid4())


@dataclass(frozen=True)
class Entity:
    """Base domain entity with immutable identifier and creation timestamp."""

    id: UUID
    created_at: datetime


class DomainError(Exception):
    """Base domain exception."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EntityNotFoundError(DomainError):
    """Raised when an entity is not found in the domain."""


class TenantIsolationError(DomainError):
    """Raised when cross-tenant access is attempted or tenant context is missing."""


class ValidationError(DomainError):
    """Domain validation error."""


E = TypeVar("E", bound=Entity)

