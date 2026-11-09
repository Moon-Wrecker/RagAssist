"""Domain models and errors for human escalation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from ragassist.shared.domain import DomainError


class EscalationNotFound(DomainError):
    """Raised when an escalation/conversation is not found or belongs to another tenant."""


class NotEscalated(DomainError):
    """Raised when a reply or resolution targets a conversation that is not currently escalated."""


class RoleNotAllowed(DomainError):
    """Raised when a principal lacks the required role for an escalation action."""


@dataclass(frozen=True)
class EscalationResult:
    """Outcome of escalating a conversation to human support."""

    ticket_id: str
    status: str = "open"
