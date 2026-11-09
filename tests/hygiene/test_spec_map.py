"""Sanity of the planned-symbol map: every entry is well formed, points into the repository's packages,
and every area is covered. A malformed map would make every pending suite lie."""

from __future__ import annotations

import pytest
from support.specs import resolve
from support.specs.map import ROUTES, TARGETS, render_appendix

pytestmark = pytest.mark.hygiene

ALLOWED_ROOTS = ("ragassist.", "evals.", "services.")
AREAS = {
    "knowledge",
    "rerank",
    "storage",
    "queue",
    "retrieval",
    "eval",
    "assistant",
    "actions",
    "escalation",
    "worker",
}


class TestEntries:
    @pytest.mark.parametrize("key", sorted(TARGETS))
    def test_each_entry_is_well_formed(self, key: str) -> None:
        target = TARGETS[key]
        assert target.module.startswith(ALLOWED_ROOTS), (
            f"{key}: module {target.module} is outside the product"
        )
        assert target.symbol and target.symbol.replace(".", "").replace("_", "").isalnum(), key
        assert target.expects.strip(), f"{key}: an entry must say what interface the tests assume"

    def test_keys_are_namespaced_by_area(self) -> None:
        assert all("." in key for key in TARGETS)

    def test_every_planned_area_has_at_least_one_entry(self) -> None:
        present = {target.area for target in TARGETS.values()}
        assert present >= AREAS, f"areas without entries: {sorted(AREAS - present)}"

    def test_pending_resolution_never_crashes_on_a_missing_module(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resolving an absent planned symbol must raise a classified error, not a bare ImportError."""
        from support.specs import Pending
        from support.specs.map import TARGETS as LIVE_TARGETS
        from support.specs.map import Target

        monkeypatch.setitem(
            LIVE_TARGETS, "test.absent", Target("test", "ragassist.modules.nope.absent", "X", "x")
        )
        with pytest.raises(Pending):
            resolve("test.absent")


class TestRoutes:
    def test_every_route_has_a_valid_method_and_absolute_path(self) -> None:
        for key, (method, path) in ROUTES.items():
            assert method in {"GET", "POST", "PUT", "PATCH", "DELETE"}, key
            assert path.startswith("/"), key

    def test_the_appendix_renders_every_entry(self) -> None:
        text = render_appendix()
        assert all(f"`{key}`" in text for key in TARGETS)
        assert all(f"`{key}`" in text for key in ROUTES)
