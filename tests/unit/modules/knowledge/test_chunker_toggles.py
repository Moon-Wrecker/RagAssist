"""Configuration toggles of the hybrid chunker: settings wiring, merge-peers, parent-child (small to big)
and semantic boundary refinement (ADR 0003, implementation plan section 4).

The hybrid chunker does not yet return ChunkDraft objects (DEFECT-34), so these run as expected failures
until it does.
"""

from __future__ import annotations

import re

import pytest
from fakes.tokens import WhitespaceCounter
from support.knowledge_builders import block, parsed_document
from support.settings import make_settings
from support.specs import need

COUNTER = WhitespaceCounter()


def normalised(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def long_document():  # type: ignore[no-untyped-def]
    return parsed_document(
        [
            block("paragraph", " ".join(f"p{i}w{j}" for j in range(30)), ("Billing", "Invoices"))
            for i in range(6)
        ]
    )


class _KeywordEmbedder:
    """Synchronous stand-in for a semantic embedder: one dimension per letter, unit length."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * 26
            for ch in text.lower():
                if "a" <= ch <= "z":
                    vec[ord(ch) - ord("a")] += 1.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out


class TestSettingsWiring:
    def test_from_settings_reads_the_chunk_budget(self) -> None:
        built = need("knowledge.chunker.hybrid").from_settings(
            make_settings(CHUNK_MAX_TOKENS=20, CHUNK_OVERLAP_TOKENS=0), COUNTER
        )
        doc = long_document()
        for chunk in built.chunk(doc, title=doc.title):
            assert COUNTER.count(chunk.text) <= 20

    def test_from_settings_reads_the_overlap(self) -> None:
        built = need("knowledge.chunker.hybrid").from_settings(
            make_settings(CHUNK_MAX_TOKENS=20, CHUNK_OVERLAP_TOKENS=5), COUNTER
        )
        assert built.overlap_tokens == 5

    def test_the_default_strategy_is_hybrid(self) -> None:
        assert make_settings().CHUNK_STRATEGY == "hybrid"


class TestMergePeers:
    def test_merging_produces_fewer_larger_chunks(self) -> None:
        cls = need("knowledge.chunker.hybrid")
        doc = parsed_document([block("paragraph", "one two three", ("S",)) for _ in range(4)])
        merged = cls(max_tokens=40, overlap_tokens=0, merge_peers=True, tokenizer=COUNTER).chunk(
            doc, title=doc.title
        )
        separate = cls(max_tokens=40, overlap_tokens=0, merge_peers=False, tokenizer=COUNTER).chunk(
            doc, title=doc.title
        )
        assert len(merged) < len(separate)

    def test_without_merging_each_peer_is_its_own_chunk(self) -> None:
        cls = need("knowledge.chunker.hybrid")
        doc = parsed_document(
            [block("paragraph", "alpha beta", ("S",)), block("paragraph", "gamma delta", ("S",))]
        )
        assert (
            len(
                cls(max_tokens=40, overlap_tokens=0, merge_peers=False, tokenizer=COUNTER).chunk(
                    doc, title=doc.title
                )
            )
            == 2
        )


class TestParentChild:
    def make(self):  # type: ignore[no-untyped-def]
        return need("knowledge.chunker.hybrid")(
            max_tokens=12, overlap_tokens=0, merge_peers=True, tokenizer=COUNTER, parent_child=True
        )

    def test_children_point_at_a_parent(self) -> None:
        doc = long_document()
        assert any(c.parent is not None for c in self.make().chunk(doc, title=doc.title))

    def test_each_parent_contains_its_children_text(self) -> None:
        doc = long_document()
        chunks = self.make().chunk(doc, title=doc.title)
        for chunk in chunks:
            if chunk.parent is not None:
                assert normalised(chunk.text) in normalised(chunks[chunk.parent].text)

    def test_parents_are_larger_than_children(self) -> None:
        doc = long_document()
        chunks = self.make().chunk(doc, title=doc.title)
        for chunk in chunks:
            if chunk.parent is not None:
                assert COUNTER.count(chunks[chunk.parent].text) > COUNTER.count(chunk.text)

    def test_parent_child_is_off_by_default(self) -> None:
        cls = need("knowledge.chunker.hybrid")
        doc = long_document()
        chunks = cls(max_tokens=12, overlap_tokens=0, merge_peers=True, tokenizer=COUNTER).chunk(
            doc, title=doc.title
        )
        assert all(c.parent is None for c in chunks)

    def test_the_setting_turns_parent_child_on(self) -> None:
        built = need("knowledge.chunker.hybrid").from_settings(
            make_settings(CHUNK_PARENT_CHILD=True, CHUNK_MAX_TOKENS=12), COUNTER
        )
        doc = long_document()
        assert any(c.parent is not None for c in built.chunk(doc, title=doc.title))


class TestSemanticRefinement:
    def test_semantic_mode_keeps_the_budget_and_the_coverage(self) -> None:
        chunker = need("knowledge.chunker.hybrid")(
            max_tokens=20,
            overlap_tokens=0,
            merge_peers=True,
            tokenizer=COUNTER,
            semantic=True,
            semantic_embedder=_KeywordEmbedder(),
        )
        doc = long_document()
        chunks = chunker.chunk(doc, title=doc.title)
        assert all(COUNTER.count(c.text) <= 20 for c in chunks)
        covered = " ".join(c.text for c in chunks).split()
        assert sorted(covered) == sorted(" ".join(b.text for b in doc.blocks).split())

    def test_semantic_mode_without_an_embedder_is_a_configuration_error(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            need("knowledge.chunker.hybrid")(
                max_tokens=20, overlap_tokens=0, merge_peers=True, tokenizer=COUNTER, semantic=True
            )

    def test_semantic_is_off_by_default(self) -> None:
        assert make_settings().CHUNK_SEMANTIC is False
