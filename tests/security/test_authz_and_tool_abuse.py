"""Role matrix and tool-abuse scenarios (plan section 5.9). PENDING until the routes and tools exist;
each test names the rule it enforces so a regression is easy to read.
"""

from __future__ import annotations

import httpx
import pytest
from factories.principals import auth_header, make_token
from support.defects import defect
from support.specs.routes import concrete, require_route

from ragassist.main import create_app
from ragassist.shared.security.jwt import UserRole

pytestmark = pytest.mark.security


@pytest.fixture
def app():  # type: ignore[no-untyped-def]
    return create_app()


async def call(app, key: str, role: UserRole, body: dict | None = None):  # type: ignore[no-untyped-def]
    method, path = require_route(app, key)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api.test"
    ) as client:
        return await client.request(
            method, concrete(path), json=body or {}, headers=auth_header(make_token(role=role))
        )


class TestRoleMatrix:
    @defect("DEFECT-39")
    async def test_only_admins_can_upload_documents(self, app) -> None:  # type: ignore[no-untyped-def]
        method, path = require_route(app, "upload_document")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api.test"
        ) as client:
            response = await client.request(
                method,
                path,
                files={"file": ("guide.md", b"# Guide\n", "text/markdown")},
                headers=auth_header(make_token(role=UserRole.USER)),
            )
        assert response.status_code == 403, f"a plain user got {response.status_code} on upload"

    async def test_an_admin_passes_the_upload_role_check(self, app) -> None:  # type: ignore[no-untyped-def]
        response = await call(app, "upload_document", UserRole.ADMIN, {})
        assert response.status_code != 403

    async def test_only_agents_can_reply_to_an_escalation(self, app) -> None:  # type: ignore[no-untyped-def]
        response = await call(app, "escalation_reply", UserRole.USER, {"text": "hi"})
        assert response.status_code == 403

    async def test_an_agent_passes_the_reply_role_check(self, app) -> None:  # type: ignore[no-untyped-def]
        response = await call(app, "escalation_reply", UserRole.AGENT, {"text": "hi"})
        assert response.status_code != 403

    async def test_document_listing_is_tenant_scoped_for_every_role(self, app) -> None:  # type: ignore[no-untyped-def]
        for role in UserRole:
            response = await call(app, "list_documents", role)
            assert response.status_code < 500, f"{role.value} got {response.status_code}"


class TestToolAbuse:
    """The model may try anything; the approval policy and the registry must hold regardless."""

    async def test_a_write_without_approval_is_never_executed(self) -> None:
        from factories.principals import make_principal
        from fakes.chat_model import tool_call_message
        from support.graph_harness import TENANT_A, make_graph, make_kit, run_turn

        kit = make_kit(route="saas_action")
        kit.strong.script = [
            tool_call_message("update_billing_email", {"new_email": "x@evil.example"}, "c1"),
            "Your email is now changed.",
        ]
        turn = await run_turn(
            make_graph(kit),
            question="change my billing email",
            principal=make_principal(tenant_id=TENANT_A),
        )
        assert kit.tools.calls_named("update_billing_email") == []
        assert turn is not None

    async def test_a_tool_the_model_invents_is_never_executed(self) -> None:
        from factories.principals import make_principal
        from fakes.chat_model import tool_call_message
        from support.graph_harness import TENANT_A, make_graph, make_kit, run_turn

        kit = make_kit(route="saas_action")
        kit.strong.script = [tool_call_message("drop_all_tenants", {}, "c2"), "Done."]
        await run_turn(
            make_graph(kit), question="clean up", principal=make_principal(tenant_id=TENANT_A)
        )
        assert kit.tools.calls == []
