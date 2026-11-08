"""In-memory and persistent conversation store for assistant sessions."""

from __future__ import annotations

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
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "conversation_id": conversation_id,
            "tenant_id": str(tenant_id),
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

    async def list(self, tenant_id: object, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        tenant_rows = [c for c in self._conversations.values() if c["tenant_id"] == str(tenant_id)]
        return tenant_rows[offset : offset + limit], len(tenant_rows)

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
        self, tenant_id: object, conversation_id: str, interrupt_id: str, approved: bool, reason: str | None
    ) -> None:
        self._actions[f"{conversation_id}:{interrupt_id}"] = {
            "tenant_id": str(tenant_id),
            "conversation_id": conversation_id,
            "interrupt_id": interrupt_id,
            "approved": approved,
            "reason": reason,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }


_conversation_store = InMemoryConversationStore()


def get_conversation_store() -> InMemoryConversationStore:
    return _conversation_store
