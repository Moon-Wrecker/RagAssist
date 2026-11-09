"""Sign-in, rotating refresh sessions, sign-out and "who am I" on the in-memory store."""

from __future__ import annotations

import secrets
from uuid import uuid4

import pytest
from support.identity_world import World, add_member, workspace_with_admin

from ragassist.modules.identity.application import GENERIC_FAILURE
from ragassist.modules.identity.domain import (
    AuthenticationError,
    InvalidTokenError,
    RateLimitedError,
    UserStatus,
)
from ragassist.shared.security.jwt import UserRole, decode_access_token

IP = "203.0.113.7"


async def login(world: World, slug: str, email: str, password: str | None = None, ip: str = IP):  # type: ignore[no-untyped-def]
    return await world.identity.auth.login(
        slug, email, world.password if password is None else password, ip
    )


class TestLogin:
    async def test_a_valid_login_returns_a_token_that_carries_the_verified_identity(
        self, world: World
    ) -> None:
        workspace, admin = await workspace_with_admin(world)

        signed_in = await login(world, "acme", "boss@acme.example")

        principal = decode_access_token(signed_in.access_token)
        assert (principal.user_id, principal.tenant_id, principal.role) == (
            admin.id,
            workspace.id,
            UserRole.ADMIN,
        )
        assert signed_in.refresh_token.startswith(f"{workspace.id}.")
        assert signed_in.expires_in == world.settings.AUTH_ACCESS_TOKEN_MINUTES * 60

    async def test_the_slug_and_email_are_case_insensitive(self, world: World) -> None:
        await workspace_with_admin(world)
        assert (await login(world, " ACME ", "Boss@Acme.Example")).user.email == "boss@acme.example"

    @pytest.mark.parametrize(
        "case",
        ["unknown_workspace", "unknown_email", "wrong_password", "disabled", "no_password_yet"],
    )
    async def test_every_failure_looks_the_same_and_costs_one_verification(
        self, world: World, case: str
    ) -> None:
        workspace, admin = await workspace_with_admin(world)
        member = await add_member(world, workspace, admin, "ada@acme.example", UserRole.USER)
        slug, email, password = "acme", "ada@acme.example", world.password
        if case == "unknown_workspace":
            slug = "nope"
        elif case == "unknown_email":
            email = "ghost@acme.example"
        elif case == "wrong_password":
            password = secrets.token_urlsafe(18)
        elif case == "disabled":
            await world.identity.accounts.change_member(
                workspace.id, admin.id, member.id, status=UserStatus.DISABLED
            )
        elif case == "no_password_yet":
            link = await world.identity.accounts.invite(
                workspace.id, admin.id, "new@acme.example", UserRole.USER
            )
            assert (
                link
            )  # invited but never accepted: no account exists, so there is nothing to sign in to
            email = "new@acme.example"
        before = world.hasher.verify_calls

        with pytest.raises(AuthenticationError) as caught:
            await login(world, slug, email, password)

        assert caught.value.message == GENERIC_FAILURE
        assert world.hasher.verify_calls - before == 1, (
            "timing must not reveal whether the account exists"
        )

    async def test_one_workspace_never_signs_into_another(self, world: World) -> None:
        await workspace_with_admin(world, "acme", "boss@acme.example")
        await workspace_with_admin(world, "globex", "boss@globex.example")
        with pytest.raises(AuthenticationError):
            await login(world, "globex", "boss@acme.example")

    async def test_an_overlong_password_is_refused_not_hashed(self, world: World) -> None:
        await workspace_with_admin(world)
        with pytest.raises(AuthenticationError):
            await login(world, "acme", "boss@acme.example", "x" * 100_000)

    async def test_repeated_failures_lock_the_account_even_for_the_right_password(
        self, world: World
    ) -> None:
        await workspace_with_admin(world)
        for _ in range(world.settings.AUTH_LOGIN_MAX_FAILURES):
            with pytest.raises(AuthenticationError):
                await login(world, "acme", "boss@acme.example", secrets.token_urlsafe(18))
        with pytest.raises(RateLimitedError):
            await login(world, "acme", "boss@acme.example")

    async def test_an_old_hash_is_upgraded_on_a_successful_login(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        world.hasher.rehash_everything = True
        hashes_before = world.hasher.hash_calls
        await login(world, "acme", "boss@acme.example")
        assert world.hasher.hash_calls == hashes_before + 1
        assert (await world.store.user_by_id(workspace.id, admin.id)).password_hash  # type: ignore[union-attr]


class TestRefresh:
    async def test_a_refresh_rotates_the_token_and_returns_a_new_access_token(
        self, world: World
    ) -> None:
        await workspace_with_admin(world)
        first = await login(world, "acme", "boss@acme.example")

        second = await world.identity.auth.refresh(first.refresh_token)

        assert second.refresh_token != first.refresh_token
        assert decode_access_token(second.access_token).user_id == first.user.id

    async def test_the_old_token_cannot_be_used_again_and_the_replay_ends_the_whole_login(
        self, world: World
    ) -> None:
        await workspace_with_admin(world)
        first = await login(world, "acme", "boss@acme.example")
        second = await world.identity.auth.refresh(first.refresh_token)

        with pytest.raises(InvalidTokenError):
            await world.identity.auth.refresh(first.refresh_token)  # a copied token replayed

        with pytest.raises(InvalidTokenError):
            await world.identity.auth.refresh(
                second.refresh_token
            )  # the legitimate one is dead too

    async def test_two_logins_are_independent_families(self, world: World) -> None:
        await workspace_with_admin(world)
        laptop = await login(world, "acme", "boss@acme.example")
        phone = await login(world, "acme", "boss@acme.example")
        await world.identity.auth.refresh(laptop.refresh_token)
        with pytest.raises(InvalidTokenError):
            await world.identity.auth.refresh(laptop.refresh_token)
        await world.identity.auth.refresh(
            phone.refresh_token
        )  # the replay on one device does not touch the other

    async def test_an_expired_session_is_refused(self, world: World) -> None:
        await workspace_with_admin(world)
        signed_in = await login(world, "acme", "boss@acme.example")
        world.clock.advance(days=world.settings.AUTH_REFRESH_TOKEN_DAYS, seconds=1)
        with pytest.raises(InvalidTokenError):
            await world.identity.auth.refresh(signed_in.refresh_token)

    async def test_a_disabled_user_cannot_refresh(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        member = await add_member(world, workspace, admin, "ada@acme.example", UserRole.USER)
        signed_in = await login(world, "acme", "ada@acme.example")
        await world.identity.accounts.change_member(
            workspace.id, admin.id, member.id, status=UserStatus.DISABLED
        )
        with pytest.raises(InvalidTokenError):
            await world.identity.auth.refresh(signed_in.refresh_token)

    async def test_a_role_change_shows_up_in_the_next_access_token(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        member = await add_member(world, workspace, admin, "ada@acme.example", UserRole.USER)
        signed_in = await login(world, "acme", "ada@acme.example")
        await world.identity.accounts.change_member(
            workspace.id, admin.id, member.id, role=UserRole.AGENT
        )
        refreshed = await world.identity.auth.refresh(signed_in.refresh_token)
        assert decode_access_token(refreshed.access_token).role is UserRole.AGENT

    @pytest.mark.parametrize("bad", ["", "garbage", f"{uuid4()}.not-a-real-secret"])
    async def test_garbage_is_refused(self, world: World, bad: str) -> None:
        with pytest.raises(InvalidTokenError):
            await world.identity.auth.refresh(bad)

    async def test_a_token_is_only_good_in_its_own_tenant(self, world: World) -> None:
        await workspace_with_admin(world, "acme", "boss@acme.example")
        other, _ = await workspace_with_admin(world, "globex", "boss@globex.example")
        mine = await login(world, "acme", "boss@acme.example")
        random_part = mine.refresh_token.split(".", 1)[1]
        with pytest.raises(InvalidTokenError):
            await world.identity.auth.refresh(f"{other.id}.{random_part}")


class TestLogoutAndMe:
    async def test_logout_kills_the_session(self, world: World) -> None:
        await workspace_with_admin(world)
        signed_in = await login(world, "acme", "boss@acme.example")
        await world.identity.auth.logout(signed_in.refresh_token)
        with pytest.raises(InvalidTokenError):
            await world.identity.auth.refresh(signed_in.refresh_token)

    @pytest.mark.parametrize("token", ["", "junk", f"{uuid4()}.unknown"])
    async def test_logout_with_nothing_valid_still_succeeds(self, world: World, token: str) -> None:
        await world.identity.auth.logout(token)

    async def test_me_returns_the_user_and_workspace(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        user, found = await world.identity.auth.me(workspace.id, admin.id)
        assert (user.id, found.slug) == (admin.id, "acme")

    async def test_me_refuses_a_user_who_has_been_disabled(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        member = await add_member(world, workspace, admin, "ada@acme.example", UserRole.USER)
        await world.identity.accounts.change_member(
            workspace.id, admin.id, member.id, status=UserStatus.DISABLED
        )
        with pytest.raises(AuthenticationError):
            await world.identity.auth.me(workspace.id, member.id)

    async def test_me_does_not_cross_tenants(self, world: World) -> None:
        a, admin_a = await workspace_with_admin(world, "acme", "boss@acme.example")
        b, _ = await workspace_with_admin(world, "globex", "boss@globex.example")
        with pytest.raises(AuthenticationError):
            await world.identity.auth.me(b.id, admin_a.id)
        assert a.id != b.id
