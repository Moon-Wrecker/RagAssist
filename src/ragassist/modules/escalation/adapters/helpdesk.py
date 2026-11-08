"""Helpdesk adapter for Mock SaaS helpdesk ticket API."""

from __future__ import annotations

from typing import Any
import httpx
from ragassist.shared.security.jwt import Principal, create_access_token


class HelpdeskClient:
    """Client for opening and managing human escalation tickets in helpdesk."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def create_ticket(self, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a ticket creation request with authenticated tenant token."""
        raw_token = getattr(principal, "raw_token", None)
        if not raw_token:
            raw_token = create_access_token(
                user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                role=principal.role,
            )
        headers = {"Authorization": f"Bearer {raw_token}"}
        resp = await self.http.post("/helpdesk/tickets", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()
