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
from collections.abc import AsyncIterator
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
from ragassist.modules.assistant.application.conversation_store import (
    InMemoryConversationStore,
    get_conversation_store,
)
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


class ActionDecisionRequest(BaseModel):
    approved: bool
    reason: str | None = None
    feedback: str | None = None


class ActionDecisionResponse(BaseModel):
    conversation_id: str
    interrupt_id: str
    approved: bool
    status: str = "resumed"


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
    store: InMemoryConversationStore = Depends(get_conversation_store),
) -> ConversationResponse:
    """Create a new conversation scoped to the authenticated tenant."""
    cid = str(uuid4())
    title = req.title if req and req.title else "New Conversation"
    row = store.create(tenant_id=principal.tenant_id, conversation_id=cid, title=title)
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
    store: InMemoryConversationStore = Depends(get_conversation_store),
) -> dict[str, Any]:
    """List conversations belonging exclusively to the authenticated tenant."""
    items, total = await store.list(principal.tenant_id, limit=limit, offset=offset)
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
    store: InMemoryConversationStore = Depends(get_conversation_store),
) -> ConversationDetailResponse:
    """Retrieve conversation details and messages with tenant verification."""
    conv = await store.get(principal.tenant_id, conversation_id)
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


async def _stream_graph_events(
    graph: Any,
    input_state: dict[str, Any],
    config: dict[str, Any],
    conversation_id: str,
    principal: Principal,
    store: InMemoryConversationStore,
) -> AsyncIterator[dict[str, Any]]:
    """Stream LangGraph StateGraph execution events mapped directly into WHATWG SSE events."""
    tokens_emitted = 0
    citations_seen: set[str] = set()
    final_answer = ""
    final_status = "completed"
    final_citations: list[dict[str, Any]] = []

    try:
        if hasattr(graph, "astream_events"):
            async for event in graph.astream_events(input_state, config, version="v2"):
                kind = event.get("event")
                data = event.get("data", {})

                # 1. Tokens from LLM generation node
                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    content = getattr(chunk, "content", "") if chunk else ""
                    if content:
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

    except GraphInterrupt as gi:
        interrupt_val = gi.args[0] if gi.args else {}
        yield {"event": "interrupt", "data": interrupt_val}
        final_status = "interrupted"
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
    except Exception:
        pass

    # If no tokens were streamed (e.g. non-streaming mock model or direct node return),
    # emit token chunks from final_answer so the client receives sequential token frames
    if tokens_emitted == 0 and final_answer:
        words = final_answer.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == len(words) - 1 else word + " "
            yield {"event": "token", "data": {"text": chunk}}

    # Terminal done event
    yield {
        "event": "done",
        "data": {
            "conversation_id": conversation_id,
            "status": final_status,
        },
    }

    # Record message in conversation store
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


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Send a message in a conversation",
)
async def ask_message(
    conversation_id: str,
    req: SendMessageRequest,
    accept: str | None = Header(None),
    principal: Principal = Depends(get_current_principal),
    store: InMemoryConversationStore = Depends(get_conversation_store),
    graph: Any = Depends(get_assistant_graph),
) -> Any:
    """Send message to assistant with Server-Sent Events streaming or JSON response."""
    is_sse = bool(accept and "text/event-stream" in accept) or (req.stream is True)

    conv = await store.get(principal.tenant_id, conversation_id)
    if conv is None:
        if is_sse:
            conv = store.create(
                tenant_id=principal.tenant_id,
                conversation_id=conversation_id,
                title=f"Chat {conversation_id[:8]}",
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
        {"role": "user", "text": req.content, "created_at": now},
    )

    thread_id = f"{principal.tenant_id}:{conversation_id}"
    config = {"configurable": {"thread_id": thread_id}}
    input_state = {
        "question": req.content,
        "principal": principal,
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
    try:
        final_state = await graph.ainvoke(input_state, config)
    except GraphInterrupt as gi:
        interrupt_val = gi.args[0] if gi.args else {}
        return MessageResponse(
            conversation_id=conversation_id,
            answer="This action requires approval.",
            citations=[],
            route="saas_action",
            status="interrupted",
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
    store: InMemoryConversationStore = Depends(get_conversation_store),
    graph: Any = Depends(get_assistant_graph),
) -> ActionDecisionResponse:
    """Approve or deny an action interrupted by human-in-the-loop policy."""
    conv = await store.get(principal.tenant_id, conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    feedback = getattr(decision, "feedback", None) or decision.reason

    await store.record_action(
        tenant_id=principal.tenant_id,
        conversation_id=conversation_id,
        interrupt_id=interrupt_id,
        approved=decision.approved,
        reason=feedback,
    )

    thread_id = f"{principal.tenant_id}:{conversation_id}"
    config = {"configurable": {"thread_id": thread_id}}
    resume_payload = {
        "decision": "approve" if decision.approved else "deny",
        "interrupt_id": interrupt_id,
        "feedback": feedback,
    }

    try:
        # Resume the interrupted execution on the checkpointer
        if hasattr(graph, "ainvoke"):
            await graph.ainvoke(Command(resume=resume_payload), config)
        elif hasattr(graph, "astream"):
            async for _ in graph.astream(Command(resume=resume_payload), config):
                pass
    except Exception as exc:
        logger.warning("assistant.action_resume_warning", error=str(exc))

    return ActionDecisionResponse(
        conversation_id=conversation_id,
        interrupt_id=interrupt_id,
        approved=decision.approved,
        status="resumed",
    )
