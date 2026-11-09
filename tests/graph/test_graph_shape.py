"""The compiled graph's shape: every planned node exists, and the edges the plan requires are present.
A topology change that the plan does not describe fails here, in review, not in production."""

from __future__ import annotations

import pytest
from support.graph_harness import PLANNED_NODES, make_graph
from support.specs import need

pytestmark = pytest.mark.graph


@pytest.fixture
def compiled(kit):  # type: ignore[no-untyped-def]
    return make_graph(kit).get_graph()


class TestNodes:
    def test_every_planned_node_is_present(self, compiled) -> None:  # type: ignore[no-untyped-def]
        assert set(PLANNED_NODES) <= set(compiled.nodes)

    def test_no_unplanned_node_is_added_silently(self, compiled) -> None:  # type: ignore[no-untyped-def]
        extra = set(compiled.nodes) - set(PLANNED_NODES) - {"__start__", "__end__"}
        assert not extra, f"unplanned nodes {sorted(extra)}: update the plan or the graph"

    def test_the_declared_node_names_match_the_built_graph(self, compiled) -> None:  # type: ignore[no-untyped-def]
        assert set(need("assistant.NODE_NAMES")) <= set(compiled.nodes)


class TestEdges:
    @pytest.mark.parametrize(
        ("source", "target"),
        [
            ("__start__", "guard_input"),
            ("guard_input", "router"),
            ("rewrite", "hybrid_retrieve"),
            ("hybrid_retrieve", "rerank"),
            ("rerank", "grade_relevance"),
            ("generate", "verify_grounding"),
        ],
    )
    def test_a_planned_edge_exists(self, compiled, source: str, target: str) -> None:  # type: ignore[no-untyped-def]
        assert any(edge.source == source and edge.target == target for edge in compiled.edges), (
            f"{source} -> {target}"
        )

    def test_the_guard_is_the_first_step(self, compiled) -> None:  # type: ignore[no-untyped-def]
        starts = [edge.target for edge in compiled.edges if edge.source == "__start__"]
        assert starts == ["guard_input"]

    def test_finalize_and_escalate_are_terminal_paths(self, compiled) -> None:  # type: ignore[no-untyped-def]
        outgoing = {edge.source for edge in compiled.edges}
        for terminal in ("finalize", "escalate"):
            assert terminal in outgoing or any(
                e.target == "__end__" and e.source == terminal for e in compiled.edges
            )
