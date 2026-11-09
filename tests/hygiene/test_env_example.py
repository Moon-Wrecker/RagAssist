"""AGENTS.md section 3.1: ``.env.example`` must stay synchronised with ``Settings``."""

from __future__ import annotations

import re

import pytest
from dotenv import dotenv_values
from support.repo import REPO_ROOT, read

from ragassist.shared.config.settings import Settings

EXAMPLE = REPO_ROOT / ".env.example"
SECRETISH = re.compile(r"(API_KEY|SECRET|PASSWORD|ACCESS_KEY|_KEY$|^SECRET_KEY$)", re.I)
PLACEHOLDER = re.compile(r"^(|test|ollama|dummy|change-this.*|dev-.*|your-.*|<.*>|none)$", re.I)
REAL_SECRET_SHAPES = {
    "OpenAI-style key": r"sk-[A-Za-z0-9_-]{20,}",
    "AWS access key id": r"AKIA[0-9A-Z]{16}",
    "Google API key": r"AIza[0-9A-Za-z_-]{30,}",
    "Google AQ. key": r"AQ\.[A-Za-z0-9_-]{30,}",
    "Slack token": r"xox[abprs]-[A-Za-z0-9-]{10,}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "JWT": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
}


@pytest.fixture(scope="module")
def example() -> dict[str, str | None]:
    return dict(dotenv_values(EXAMPLE))


@pytest.fixture(scope="module")
def documented_keys() -> set[str]:
    """Keys that appear as ``KEY=`` lines, whether active or commented-out documentation."""
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", read(".env.example"), re.M))


class TestKeysMatchSettings:
    def test_file_exists_and_is_utf8(self) -> None:
        assert EXAMPLE.is_file() and read(".env.example").strip()

    def test_every_settings_field_is_documented(self, documented_keys: set[str]) -> None:
        missing = sorted(set(Settings.model_fields) - documented_keys)
        assert not missing, f"Add to .env.example: {missing}"

    def test_every_documented_key_is_a_real_settings_field(self, documented_keys: set[str]) -> None:
        stale = sorted(documented_keys - set(Settings.model_fields))
        assert not stale, f"Remove from .env.example (no such Settings field): {stale}"

    def test_no_key_is_defined_twice(self) -> None:
        keys = re.findall(r"^([A-Z][A-Z0-9_]+)=", read(".env.example"), re.M)
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        assert not duplicates, f"Duplicated keys: {duplicates}"


class TestValuesMatchDefaults:
    def test_the_file_loads_into_valid_settings(self) -> None:
        Settings(_env_file=EXAMPLE)  # raises ValidationError on a bad value

    def test_every_value_equals_the_code_default(self) -> None:
        from_file = Settings(_env_file=EXAMPLE)
        from_code = Settings(_env_file=None, SECRET_KEY=from_file.SECRET_KEY)
        different = {
            name: (getattr(from_file, name), getattr(from_code, name))
            for name in Settings.model_fields
            if getattr(from_file, name) != getattr(from_code, name)
        }
        assert not different, f"(.env.example, settings.py default) differ for: {different}"

    def test_the_template_defaults_to_a_development_environment(
        self, example: dict[str, str | None]
    ) -> None:
        assert example["APP_ENV"] == "development"
        assert example["DEBUG"] == "true"


class TestNoRealSecrets:
    @pytest.mark.parametrize("label", sorted(REAL_SECRET_SHAPES))
    def test_file_contains_no_credential_shaped_strings(self, label: str) -> None:
        assert not re.search(REAL_SECRET_SHAPES[label], read(".env.example")), (
            f"looks like a real {label}"
        )

    def test_secret_fields_hold_only_placeholders(self, example: dict[str, str | None]) -> None:
        offenders = {
            k: v
            for k, v in example.items()
            if SECRETISH.search(k) and not k.endswith("_NAME") and not PLACEHOLDER.match(v or "")
        }
        assert not offenders, f"Replace with an empty value or an obvious placeholder: {offenders}"

    def test_provider_api_keys_are_empty(self, example: dict[str, str | None]) -> None:
        provider_keys = [
            k for k in example if k.endswith("_API_KEY") and k != "OPENAI_COMPATIBLE_API_KEY"
        ]
        assert provider_keys, "expected provider API key placeholders"
        assert {k: example[k] for k in provider_keys if example[k]} == {}

    def test_the_real_env_file_is_never_tracked_or_copied_here(self) -> None:
        assert ".env" in [line.strip() for line in read(".gitignore").splitlines()]
