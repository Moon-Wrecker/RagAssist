"""Regression tests for the security audit findings (each was reproduced before it was fixed).

Every test names the boundary it protects. They run on the in-memory backends, so they need no Docker.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from factories.principals import auth_header, make_token
from fastapi import HTTPException

from ragassist.main import create_app
from ragassist.modules.assistant.application.conversation_store import InMemoryConversationStore
from ragassist.shared.config import settings as settings_module
from ragassist.shared.security.jwt import Principal, UserRole
from ragassist.shared.security.rate_limiter import SlidingWindowRateLimiter

pytestmark = pytest.mark.security


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    settings_module._settings = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://api.test"
    ) as c:
        yield c


def as_role(role: UserRole, tenant) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return auth_header(make_token(role=role, tenant_id=tenant))


async def upload(client: httpx.AsyncClient, tenant) -> str:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/v1/documents",
        headers=as_role(UserRole.ADMIN, tenant),
        files={"file": ("kb.md", b"# Title\n\nbody", "text/markdown")},
    )
    assert response.status_code == 202, response.text
    return response.json()["document_id"]


class TestDocumentMutationIsAdminOnly:
    @pytest.mark.parametrize("role", [UserRole.USER, UserRole.AGENT])
    async def test_a_non_admin_cannot_delete_or_reindex(
        self, client: httpx.AsyncClient, role: UserRole
    ) -> None:
        tenant = uuid4()
        doc = await upload(client, tenant)
        headers = as_role(role, tenant)

        assert (await client.delete(f"/v1/documents/{doc}", headers=headers)).status_code == 403
        assert (
            await client.post(f"/v1/documents/{doc}/reindex", headers=headers)
        ).status_code == 403

        listing = await client.get("/v1/documents", headers=headers)
        assert [d["document_id"] for d in listing.json()["items"]] == [doc], "the document survived"

    async def test_an_admin_still_can(self, client: httpx.AsyncClient) -> None:
        tenant = uuid4()
        doc = await upload(client, tenant)
        admin = as_role(UserRole.ADMIN, tenant)
        assert (await client.post(f"/v1/documents/{doc}/reindex", headers=admin)).status_code == 200
        assert (await client.delete(f"/v1/documents/{doc}", headers=admin)).status_code == 200


class TestUploadIsBounded:
    async def test_an_oversized_upload_is_refused_without_reading_it_all(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ragassist.modules.knowledge.api import router as knowledge_router

        monkeypatch.setattr(knowledge_router, "MAX_UPLOAD_BYTES", 2048)
        monkeypatch.setattr(knowledge_router, "_READ_CHUNK", 512)
        response = await client.post(
            "/v1/documents",
            headers=as_role(UserRole.ADMIN, uuid4()),
            files={"file": ("big.md", b"x" * 5000, "text/markdown")},
        )
        assert response.status_code == 413


class TestMetrics:
    async def test_only_administrators_read_them(self, client: httpx.AsyncClient) -> None:
        tenant = uuid4()
        assert (
            await client.get("/metrics", headers=as_role(UserRole.USER, tenant))
        ).status_code == 403
        assert (
            await client.get("/metrics", headers=as_role(UserRole.AGENT, tenant))
        ).status_code == 403
        assert (
            await client.get("/metrics", headers=as_role(UserRole.ADMIN, tenant))
        ).status_code == 200

    async def test_junk_paths_do_not_create_new_series(self, client: httpx.AsyncClient) -> None:
        admin = as_role(UserRole.ADMIN, uuid4())

        async def series() -> int:
            text = (await client.get("/metrics", headers=admin)).text
            return sum(1 for line in text.splitlines() if line.startswith("http_requests_total"))

        for _ in range(5):
            await client.get(f"/v1/nowhere/{uuid4()}")
        before = await series()
        for _ in range(100):
            await client.get(f"/v1/nowhere/{uuid4()}")
            await client.get(f"/v1/conversations/{uuid4()}", headers=admin)
        assert await series() - before <= 2, "labels are route templates, not raw paths"

    async def test_identifiers_in_paths_never_reach_the_exposition(
        self, client: httpx.AsyncClient
    ) -> None:
        admin = as_role(UserRole.ADMIN, uuid4())
        secret_id = str(uuid4())
        await client.get(f"/v1/conversations/{secret_id}", headers=admin)
        assert secret_id not in (await client.get("/metrics", headers=admin)).text

    async def test_a_quote_in_the_path_cannot_forge_exposition_text(
        self, client: httpx.AsyncClient
    ) -> None:
        admin = as_role(UserRole.ADMIN, uuid4())
        await client.get("/v1/x%22%7D%20evil_metric%201%0A")
        for line in (await client.get("/metrics", headers=admin)).text.splitlines():
            assert not line.startswith("evil_metric")

    def test_label_values_are_escaped(self) -> None:
        from ragassist.shared.observability.metrics import SimplePrometheusRegistry

        registry = SimplePrometheusRegistry()
        registry.increment_counter("m", handler='a"b\\c\nd')
        assert 'handler="a\\"b\\\\c\\nd"' in registry.export_text()

    def test_the_latency_histogram_uses_constant_memory(self) -> None:
        from ragassist.shared.observability.metrics import SimplePrometheusRegistry

        registry = SimplePrometheusRegistry()
        for _ in range(10_000):
            registry.observe_histogram("h", 0.5)
        assert len(registry._histograms["h"]) == 2
        assert (
            "h_count 10000" in registry.export_text()
            and "h_sum 5000.000000" in registry.export_text()
        )


class TestRateLimiter:
    async def test_forging_the_authorization_header_does_not_buy_a_fresh_bucket(
        self, client: httpx.AsyncClient
    ) -> None:
        from ragassist.shared.security import rate_limiter

        limiter = SlidingWindowRateLimiter(limit=5, window_seconds=60.0)
        app = create_app()
        app.user_middleware.clear()
        app.middleware_stack = None
        app.add_middleware(rate_limiter.RateLimitMiddleware, limiter=limiter)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api.test"
        ) as c:
            codes = [
                (
                    await c.get("/v1/documents", headers={"Authorization": f"Bearer forged-{i}"})
                ).status_code
                for i in range(12)
            ]
        assert 429 in codes, "one client address, one bucket, whatever it sends"
        assert len(limiter._history) == 1

    def test_the_table_is_bounded(self) -> None:
        limiter = SlidingWindowRateLimiter(limit=5, window_seconds=60.0, max_keys=100)
        for i in range(1000):
            limiter.is_allowed(f"client-{i}")
        assert len(limiter._history) <= 100


class TestCheckpointCarriesNoBearerToken:
    def test_the_durable_checkpoint_gets_a_principal_without_its_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ragassist.modules.assistant.api import router
        from ragassist.modules.assistant.graph.serde import checkpoint_serde

        marker = "bearer-" + uuid4().hex
        principal = Principal(
            user_id=uuid4(), tenant_id=uuid4(), role=UserRole.USER, raw_token=marker
        )
        monkeypatch.setattr(
            "ragassist.runtime.active_runtime", lambda: object()
        )  # the Postgres runtime is up

        stripped = router._checkpointable(principal)

        _, blob = checkpoint_serde().dumps_typed({"principal": stripped})
        assert marker.encode() not in blob
        assert (stripped.user_id, stripped.tenant_id, stripped.role) == (
            principal.user_id,
            principal.tenant_id,
            principal.role,
        )

    def test_the_in_process_checkpointer_keeps_the_token_the_in_process_tools_use(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ragassist.modules.assistant.api import router

        principal = Principal(user_id=uuid4(), tenant_id=uuid4(), role=UserRole.USER, raw_token="t")
        monkeypatch.setattr("ragassist.runtime.active_runtime", lambda: None)
        assert router._checkpointable(principal) == principal
        assert replace(principal, raw_token="") != principal


class TestInMemoryStoreIsTenantKeyed:
    async def test_the_same_conversation_id_in_two_tenants_does_not_collide(self) -> None:
        store = InMemoryConversationStore()
        tenant_a, tenant_b, cid = uuid4(), uuid4(), str(uuid4())
        store.create(tenant_id=tenant_a, conversation_id=cid, user_id=uuid4())
        await store.append_message(tenant_a, cid, {"role": "user", "text": "private"})

        store.create(tenant_id=tenant_b, conversation_id=cid, user_id=uuid4())

        mine = await store.get(tenant_a, cid)
        assert mine is not None and [m["text"] for m in mine["messages"]] == ["private"]
        theirs = await store.get(tenant_b, cid)
        assert theirs is not None and theirs["messages"] == []


class TestEscalationActsOnlyOnEscalatedConversations:
    async def _open_conversation(self, client: httpx.AsyncClient, tenant) -> str:  # type: ignore[no-untyped-def]
        created = await client.post(
            "/v1/conversations", headers=as_role(UserRole.USER, tenant), json={"title": "hello"}
        )
        assert created.status_code == 201, created.text
        return created.json()["conversation_id"]

    async def test_an_agent_cannot_reply_to_or_resolve_an_open_conversation(
        self, client: httpx.AsyncClient
    ) -> None:
        tenant = uuid4()
        cid = await self._open_conversation(client, tenant)
        agent = as_role(UserRole.AGENT, tenant)

        reply = await client.post(
            f"/v1/escalations/{cid}/reply", headers=agent, json={"text": "hi"}
        )
        resolve = await client.post(f"/v1/escalations/{cid}/resolve", headers=agent)

        assert reply.status_code == 409 and resolve.status_code == 409
        history = await client.get(
            f"/v1/conversations/{cid}", headers=as_role(UserRole.USER, tenant)
        )
        assert history.json().get("status", "open") == "open"
        assert all(m["role"] != "agent" for m in history.json().get("messages", []))


def test_unused_import_guard() -> None:
    assert HTTPException  # keeps the import list honest if a test above is removed
