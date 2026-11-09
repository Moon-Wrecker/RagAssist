"""Live tier: real model calls. Off by default; never part of CI's quick loop.

Enable:   pytest tests/live --run-live         (or  RAGASSIST_LIVE=1)
Configure (all optional):
    RAGASSIST_LIVE_BASE_URL   default http://localhost:11434/v1   (an OpenAI-compatible server)
    RAGASSIST_LIVE_MODEL      default gemma4:31b-cloud            (an Ollama cloud model)
    RAGASSIST_LIVE_API_KEY    default empty   (pass real keys via the environment only; never commit)

Examples:
    RAGASSIST_LIVE_MODEL=qwen3.5:2b pytest tests/live --run-live
    RAGASSIST_LIVE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai \
    RAGASSIST_LIVE_MODEL=gemini-flash-latest RAGASSIST_LIVE_API_KEY=... pytest tests/live --run-live

The endpoint is probed once per session; if it is unreachable or the model is missing, the whole
tier skips with a reason instead of failing. Tests assert behaviour that any competent model shows
on unambiguous inputs, and are tolerant of wording.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest
from support.settings import make_settings

from ragassist.platform.llm.adapters.openrouter_adapter import OpenAICompatibleAdapter

BASE_URL = os.environ.get("RAGASSIST_LIVE_BASE_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("RAGASSIST_LIVE_MODEL", "gemma4:31b-cloud")
API_KEY = os.environ.get("RAGASSIST_LIVE_API_KEY", "")


def _enabled(config: pytest.Config) -> bool:
    return bool(config.getoption("--run-live")) or os.environ.get("RAGASSIST_LIVE") == "1"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _enabled(config):
        return
    skip = pytest.mark.skip(reason="live tier is opt-in: pass --run-live or set RAGASSIST_LIVE=1")
    for item in items:
        if "tests/live" in item.nodeid.replace("\\", "/"):
            # Real endpoints (Gemini, OpenRouter, ...) are not loopback: let them past the guard.
            item.add_marker(pytest.mark.network)
            if not _enabled(config):
                item.add_marker(skip)


def _probe() -> str | None:
    """Return a skip reason, or None when the endpoint is usable.

    Ollama (native ``/api/tags``): the model must be present. Any other OpenAI-compatible server
    (Gemini, OpenRouter, vLLM): the authenticated model list must be reachable; the model itself is
    not required to be listed because providers expose aliases such as ``gemini-flash-latest``.
    """
    parts = urlsplit(BASE_URL)
    root = f"{parts.scheme}://{parts.netloc}"
    try:
        with urllib.request.urlopen(f"{root}/api/tags", timeout=5) as response:  # noqa: S310
            names = {m.get("name") for m in json.load(response).get("models", [])}
        if MODEL not in names:
            return f"model {MODEL!r} is not pulled at {root} (found: {sorted(n for n in names if n)[:5]})"
        return None
    except (urllib.error.URLError, OSError, ValueError):
        pass  # not Ollama's native API
    request = urllib.request.Request(  # noqa: S310
        f"{BASE_URL.rstrip('/')}/models", headers={"Authorization": f"Bearer {API_KEY}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10):  # noqa: S310
            return None
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return f"live endpoint {BASE_URL} rejected the API key (HTTP {exc.code})"
        return None  # some servers do not implement /models; let the tests decide
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"live endpoint {BASE_URL} is unreachable ({exc})"


@pytest.fixture(scope="session")
def live_endpoint(request: pytest.FixtureRequest) -> dict[str, str]:
    if not _enabled(request.config):
        pytest.skip("live tier is opt-in")
    reason = _probe()
    if reason:
        pytest.skip(reason)
    return {"base_url": BASE_URL, "model": MODEL, "api_key": API_KEY}


@pytest.fixture
def live_model_factory(live_endpoint: dict[str, str]):  # type: ignore[no-untyped-def]
    """Build real chat models through the production adapter (not a hand-made client)."""
    adapter = OpenAICompatibleAdapter(make_settings())

    def build(*, streaming: bool = False, max_tokens: int = 1500):  # type: ignore[no-untyped-def]
        return adapter.build_chat_model(
            live_endpoint["model"],
            temperature=0.0,
            # The model "thinks" first; leave headroom or the visible answer can be empty.
            max_tokens=max_tokens,
            streaming=streaming,
            base_url=live_endpoint["base_url"],
            api_key=live_endpoint["api_key"],
            timeout=120,
        )

    return build


@pytest.fixture
def live_chat_model(live_model_factory):  # type: ignore[no-untyped-def]
    return live_model_factory()


@pytest.fixture(autouse=True)
def _generous_timeout(request: pytest.FixtureRequest) -> Iterator[None]:
    if not request.node.get_closest_marker("timeout"):
        request.node.add_marker(pytest.mark.timeout(180))
    yield
