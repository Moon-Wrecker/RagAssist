"""FastAPI router for human escalation tickets, agent replies, and ticket resolution.

Consulted References:
- FastAPI Dependency Injection and Role Security:
  https://fastapi.tiangolo.com/tutorial/security/
- Project Escalation Specifications in tests/unit/modules/escalation/test_escalation.py.
- HTTP Status Codes (RFC 9110): 403 Forbidden for non-agents, 404 Not Found for missing/foreign escalations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ragassist.modules.assistant.application.conversation_store import get_conversation_store
from ragassist.modules.escalation.application import ReplyToEscalation
from ragassist.modules.escalation.domain import EscalationNotFound, RoleNotAllowed
from ragassist.shared.security.deps import get_current_principal
from ragassist.shared.security.jwt import Principal, UserRole

router = APIRouter(tags=["Escalation"])


class EscalationSummary(BaseModel):
    escalation_id: str
    tenant_id: str
    status: str
    summary: str = ""
    priority: str = "high"
    created_at: str
    updated_at: str


class EscalationListResponse(BaseModel):
    items: list[EscalationSummary]
    total: int


class EscalationReplyRequest(BaseModel):
    text: str = Field(..., description="Reply text message from agent")


class EscalationReplyResponse(BaseModel):
    role: str = "agent"
    text: str
    user_id: str
    created_at: str


class EscalationResolveResponse(BaseModel):
    escalation_id: str
    status: str = "resolved"
    resolved_at: str


@router.get(
    "/escalations",
    response_model=EscalationListResponse,
    summary="List escalated conversations",
)
async def list_escalations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_conversation_store),
) -> EscalationListResponse:
    """List all escalated conversations for the tenant."""
    rows, _ = await store.list(principal.tenant_id, limit=limit, offset=offset)
    escalated = [r for r in rows if r.get("status") in ("escalated", "resolved")]
    items = [
        EscalationSummary(
            escalation_id=r["conversation_id"],
            tenant_id=r["tenant_id"],
            status=r["status"],
            summary=r.get("title", ""),
            priority=r.get("priority", "high"),
            created_at=r.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=r.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )
        for r in escalated
    ]
    return EscalationListResponse(items=items, total=len(items))


async def _handle_reply(
    escalation_id: str,
    req: EscalationReplyRequest,
    principal: Principal,
    store: Any,
) -> EscalationReplyResponse:
    if not req.text or not req.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reply text cannot be empty or whitespace only",
        )

    service = ReplyToEscalation(conversations=store)
    try:
        reply = await service.execute(principal, escalation_id, text=req.text)
        return EscalationReplyResponse(
            role=reply["role"],
            text=reply["text"],
            user_id=reply["user_id"],
            created_at=reply["created_at"],
        )
    except RoleNotAllowed as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except EscalationNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/escalations/{escalation_id}/reply",
    response_model=EscalationReplyResponse,
    summary="Post an agent reply to an escalation",
)
async def reply_escalation(
    escalation_id: str,
    req: EscalationReplyRequest,
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_conversation_store),
) -> EscalationReplyResponse:
    return await _handle_reply(escalation_id, req, principal, store)


@router.post(
    "/escalations/{escalation_id}/replies",
    response_model=EscalationReplyResponse,
    summary="Post an agent reply to an escalation (plural alias)",
)
async def reply_escalation_plural(
    escalation_id: str,
    req: EscalationReplyRequest,
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_conversation_store),
) -> EscalationReplyResponse:
    return await _handle_reply(escalation_id, req, principal, store)


@router.post(
    "/escalations/{escalation_id}/resolve",
    response_model=EscalationResolveResponse,
    summary="Resolve an escalated conversation",
)
async def resolve_escalation(
    escalation_id: str,
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_conversation_store),
) -> EscalationResolveResponse:
    """Mark an escalated conversation as resolved."""
    if principal.role != UserRole.AGENT and not getattr(principal, "is_agent", False) and not getattr(principal, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agents or admins can resolve an escalation",
        )

    conv = await store.get(principal.tenant_id, escalation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escalation not found",
        )

    await store.set_status(principal.tenant_id, escalation_id, "resolved")
    return EscalationResolveResponse(
        escalation_id=escalation_id,
        status="resolved",
        resolved_at=datetime.now(timezone.utc).isoformat(),
    )
