"""HTTP caching of ``GET /v1/chunks/{id}`` and ``GET /v1/documents`` (ADR 0015).

The passage carries a strong ETag and ``private, max-age``; the document list carries an ETag and ``private,
no-cache``. A conditional request returns ``304`` only after the caller was authenticated and the resource was found
for their own tenant, so a ``304`` can never reveal that another tenant has a given chunk.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from factories.principals import auth_header, make_token
from support.specs.routes import concrete, mounted_routes

from ragassist.main import create_app
from ragassist.modules.retrieval.adapters.chunk_repository import InMemoryChunkRepository
from ragassist.modules.retrieval.api import router as chunk_router
from ragassist.modules.retrieval.domain import ChunkDetail
from ragassist.shared.config.settings import get_settings
from ragassist.shared.security.jwt import UserRole

TENANT_A = uuid4()
TENANT_B = uuid4()


@pytest.fixture
def chunks(monkeypatch: pytest.MonkeyPatch) -> InMemoryChunkRepository:
    repo = InMemoryChunkRepository()
    monkeypatch.setattr(chunk_router, "_memory_chunks", repo)
    repo.add(
        ChunkDetail(chunk_id="own-1", document_id="d", text="Refunds take 5 days."),
        tenant_id=TENANT_A,
    )
    repo.add(
        ChunkDetail(chunk_id="foreign-1", document_id="e", text="Tenant B secret."),
        tenant_id=TENANT_B,
    )
    return repo


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://api.test"
    ) as c:
        yield c


def headers(tenant=TENANT_A, role: UserRole = UserRole.USER, **extra: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {**auth_header(make_token(role=role, tenant_id=tenant)), **extra}


def conditional(tag: str, **kw):  # type: ignore[no-untyped-def]
    return headers(**{"If-None-Match": tag}, **kw)


class TestChunkValidators:
    async def test_the_passage_is_private_cacheable_and_tagged(self, client, chunks) -> None:  # type: ignore[no-untyped-def]
        response = await client.get("/v1/chunks/own-1", headers=headers())
        assert response.status_code == 200
        max_age = get_settings().CACHE_HTTP_MAX_AGE_SECONDS
        expected = f"private, max-age={max_age}" if max_age > 0 else "private, no-cache"
        assert response.headers["cache-control"] == expected
        assert "public" not in response.headers["cache-control"]
        assert "Authorization" in response.headers["vary"]
        assert response.headers["etag"].startswith('"')

    async def test_a_matching_tag_gets_304_with_no_body_and_the_same_headers(
        self, client, chunks
    ) -> None:  # type: ignore[no-untyped-def]
        first = await client.get("/v1/chunks/own-1", headers=headers())
        again = await client.get("/v1/chunks/own-1", headers=conditional(first.headers["etag"]))
        assert again.status_code == 304
        assert again.content == b""
        for name in ("etag", "cache-control", "vary"):
            assert again.headers[name] == first.headers[name]

    async def test_weak_and_listed_tags_and_star_match(self, client, chunks) -> None:  # type: ignore[no-untyped-def]
        tag = (await client.get("/v1/chunks/own-1", headers=headers())).headers["etag"]
        for value in (f"W/{tag}", f'"nope", {tag}', "*"):
            response = await client.get("/v1/chunks/own-1", headers=conditional(value))
            assert response.status_code == 304, value

    async def test_a_stale_tag_gets_the_new_body(self, client, chunks) -> None:  # type: ignore[no-untyped-def]
        old = (await client.get("/v1/chunks/own-1", headers=headers())).headers["etag"]
        chunks.add(
            ChunkDetail(chunk_id="own-1", document_id="d", text="Refunds take 7 days."),
            tenant_id=TENANT_A,
        )
        response = await client.get("/v1/chunks/own-1", headers=conditional(old))
        assert response.status_code == 200
        assert response.json()["text"] == "Refunds take 7 days."
        assert response.headers["etag"] != old


class TestConditionalRequestsStayAuthorised:
    async def test_no_token_means_401_even_with_a_valid_tag(self, client, chunks) -> None:  # type: ignore[no-untyped-def]
        tag = (await client.get("/v1/chunks/own-1", headers=headers())).headers["etag"]
        response = await client.get("/v1/chunks/own-1", headers={"If-None-Match": tag})
        assert response.status_code in (401, 403)
        assert "etag" not in response.headers

    async def test_another_tenant_replaying_the_tag_gets_404_not_304(self, client, chunks) -> None:  # type: ignore[no-untyped-def]
        tag = (await client.get("/v1/chunks/own-1", headers=headers())).headers["etag"]
        other = await client.get("/v1/chunks/own-1", headers=conditional(tag, tenant=TENANT_B))
        missing = await client.get("/v1/chunks/nothing", headers=conditional(tag, tenant=TENANT_B))
        assert other.status_code == missing.status_code == 404
        assert other.json() == missing.json()
        assert "etag" not in other.headers and "cache-control" not in other.headers

    async def test_a_missing_chunk_is_never_304_even_for_star(self, client, chunks) -> None:  # type: ignore[no-untyped-def]
        response = await client.get("/v1/chunks/nothing", headers=conditional("*"))
        assert response.status_code == 404


class TestDocumentList:
    async def test_the_list_is_tagged_and_always_revalidated(self, client) -> None:  # type: ignore[no-untyped-def]
        admin = headers(role=UserRole.ADMIN)
        first = await client.get("/v1/documents", headers=admin)
        assert first.status_code == 200
        assert first.headers["cache-control"] == "private, no-cache"
        assert "Authorization" in first.headers["vary"]
        again = await client.get(
            "/v1/documents", headers={**admin, "If-None-Match": first.headers["etag"]}
        )
        assert again.status_code == 304 and again.content == b""

    async def test_an_upload_changes_the_tag(self, client) -> None:  # type: ignore[no-untyped-def]
        admin = headers(uuid4(), role=UserRole.ADMIN)
        before = await client.get("/v1/documents", headers=admin)
        up = await client.post(
            "/v1/documents", files={"file": ("a.md", b"hello", "text/markdown")}, headers=admin
        )
        assert up.status_code in (200, 201, 202)
        after = await client.get(
            "/v1/documents", headers={**admin, "If-None-Match": before.headers["etag"]}
        )
        assert after.status_code == 200
        assert after.headers["etag"] != before.headers["etag"]

    async def test_a_token_is_required_for_a_conditional_list(self, client) -> None:  # type: ignore[no-untyped-def]
        response = await client.get("/v1/documents", headers={"If-None-Match": "*"})
        assert response.status_code in (401, 403)


class TestNoStoreOnSensitiveRoutes:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("POST", "/v1/auth/login"),
            ("POST", "/v1/auth/refresh"),
            ("POST", "/v1/auth/logout"),
            ("POST", "/v1/auth/token"),
            ("GET", "/v1/auth/me"),
            ("POST", "/v1/auth/invites/accept"),
        ],
    )
    async def test_auth_routes_are_no_store_even_on_errors(self, client, method, path) -> None:  # type: ignore[no-untyped-def]
        response = await client.request(method, path, json={})
        assert response.headers["cache-control"] == "no-store", (path, response.status_code)
        assert response.headers["pragma"] == "no-cache"

    async def test_every_mounted_auth_route_is_covered(self, client) -> None:  # type: ignore[no-untyped-def]
        """Discovered from the app, so a new /v1/auth route cannot be forgotten."""
        routes = sorted(
            (method, path)
            for method, path in mounted_routes(create_app())
            if path.startswith("/v1/auth")
        )
        assert routes, "no /v1/auth routes found"
        for method, path in routes:
            response = await client.request(method, concrete(path), json={})
            assert response.headers["cache-control"] == "no-store", (method, path)

    async def test_other_routes_are_not_marked_no_store(self, client) -> None:  # type: ignore[no-untyped-def]
        response = await client.get("/healthz")
        assert response.headers.get("cache-control") != "no-store"
