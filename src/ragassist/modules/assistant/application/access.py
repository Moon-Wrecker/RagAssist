"""Who may touch a conversation (per-user access inside a tenant).

Tenant isolation is enforced by row-level security. Inside one tenant a conversation still belongs to the
user who opened it: plain users see only their own; agents (support staff) may read any, and only the owner
or an admin may approve a write action that runs on the owner's behalf. A conversation without a recorded
owner is reachable by staff only (fail closed).
"""

from __future__ import annotations

from typing import Any

from ragassist.shared.security.jwt import Principal, UserRole

STAFF_ROLES = frozenset({UserRole.AGENT, UserRole.ADMIN})


def is_staff(principal: Principal) -> bool:
    return principal.role in STAFF_ROLES


def owns(principal: Principal, conversation: dict[str, Any]) -> bool:
    owner = conversation.get("user_id")
    return owner is not None and str(owner) == str(principal.user_id)


def can_access_conversation(principal: Principal, conversation: dict[str, Any]) -> bool:
    """Read the history and post messages."""
    return is_staff(principal) or owns(principal, conversation)


def can_decide_action(principal: Principal, conversation: dict[str, Any]) -> bool:
    """Approve or deny a paused write action: the conversation's owner, or an admin."""
    return principal.role == UserRole.ADMIN or owns(principal, conversation)


def owner_filter(principal: Principal) -> object | None:
    """The owner id to filter listings by, or ``None`` for staff (who see the whole tenant)."""
    return None if is_staff(principal) else principal.user_id
