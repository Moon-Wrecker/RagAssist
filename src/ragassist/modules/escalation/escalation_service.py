"""Direct module export for escalation service and reply use-cases."""

from ragassist.modules.escalation.application import (
    EscalateConversation,
    ReplyToEscalation,
)
from ragassist.modules.escalation.domain import EscalationResult

__all__ = [
    "EscalateConversation",
    "EscalationResult",
    "ReplyToEscalation",
]
