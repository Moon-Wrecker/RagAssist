"""The identity HTTP surface: sign-in, refresh cookie, sign-out, links and the admin-only team routes."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from support.identity_world import World, add_member, token_of, workspace_with_admin

from ragassist.main import create_app
from ragassist.modules.identity.api.deps import REFRESH_COOKIE
from ragassist.shared.config import settings as settings_module
from ragassist.shared.security.jwt import UserRole

ORIGIN = {"Origin": "http://localhost:5173"}  # one of CORS_ORIGINS in .env.example


@pytest.fixture
async def client(world: World) -> AsyncIterator[httpx.AsyncClient]:
    settings_module._settings = None
    app = create_app()
    app.state.identity = world.identity
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api.test"
    ) as c:
        yield c


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def sign_in(
    client: httpx.AsyncClient, world: World, email: str = "boss@acme.example"
) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        "/v1/auth/login", json={"workspace": "acme", "email": email, "password": world.password}
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestLogin:
    async def test_it_returns_a_token_user_and_workspace_and_sets_the_refresh_cookie(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        await workspace_with_admin(world)
        response = await client.post(
            "/v1/auth/login",
            json={"workspace": "acme", "email": "boss@acme.example", "password": world.password},
        )
        body = response.json()
        assert response.status_code == 200
        assert body["token_type"] == "bearer" and body["user"]["role"] == "admin"
        assert body["workspace"]["slug"] == "acme"
        assert "password" not in str(body).lower().replace("password_", "")

    async def test_the_refresh_token_is_only_ever_in_an_httponly_strict_cookie(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        await workspace_with_admin(world)
        response = await client.post(
            "/v1/auth/login",
            json={"workspace": "acme", "email": "boss@acme.example", "password": world.password},
        )
        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f"{REFRESH_COOKIE}=")
        lowered = cookie.lower()
        assert "httponly" in lowered and "samesite=strict" in lowered and "path=/v1/auth" in lowered
        assert response.cookies[REFRESH_COOKIE] not in response.text, (
            "never in the body, where script could read it"
        )

    async def test_a_bad_login_is_a_generic_401(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        await workspace_with_admin(world)
        wrong_password = await client.post(
            "/v1/auth/login",
            json={"workspace": "acme", "email": "boss@acme.example", "password": "x" * 14},
        )
        unknown_user = await client.post(
            "/v1/auth/login",
            json={"workspace": "acme", "email": "who@acme.example", "password": "x" * 14},
        )
        unknown_workspace = await client.post(
            "/v1/auth/login",
            json={"workspace": "zzz", "email": "boss@acme.example", "password": "x" * 14},
        )
        assert {r.status_code for r in (wrong_password, unknown_user, unknown_workspace)} == {401}
        assert wrong_password.json() == unknown_user.json() == unknown_workspace.json()
        assert "set-cookie" not in wrong_password.headers

    async def test_too_many_failures_answer_429_with_retry_after(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        await workspace_with_admin(world)
        for _ in range(world.settings.AUTH_LOGIN_MAX_FAILURES):
            await client.post(
                "/v1/auth/login",
                json={"workspace": "acme", "email": "boss@acme.example", "password": "x" * 14},
            )
        response = await client.post(
            "/v1/auth/login",
            json={"workspace": "acme", "email": "boss@acme.example", "password": world.password},
        )
        assert response.status_code == 429 and int(response.headers["retry-after"]) > 0

    async def test_oversized_input_is_rejected_before_any_hashing(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        response = await client.post(
            "/v1/auth/login",
            json={"workspace": "acme", "email": "boss@acme.example", "password": "x" * 5000},
        )
        assert response.status_code == 422
        assert world.hasher.verify_calls == 0


class TestRefreshAndLogout:
    async def test_the_cookie_buys_a_new_token_and_rotates(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        await workspace_with_admin(world)
        await sign_in(client, world)
        first_cookie = client.cookies[REFRESH_COOKIE]

        response = await client.post("/v1/auth/refresh", headers=ORIGIN)

        assert response.status_code == 200 and response.json()["access_token"]
        assert client.cookies[REFRESH_COOKIE] != first_cookie

    async def test_a_request_without_a_trusted_origin_is_refused_and_does_not_spend_the_token(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        await workspace_with_admin(world)
        await sign_in(client, world)
        for headers in ({}, {"Origin": "https://evil.example"}):
            assert (await client.post("/v1/auth/refresh", headers=headers)).status_code == 403
            assert (await client.post("/v1/auth/logout", headers=headers)).status_code == 403
        assert (
            await client.post("/v1/auth/refresh", headers=ORIGIN)
        ).status_code == 200  # still valid

    async def test_no_cookie_is_a_401(self, client: httpx.AsyncClient) -> None:
        assert (await client.post("/v1/auth/refresh", headers=ORIGIN)).status_code == 401

    async def test_a_replayed_cookie_is_a_401_that_clears_the_cookie(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        await workspace_with_admin(world)
        await sign_in(client, world)
        stolen = client.cookies[REFRESH_COOKIE]
        assert (await client.post("/v1/auth/refresh", headers=ORIGIN)).status_code == 200

        client.cookies.set(REFRESH_COOKIE, stolen, path="/v1/auth")
        replay = await client.post("/v1/auth/refresh", headers=ORIGIN)

        assert replay.status_code == 401
        assert "max-age=0" in replay.headers["set-cookie"].lower()

    async def test_logout_clears_the_cookie_and_the_session_is_dead(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        await workspace_with_admin(world)
        await sign_in(client, world)
        cookie = client.cookies[REFRESH_COOKIE]

        out = await client.post("/v1/auth/logout", headers=ORIGIN)
        assert out.status_code == 204 and "max-age=0" in out.headers["set-cookie"].lower()

        client.cookies.set(REFRESH_COOKIE, cookie, path="/v1/auth")
        assert (await client.post("/v1/auth/refresh", headers=ORIGIN)).status_code == 401


class TestMe:
    async def test_me_needs_a_token(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/v1/auth/me")).status_code in (401, 403)

    async def test_me_returns_the_caller(self, client: httpx.AsyncClient, world: World) -> None:
        await workspace_with_admin(world)
        token = (await sign_in(client, world))["access_token"]
        body = (await client.get("/v1/auth/me", headers=bearer(token))).json()
        assert body["user"]["email"] == "boss@acme.example" and body["workspace"]["name"] == "Acme"


class TestAcceptingLinksOverHttp:
    async def test_a_new_admin_sets_a_password_and_lands_signed_in(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        _, link = await world.identity.accounts.create_workspace(
            "Acme", "acme", "boss@acme.example"
        )
        response = await client.post(
            "/v1/auth/invites/accept", json={"token": token_of(link), "password": world.password}
        )
        assert response.status_code == 200 and REFRESH_COOKIE in response.cookies
        assert response.json()["user"]["role"] == "admin"

    async def test_a_used_link_is_a_401_and_a_weak_password_a_422(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        _, link = await world.identity.accounts.create_workspace(
            "Acme", "acme", "boss@acme.example"
        )
        weak = await client.post(
            "/v1/auth/invites/accept", json={"token": token_of(link), "password": "short"}
        )
        assert weak.status_code == 422 and "at least" in weak.json()["detail"]
        ok = await client.post(
            "/v1/auth/invites/accept", json={"token": token_of(link), "password": world.password}
        )
        again = await client.post(
            "/v1/auth/invites/accept", json={"token": token_of(link), "password": world.password}
        )
        assert ok.status_code == 200 and again.status_code == 401


class TestTeamRoutes:
    async def _tokens(self, client: httpx.AsyncClient, world: World):  # type: ignore[no-untyped-def]
        workspace, admin = await workspace_with_admin(world)
        await add_member(world, workspace, admin, "ada@acme.example", UserRole.USER)
        await add_member(world, workspace, admin, "ray@acme.example", UserRole.AGENT)
        return (
            workspace,
            (await sign_in(client, world))["access_token"],
            (await sign_in(client, world, "ada@acme.example"))["access_token"],
            (await sign_in(client, world, "ray@acme.example"))["access_token"],
        )

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/v1/team/members"),
            ("GET", "/v1/team/invites"),
            ("POST", "/v1/team/invites"),
        ],
    )
    async def test_only_administrators_get_in(
        self, client: httpx.AsyncClient, world: World, method: str, path: str
    ) -> None:
        _, _, user_token, agent_token = await self._tokens(client, world)
        for token in (user_token, agent_token):
            response = await client.request(
                method,
                path,
                headers=bearer(token),
                json={"email": "x@acme.example", "role": "user"},
            )
            assert response.status_code == 403

    async def test_an_admin_invites_and_the_person_joins(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        _, admin_token, *_ = await self._tokens(client, world)
        created = await client.post(
            "/v1/team/invites",
            headers=bearer(admin_token),
            json={"email": "new@acme.example", "role": "agent"},
        )
        assert created.status_code == 201
        link = created.json()["url"]
        assert link.startswith(world.settings.WEB_BASE_URL) and "#token=" in link

        joined = await client.post(
            "/v1/auth/invites/accept",
            json={"token": link.split("#token=", 1)[1], "password": world.password},
        )
        assert joined.status_code == 200 and joined.json()["user"]["role"] == "agent"

        pending = await client.get("/v1/team/invites", headers=bearer(admin_token))
        assert pending.json() == []

    async def test_the_member_list_never_exposes_a_hash_or_a_token(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        _, admin_token, *_ = await self._tokens(client, world)
        response = await client.get("/v1/team/members", headers=bearer(admin_token))
        members = response.json()
        assert [m["email"] for m in members] == [
            "ada@acme.example",
            "boss@acme.example",
            "ray@acme.example",
        ]
        assert all(set(m) == {"id", "email", "role", "status", "has_password"} for m in members)
        assert "fake$" not in response.text

    async def test_change_role_disable_and_the_guards(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        workspace, admin_token, *_ = await self._tokens(client, world)
        ada = await world.store.user_by_email(workspace.id, "ada@acme.example")
        boss = await world.store.user_by_email(workspace.id, "boss@acme.example")
        assert ada and boss
        headers = bearer(admin_token)

        promoted = await client.patch(
            f"/v1/team/members/{ada.id}", headers=headers, json={"role": "agent"}
        )
        assert promoted.status_code == 200 and promoted.json()["role"] == "agent"

        self_change = await client.patch(
            f"/v1/team/members/{boss.id}", headers=headers, json={"status": "disabled"}
        )
        assert self_change.status_code == 409

        bad_status = await client.patch(
            f"/v1/team/members/{ada.id}", headers=headers, json={"status": "banned"}
        )
        assert bad_status.status_code == 422

        disabled = await client.patch(
            f"/v1/team/members/{ada.id}", headers=headers, json={"status": "disabled"}
        )
        assert disabled.status_code == 200
        blocked = await client.post(
            "/v1/auth/login",
            json={"workspace": "acme", "email": "ada@acme.example", "password": world.password},
        )
        assert blocked.status_code == 401

    async def test_a_reset_link_is_issued_once_and_unknown_members_are_404(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        workspace, admin_token, *_ = await self._tokens(client, world)
        ada = await world.store.user_by_email(workspace.id, "ada@acme.example")
        assert ada
        ok = await client.post(f"/v1/team/members/{ada.id}/reset-link", headers=bearer(admin_token))
        assert ok.status_code == 201 and ok.json()["kind"] == "reset"
        missing = await client.post(
            "/v1/team/members/00000000-0000-0000-0000-000000000009/reset-link",
            headers=bearer(admin_token),
        )
        assert missing.status_code == 404

    async def test_an_admin_of_another_workspace_cannot_reach_these_members(
        self, client: httpx.AsyncClient, world: World
    ) -> None:
        workspace, *_ = await self._tokens(client, world)
        other, _ = await workspace_with_admin(world, "globex", "boss@globex.example")
        other_login = await client.post(
            "/v1/auth/login",
            json={
                "workspace": "globex",
                "email": "boss@globex.example",
                "password": world.password,
            },
        )
        token = other_login.json()["access_token"]
        ada = await world.store.user_by_email(workspace.id, "ada@acme.example")
        assert ada and other.id != workspace.id

        listing = await client.get("/v1/team/members", headers=bearer(token))
        assert [m["email"] for m in listing.json()] == ["boss@globex.example"]
        patched = await client.patch(
            f"/v1/team/members/{ada.id}", headers=bearer(token), json={"role": "admin"}
        )
        assert patched.status_code == 404
