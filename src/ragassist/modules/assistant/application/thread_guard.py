"""Namespaced thread IDs and tenancy verification for LangGraph checkpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ragassist.shared.domain import DomainError
from ragassist.shared.security.jwt import Principal


class ThreadAccessDenied(DomainError):
    """Raised when a principal attempts to access a conversation checkpoint of another tenant."""


def namespaced_thread_id(tenant_id: UUID | str, conversation_id: str) -> str:
    """Format namespaced thread ID as '<tenant_id>:<conversation_id>'."""
    return f"{tenant_id}:{conversation_id}"


async def ensure_thread_access(
    principal: Principal,
    conversation_id: str,
    conversations: Any,
) -> None:
    """Verify principal has access to conversation before reading checkpoints."""
    conv = await conversations.get(principal.tenant_id, conversation_id)
    if conv is None:
        raise ThreadAccessDenied(
            f"Tenant {principal.tenant_id} does not have access to conversation '{conversation_id}'"
        )
