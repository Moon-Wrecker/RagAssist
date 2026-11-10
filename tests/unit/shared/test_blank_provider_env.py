"""A blank OPENAI_BASE_URL must not reach the OpenAI SDK.

`.env.example` ships `OPENAI_BASE_URL=` (blank means "use the provider default"). Compose passes that blank
value into the container as an empty string, and the SDK reads the variable itself when no `base_url` is
given: an empty string counts as set, so every call failed with "Request URL is missing an 'http://' or
'https://' protocol" (shown as `APIConnectionError: Connection error.`). Checked in openai 2.54.0:
`if base_url is None: base_url = os.environ.get("OPENAI_BASE_URL")`.
"""

from __future__ import annotations

import os
import secrets

import openai
import pytest

from ragassist.shared.config import settings as settings_module
from ragassist.shared.config.settings import drop_blank_provider_env

VARIABLE = "OPENAI_BASE_URL"


def sdk_base_url() -> str:
    return str(openai.AsyncOpenAI(api_key=secrets.token_urlsafe(16)).base_url)


class TestDropBlankProviderEnv:
    def test_a_blank_value_is_removed_so_the_sdk_uses_its_own_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(VARIABLE, raising=False)
        default_url = sdk_base_url()

        monkeypatch.setenv(VARIABLE, "")
        assert sdk_base_url() != default_url  # the bug: a blank value is taken as the address

        drop_blank_provider_env()
        assert sdk_base_url() == default_url

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_whitespace_only_counts_as_blank(
        self, monkeypatch: pytest.MonkeyPatch, blank: str
    ) -> None:
        monkeypatch.setenv(VARIABLE, blank)
        drop_blank_provider_env()
        assert VARIABLE not in os.environ

    def test_a_real_override_is_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(VARIABLE, "https://proxy.example.test/v1")
        drop_blank_provider_env()
        assert sdk_base_url().startswith("https://proxy.example.test/v1")

    def test_an_unset_variable_stays_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(VARIABLE, raising=False)
        drop_blank_provider_env()
        assert VARIABLE not in os.environ


def test_get_settings_drops_the_blank_value_before_anything_builds_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, bool] = {}

    class FakeSettings:
        def __init__(self) -> None:
            seen["blank_variable_present"] = VARIABLE in os.environ

    monkeypatch.setenv(VARIABLE, "")
    monkeypatch.setattr(settings_module, "Settings", FakeSettings)
    monkeypatch.setattr(settings_module, "_settings", None)

    settings_module.get_settings()

    assert seen == {"blank_variable_present": False}
