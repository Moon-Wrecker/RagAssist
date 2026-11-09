"""FastAPI auth dependencies: bearer parsing, principal extraction, role gating, tenant UoW."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from datetime import timedelta

import httpx
import pytest
from factories import auth_header, forge_token, make_token, new_tenant
from fakes import FakeAsyncSession
from fastapi import Depends, FastAPI

from ragassist.shared.db.session import get_db_session
from ragassist.shared.db.uow import UnitOfWork
from ragassist.shared.security.deps import get_current_principal, get_tenant_uow, require_role
from ragassist.shared.security.jwt import Principal, UserRole


@pytest.fixture
def session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture
def app(session: FakeAsyncSession) -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(principal: Principal = Depends(get_current_principal)) -> dict[str, str]:
        return {
            "user_id": str(principal.user_id),
            "tenant_id": str(principal.tenant_id),
            "role": principal.role.value,
        }

    @app.get("/admin-only")
    async def admin_only(
        principal: Principal = Depends(require_role(UserRole.ADMIN)),
    ) -> dict[str, str]:
        return {"role": principal.role.value}

    @app.get("/staff")
    async def staff(
        principal: Principal = Depends(require_role(UserRole.ADMIN, UserRole.AGENT)),
    ) -> dict[str, str]:
        return {"role": principal.role.value}

    @app.get("/tx")
    async def tx(uow: UnitOfWork = Depends(get_tenant_uow)) -> dict[str, str | None]:
        return {"tenant": str(uow.tenant_id)}

    @app.get("/tx-boom")
    async def tx_boom(uow: UnitOfWork = Depends(get_tenant_uow)) -> None:
        raise RuntimeError("handler exploded")

    async def _fake_session() -> AsyncGenerator[FakeAsyncSession, None]:
        yield session

    app.dependency_overrides[get_db_session] = _fake_session
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


class TestAuthentication:
    async def test_valid_token_yields_the_principal(self, client: httpx.AsyncClient) -> None:
        tenant = new_tenant()
        token = make_token(role=UserRole.AGENT, tenant_id=tenant)
        response = await client.get("/whoami", headers=auth_header(token))
        assert response.status_code == 200
        assert response.json()["tenant_id"] == str(tenant)
        assert response.json()["role"] == "agent"

    async def test_missing_header_is_unauthenticated(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/whoami")
        assert response.status_code == 401

    @pytest.mark.parametrize("header", ["Basic abc", "Token abc", "Bearer", "bearer"])
    async def test_non_bearer_or_empty_credentials(
        self, client: httpx.AsyncClient, header: str
    ) -> None:
        response = await client.get("/whoami", headers={"Authorization": header})
        assert response.status_code in (401, 403)  # FastAPI version dependent; never 200

    async def test_invalid_token_is_401_with_challenge(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/whoami", headers=auth_header("not.a.jwt"))
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.parametrize(
        "token",
        [
            forge_token(key="another-secret-key-that-is-long-enough-1234567890"),
            forge_token(algorithm="none"),
            forge_token(expired=True),
            forge_token(drop=("tenant_id",)),
        ],
        ids=["wrong-key", "alg-none", "expired", "no-tenant"],
    )
    async def test_forged_tokens_are_rejected(self, client: httpx.AsyncClient, token: str) -> None:
        response = await client.get("/whoami", headers=auth_header(token))
        assert response.status_code == 401

    async def test_expired_token(self, client: httpx.AsyncClient) -> None:
        token = make_token(expires_delta=timedelta(seconds=-5))
        assert (await client.get("/whoami", headers=auth_header(token))).status_code == 401


class TestAuthorization:
    @pytest.mark.parametrize(
        ("path", "role", "expected"),
        [
            ("/admin-only", UserRole.ADMIN, 200),
            ("/admin-only", UserRole.USER, 403),
            ("/admin-only", UserRole.AGENT, 403),
            ("/staff", UserRole.ADMIN, 200),
            ("/staff", UserRole.AGENT, 200),
            ("/staff", UserRole.USER, 403),
        ],
    )
    async def test_role_matrix(
        self, client: httpx.AsyncClient, path: str, role: UserRole, expected: int
    ) -> None:
        response = await client.get(path, headers=auth_header(make_token(role=role)))
        assert response.status_code == expected

    async def test_forbidden_message_names_the_role_but_not_the_token(
        self, client: httpx.AsyncClient
    ) -> None:
        token = make_token(role=UserRole.USER)
        response = await client.get("/admin-only", headers=auth_header(token))
        assert "user" in response.json()["detail"]
        assert token not in response.text

    async def test_role_check_runs_after_authentication(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/admin-only")).status_code == 401


class TestTenantUnitOfWork:
    async def test_uow_is_bound_to_the_callers_tenant_and_committed(
        self, client: httpx.AsyncClient, session: FakeAsyncSession
    ) -> None:
        tenant = new_tenant()
        response = await client.get("/tx", headers=auth_header(make_token(tenant_id=tenant)))
        assert response.status_code == 200
        assert session.tenant_setting == str(tenant)
        assert session.committed and not session.rolled_back

    async def test_handler_error_rolls_back(
        self, client: httpx.AsyncClient, session: FakeAsyncSession
    ) -> None:
        with pytest.raises(RuntimeError, match="handler exploded"):
            await client.get("/tx-boom", headers=auth_header(make_token()))
        assert session.rolled_back and not session.committed

    async def test_no_database_work_without_authentication(
        self, client: httpx.AsyncClient, session: FakeAsyncSession
    ) -> None:
        response = await client.get("/tx")
        assert response.status_code == 401
        assert session.events == []
