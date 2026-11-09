"""Empirical Challenger adversarial stress suite for M2-M5.

Focus areas:
1. LangGraph cyclic state machine: loop bounds, interrupt resumption, thread isolation across {tenant_id}:{conversation_id}, state pollution across abandoned turns.
2. Tool abuse and authorization: invented tool names, schema validation, type confusion attacks, secret masking.
3. Hybrid Retrieval & Reranker cascade: RRF edge cases (empty, duplicates, disjoint), ContextBuilder budget truncation, fallback cascade under cascading failures.
4. SSE Streaming protocol: ordering, error handling without leak, client disconnect cleanup, invalid event filtering.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from factories.principals import make_principal
from fakes.chat_model import tool_call_message
from support.graph_harness import (
    TENANT_A,
    TENANT_B,
    CountingSaver,
    make_graph,
    make_kit,
    paused,
    resume_turn,
    run_turn,
)
from support.sse import parse_sse

from ragassist.modules.actions.application import (
    AuditLog,
    ToolRegistry,
    ToolSpec,
)
from ragassist.modules.actions.domain import UnknownTool
from ragassist.modules.assistant.api.sse import format_sse_frame, sse_stream
from ragassist.modules.retrieval.application import ContextBuilder
from ragassist.modules.retrieval.domain import Hit, reciprocal_rank_fusion
from ragassist.modules.retrieval.fusion import fuse_hit_rankings
from ragassist.platform.rerank.adapters.noop_adapter import NoopReranker
from ragassist.platform.rerank.adapters.reranker_chain import RerankerChain
from ragassist.platform.rerank.ports import Candidate, Reranker, Scored
from ragassist.shared.security.jwt import Principal, UserRole

pytestmark = pytest.mark.security


# ==============================================================================
# 1. LangGraph State Machine Loop Bounds & Isolation
# ==============================================================================


class TestLangGraphLoopBoundsAndIsolation:
    """Stress-test loop limits, thread boundaries, and resumption payloads."""

    async def test_relevance_grading_failure_loop_is_strictly_bounded(self) -> None:
        """When retrieved chunks are repeatedly irrelevant, graph must terminate via escalate within bound."""
        kit = make_kit(route="rag_search", relevant=False)
        graph = make_graph(kit)
        principal = make_principal(tenant_id=TENANT_A)

        turn = await run_turn(graph, question="Need specific details", principal=principal)

        assert "escalate" in turn.path
        assert "finalize" in turn.path
        assert turn.state.get("escalated") is True
        # Verify finite step count: cannot loop indefinitely
        assert len(turn.path) <= 15
        assert turn.state.get("rewrite_count", 0) <= 2
        assert turn.state.get("retrieve_count", 0) <= 3

    async def test_grounding_failure_loop_is_strictly_bounded(self) -> None:
        """When generation is repeatedly ungrounded, graph regenerates at most once, then escalates."""
        kit = make_kit(route="rag_search", relevant=True, grounded=False)
        graph = make_graph(kit)
        principal = make_principal(tenant_id=TENANT_A)

        turn = await run_turn(graph, question="What are terms?", principal=principal)

        assert "escalate" in turn.path
        assert turn.state.get("escalated") is True
        assert turn.state.get("generate_count", 0) <= 2

    async def test_thread_isolation_between_tenants_with_same_conversation_id(self) -> None:
        """Tenant A and Tenant B using the same conversation_id 'conv-shared' must have zero state bleed."""
        saver = CountingSaver()
        kit = make_kit(route="general_chat")
        graph = make_graph(kit, checkpointer=saver)

        princ_a = make_principal(tenant_id=TENANT_A, user_id=uuid4())
        princ_b = make_principal(tenant_id=TENANT_B, user_id=uuid4())

        kit.cheap.script = ["Hello from Tenant A", "Hello from Tenant B"]

        turn_a = await run_turn(
            graph, question="Hi Tenant A", principal=princ_a, conversation_id="conv-shared"
        )
        turn_b = await run_turn(
            graph, question="Hi Tenant B", principal=princ_b, conversation_id="conv-shared"
        )

        assert turn_a.state["principal"].tenant_id == TENANT_A
        assert turn_b.state["principal"].tenant_id == TENANT_B
        assert turn_a.config["configurable"]["thread_id"] == f"{TENANT_A}:conv-shared"
        assert turn_b.config["configurable"]["thread_id"] == f"{TENANT_B}:conv-shared"

        # Checkpoint tuple reads are strictly tenant-namespaced
        state_a = (await graph.aget_state(turn_a.config)).values
        state_b = (await graph.aget_state(turn_b.config)).values
        assert state_a["principal"].tenant_id == TENANT_A
        assert state_b["principal"].tenant_id == TENANT_B

    async def test_interrupt_resumption_with_adversarial_decision_payloads(self) -> None:
        """Verify resume_turn with non-standard decision payloads (None, SQLi string, dict) defaults to safe denial."""
        write_call = tool_call_message(
            "update_billing_email", {"new_email": "admin@target.com"}, "w1"
        )
        adversarial_decisions = [
            "deny",
            "approve'; DROP TABLE users;--",
            "RANDOM_STRING",
            "",
            "APPROVE",  # case-sensitive check
        ]

        for bad_decision in adversarial_decisions:
            kit = make_kit(route="saas_action")
            kit.strong.script = [write_call, "Operation finished."]
            graph = make_graph(kit)
            principal = make_principal(tenant_id=TENANT_A)

            turn = await run_turn(
                graph,
                question="Update email",
                principal=principal,
                conversation_id=f"conv-{uuid4()}",
            )
            assert paused(turn)

            await resume_turn(
                graph,
                decision=bad_decision,
                principal=principal,
                conversation_id=turn.config["configurable"]["thread_id"].split(":")[1],
            )

            # Write tool must NOT be executed unless exact decision == "approve"
            executed = kit.tools.calls_named("update_billing_email")
            assert executed == [], (
                f"Decision '{bad_decision}' unexpectedly executed the write tool!"
            )


# ==============================================================================
# 2. Tool Abuse, Schema Tampering & Authorization
# ==============================================================================


class TestToolAbuseAndAuthorization:
    """Stress-test tool registration, type confusion attacks, and secret leakage in audit logs."""

    async def test_unknown_tool_invocation_fails_immediately(self) -> None:
        """Invoking an unregistered tool raises UnknownTool."""
        registry = ToolRegistry([])
        principal = make_principal(tenant_id=TENANT_A)

        with pytest.raises(UnknownTool):
            await registry.invoke("rm_rf_database", {}, principal)

    async def test_tool_argument_type_confusion_attacks(self) -> None:
        """Schema validation rejects type-confused payloads (bool for int, int for str, etc.)."""

        async def dummy_handler(p: Principal, args: dict[str, Any]) -> dict[str, str]:
            return {"status": "ok"}

        tool = ToolSpec(
            name="set_quota",
            description="Set tenant seat quota",
            input_schema={
                "type": "object",
                "properties": {
                    "seats": {"type": "integer"},
                    "plan": {"type": "string"},
                    "active": {"type": "boolean"},
                },
                "required": ["seats", "plan"],
            },
            is_write=True,
            handler=dummy_handler,
        )
        registry = ToolRegistry([tool])
        principal = make_principal(tenant_id=TENANT_A, role=UserRole.ADMIN)

        # 1. Missing required field
        with pytest.raises(ValueError, match="Missing required argument"):
            await registry.invoke("set_quota", {"seats": 10}, principal)

        # 2. Boolean passed where integer expected (Python bool is subclass of int)
        with pytest.raises(TypeError, match="must be an integer"):
            await registry.invoke("set_quota", {"seats": True, "plan": "pro"}, principal)

        # 3. Integer passed where string expected
        with pytest.raises(TypeError, match="must be a string"):
            await registry.invoke("set_quota", {"seats": 10, "plan": 9999}, principal)

        # 4. String passed where boolean expected
        with pytest.raises(TypeError, match="must be a boolean"):
            await registry.invoke(
                "set_quota", {"seats": 10, "plan": "pro", "active": "yes"}, principal
            )

    async def test_audit_log_recursively_redacts_nested_secrets(self) -> None:
        """AuditLog must mask secret fields in nested dictionaries and lists."""

        class InMemoryAuditStore:
            def __init__(self) -> None:
                self.rows: list[dict[str, Any]] = []

            def add(self, row: dict[str, Any], uow: Any) -> None:
                self.rows.append(row)

        store = InMemoryAuditStore()
        audit = AuditLog(store)
        principal = make_principal(tenant_id=TENANT_A, user_id=uuid4())

        payload = {
            "name": "Acme",
            "credentials": {
                "api_key": "secret-token-12345",
                "password": "super-secret-password",
                "headers": [{"authorization": "Bearer eyJhbGci..."}, {"host": "api.com"}],
            },
            "public_key": "ssh-rsa AAAAB3NzaC1yc2EAAA...",
        }

        entry = await audit.record(
            principal,
            tool="configure_integration",
            arguments=payload,
            approved=True,
            outcome="success",
            uow=object(),
        )

        args = entry["arguments"]
        assert args["credentials"]["api_key"] == "***REDACTED***"
        assert args["credentials"]["password"] == "***REDACTED***"
        assert args["credentials"]["headers"][0]["authorization"] == "***REDACTED***"
        assert args["credentials"]["headers"][1]["host"] == "api.com"
        assert "secret-token-12345" not in str(args)
        assert "super-secret-password" not in str(args)


# ==============================================================================
# 3. Hybrid Retrieval & Reranker Cascade Stress
# ==============================================================================


class TestRetrievalAndRerankerCascade:
    """Stress-test RRF fusion edge cases, ContextBuilder budget enforcement, and reranker fallback."""

    def test_rrf_with_extreme_and_empty_inputs(self) -> None:
        """RRF behaves correctly on empty lists, duplicate elements, and single candidate lists."""
        # Empty inputs
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[]]) == []
        assert reciprocal_rank_fusion([[], [], []]) == []

        # Single candidate in single list
        res = reciprocal_rank_fusion([["doc1"]], k=60)
        assert len(res) == 1
        assert res[0][0] == "doc1"
        assert abs(res[0][1] - (1.0 / 61)) < 1e-6

        # Candidate repeated multiple times inside the same ranking: uses 1-based index in ranking
        res_dup = reciprocal_rank_fusion([["doc1", "doc1", "doc1", "doc2"]], k=60)
        assert len(res_dup) == 2
        assert res_dup[0][0] == "doc1"
        assert abs(res_dup[0][1] - (1.0 / 61)) < 1e-6
        # doc2 is at index 4 (1-based), so rank is 4: 1.0 / (60 + 4)
        assert abs(res_dup[1][1] - (1.0 / 64)) < 1e-6

        # Disjoint rankings tie-breaking: first seen order
        res_disjoint = reciprocal_rank_fusion([["a"], ["b"]], k=60)
        assert len(res_disjoint) == 2
        assert res_disjoint[0][0] == "a"
        assert res_disjoint[1][0] == "b"
        assert res_disjoint[0][1] == res_disjoint[1][1]

    def test_fuse_hit_rankings_preserves_metadata(self) -> None:
        """fuse_hit_rankings correctly aggregates scores while preserving Hit metadata."""
        h1 = Hit(
            chunk_id="c1",
            document_id="d1",
            tenant_id=str(TENANT_A),
            score=0.9,
            text="Content 1",
            title="Title 1",
        )
        h2 = Hit(
            chunk_id="c2",
            document_id="d1",
            tenant_id=str(TENANT_A),
            score=0.8,
            text="Content 2",
            title="Title 1",
        )

        fused = fuse_hit_rankings([[h1], [h2, h1]], k=60)
        assert len(fused) == 2
        assert fused[0].chunk_id == "c1"  # c1 is rank 1 in list 1 and rank 2 in list 2
        assert fused[0].title == "Title 1"
        assert fused[0].score > fused[1].score

    def test_context_builder_zero_and_negative_budgets(self) -> None:
        """ContextBuilder safely returns empty ContextPack when budget is 0 or negative."""

        class SimpleTokenizer:
            def count(self, text: str) -> int:
                return len(text.split())

        hits = [Hit(chunk_id="c1", document_id="d1", tenant_id=None, score=0.9, text="Word " * 50)]

        cb_zero = ContextBuilder(SimpleTokenizer(), budget_tokens=0)
        assert cb_zero.build(hits).passages == []

        cb_neg = ContextBuilder(SimpleTokenizer(), budget_tokens=-10)
        assert cb_neg.build(hits).passages == []

    def test_context_builder_truncates_oversized_hit(self) -> None:
        """Oversized hit is truncated to fit remaining token budget without error."""

        class WordTokenizer:
            def count(self, text: str) -> int:
                return len(text.split())

            def encode(self, text: str) -> list[str]:
                return text.split()

            def decode(self, tokens: list[str]) -> str:
                return " ".join(tokens)

        hits = [
            Hit(
                chunk_id="c1",
                document_id="d1",
                tenant_id=None,
                score=1.0,
                text="one two three four five six seven eight nine ten",
            )
        ]
        cb = ContextBuilder(WordTokenizer(), budget_tokens=4)
        pack = cb.build(hits)
        assert len(pack.passages) == 1
        assert pack.passages[0].text == "one two three four"

    async def test_reranker_chain_full_cascade_fallback_to_none(self) -> None:
        """When all upstream rerankers throw exceptions or timeout, chain gracefully falls back to none."""

        class FailingReranker(Reranker):
            def __init__(self, name: str, exc: Exception) -> None:
                self._name = name
                self._exc = exc

            @property
            def name(self) -> str:
                return self._name

            async def rerank(
                self, query: str, candidates: list[Candidate], top_n: int = 6
            ) -> list[Scored]:
                raise self._exc

        class TimeoutReranker(Reranker):
            @property
            def name(self) -> str:
                return "timeout_reranker"

            async def rerank(
                self, query: str, candidates: list[Candidate], top_n: int = 6
            ) -> list[Scored]:
                await asyncio.sleep(1.0)
                return []

        candidates = [
            Candidate(chunk_id="c1", text="text 1", score=0.95),
            Candidate(chunk_id="c2", text="text 2", score=0.85),
        ]

        chain = RerankerChain(
            members=[
                FailingReranker("cross_encoder", RuntimeError("GPU CUDA OOM")),
                TimeoutReranker(),
                NoopReranker(),
            ],
            timeout_ms=50,  # 50ms forces TimeoutReranker to timeout
        )

        result = await chain.rerank("test query", candidates, top_n=2)
        assert result.reranker == "none"
        assert len(result.items) == 2
        assert result.items[0].chunk_id == "c1"
        assert result.items[1].chunk_id == "c2"


# ==============================================================================
# 4. SSE Streaming Protocol Stress & Resilience
# ==============================================================================


class TestSSEStreamingProtocolStress:
    """Stress-test SSE event formatting, error shields, and client disconnect cancellation."""

    async def test_sse_stream_filters_disallowed_events(self) -> None:
        """Events outside the permitted schema are silently ignored without breaking stream."""

        async def event_generator() -> AsyncIterator[dict[str, Any]]:
            yield {"event": "token", "data": {"text": "A"}}
            yield {"event": "malicious_injected_event", "data": {"cmd": "exec"}}
            yield {"event": "token", "data": {"text": "B"}}
            yield {"event": "done", "data": {"status": "completed"}}

        stream = sse_stream(event_generator(), heartbeat_seconds=60)
        frames = [f async for f in stream]
        raw = "".join(frames)
        parsed = parse_sse(raw)

        assert "malicious_injected_event" not in parsed.names
        assert parsed.names == ["token", "token", "done"]

    async def test_sse_stream_gracefully_catches_midstream_exception_without_leaks(self) -> None:
        """Exception during generation yields clean 'error' frame and masks internal details."""

        async def failing_stream() -> AsyncIterator[dict[str, Any]]:
            yield {"event": "token", "data": {"text": "Working..."}}
            raise ValueError(
                "SECRET_DB_PASSWORD_123 failed connection to postgres://admin:xyz@db:5432"
            )

        stream = sse_stream(failing_stream(), heartbeat_seconds=60)
        frames = [f async for f in stream]
        raw = "".join(frames)
        parsed = parse_sse(raw)

        assert "SECRET_DB_PASSWORD" not in raw
        assert "postgres://" not in raw
        assert parsed.names[-1] == "error"
        err = parsed.of("error")[0].json()
        assert err["code"] == "internal_error"

    async def test_sse_stream_aclose_cancels_in_flight_coroutine(self) -> None:
        """Client disconnect triggers proper async generator cleanup without unhandled exceptions."""
        cancelled = False

        async def endless_stream() -> AsyncIterator[dict[str, Any]]:
            nonlocal cancelled
            try:
                while True:
                    yield {"event": "token", "data": {"text": "tick"}}
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                cancelled = True
                raise

        stream = sse_stream(endless_stream(), heartbeat_seconds=60)
        # Read one item
        item = await stream.__anext__()
        assert "event: token" in item

        # Simulate disconnect
        await stream.aclose()
        assert cancelled is True

    def test_format_sse_frame_multiline_string_and_json(self) -> None:
        """format_sse_frame properly formats multiline string payloads and json dicts."""
        frame = format_sse_frame("token", {"text": "Line 1\nLine 2"}, event_id="123")
        assert "event: token\n" in frame
        assert "id: 123\n" in frame
        assert frame.endswith("\n\n")
