"""The five hybrid-chunking passes (ADR 0003), each tested on its own with the domain's Block objects.

The passes are pure functions, so each test states the input and the exact shape it expects. Tokens are
whitespace words (fakes/tokens.py).
"""

from __future__ import annotations

from fakes.tokens import WhitespaceCounter
from support.knowledge_builders import block, parsed_document
from support.specs import need

COUNTER = WhitespaceCounter()


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def sentences(count: int, words_each: int) -> str:
    return " ".join(f"{words(words_each, f's{i}_')}." for i in range(count))


class TestPass1Structure:
    def test_one_block_per_logical_element(self) -> None:
        out = need("knowledge.pass.structure")(
            parsed_document(
                [
                    block("heading", "Invoices", ("Invoices",)),
                    block("paragraph", "First paragraph.", ("Invoices",), 1),
                    block("table", "| a | b |", ("Invoices",), 1),
                    block("code", "x = 1", ("Invoices", "Examples")),
                ]
            )
        )
        assert [b.kind for b in out] == ["heading", "paragraph", "table", "code"]

    def test_heading_paths_are_kept_on_every_block(self) -> None:
        (only,) = need("knowledge.pass.structure")(
            parsed_document([block("paragraph", "Body.", ("A", "B"))])
        )
        assert tuple(only.heading_path) == ("A", "B")

    def test_document_order_is_preserved(self) -> None:
        texts = ["one.", "two.", "three."]
        out = need("knowledge.pass.structure")(
            parsed_document([block("paragraph", t) for t in texts])
        )
        assert [b.text for b in out] == texts

    def test_empty_blocks_are_dropped(self) -> None:
        out = need("knowledge.pass.structure")(
            parsed_document([block("paragraph", "   "), block("paragraph", "kept.")])
        )
        assert [b.text for b in out] == ["kept."]

    def test_an_empty_document_gives_no_blocks(self) -> None:
        assert need("knowledge.pass.structure")(parsed_document([])) == []


class TestPass2TokenSplit:
    def test_a_block_within_budget_is_unchanged(self) -> None:
        (out,) = need("knowledge.pass.token")(
            [block("paragraph", words(5), ("S",))], max_tokens=20, tokenizer=COUNTER
        )
        assert out.text == words(5)

    def test_an_oversized_block_is_split_into_parts_within_budget(self) -> None:
        parts = need("knowledge.pass.token")(
            [block("paragraph", words(60))], max_tokens=20, tokenizer=COUNTER
        )
        assert len(parts) >= 3 and all(COUNTER.count(p.text) <= 20 for p in parts)

    def test_splitting_loses_no_words_and_keeps_their_order(self) -> None:
        parts = need("knowledge.pass.token")(
            [block("paragraph", words(60))], max_tokens=20, tokenizer=COUNTER
        )
        assert " ".join(p.text for p in parts).split() == words(60).split()

    def test_splits_fall_on_sentence_boundaries_when_possible(self) -> None:
        parts = need("knowledge.pass.token")(
            [block("paragraph", sentences(6, 8))], max_tokens=20, tokenizer=COUNTER
        )
        assert all(p.text.endswith(".") for p in parts)

    def test_a_single_sentence_longer_than_the_budget_is_still_bounded(self) -> None:
        parts = need("knowledge.pass.token")(
            [block("paragraph", words(50))], max_tokens=10, tokenizer=COUNTER
        )
        assert all(COUNTER.count(p.text) <= 10 for p in parts)

    def test_split_parts_keep_the_heading_path(self) -> None:
        parts = need("knowledge.pass.token")(
            [block("paragraph", words(40), ("Billing", "Invoices"))],
            max_tokens=10,
            tokenizer=COUNTER,
        )
        assert all(tuple(p.heading_path) == ("Billing", "Invoices") for p in parts)


class TestPass3Merge:
    def test_small_prose_siblings_under_one_heading_are_merged(self) -> None:
        source = [
            block("paragraph", words(5, "a"), ("S",)),
            block("paragraph", words(5, "b"), ("S",)),
            block("paragraph", words(5, "c"), ("S",)),
        ]
        assert len(need("knowledge.pass.merge")(source, max_tokens=20, tokenizer=COUNTER)) == 1

    def test_merging_never_exceeds_the_budget(self) -> None:
        source = [
            block("paragraph", words(12, "a"), ("S",)),
            block("paragraph", words(12, "b"), ("S",)),
            block("paragraph", words(12, "c"), ("S",)),
        ]
        merged = need("knowledge.pass.merge")(source, max_tokens=20, tokenizer=COUNTER)
        assert len(merged) == 3 and all(COUNTER.count(m.text) <= 20 for m in merged)

    def test_blocks_under_different_headings_are_never_merged(self) -> None:
        source = [block("paragraph", "x y", ("A",)), block("paragraph", "p q", ("B",))]
        assert len(need("knowledge.pass.merge")(source, max_tokens=20, tokenizer=COUNTER)) == 2

    def test_a_table_is_not_merged_with_prose(self) -> None:
        source = [block("paragraph", "prose words", ("S",)), block("table", "| a |", ("S",))]
        merged = need("knowledge.pass.merge")(source, max_tokens=50, tokenizer=COUNTER)
        assert [m.kind for m in merged] == ["paragraph", "table"]

    def test_merge_keeps_document_order(self) -> None:
        source = [block("paragraph", "first", ("S",)), block("paragraph", "second", ("S",))]
        merged = need("knowledge.pass.merge")(source, max_tokens=20, tokenizer=COUNTER)
        assert merged[0].text.index("first") < merged[0].text.index("second")


class TestPass4TableProtection:
    def test_a_table_that_fits_stays_whole(self) -> None:
        table = block("table", "| a | b |\n|---|---|\n| 1 | 2 |", ("S",))
        out = need("knowledge.pass.table")([table], max_tokens=40, tokenizer=COUNTER)
        assert len(out) == 1 and out[0].text == table.text

    def test_an_oversized_table_is_split_by_rows(self) -> None:
        rows = "\n".join(f"| r{i} | v{i} |" for i in range(30))
        out = need("knowledge.pass.table")(
            [block("table", "| name | value |\n|---|---|\n" + rows, ("S",))],
            max_tokens=20,
            tokenizer=COUNTER,
        )
        assert len(out) > 1

    def test_every_part_of_a_split_table_repeats_the_header(self) -> None:
        rows = "\n".join(f"| r{i} | v{i} |" for i in range(30))
        out = need("knowledge.pass.table")(
            [block("table", "| name | value |\n|---|---|\n" + rows, ("S",))],
            max_tokens=20,
            tokenizer=COUNTER,
        )
        assert all(part.text.splitlines()[0] == "| name | value |" for part in out)

    def test_no_data_row_is_lost_when_a_table_is_split(self) -> None:
        rows = [f"| r{i} | v{i} |" for i in range(30)]
        out = need("knowledge.pass.table")(
            [block("table", "| name | value |\n|---|---|\n" + "\n".join(rows), ("S",))],
            max_tokens=20,
            tokenizer=COUNTER,
        )
        seen = [line for part in out for line in part.text.splitlines() if line.startswith("| r")]
        assert seen == rows

    def test_non_table_blocks_pass_through_untouched(self) -> None:
        prose = block("paragraph", "just prose here", ("S",))
        (out,) = need("knowledge.pass.table")([prose], max_tokens=20, tokenizer=COUNTER)
        assert out.text == prose.text


class TestPass5ContextHeader:
    def test_embed_text_starts_with_the_document_and_section(self) -> None:
        out = need("knowledge.pass.context")(
            [block("paragraph", "Invoices are monthly.", ("Billing", "Invoices"))],
            title="Billing guide",
        )
        assert out[0].embed_text.startswith(
            "[Document: Billing guide | Section: Billing > Invoices]"
        )

    def test_the_raw_text_is_kept_for_citations(self) -> None:
        out = need("knowledge.pass.context")(
            [block("paragraph", "Invoices are monthly.", ("Billing",))], title="G"
        )
        assert out[0].text == "Invoices are monthly."

    def test_a_block_without_a_heading_gets_only_the_document_title(self) -> None:
        out = need("knowledge.pass.context")([block("paragraph", "Loose text.")], title="Guide")
        assert out[0].embed_text.startswith("[Document: Guide")
        assert "Section:" not in out[0].embed_text

    def test_the_heading_path_is_carried_on_the_output(self) -> None:
        out = need("knowledge.pass.context")([block("paragraph", "x", ("A", "B"))], title="G")
        assert tuple(out[0].heading_path) == ("A", "B")
