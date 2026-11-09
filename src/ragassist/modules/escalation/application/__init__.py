"""Application services for human escalation.

Consulted References:
- Hexagonal Architecture Application Service patterns.
- Mock SaaS API contract for Helpdesk Tickets (/helpdesk/tickets).
- Project specifications in tests/support/specs/map.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from ragassist.modules.escalation.domain import (
    EscalationNotFound,
    EscalationResult,
    NotEscalated,
    RoleNotAllowed,
)
from ragassist.platform.events.model import (
    conversation_updated,
    escalation_changed,
    message_created,
)
from ragassist.platform.events.ports import EventPublisher, publish_safely
from ragassist.shared.security.jwt import Principal, UserRole

class HelpdeskPort(Protocol):
    """Port for helpdesk ticketing integrations."""

    async def create_ticket(
        self, principal: Principal, payload: dict[str, Any]
    ) -> dict[str, Any]:
        ...


class EscalateConversation:
    """Application use case to escalate a customer conversation to a human support ticket."""

    def __init__(
        self, conversations: Any, helpdesk: HelpdeskPort | Any, events: EventPublisher | None = None
    ) -> None:
        self.conversations = conversations
        self.helpdesk = helpdesk
        self.events = events
        self._tickets: dict[str, EscalationResult] = {}

    async def execute(
        self,
        principal: Principal,
        conversation_id: str,
        *,
        summary: str,
        priority: str = "high",
    ) -> EscalationResult:
        """Escalate conversation idempotently to create at most one ticket."""
        conv = await self.conversations.get(principal.tenant_id, conversation_id)
        if conv is None:
            raise EscalationNotFound(f"Conversation '{conversation_id}' not found")

        # Idempotency: Return the open ticket if the conversation is already escalated. A resolved conversation that
        # escalates again gets a new ticket (the previous one was closed with the resolution).
        if conversation_id in self._tickets:
            return self._tickets[conversation_id]
        if conv.get("ticket_id") and conv.get("status") == "escalated":
            res = EscalationResult(ticket_id=conv["ticket_id"], status="open")
            self._tickets[conversation_id] = res
            return res

        payload = {
            "subject": summary,
            "description": summary,
            "conversation_id": conversation_id,
            "priority": priority,
        }
        ticket = await self.helpdesk.create_ticket(principal, payload)
        ticket_id = str(ticket.get("id", ""))
        if hasattr(self.conversations, "set_ticket"):  # durable stores record the ticket with the status
            await self.conversations.set_ticket(
                principal.tenant_id, conversation_id, ticket_id=ticket_id, priority=priority, summary=summary
            )
        else:
            conv["ticket_id"] = ticket_id
            await self.conversations.set_status(principal.tenant_id, conversation_id, "escalated")

        result = EscalationResult(ticket_id=ticket_id, status="open")
        self._tickets[conversation_id] = result
        await publish_safely(
            self.events,
            conversation_updated(principal.tenant_id, conversation_id, conv.get("user_id")),
            escalation_changed(principal.tenant_id, conversation_id, ticket_id),
        )
        return result


class ReplyToEscalation:
    """Application use case for human agent replies to escalated conversations."""

    def __init__(self, conversations: Any, events: EventPublisher | None = None) -> None:
        self.conversations = conversations
        self.events = events

    async def execute(
        self,
        principal: Principal,
        escalation_id: str,
        *,
        text: str,
    ) -> dict[str, Any]:
        """Deliver reply to customer thread on behalf of verified agent."""
        role_val = getattr(principal.role, "value", str(principal.role)).lower()
        if role_val != UserRole.AGENT.value:
            raise RoleNotAllowed(f"Role '{principal.role}' is not allowed to reply as an agent")

        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Reply text cannot be empty or whitespace only")

        conv = await self.conversations.get(principal.tenant_id, escalation_id)
        if conv is None:
            raise EscalationNotFound(f"Conversation '{escalation_id}' not found")
        if conv.get("status") != "escalated":
            raise NotEscalated("This conversation is not escalated.")

        reply_message = {
            "role": "agent",
            "text": cleaned,
            "user_id": str(principal.user_id),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.conversations.append_message(principal.tenant_id, escalation_id, reply_message)
        await publish_safely(
            self.events,
            message_created(principal.tenant_id, escalation_id, conv.get("user_id")),
            escalation_changed(principal.tenant_id, escalation_id),
        )
        return reply_message


class ResolveEscalation:
    """Application use case: an agent or admin closes an escalation, handing the conversation back to the assistant."""

    def __init__(self, conversations: Any, events: EventPublisher | None = None) -> None:
        self.conversations = conversations
        self.events = events

    async def execute(self, principal: Principal, escalation_id: str) -> None:
        if principal.role not in (UserRole.AGENT, UserRole.ADMIN):
            raise RoleNotAllowed("Only agents or admins can resolve an escalation")
        conv = await self.conversations.get(principal.tenant_id, escalation_id)
        if conv is None:
            raise EscalationNotFound("Escalation not found")
        if conv.get("status") != "escalated":
            raise NotEscalated("This conversation is not escalated.")
        await self.conversations.set_status(principal.tenant_id, escalation_id, "resolved")
        await publish_safely(
            self.events,
            conversation_updated(principal.tenant_id, escalation_id, conv.get("user_id")),
            escalation_changed(principal.tenant_id, escalation_id),
        )
