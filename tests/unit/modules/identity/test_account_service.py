"""Workspaces, invites, one-time links and team management on the in-memory store."""

from __future__ import annotations

import pytest
from support.identity_world import World, add_member, token_of, workspace_with_admin

from ragassist.modules.identity.domain import (
    AccountConflictError,
    InvalidTokenError,
    LastAdminError,
    PasswordPolicyError,
    SelfChangeError,
    UserStatus,
    WorkspaceExistsError,
)
from ragassist.shared.domain import EntityNotFoundError, ValidationError
from ragassist.shared.security.jwt import UserRole, decode_access_token


class TestCreateWorkspace:
    async def test_it_creates_the_workspace_and_an_admin_without_a_password(
        self, world: World
    ) -> None:
        workspace, link = await world.identity.accounts.create_workspace(
            "Acme Inc", "Acme", "Boss@Acme.example"
        )

        assert (workspace.name, workspace.slug) == ("Acme Inc", "acme")
        admin = await world.store.user_by_email(workspace.id, "boss@acme.example")
        assert admin is not None and admin.role is UserRole.ADMIN and admin.password_hash is None
        assert not admin.can_sign_in, (
            "no default password exists: the account is unusable until the link is spent"
        )
        assert link.url.startswith(f"{world.identity.policy.web_base_url}/accept#token=")

    async def test_the_token_sits_in_the_url_fragment_so_servers_never_see_it(
        self, world: World
    ) -> None:
        _, link = await world.identity.accounts.create_workspace(
            "Acme", "acme", "boss@acme.example"
        )
        assert "?" not in link.url and "#token=" in link.url

    async def test_a_taken_slug_is_refused(self, world: World) -> None:
        await world.identity.accounts.create_workspace("Acme", "acme", "boss@acme.example")
        with pytest.raises(WorkspaceExistsError):
            await world.identity.accounts.create_workspace("Other", "acme", "x@other.example")

    @pytest.mark.parametrize(
        ("name", "slug", "email"),
        [("", "acme", "a@x.com"), ("Acme", "A c", "a@x.com"), ("Acme", "acme", "not-an-email")],
    )
    async def test_bad_input_is_refused(
        self, world: World, name: str, slug: str, email: str
    ) -> None:
        with pytest.raises(ValidationError):
            await world.identity.accounts.create_workspace(name, slug, email)


class TestAcceptingALink:
    async def test_the_admin_sets_a_password_and_is_signed_in(self, world: World) -> None:
        workspace, link = await world.identity.accounts.create_workspace(
            "Acme", "acme", "boss@acme.example"
        )

        signed_in = await world.identity.accounts.accept(token_of(link), world.password)

        assert decode_access_token(signed_in.access_token).tenant_id == workspace.id
        assert signed_in.user.can_sign_in

    async def test_a_link_works_once(self, world: World) -> None:
        _, link = await world.identity.accounts.create_workspace(
            "Acme", "acme", "boss@acme.example"
        )
        await world.identity.accounts.accept(token_of(link), world.password)
        with pytest.raises(InvalidTokenError):
            await world.identity.accounts.accept(token_of(link), world.password)

    async def test_a_link_expires(self, world: World) -> None:
        _, link = await world.identity.accounts.create_workspace(
            "Acme", "acme", "boss@acme.example"
        )
        world.clock.advance(hours=world.settings.AUTH_INVITE_HOURS, seconds=1)
        with pytest.raises(InvalidTokenError):
            await world.identity.accounts.accept(token_of(link), world.password)

    async def test_a_weak_password_is_refused_and_the_link_is_not_spent(self, world: World) -> None:
        _, link = await world.identity.accounts.create_workspace(
            "Acme", "acme", "boss@acme.example"
        )
        with pytest.raises(PasswordPolicyError):
            await world.identity.accounts.accept(token_of(link), "short")
        await world.identity.accounts.accept(token_of(link), world.password)  # still valid

    @pytest.mark.parametrize("bad", ["", "garbage", "00000000-0000-0000-0000-000000000000.nope"])
    async def test_garbage_is_refused(self, world: World, bad: str) -> None:
        with pytest.raises(InvalidTokenError):
            await world.identity.accounts.accept(bad, world.password)

    async def test_an_invite_creates_the_account_with_the_invited_role(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        member = await add_member(world, workspace, admin, "Agent@Acme.example", UserRole.AGENT)
        assert (member.email, member.role, member.status) == (
            "agent@acme.example",
            UserRole.AGENT,
            UserStatus.ACTIVE,
        )

    async def test_a_reset_link_changes_the_password_and_ends_every_session(
        self, world: World
    ) -> None:
        workspace, admin = await workspace_with_admin(world)
        member = await add_member(world, workspace, admin, "ada@acme.example", UserRole.USER)
        old = await world.identity.auth.login(
            "acme", "ada@acme.example", world.password, "198.51.100.1"
        )

        link = await world.identity.accounts.reset_link(workspace.id, admin.id, member.id)
        new_password = world.password + "-new"
        await world.identity.accounts.accept(token_of(link), new_password)

        with pytest.raises(InvalidTokenError):
            await world.identity.auth.refresh(old.refresh_token)
        await world.identity.auth.login("acme", "ada@acme.example", new_password, "198.51.100.1")

    async def test_a_new_reset_link_supersedes_the_previous_one(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        member = await add_member(world, workspace, admin, "ada@acme.example", UserRole.USER)
        first = await world.identity.accounts.reset_link(workspace.id, admin.id, member.id)
        second = await world.identity.accounts.reset_link(workspace.id, admin.id, member.id)
        with pytest.raises(InvalidTokenError):
            await world.identity.accounts.accept(token_of(first), world.password + "-x")
        await world.identity.accounts.accept(token_of(second), world.password + "-x")

    async def test_a_link_for_a_disabled_account_is_refused(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        member = await add_member(world, workspace, admin, "ada@acme.example", UserRole.USER)
        link = await world.identity.accounts.reset_link(workspace.id, admin.id, member.id)
        await world.identity.accounts.change_member(
            workspace.id, admin.id, member.id, status=UserStatus.DISABLED
        )
        with pytest.raises(InvalidTokenError):
            await world.identity.accounts.accept(token_of(link), world.password)


class TestInvites:
    async def test_an_address_with_an_account_cannot_be_invited(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        with pytest.raises(AccountConflictError):
            await world.identity.accounts.invite(
                workspace.id, admin.id, "BOSS@acme.example", UserRole.USER
            )

    async def test_an_address_can_have_only_one_pending_invite(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        await world.identity.accounts.invite(
            workspace.id, admin.id, "new@acme.example", UserRole.USER
        )
        with pytest.raises(AccountConflictError):
            await world.identity.accounts.invite(
                workspace.id, admin.id, "New@acme.example", UserRole.AGENT
            )

    async def test_revoking_frees_the_address_and_kills_the_link(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        link = await world.identity.accounts.invite(
            workspace.id, admin.id, "new@acme.example", UserRole.USER
        )
        await world.identity.accounts.revoke_invite(workspace.id, link.invite_id)
        with pytest.raises(InvalidTokenError):
            await world.identity.accounts.accept(token_of(link), world.password)
        await world.identity.accounts.invite(
            workspace.id, admin.id, "new@acme.example", UserRole.USER
        )

    async def test_revoking_something_unknown_is_a_not_found(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        link = await world.identity.accounts.invite(
            workspace.id, admin.id, "new@acme.example", UserRole.USER
        )
        await world.identity.accounts.revoke_invite(workspace.id, link.invite_id)
        with pytest.raises(EntityNotFoundError):
            await world.identity.accounts.revoke_invite(workspace.id, link.invite_id)

    async def test_the_pending_list_shows_only_usable_invites_of_this_workspace(
        self, world: World
    ) -> None:
        a, admin_a = await workspace_with_admin(world, "acme", "boss@acme.example")
        b, admin_b = await workspace_with_admin(world, "globex", "boss@globex.example")
        mine = await world.identity.accounts.invite(
            a.id, admin_a.id, "one@acme.example", UserRole.USER
        )
        gone = await world.identity.accounts.invite(
            a.id, admin_a.id, "two@acme.example", UserRole.USER
        )
        await world.identity.accounts.revoke_invite(a.id, gone.invite_id)
        await world.identity.accounts.invite(b.id, admin_b.id, "x@globex.example", UserRole.USER)

        pending = await world.identity.accounts.list_invites(a.id)

        assert [i.id for i in pending] == [mine.invite_id]

    async def test_an_invite_link_is_not_valid_in_another_workspace(self, world: World) -> None:
        a, admin_a = await workspace_with_admin(world, "acme", "boss@acme.example")
        b, _ = await workspace_with_admin(world, "globex", "boss@globex.example")
        link = await world.identity.accounts.invite(
            a.id, admin_a.id, "ada@acme.example", UserRole.ADMIN
        )
        forged = f"{b.id}.{token_of(link).split('.', 1)[1]}"
        with pytest.raises(InvalidTokenError):
            await world.identity.accounts.accept(forged, world.password)


class TestTeamChanges:
    async def test_members_are_listed_for_one_workspace_only(self, world: World) -> None:
        a, admin_a = await workspace_with_admin(world, "acme", "boss@acme.example")
        await workspace_with_admin(world, "globex", "boss@globex.example")
        await add_member(world, a, admin_a, "ada@acme.example", UserRole.USER)
        assert [m.email for m in await world.identity.accounts.list_members(a.id)] == [
            "ada@acme.example",
            "boss@acme.example",
        ]

    async def test_a_role_can_be_changed(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        member = await add_member(world, workspace, admin, "ada@acme.example", UserRole.USER)
        updated = await world.identity.accounts.change_member(
            workspace.id, admin.id, member.id, role=UserRole.AGENT
        )
        assert updated.role is UserRole.AGENT

    async def test_an_admin_cannot_change_themselves(self, world: World) -> None:
        workspace, admin = await workspace_with_admin(world)
        with pytest.raises(SelfChangeError):
            await world.identity.accounts.change_member(
                workspace.id, admin.id, admin.id, role=UserRole.USER
            )
        with pytest.raises(SelfChangeError):
            await world.identity.accounts.change_member(
                workspace.id, admin.id, admin.id, status=UserStatus.DISABLED
            )

    async def test_the_last_active_admin_cannot_be_removed_even_by_a_stale_admin_token(
        self, world: World
    ) -> None:
        """An administrator demoted a minute ago still holds a valid access token for a few minutes. Whatever they
        do with it, the workspace must keep one active administrator."""
        workspace, first = await workspace_with_admin(world)
        second = await add_member(world, workspace, first, "two@acme.example", UserRole.ADMIN)
        await world.identity.accounts.change_member(
            workspace.id, second.id, first.id, role=UserRole.USER
        )

        with pytest.raises(LastAdminError):
            await world.identity.accounts.change_member(
                workspace.id, first.id, second.id, status=UserStatus.DISABLED
            )
        with pytest.raises(LastAdminError):
            await world.identity.accounts.change_member(
                workspace.id, first.id, second.id, role=UserRole.USER
            )

    async def test_disabling_a_member_ends_their_sessions_and_pending_links(
        self, world: World
    ) -> None:
        workspace, admin = await workspace_with_admin(world)
        member = await add_member(world, workspace, admin, "ada@acme.example", UserRole.USER)
        signed_in = await world.identity.auth.login(
            "acme", "ada@acme.example", world.password, "198.51.100.1"
        )
        reset = await world.identity.accounts.reset_link(workspace.id, admin.id, member.id)

        await world.identity.accounts.change_member(
            workspace.id, admin.id, member.id, status=UserStatus.DISABLED
        )

        with pytest.raises(InvalidTokenError):
            await world.identity.auth.refresh(signed_in.refresh_token)
        with pytest.raises(InvalidTokenError):
            await world.identity.accounts.accept(token_of(reset), world.password)

    async def test_a_member_of_another_workspace_cannot_be_touched(self, world: World) -> None:
        a, admin_a = await workspace_with_admin(world, "acme", "boss@acme.example")
        b, admin_b = await workspace_with_admin(world, "globex", "boss@globex.example")
        with pytest.raises(EntityNotFoundError):
            await world.identity.accounts.change_member(
                a.id, admin_a.id, admin_b.id, role=UserRole.USER
            )
        with pytest.raises(EntityNotFoundError):
            await world.identity.accounts.reset_link(a.id, admin_a.id, admin_b.id)
        assert (await world.store.user_by_id(b.id, admin_b.id)).role is UserRole.ADMIN  # type: ignore[union-attr]
