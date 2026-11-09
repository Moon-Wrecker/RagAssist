"""Tracing redacts credentials before export, costs nothing when off, and traces a turn when on.

Key-shaped samples are generated at run time (the repository bans key-shaped literals, tests included).
"""

from __future__ import annotations

import json
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from ragassist.shared.observability import tracing
from ragassist.shared.observability.tracing import (
    REDACTED,
    Tracing,
    TurnContext,
    build_tracing,
    redact,
)


def _jwt() -> str:
    return ".".join("eyJ" + secrets.token_hex(12) for _ in range(3))


@dataclass(frozen=True)
class FakePrincipal:
    user_id: str
    raw_token: str


class TestRedact:
    def test_a_secret_named_key_is_redacted_whatever_its_value(self) -> None:
        value = secrets.token_urlsafe(8)
        out = redact({"raw_token": value, "api_key": value, "Authorization": value, "name": "ada"})
        assert out == {
            "raw_token": REDACTED,
            "api_key": REDACTED,
            "Authorization": REDACTED,
            "name": "ada",
        }

    def test_a_credential_inside_free_text_is_redacted(self) -> None:
        token = _jwt()
        out = redact(f"the header was Bearer {token} and the session {token}")
        assert token not in out and REDACTED in out

    def test_provider_keys_in_text_are_redacted(self) -> None:
        text = (
            "use "
            + "sk-"
            + "proj-"
            + secrets.token_hex(24)
            + " or "
            + "AIza"
            + secrets.token_hex(18)
        )
        assert redact(text).count(REDACTED) == 2

    def test_nested_structures_and_dataclasses_are_walked(self) -> None:
        token = _jwt()
        principal = FakePrincipal(user_id="u1", raw_token=token)
        out = redact(
            {"input": {"principal": principal, "messages": [{"content": f"Bearer {token}"}]}}
        )
        assert token not in json.dumps(out)
        assert out["input"]["principal"]["user_id"] == "u1"

    def test_token_counts_and_ordinary_text_are_left_alone(self) -> None:
        data = {"max_tokens": 512, "usage": {"total_tokens": 9}, "text": "reset my password please"}
        assert redact(data) == data

    def test_an_empty_secret_stays_empty(self) -> None:
        assert redact({"raw_token": ""}) == {"raw_token": ""}


class TestMaskOtelSpans:
    def test_attributes_are_redacted_and_others_untouched(self) -> None:
        pytest.importorskip("langfuse")
        token = _jwt()
        attrs = {
            "langfuse.observation.input": json.dumps(
                {"principal": {"raw_token": token}, "q": "hi"}
            ),
            "langfuse.observation.output": f"Bearer {token}",
            "langfuse.observation.metadata.raw_token": json.dumps(secrets.token_hex(8)),
            "langfuse.observation.model.name": "a-model",
            "gen_ai.system": "a-vendor",
        }
        span = SimpleNamespace(attributes=attrs)
        result = tracing.mask_otel_spans(params=SimpleNamespace(spans={"id": span}))

        patch = result.span_patches["id"].set_attributes
        assert token not in json.dumps(patch)
        assert json.loads(patch["langfuse.observation.input"])["q"] == "hi"
        assert "langfuse.observation.model.name" not in patch and "gen_ai.system" not in patch

    def test_a_clean_batch_yields_no_patches(self) -> None:
        pytest.importorskip("langfuse")
        span = SimpleNamespace(
            attributes={"langfuse.observation.input": json.dumps({"q": "hello"})}
        )
        assert tracing.mask_otel_spans(params=SimpleNamespace(spans={"id": span})) is None


def _ctx() -> TurnContext:
    return TurnContext(
        name="answer-question",
        mode="stream",
        question="How do I reset my password?",
        conversation_id=str(uuid4()),
        user_id=str(uuid4()),
        tenant_id=str(uuid4()),
        role="user",
    )


class _Root:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class _FakeClient:
    def __init__(self) -> None:
        self.roots: list[tuple[dict[str, Any], _Root]] = []
        self.flushed = self.closed = False

    @contextmanager
    def start_as_current_observation(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        root = _Root()
        self.roots.append((kwargs, root))
        yield root

    def flush(self) -> None:
        self.flushed = True

    def shutdown(self) -> None:
        self.closed = True


class TestFacade:
    def test_when_off_the_graph_config_is_untouched(self) -> None:
        facade = Tracing()
        assert not facade.enabled
        with facade.turn(_ctx()) as turn:
            config = {"configurable": {"thread_id": "t"}}
            assert turn.config(config) is config
            turn.finish("answer", status="completed")

    def test_when_on_a_turn_is_one_root_with_the_question_in_and_the_answer_out(self) -> None:
        pytest.importorskip("langfuse")
        client = _FakeClient()
        marker = object()
        facade = Tracing(client, lambda: marker)
        ctx = _ctx()

        with facade.turn(ctx) as turn:
            config = turn.config({"configurable": {"thread_id": "t"}})
            turn.finish("Use the reset link.", route="rag_search", status="completed", empty="")

        ((kwargs, root),) = client.roots
        assert kwargs["name"] == "answer-question" and kwargs["input"] == ctx.question
        assert config["callbacks"] == [marker] and config["run_name"] == "assistant-graph"
        assert config["configurable"] == {"thread_id": "t"}
        assert root.updates == [
            {
                "output": "Use the reset link.",
                "metadata": {"route": "rag_search", "status": "completed"},
            }
        ]

    def test_observe_is_free_when_off(self) -> None:
        with Tracing().observe("retrieve-passages", as_type="retriever", input="q") as span:
            span.finish([], hits="0")

    def test_observe_records_a_typed_child_with_input_output_and_metadata(self) -> None:
        client = _FakeClient()
        facade = Tracing(client, lambda: None)
        with facade.observe(
            "retrieve-passages", as_type="retriever", input="reset password"
        ) as span:
            span.finish([{"chunk_id": "c1"}], hits="1")
        ((kwargs, root),) = client.roots
        assert kwargs == {
            "name": "retrieve-passages",
            "as_type": "retriever",
            "input": "reset password",
        }
        assert root.updates == [{"output": [{"chunk_id": "c1"}], "metadata": {"hits": "1"}}]

    def test_flush_and_shutdown_reach_the_client(self) -> None:
        client = _FakeClient()
        facade = Tracing(client, lambda: None)
        facade.flush()
        facade.shutdown()
        assert client.flushed and client.closed


def _settings(**over: Any) -> SimpleNamespace:
    base = {
        "LANGFUSE_TRACING": False,
        "LANGFUSE_PUBLIC_KEY": "",
        "LANGFUSE_SECRET_KEY": "",
        "LANGFUSE_BASE_URL": "http://langfuse.invalid",
        "LANGFUSE_SAMPLE_RATE": 1.0,
        "APP_ENV": "test",
        "LANGSMITH_TRACING": False,
        "LANGSMITH_API_KEY": "",
        "LANGSMITH_ENDPOINT": "http://langsmith.invalid",
        "LANGSMITH_PROJECT": "p",
    }
    return SimpleNamespace(**{**base, **over})


class TestBuild:
    def test_off_by_default(self) -> None:
        assert not build_tracing(_settings()).enabled

    def test_on_without_keys_stays_off_instead_of_failing_startup(self) -> None:
        assert not build_tracing(_settings(LANGFUSE_TRACING=True)).enabled

    def test_a_missing_secret_key_alone_also_stays_off(self) -> None:
        keys = {"LANGFUSE_TRACING": True, "LANGFUSE_PUBLIC_KEY": secrets.token_hex(8)}
        assert not build_tracing(_settings(**keys)).enabled

    def test_langsmith_is_off_unless_flag_and_key_are_set(self) -> None:
        pytest.importorskip("langsmith")
        assert tracing.configure_langsmith(_settings()) is False
        assert tracing.configure_langsmith(_settings(LANGSMITH_TRACING=True)) is False
