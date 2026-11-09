"""Settings: defaults, environment precedence, validation, singleton behaviour."""

from __future__ import annotations

import secrets
from pathlib import Path
from urllib.parse import quote

import pytest
from pydantic import ValidationError
from support.defects import defect
from support.settings import make_settings

from ragassist.shared.config import settings as settings_module
from ragassist.shared.config.settings import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestDefaultsMatchTheSpec:
    """Values the approved plan states explicitly. If one changes, the docs must change too."""

    def test_retrieval_and_chunking_defaults(self) -> None:
        s = make_settings()
        assert s.RETRIEVAL_RRF_K == 60
        assert (s.CHUNK_MAX_TOKENS, s.CHUNK_OVERLAP_TOKENS) == (512, 64)
        assert s.CHUNK_MERGE_PEERS is True
        assert (s.CHUNK_SEMANTIC, s.CHUNK_PARENT_CHILD) == (False, False)
        assert s.CHUNK_STRATEGY == "hybrid"

    def test_reranker_chain_prefers_cross_encoder_then_flashrank_then_none(self) -> None:
        assert make_settings().RERANKER_CHAIN.split(",") == ["cross_encoder", "flashrank", "none"]

    def test_decider_chain_defaults_end_in_an_always_available_member(self) -> None:
        s = make_settings()
        assert s.DECIDER_CHAIN.split(",")[-1] == "rules"  # last-resort guard, never fails
        assert s.ROUTER_DECIDER_CHAIN.split(",")[0] == "semantic_router"
        assert s.ROUTER_DECIDER_CHAIN.split(",")[-1] == "rules"
        assert pytest.approx(0.70) == s.DECIDER_MIN_CONFIDENCE

    def test_security_defaults(self) -> None:
        s = make_settings()
        assert s.JWT_ALGORITHM == "HS256"
        assert s.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 1440
        assert s.API_V1_PREFIX == "/v1"

    def test_database_role_is_not_a_superuser_name(self) -> None:
        """RLS does not apply to superusers: the app must connect as the restricted role."""
        user = make_settings().DATABASE_URL.split("://", 1)[1].split(":", 1)[0]
        assert user == "app_user"


class TestEnvironmentHandling:
    def test_environment_variable_overrides_the_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHUNK_MAX_TOKENS", "256")
        assert Settings(_env_file=None).CHUNK_MAX_TOKENS == 256

    def test_bool_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RERANK_ENABLED", "false")
        monkeypatch.setenv("CHUNK_SEMANTIC", "1")
        s = Settings(_env_file=None)
        assert s.RERANK_ENABLED is False and s.CHUNK_SEMANTIC is True

    def test_list_fields_are_read_as_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORS_ORIGINS", '["https://a.example","https://b.example"]')
        assert Settings(_env_file=None).CORS_ORIGINS == ["https://a.example", "https://b.example"]

    def test_env_file_is_read_when_given_and_environment_wins_over_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file = tmp_path / "custom.env"
        env_file.write_text("CHUNK_MAX_TOKENS=111\nCHUNK_OVERLAP_TOKENS=11\n", encoding="utf-8")
        monkeypatch.delenv(
            "CHUNK_MAX_TOKENS"
        )  # the hermetic baseline sets it; remove so the file applies
        monkeypatch.setenv("CHUNK_OVERLAP_TOKENS", "22")
        s = Settings(_env_file=env_file)
        assert s.CHUNK_MAX_TOKENS == 111  # from the file
        assert s.CHUNK_OVERLAP_TOKENS == 22  # environment beats the file

    def test_unknown_variables_are_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TOTALLY_UNKNOWN_SETTING", "x")
        Settings(_env_file=None)  # must not raise

    def test_the_developers_real_env_file_is_never_read_in_tests(self) -> None:
        """Guards the hermetic setup: a real `.env` must not influence any test."""
        assert Settings.model_config.get("env_file") is None

    @pytest.mark.parametrize("value", ["dev", "prod", "Production", ""])
    def test_invalid_app_env_is_rejected(self, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", value)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)

    @pytest.mark.parametrize("name", ["CHUNK_MAX_TOKENS", "WORKER_CONCURRENCY", "DB_POOL_SIZE"])
    def test_non_numeric_values_are_rejected(
        self, name: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(name, "lots")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)


class TestSingleton:
    def test_get_settings_is_cached(self) -> None:
        assert get_settings() is get_settings()

    def test_cache_reset_rereads_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        first = get_settings()
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        assert get_settings() is first  # cached: change not visible yet
        settings_module._settings = None
        assert get_settings().LOG_LEVEL == "DEBUG"

    def test_hermetic_fixture_provides_the_test_environment(self) -> None:
        s = get_settings()
        assert s.APP_ENV == "test"
        assert s.MOCK_SAAS_BASE_URL == "http://mocksaas.test"


class TestValidationGaps:
    @pytest.mark.parametrize("weak", ["short", "change-" + "x" * 40, "dev-" + "x" * 40])
    def test_production_refuses_short_or_template_signing_keys(self, weak: str) -> None:
        with pytest.raises(ValidationError):
            make_settings(APP_ENV="production", SECRET_KEY=weak)

    @pytest.mark.parametrize(
        "name",
        [
            "SECRET_KEY",
            "DEV_AUTH_SECRET",
            "DB_APP_PASSWORD",
            "DB_ADMIN_PASSWORD",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ],
    )
    def test_secrets_have_no_code_default_and_are_required(self, name: str) -> None:
        """AGENTS.md 3.7: a credential is never committed as a default; leaving it out fails at start-up."""
        assert Settings.model_fields[name].is_required()

    def test_a_missing_secret_fails_loudly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SECRET_KEY")
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            Settings(_env_file=None)

    def test_database_urls_are_built_from_the_parts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Characters that must be percent-encoded in a URL's userinfo; the rest is random per run.
        special_password = f"@/:{secrets.token_urlsafe(12)}"
        monkeypatch.setenv("DB_APP_PASSWORD", special_password)
        s = Settings(_env_file=None)
        encoded = quote(special_password, safe="")
        assert encoded != special_password
        assert s.DATABASE_URL.startswith(f"postgresql+asyncpg://{s.DB_APP_USER}:{encoded}@")
        assert s.DATABASE_ADMIN_URL.startswith(f"postgresql+asyncpg://{s.DB_ADMIN_USER}:")
        assert s.DATABASE_URL.endswith(f"@{s.DB_HOST}:{s.DB_PORT}/{s.DB_NAME}")

    def test_a_full_database_url_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        override = f"postgresql+asyncpg://override:{secrets.token_urlsafe(12)}@db.internal:5432/x"
        monkeypatch.setenv("DATABASE_URL", override)
        assert override == Settings(_env_file=None).DATABASE_URL

    def test_production_accepts_an_explicit_strong_secret(self) -> None:
        make_settings(APP_ENV="production", SECRET_KEY="x" * 64)

    @defect("DEFECT-16")
    @pytest.mark.parametrize("name", ["ESCALATION_THRESHOLD", "DECIDER_MIN_CONFIDENCE"])
    @pytest.mark.parametrize("value", [-0.1, 1.5, 65])
    def test_confidence_thresholds_must_be_probabilities(self, name: str, value: float) -> None:
        with pytest.raises(ValidationError):
            make_settings(**{name: value})


class TestRoleDefaultsDoNotShadowTheCatalog:
    """Regression guard for the fixed DEFECT-14: empty defaults let models.yaml decide the roles."""

    def test_llm_role_settings_default_to_empty(self) -> None:
        settings = make_settings()
        assert settings.LLM_ROLE_GENERATOR_PRIMARY == ""
        assert settings.LLM_ROLE_REWRITER_PRIMARY == ""
