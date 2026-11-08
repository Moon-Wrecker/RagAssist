"""The reranker chain (ADR 0005): order from RERANKER_CHAIN, fall-through on failure and on timeout,
RRF order when everything fails, and the disabled switch."""

from __future__ import annotations

import time

from fakes.reranker import FakeCandidate, FakeReranker
from support.settings import make_settings
from support.specs import need

CANDIDATES = [
    FakeCandidate("c1", "billing invoice enterprise"),
    FakeCandidate("c2", "service account key rotation"),
    FakeCandidate("c3", "invoice history and billing email"),
]


def chain(instances: dict[str, FakeReranker], **settings: object):  # type: ignore[no-untyped-def]
    build = need("rerank.build_reranker_chain")
    return build(make_settings(**settings), instances=instances)


class TestOrderAndSelection:
    async def test_the_first_member_in_the_configured_order_answers(self) -> None:
        members = {"api": FakeReranker("api"), "flashrank": FakeReranker("flashrank")}
        result = await chain(members, RERANKER_CHAIN="api,flashrank,none").rerank(
            "billing invoice", CANDIDATES, top_n=2
        )
        assert result.reranker == "api"
        assert members["flashrank"].calls == 0

    async def test_the_chain_records_which_reranker_ran(self) -> None:
        members = {"flashrank": FakeReranker("flashrank")}
        result = await chain(members, RERANKER_CHAIN="flashrank,none").rerank(
            "billing", CANDIDATES, top_n=3
        )
        assert result.reranker == "flashrank"

    async def test_top_n_limits_the_result(self) -> None:
        members = {"flashrank": FakeReranker("flashrank")}
        result = await chain(members, RERANKER_CHAIN="flashrank,none").rerank(
            "billing", CANDIDATES, top_n=1
        )
        assert len(result.items) == 1

    async def test_the_default_chain_is_cross_encoder_then_flashrank_then_none(self) -> None:
        assert make_settings().RERANKER_CHAIN == "cross_encoder,flashrank,none"

    async def test_chain_keys_are_case_insensitive(self) -> None:
        members = {"flashrank": FakeReranker("flashrank")}
        result = await chain(members, RERANKER_CHAIN="FlashRank,None").rerank(
            "billing", CANDIDATES, top_n=3
        )
        assert result.reranker == "flashrank"


class TestFallThrough:
    async def test_a_missing_cross_encoder_falls_back_to_flashrank(self) -> None:
        """No torch or CUDA: the cross-encoder cannot load, so the chain moves on."""
        members = {
            "cross_encoder": FakeReranker(
                "cross_encoder", error=ImportError("torch is not installed")
            ),
            "flashrank": FakeReranker("flashrank"),
        }
        result = await chain(members, RERANKER_CHAIN="cross_encoder,flashrank,none").rerank(
            "billing", CANDIDATES, top_n=3
        )
        assert result.reranker == "flashrank"

    async def test_a_member_that_raises_is_skipped(self) -> None:
        members = {
            "api": FakeReranker("api", error=RuntimeError("503")),
            "flashrank": FakeReranker("flashrank"),
        }
        result = await chain(members, RERANKER_CHAIN="api,flashrank,none").rerank(
            "billing", CANDIDATES, top_n=3
        )
        assert result.reranker == "flashrank"

    async def test_a_slow_member_times_out_at_rerank_timeout_ms(self) -> None:
        members = {
            "cross_encoder": FakeReranker("cross_encoder", delay=2.0),
            "flashrank": FakeReranker("flashrank"),
        }
        started = time.monotonic()
        result = await chain(
            members, RERANKER_CHAIN="cross_encoder,flashrank,none", RERANK_TIMEOUT_MS=50
        ).rerank("billing", CANDIDATES, top_n=3)
        assert result.reranker == "flashrank"
        assert time.monotonic() - started < 1.5

    async def test_when_every_member_fails_the_rrf_order_is_kept(self) -> None:
        members = {
            "cross_encoder": FakeReranker("cross_encoder", error=RuntimeError("boom")),
            "flashrank": FakeReranker("flashrank", error=RuntimeError("boom")),
        }
        result = await chain(members, RERANKER_CHAIN="cross_encoder,flashrank").rerank(
            "billing", CANDIDATES, top_n=3
        )
        assert [item.chunk_id for item in result.items] == ["c1", "c2", "c3"]
        assert result.reranker in {"none", "rrf"}

    async def test_the_none_member_always_returns_the_input_order(self) -> None:
        result = await chain({}, RERANKER_CHAIN="none").rerank("anything", CANDIDATES, top_n=3)
        assert [item.chunk_id for item in result.items] == ["c1", "c2", "c3"]
        assert result.reranker == "none"


class TestDisabled:
    async def test_rerank_disabled_calls_no_member(self) -> None:
        members = {"flashrank": FakeReranker("flashrank")}
        result = await chain(members, RERANK_ENABLED=False, RERANKER_CHAIN="flashrank,none").rerank(
            "billing", CANDIDATES, top_n=3
        )
        assert members["flashrank"].calls == 0
        assert [item.chunk_id for item in result.items] == ["c1", "c2", "c3"]
        assert result.reranker == "none"

    async def test_empty_candidates_return_empty_without_calling_members(self) -> None:
        members = {"flashrank": FakeReranker("flashrank")}
        result = await chain(members, RERANKER_CHAIN="flashrank,none").rerank(
            "billing", [], top_n=3
        )
        assert result.items == []


class TestSettings:
    def test_timeout_default_matches_the_plan(self) -> None:
        assert make_settings().RERANK_TIMEOUT_MS == 1500

    def test_top_n_default_matches_the_retrieval_setting(self) -> None:
        assert make_settings().RETRIEVAL_TOP_N == 6
