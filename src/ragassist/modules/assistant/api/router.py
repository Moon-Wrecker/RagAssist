"""FastAPI router for Assistant conversations, SSE streaming, and human-in-the-loop actions.

Consulted References:
- FastAPI StreamingResponse: https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
- LangGraph Human-in-the-loop / Interrupt Resumption patterns (Command(resume=...)):
  https://langchain-ai.github.io/langgraph/how-tos/human-in-the-loop/
- Starlette StreamingResponse & Disconnect Handling: https://www.starlette.io/responses/#streamingresponse
- Project SSE Contract in docs/api/sse-contract.md and tests/support/specs/map.py.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from pydantic import BaseModel, Field
import structlog

from ragassist.modules.assistant.api.sse import SSE_HEADERS, sse_stream
from ragassist.modules.assistant.application.access import (
    can_access_conversation,
    can_decide_action,
    owner_filter,
)
from ragassist.modules.assistant.application.conversation_store import get_conversation_store
from ragassist.shared.security.deps import get_current_principal
from ragassist.shared.security.jwt import Principal

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Assistant"])


class CreateConversationRequest(BaseModel):
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    conversation_id: str
    tenant_id: str
    title: str
    status: str
    messages_count: int = 0
    created_at: str
    updated_at: str


class ConversationDetailResponse(BaseModel):
    conversation_id: str
    tenant_id: str
    title: str
    status: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    updated_at: str


class SendMessageRequest(BaseModel):
    content: str = Field(..., description="User query or message text")
    stream: bool | None = None


class MessageResponse(BaseModel):
    conversation_id: str
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    route: str = "rag_search"
    status: str = "completed"
    interrupt: dict[str, Any] | None = None


class ActionDecisionRequest(BaseModel):
    approved: bool
    reason: str | None = None
    feedback: str | None = None


class ActionDecisionResponse(BaseModel):
    conversation_id: str
    interrupt_id: str
    approved: bool
    status: str = "resumed"
    answer: str | None = None
    interrupt: dict[str, Any] | None = None


async def _create_conversation(
    store: Any, principal: Principal, conversation_id: str, title: str
) -> dict[str, Any]:
    """Create through either store: the Postgres one is async and records the owning user."""
    kwargs: dict[str, Any] = {
        "tenant_id": principal.tenant_id,
        "conversation_id": conversation_id,
        "title": title,
    }
    if "user_id" in inspect.signature(store.create).parameters:
        kwargs["user_id"] = principal.user_id
    row = store.create(**kwargs)
    return await row if inspect.isawaitable(row) else row


def _checkpointable(principal: Principal) -> Principal:
    """The principal as it may be written to the durable checkpoint: without the caller's bearer token.

    With the Postgres runtime the state is stored in plaintext, so the token must not be part of it; each tool call
    mints a short-lived token for the verified user instead (``runtime.build_tool_registry``). The in-memory
    checkpointer never leaves the process, so it keeps the token the in-process tools forward.
    """
    from ragassist.runtime import active_runtime

    return replace(principal, raw_token="") if active_runtime() is not None else principal


def _pending_interrupt(snapshot: Any) -> dict[str, Any] | None:
    """The first interrupt the checkpoint is paused on, with its id, or ``None``."""
    for task in getattr(snapshot, "tasks", ()) or ():
        for item in getattr(task, "interrupts", ()) or ():
            value = getattr(item, "value", None)
            payload = dict(value) if isinstance(value, dict) else {"value": value}
            return {**payload, "interrupt_id": str(getattr(item, "id", ""))}
    return None


async def _visible_conversation(store: Any, principal: Principal, conversation_id: str) -> dict[str, Any] | None:
    """The conversation if it exists in the tenant and this principal may see it, else ``None`` (a 404)."""
    conv = await store.get(principal.tenant_id, conversation_id)
    if conv is None or not can_access_conversation(principal, conv):
        return None
    return conv


def get_assistant_graph(request: Request) -> Any:
    """Resolve compiled Assistant StateGraph from app container or singleton."""
    container = getattr(request.app.state, "container", None)
    if container is not None and hasattr(container, "get_assistant_graph"):
        return container.get_assistant_graph()
    from ragassist.container import get_container

    return get_container().get_assistant_graph()


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation session",
)
async def create_conversation(
    req: CreateConversationRequest | None = None,
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_conversation_store),
) -> ConversationResponse:
    """Create a new conversation scoped to the authenticated tenant."""
    cid = str(uuid4())
    title = req.title if req and req.title else "New Conversation"
    row = await _create_conversation(store, principal, cid, title)
    return ConversationResponse(
        conversation_id=row["conversation_id"],
        tenant_id=row["tenant_id"],
        title=row["title"],
        status=row["status"],
        messages_count=0,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get(
    "/conversations",
    summary="List tenant conversations",
)
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_conversation_store),
) -> dict[str, Any]:
    """List the caller's conversations (staff see every conversation of the tenant)."""
    items, total = await store.list(
        principal.tenant_id, limit=limit, offset=offset, owner_id=owner_filter(principal)
    )
    return {
        "items": [
            ConversationResponse(
                conversation_id=c["conversation_id"],
                tenant_id=c["tenant_id"],
                title=c["title"],
                status=c["status"],
                messages_count=len(c.get("messages", [])),
                created_at=c["created_at"],
                updated_at=c["updated_at"],
            )
            for c in items
        ],
        "total": total,
    }


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get conversation details and history",
)
async def get_conversation(
    conversation_id: str,
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_conversation_store),
) -> ConversationDetailResponse:
    """Retrieve conversation details and messages with tenant and owner verification."""
    conv = await _visible_conversation(store, principal, conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    return ConversationDetailResponse(
        conversation_id=conv["conversation_id"],
        tenant_id=conv["tenant_id"],
        title=conv["title"],
        status=conv["status"],
        messages=conv.get("messages", []),
        created_at=conv["created_at"],
        updated_at=conv["updated_at"],
    )


async def _open_ticket(
    store: Any, principal: Principal, conversation_id: str, question: str
) -> dict[str, Any] | None:
    """Create the helpdesk ticket for an escalated turn (idempotent). ``None`` without a helpdesk (memory mode)."""
    from ragassist.runtime import active_runtime

    runtime = active_runtime()
    if runtime is None:
        return None
    from ragassist.modules.escalation.application import EscalateConversation

    try:
        result = await EscalateConversation(store, runtime.helpdesk).execute(
            principal, conversation_id, summary=question[:500] or "Customer needs a human agent", priority="high"
        )
    except Exception as exc:  # noqa: BLE001 - the answer was already produced; do not fail the turn over the ticket
        logger.error("assistant.escalation_failed", error=str(exc))
        return None
    return {"ticket_id": result.ticket_id, "status": result.status, "priority": "high"}


#: Graph nodes whose chat-model tokens are the answer streamed to the client.
ANSWER_NODES = frozenset({"generate", "account_agent"})


async def _stream_graph_events(
    graph: Any,
    input_state: dict[str, Any],
    config: dict[str, Any],
    conversation_id: str,
    principal: Principal,
    store: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Stream LangGraph StateGraph execution events mapped directly into WHATWG SSE events."""
    user_query = str(input_state.get("question", "")).strip()
    tokens_emitted = 0
    citations_seen: set[str] = set()
    final_answer = ""
    final_status = "completed"
    final_citations: list[dict[str, Any]] = []
    paused = False

    try:
        if hasattr(graph, "astream_events"):
            async for event in graph.astream_events(input_state, config, version="v2"):
                kind = event.get("event")
                data = event.get("data", {})

                # 1. Tokens from LLM generation node
                if kind == "on_chat_model_start":
                    node = (event.get("metadata") or {}).get("langgraph_node")
                    if node in ANSWER_NODES and final_answer:
                        # The graph is regenerating: the client drops what it showed so far.
                        final_answer = ""
                        yield {"event": "token", "data": {"text": "", "reset": True}}
                elif kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    content = getattr(chunk, "content", "") if chunk else ""
                    node = (event.get("metadata") or {}).get("langgraph_node")
                    # Rewriter and decider models stream too; only the answer nodes belong in the answer.
                    if content and (node is None or node in ANSWER_NODES):
                        tokens_emitted += 1
                        final_answer += str(content)
                        yield {"event": "token", "data": {"text": str(content)}}

                # 2. Custom events dispatched by StateGraph nodes (e.g. finalize_node)
                elif kind == "on_custom_event":
                    custom_name = event.get("name")
                    if custom_name in ("citation", "source"):
                        for c in data.get("citations", []):
                            c_dict = (
                                c.model_dump()
                                if hasattr(c, "model_dump")
                                else (dict(c) if isinstance(c, dict) else {"chunk_id": str(c)})
                            )
                            cid = c_dict.get("chunk_id", str(len(citations_seen)))
                            if cid not in citations_seen:
                                citations_seen.add(cid)
                                final_citations.append(c_dict)
                                yield {"event": "citation", "data": c_dict}
                    elif custom_name == "done":
                        final_status = data.get("status", "completed")

                # 3. Tool call notifications
                elif kind == "on_tool_start":
                    yield {
                        "event": "tool_call",
                        "data": {
                            "tool": event.get("name"),
                            "status": "started",
                            "arguments": data.get("input"),
                        },
                    }
                elif kind == "on_tool_end":
                    yield {
                        "event": "tool_call",
                        "data": {
                            "tool": event.get("name"),
                            "status": "completed",
                            "result": data.get("output"),
                        },
                    }

                # 4. Finalize node state extraction
                elif kind == "on_chain_end" and event.get("name") == "finalize":
                    output = data.get("output", {})
                    if isinstance(output, dict):
                        if output.get("answer") and not final_answer:
                            final_answer = str(output["answer"])
                        if output.get("status"):
                            final_status = str(output["status"])
                        for c in output.get("citations", []):
                            c_dict = (
                                c.model_dump()
                                if hasattr(c, "model_dump")
                                else (dict(c) if isinstance(c, dict) else {"chunk_id": str(c)})
                            )
                            cid = c_dict.get("chunk_id", str(len(citations_seen)))
                            if cid not in citations_seen:
                                citations_seen.add(cid)
                                final_citations.append(c_dict)
                                yield {"event": "citation", "data": c_dict}
        else:
            res = await graph.ainvoke(input_state, config)
            if isinstance(res, dict):
                final_answer = str(res.get("answer", ""))
                final_status = str(res.get("status", "completed"))
                for c in res.get("citations", []):
                    c_dict = (
                        c.model_dump()
                        if hasattr(c, "model_dump")
                        else (dict(c) if isinstance(c, dict) else {"chunk_id": str(c)})
                    )
                    final_citations.append(c_dict)

    except GraphInterrupt:
        paused = True
    except Exception as exc:
        if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
            raise
        logger.error("assistant.stream_error", error=str(exc))
        yield {
            "event": "error",
            "data": {
                "code": "internal_error",
                "message": "An error occurred while processing the request.",
            },
        }
        return

    # Check state from checkpointer for any updates/citations/answer not captured during stream
    try:
        state_tuple = await graph.aget_state(config)
        pending = _pending_interrupt(state_tuple)
        if pending is not None:
            # The checkpoint is paused on a write action: tell the client which one (its id binds the decision).
            yield {"event": "interrupt", "data": pending}
            final_status = "interrupted"
            paused = True
        state_vals = getattr(state_tuple, "values", {}) or {}
        if not final_answer and state_vals.get("answer"):
            final_answer = str(state_vals["answer"])
        if state_vals.get("citations"):
            for c in state_vals["citations"]:
                c_dict = (
                    c.model_dump()
                    if hasattr(c, "model_dump")
                    else (dict(c) if isinstance(c, dict) else {"chunk_id": str(c)})
                )
                cid = c_dict.get("chunk_id", str(len(citations_seen)))
                if cid not in citations_seen:
                    citations_seen.add(cid)
                    final_citations.append(c_dict)
                    yield {"event": "citation", "data": c_dict}
    except Exception as exc:  # noqa: BLE001 - the stream already carried the answer; state is a best-effort extra
        logger.warning("assistant.state_read_failed", error=str(exc))
    if paused:
        final_status = "interrupted"

    # If no tokens were streamed (e.g. non-streaming mock model or direct node return),
    # emit token chunks from final_answer so the client receives sequential token frames
    if tokens_emitted == 0 and final_answer:
        words = final_answer.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == len(words) - 1 else word + " "
            yield {"event": "token", "data": {"text": chunk}}

    # Persist the turn first: the SSE wrapper stops at the terminal event, so nothing after it would run.
    if final_answer:
        await store.append_message(
            principal.tenant_id,
            conversation_id,
            {
                "role": "assistant",
                "text": final_answer,
                "citations": final_citations,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    if final_status == "escalated":
        ticket = await _open_ticket(store, principal, conversation_id, user_query)
        if ticket is not None:
            yield {"event": "escalated", "data": ticket}

    # Terminal done event
    yield {
        "event": "done",
        "data": {
            "conversation_id": conversation_id,
            "status": final_status,
        },
    }


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Send a message in a conversation",
)
async def ask_message(
    conversation_id: str,
    req: SendMessageRequest,
    accept: str | None = Header(None),
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_conversation_store),
    graph: Any = Depends(get_assistant_graph),
) -> Any:
    """Send message to assistant with Server-Sent Events streaming or JSON response."""
    is_sse = bool(accept and "text/event-stream" in accept) or (req.stream is True)

    conv = await store.get(principal.tenant_id, conversation_id)
    if conv is not None and not can_access_conversation(principal, conv):
        # Another user's conversation is indistinguishable from one that does not exist.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if conv is None:
        if is_sse:
            conv = await _create_conversation(
                store, principal, conversation_id, f"Chat {conversation_id[:8]}"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

    # Append user message
    now = datetime.now(timezone.utc).isoformat()
    await store.append_message(
        principal.tenant_id,
        conversation_id,
        {"role": "user", "text": req.content, "user_id": str(principal.user_id), "created_at": now},
    )

    thread_id = f"{principal.tenant_id}:{conversation_id}"
    config = {"configurable": {"thread_id": thread_id}}
    input_state = {
        "question": req.content,
        "principal": _checkpointable(principal),
        "conversation_id": conversation_id,
    }

    if is_sse:
        generator = _stream_graph_events(
            graph=graph,
            input_state=input_state,
            config=config,
            conversation_id=conversation_id,
            principal=principal,
            store=store,
        )
        return StreamingResponse(
            sse_stream(generator, heartbeat_seconds=15.0),
            headers=SSE_HEADERS,
            media_type="text/event-stream",
        )

    # Non-streaming JSON response: execute graph to completion
    pending: dict[str, Any] | None = None
    final_state: Any = {}
    try:
        final_state = await graph.ainvoke(input_state, config)
    except GraphInterrupt:
        pass
    try:
        pending = _pending_interrupt(await graph.aget_state(config))
    except Exception as exc:  # noqa: BLE001 - without a readable checkpoint the turn is treated as finished
        logger.warning("assistant.state_read_failed", error=str(exc))
    if pending is not None:
        return MessageResponse(
            conversation_id=conversation_id,
            answer="This action requires approval.",
            citations=[],
            route="saas_action",
            status="interrupted",
            interrupt=pending,
        )

    state_dict = final_state if isinstance(final_state, dict) else {}
    answer_text = str(state_dict.get("answer", ""))
    citations = state_dict.get("citations", [])
    route = str(state_dict.get("route", "rag_search"))
    status_val = str(state_dict.get("status", "completed"))

    await store.append_message(
        principal.tenant_id,
        conversation_id,
        {"role": "assistant", "text": answer_text, "citations": citations, "created_at": now},
    )
    if status_val == "escalated":
        await _open_ticket(store, principal, conversation_id, req.content)

    return MessageResponse(
        conversation_id=conversation_id,
        answer=answer_text,
        citations=citations,
        route=route,
        status=status_val,
    )


@router.post(
    "/conversations/{conversation_id}/actions/{interrupt_id}",
    response_model=ActionDecisionResponse,
    summary="Approve or deny a human-in-the-loop action",
)
async def decide_action(
    conversation_id: str,
    interrupt_id: str,
    decision: ActionDecisionRequest,
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_conversation_store),
    graph: Any = Depends(get_assistant_graph),
) -> ActionDecisionResponse:
    """Approve or deny the write action the conversation is paused on.

    The decision is bound to the pending interrupt: ``interrupt_id`` must be the one the checkpoint is paused
    on, and the tool and arguments that run are the ones stored with it, never anything sent by the client.
    Only the conversation's owner or an admin may decide.
    """
    conv = await _visible_conversation(store, principal, conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if not can_decide_action(principal, conv):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the conversation's owner or an admin can decide this action",
        )

    thread_id = f"{principal.tenant_id}:{conversation_id}"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        pending = _pending_interrupt(await graph.aget_state(config))
    except Exception as exc:  # noqa: BLE001
        logger.error("assistant.action_state_unavailable", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The pending action could not be verified",
        ) from exc
    if pending is None or pending["interrupt_id"] != interrupt_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There is no pending action with this id",
        )

    feedback = getattr(decision, "feedback", None) or decision.reason
    await store.record_action(
        tenant_id=principal.tenant_id,
        conversation_id=conversation_id,
        interrupt_id=interrupt_id,
        approved=decision.approved,
        reason=feedback,
        approver_id=principal.user_id,
    )

    resume_payload = {
        "decision": "approve" if decision.approved else "deny",
        "interrupt_id": interrupt_id,
        "feedback": feedback,
        # What the human was shown, read back from the checkpoint: this is what runs on approval.
        "tool": pending.get("tool"),
        "arguments": pending.get("arguments"),
        "call_id": pending.get("call_id"),
    }

    try:
        result = await graph.ainvoke(Command(resume=resume_payload), config)
    except GraphInterrupt:
        result = {}
    except Exception as exc:  # noqa: BLE001
        logger.error("assistant.action_resume_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The action could not be completed",
        ) from exc

    state = result if isinstance(result, dict) else {}
    still_pending = _pending_interrupt(await graph.aget_state(config))
    if still_pending is not None:
        return ActionDecisionResponse(
            conversation_id=conversation_id,
            interrupt_id=interrupt_id,
            approved=decision.approved,
            status="interrupted",
            interrupt=still_pending,
        )

    answer = str(state.get("answer", ""))
    if answer:
        await store.append_message(
            principal.tenant_id,
            conversation_id,
            {
                "role": "assistant",
                "text": answer,
                "citations": state.get("citations", []),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    if str(state.get("status", "")) == "escalated":
        await _open_ticket(store, principal, conversation_id, str(state.get("question", "")))

    return ActionDecisionResponse(
        conversation_id=conversation_id,
        interrupt_id=interrupt_id,
        approved=decision.approved,
        status="resumed",
        answer=answer or None,
    )
