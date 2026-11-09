"""PostgreSQL conversation store and tool audit repository (row-level security scoped).

Goal: persist conversations, their messages, the escalation ticket and the approval/tool audit trail so that
history survives restarts and every row is isolated per tenant by PostgreSQL itself (AGENTS.md section 1.3).

``PostgresConversationStore`` mirrors the in-memory store's contract, so the routers and the escalation use
cases run unchanged on either backend; the rows it returns are plain dicts with the same keys.

Consulted: PostgreSQL row security policies and ``clock_timestamp()`` (``now()`` is the transaction start, so two
messages written in one transaction would tie), SQLAlchemy 2.0 asyncio ``text()`` with JSONB cast.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from ragassist.shared.db.scoped import ScopedDatabase

_SECRET_KEYS = {"password", "api_key", "token", "authorization", "secret"}


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else datetime.now(timezone.utc).isoformat()


def _uuid_or_none(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _mask(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            k: ("***REDACTED***" if str(k).lower() in _SECRET_KEYS else _mask(v)) for k, v in data.items()
        }
    if isinstance(data, list):
        return [_mask(v) for v in data]
    return data


def _conversation_dict(row: Any, messages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "conversation_id": row.id,
        "tenant_id": str(row.tenant_id),
        "user_id": str(row.user_id) if getattr(row, "user_id", None) else None,
        "title": row.title,
        "status": row.status,
        "ticket_id": row.ticket_id,
        "priority": row.priority,
        "summary": row.summary,
        "messages_count": int(getattr(row, "messages_count", 0) or 0),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    if messages is not None:
        result["messages"] = messages
        result["messages_count"] = len(messages)
    return result


class PostgresConversationStore:
    """Tenant-scoped conversations, messages and escalation ticket state."""

    def __init__(self, database: ScopedDatabase) -> None:
        self._db = database

    async def create(
        self,
        *,
        tenant_id: object,
        conversation_id: str,
        title: str = "New Conversation",
        status: str = "open",
        user_id: object | None = None,
    ) -> dict[str, Any]:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text(
                        "INSERT INTO conversations (tenant_id, id, user_id, title, status) "
                        "VALUES (:tenant_id, :id, :user_id, :title, :status) "
                        "ON CONFLICT (tenant_id, id) DO UPDATE SET updated_at = conversations.updated_at "
                        "RETURNING *, 0 AS messages_count"
                    ),
                    {
                        "tenant_id": _uuid_or_none(tenant_id),
                        "id": conversation_id,
                        "user_id": _uuid_or_none(user_id),
                        "title": title[:255],
                        "status": status,
                    },
                )
            ).one()
        return _conversation_dict(row, messages=[])

    async def get(self, tenant_id: object, conversation_id: str) -> dict[str, Any] | None:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text("SELECT * FROM conversations WHERE tenant_id = :tenant_id AND id = :id"),
                    {"tenant_id": _uuid_or_none(tenant_id), "id": conversation_id},
                )
            ).first()
            if row is None:
                return None
            message_rows = (
                await session.execute(
                    text(
                        "SELECT * FROM messages WHERE tenant_id = :tenant_id AND conversation_id = :id "
                        "ORDER BY created_at, id"
                    ),
                    {"tenant_id": _uuid_or_none(tenant_id), "id": conversation_id},
                )
            ).all()
        messages = [
            {
                "role": m.role,
                "text": m.text,
                "citations": m.citations or [],
                "route": m.route,
                "model_used": m.model_used,
                "user_id": str(m.user_id) if m.user_id else None,
                "created_at": _iso(m.created_at),
            }
            for m in message_rows
        ]
        return _conversation_dict(row, messages=messages)

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
        clauses = ["c.tenant_id = :tenant_id"]
        params: dict[str, Any] = {"tenant_id": _uuid_or_none(tenant_id), "limit": limit, "offset": offset}
        if owner_id is not None:
            clauses.append("c.user_id = :owner_id")
            params["owner_id"] = _uuid_or_none(owner_id)
        if statuses is not None:
            clauses.append("c.status = ANY(:statuses)")
            params["statuses"] = list(statuses)
        where = " AND ".join(clauses)  # fixed fragments only; every value is bound
        async with self._db.scope(tenant_id) as session:
            total = (
                await session.execute(text(f"SELECT count(*) FROM conversations c WHERE {where}"), params)
            ).scalar_one()
            rows = (
                await session.execute(
                    text(
                        "SELECT c.*, (SELECT count(*) FROM messages m WHERE m.tenant_id = c.tenant_id "
                        f"AND m.conversation_id = c.id) AS messages_count FROM conversations c WHERE {where} "
                        "ORDER BY c.updated_at DESC LIMIT :limit OFFSET :offset"
                    ),
                    params,
                )
            ).all()
        return [_conversation_dict(r) for r in rows], int(total)

    async def set_status(self, tenant_id: object, conversation_id: str, status: str) -> None:
        async with self._db.scope(tenant_id) as session:
            result = await session.execute(
                text(
                    "UPDATE conversations SET status = :status, updated_at = now() "
                    "WHERE tenant_id = :tenant_id AND id = :id"
                ),
                {"status": status, "tenant_id": _uuid_or_none(tenant_id), "id": conversation_id},
            )
        if not result.rowcount:
            raise KeyError(conversation_id)

    async def set_ticket(
        self,
        tenant_id: object,
        conversation_id: str,
        *,
        ticket_id: str,
        priority: str | None = None,
        summary: str | None = None,
    ) -> None:
        """Attach the helpdesk ticket and mark the conversation escalated, in one statement."""
        async with self._db.scope(tenant_id) as session:
            result = await session.execute(
                text(
                    "UPDATE conversations SET ticket_id = :ticket_id, priority = :priority, summary = :summary, "
                    "status = 'escalated', updated_at = now() WHERE tenant_id = :tenant_id AND id = :id"
                ),
                {
                    "ticket_id": ticket_id,
                    "priority": priority,
                    "summary": summary,
                    "tenant_id": _uuid_or_none(tenant_id),
                    "id": conversation_id,
                },
            )
        if not result.rowcount:
            raise KeyError(conversation_id)

    async def append_message(
        self, tenant_id: object, conversation_id: str, message: dict[str, Any]
    ) -> None:
        async with self._db.scope(tenant_id) as session:
            exists = (
                await session.execute(
                    text("SELECT 1 FROM conversations WHERE tenant_id = :tenant_id AND id = :id"),
                    {"tenant_id": _uuid_or_none(tenant_id), "id": conversation_id},
                )
            ).first()
            if exists is None:
                raise KeyError(conversation_id)
            await session.execute(
                text(
                    "INSERT INTO messages (id, tenant_id, conversation_id, role, text, citations, user_id, "
                    "route, model_used, decider_used, created_at) VALUES (:id, :tenant_id, :conversation_id, "
                    ":role, :text, CAST(:citations AS jsonb), :user_id, :route, :model_used, :decider_used, "
                    "clock_timestamp())"
                ),
                {
                    "id": uuid4(),
                    "tenant_id": _uuid_or_none(tenant_id),
                    "conversation_id": conversation_id,
                    "role": message.get("role", "user"),
                    "text": message.get("text", ""),
                    "citations": json.dumps(message.get("citations") or []),
                    "user_id": _uuid_or_none(message.get("user_id")),
                    "route": message.get("route"),
                    "model_used": message.get("model_used"),
                    "decider_used": message.get("decider_used"),
                },
            )
            await session.execute(
                text(
                    "UPDATE conversations SET updated_at = now() WHERE tenant_id = :tenant_id AND id = :id"
                ),
                {"tenant_id": _uuid_or_none(tenant_id), "id": conversation_id},
            )

    async def record_action(
        self,
        tenant_id: object,
        conversation_id: str,
        interrupt_id: str,
        approved: bool,
        reason: str | None,
        approver_id: object | None = None,
    ) -> None:
        """Audit the human decision on a paused write action."""
        async with self._db.scope(tenant_id) as session:
            await session.execute(
                text(
                    "INSERT INTO tool_audit_log (id, tenant_id, conversation_id, tool, arguments, status, "
                    "approver_id, reason) VALUES (:id, :tenant_id, :conversation_id, 'approval_decision', "
                    "CAST(:arguments AS jsonb), :status, :approver_id, :reason)"
                ),
                {
                    "id": uuid4(),
                    "tenant_id": _uuid_or_none(tenant_id),
                    "conversation_id": conversation_id,
                    "arguments": json.dumps({"interrupt_id": interrupt_id}),
                    "status": "approved" if approved else "denied",
                    "approver_id": _uuid_or_none(approver_id),
                    "reason": reason,
                },
            )


class PostgresAuditRepository:
    """Append-only audit trail of every tool execution (arguments are secret-masked)."""

    def __init__(self, database: ScopedDatabase) -> None:
        self._db = database

    async def record(
        self,
        *,
        tenant_id: object,
        user_id: object | None,
        tool: str,
        arguments: dict[str, Any],
        status: str,
        result: Any = None,
        conversation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        async with self._db.scope(tenant_id) as session:
            await session.execute(
                text(
                    "INSERT INTO tool_audit_log (id, tenant_id, conversation_id, user_id, tool, arguments, "
                    "result, status, reason) VALUES (:id, :tenant_id, :conversation_id, :user_id, :tool, "
                    "CAST(:arguments AS jsonb), CAST(:result AS jsonb), :status, :reason)"
                ),
                {
                    "id": uuid4(),
                    "tenant_id": _uuid_or_none(tenant_id),
                    "conversation_id": conversation_id,
                    "user_id": _uuid_or_none(user_id),
                    "tool": tool,
                    "arguments": json.dumps(_mask(arguments), default=str),
                    "result": json.dumps(_mask(result), default=str) if result is not None else None,
                    "status": status,
                    "reason": reason,
                },
            )

    async def list_for_tenant(self, tenant_id: object, limit: int = 100) -> list[dict[str, Any]]:
        async with self._db.scope(tenant_id) as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT * FROM tool_audit_log WHERE tenant_id = :tenant_id "
                        "ORDER BY created_at DESC LIMIT :limit"
                    ),
                    {"tenant_id": _uuid_or_none(tenant_id), "limit": limit},
                )
            ).all()
        return [
            {
                "id": str(r.id),
                "tool": r.tool,
                "arguments": r.arguments,
                "status": r.status,
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ]
