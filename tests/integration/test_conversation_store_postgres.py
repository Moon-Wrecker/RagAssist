"""PostgresConversationStore against a real PostgreSQL: owner and status filters, and tenant isolation.

The filters must be applied in SQL before paging, so ``total`` and the page agree.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ragassist.modules.assistant.adapters.persistence import PostgresConversationStore
from ragassist.shared.db.scoped import ScopedDatabase

from .conftest import Seed


@pytest.fixture
def store(app_engines: Callable[..., AsyncEngine]) -> PostgresConversationStore:
    engine = app_engines()
    return PostgresConversationStore(ScopedDatabase(async_sessionmaker(engine, expire_on_commit=False)))


async def make(store: PostgresConversationStore, tenant, user, status: str = "open") -> str:  # type: ignore[no-untyped-def]
    cid = str(uuid4())
    await store.create(tenant_id=tenant, conversation_id=cid, user_id=user, status=status)
    return cid


async def test_the_owner_is_recorded_and_returned(seed: Seed, store: PostgresConversationStore) -> None:
    alice = seed.a_users[0]
    cid = await make(store, seed.tenant_a, alice)
    row = await store.get(seed.tenant_a, cid)
    assert row is not None and row["user_id"] == str(alice)


async def test_listing_by_owner_returns_only_that_users_conversations(
    seed: Seed, store: PostgresConversationStore
) -> None:
    alice, bob = seed.a_users
    mine = {await make(store, seed.tenant_a, alice) for _ in range(3)}
    await make(store, seed.tenant_a, bob)

    rows, total = await store.list(seed.tenant_a, owner_id=alice)

    assert total == 3 and {r["conversation_id"] for r in rows} == mine
    _, everyone = await store.list(seed.tenant_a)
    assert everyone == 4


async def test_the_status_filter_applies_before_paging(seed: Seed, store: PostgresConversationStore) -> None:
    alice = seed.a_users[0]
    for _ in range(3):
        await make(store, seed.tenant_a, alice, "open")
    escalated = {await make(store, seed.tenant_a, alice, "escalated") for _ in range(2)}

    first, total = await store.list(seed.tenant_a, limit=1, offset=0, statuses=("escalated", "resolved"))
    second, _ = await store.list(seed.tenant_a, limit=1, offset=1, statuses=("escalated", "resolved"))

    assert total == 2
    assert {first[0]["conversation_id"], second[0]["conversation_id"]} == escalated


async def test_another_tenant_sees_none_of_it(seed: Seed, store: PostgresConversationStore) -> None:
    cid = await make(store, seed.tenant_a, seed.a_users[0])
    assert await store.get(seed.tenant_b, cid) is None
    rows, total = await store.list(seed.tenant_b, owner_id=seed.a_users[0])
    assert rows == [] and total == 0
