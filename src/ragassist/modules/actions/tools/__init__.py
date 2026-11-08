"""Tool specifications and factory for SaaS and platform actions."""

from __future__ import annotations

from typing import TYPE_CHECKING
from ragassist.modules.actions.application import ToolSpec

if TYPE_CHECKING:
    from ragassist.modules.actions.adapters.saas_client import SaaSClient


def default_tools(saas: SaaSClient) -> list[ToolSpec]:
    """Build the production tool specs using the provided SaaSClient."""

    async def _handle_overview(principal, arguments):  # type: ignore[no-untyped-def]
        return await saas.get_overview(principal)

    async def _handle_subscription(principal, arguments):  # type: ignore[no-untyped-def]
        return await saas.get_subscription(principal)

    async def _handle_invoices(principal, arguments):  # type: ignore[no-untyped-def]
        return await saas.get_invoices(principal)

    async def _handle_update_billing_email(principal, arguments):  # type: ignore[no-untyped-def]
        return await saas.update_billing_email(principal, arguments["new_email"])

    async def _handle_query_dataset(principal, arguments):  # type: ignore[no-untyped-def]
        return {
            "status": "success",
            "query": arguments["query"],
            "dataset": arguments.get("dataset", "default"),
            "rows": [],
        }

    return [
        ToolSpec(
            name="get_account_overview",
            description="Retrieve account overview details (plan, status, billing contact) for current tenant.",
            input_schema={"type": "object", "properties": {}},
            is_write=False,
            handler=_handle_overview,
        ),
        ToolSpec(
            name="get_subscription",
            description="Retrieve subscription details, seat limits, and renewal dates for current tenant.",
            input_schema={"type": "object", "properties": {}},
            is_write=False,
            handler=_handle_subscription,
        ),
        ToolSpec(
            name="list_invoices",
            description="List past invoices, dates, amounts, and payment statuses for current tenant.",
            input_schema={"type": "object", "properties": {"month": {"type": "string"}}},
            is_write=False,
            handler=_handle_invoices,
        ),
        ToolSpec(
            name="get_invoices",
            description="Alias for list_invoices: retrieve invoices for current tenant.",
            input_schema={"type": "object", "properties": {"month": {"type": "string"}}},
            is_write=False,
            handler=_handle_invoices,
        ),
        ToolSpec(
            name="update_billing_email",
            description="Update the tenant billing email address for invoices and receipts.",
            input_schema={
                "type": "object",
                "properties": {"new_email": {"type": "string"}},
                "required": ["new_email"],
            },
            is_write=True,
            handler=_handle_update_billing_email,
        ),
        ToolSpec(
            name="query_dataset",
            description="Query tenant metrics or dataset items.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "dataset": {"type": "string"},
                },
                "required": ["query"],
            },
            is_write=False,
            handler=_handle_query_dataset,
        ),
    ]


__all__ = ["default_tools"]
