"""Hardening of the action tools: authorisation before approval, input validation, honest stubs and a SaaS
client that never invents credentials or leaks upstream bodies."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from factories.principals import make_principal

from ragassist.modules.actions.adapters.saas_client import (
    SaaSClient,
    SaaSClientError,
    SaaSUnavailable,
)
from ragassist.modules.actions.application import ToolRegistry
from ragassist.modules.actions.domain import ToolExecutionError, UnknownTool
from ragassist.modules.actions.tools import default_tools
from ragassist.shared.security.jwt import UserRole


class RecordingSaaS:
    def __init__(self) -> None:
        self.billing_emails: list[str] = []

    async def update_billing_email(self, principal: Any, new_email: str) -> dict[str, Any]:
        self.billing_emails.append(new_email)
        return {
            "status": "ok",
            "tenant_id": str(principal.tenant_id),
            "updated_billing_email": new_email,
        }


@pytest.fixture
def saas() -> RecordingSaaS:
    return RecordingSaaS()


@pytest.fixture
def registry(saas: RecordingSaaS) -> ToolRegistry:
    return ToolRegistry(default_tools(saas))  # type: ignore[arg-type]


class TestAuthorizeRunsBeforeApproval:
    def test_a_non_admin_is_refused_for_a_write_tool(self, registry: ToolRegistry) -> None:
        with pytest.raises(PermissionError):
            registry.authorize("update_billing_email", make_principal(role=UserRole.USER))

    def test_an_admin_and_any_role_for_a_read_tool_pass(self, registry: ToolRegistry) -> None:
        registry.authorize("update_billing_email", make_principal(role=UserRole.ADMIN))
        registry.authorize("get_subscription", make_principal(role=UserRole.USER))

    def test_an_unknown_tool_is_refused(self, registry: ToolRegistry) -> None:
        with pytest.raises(UnknownTool):
            registry.authorize("drop_database", make_principal(role=UserRole.ADMIN))


class TestBillingEmailValidation:
    @pytest.mark.parametrize(
        "value",
        [
            "",
            "not-an-email",
            "a@b",
            "a b@example.com",
            "a@example.com, b@example.com",
            "x@y.example\r\nBcc: z@y.example",
        ],
    )
    async def test_a_malformed_address_never_reaches_the_service(
        self, registry: ToolRegistry, saas: RecordingSaaS, value: str
    ) -> None:
        with pytest.raises(ValueError):
            await registry.invoke(
                "update_billing_email", {"new_email": value}, make_principal(role=UserRole.ADMIN)
            )
        assert saas.billing_emails == []

    async def test_a_valid_address_is_trimmed_and_sent(
        self, registry: ToolRegistry, saas: RecordingSaaS
    ) -> None:
        await registry.invoke(
            "update_billing_email",
            {"new_email": "  ap@acme.example "},
            make_principal(role=UserRole.ADMIN),
        )
        assert saas.billing_emails == ["ap@acme.example"]


class TestUnbuiltToolsAreHonest:
    async def test_query_dataset_reports_that_it_is_not_available(
        self, registry: ToolRegistry
    ) -> None:
        with pytest.raises(ToolExecutionError, match="not available"):
            await registry.invoke("query_dataset", {"query": "revenue"}, make_principal())


def client_for(handler) -> SaaSClient:  # type: ignore[no-untyped-def]
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://saas.test")
    return SaaSClient(http=http, max_retries=0)


class TestSaaSClientCredentials:
    @pytest.mark.parametrize("token", [None, ""])
    async def test_a_principal_without_a_token_is_refused_instead_of_sending_the_tenant_id(
        self, token: str | None
    ) -> None:
        sent: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(request)
            return httpx.Response(200, json=[])

        principal = SimpleNamespace(tenant_id=uuid4(), user_id=uuid4(), raw_token=token)
        with pytest.raises(SaaSClientError) as raised:
            await client_for(handler).get_invoices(principal)  # type: ignore[arg-type]
        assert raised.value.status_code == 401
        assert sent == [], "no request may leave without the caller's own token"

    async def test_the_upstream_error_body_is_kept_out_of_the_message(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="internal detail: db host 10.0.0.9")

        with pytest.raises(SaaSClientError) as raised:
            await client_for(handler).get_invoices(make_principal())
        assert "10.0.0.9" not in str(raised.value)
        assert "10.0.0.9" in raised.value.body

    async def test_a_server_error_does_not_echo_the_response(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="stack trace at /srv/app/billing.py")

        with pytest.raises(SaaSUnavailable) as raised:
            await client_for(handler).get_invoices(make_principal())
        assert "/srv/app" not in str(raised.value)
