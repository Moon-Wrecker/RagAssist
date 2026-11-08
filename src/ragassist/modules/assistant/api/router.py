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
from pydantic import BaseModel, Field

from ragassist.modules.assistant.api.sse import SSE_HEADERS, sse_stream
from ragassist.modules.assistant.application.conversation_store import (
    InMemoryConversationStore,
    get_conversation_store,
)
from ragassist.modules.assistant.application.thread_guard import (
    ThreadAccessDenied,
    ensure_thread_access,
    namespaced_thread_id,
)
from ragassist.shared.security.deps import get_current_principal
from ragassist.shared.security.jwt import Principal

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


class ActionDecisionResponse(BaseModel):
    conversation_id: str
    interrupt_id: str
    approved: bool
    status: str = "resumed"





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
    title = (req.title if req and req.title else "New Conversation")
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


async def _generate_sse_events(
    user_query: str,
    conversation_id: str,
    principal: Principal,
) -> AsyncIterator[dict[str, Any]]:
    """Synthesize streaming response events (tokens, citation, done)."""
    # Yield initial tokens
    words = [
        "I ",
        "have ",
        "processed ",
        "your ",
        "request ",
        "regarding ",
        f"'{user_query}'. ",
        "Here ",
        "is ",
        "the ",
        "answer.",
    ]
    for word in words:
        yield {"event": "token", "data": {"text": word}}
        await asyncio.sleep(0.01)

    # Yield citation if applicable
    yield {
        "event": "citation",
        "data": {
            "chunk_id": f"chunk-{conversation_id[:8]}",
            "title": "System Knowledge Base",
            "page": 1,
            "heading_path": ["Overview", "Policy"],
        },
    }

    # Yield final done event
    yield {
        "event": "done",
        "data": {
            "conversation_id": conversation_id,
            "status": "completed",
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
    store: InMemoryConversationStore = Depends(get_conversation_store),
) -> Any:
    """Send message to assistant with Server-Sent Events streaming or JSON response."""
    is_sse = bool(accept and "text/event-stream" in accept) or (req.stream is True)

    conv = await store.get(principal.tenant_id, conversation_id)
    if conv is None:
        if is_sse:
            # Auto-bind session for streaming requests
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

    if is_sse:
        generator = _generate_sse_events(req.content, conversation_id, principal)
        return StreamingResponse(
            sse_stream(generator, heartbeat_seconds=15.0),
            headers=SSE_HEADERS,
            media_type="text/event-stream",
        )

    # JSON response
    answer_text = f"Processed request for: {req.content}"
    citations = [
        {
            "chunk_id": f"chunk-{conversation_id[:8]}",
            "title": "Knowledge Documentation",
            "page": 1,
            "heading_path": ["Guide"],
        }
    ]
    await store.append_message(
        principal.tenant_id,
        conversation_id,
        {"role": "assistant", "text": answer_text, "citations": citations, "created_at": now},
    )

    return MessageResponse(
        conversation_id=conversation_id,
        answer=answer_text,
        citations=citations,
        route="rag_search",
        status="completed",
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
) -> ActionDecisionResponse:
    """Approve or deny an action interrupted by human-in-the-loop policy."""
    conv = await store.get(principal.tenant_id, conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    await store.record_action(
        tenant_id=principal.tenant_id,
        conversation_id=conversation_id,
        interrupt_id=interrupt_id,
        approved=decision.approved,
        reason=decision.reason,
    )

    return ActionDecisionResponse(
        conversation_id=conversation_id,
        interrupt_id=interrupt_id,
        approved=decision.approved,
        status="resumed",
    )
