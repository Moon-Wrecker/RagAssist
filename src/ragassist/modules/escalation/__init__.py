"""Escalation module public API."""

from ragassist.modules.escalation.adapters.helpdesk import HelpdeskClient
from ragassist.modules.escalation.application import (
    EscalateConversation,
    ReplyToEscalation,
)
from ragassist.modules.escalation.domain import (
    EscalationNotFound,
    EscalationResult,
    RoleNotAllowed,
)

__all__ = [
    "EscalateConversation",
    "EscalationNotFound",
    "EscalationResult",
    "HelpdeskClient",
    "ReplyToEscalation",
    "RoleNotAllowed",
]
