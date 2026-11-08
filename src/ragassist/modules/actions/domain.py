"""Domain models and exceptions for the actions bounded context."""

from __future__ import annotations

from ragassist.shared.domain import DomainError


class UnknownTool(DomainError):
    """Raised when an unrecognized tool is invoked."""


class ToolExecutionError(DomainError):
    """Raised when a tool execution fails."""
