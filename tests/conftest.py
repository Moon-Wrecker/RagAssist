"""Root conftest: hermetic environment, global-state resets, automatic markers.

Deliberately contains NO business fixtures. Builders live in ``tests/factories``, fakes in
``tests/fakes``, shared helpers in ``tests/support``; each tier adds only what it needs in its own
``conftest.py``.

Why this exists (found while surveying the repo):

* ``get_settings()`` is a process-wide singleton and ``Settings`` reads the developer's real
  ``.env`` -> tests silently used real values and ignored ``monkeypatch.setenv``.
* The DB engine / session factory are module-level singletons.
* The mock SaaS service keeps its data in module-level dicts, so tests leaked state into each other
  (and ``pytest-randomly`` order shuffling exposed it).
"""

from __future__ import annotations

import copy
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# Windows sandbox patch for asyncio event loop self-pipe (test runners only)
if sys.platform == "win32":
    try:
        import _overlapped
        import asyncio.proactor_events
        import asyncio.windows_events
        import socket

        def _mock_make_self_pipe(self: Any) -> None:
            self._ssock = socket.socket()
            self._csock = socket.socket()
            self._internal_fds += 1

        def _mock_write_to_self(self: Any) -> None:
            try:
                _overlapped.PostQueuedCompletionStatus(self._proactor._iocp, 0, 0, 0)
            except Exception:
                pass

        orig_poll = asyncio.windows_events.IocpProactor._poll

        def _safe_poll(self: Any, timeout: Any = None) -> Any:
            try:
                return orig_poll(self, timeout)
            except OSError:
                return None

        asyncio.proactor_events.BaseProactorEventLoop._make_self_pipe = _mock_make_self_pipe  # type: ignore[method-assign]
        asyncio.proactor_events.BaseProactorEventLoop._loop_self_reading = lambda self, f=None: None  # type: ignore[method-assign]
        asyncio.proactor_events.BaseProactorEventLoop._write_to_self = _mock_write_to_self  # type: ignore[method-assign]
        asyncio.windows_events.IocpProactor._poll = _safe_poll  # type: ignore[method-assign]
    except Exception:
        pass

# Shim for python-multipart in offline test environment
try:
    import python_multipart  # type: ignore  # noqa: F401 - availability probe
except ImportError:
    import types

    _pm = types.ModuleType("python_multipart")
    _pm.__version__ = "0.0.20"
    sys.modules["python_multipart"] = _pm
    _mp = types.ModuleType("multipart")
    _mp_sub = types.ModuleType("multipart.multipart")
    _mp_sub.parse_options_header = lambda *a, **k: (None, {})  # type: ignore
    sys.modules["multipart"] = _mp
    sys.modules["multipart.multipart"] = _mp_sub

import pytest
from dotenv import dotenv_values
from hypothesis import HealthCheck
from hypothesis import settings as hypothesis_settings
from support.repo import REPO_ROOT
from support.spec import TEST_SECRET_KEY

from ragassist.shared.config import settings as settings_module
from ragassist.shared.config.envfile import blank_required_fields, generate_value
from ragassist.shared.config.settings import Settings

# Never read the developer's real .env during the test session. Individual tests that need a
# file pass ``Settings(_env_file=path)`` explicitly.
Settings.model_config["env_file"] = None


def _baseline_env() -> dict[str, str]:
    """The test environment: ``.env.example`` for every non-secret value, random values for the blank secrets.

    ``Settings`` has no defaults and no credential is committed, so each test run builds its own secrets.
    """
    example = REPO_ROOT / ".env.example"
    values = {name: (value or "") for name, value in dotenv_values(example).items()}
    for name in blank_required_fields(example):
        values[name] = generate_value(name)
    values["SECRET_KEY"] = TEST_SECRET_KEY
    # The automated tests run on the in-process stores, whatever the shell exports.
    values["PERSISTENCE_BACKEND"] = "memory"
    return {name: value for name, value in values.items() if name in Settings.model_fields}


BASELINE_ENV = _baseline_env()
for _name, _value in BASELINE_ENV.items():
    os.environ.setdefault(_name, _value)
os.environ["PERSISTENCE_BACKEND"] = "memory"

hypothesis_settings.register_profile(
    "default",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
hypothesis_settings.load_profile("default")

_TIER_MARKERS = {
    "unit",
    "integration",
    "graph",
    "security",
    "e2e",
    "hygiene",
    "eval",
    "live",
    "selfcheck",
}

# Registers the PENDING/DRIFT and defect report hooks (reports/ is written at the end of a run).
from support.pending_report import (  # noqa: E402,F401  (pytest finds hooks by their real names)
    pytest_collection_finish,
    pytest_collectreport,
    pytest_runtest_logreport,
    pytest_terminal_summary,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run the opt-in `live` tier against a real model endpoint (see tests/live/conftest.py).",
    )


#: Environment applied to every test (after real values for known Settings fields are removed).
TEST_ENV = {
    "APP_ENV": "test",
    "SECRET_KEY": TEST_SECRET_KEY,
    "MOCK_SAAS_BASE_URL": "http://mocksaas.test",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply the tier marker from the directory name (tests/unit/... -> ``unit``)."""
    for item in items:
        for part in Path(str(item.fspath)).parts:
            if part in _TIER_MARKERS:
                item.add_marker(getattr(pytest.mark, part))
                break


def _reset_db_singletons() -> None:
    try:
        from ragassist.shared.db import session
    except ImportError:  # pragma: no cover - module removed/renamed by the implementation team
        return
    for name in ("_engine", "_session_factory"):
        if hasattr(session, name):
            setattr(session, name, None)


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Known env, empty settings cache, no DB singletons, for every test."""
    for field in Settings.model_fields:
        monkeypatch.delenv(field, raising=False)
    for key, value in {**BASELINE_ENV, **TEST_ENV}.items():
        monkeypatch.setenv(key, value)
    settings_module._settings = None
    _reset_db_singletons()
    yield
    settings_module._settings = None
    _reset_db_singletons()


_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", "::"}  # noqa: S104 - comparison only


@pytest.fixture(autouse=True)
def _block_external_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail any test that tries to leave the machine. Loopback (fake servers, testcontainers
    mapped ports) and unix sockets stay allowed. Opt out with ``@pytest.mark.network``.

    Found necessary: the OpenAI SDK runs on httpx2, which respx cannot intercept, so a mocked
    test could silently call the real API with a fake key.
    """
    if request.node.get_closest_marker("network"):
        return
    import socket

    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def _check(address: object) -> None:
        if isinstance(address, tuple) and address and str(address[0]) not in _LOOPBACK:
            raise RuntimeError(
                f"External network access is blocked in tests (tried {address[0]}). "
                "Use a fake/loopback server or mark the test with @pytest.mark.network."
            )

    def guarded_connect(self: socket.socket, address: object) -> None:
        _check(address)
        return real_connect(self, address)  # type: ignore[arg-type]

    def guarded_connect_ex(self: socket.socket, address: object) -> int:
        _check(address)
        return real_connect_ex(self, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)


@pytest.fixture(autouse=True)
def _reset_mock_saas() -> Iterator[None]:
    """Restore the mock SaaS in-memory data after each test (it is module-level state)."""
    try:
        from services.mock_saas import main as saas
    except ImportError:  # pragma: no cover
        yield
        return
    accounts = copy.deepcopy(getattr(saas, "_ACCOUNTS", None))
    tickets = copy.deepcopy(getattr(saas, "_TICKETS", None))
    yield
    if accounts is not None:
        saas._ACCOUNTS.clear()
        saas._ACCOUNTS.update(accounts)
    if tickets is not None:
        saas._TICKETS[:] = tickets


@pytest.fixture(autouse=True)
def _reset_account_agent_pending_calls() -> Iterator[None]:
    """Empty the account agent's module-level pending-call cache around every test.

    The node keeps an unanswered write approval in a process-wide dict keyed by thread (DEFECT-41), so a test
    that ends at the approval step would otherwise replay its write into a later test that shares the thread.
    """
    try:
        from ragassist.modules.assistant.graph.nodes import account_agent_node as node
    except ImportError:  # pragma: no cover - the module is not importable in this environment
        yield
        return
    cache = getattr(node, "_PENDING_TOOL_CALLS", None)
    if isinstance(cache, dict):
        cache.clear()
    yield
    if isinstance(cache, dict):
        cache.clear()
