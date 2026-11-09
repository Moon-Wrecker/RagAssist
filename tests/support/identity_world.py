"""A ready-made identity world for tests: services on the in-memory store, instant hasher, controllable clock."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fakes.identity import FakeHasher, MutableClock, make_identity

from ragassist.modules.identity.adapters.memory import InMemoryIdentityStore
from ragassist.modules.identity.application import IssuedLink
from ragassist.modules.identity.domain import UserRecord, Workspace
from ragassist.modules.identity.wiring import IdentityServices
from ragassist.shared.config.settings import Settings
from ragassist.shared.security.jwt import UserRole
from support.settings import make_settings


@dataclass
class World:
    identity: IdentityServices
    hasher: FakeHasher
    clock: MutableClock
    store: InMemoryIdentityStore
    settings: Settings
    password: str


def new_world(**settings_overrides: object) -> World:
    settings = make_settings(**settings_overrides)
    identity, hasher, clock, store = make_identity(settings)
    return World(identity, hasher, clock, store, settings, password=secrets.token_urlsafe(18))


def token_of(link: IssuedLink) -> str:
    """The raw token inside a link (the part after ``#token=``)."""
    return link.url.split("#token=", 1)[1]


async def workspace_with_admin(
    world: World, slug: str = "acme", email: str = "boss@acme.example"
) -> tuple[Workspace, UserRecord]:
    """A workspace whose administrator has already set a password."""
    workspace, link = await world.identity.accounts.create_workspace("Acme", slug, email)
    signed_in = await world.identity.accounts.accept(token_of(link), world.password)
    return workspace, signed_in.user


async def add_member(
    world: World, workspace: Workspace, admin: UserRecord, email: str, role: UserRole
) -> UserRecord:
    """Invite ``email`` and have them accept."""
    link = await world.identity.accounts.invite(workspace.id, admin.id, email, role)
    return (await world.identity.accounts.accept(token_of(link), world.password)).user
