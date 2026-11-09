"""Token counting for chunkers and context builders: one token per whitespace-separated word.

Production uses the embedding model's tokenizer. Tests inject this counter so budgets are exact and
easy to reason about. The chunker suites never depend on a real tokenizer."""

from __future__ import annotations


class WhitespaceCounter:
    def count(self, text: str) -> int:
        return len(text.split())

    def encode(self, text: str) -> list[str]:
        return text.split()
