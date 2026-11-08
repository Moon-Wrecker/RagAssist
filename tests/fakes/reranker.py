"""Scriptable reranker double. Scores are the share of query terms a candidate contains, so ordering
is predictable. ``delay``, ``error`` and ``fail_times`` simulate slow and failing rerankers for the
chain tests. Checked against ``RerankerContract`` in tests/selfcheck."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class FakeCandidate:
    chunk_id: str
    text: str
    score: float = 0.0


@dataclass(frozen=True)
class FakeScored:
    chunk_id: str
    score: float


class FakeReranker:
    def __init__(
        self,
        name: str = "fake",
        *,
        delay: float = 0.0,
        error: BaseException | None = None,
        fail_times: int | None = None,
    ) -> None:
        self._name = name
        self.delay = delay
        self.error = error
        self.fail_times = fail_times
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def rerank(
        self, query: str, candidates: list[FakeCandidate], *, top_n: int
    ) -> list[FakeScored]:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None and (self.fail_times is None or self.calls <= self.fail_times):
            raise self.error
        if top_n <= 0 or not candidates:
            return []
        terms = set(query.lower().split())
        scored = [
            FakeScored(
                c.chunk_id,
                (len(terms & set(c.text.lower().split())) / len(terms)) if terms else 0.0,
            )
            for c in candidates
        ]
        scored.sort(key=lambda item: (-item.score, item.chunk_id))
        return scored[:top_n]
