"""ContextBuilder (plan section 9, retrieval): de-duplication, token budget, score order and citation
metadata that the answer needs for its [n] references."""

from __future__ import annotations

from fakes.retriever import FakeHit
from fakes.tokens import WhitespaceCounter
from support.specs import need

COUNTER = WhitespaceCounter()


def hit(
    chunk_id: str,
    text: str,
    score: float,
    *,
    title: str = "Billing guide",
    page: int | None = 1,
    heading_path: tuple[str, ...] = ("Invoices",),
    document_id: str = "doc-1",
) -> FakeHit:
    return FakeHit(chunk_id, document_id, None, score, text, heading_path, page, title)


def builder(budget: int = 60):  # type: ignore[no-untyped-def]
    return need("retrieval.ContextBuilder")(tokenizer=COUNTER, budget_tokens=budget)


class TestBudget:
    def test_the_passages_fit_the_token_budget(self) -> None:
        hits = [hit(f"c{i}", " ".join(["word"] * 10), 1.0 - i / 10) for i in range(5)]
        pack = builder(budget=25).build(hits)
        assert sum(COUNTER.count(p.text) for p in pack.passages) <= 25

    def test_a_large_budget_keeps_every_hit(self) -> None:
        hits = [hit(f"c{i}", "short text", 1.0 - i / 10) for i in range(3)]
        assert len(builder(budget=1000).build(hits).passages) == 3

    def test_a_single_hit_bigger_than_the_budget_is_not_over_stuffed(self) -> None:
        pack = builder(budget=5).build([hit("big", " ".join(["w"] * 50), 1.0)])
        assert sum(COUNTER.count(p.text) for p in pack.passages) <= 5

    def test_an_empty_hit_list_gives_an_empty_pack(self) -> None:
        assert builder().build([]).passages == []


class TestDeduplication:
    def test_the_same_chunk_id_appears_once(self) -> None:
        pack = builder().build([hit("c1", "same", 0.9), hit("c1", "same", 0.8)])
        assert [p.chunk_id for p in pack.passages] == ["c1"]

    def test_identical_text_from_two_chunks_appears_once(self) -> None:
        pack = builder().build(
            [hit("c1", "identical words", 0.9), hit("c2", "identical words", 0.8)]
        )
        assert len(pack.passages) == 1


class TestOrderAndCitations:
    def test_passages_are_ordered_by_score_descending(self) -> None:
        pack = builder().build([hit("low", "a", 0.1), hit("high", "b", 0.9), hit("mid", "c", 0.5)])
        assert [p.chunk_id for p in pack.passages] == ["high", "mid", "low"]

    def test_each_passage_keeps_its_citation_metadata(self) -> None:
        pack = builder().build(
            [
                hit(
                    "c1",
                    "text",
                    0.9,
                    title="Billing guide",
                    page=3,
                    heading_path=("Invoices", "Prices"),
                )
            ]
        )
        citation = pack.passages[0].citation
        assert (citation.title, citation.page, citation.heading_path) == (
            "Billing guide",
            3,
            ("Invoices", "Prices"),
        )

    def test_the_passage_text_is_the_raw_text_not_the_context_prefix(self) -> None:
        pack = builder().build([hit("c1", "Invoices are monthly.", 0.9)])
        assert pack.passages[0].text == "Invoices are monthly."

    def test_a_missing_page_is_kept_as_none(self) -> None:
        pack = builder().build([hit("c1", "markdown has no pages", 0.9, page=None)])
        assert pack.passages[0].citation.page is None
