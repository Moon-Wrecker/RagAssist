"""Escalation announces its changes, and a resolved conversation that escalates again gets a new ticket."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from factories.principals import make_principal
from fakes.conversations import InMemoryConversations

from ragassist.modules.escalation.application import EscalateConversation, ResolveEscalation
from ragassist.platform.events import InMemoryEventBus
from ragassist.shared.security.jwt import UserRole

TENANT = uuid4()


class CountingHelpdesk:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create_ticket(self, principal: Any, payload: dict[str, Any]) -> dict[str, Any]:
        self.created.append(payload)
        return {"id": f"TICK-{len(self.created)}"}


async def test_escalating_publishes_status_and_inbox_events_with_the_ticket_id() -> None:
    conversations = InMemoryConversations()
    conversations.create(tenant_id=TENANT, conversation_id="c1")
    conversations.raw("c1")["user_id"] = "owner-1"
    bus = InMemoryEventBus()

    await EscalateConversation(conversations, CountingHelpdesk(), bus).execute(
        make_principal(tenant_id=TENANT), "c1", summary="help"
    )

    assert [(e.type, dict(e.data), e.owner_id) for e in bus.published] == [
        ("conversation.updated", {"conversation_id": "c1"}, "owner-1"),
        ("escalation.changed", {"conversation_id": "c1", "ticket_id": "TICK-1"}, None),
    ]


async def test_resolving_publishes_and_a_second_escalation_opens_a_new_ticket() -> None:
    conversations = InMemoryConversations()
    conversations.create(tenant_id=TENANT, conversation_id="c2")
    helpdesk = CountingHelpdesk()
    bus = InMemoryEventBus()
    customer = make_principal(tenant_id=TENANT)
    agent = make_principal(tenant_id=TENANT, role=UserRole.AGENT)

    first = await EscalateConversation(conversations, helpdesk, bus).execute(
        customer, "c2", summary="one"
    )
    again = await EscalateConversation(conversations, helpdesk, bus).execute(
        customer, "c2", summary="one"
    )
    assert (
        first.ticket_id == again.ticket_id and len(helpdesk.created) == 1
    )  # still idempotent while open

    await ResolveEscalation(conversations, bus).execute(agent, "c2")
    assert conversations.raw("c2")["status"] == "resolved"
    assert [e.type for e in bus.published][-2:] == ["conversation.updated", "escalation.changed"]

    second = await EscalateConversation(conversations, helpdesk, bus).execute(
        customer, "c2", summary="two"
    )
    assert second.ticket_id != first.ticket_id and len(helpdesk.created) == 2
    assert conversations.raw("c2")["status"] == "escalated"
