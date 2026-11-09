"""PostgresIdentityStore against a real PostgreSQL, as the restricted application role (row-level security binds it).

Covers what unit tests cannot: the slug-lookup policy, tenant isolation of sessions and invites, the case-insensitive
unique address, and single-use claims under real concurrency.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ragassist.modules.identity.adapters.postgres import PostgresIdentityStore
from ragassist.modules.identity.domain import (
    AccountConflictError,
    InviteKind,
    InviteRecord,
    SessionRecord,
    UserRecord,
    UserStatus,
    Workspace,
    WorkspaceExistsError,
    issue_token,
)
from ragassist.shared.db.scoped import ScopedDatabase
from ragassist.shared.security.jwt import UserRole

from .conftest import Seed

NOW = datetime(2030, 1, 1, tzinfo=UTC)


@pytest.fixture
def db(app_engines: Callable[..., AsyncEngine]) -> ScopedDatabase:
    return ScopedDatabase(async_sessionmaker(app_engines(), expire_on_commit=False))


@pytest.fixture
def store(db: ScopedDatabase) -> PostgresIdentityStore:
    return PostgresIdentityStore(db)


def user(tenant: UUID, email: str, role: UserRole = UserRole.USER) -> UserRecord:
    return UserRecord(
        id=uuid4(), tenant_id=tenant, email=email, role=role, status=UserStatus.ACTIVE
    )


def session_for(tenant: UUID, user_id: UUID, family: UUID | None = None) -> SessionRecord:
    return SessionRecord(
        id=uuid4(),
        tenant_id=tenant,
        user_id=user_id,
        family_id=family or uuid4(),
        token_hash=issue_token(tenant)[1],
        expires_at=NOW + timedelta(days=14),
    )


def invite_for(
    tenant: UUID, email: str, kind: InviteKind = InviteKind.INVITE, user_id: UUID | None = None
) -> InviteRecord:
    return InviteRecord(
        id=uuid4(),
        tenant_id=tenant,
        kind=kind,
        email=email,
        role=UserRole.USER,
        token_hash=issue_token(tenant)[1],
        expires_at=NOW + timedelta(hours=72),
        user_id=user_id,
        created_at=NOW,
    )


class TestWorkspaceLookup:
    async def test_a_slug_resolves_to_exactly_its_workspace(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        found = await store.workspace_by_slug("acme")
        assert found is not None and (found.id, found.name) == (seed.tenant_a, "Acme")

    async def test_an_unknown_slug_finds_nothing(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        assert await store.workspace_by_slug("nope") is None

    async def test_the_slug_policy_does_not_let_the_application_list_workspaces(
        self, seed: Seed, db: ScopedDatabase
    ) -> None:
        async with db.scope(None) as session:
            assert (await session.execute(text("SELECT count(*) FROM tenants"))).scalar_one() == 0
        async with db.scope(None) as session:
            await session.execute(text("SELECT set_config('app.tenant_slug', 'acme', true)"))
            names = (await session.execute(text("SELECT slug FROM tenants"))).scalars().all()
        assert names == ["acme"], "one slug opens one row, never the list"

    async def test_the_slug_setting_does_not_outlive_its_transaction(
        self, seed: Seed, db: ScopedDatabase
    ) -> None:
        async with db.scope(None) as session:
            await session.execute(text("SELECT set_config('app.tenant_slug', 'acme', true)"))
        async with db.scope(None) as session:
            assert (await session.execute(text("SELECT count(*) FROM tenants"))).scalar_one() == 0

    async def test_a_workspace_is_created_with_its_admin_and_the_slug_is_unique(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        workspace = Workspace(id=uuid4(), name="New Co", slug="new-co")
        admin = user(workspace.id, "boss@new.example", UserRole.ADMIN)
        await store.create_workspace(workspace, admin)

        assert (await store.workspace_by_slug("new-co")) == workspace
        stored = await store.user_by_email(workspace.id, "BOSS@new.example")
        assert stored is not None and stored.role is UserRole.ADMIN and stored.password_hash is None

        with pytest.raises(WorkspaceExistsError):
            await store.create_workspace(
                Workspace(id=uuid4(), name="Dup", slug="acme"), user(uuid4(), "x@y.example")
            )


class TestUsers:
    async def test_an_address_is_unique_per_workspace_ignoring_case(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        await store.add_user(user(seed.tenant_a, "ada@acme.example"))
        with pytest.raises(AccountConflictError):
            await store.add_user(user(seed.tenant_a, "ADA@acme.example"))
        await store.add_user(
            user(seed.tenant_b, "ada@acme.example")
        )  # another workspace may reuse it

    async def test_the_application_role_cannot_read_another_workspaces_users(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        other = seed.b_users[0]
        assert await store.user_by_id(seed.tenant_a, other) is None
        assert {u.id for u in await store.list_users(seed.tenant_a)} == set(seed.a_users)

    async def test_update_and_admin_count(self, seed: Seed, store: PostgresIdentityStore) -> None:
        admin = user(seed.tenant_a, "root@acme.example", UserRole.ADMIN)
        await store.add_user(admin)
        assert await store.count_active_admins(seed.tenant_a) == 1
        updated = await store.update_user(seed.tenant_a, admin.id, status="disabled")
        assert updated is not None and updated.status is UserStatus.DISABLED
        assert await store.count_active_admins(seed.tenant_a) == 0
        assert await store.update_user(seed.tenant_a, seed.b_users[0], role="admin") is None

    async def test_a_password_hash_is_stored_and_read_back(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        who = seed.a_users[0]
        marker = secrets.token_urlsafe(12)
        await store.set_password_hash(seed.tenant_a, who, marker)
        found = await store.user_by_id(seed.tenant_a, who)
        assert found is not None and found.password_hash == marker and found.can_sign_in


class TestSessions:
    async def test_a_session_is_found_by_hash_only_inside_its_tenant(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        record = session_for(seed.tenant_a, seed.a_users[0])
        await store.add_session(record)
        assert (await store.get_session(seed.tenant_a, record.token_hash)) == record
        assert await store.get_session(seed.tenant_b, record.token_hash) is None

    async def test_only_one_of_many_concurrent_refreshes_claims_a_session(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        record = session_for(seed.tenant_a, seed.a_users[0])
        await store.add_session(record)
        results = await asyncio.gather(
            *(store.claim_session(seed.tenant_a, record.id, NOW) for _ in range(8))
        )
        assert results.count(True) == 1

    async def test_a_claimed_or_revoked_session_cannot_be_claimed(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        first = session_for(seed.tenant_a, seed.a_users[0])
        await store.add_session(first)
        assert await store.claim_session(seed.tenant_a, first.id, NOW) is True
        assert await store.claim_session(seed.tenant_a, first.id, NOW) is False

        revoked = session_for(seed.tenant_a, seed.a_users[0])
        await store.add_session(revoked)
        await store.revoke_family(seed.tenant_a, revoked.family_id, NOW)
        assert await store.claim_session(seed.tenant_a, revoked.id, NOW) is False

    async def test_revoking_a_family_leaves_other_logins_alone(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        who = seed.a_users[0]
        a, b = session_for(seed.tenant_a, who), session_for(seed.tenant_a, who)
        await store.add_session(a)
        await store.add_session(b)
        await store.revoke_family(seed.tenant_a, a.family_id, NOW)
        assert (await store.get_session(seed.tenant_a, a.token_hash)).revoked_at is not None  # type: ignore[union-attr]
        assert (await store.get_session(seed.tenant_a, b.token_hash)).revoked_at is None  # type: ignore[union-attr]

    async def test_revoking_a_user_ends_all_their_sessions(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        who = seed.a_users[0]
        records = [session_for(seed.tenant_a, who) for _ in range(3)]
        for r in records:
            await store.add_session(r)
        await store.revoke_user_sessions(seed.tenant_a, who, NOW)
        for r in records:
            assert (await store.get_session(seed.tenant_a, r.token_hash)).revoked_at is not None  # type: ignore[union-attr]

    async def test_another_tenant_cannot_revoke_these_sessions(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        record = session_for(seed.tenant_a, seed.a_users[0])
        await store.add_session(record)
        await store.revoke_family(seed.tenant_b, record.family_id, NOW)
        await store.revoke_user_sessions(seed.tenant_b, record.user_id, NOW)
        assert (await store.get_session(seed.tenant_a, record.token_hash)).revoked_at is None  # type: ignore[union-attr]


class TestInvites:
    async def test_an_invite_is_single_use_even_under_concurrency(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        record = invite_for(seed.tenant_a, "new@acme.example")
        await store.add_invite(record)
        results = await asyncio.gather(
            *(store.claim_invite(seed.tenant_a, record.id, NOW) for _ in range(8))
        )
        assert results.count(True) == 1

    async def test_an_expired_invite_cannot_be_claimed(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        record = invite_for(seed.tenant_a, "late@acme.example")
        await store.add_invite(record)
        assert (
            await store.claim_invite(
                seed.tenant_a, record.id, record.expires_at + timedelta(seconds=1)
            )
            is False
        )

    async def test_one_pending_invite_per_address_until_it_is_revoked(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        first = invite_for(seed.tenant_a, "new@acme.example")
        await store.add_invite(first)
        with pytest.raises(AccountConflictError):
            await store.add_invite(invite_for(seed.tenant_a, "NEW@acme.example"))
        assert await store.revoke_invite(seed.tenant_a, first.id, NOW) is True
        await store.add_invite(invite_for(seed.tenant_a, "new@acme.example"))

    async def test_the_pending_list_is_per_tenant_and_hides_spent_links(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        live = invite_for(seed.tenant_a, "live@acme.example")
        spent = invite_for(seed.tenant_a, "spent@acme.example")
        theirs = invite_for(seed.tenant_b, "other@globex.example")
        for record in (live, spent, theirs):
            await store.add_invite(record)
        await store.claim_invite(seed.tenant_a, spent.id, NOW)

        pending = await store.list_pending_invites(seed.tenant_a, NOW)

        assert [i.id for i in pending] == [live.id]

    async def test_another_tenant_cannot_see_or_revoke_an_invite(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        record = invite_for(seed.tenant_a, "new@acme.example")
        await store.add_invite(record)
        assert await store.get_invite(seed.tenant_b, record.token_hash) is None
        assert await store.revoke_invite(seed.tenant_b, record.id, NOW) is False
        assert await store.claim_invite(seed.tenant_b, record.id, NOW) is False
        assert await store.get_invite(seed.tenant_a, record.token_hash) is not None

    async def test_reset_links_for_a_user_are_revoked_together(
        self, seed: Seed, store: PostgresIdentityStore
    ) -> None:
        who = seed.a_users[0]
        link = invite_for(seed.tenant_a, "u0@acme.example", InviteKind.RESET, user_id=who)
        await store.add_invite(link)
        await store.revoke_invites_for_user(seed.tenant_a, who, NOW)
        assert (await store.get_invite_by_id(seed.tenant_a, link.id)).revoked_at is not None  # type: ignore[union-attr]
