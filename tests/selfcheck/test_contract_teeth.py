"""A contract that accepts everything proves nothing. Each test here feeds a deliberately broken
implementation to a contract check and requires the check to fail. If one starts passing, the contract
has lost its teeth.

Production adapters are resolved lazily (``need``), so a missing optional dependency skips these tests
instead of breaking collection for the whole run.
"""

from __future__ import annotations

import uuid

import pytest
from fakes.reranker import FakeCandidate, FakeScored
from fakes.retriever import FakeHit
from support.contracts import (
    MessageQueueContract,
    ObjectStoreContract,
    RerankerContract,
    RetrieverContract,
)
from support.contracts.retriever import Corpus
from support.specs import need

pytestmark = pytest.mark.selfcheck

#: What a failing contract check raises: a failed assertion, a failed pytest.fail, or an unexpected
#: value shape. Any of them proves the contract caught the broken implementation.
CONTRACT_FAILURES = (AssertionError, pytest.fail.Exception, ValueError)


def silently_empty_store():  # type: ignore[no-untyped-def]
    base = need("storage.memory")

    class SilentlyEmptyStore(base):  # type: ignore[valid-type,misc]
        async def get_object(
            self, key: str
        ) -> bytes:  # a missing key returns b"" instead of raising
            return self._storage[key][0] if key in self._storage else b""

    return SilentlyEmptyStore()


def forgetful_queue():  # type: ignore[no-untyped-def]
    base = need("queue.memory")

    class ForgetfulQueue(base):  # type: ignore[valid-type,misc]
        async def receive_messages(self, queue_name, max_messages=10, wait_time_seconds=10):  # type: ignore[no-untyped-def]
            return []  # never delivers anything

    return ForgetfulQueue()


class UnsortedReranker:
    name = "unsorted"

    async def rerank(
        self, query: str, candidates: list[FakeCandidate], *, top_n: int
    ) -> list[FakeScored]:
        return [FakeScored(c.chunk_id, float(i)) for i, c in enumerate(candidates)][
            :top_n
        ]  # ascending


class IgnoresTopN:
    name = "ignores_top_n"

    async def rerank(
        self, query: str, candidates: list[FakeCandidate], *, top_n: int
    ) -> list[FakeScored]:
        return [FakeScored(c.chunk_id, 1.0 - i * 0.1) for i, c in enumerate(candidates)]


class MutatingReranker:
    name = "mutating"

    async def rerank(
        self, query: str, candidates: list[FakeCandidate], *, top_n: int
    ) -> list[FakeScored]:
        candidates.reverse()  # changes the caller's list
        return [FakeScored(c.chunk_id, 1.0 - i * 0.1) for i, c in enumerate(candidates)][:top_n]


class LeakyRetriever:
    """Returns another tenant's rows: the most dangerous retriever bug there can be."""

    async def search(self, query: str, *, tenant_id: object, k: int, filters=None) -> list[FakeHit]:  # type: ignore[no-untyped-def]
        return [FakeHit("x", "doc", "other", 1.0, f"{query} from another tenant")][:k]


class TestContractsCatchBrokenImplementations:
    async def test_object_store_contract_catches_a_store_that_hides_missing_keys(self) -> None:
        check = ObjectStoreContract()
        with pytest.raises(CONTRACT_FAILURES):
            await check.test_missing_key_raises_the_documented_error(silently_empty_store())

    async def test_queue_contract_catches_a_queue_that_forgets_messages(self) -> None:
        check = MessageQueueContract()
        with pytest.raises(CONTRACT_FAILURES):
            await check.test_a_sent_dict_body_is_delivered_unchanged(forgetful_queue())

    async def test_reranker_contract_catches_an_unsorted_reranker(self) -> None:
        check = RerankerContract()
        with pytest.raises(CONTRACT_FAILURES):
            await check.test_scores_are_sorted_descending(UnsortedReranker())

    async def test_reranker_contract_catches_a_reranker_that_ignores_top_n(self) -> None:
        check = RerankerContract()
        with pytest.raises(CONTRACT_FAILURES):
            await check.test_top_n_limits_the_result(IgnoresTopN())

    async def test_reranker_contract_catches_mutation_of_the_input(self) -> None:
        check = RerankerContract()
        with pytest.raises(CONTRACT_FAILURES):
            await check.test_the_input_list_is_not_mutated(MutatingReranker())

    async def test_retriever_contract_catches_a_cross_tenant_leak(self) -> None:
        check = RetrieverContract()
        tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
        corpus = Corpus(LeakyRetriever(), tenant_a, tenant_b, "doc-a", "doc-b")
        with pytest.raises(CONTRACT_FAILURES):
            await check.test_another_tenant_never_sees_the_document(corpus)
