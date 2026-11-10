# Add an action tool with approval

**Type:** How-to · **Audience:** a backend developer who gives the assistant a new ability · **Verified against:** `a989287`

**In plain English:** An [action tool](../glossary.md) is a function that the assistant can call on a customer account.
A read tool only looks at data. A write tool changes data, so a person must approve each call. This page shows how to add
a tool and how to make it ask for approval. Marking the tool as a write tool is what turns the approval on.

## Goal

Add one tool. If it changes data, the graph pauses and waits for an administrator before the tool runs.

## Before you start

- You know the terms [interrupt](../glossary.md), [approval](../glossary.md) and [Principal](../glossary.md).
- You read [ADR 0006](../adr/0006-conversation-access-and-approval-binding.md) and
  [approvals and actions](../explanation/approvals-and-actions.md).
- You know the existing tools in `src/ragassist/modules/actions/tools/__init__.py`. The read tools are
  `get_account_overview`, `get_subscription` and `list_invoices`. The write tool is `update_billing_email`.
- The tool calls the customer system through the client in `src/ragassist/modules/actions/adapters/saas_client.py`. The
  local test system is the `mock-saas` service in `services/mock_saas/`.

> **WARNING.** A model chooses the tool arguments. Treat them as untrusted input. Validate them in the handler. Never use
> an argument for `tenant_id`, `user_id` or `role`. Those come from the `Principal`.

## Steps

1. Add a method to the SaaS client for the new call. Use the `Principal` to scope the request. The client retries `GET`
   requests only. Do not make a write retry on its own.
2. Add the matching route to the mock service in `services/mock_saas/main.py`, so that tests and local runs work.
3. Write the handler in `modules/actions/tools/__init__.py`. Check the role when the action is sensitive:

   ```python
   async def _handle_close_account(principal, arguments):
       if getattr(principal, "role", None) != UserRole.ADMIN:
           raise PermissionError("Admin role required to close the account")
       return await saas.close_account(principal, _valid_reason(arguments["reason"]))
   ```

   The name `close_account` is an invented example.

4. Add a `ToolSpec` to the list that `default_tools(saas)` returns:

   ```python
   ToolSpec(
       name="close_account",
       description="Close the workspace account at the customer system.",
       input_schema={
           "type": "object",
           "properties": {"reason": {"type": "string"}},
           "required": ["reason"],
       },
       is_write=True,
       handler=_handle_close_account,
   )
   ```

   The five fields are `name`, `description`, `input_schema`, `is_write` and `handler`.

5. Set `is_write=True` for any tool that changes data. This one flag has two effects:

   - `ToolRegistry.authorize` demands the role `admin` for a write tool.
   - `ToolRegistry.is_write` returns true for the tool. The account agent node then calls `interrupt()` with the action
     `approval_required`, the tool name, the arguments and a `call_id`. The graph pauses. (`ApprovalPolicy` in
     `modules/actions/application.py` also reads `is_write`, but no production code calls it at this commit.)

6. Know that the audit wrapper in `runtime.build_tool_registry` writes an audit record for each call. You do not add it.
7. Know that `HIDDEN_TOOLS` in `src/ragassist/runtime.py` lists tools that exist in code and that the runtime does not
   offer. Do not add your tool there unless you want to hide it.
8. For a read tool, set `is_write=False`. It runs with no approval.
9. Rebuild the containers so that the image has the new code:

   ```bash
   docker compose up -d --build api worker mock-saas
   ```

10. Test the flow by hand. Sign in as an administrator. Ask the assistant to do the action. The chat shows an approval
    card with the buttons "Approve close_account" and "Deny close_account".
11. Select the button. The browser sends `POST /v1/conversations/{id}/actions/{interrupt_id}` with the body
    `{"approved": true}` or `{"approved": false}`. The call returns 409 if the decision does not match the pending
    interrupt of that conversation.
12. Write the tests:

    - A unit test of the handler and the argument checks.
    - A graph test that the write tool pauses and that a denial does not run it. See
      `tests/graph/test_approval_binding.py` and `tests/graph/test_interrupts_and_tenancy.py`.
    - A security test that a non-admin cannot run the write tool. See `tests/security/test_authz_and_tool_abuse.py`.
    - Use the fake tools in `tests/fakes/tools.py`.

## Check

- Before the approval, the mock service shows no change.
- After "Approve", the change is present and an audit record exists.
- After "Deny", the change is absent and the assistant says that it did not run.
- A signed-in customer who is not an admin cannot approve.

## Troubleshooting

- The tool never pauses. `is_write` is `False`, or the tool is in `HIDDEN_TOOLS`.
- The decision returns 409. The `interrupt_id` is old or belongs to another conversation. This is the binding that
  [ADR 0006](../adr/0006-conversation-access-and-approval-binding.md) describes.
- The assistant does not call the tool. The model sees only the `description` and `input_schema`. Make them exact.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Assistant graph](../reference/assistant-graph.md)
- [Roles and permissions](../reference/roles-and-permissions.md)
- [The SSE contract](../api/sse-contract.md)
