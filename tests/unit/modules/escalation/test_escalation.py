"""Escalation (plan section 7, "Escalation"): a ticket is opened once, the conversation is marked
escalated, only agents reply, and another tenant's escalation looks like a missing one.

The helpdesk is the real mock SaaS over ASGI, so the ticket payload is checked where it lands."""

from __future__ import annotations

import httpx
import pytest
from factories.principals import make_principal
from fakes.conversations import InMemoryConversations
from support.specs import need

from ragassist.shared.security.jwt import UserRole
from services.mock_saas import main as mock_saas

TENANT_A = "a0000000-0000-0000-0000-000000000001"
TENANT_B = "b0000000-0000-0000-0000-000000000002"


def helpdesk():  # type: ignore[no-untyped-def]
    client_cls = need("escalation.HelpdeskClient")
    http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_saas.app), base_url="http://mocksaas.test"
    )
    return client_cls(http=http)


def escalator(conversations: InMemoryConversations):  # type: ignore[no-untyped-def]
    return need("escalation.EscalateConversation")(conversations=conversations, helpdesk=helpdesk())


def tickets_for(conversation_id: str) -> list[dict]:
    return [t for t in mock_saas._TICKETS if t.get("conversation_id") == conversation_id]


class TestEscalate:
    async def test_a_ticket_is_opened_with_the_conversation_and_priority(self) -> None:
        conversations = InMemoryConversations()
        conversations.create(tenant_id=TENANT_A, conversation_id="conv-1")
        principal = make_principal(role=UserRole.USER, tenant_id=TENANT_A)
        result = await escalator(conversations).execute(
            principal, "conv-1", summary="Customer wants a human", priority="high"
        )
        (ticket,) = tickets_for("conv-1")
        assert ticket["priority"] == "high"
        assert result.ticket_id == ticket["id"]

    async def test_the_conversation_is_marked_escalated(self) -> None:
        conversations = InMemoryConversations()
        conversations.create(tenant_id=TENANT_A, conversation_id="conv-2")
        await escalator(conversations).execute(
            make_principal(tenant_id=TENANT_A), "conv-2", summary="s", priority="high"
        )
        assert conversations.raw("conv-2")["status"] == "escalated"

    async def test_the_transcript_summary_reaches_the_ticket(self) -> None:
        conversations = InMemoryConversations()
        conversations.create(tenant_id=TENANT_A, conversation_id="conv-3")
        await escalator(conversations).execute(
            make_principal(tenant_id=TENANT_A),
            "conv-3",
            summary="Billing dispute on invoice 102",
            priority="high",
        )
        assert "Billing dispute" in tickets_for("conv-3")[0]["description"]

    async def test_escalating_twice_returns_the_same_ticket_and_creates_no_second(self) -> None:
        conversations = InMemoryConversations()
        conversations.create(tenant_id=TENANT_A, conversation_id="conv-4")
        service = escalator(conversations)
        principal = make_principal(tenant_id=TENANT_A)
        first = await service.execute(principal, "conv-4", summary="s", priority="high")
        second = await service.execute(principal, "conv-4", summary="s", priority="high")
        assert first.ticket_id == second.ticket_id
        assert len(tickets_for("conv-4")) == 1

    async def test_another_tenants_conversation_is_reported_as_missing(self) -> None:
        conversations = InMemoryConversations()
        conversations.create(tenant_id=TENANT_B, conversation_id="conv-of-b")
        with pytest.raises(need("escalation.EscalationNotFound")):
            await escalator(conversations).execute(
                make_principal(tenant_id=TENANT_A), "conv-of-b", summary="s", priority="high"
            )
        assert tickets_for("conv-of-b") == [], "no ticket may be opened for a foreign conversation"
        assert conversations.raw("conv-of-b")["status"] == "open"


class TestReplyToEscalation:
    async def test_an_agent_reply_is_added_to_the_conversation(self) -> None:
        conversations = InMemoryConversations()
        conversations.create(tenant_id=TENANT_A, conversation_id="conv-5", status="escalated")
        reply_service = need("escalation.ReplyToEscalation")(conversations=conversations)
        agent = make_principal(role=UserRole.AGENT, tenant_id=TENANT_A)
        await reply_service.execute(agent, "conv-5", text="Hi, I am picking this up.")
        messages = conversations.raw("conv-5")["messages"]
        assert (
            messages[-1]["text"] == "Hi, I am picking this up." and messages[-1]["role"] == "agent"
        )

    async def test_a_plain_user_cannot_reply_as_an_agent(self) -> None:
        conversations = InMemoryConversations()
        conversations.create(tenant_id=TENANT_A, conversation_id="conv-6", status="escalated")
        reply_service = need("escalation.ReplyToEscalation")(conversations=conversations)
        with pytest.raises(need("escalation.RoleNotAllowed")):
            await reply_service.execute(
                make_principal(role=UserRole.USER, tenant_id=TENANT_A), "conv-6", text="x"
            )
        assert conversations.raw("conv-6")["messages"] == []

    async def test_an_agent_of_another_tenant_sees_the_conversation_as_missing(self) -> None:
        conversations = InMemoryConversations()
        conversations.create(tenant_id=TENANT_B, conversation_id="conv-7", status="escalated")
        reply_service = need("escalation.ReplyToEscalation")(conversations=conversations)
        with pytest.raises(need("escalation.EscalationNotFound")):
            await reply_service.execute(
                make_principal(role=UserRole.AGENT, tenant_id=TENANT_A), "conv-7", text="x"
            )

    async def test_an_empty_reply_is_refused(self) -> None:
        conversations = InMemoryConversations()
        conversations.create(tenant_id=TENANT_A, conversation_id="conv-8", status="escalated")
        reply_service = need("escalation.ReplyToEscalation")(conversations=conversations)
        with pytest.raises(ValueError):
            await reply_service.execute(
                make_principal(role=UserRole.AGENT, tenant_id=TENANT_A), "conv-8", text="   "
            )
