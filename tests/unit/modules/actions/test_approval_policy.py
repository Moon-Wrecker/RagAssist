"""Approval policy (plan section 7, "Write-tool approvals"): writes always need a human's approval,
reads never do, and the intent check can never replace approval."""

from __future__ import annotations

import pytest
from support.specs import need


def tool(name: str, *, is_write: bool):  # type: ignore[no-untyped-def]
    spec_cls = need("actions.ToolSpec")

    async def handler(principal, arguments):  # type: ignore[no-untyped-def]
        return None

    return spec_cls(
        name=name,
        description=name,
        input_schema={"type": "object"},
        is_write=is_write,
        handler=handler,
    )


class TestWrites:
    def test_a_write_tool_always_requires_approval(self) -> None:
        policy = need("actions.ApprovalPolicy")()
        assert policy.requires_approval(tool("update_billing_email", is_write=True)) is True

    def test_an_intent_check_that_says_the_user_asked_does_not_remove_approval(self) -> None:
        policy = need("actions.ApprovalPolicy")(intent_check=lambda *_: True)
        assert policy.requires_approval(tool("update_billing_email", is_write=True)) is True

    def test_an_intent_check_that_says_the_user_did_not_ask_still_requires_approval(self) -> None:
        policy = need("actions.ApprovalPolicy")(intent_check=lambda *_: False)
        assert policy.requires_approval(tool("update_billing_email", is_write=True)) is True


class TestReads:
    def test_a_read_tool_never_requires_approval(self) -> None:
        policy = need("actions.ApprovalPolicy")()
        assert policy.requires_approval(tool("get_invoices", is_write=False)) is False

    def test_a_read_tool_is_not_blocked_by_the_intent_check(self) -> None:
        policy = need("actions.ApprovalPolicy")(intent_check=lambda *_: False)
        assert policy.requires_approval(tool("get_invoices", is_write=False)) is False


class TestDecisionsAreStable:
    @pytest.mark.parametrize("is_write", [True, False])
    def test_the_same_tool_gets_the_same_answer_every_time(self, is_write: bool) -> None:
        policy = need("actions.ApprovalPolicy")()
        spec = tool("t", is_write=is_write)
        assert [policy.requires_approval(spec) for _ in range(3)] == [is_write] * 3
