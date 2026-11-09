"""Authentication sweep over every route the application serves (plan section 5.9, "Auth").

The sweep discovers routes from the app itself, so a route added later is covered without editing this
file: every route outside the public allowlist must refuse every kind of bad credential with 401 or
403. A route that answers 2xx or 5xx to a bad token fails the build.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from factories.principals import auth_header, forge_token
from support.specs.routes import concrete, mounted_routes

from ragassist.main import create_app

pytestmark = pytest.mark.security

PUBLIC_EXACT = {
    ("GET", "/healthz"),
    (
        "POST",
        "/v1/auth/token",
    ),  # dev token stub: gated per environment (see identity tests, DEFECT-08)
    ("GET", "/openapi.json"),
    # Sign-in and spending an invite link are how a credential is obtained, so they cannot require one.
    ("POST", "/v1/auth/login"),
    ("POST", "/v1/auth/invites/accept"),
}
PUBLIC_PREFIXES = ("/docs", "/redoc")  # FastAPI's interactive documentation pages


def is_public(route: tuple[str, str]) -> bool:
    method, path = route
    return route in PUBLIC_EXACT or any(
        path in (p, p) or path.startswith(p + "/") for p in PUBLIC_PREFIXES
    )


BAD_CREDENTIALS: dict[str, Callable[[], dict[str, str]]] = {
    "no_token": lambda: {},
    "malformed_token": lambda: {"Authorization": "Bearer not-a-jwt"},
    "wrong_signing_key": lambda: auth_header(
        forge_token(key="attacker-controlled-key-0123456789abcdefghijklmnopqrstuvwxyz-ABCDEFGH")
    ),
    "expired": lambda: auth_header(forge_token(expired=True)),
    "alg_none": lambda: auth_header(forge_token(algorithm="none")),
    "missing_tenant_claim": lambda: auth_header(forge_token(drop=("tenant_id",))),
    "basic_scheme": lambda: {"Authorization": "Basic dXNlcjpwYXNz"},
}


def protected_routes() -> list[tuple[str, str]]:
    return sorted(route for route in mounted_routes(create_app()) if not is_public(route))


def _params(marked: bool) -> list[Any]:
    return [
        pytest.param(
            route,
            id=f"{route[0]} {route[1]}",
        )
        for route in protected_routes()
    ] or [
        pytest.param(
            None,
            marks=pytest.mark.skip(reason="PENDING: no protected routes are mounted yet"),
            id="none-yet",
        )
    ]


ROUTE_PARAMS: list[Any] = _params(
    marked=False
)  # refusal does not echo the credential: holds for every route
CREDENTIAL_ROUTE_PARAMS: list[Any] = _params(
    marked=True
)  # /metrics answers without credentials: DEFECT-38


@pytest.fixture
def app():  # type: ignore[no-untyped-def]
    return create_app()


@pytest.fixture
async def client(app):  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api.test"
    ) as c:
        yield c


class TestRouteInventory:
    def test_the_public_routes_are_mounted(self, app) -> None:  # type: ignore[no-untyped-def]
        mounted = mounted_routes(app)
        assert ("GET", "/healthz") in mounted
        assert ("POST", "/v1/auth/token") in mounted

    def test_every_non_public_route_is_known_to_the_sweep(self) -> None:
        assert set(protected_routes()) <= set(mounted_routes(create_app()))
        assert not any(
            is_public(r) and r in protected_routes() for r in mounted_routes(create_app())
        )


class TestBadCredentialsAreRefused:
    @pytest.mark.parametrize("route", CREDENTIAL_ROUTE_PARAMS)
    @pytest.mark.parametrize("credential", sorted(BAD_CREDENTIALS))
    async def test_a_protected_route_refuses_the_credential(
        self, client, route, credential: str
    ) -> None:  # type: ignore[no-untyped-def]
        method, path = route
        response = await client.request(
            method, concrete(path), json={}, headers=BAD_CREDENTIALS[credential]()
        )
        assert response.status_code in (401, 403), (
            f"{method} {path} answered {response.status_code} to {credential}"
        )

    @pytest.mark.parametrize("route", ROUTE_PARAMS)
    async def test_refusals_do_not_echo_the_credential(self, client, route) -> None:  # type: ignore[no-untyped-def]
        method, path = route
        marker = "marker-token-must-not-be-echoed"
        response = await client.request(
            method, concrete(path), json={}, headers={"Authorization": f"Bearer {marker}"}
        )
        assert marker not in response.text
