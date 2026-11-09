"""In-memory audit store: append-only rows, filtered by tenant the way the database query will be."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InMemoryAuditStore:
    rows: list[dict[str, Any]] = field(default_factory=list)
    received_units_of_work: list[object] = field(default_factory=list)

    def add(self, row: dict[str, Any], *, uow: object) -> None:
        self.received_units_of_work.append(uow)
        self.rows.append(dict(row))

    def for_tenant(self, tenant_id: object) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["tenant_id"] == str(tenant_id)]
