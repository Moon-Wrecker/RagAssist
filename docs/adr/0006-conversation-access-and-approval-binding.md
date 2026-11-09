# ADR 0006: Per-User Conversation Access and Approval Bound to the Pending Action

## Context & Problem
Row-level security isolates tenants, but inside a tenant every conversation was reachable by every user, and the
approval endpoint accepted any `interrupt_id` for any conversation. After an approval the graph re-runs the account
agent node from the top; the call that executed came from a process-local cache, so a cache miss could execute
arguments the human never saw. A failed resume was reported as success and its result was dropped.

## Decision
1. **Ownership.** Conversations record their `user_id`. Plain users read, list and post only to their own;
   agents and admins see the tenant. Another user's conversation answers `404`. A conversation with no recorded
   owner is staff-only. The rule lives in `assistant/application/access.py`; stores filter in SQL
   (`owner_id`, `statuses`) before paging.
2. **Approval is bound to the checkpoint.** `interrupt_id` must be the interrupt the checkpoint is paused on
   (`409` otherwise). Only the owner or an admin may decide. The router reads the paused tool, arguments and call
   id from the checkpointed interrupt and passes them in the resume payload; the node executes exactly those.
   The in-process proposal cache is now bounded and only an optimisation.
3. **Fail closed.** If the write policy cannot be read, a human is asked. A caller who may not run a write tool is
   refused before any prompt (`ToolRegistry.authorize`).
4. **Honest outcomes.** A failed resume is `502` without internal detail; the resumed answer is persisted.
   Ingestion job rows store the stage and exception class, not the exception text; the SaaS client keeps
   upstream bodies out of messages and never invents a bearer token.

## Consequences
- **Positive:** users cannot read or approve each other's work; an approval cannot be redirected by a restart or a
  second worker; failures are visible without leaking internals.
- **Negative:** the SSE `interrupt` frame and the actions endpoint changed (see `docs/api/sse-contract.md`).
  Conversations created before ownership was recorded are visible to staff only.

## Consulted
LangGraph human-in-the-loop (`interrupt`, `Command(resume=...)`, `StateSnapshot.tasks[].interrupts[].id`),
FastAPI security tutorial, PostgreSQL row security policies (ADR 0002).
