"""Application services and registries for tool actions, approval, and auditing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from ragassist.modules.actions.domain import ToolExecutionError, UnknownTool
from ragassist.shared.security.jwt import Principal, UserRole

SECRET_KEYS = {"password", "api_key", "token", "authorization", "secret"}


def _mask_secrets(data: Any) -> Any:
    """Recursively mask secrets in nested dictionary/list structures."""
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if str(key).lower() in SECRET_KEYS:
                result[key] = "***REDACTED***"
            else:
                result[key] = _mask_secrets(value)
        return result
    if isinstance(data, list):
        return [_mask_secrets(item) for item in data]
    return data


def _validate_schema(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    """Basic JSON-schema validation for tool arguments."""
    if not isinstance(arguments, dict):
        raise TypeError("Tool arguments must be a dictionary")

    required = schema.get("required", [])
    for field in required:
        if field not in arguments:
            raise ValueError(f"Missing required argument: {field}")

    properties = schema.get("properties", {})
    for field, val in arguments.items():
        if field in properties:
            prop = properties[field]
            expected_type = prop.get("type")
            if expected_type == "string" and not isinstance(val, str):
                raise TypeError(f"Argument '{field}' must be a string, got {type(val).__name__}")
            elif expected_type == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
                raise TypeError(f"Argument '{field}' must be an integer, got {type(val).__name__}")
            elif expected_type == "number" and (not isinstance(val, (int, float)) or isinstance(val, bool)):
                raise TypeError(f"Argument '{field}' must be a number, got {type(val).__name__}")
            elif expected_type == "boolean" and not isinstance(val, bool):
                raise TypeError(f"Argument '{field}' must be a boolean, got {type(val).__name__}")
            elif expected_type == "object" and not isinstance(val, dict):
                raise TypeError(f"Argument '{field}' must be an object, got {type(val).__name__}")
            elif expected_type == "array" and not isinstance(val, list):
                raise TypeError(f"Argument '{field}' must be an array, got {type(val).__name__}")


@dataclass
class ToolSpec:
    """Specification for an invocable tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    is_write: bool
    handler: Callable[[Principal, dict[str, Any]], Awaitable[Any]]


class ToolRegistry:
    """Registry of tool specifications with validation and tenant isolation."""

    def __init__(self, tools: Sequence[ToolSpec]) -> None:
        self._tools: dict[str, ToolSpec] = {t.name: t for t in tools}

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def is_write(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool.is_write if tool else False

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "is_write": t.is_write,
            }
            for t in self._tools.values()
        ]

    def authorize(self, name: str, principal: Principal) -> None:
        """Raise unless ``principal`` may run the tool. Checked before a human is asked to approve it."""
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownTool(f"Tool '{name}' is not recognized")
        if tool.is_write and getattr(principal, "role", None) != UserRole.ADMIN:
            raise PermissionError(f"Admin role required to execute write tool '{name}'")

    async def invoke(self, name: str, arguments: dict[str, Any], principal: Principal) -> Any:
        self.authorize(name, principal)
        tool = self._tools[name]
        _validate_schema(tool.input_schema, arguments)
        try:
            return await tool.handler(principal, arguments)
        except Exception as exc:
            if isinstance(exc, (UnknownTool, ValueError, TypeError, PermissionError)):
                raise
            raise ToolExecutionError(f"Error executing tool '{name}': {exc}") from exc


class ApprovalPolicy:
    """Policy for determining if tool execution requires human approval."""

    def __init__(self, intent_check: Callable[..., bool] | None = None) -> None:
        self.intent_check = intent_check

    def requires_approval(self, tool: ToolSpec | str | Any) -> bool:
        if hasattr(tool, "is_write"):
            return bool(tool.is_write)
        return False


class AuditLog:
    """Tenant-scoped audit logging for tool executions."""

    def __init__(self, store: Any) -> None:
        self.store = store

    async def record(
        self,
        principal: Principal,
        tool: str,
        arguments: dict[str, Any],
        *,
        approved: bool,
        outcome: str,
        uow: Any,
    ) -> dict[str, Any]:
        if uow is None:
            raise ValueError("A unit of work is required to record audit log")

        copied_args = copy.deepcopy(arguments)
        masked_args = _mask_secrets(copied_args)

        row = {
            "id": str(uuid4()),
            "tenant_id": str(principal.tenant_id),
            "user_id": str(principal.user_id),
            "tool": tool,
            "arguments": masked_args,
            "approved": approved,
            "outcome": outcome,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self.store.add(row, uow=uow)
        return row

    async def list_for_tenant(self, tenant_id: UUID | str) -> list[dict[str, Any]]:
        if hasattr(self.store, "for_tenant"):
            return self.store.for_tenant(str(tenant_id))
        return [r for r in getattr(self.store, "rows", []) if r.get("tenant_id") == str(tenant_id)]
