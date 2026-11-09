"""In-memory conversation store with the tenant rule the database enforces: a conversation that
belongs to another tenant is indistinguishable from one that does not exist."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InMemoryConversations:
    _rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    lookups: list[str] = field(default_factory=list)

    def create(self, *, tenant_id: object, conversation_id: str, status: str = "open") -> None:
        self._rows[conversation_id] = {
            "tenant_id": str(tenant_id),
            "status": status,
            "messages": [],
        }

    async def get(self, tenant_id: object, conversation_id: str) -> dict[str, Any] | None:
        self.lookups.append(conversation_id)
        row = self._rows.get(conversation_id)
        if row is None or row["tenant_id"] != str(tenant_id):
            return None
        return row

    async def set_status(self, tenant_id: object, conversation_id: str, status: str) -> None:
        row = await self.get(tenant_id, conversation_id)
        if row is None:
            raise KeyError(conversation_id)
        row["status"] = status

    async def append_message(
        self, tenant_id: object, conversation_id: str, message: dict[str, Any]
    ) -> None:
        row = await self.get(tenant_id, conversation_id)
        if row is None:
            raise KeyError(conversation_id)
        row["messages"].append(dict(message))

    def raw(self, conversation_id: str) -> dict[str, Any] | None:
        return self._rows.get(conversation_id)
