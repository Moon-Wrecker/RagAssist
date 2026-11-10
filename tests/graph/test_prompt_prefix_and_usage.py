"""Provider prompt caching (ADR 0015): the fixed instructions come first and never vary, and cached-token usage is
recorded when the provider reports it."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from factories.principals import make_principal
from langchain_core.messages import AIMessageChunk, SystemMessage
from support.graph_harness import TENANT_A, make_graph, make_kit, run_turn

from ragassist.modules.assistant.graph.nodes.generate_node import (
    SYSTEM_PROMPT_CHAT,
    SYSTEM_PROMPT_GROUNDED,
)
from ragassist.modules.assistant.graph.usage import UsageTally
from ragassist.shared.observability.metrics import get_metrics_registry
from ragassist.shared.security.jwt import UserRole

pytestmark = pytest.mark.graph


async def ask(kit, question: str) -> list:  # type: ignore[no-untyped-def]
    graph = make_graph(kit)
    principal = make_principal(role=UserRole.USER, tenant_id=TENANT_A)
    await run_turn(graph, question=question, principal=principal, conversation_id=question[:8])
    return kit.strong.calls[-1]


class TestStaticPrefixFirst:
    async def test_the_fixed_instructions_are_the_first_message_and_do_not_vary(self) -> None:
        kit = make_kit()
        first = await ask(kit, "When are invoices issued?")
        second = await ask(kit, "Are invoices issued on the first day?")
        assert isinstance(first[0], SystemMessage) and isinstance(second[0], SystemMessage)
        assert first[0].content == second[0].content == SYSTEM_PROMPT_GROUNDED

    async def test_everything_that_varies_comes_after_the_system_message(self) -> None:
        kit = make_kit()
        messages = await ask(kit, "When are invoices issued?")
        assert "invoices" not in str(messages[0].content).lower()
        assert "When are invoices issued?" in str(messages[-1].content)
        assert str(messages[-1].content).rstrip().endswith("When are invoices issued?")

    def test_the_system_prompts_hold_no_placeholders(self) -> None:
        for prompt in (SYSTEM_PROMPT_GROUNDED, SYSTEM_PROMPT_CHAT):
            assert "{" not in prompt and "}" not in prompt

    async def test_passages_stay_delimited_as_untrusted_data(self) -> None:
        kit = make_kit()
        messages = await ask(kit, "When are invoices issued?")
        assert "<untrusted_document_context>" in str(messages[-1].content)


def chunk(input_tokens: int, cached: int | None) -> AIMessageChunk:
    details = {"cache_read": cached} if cached is not None else {}
    return AIMessageChunk(
        content="x",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": 5,
            "total_tokens": input_tokens + 5,
            "input_token_details": details,
        },
    )


def counter(cached: str) -> float:
    series = get_metrics_registry()._counters["ragassist_llm_input_tokens_total"]
    return series.get((("cached", cached),), 0.0)


class TestUsageTally:
    def test_cached_tokens_are_summed_and_counted(self) -> None:
        before_true, before_false = counter("true"), counter("false")
        tally = UsageTally()
        tally.add(chunk(1200, 1024))
        tally.record("some-model")
        assert counter("true") - before_true == 1024
        assert counter("false") - before_false == 176

    def test_no_usage_records_nothing(self) -> None:
        before_true, before_false = counter("true"), counter("false")
        tally = UsageTally()
        tally.add(SimpleNamespace(content="x"))  # a provider that streams no usage
        tally.add(AIMessageChunk(content="y"))
        tally.record("some-model")
        assert (counter("true"), counter("false")) == (before_true, before_false)

    def test_cached_never_exceeds_the_input(self) -> None:
        before_true = counter("true")
        tally = UsageTally()
        tally.add(chunk(10, 50))
        tally.record("m")
        assert counter("true") - before_true == 10
