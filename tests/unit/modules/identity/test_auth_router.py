"""``POST /v1/auth/token`` (dev token stub) and the app-level wiring around it."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import httpx
import pytest

from ragassist.shared.security.jwt import UserRole, decode_access_token

TOKEN_URL = "/v1/auth/token"


def body(**overrides: object) -> dict[str, object]:
    return {"user_id": str(uuid4()), "tenant_id": str(uuid4()), **overrides}


@pytest.fixture
async def client(api_client_for: Callable[..., httpx.AsyncClient]):  # type: ignore[no-untyped-def]
    async with api_client_for() as c:
        yield c


class TestTokenIssuance:
    async def test_issues_a_bearer_token(self, client: httpx.AsyncClient) -> None:
        response = await client.post(TOKEN_URL, json=body())
        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer" and data["access_token"].count(".") == 2

    async def test_token_carries_exactly_the_requested_identity(
        self, client: httpx.AsyncClient
    ) -> None:
        request = body(role="admin")
        data = (await client.post(TOKEN_URL, json=request)).json()
        principal = decode_access_token(data["access_token"])
        assert str(principal.user_id) == request["user_id"]
        assert str(principal.tenant_id) == request["tenant_id"]
        assert principal.role is UserRole.ADMIN

    async def test_response_echoes_the_identity(self, client: httpx.AsyncClient) -> None:
        request = body(role="agent")
        data = (await client.post(TOKEN_URL, json=request)).json()
        assert (data["user_id"], data["tenant_id"], data["role"]) == (
            request["user_id"],
            request["tenant_id"],
            "agent",
        )

    async def test_role_defaults_to_the_least_privileged(self, client: httpx.AsyncClient) -> None:
        data = (await client.post(TOKEN_URL, json=body())).json()
        assert data["role"] == "user"
        assert decode_access_token(data["access_token"]).role is UserRole.USER

    @pytest.mark.parametrize("role", [r.value for r in UserRole])
    async def test_every_declared_role_can_be_issued(
        self, client: httpx.AsyncClient, role: str
    ) -> None:
        data = (await client.post(TOKEN_URL, json=body(role=role))).json()
        assert decode_access_token(data["access_token"]).role.value == role

    async def test_tokens_for_different_tenants_differ(self, client: httpx.AsyncClient) -> None:
        a = (await client.post(TOKEN_URL, json=body())).json()["access_token"]
        b = (await client.post(TOKEN_URL, json=body())).json()["access_token"]
        assert a != b


class TestValidation:
    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"user_id": str(uuid4())},
            {"tenant_id": str(uuid4())},
            {"user_id": "not-a-uuid", "tenant_id": str(uuid4())},
            {"user_id": str(uuid4()), "tenant_id": "tenant-1"},
            {"user_id": str(uuid4()), "tenant_id": str(uuid4()), "role": "superuser"},
            {"user_id": str(uuid4()), "tenant_id": str(uuid4()), "role": "ADMIN"},
            {"user_id": None, "tenant_id": None},
        ],
    )
    async def test_malformed_requests_get_422(
        self, client: httpx.AsyncClient, payload: dict
    ) -> None:
        assert (await client.post(TOKEN_URL, json=payload)).status_code == 422

    async def test_non_json_body_is_rejected(self, client: httpx.AsyncClient) -> None:
        assert (
            await client.post(TOKEN_URL, content=b"user=1", headers={"Content-Type": "text/plain"})
        ).status_code == 422

    async def test_get_is_not_allowed(self, client: httpx.AsyncClient) -> None:
        assert (await client.get(TOKEN_URL)).status_code == 405


class TestEnvironmentGating:
    @pytest.mark.parametrize("env", ["staging", "production"])
    async def test_token_minting_is_not_available_outside_dev_and_test(
        self, api_client_for: Callable[..., httpx.AsyncClient], env: str
    ) -> None:
        async with api_client_for(APP_ENV=env) as production_client:
            response = await production_client.post(TOKEN_URL, json=body(role="admin"))
        assert response.status_code in (403, 404)

    @pytest.mark.parametrize("env", ["development", "test"])
    async def test_token_minting_is_available_in_dev_and_test(
        self, api_client_for: Callable[..., httpx.AsyncClient], env: str
    ) -> None:
        async with api_client_for(APP_ENV=env) as dev_client:
            assert (await dev_client.post(TOKEN_URL, json=body())).status_code == 200


class TestApplication:
    async def test_healthz(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/healthz")
        assert response.status_code == 200 and response.json()["status"] == "ok"

    async def test_unknown_routes_are_404(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/v1/nope")).status_code == 404

    async def test_openapi_documents_the_token_route(self, client: httpx.AsyncClient) -> None:
        schema = (await client.get("/openapi.json")).json()
        assert "post" in schema["paths"][TOKEN_URL]

    async def test_cors_preflight_allows_a_configured_origin(
        self, api_client_for: Callable[..., httpx.AsyncClient]
    ) -> None:
        async with api_client_for(CORS_ORIGINS='["https://app.example"]') as c:
            response = await c.options(
                TOKEN_URL,
                headers={"Origin": "https://app.example", "Access-Control-Request-Method": "POST"},
            )
        assert response.headers.get("access-control-allow-origin") == "https://app.example"

    async def test_cors_preflight_rejects_an_unlisted_origin(
        self, api_client_for: Callable[..., httpx.AsyncClient]
    ) -> None:
        async with api_client_for(CORS_ORIGINS='["https://app.example"]') as c:
            response = await c.options(
                TOKEN_URL,
                headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
            )
        assert response.headers.get("access-control-allow-origin") != "https://evil.example"
