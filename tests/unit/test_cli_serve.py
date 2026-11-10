"""`ragassist serve` runs uvicorn behind the web container's proxy (ADR 0014)."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from ragassist.cli import main as cli
from ragassist.shared.config.settings import Settings

pytestmark = pytest.mark.unit


def run_serve(monkeypatch: pytest.MonkeyPatch, trusted: str) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: seen.update(kwargs))
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: Settings.model_construct(LOG_LEVEL="INFO", TRUSTED_PROXY_IPS=trusted),
    )
    result = CliRunner().invoke(cli.app, ["serve", "--host", "0.0.0.0", "--port", "8000"])  # noqa: S104
    assert result.exit_code == 0, result.output
    return seen


def test_proxy_headers_are_on_and_the_trusted_peers_come_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = run_serve(monkeypatch, "10.0.0.0/8,172.16.0.0/12")
    assert seen["proxy_headers"] is True
    assert seen["forwarded_allow_ips"] == "10.0.0.0/8,172.16.0.0/12"


def test_an_empty_setting_leaves_uvicorns_loopback_only_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = run_serve(monkeypatch, "")
    assert seen["forwarded_allow_ips"] is None


def test_the_setting_is_optional_and_empty_by_default() -> None:
    field = Settings.model_fields["TRUSTED_PROXY_IPS"]
    assert not field.is_required() and field.default == ""
