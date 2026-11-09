"""In-memory and persistent conversation store for assistant sessions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any


class InMemoryConversationStore:
    """Thread-safe conversation store for production runtime and testing."""

    def __init__(self) -> None:
        self._conversations: dict[str, dict[str, Any]] = {}
        self._actions: dict[str, dict[str, Any]] = {}

    def create(
        self,
        *,
        tenant_id: object,
        conversation_id: str,
        title: str = "New Conversation",
        status: str = "open",
        user_id: object | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "conversation_id": conversation_id,
            "tenant_id": str(tenant_id),
            "user_id": str(user_id) if user_id is not None else None,
            "title": title,
            "status": status,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        self._conversations[conversation_id] = row
        return row

    async def get(self, tenant_id: object, conversation_id: str) -> dict[str, Any] | None:
        row = self._conversations.get(conversation_id)
        if row is None or row["tenant_id"] != str(tenant_id):
            return None
        return row

    async def list(
        self,
        tenant_id: object,
        limit: int = 50,
        offset: int = 0,
        *,
        owner_id: object | None = None,
        statuses: Sequence[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Tenant conversations, optionally only one owner's and/or only some statuses (filtered before paging)."""
        rows = [c for c in self._conversations.values() if c["tenant_id"] == str(tenant_id)]
        if owner_id is not None:
            rows = [c for c in rows if c.get("user_id") == str(owner_id)]
        if statuses is not None:
            rows = [c for c in rows if c["status"] in statuses]
        return rows[offset : offset + limit], len(rows)

    async def set_status(self, tenant_id: object, conversation_id: str, status: str) -> None:
        row = await self.get(tenant_id, conversation_id)
        if row is None:
            raise KeyError(conversation_id)
        row["status"] = status
        row["updated_at"] = datetime.now(timezone.utc).isoformat()

    async def append_message(self, tenant_id: object, conversation_id: str, message: dict[str, Any]) -> None:
        row = await self.get(tenant_id, conversation_id)
        if row is None:
            raise KeyError(conversation_id)
        row["messages"].append(dict(message))
        row["updated_at"] = datetime.now(timezone.utc).isoformat()

    async def record_action(
        self,
        tenant_id: object,
        conversation_id: str,
        interrupt_id: str,
        approved: bool,
        reason: str | None,
        approver_id: object | None = None,
    ) -> None:
        self._actions[f"{conversation_id}:{interrupt_id}"] = {
            "tenant_id": str(tenant_id),
            "conversation_id": conversation_id,
            "interrupt_id": interrupt_id,
            "approved": approved,
            "approver_id": str(approver_id) if approver_id is not None else None,
            "reason": reason,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }


_conversation_store = InMemoryConversationStore()


def get_conversation_store() -> Any:
    """The Postgres store when the runtime is started (PERSISTENCE_BACKEND=postgres), else the in-memory one."""
    from ragassist.runtime import active_runtime

    runtime = active_runtime()
    return runtime.conversations if runtime is not None else _conversation_store
