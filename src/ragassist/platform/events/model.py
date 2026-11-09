"""Event model and audience rules for the live events stream (ADR 0008).

Goal: describe a change notification that carries only a type and ids (never content) and decide, on the server,
which signed-in user may receive it. The client refetches through the normal API, which enforces tenant, owner and
role a second time, so a leaked or forged notification cannot expose data.

Consulted: PostgreSQL ``NOTIFY`` documentation (payload is a string below 8000 bytes, so only ids travel), WHATWG
Server-Sent Events specification, docs/api/sse-contract.md (the wire contract these names implement).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ragassist.shared.security.jwt import Principal, UserRole

# --- Event types delivered to clients (docs/api/sse-contract.md) ---------------------------------------------------
JOB_UPDATED = "job.updated"
DOCUMENT_CHANGED = "document.changed"
MESSAGE_CREATED = "message.created"
CONVERSATION_UPDATED = "conversation.updated"
ESCALATION_CHANGED = "escalation.changed"
#: Produced by the stream itself for one connection, never through the bus.
READY = "ready"
RESYNC = "resync"
REAUTH = "reauth"

BUS_EVENT_TYPES = frozenset(
    {JOB_UPDATED, DOCUMENT_CHANGED, MESSAGE_CREATED, CONVERSATION_UPDATED, ESCALATION_CHANGED}
)

#: The only payload keys an event may carry. Anything else is rejected, so content cannot slip into the channel.
ID_KEYS = frozenset({"job_id", "document_id", "conversation_id", "ticket_id"})
MAX_ID_LENGTH = 128


class Audience(str, Enum):
    """Who may receive an event inside the tenant."""

    ADMINS = "admins"
    STAFF = "staff"  # agents and admins
    OWNER_AND_STAFF = "owner_and_staff"  # the conversation owner, agents and admins


class InvalidEvent(ValueError):
    """The event is malformed or could carry more than ids."""


@dataclass(frozen=True)
class Viewer:
    """The verified identity of a stream's owner, taken from the JWT principal only."""

    tenant_id: str
    user_id: str
    role: str

    @classmethod
    def from_principal(cls, principal: Principal) -> Viewer:
        return cls(
            tenant_id=str(principal.tenant_id),
            user_id=str(principal.user_id),
            role=principal.role.value,
        )

    @property
    def is_staff(self) -> bool:
        return self.role in (UserRole.AGENT.value, UserRole.ADMIN.value)

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value


@dataclass(frozen=True)
class Event:
    """One change notification: a type, the tenant it belongs to, ids, and the audience."""

    type: str
    tenant_id: str
    audience: Audience
    data: Mapping[str, str] = field(default_factory=dict)
    owner_id: str | None = None

    def __post_init__(self) -> None:
        if self.type not in BUS_EVENT_TYPES:
            raise InvalidEvent(f"unknown event type {self.type!r}")
        if not self.tenant_id:
            raise InvalidEvent("an event needs a tenant")
        for key, value in self.data.items():
            if key not in ID_KEYS:
                raise InvalidEvent(f"{key!r} is not an id field")
            if not isinstance(value, str) or not value or len(value) > MAX_ID_LENGTH:
                raise InvalidEvent(f"{key!r} must be a short non-empty string id")

    def payload(self) -> dict[str, str]:
        """The ``data`` of the SSE frame."""
        return dict(self.data)

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": self.type,
                "tenant_id": self.tenant_id,
                "audience": self.audience.value,
                "data": dict(self.data),
                "owner_id": self.owner_id,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str) -> Event:
        """Parse a notification from the channel; anything unexpected raises ``InvalidEvent``."""
        try:
            body: Any = json.loads(raw)
            if not isinstance(body, dict):
                raise TypeError("not an object")
            owner = body.get("owner_id")
            return cls(
                type=str(body["type"]),
                tenant_id=str(body["tenant_id"]),
                audience=Audience(body["audience"]),
                data=dict(body.get("data") or {}),
                owner_id=str(owner) if owner else None,
            )
        except InvalidEvent:
            raise
        except (ValueError, TypeError, KeyError) as exc:
            raise InvalidEvent("malformed event payload") from exc


def visible_to(viewer: Viewer, event: Event) -> bool:
    """Server-side filter: same tenant first, then the audience rule. Anything unclear is not delivered."""
    if event.tenant_id != viewer.tenant_id:
        return False
    if event.audience is Audience.ADMINS:
        return viewer.is_admin
    if event.audience is Audience.STAFF:
        return viewer.is_staff
    if event.audience is Audience.OWNER_AND_STAFF:
        if viewer.is_staff:
            return True
        return event.owner_id is not None and event.owner_id == viewer.user_id
    return False


# --- Builders: one per kind of change, so call sites cannot invent payloads ---------------------------------------
def job_updated(tenant_id: object, job_id: object, document_id: object) -> Event:
    return Event(
        JOB_UPDATED,
        str(tenant_id),
        Audience.ADMINS,
        {"job_id": str(job_id), "document_id": str(document_id)},
    )


def document_changed(tenant_id: object, document_id: object) -> Event:
    return Event(DOCUMENT_CHANGED, str(tenant_id), Audience.ADMINS, {"document_id": str(document_id)})


def message_created(tenant_id: object, conversation_id: object, owner_id: object | None) -> Event:
    return Event(
        MESSAGE_CREATED,
        str(tenant_id),
        Audience.OWNER_AND_STAFF,
        {"conversation_id": str(conversation_id)},
        owner_id=str(owner_id) if owner_id else None,
    )


def conversation_updated(tenant_id: object, conversation_id: object, owner_id: object | None) -> Event:
    return Event(
        CONVERSATION_UPDATED,
        str(tenant_id),
        Audience.OWNER_AND_STAFF,
        {"conversation_id": str(conversation_id)},
        owner_id=str(owner_id) if owner_id else None,
    )


def escalation_changed(tenant_id: object, conversation_id: object, ticket_id: object | None = None) -> Event:
    data = {"conversation_id": str(conversation_id)}
    if ticket_id:
        data["ticket_id"] = str(ticket_id)
    return Event(ESCALATION_CHANGED, str(tenant_id), Audience.STAFF, data)
