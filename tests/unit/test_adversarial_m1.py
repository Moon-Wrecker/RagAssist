"""Adversarial stress-testing and empirical validation for Milestone 1.

Targets:
1. ModelCatalog (catalog.py):
   - Circular alias detection (direct, self, multi-step, roles, overrides, long chains)
   - Unknown role mappings (bad roles, empty, whitespace, special chars, SQLi-like strings)
   - Malformed YAML handling (corrupted, empty, non-dict root, missing sections, invalid schemas)
   - Settings role override precedence (clean/dirty whitespace, comma parsing, deduplication)

2. DimensionProjector & EmbeddingService (embeddings/):
   - Projecting zero-vectors, single-element vectors, huge vectors (10k+ dimensions)
   - Cosine similarity invariance checks (across multiple dimensions, orthogonal, antiparallel)
   - Full FallbackChain exhaustion (timeouts, network errors, wrong dimensions, count mismatches)
   - Empty input handling (embed_documents([]), embed_query(""), embed_query("   "))
"""

import math
import random
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from support.settings import make_settings

from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.platform.embeddings.projector import DimensionProjector
from ragassist.platform.embeddings.service import EmbeddingService
from ragassist.platform.llm.catalog import ModelCatalog
from ragassist.platform.llm.catalog_models import (
    ModelDefinitionConfig,
    ModelsFileConfig,
    PricingConfig,
)
from ragassist.shared.resilience import FallbackChain

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def make_dummy_model(
    name: str = "test-model", provider: str = "openai", **kwargs: Any
) -> dict[str, Any]:
    return {"provider": provider, "model_name": name, **kwargs}


def build_catalog_from_dicts(
    models: dict[str, Any] | None = None,
    aliases: dict[str, str] | None = None,
    roles: dict[str, Any] | None = None,
) -> ModelCatalog:
    data = {
        "providers": {"openai": {"adapter": "openai"}},
        "models": models
        or {
            "m1": make_dummy_model("m1"),
            "m2": make_dummy_model("m2"),
            "m3": make_dummy_model("m3"),
        },
        "aliases": aliases or {},
        "roles": roles or {"generator": {"primary": "m1", "fallbacks": ["m2", "m3"]}},
    }
    return ModelCatalog(ModelsFileConfig.model_validate(data))


# ---------------------------------------------------------------------------
# 1. ModelCatalog Adversarial Tests
# ---------------------------------------------------------------------------


class TestModelCatalogAdversarial:
    """Adversarial stress-testing of ModelCatalog."""

    def test_circular_aliases_direct_loop(self) -> None:
        """Direct 2-step cycle: a -> b -> a."""
        catalog = build_catalog_from_dicts(aliases={"a": "b", "b": "a"})
        with pytest.raises(ValueError, match="Circular alias loop detected"):
            catalog.resolve_model_id("a")

    def test_circular_aliases_self_loop(self) -> None:
        """Self loop: loop -> loop."""
        catalog = build_catalog_from_dicts(aliases={"loop": "loop"})
        with pytest.raises(ValueError, match="Circular alias loop detected"):
            catalog.resolve_model_id("loop")

    def test_circular_aliases_deep_multistep_loop(self) -> None:
        """Deep cycle: a -> b -> c -> d -> e -> f -> b."""
        aliases = {
            "a": "b",
            "b": "c",
            "c": "d",
            "d": "e",
            "e": "f",
            "f": "b",
        }
        catalog = build_catalog_from_dicts(aliases=aliases)
        with pytest.raises(ValueError, match="Circular alias loop detected"):
            catalog.resolve_model_id("a")

    def test_circular_alias_referenced_in_role_primary(self) -> None:
        """A role's primary model references a circular alias."""
        catalog = build_catalog_from_dicts(
            aliases={"cycle1": "cycle2", "cycle2": "cycle1"},
            roles={"generator": {"primary": "cycle1", "fallbacks": ["m2"]}},
        )
        with pytest.raises(ValueError, match="Circular alias loop detected"):
            catalog.resolve_role_chain("generator")

    def test_circular_alias_referenced_in_role_fallbacks(self) -> None:
        """A role's fallback references a circular alias."""
        catalog = build_catalog_from_dicts(
            aliases={"cycle1": "cycle2", "cycle2": "cycle1"},
            roles={"generator": {"primary": "m1", "fallbacks": ["cycle1"]}},
        )
        with pytest.raises(ValueError, match="Circular alias loop detected"):
            catalog.resolve_role_chain("generator")

    def test_circular_alias_referenced_in_settings_override(self) -> None:
        """Settings override injects a circular alias."""
        catalog = build_catalog_from_dicts(
            aliases={"cycle1": "cycle2", "cycle2": "cycle1"},
        )
        settings = make_settings(LLM_ROLE_GENERATOR_PRIMARY="cycle1")
        with pytest.raises(ValueError, match="Circular alias loop detected"):
            catalog.resolve_role_chain("generator", settings)

    def test_long_alias_chain_without_cycle_resolves_cleanly(self) -> None:
        """A 30-hop non-circular chain resolves correctly without false positives."""
        hops = 30
        aliases = {f"alias_{i}": f"alias_{i + 1}" for i in range(hops)}
        aliases[f"alias_{hops}"] = "m1"
        catalog = build_catalog_from_dicts(aliases=aliases)
        assert catalog.resolve_model_id("alias_0") == "m1"

    def test_broken_alias_pointer_fails_loudly_with_missing_target(self) -> None:
        """Alias pointing to a non-existent model raises KeyError."""
        catalog = build_catalog_from_dicts(aliases={"alias1": "alias2", "alias2": "ghost_model"})
        with pytest.raises(KeyError) as exc_info:
            catalog.resolve_model_id("alias1")
        # Note: reports key_or_alias 'alias1' in exception message
        assert "alias1" in str(exc_info.value)

    def test_unknown_role_mapping_raises_key_error_with_inventory(self) -> None:
        """Querying unknown roles raises KeyError listing available roles."""
        catalog = build_catalog_from_dicts(roles={"generator": {"primary": "m1"}})
        with pytest.raises(KeyError) as exc_info:
            catalog.get_role_mapping("astronomer")
        assert "astronomer" in str(exc_info.value)
        assert "generator" in str(exc_info.value)

    @pytest.mark.parametrize(
        "bad_role",
        [
            "",
            "   ",
            "nonexistent_role_xyz",
            "generator\x00nullbyte",
            "'; DROP TABLE roles; --",
            "🤖_role",
        ],
    )
    def test_adversarial_role_names_fail_cleanly(self, bad_role: str) -> None:
        """Adversarial/malformed role names fail safely with KeyError."""
        catalog = build_catalog_from_dicts()
        with pytest.raises(KeyError):
            catalog.get_role_mapping(bad_role)
        with pytest.raises(KeyError):
            catalog.resolve_role_chain(bad_role)

    def test_role_with_duplicate_fallbacks_deduplicates_preserving_order(self) -> None:
        """Role with overlapping primary and fallbacks deduplicates correctly."""
        catalog = build_catalog_from_dicts(
            models={
                "m1": make_dummy_model("m1"),
                "m2": make_dummy_model("m2"),
                "m3": make_dummy_model("m3"),
            },
            roles={"generator": {"primary": "m1", "fallbacks": ["m2", "m1", "m3", "m2"]}},
        )
        resolved = catalog.resolve_role_chain("generator")
        assert resolved == ["m1", "m2", "m3"]

    def test_malformed_yaml_corrupt_syntax(self, tmp_path) -> None:
        """Corrupt YAML syntax raises YAMLError / ScannerError."""
        bad_yaml = tmp_path / "corrupt.yaml"
        bad_yaml.write_text(
            "providers:\n  openai:\n    adapter: [unclosed list\n", encoding="utf-8"
        )
        with pytest.raises(yaml.YAMLError):
            ModelCatalog.load_from_yaml(bad_yaml)

    def test_malformed_yaml_empty_content(self, tmp_path) -> None:
        """Empty YAML file raises ValidationError."""
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("", encoding="utf-8")
        with pytest.raises(ValidationError):
            ModelCatalog.load_from_yaml(empty_yaml)

    def test_malformed_yaml_non_dict_root(self, tmp_path) -> None:
        """YAML with non-dict root (e.g. list) raises ValidationError."""
        list_yaml = tmp_path / "list_root.yaml"
        list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValidationError):
            ModelCatalog.load_from_yaml(list_yaml)

    def test_malformed_yaml_missing_required_roles_section(self) -> None:
        """Missing roles section fails validation."""
        raw = {
            "providers": {"p": {"adapter": "openai"}},
            "models": {"m": make_dummy_model("m")},
        }
        with pytest.raises(ValidationError):
            ModelsFileConfig.model_validate(raw)

    def test_malformed_yaml_forbidden_extra_field_on_model(self) -> None:
        """Extra undocumented fields on a model definition are forbidden."""
        raw = make_dummy_model("m")
        raw["hallucinated_property"] = 12345
        with pytest.raises(ValidationError):
            ModelDefinitionConfig.model_validate(raw)

    def test_malformed_yaml_invalid_numeric_ranges(self) -> None:
        """Invalid numbers (negative context, negative price) are rejected."""
        with pytest.raises(ValidationError):
            ModelDefinitionConfig.model_validate(make_dummy_model("m", context_window=-10))
        with pytest.raises(ValidationError):
            PricingConfig.model_validate({"input_cost_per_mtok": -0.5})

    def test_settings_role_override_precedence(self) -> None:
        """Settings override replaces primary and fallbacks, stripping dirty whitespace."""
        catalog = build_catalog_from_dicts(
            models={
                "m1": make_dummy_model("m1"),
                "m2": make_dummy_model("m2"),
                "m3": make_dummy_model("m3"),
                "override_p": make_dummy_model("override_p"),
                "override_fb": make_dummy_model("override_fb"),
            },
            roles={"generator": {"primary": "m1", "fallbacks": ["m2", "m3"]}},
        )
        settings = make_settings(
            LLM_ROLE_GENERATOR_PRIMARY="  override_p  ",
            LLM_ROLE_GENERATOR_FALLBACKS=" ,  override_fb , , override_p , ",
        )
        resolved = catalog.resolve_role_chain("generator", settings)
        # Should deduplicate and prioritize override_p, then override_fb
        assert resolved == ["override_p", "override_fb"]


# ---------------------------------------------------------------------------
# 2. DimensionProjector Adversarial Tests
# ---------------------------------------------------------------------------


class TestDimensionProjectorAdversarial:
    """Adversarial stress-testing of DimensionProjector."""

    def test_zero_vector_smaller_dimension_padding(self) -> None:
        """Zero vector smaller than target: should pad to 1536 without ZeroDivisionError."""
        projector = DimensionProjector(target_dimension=1536)
        zero_384 = [0.0] * 384
        out = projector.project_vector(zero_384)
        assert len(out) == 1536
        assert all(x == 0.0 for x in out)

    def test_zero_vector_exact_dimension(self) -> None:
        """Zero vector exact target dimension."""
        projector = DimensionProjector(target_dimension=1536)
        zero_1536 = [0.0] * 1536
        out = projector.project_vector(zero_1536)
        assert len(out) == 1536
        assert all(x == 0.0 for x in out)

    def test_zero_vector_larger_dimension_truncation(self) -> None:
        """Zero vector larger than target: should truncate without ZeroDivisionError."""
        projector = DimensionProjector(target_dimension=1536)
        zero_3072 = [0.0] * 3072
        out = projector.project_vector(zero_3072)
        assert len(out) == 1536
        assert all(x == 0.0 for x in out)

    def test_empty_vector_input(self) -> None:
        """Empty vector input: should pad to target dimension with zeros."""
        projector = DimensionProjector(target_dimension=1536)
        out = projector.project_vector([])
        assert len(out) == 1536
        assert all(x == 0.0 for x in out)

    def test_single_element_vectors(self) -> None:
        """Single-element vectors normalized and zero-padded."""
        projector = DimensionProjector(target_dimension=1536)

        # Positive element
        out_pos = projector.project_vector([5.0])
        assert len(out_pos) == 1536
        assert out_pos[0] == pytest.approx(1.0, abs=1e-7)
        assert all(x == 0.0 for x in out_pos[1:])

        # Negative element
        out_neg = projector.project_vector([-99.0])
        assert len(out_neg) == 1536
        assert out_neg[0] == pytest.approx(-1.0, abs=1e-7)
        assert all(x == 0.0 for x in out_neg[1:])

        # Zero element
        out_zero = projector.project_vector([0.0])
        assert len(out_zero) == 1536
        assert all(x == 0.0 for x in out_zero)

    def test_tuple_and_integer_sequence_inputs(self) -> None:
        """DimensionProjector accepts tuples and integer sequences without crashing."""
        projector = DimensionProjector(target_dimension=1536)
        int_tuple = (1, 2, 3, 4)
        out = projector.project_vector(int_tuple)
        assert len(out) == 1536
        norm = math.sqrt(sum(x * x for x in out))
        assert pytest.approx(1.0, abs=1e-6) == norm

    def test_projector_idempotency_on_target_dimension(self) -> None:
        """Projecting an already projected vector of target dimension preserves exact values."""
        projector = DimensionProjector(target_dimension=1536)
        initial = projector.project_vector([1.0, 2.0, 3.0])
        second = projector.project_vector(initial)
        assert initial == second

    def test_huge_vector_truncation(self) -> None:
        """Vector with 20,000 dimensions truncated to 1536 and normalized."""
        projector = DimensionProjector(target_dimension=1536)
        huge_dim = 20_000
        # First 1536 elements have values
        vec = [float(i % 10 + 1) for i in range(huge_dim)]
        out = projector.project_vector(vec)
        assert len(out) == 1536
        norm = math.sqrt(sum(x * x for x in out))
        assert pytest.approx(1.0, abs=1e-6) == norm

    def test_cosine_similarity_invariance_multi_dimensions(self) -> None:
        """Zero-padding preserves exact cosine similarity across diverse dimensions."""
        projector = DimensionProjector(target_dimension=1536)
        rng = random.Random(42)

        test_dimensions = [2, 3, 16, 64, 128, 384, 512, 768, 1024]
        for d in test_dimensions:
            # Generate 5 random pairs for each dimension
            for _ in range(5):
                u = [rng.gauss(0, 1) for _ in range(d)]
                v = [rng.gauss(0, 1) for _ in range(d)]

                orig_sim = cosine_similarity(u, v)

                u_proj = projector.project_vector(u)
                v_proj = projector.project_vector(v)

                assert len(u_proj) == 1536
                assert len(v_proj) == 1536
                proj_sim = cosine_similarity(u_proj, v_proj)

                assert pytest.approx(orig_sim, abs=1e-5) == proj_sim, (
                    f"Cosine invariance violated for dimension {d}: {orig_sim} != {proj_sim}"
                )

    def test_cosine_similarity_orthogonal_and_antiparallel(self) -> None:
        """Orthogonal vectors stay orthogonal (cos=0), antiparallel stay antiparallel (cos=-1)."""
        projector = DimensionProjector(target_dimension=1536)

        # Orthogonal in 3D
        u = [1.0, 0.0, 0.0]
        v = [0.0, 1.0, 0.0]
        assert cosine_similarity(u, v) == 0.0
        assert pytest.approx(0.0, abs=1e-7) == cosine_similarity(
            projector.project_vector(u), projector.project_vector(v)
        )

        # Antiparallel in 4D
        a = [1.0, -2.0, 3.0, -4.0]
        b = [-1.0, 2.0, -3.0, 4.0]
        assert pytest.approx(-1.0, abs=1e-6) == cosine_similarity(a, b)
        assert pytest.approx(-1.0, abs=1e-6) == cosine_similarity(
            projector.project_vector(a), projector.project_vector(b)
        )


# ---------------------------------------------------------------------------
# 3. EmbeddingService Adversarial Tests
# ---------------------------------------------------------------------------


class MockFaultyProvider(EmbeddingProvider):
    """Mock provider configurable to fail with timeouts, errors, or invalid responses."""

    def __init__(
        self,
        name: str,
        dim: int = 1536,
        raise_timeout: bool = False,
        raise_error: Exception | None = None,
        return_wrong_dim: int | None = None,
        return_wrong_count: int | None = None,
    ) -> None:
        self._name = name
        self._dim = dim
        self.raise_timeout = raise_timeout
        self.raise_error = raise_error
        self.return_wrong_dim = return_wrong_dim
        self.return_wrong_count = return_wrong_count
        self.call_count_docs = 0
        self.call_count_query = 0

    @property
    def name(self) -> str:
        return self._name

    def dimension(self) -> int:
        return self._dim

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.call_count_docs += 1
        if self.raise_timeout:
            raise TimeoutError(f"Provider {self._name} timed out")
        if self.raise_error:
            raise self.raise_error
        if self.return_wrong_count is not None:
            return [[0.1] * self._dim for _ in range(self.return_wrong_count)]
        dim = self.return_wrong_dim if self.return_wrong_dim is not None else self._dim
        return [[0.1] * dim for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.call_count_query += 1
        if self.raise_timeout:
            raise TimeoutError(f"Provider {self._name} timed out")
        if self.raise_error:
            raise self.raise_error
        dim = self.return_wrong_dim if self.return_wrong_dim is not None else self._dim
        return [0.1] * dim


class TestEmbeddingServiceAdversarial:
    """Adversarial stress-testing of EmbeddingService."""

    @pytest.mark.asyncio
    async def test_embed_documents_empty_list_returns_immediately(self) -> None:
        """Empty input list returns [] without invoking providers."""
        provider = MockFaultyProvider("p1", raise_error=RuntimeError("Should not be called"))
        chain = FallbackChain("test_chain", [provider])
        svc = EmbeddingService(chain, expected_dimension=1536)

        result = await svc.embed_documents([])
        assert result == []
        assert provider.call_count_docs == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("empty_query", ["", "   ", "\t\n"])
    async def test_embed_query_empty_or_whitespace_returns_zero_vector(
        self, empty_query: str
    ) -> None:
        """Empty or whitespace query returns zero-vector without invoking providers."""
        provider = MockFaultyProvider("p1", raise_error=RuntimeError("Should not be called"))
        chain = FallbackChain("test_chain", [provider])
        svc = EmbeddingService(chain, expected_dimension=1536)

        result = await svc.embed_query(empty_query)
        assert len(result) == 1536
        assert all(x == 0.0 for x in result)
        assert provider.call_count_query == 0

    @pytest.mark.asyncio
    async def test_full_fallback_chain_exhaustion_multi_failure(self) -> None:
        """Chain with timeout, network error, and wrong dimension fails through all members."""
        p1 = MockFaultyProvider("p1_timeout", raise_timeout=True)
        p2 = MockFaultyProvider("p2_network", raise_error=ConnectionResetError("Socket reset"))
        p3 = MockFaultyProvider("p3_wrong_dim", return_wrong_dim=512)

        chain = FallbackChain("resilience_chain", [p1, p2, p3])
        svc = EmbeddingService(chain, expected_dimension=1536)

        with pytest.raises(RuntimeError) as exc_info:
            await svc.embed_documents(["doc1", "doc2"])

        err_msg = str(exc_info.value)
        assert "All 3 members of FallbackChain 'resilience_chain' failed" in err_msg
        assert p1.call_count_docs == 1
        assert p2.call_count_docs == 1
        assert p3.call_count_docs == 1

    @pytest.mark.asyncio
    async def test_fallback_rejection_on_mismatched_vector_count(self) -> None:
        """Provider returning fewer vectors than requested texts is rejected by _is_acceptable."""
        # Provider returns 1 vector when 2 documents were sent
        p1 = MockFaultyProvider("p1_bad_count", return_wrong_count=1)
        p2 = MockFaultyProvider("p2_healthy", dim=1536)

        chain = FallbackChain("count_chain", [p1, p2])
        svc = EmbeddingService(chain, expected_dimension=1536)

        result = await svc.embed_documents(["doc1", "doc2"])
        assert len(result) == 2
        assert p1.call_count_docs == 1
        assert p2.call_count_docs == 1

    @pytest.mark.asyncio
    async def test_fallback_rejection_on_empty_vector_list(self) -> None:
        """Provider returning empty vector list for non-empty documents is rejected."""
        p1 = MockFaultyProvider("p1_empty", return_wrong_count=0)
        p2 = MockFaultyProvider("p2_healthy", dim=1536)

        chain = FallbackChain("empty_res_chain", [p1, p2])
        svc = EmbeddingService(chain, expected_dimension=1536)

        result = await svc.embed_documents(["doc1"])
        assert len(result) == 1
        assert p1.call_count_docs == 1
        assert p2.call_count_docs == 1

    @pytest.mark.asyncio
    async def test_fallback_chain_with_single_failing_member(self) -> None:
        """Single provider in chain failing produces informative exhaustion exception."""
        p1 = MockFaultyProvider("solo", raise_timeout=True)
        chain = FallbackChain("solo_chain", [p1])
        svc = EmbeddingService(chain, expected_dimension=1536)

        with pytest.raises(RuntimeError) as exc_info:
            await svc.embed_query("search")

        assert "All 1 members of FallbackChain 'solo_chain' failed" in str(exc_info.value)
        assert p1.call_count_query == 1
