"""Jev, OpenAI Decisions and Strands adapters, against an in-process fake server (respx; these
adapters use plain httpx). One contract suite and one wire-format suite run for all three."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import respx
from support.assertions import assert_probabilities
from support.contracts import DeciderContract
from support.contracts.decider import CHOICE, PREDICATE, SCORE
from support.settings import make_settings

from ragassist.platform.decisions.adapters.jev_adapter import JevAdapter
from ragassist.platform.decisions.adapters.openai_decisions_adapter import OpenAIDecisionsAdapter
from ragassist.platform.decisions.adapters.strands_adapter import StrandsDeciderAdapter
from ragassist.platform.decisions.ports import (
    ChoiceAnswer,
    Decider,
    PredicateAnswer,
    PredicateQuestion,
    ScoreAnswer,
)

JEV_URL = "https://jev.test/v1/decide"
OPENAI_BASE = "https://openai.test/v1"
STRANDS_URL = "http://strands.test/decide"


def _answer_for(question: dict[str, Any]) -> dict[str, Any]:
    """What a well-behaved decision server returns for one wire-format question."""
    kind = question["type"]
    if kind == "choice":
        options = question.get("options") or question["choices"]
        options = [o["value"] if isinstance(o, dict) else o for o in options]
        probs = {o: (0.7 if i == 0 else 0.3 / (len(options) - 1)) for i, o in enumerate(options)}
        return {
            "name": question["name"],
            "choice": options[0],
            "confidence": 0.7,
            "probabilities": probs,
        }
    if kind == "predicate":
        return {"name": question["name"], "probability": 0.9, "verdict": True}
    return {"name": question["name"], "score": 0.6, "confidence": 0.8}


@dataclass
class Wire:
    """Describes one adapter's HTTP dialect."""

    name: str
    factory: Callable[..., Decider]
    url: str
    text_key: str
    questions_key: str
    answers_key: str
    auth_header: str | None

    def mount(
        self, router: respx.MockRouter, *, answers: Callable[[list[dict]], list[dict]] | None = None
    ):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            questions = body[self.questions_key]
            produced = (answers or (lambda qs: [_answer_for(q) for q in qs]))(questions)
            return httpx.Response(200, json={self.answers_key: produced})

        return router.post(self.url).mock(side_effect=handler)


WIRES = [
    Wire(
        "jev",
        lambda **kw: JevAdapter(
            api_key="jev-key", endpoint=JEV_URL, settings=make_settings(), **kw
        ),
        JEV_URL,
        "text",
        "queries",
        "results",
        "Bearer jev-key",
    ),
    Wire(
        "openai_decisions",
        lambda **kw: OpenAIDecisionsAdapter(
            api_key="oai-key", base_url=OPENAI_BASE, settings=make_settings(), **kw
        ),
        f"{OPENAI_BASE}/decisions",
        "input",
        "questions",
        "answers",
        "Bearer oai-key",
    ),
    Wire(
        "strands_local",
        lambda **kw: StrandsDeciderAdapter(endpoint=STRANDS_URL, settings=make_settings(), **kw),
        STRANDS_URL,
        "input",
        "questions",
        "answers",
        None,
    ),
]
WIRE_IDS = [w.name for w in WIRES]


@pytest.fixture
def router():
    with respx.mock(assert_all_called=False) as r:
        yield r


@pytest.fixture(params=WIRES, ids=WIRE_IDS)
def wire(request, router) -> Wire:
    wire: Wire = request.param
    wire.mount(router)
    return wire


class TestHTTPDeciderContract(DeciderContract):
    @pytest.fixture
    def decider(self, wire: Wire) -> Decider:
        return wire.factory()


class TestWireFormat:
    async def test_posts_the_input_text_and_every_question_once(self, wire: Wire, router) -> None:
        await wire.factory().decide("hello world", [CHOICE, PREDICATE, SCORE])
        (call,) = router.calls
        body = json.loads(call.request.content)
        assert body[wire.text_key] == "hello world"
        assert [q["name"] for q in body[wire.questions_key]] == ["route", "safe", "relevance"]
        assert [q["type"] for q in body[wire.questions_key]] == ["choice", "predicate", "score"]

    async def test_choice_options_are_sent_in_order(self, wire: Wire, router) -> None:
        await wire.factory().evaluate_choice("x", CHOICE)
        sent = json.loads(router.calls.last.request.content)[wire.questions_key][0]
        options = sent.get("options") or sent["choices"]
        assert [o["value"] if isinstance(o, dict) else o for o in options] == CHOICE.choices

    async def test_authorisation_header(self, wire: Wire, router) -> None:
        await wire.factory().evaluate_predicate("x", PREDICATE)
        header = router.calls.last.request.headers.get("authorization")
        assert header == wire.auth_header

    async def test_empty_batch_makes_no_request(self, wire: Wire, router) -> None:
        assert await wire.factory().decide("x", []) == []
        assert router.calls.call_count == 0

    async def test_one_request_per_decide_call_regardless_of_question_count(
        self, wire: Wire, router
    ) -> None:
        questions = [PredicateQuestion(f"q{i}", "?") for i in range(25)]
        answers = await wire.factory().decide("x", questions)
        assert router.calls.call_count == 1
        assert [a.name for a in answers] == [q.name for q in questions]


class TestAnswerMapping:
    async def test_answers_are_matched_by_name_not_position(self, wire: Wire, router) -> None:
        router.reset()
        wire.mount(router, answers=lambda qs: [_answer_for(q) for q in reversed(qs)])
        answers = await wire.factory().decide("x", [CHOICE, PREDICATE, SCORE])
        assert [type(a) for a in answers] == [ChoiceAnswer, PredicateAnswer, ScoreAnswer]
        assert [a.name for a in answers] == ["route", "safe", "relevance"]

    async def test_server_values_are_passed_through(self, wire: Wire, router) -> None:
        router.reset()
        wire.mount(
            router,
            answers=lambda qs: [
                {
                    "name": "route",
                    "choice": "saas_action",
                    "confidence": 0.91,
                    "probabilities": {
                        "rag_search": 0.03,
                        "saas_action": 0.91,
                        "general_chat": 0.03,
                        "human_escalation": 0.03,
                    },
                },
                {"name": "safe", "probability": 0.12, "verdict": False},
                {"name": "relevance", "score": 0.4, "confidence": 0.66},
            ],
        )
        choice, predicate, score = await wire.factory().decide("x", [CHOICE, PREDICATE, SCORE])
        assert (choice.choice, choice.confidence) == ("saas_action", pytest.approx(0.91))
        assert (predicate.verdict, predicate.probability) == (False, pytest.approx(0.12))
        assert (score.score, score.confidence) == (pytest.approx(0.4), pytest.approx(0.66))

    async def test_predicate_verdict_defaults_to_probability_threshold(
        self, wire: Wire, router
    ) -> None:
        router.reset()
        wire.mount(router, answers=lambda qs: [{"name": q["name"], "probability": 0.2} for q in qs])
        answer = await wire.factory().evaluate_predicate("x", PREDICATE)
        assert answer.verdict is False

    async def test_a_missing_choice_answer_is_not_presented_as_confident(
        self, wire: Wire, router
    ) -> None:
        router.reset()
        wire.mount(router, answers=lambda qs: [])
        answer = await wire.factory().evaluate_choice("x", CHOICE)
        assert answer.confidence < 0.5, "an absent answer must not look confident"
        assert_probabilities(answer.probabilities)

    async def test_a_choice_outside_the_options_is_not_returned(self, wire: Wire, router) -> None:
        router.reset()
        wire.mount(
            router,
            answers=lambda qs: [
                {"name": q["name"], "choice": "bogus", "confidence": 0.9} for q in qs
            ],
        )
        answer = await wire.factory().evaluate_choice("x", CHOICE)
        assert answer.choice in CHOICE.choices


class TestFailureModes:
    @pytest.mark.parametrize("status", [401, 429, 500, 503])
    async def test_http_errors_raise_so_the_chain_can_fall_through(
        self, wire: Wire, router, status: int
    ) -> None:
        router.reset()
        router.post(wire.url).mock(return_value=httpx.Response(status))
        with pytest.raises(httpx.HTTPStatusError):
            await wire.factory().evaluate_choice("x", CHOICE)

    async def test_timeouts_raise(self, wire: Wire, router) -> None:
        router.reset()
        router.post(wire.url).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(httpx.TimeoutException):
            await wire.factory().evaluate_choice("x", CHOICE)

    async def test_connection_errors_raise(self, wire: Wire, router) -> None:
        router.reset()
        router.post(wire.url).mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(httpx.ConnectError):
            await wire.factory().evaluate_choice("x", CHOICE)

    async def test_non_json_body_raises_rather_than_returning_garbage(
        self, wire: Wire, router
    ) -> None:
        router.reset()
        router.post(wire.url).mock(return_value=httpx.Response(200, text="<html>gateway</html>"))
        with pytest.raises(ValueError):
            await wire.factory().evaluate_choice("x", CHOICE)

    async def test_configured_timeout_is_applied(self, wire: Wire, router) -> None:
        router.reset()
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.extensions["timeout"])
            return httpx.Response(
                200,
                json={
                    wire.answers_key: [
                        _answer_for(q) for q in json.loads(request.content)[wire.questions_key]
                    ]
                },
            )

        router.post(wire.url).mock(side_effect=handler)
        await wire.factory(timeout_seconds=0.25).evaluate_predicate("x", PREDICATE)
        assert seen["read"] == pytest.approx(0.25)


class TestProviderSpecifics:
    async def test_jev_uses_the_typesafe_key_from_settings_when_none_is_given(self, router) -> None:
        router.post(JEV_URL).mock(return_value=httpx.Response(200, json={"results": []}))
        adapter = JevAdapter(
            endpoint=JEV_URL, settings=make_settings(TYPESAFE_API_KEY="from-settings")
        )
        await adapter.evaluate_predicate("x", PREDICATE)
        assert router.calls.last.request.headers["authorization"] == "Bearer from-settings"

    @pytest.mark.parametrize(
        ("settings", "expected"),
        [
            ({"OPENAI_DECISIONS_API_KEY": "dec-key", "OPENAI_API_KEY": "chat-key"}, "dec-key"),
            ({"OPENAI_API_KEY": "chat-key"}, "chat-key"),
        ],
    )
    async def test_openai_decisions_key_precedence(self, router, settings, expected) -> None:
        router.post(f"{OPENAI_BASE}/decisions").mock(
            return_value=httpx.Response(200, json={"answers": []})
        )
        adapter = OpenAIDecisionsAdapter(base_url=OPENAI_BASE, settings=make_settings(**settings))
        await adapter.evaluate_predicate("x", PREDICATE)
        assert router.calls.last.request.headers["authorization"] == f"Bearer {expected}"

    async def test_openai_decisions_sends_the_model_and_tolerates_a_trailing_slash(
        self, router
    ) -> None:
        route = router.post(f"{OPENAI_BASE}/decisions").mock(
            return_value=httpx.Response(200, json={"answers": []})
        )
        adapter = OpenAIDecisionsAdapter(
            api_key="k", base_url=OPENAI_BASE + "/", model="decider-x", settings=make_settings()
        )
        await adapter.evaluate_predicate("x", PREDICATE)
        assert route.called
        assert json.loads(router.calls.last.request.content)["model"] == "decider-x"

    async def test_openai_decisions_sends_choices_as_value_objects_and_levels_with_labels(
        self, router
    ) -> None:
        router.post(f"{OPENAI_BASE}/decisions").mock(
            return_value=httpx.Response(200, json={"answers": []})
        )
        adapter = OpenAIDecisionsAdapter(
            api_key="k", base_url=OPENAI_BASE, settings=make_settings()
        )
        await adapter.decide("x", [CHOICE, SCORE])
        choice_q, score_q = json.loads(router.calls.last.request.content)["questions"]
        assert choice_q["choices"][0] == {"value": "rag_search"}
        assert score_q["levels"][0] == {"value": 1, "label": "low"}

    async def test_strands_endpoint_comes_from_settings(self, router) -> None:
        router.post("http://configured.test/decide").mock(
            return_value=httpx.Response(200, json={"answers": []})
        )
        adapter = StrandsDeciderAdapter(
            settings=make_settings(STRANDS_DECIDER_ENDPOINT="http://configured.test/decide")
        )
        await adapter.evaluate_predicate("x", PREDICATE)
        assert router.calls.call_count == 1

    async def test_openai_decisions_splits_batches_at_400_questions(self, router) -> None:
        route = router.post(f"{OPENAI_BASE}/decisions").mock(
            side_effect=lambda req: httpx.Response(
                200,
                json={"answers": [_answer_for(q) for q in json.loads(req.content)["questions"]]},
            )
        )
        adapter = OpenAIDecisionsAdapter(
            api_key="k", base_url=OPENAI_BASE, settings=make_settings()
        )
        questions = [PredicateQuestion(f"q{i}", "?") for i in range(401)]
        answers = await adapter.decide("x", questions)
        sizes = [len(json.loads(c.request.content)["questions"]) for c in route.calls]
        assert max(sizes) <= 400 and sum(sizes) == 401
        assert [a.name for a in answers] == [q.name for q in questions]
