"""Recording tool registry for graph and action tests.

Every call is recorded with the tenant that the call ran for, so a test can prove that tools only
ever see the principal's tenant. Write tools are flagged, as the approval policy expects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Tool:
    name: str
    write: bool
    result: Any
    schema: dict[str, Any]


@dataclass
class RecordingToolRegistry:
    _tools: dict[str, _Tool] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)
    audit: list[dict[str, Any]] = field(default_factory=list)

    def add(
        self,
        name: str,
        *,
        write: bool = False,
        result: Any = None,
        schema: dict[str, Any] | None = None,
    ) -> None:
        self._tools[name] = _Tool(
            name, write, result if result is not None else {"ok": True}, schema or {}
        )

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "is_write": t.write, "input_schema": t.schema or {"type": "object"}}
            for t in self._tools.values()
        ]

    def get(self, name: str) -> _Tool | None:
        return self._tools.get(name)

    def is_write(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool.write if tool is not None else False

    async def invoke(self, name: str, arguments: dict[str, Any], principal: Any) -> Any:
        tool = self._tools[name]
        self.calls.append(
            {"name": name, "arguments": dict(arguments), "tenant_id": str(principal.tenant_id)}
        )
        self.audit.append(
            {"name": name, "tenant_id": str(principal.tenant_id), "user_id": str(principal.user_id)}
        )
        return tool.result

    def calls_named(self, name: str) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["name"] == name]
