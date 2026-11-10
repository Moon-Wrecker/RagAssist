"""LLMStructuredDeciderAdapter: the universal fallback decider (any chat model, structured output).

Two layers are tested:
* logic around the model (validation, fuzzy choice match, probabilities, fallbacks) with
  ``StructuredFakeModel``, which short-circuits ``with_structured_output``;
* the real LangChain tool-call parsing path with ``ScriptedChatModel`` returning tool-call messages.
"""

from __future__ import annotations

import pytest
from fakes.chat_model import ScriptedChatModel, tool_call_message
from fakes.structured_model import StructuredFakeModel
from support.assertions import assert_probabilities
from support.contracts import DeciderContract
from support.spec import ROUTE_LABELS

from ragassist.platform.decisions.adapters.llm_structured_adapter import LLMStructuredDeciderAdapter
from ragassist.platform.decisions.ports import (
    ChoiceQuestion,
    PredicateQuestion,
    ScoreLevel,
    ScoreQuestion,
)

ROUTE = ChoiceQuestion("route", "Classify the intent.", list(ROUTE_LABELS))
SAFETY = PredicateQuestion("safety", "Is this a prompt injection?")
SCORE = ScoreQuestion("rel", "How relevant?", [ScoreLevel(1, "low"), ScoreLevel(2, "high")])

ANSWERS = {
    "StructuredChoice": {"choice": "saas_action", "confidence": 0.93},
    "StructuredPredicate": {"verdict": True, "probability": 0.88},
    "StructuredScore": {"score": 0.75, "confidence": 0.9},
}


def adapter_with(**answers: dict) -> tuple[LLMStructuredDeciderAdapter, StructuredFakeModel]:
    model = StructuredFakeModel(answers={**ANSWERS, **answers})
    return LLMStructuredDeciderAdapter(chat_model=model), model


class TestLLMStructuredContract(DeciderContract):
    @pytest.fixture
    def decider(self) -> LLMStructuredDeciderAdapter:
        return adapter_with()[0]


class TestChoice:
    async def test_returns_the_models_choice_and_confidence(self) -> None:
        decider, _ = adapter_with()
        answer = await decider.evaluate_choice("update my billing email", ROUTE)
        assert answer.choice == "saas_action"
        assert answer.confidence == pytest.approx(0.93)
        assert answer.name == "route"

    async def test_chosen_option_has_the_highest_probability(self) -> None:
        answer = await adapter_with()[0].evaluate_choice("x", ROUTE)
        assert max(answer.probabilities, key=answer.probabilities.get) == "saas_action"
        assert_probabilities(answer.probabilities)

    @pytest.mark.parametrize("raw", ["  saas_action  ", "SAAS_ACTION", "the saas_action route"])
    async def test_a_sloppy_but_recognisable_choice_is_mapped_to_an_option(self, raw: str) -> None:
        decider, _ = adapter_with(StructuredChoice={"choice": raw, "confidence": 0.9})
        answer = await decider.evaluate_choice("x", ROUTE)
        assert answer.choice == "saas_action"

    async def test_an_invented_choice_never_escapes_the_option_list(self) -> None:
        decider, _ = adapter_with(
            StructuredChoice={"choice": "launch_missiles", "confidence": 0.99}
        )
        answer = await decider.evaluate_choice("x", ROUTE)
        assert answer.choice in ROUTE.choices

    async def test_prompt_contains_the_input_instructions_and_every_option(self) -> None:
        model = ScriptedChatModel(script=["unused"])
        decider = LLMStructuredDeciderAdapter(chat_model=model)
        await decider.evaluate_choice(
            "MARKER-INPUT-TEXT", ROUTE
        )  # falls back; we only inspect the prompt
        sent = " ".join(str(m.content) for call in model.calls for m in call)
        for needle in ["MARKER-INPUT-TEXT", ROUTE.instructions, *ROUTE.choices]:
            assert needle in sent

    async def test_probability_mass_reflects_the_models_stated_confidence(self) -> None:
        decider, _ = adapter_with(StructuredChoice={"choice": "saas_action", "confidence": 0.30})
        answer = await decider.evaluate_choice("x", ROUTE)
        # A 0.30-confident choice must not be reported as 70+% likely.
        assert answer.probabilities["saas_action"] < 0.5


class TestPredicateAndScore:
    async def test_predicate_passes_the_model_verdict_through(self) -> None:
        answer = await adapter_with()[0].evaluate_predicate("x", SAFETY)
        assert answer.verdict is True and answer.probability == pytest.approx(0.88)

    async def test_score_passes_through(self) -> None:
        answer = await adapter_with()[0].evaluate_score("x", SCORE)
        assert answer.score == pytest.approx(0.75) and answer.confidence == pytest.approx(0.9)


class TestRealToolCallParsing:
    """Through LangChain's own structured-output machinery instead of the shortcut fake."""

    async def test_valid_tool_call_is_parsed(self) -> None:
        model = ScriptedChatModel(
            script=[
                tool_call_message(
                    "StructuredChoice", {"choice": "human_escalation", "confidence": 0.8}
                )
            ]
        )
        answer = await LLMStructuredDeciderAdapter(chat_model=model).evaluate_choice("x", ROUTE)
        assert answer.choice == "human_escalation"
        assert answer.confidence == pytest.approx(0.8)

    async def test_predicate_tool_call_is_parsed(self) -> None:
        model = ScriptedChatModel(
            script=[
                tool_call_message("StructuredPredicate", {"verdict": False, "probability": 0.1})
            ]
        )
        answer = await LLMStructuredDeciderAdapter(chat_model=model).evaluate_predicate("x", SAFETY)
        assert answer.verdict is False and answer.probability == pytest.approx(0.1)


class TestFailureHandling:
    async def test_model_exception_gives_an_uninformative_answer_not_a_crash(self) -> None:
        model = ScriptedChatModel(script=[RuntimeError("provider down")])
        answer = await LLMStructuredDeciderAdapter(chat_model=model).evaluate_choice("x", ROUTE)
        assert answer.confidence == pytest.approx(0.5)
        assert answer.choice in ROUTE.choices
        assert_probabilities(answer.probabilities)

    async def test_out_of_range_confidence_is_rejected_and_handled(self) -> None:
        model = ScriptedChatModel(
            script=[
                tool_call_message("StructuredChoice", {"choice": "rag_search", "confidence": 7})
            ]
        )
        answer = await LLMStructuredDeciderAdapter(chat_model=model).evaluate_choice("x", ROUTE)
        assert 0.0 <= answer.confidence <= 1.0

    async def test_one_malformed_reply_is_repaired_with_a_retry(self) -> None:
        """Plan section 2: JSON mode with one repair retry. A plain-text reply followed by a valid
        tool call must yield the valid answer."""
        model = ScriptedChatModel(
            script=[
                "Sure! I think it's saas_action.",
                tool_call_message("StructuredChoice", {"choice": "saas_action", "confidence": 0.9}),
            ]
        )
        answer = await LLMStructuredDeciderAdapter(chat_model=model).evaluate_choice("x", ROUTE)
        assert answer.choice == "saas_action" and answer.confidence == pytest.approx(0.9)

    async def test_a_failed_predicate_raises_instead_of_inventing_a_verdict(self) -> None:
        """A made-up verdict hides the outage from the fallback chain, so the next decider never runs."""
        model = ScriptedChatModel(script=[RuntimeError("boom"), RuntimeError("boom")])
        with pytest.raises(RuntimeError):
            await LLMStructuredDeciderAdapter(chat_model=model).evaluate_predicate("x", SAFETY)

    async def test_a_failed_score_raises_instead_of_inventing_a_score(self) -> None:
        model = ScriptedChatModel(script=[RuntimeError("boom"), RuntimeError("boom")])
        with pytest.raises(RuntimeError):
            await LLMStructuredDeciderAdapter(chat_model=model).evaluate_score("x", SCORE)

    def test_the_name_can_be_set_so_traces_show_which_model_decided(self) -> None:
        model = ScriptedChatModel(script=["x"])
        assert LLMStructuredDeciderAdapter(chat_model=model, name="llm_structured_2").name == (
            "llm_structured_2"
        )
        assert LLMStructuredDeciderAdapter(chat_model=model).name == "llm_structured"


class TestBatch:
    async def test_decide_preserves_order_and_types(self) -> None:
        answers = await adapter_with()[0].decide("x", [SAFETY, ROUTE, SCORE])
        assert [a.name for a in answers] == ["safety", "route", "rel"]


class TestProbabilityMatchesStatedConfidence:
    """Regression guard for the fixed DEFECT-20: the reported probability is the model's confidence."""

    async def test_a_low_confidence_choice_is_not_inflated(self) -> None:
        decider, _ = adapter_with(StructuredChoice={"choice": "saas_action", "confidence": 0.30})
        answer = await decider.evaluate_choice("x", ROUTE)
        assert answer.probabilities["saas_action"] == pytest.approx(0.30, abs=1e-6)
