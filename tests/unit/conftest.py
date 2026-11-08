"""Unit-tier fixtures for HTTP-level components that run in-process (ASGI, no sockets)."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable

import httpx
import pytest

from ragassist.shared.config import settings as settings_module
from services.mock_saas.main import app as mock_saas_app


@pytest.fixture
async def mock_saas_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Mock SaaS service (state is restored per test by the root conftest)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_saas_app), base_url="http://mocksaas.test"
    ) as client:
        yield client


@pytest.fixture
def api_client_for(monkeypatch: pytest.MonkeyPatch) -> Callable[..., httpx.AsyncClient]:
    """Build a RagAssist API client for a given environment: ``api_client_for(APP_ENV="production")``.

    The app is created *after* the environment is applied, so settings-dependent wiring is real.
    """

    def build(**env: str) -> httpx.AsyncClient:
        from ragassist.main import (
            create_app,  # imported here so a broken app never breaks unrelated tests
        )

        for key, value in env.items():
            monkeypatch.setenv(key, value)
        settings_module._settings = None  # drop the cached Settings so the env above is read
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://api.test"
        )

    return build
