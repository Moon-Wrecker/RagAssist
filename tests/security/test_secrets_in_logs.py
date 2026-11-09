"""Secrets never reach logs, error bodies or serialised settings (plan section 5.9 "Secrets").

Runs live: it uses the mock SaaS, the real token code and the real provider adapter, capturing stdout,
stderr and log records. Tests that expose a real gap carry their DEFECT id.
"""

from __future__ import annotations

import logging

import httpx
import pytest
from factories.principals import auth_header, forge_token, make_token
from support.fake_openai_server import FakeOpenAIServer
from support.settings import make_settings
from support.spec import TEST_SECRET_KEY

from services.mock_saas.main import app as mock_saas_app

pytestmark = pytest.mark.security

OPENAI_MARKER = "sk-marker-" + "x" * 24


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_saas_app), base_url="http://mocksaas.test"
    )


class TestTokensNeverLeak:
    async def test_a_tampered_token_is_refused_and_not_echoed(self) -> None:
        token = make_token() + "marker-token-body-do-not-echo"
        async with client() as http:
            response = await http.get("/accounts/overview", headers=auth_header(token))
        assert response.status_code == 401
        assert "marker-token-body" not in response.text and token not in response.text

    async def test_issuing_a_token_writes_no_secret_to_the_logs(
        self, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            token = make_token()
        captured = capsys.readouterr()
        everything = captured.out + captured.err + caplog.text
        assert token not in everything
        assert TEST_SECRET_KEY not in everything

    async def test_a_forged_signature_is_refused_without_logging_the_token(
        self, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        forged = forge_token(key="attacker-key-0123456789abcdefghijklmnopqrstuvwxyz-ABCDEFGH")
        async with client() as http:
            await http.get("/accounts/overview", headers=auth_header(forged))
        captured = capsys.readouterr()
        assert forged not in captured.out + captured.err + caplog.text


class TestProviderKeysNeverLeak:
    async def test_a_provider_auth_failure_does_not_expose_the_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from ragassist.platform.embeddings.adapters.openai_adapter import OpenAIEmbeddingAdapter

        server = FakeOpenAIServer(default_dimension=8).start()
        try:
            server.fail_next(401, "invalid api key")
            monkeypatch.setenv(
                "OPENAI_API_BASE", server.base_url
            )  # legacy name, honoured by older SDKs
            monkeypatch.setenv(
                "OPENAI_BASE_URL", server.base_url
            )  # current name, the only one newer SDKs read
            adapter = OpenAIEmbeddingAdapter(
                settings=make_settings(OPENAI_API_KEY=OPENAI_MARKER, EMBEDDING_DIMENSION=8)
            )
            with pytest.raises(Exception) as info:  # noqa: B017 - the provider error type belongs to the SDK
                await adapter.embed_query("hello")
            message = str(info.value)
        finally:
            server.stop()
        captured = capsys.readouterr()
        assert OPENAI_MARKER not in message
        assert OPENAI_MARKER not in captured.out + captured.err + caplog.text

    def test_settings_repr_and_json_hide_secret_values(self) -> None:
        settings = make_settings(OPENAI_API_KEY=OPENAI_MARKER)
        assert OPENAI_MARKER not in repr(settings)
        assert OPENAI_MARKER not in settings.model_dump_json()
