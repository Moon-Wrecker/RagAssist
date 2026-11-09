"""Standalone Mock SaaS Service (Accounts, Billing, Invoices, Subscriptions, Helpdesk).

Validates the incoming caller JWT and provides tenant-isolated account data and tools.
"""

from datetime import datetime, timezone
import os
import re
from typing import Any
from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator
import jwt

app = FastAPI(title="Mock SaaS Service", version="1.0.0")
_security = HTTPBearer()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# In-memory tenant account databases
_ACCOUNTS: dict[str, dict[str, Any]] = {
    # Acme Corp Demo Tenant
    "a0000000-0000-0000-0000-000000000001": {
        "company_name": "Acme Corp",
        "plan": "Enterprise Scale",
        "billing_email": "billing@acme.example.com",
        "status": "active",
        "seats": 50,
        "seats_used": 38,
        "monthly_spend": 2400.0,
        "subscription_renews": "2027-01-01T00:00:00Z",
        "invoices": [
            {"id": "inv_acme_101", "amount": 2400.0, "status": "paid", "date": "2026-10-01"},
            {"id": "inv_acme_102", "amount": 2400.0, "status": "paid", "date": "2026-11-01"},
        ],
    },
    # Globex Corp Demo Tenant
    "b0000000-0000-0000-0000-000000000002": {
        "company_name": "Globex Corp",
        "plan": "Pro Starter",
        "billing_email": "finance@globex.example.com",
        "status": "active",
        "seats": 10,
        "seats_used": 9,
        "monthly_spend": 490.0,
        "subscription_renews": "2026-12-15T00:00:00Z",
        "invoices": [
            {"id": "inv_globex_201", "amount": 490.0, "status": "paid", "date": "2026-10-15"},
        ],
    },
}

_TICKETS: list[dict[str, Any]] = []


def _decode_jwt(credentials: HTTPAuthorizationCredentials = Security(_security)) -> dict[str, Any]:
    """Verify JWT signature, expiry, algorithm, and tenant claim."""
    # Standalone service: it reads only the two values it needs and does not import the application package.
    secret_key, algorithm = os.environ["SECRET_KEY"], os.environ["JWT_ALGORITHM"]
    try:
        payload: dict[str, Any] = jwt.decode(
            credentials.credentials,
            secret_key,
            algorithms=[algorithm],
            options={"require": ["exp", "tenant_id"]},
        )
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            raise ValueError("Missing tenant_id in JWT")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc


def _extract_tenant_id(payload: dict[str, Any] = Depends(_decode_jwt)) -> str:
    return str(payload["tenant_id"])


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/accounts/overview")
async def get_account_overview(tenant_id: str = Depends(_extract_tenant_id)) -> dict[str, Any]:
    if tenant_id not in _ACCOUNTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant account not found")
    data = _ACCOUNTS[tenant_id]
    return {
        "tenant_id": tenant_id,
        "company_name": data["company_name"],
        "plan": data["plan"],
        "status": data["status"],
        "billing_email": data["billing_email"],
    }


@app.get("/accounts/subscription")
async def get_subscription(tenant_id: str = Depends(_extract_tenant_id)) -> dict[str, Any]:
    if tenant_id not in _ACCOUNTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant account not found")
    data = _ACCOUNTS[tenant_id]
    return {
        "tenant_id": tenant_id,
        "plan": data["plan"],
        "seats": data["seats"],
        "seats_used": data["seats_used"],
        "monthly_spend": data["monthly_spend"],
        "subscription_renews": data["subscription_renews"],
    }


@app.get("/accounts/invoices")
async def list_invoices(tenant_id: str = Depends(_extract_tenant_id)) -> list[dict[str, Any]]:
    if tenant_id not in _ACCOUNTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant account not found")
    return _ACCOUNTS[tenant_id]["invoices"]


class UpdateBillingEmailRequest(BaseModel):
    new_email: str

    @field_validator("new_email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not v or not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address")
        return v


@app.post("/accounts/billing-email")
async def update_billing_email(
    req: UpdateBillingEmailRequest, payload: dict[str, Any] = Depends(_decode_jwt)
) -> dict[str, Any]:
    tenant_id = str(payload["tenant_id"])
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )
    if tenant_id not in _ACCOUNTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant account not found")
    _ACCOUNTS[tenant_id]["billing_email"] = req.new_email
    return {
        "status": "success",
        "tenant_id": tenant_id,
        "updated_billing_email": req.new_email,
    }


class CreateTicketRequest(BaseModel):
    subject: str
    description: str
    conversation_id: str | None = None
    priority: str = "high"


@app.post("/helpdesk/tickets")
async def create_ticket(
    req: CreateTicketRequest, tenant_id: str = Depends(_extract_tenant_id)
) -> dict[str, Any]:
    ticket_id = f"TICK-{len(_TICKETS) + 1:04d}"
    ticket = {
        "id": ticket_id,
        "tenant_id": tenant_id,
        "subject": req.subject,
        "description": req.description,
        "conversation_id": req.conversation_id,
        "priority": req.priority,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _TICKETS.append(ticket)
    return ticket

