"""``GET /v1/chunks/{chunk_id}``: the passage behind a citation, through the retrieval facade.

A user reads chunks of their own tenant and global ones; another tenant's chunk and an unknown id look the same (404).
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from factories.principals import auth_header, make_token

from ragassist.main import create_app
from ragassist.modules.retrieval.adapters.chunk_repository import InMemoryChunkRepository
from ragassist.modules.retrieval.api import router as chunk_router
from ragassist.modules.retrieval.application import GetChunk
from ragassist.modules.retrieval.domain import ChunkDetail
from ragassist.shared.security.jwt import UserRole

TENANT_A = uuid4()
TENANT_B = uuid4()


@pytest.fixture
def chunks(monkeypatch: pytest.MonkeyPatch) -> InMemoryChunkRepository:
    repo = InMemoryChunkRepository()
    monkeypatch.setattr(chunk_router, "_memory_chunks", repo)
    repo.add(
        ChunkDetail(
            chunk_id="own-1",
            document_id="doc-a",
            text="Refunds are issued within 5 business days.",
            document_title="Billing FAQ",
            title="Refunds",
            page=3,
            heading_path=("Billing", "Refunds"),
        ),
        tenant_id=TENANT_A,
    )
    repo.add(
        ChunkDetail(
            chunk_id="global-1", document_id="doc-g", text="Shared guide text.", is_global=True
        ),
        tenant_id=None,
    )
    repo.add(
        ChunkDetail(chunk_id="foreign-1", document_id="doc-b", text="Tenant B secret."),
        tenant_id=TENANT_B,
    )
    return repo


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://api.test"
    ) as c:
        yield c


def headers(tenant=TENANT_A, role: UserRole = UserRole.USER) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return auth_header(make_token(role=role, tenant_id=tenant))


class TestGetChunk:
    async def test_the_passage_and_its_provenance_are_returned(self, client, chunks) -> None:  # type: ignore[no-untyped-def]
        response = await client.get("/v1/chunks/own-1", headers=headers())
        assert response.status_code == 200
        assert response.json() == {
            "chunk_id": "own-1",
            "document_id": "doc-a",
            "document_title": "Billing FAQ",
            "title": "Refunds",
            "text": "Refunds are issued within 5 business days.",
            "page": 3,
            "heading_path": ["Billing", "Refunds"],
            "is_global": False,
        }

    async def test_a_global_chunk_is_readable_by_every_tenant_and_marked_global(
        self, client, chunks
    ) -> None:  # type: ignore[no-untyped-def]
        for tenant in (TENANT_A, TENANT_B):
            response = await client.get("/v1/chunks/global-1", headers=headers(tenant))
            assert response.status_code == 200 and response.json()["is_global"] is True

    @pytest.mark.parametrize("role", [UserRole.USER, UserRole.AGENT, UserRole.ADMIN])
    async def test_every_role_of_the_tenant_may_read_a_chunk(self, client, chunks, role) -> None:  # type: ignore[no-untyped-def]
        assert (await client.get("/v1/chunks/own-1", headers=headers(role=role))).status_code == 200

    async def test_another_tenants_chunk_looks_like_a_missing_one(self, client, chunks) -> None:  # type: ignore[no-untyped-def]
        foreign = await client.get("/v1/chunks/foreign-1", headers=headers())
        missing = await client.get("/v1/chunks/does-not-exist", headers=headers())
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
        assert "secret" not in foreign.text

    async def test_a_token_is_required(self, client, chunks) -> None:  # type: ignore[no-untyped-def]
        assert (await client.get("/v1/chunks/own-1")).status_code in (401, 403)

    async def test_an_oversized_id_is_not_looked_up(self) -> None:
        class Spy:
            calls = 0

            async def get(self, tenant_id: object, chunk_id: str) -> ChunkDetail | None:
                Spy.calls += 1
                return None

        assert await GetChunk(Spy()).execute(TENANT_A, "x" * 200) is None
        assert Spy.calls == 0
