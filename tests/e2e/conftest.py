"""Fixtures for the e2e tier (HTTP level). Thin: data builders, fakes and the hermetic environment
come from ``tests/factories``, ``tests/fakes`` and ``tests/conftest.py``."""

from collections.abc import AsyncGenerator, Callable
from uuid import UUID, uuid4

import httpx
import pytest
from fakes.session import FakeAsyncSession  # noqa: F401  (re-exported for existing e2e tests)
from fakes.vector_store import InMemoryVectorStore
from support.spec import DEMO_TENANT_A_ID, DEMO_TENANT_B_ID

from ragassist.main import create_app
from ragassist.shared.domain import TenantId, UserId
from ragassist.shared.security.jwt import UserRole, create_access_token
from services.mock_saas.main import app as mock_saas_app


@pytest.fixture
def tenant_a() -> TenantId:
    return TenantId(UUID(DEMO_TENANT_A_ID))  # Acme Corp


@pytest.fixture
def tenant_b() -> TenantId:
    return TenantId(UUID(DEMO_TENANT_B_ID))  # Globex Corp


@pytest.fixture
def random_tenant() -> TenantId:
    return TenantId(uuid4())


@pytest.fixture
def user_a() -> UserId:
    return UserId(uuid4())


@pytest.fixture
def user_b() -> UserId:
    return UserId(uuid4())


@pytest.fixture
def token_factory() -> Callable[[UserId, TenantId, UserRole], str]:
    def _make(user_id: UserId, tenant_id: TenantId, role: UserRole = UserRole.USER) -> str:
        return create_access_token(user_id=user_id, tenant_id=tenant_id, role=role)

    return _make


@pytest.fixture
def user_token_a(token_factory: Callable[..., str], user_a: UserId, tenant_a: TenantId) -> str:
    return token_factory(user_a, tenant_a, UserRole.USER)


@pytest.fixture
def admin_token_a(token_factory: Callable[..., str], user_a: UserId, tenant_a: TenantId) -> str:
    return token_factory(user_a, tenant_a, UserRole.ADMIN)


@pytest.fixture
def user_token_b(token_factory: Callable[..., str], user_b: UserId, tenant_b: TenantId) -> str:
    return token_factory(user_b, tenant_b, UserRole.USER)


@pytest.fixture
def admin_token_b(token_factory: Callable[..., str], user_b: UserId, tenant_b: TenantId) -> str:
    return token_factory(user_b, tenant_b, UserRole.ADMIN)


@pytest.fixture
def auth_headers_a(user_token_a: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_token_a}"}


@pytest.fixture
def admin_headers_a(admin_token_a: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token_a}"}


@pytest.fixture
def auth_headers_b(user_token_b: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_token_b}"}


@pytest.fixture
def admin_headers_b(admin_token_b: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token_b}"}


@pytest.fixture
async def mock_saas_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """In-memory client for the standalone Mock SaaS service (state reset by the root conftest)."""
    transport = httpx.ASGITransport(app=mock_saas_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://mocksaas.test") as client:
        yield client


@pytest.fixture
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """In-memory client for the RagAssist FastAPI application."""
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def fake_vector_store() -> InMemoryVectorStore:
    return InMemoryVectorStore()
