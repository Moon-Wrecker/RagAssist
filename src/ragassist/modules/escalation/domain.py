"""Domain models and exceptions for human escalation."""

from __future__ import annotations

from dataclasses import dataclass
from ragassist.shared.domain import DomainError


class EscalationNotFound(DomainError):
    """Raised when an escalation or conversation is not found for tenant."""


class RoleNotAllowed(DomainError):
    """Raised when a user lacks the required role to perform an escalation action."""


@dataclass(frozen=True)
class EscalationResult:
    """Outcome of an escalation request."""

    ticket_id: str
    status: str
