"""ProviderRegistry (feature 5): name -> factory lookup used to swap providers by configuration."""

from __future__ import annotations

import threading

import pytest

from ragassist.shared.registry import ProviderRegistry


@pytest.fixture
def registry() -> ProviderRegistry[dict[str, object]]:
    return ProviderRegistry[dict[str, object]]("widget")


class TestRegistration:
    def test_create_calls_the_factory(self, registry: ProviderRegistry[dict[str, object]]) -> None:
        registry.register("a", lambda: {"who": "a"})
        assert registry.create("a") == {"who": "a"}

    def test_args_and_kwargs_are_forwarded(
        self, registry: ProviderRegistry[dict[str, object]]
    ) -> None:
        registry.register("a", lambda x, *, y: {"x": x, "y": y})
        assert registry.create("a", 1, y=2) == {"x": 1, "y": 2}

    def test_each_create_builds_a_new_instance(
        self, registry: ProviderRegistry[dict[str, object]]
    ) -> None:
        registry.register("a", dict)
        assert registry.create("a") is not registry.create("a")

    @pytest.mark.parametrize("spelling", ["openai", "OpenAI", "  openai  ", "OPENAI\t"])
    def test_keys_are_case_and_whitespace_insensitive(
        self, registry: ProviderRegistry[dict[str, object]], spelling: str
    ) -> None:
        registry.register(" OpenAI ", lambda: {"ok": True})
        assert registry.is_registered(spelling)
        assert registry.create(spelling) == {"ok": True}

    def test_registering_again_replaces_the_factory(
        self, registry: ProviderRegistry[dict[str, object]]
    ) -> None:
        registry.register("a", lambda: {"v": 1})
        registry.register("A", lambda: {"v": 2})
        assert registry.create("a") == {"v": 2}
        assert registry.available_providers() == ["a"]

    def test_registries_are_independent(self) -> None:
        one, two = ProviderRegistry[int]("one"), ProviderRegistry[int]("two")
        one.register("x", lambda: 1)
        assert not two.is_registered("x")


class TestLookupErrors:
    def test_unknown_key_lists_alternatives(
        self, registry: ProviderRegistry[dict[str, object]]
    ) -> None:
        registry.register("zeta", dict)
        registry.register("alpha", dict)
        with pytest.raises(KeyError) as excinfo:
            registry.create("missing")
        message = str(excinfo.value)
        assert "widget" in message and "missing" in message
        assert message.index("alpha") < message.index("zeta")  # sorted, deterministic

    def test_empty_registry_says_none(self, registry: ProviderRegistry[dict[str, object]]) -> None:
        with pytest.raises(KeyError, match="none"):
            registry.create("anything")

    def test_factory_errors_propagate_unchanged(
        self, registry: ProviderRegistry[dict[str, object]]
    ) -> None:
        def broken() -> dict[str, object]:
            raise ConnectionError("cannot connect")

        registry.register("a", broken)
        with pytest.raises(ConnectionError, match="cannot connect"):
            registry.create("a")

    def test_is_registered_false_for_unknown(
        self, registry: ProviderRegistry[dict[str, object]]
    ) -> None:
        assert registry.is_registered("nope") is False


def test_available_providers_is_sorted(registry: ProviderRegistry[dict[str, object]]) -> None:
    for key in ("c", "a", "b"):
        registry.register(key, dict)
    assert registry.available_providers() == ["a", "b", "c"]


def test_concurrent_registration_loses_nothing(
    registry: ProviderRegistry[dict[str, object]],
) -> None:
    errors: list[BaseException] = []

    def worker(offset: int) -> None:
        try:
            for i in range(200):
                registry.register(f"k{offset}-{i}", dict)
                registry.available_providers()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(registry.available_providers()) == 8 * 200
