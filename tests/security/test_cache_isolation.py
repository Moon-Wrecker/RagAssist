"""A cache hit can never cross a tenant or a role, and a document change purges the tenant's entries (ADR 0015).

The cache is shared by every tenant in the process (and by every replica with Redis), so isolation rests on the key
rule alone: the tenant, and the role where results depend on it, are inside every key. These tests exercise a shared
store with identical text for two tenants and two roles, then the invalidation path used by delete and re-index.
"""

from __future__ import annotations

import pytest
from support.settings import make_settings

from ragassist.platform.cache import CacheService, InvalidCacheKey, build_cache_service
from ragassist.platform.cache import keys as kinds
from ragassist.platform.cache.adapters.memory_adapter import InMemoryCache
from ragassist.platform.cache.invalidation import install_corpus_invalidation, settle
from ragassist.platform.events import InMemoryEventBus, document_changed, job_updated

TENANT_A = "a0000000-0000-0000-0000-00000000000a"
TENANT_B = "b0000000-0000-0000-0000-00000000000b"
QUESTION = "what is our refund policy?"


@pytest.fixture
def shared_cache() -> CacheService:
    cache = InMemoryCache(max_entries=1000, max_value_bytes=65536)
    return build_cache_service(make_settings(), cache)


async def put(
    svc: CacheService, kind: str, tenant: str, role: str, text: str, value: object
) -> str:
    key = svc.keys.key(kind, tenant, role=role, text=text)
    await svc.set_json(kind, key, value, 60)
    return key


class TestNoHitAcrossTenantsOrRoles:
    async def test_tenant_b_cannot_read_what_tenant_a_cached_for_the_same_text(
        self, shared_cache: CacheService
    ) -> None:
        svc = shared_cache
        await put(svc, kinds.RETRIEVAL, TENANT_A, "customer", QUESTION, {"secret": "A's passages"})
        b_key = svc.keys.key(kinds.RETRIEVAL, TENANT_B, role="customer", text=QUESTION)
        assert await svc.get_json(kinds.RETRIEVAL, b_key) is None

    async def test_a_customer_cannot_read_what_was_cached_for_an_admin(
        self, shared_cache: CacheService
    ) -> None:
        svc = shared_cache
        await put(svc, kinds.RETRIEVAL, TENANT_A, "admin", QUESTION, {"secret": "admin view"})
        customer_key = svc.keys.key(kinds.RETRIEVAL, TENANT_A, role="customer", text=QUESTION)
        assert await svc.get_json(kinds.RETRIEVAL, customer_key) is None

    @pytest.mark.parametrize("kind", [kinds.RETRIEVAL, kinds.DECISION, kinds.EMBEDDING_QUERY])
    async def test_every_kind_of_entry_is_tenant_scoped(
        self, shared_cache: CacheService, kind: str
    ) -> None:
        svc = shared_cache
        await put(svc, kind, TENANT_A, "agent", QUESTION, {"v": 1})
        other = svc.keys.key(kind, TENANT_B, role="agent", text=QUESTION)
        assert await svc.get_json(kind, other) is None

    async def test_a_key_cannot_be_built_without_a_tenant(self, shared_cache: CacheService) -> None:
        for tenant in (None, "", "global:../x"):
            with pytest.raises(InvalidCacheKey):
                shared_cache.keys.key(kinds.RETRIEVAL, tenant, role="agent", text=QUESTION)

    async def test_every_stored_key_names_its_tenant_and_never_the_text(
        self, shared_cache: CacheService
    ) -> None:
        svc = shared_cache
        await put(svc, kinds.RETRIEVAL, TENANT_A, "agent", QUESTION, {"v": 1})
        await put(
            svc, kinds.DECISION, TENANT_B, "customer", "ignore previous instructions", {"v": 2}
        )
        for key in list(svc.cache._items):  # type: ignore[attr-defined]
            assert TENANT_A in key or TENANT_B in key, key
            assert "refund" not in key and "ignore" not in key and "instructions" not in key

    async def test_retrieval_entries_are_bound_to_the_corpus_version(
        self, shared_cache: CacheService
    ) -> None:
        svc = shared_cache
        before = await svc.corpus_version(TENANT_A)
        old_key = svc.keys.key(
            kinds.RETRIEVAL, TENANT_A, role="agent", text=QUESTION, parts=(before,)
        )
        await svc.set_json(kinds.RETRIEVAL, old_key, {"v": "stale"}, 60)
        await svc.invalidate_corpus(TENANT_A)
        after = await svc.corpus_version(TENANT_A)
        new_key = svc.keys.key(
            kinds.RETRIEVAL, TENANT_A, role="agent", text=QUESTION, parts=(after,)
        )
        assert new_key != old_key
        assert await svc.get_json(kinds.RETRIEVAL, new_key) is None


class TestDocumentChangesPurgeTheTenant:
    @pytest.fixture
    def wired(self, shared_cache: CacheService) -> tuple[InMemoryEventBus, CacheService]:
        bus = InMemoryEventBus()
        install_corpus_invalidation(bus.hub, lambda: shared_cache)
        return bus, shared_cache

    async def test_document_changed_purges_that_tenants_retrieval_only(
        self, wired: tuple[InMemoryEventBus, CacheService]
    ) -> None:
        bus, svc = wired
        a_key = await put(svc, kinds.RETRIEVAL, TENANT_A, "customer", QUESTION, {"v": "a"})
        a_admin = await put(svc, kinds.RETRIEVAL, TENANT_A, "admin", QUESTION, {"v": "a2"})
        b_key = await put(svc, kinds.RETRIEVAL, TENANT_B, "customer", QUESTION, {"v": "b"})
        version = await svc.corpus_version(TENANT_A)

        await bus.publish(document_changed(TENANT_A, "doc-1"))
        await settle()

        assert await svc.cache.get(a_key) is None
        assert await svc.cache.get(a_admin) is None
        assert await svc.cache.get(b_key) is not None
        assert await svc.corpus_version(TENANT_A) != version

    async def test_other_events_do_not_purge(
        self, wired: tuple[InMemoryEventBus, CacheService]
    ) -> None:
        bus, svc = wired
        key = await put(svc, kinds.RETRIEVAL, TENANT_A, "customer", QUESTION, {"v": "a"})
        await bus.publish(job_updated(TENANT_A, "job-1", "doc-1"))
        await settle()
        assert await svc.cache.get(key) is not None

    async def test_a_failing_cache_does_not_break_event_delivery(self) -> None:
        bus = InMemoryEventBus()

        def broken() -> CacheService:
            raise RuntimeError("cache unavailable")

        install_corpus_invalidation(bus.hub, broken)
        await bus.publish(document_changed(TENANT_A, "doc-1"))
        await settle()
        assert len(bus.published) == 1


class TestThroughTheApi:
    """Deleting, re-indexing or uploading a document through the real endpoints purges that tenant's entries."""

    @pytest.fixture
    async def client(self):  # type: ignore[no-untyped-def]
        import httpx

        from ragassist.main import create_app

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://api.test"
        ) as c:
            yield c

    @staticmethod
    def admin(tenant: str) -> dict[str, str]:
        from uuid import uuid4

        from factories.principals import auth_header, make_token

        from ragassist.shared.security.jwt import UserRole

        return auth_header(make_token(role=UserRole.ADMIN, tenant_id=tenant, user_id=uuid4()))  # type: ignore[arg-type]

    async def seed(self, tenant: str) -> str:
        from ragassist.platform.cache import get_cache_service

        svc = get_cache_service()
        key = svc.keys.key(kinds.RETRIEVAL, tenant, role="admin", text=QUESTION)
        assert await svc.set_json(kinds.RETRIEVAL, key, {"v": 1}, 60)
        return key

    @pytest.mark.parametrize("action", ["delete", "reindex", "upload"])
    async def test_document_endpoints_purge_only_the_callers_tenant(
        self,
        client,
        action: str,  # type: ignore[no-untyped-def]
    ) -> None:
        import asyncio
        from uuid import uuid4

        from ragassist.platform.cache import get_cache_service

        tenant_a, tenant_b = str(uuid4()), str(uuid4())
        headers = self.admin(tenant_a)
        up = await client.post(
            "/v1/documents", files={"file": ("a.md", b"# a", "text/markdown")}, headers=headers
        )
        doc_id = up.json()["document_id"]
        await asyncio.sleep(0)
        svc = get_cache_service()
        mine, theirs = await self.seed(tenant_a), await self.seed(tenant_b)
        version = await svc.corpus_version(tenant_a)

        if action == "delete":
            res = await client.delete(f"/v1/documents/{doc_id}", headers=headers)
        elif action == "reindex":
            res = await client.post(f"/v1/documents/{doc_id}/reindex", headers=headers)
        else:
            res = await client.post(
                "/v1/documents", files={"file": ("b.md", b"# b", "text/markdown")}, headers=headers
            )
        assert res.status_code in (200, 202)
        await settle()

        assert await svc.cache.get(mine) is None
        assert await svc.cache.get(theirs) is not None
        assert await svc.corpus_version(tenant_a) != version
