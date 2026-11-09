"""Hermetic ``Settings`` construction for tests."""

from __future__ import annotations

from typing import Any

from ragassist.shared.config.settings import Settings
from support.spec import TEST_SECRET_KEY


def make_settings(**overrides: Any) -> Settings:
    """Build a fresh ``Settings`` that ignores any ``.env`` file and the process-wide singleton.

    Defaults are the code defaults plus a known test ``SECRET_KEY``. Anything can be overridden:

        make_settings(APP_ENV="production", OPENAI_API_KEY="")
    """
    values: dict[str, Any] = {"SECRET_KEY": TEST_SECRET_KEY, "APP_ENV": "test"}
    values.update(overrides)
    return Settings(_env_file=None, **values)
