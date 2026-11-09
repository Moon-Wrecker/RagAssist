# ADR 0011: Admin Screens: Inbox, Knowledge Base and Team

## Context & Problem
Agents and admins need three screens on top of the existing API: an inbox of escalated conversations, a knowledge
base of uploaded documents with live indexing status, and team management (members, roles, invitations, one-time
links). They share the web app's rules (ADR 0009): server state only in TanStack Query, live events only mark
queries stale, monochrome status carried by shape and weight, glass surfaces, keyboard and screen-reader access.

## Decision
1. **Server state stays in the query cache.** Lists and details use the query keys that `useEvents` already
   invalidates (`escalations`, `conversation(id)`, `documents`, `ingestionJob(id)`), plus `teamInvites`. Nothing is
   copied into component state except drafts, dialogs and the upload queue.
2. **Optimistic updates through one hook** (`src/api/optimistic.ts`): cancel in-flight fetches, update every touched
   query, keep the previous values, roll back on error, invalidate on settle. Used for the agent reply (a pending
   message), resolve (thread and list), re-index, delete, role and status changes and invite revocation. The updates
   themselves are pure functions (`inbox-logic`, `documents-logic`, `team-logic`) with unit tests.
3. **Inbox.** The open thread is `?thread=<id>` so Back, reload and links work; below `lg` the thread replaces the
   list and a link goes back. `escalation_id` equals the conversation id, so a thread is `GET /v1/conversations/{id}`.
   Only the `agent` role may reply (`ReplyToEscalation` refuses admins with 403), so admins see the thread, can
   resolve it, and are told why the composer is absent. Resolving hands the conversation back to the assistant
   (ADR 0008); the UI says so next to the button.
4. **Knowledge base.** Client checks mirror the server (50 MiB per file, PDF, Markdown, HTML, CSV) and are decided by
   file extension, not the browser's MIME guess (a `.csv` can arrive as `application/vnd.ms-excel` on Windows); the
   upload re-wraps the file with the extension's MIME type, which is what the server's allow-list expects. The server
   still answers 413, 415, 403 and 400, and each is shown in plain words. Stage text (parsing, chunking, embedding,
   indexing) comes from the ingestion job for documents whose job id we know (started by upload or re-index in this
   session); every document also shows its own status.
5. **Failure reason in the document list.** `GET /v1/documents` now returns `error_message` per document (additive,
   nullable; the Postgres store already kept it on the document row). Without it the reason would be unrecoverable
   after a reload, because the list carries no job id. `openapi.json` and the generated types were regenerated.
6. **Team.** Uses the existing admin-only team API. Own row is read-only (the server refuses self changes). Deactivate
   asks first (it ends the member's sessions). Links from `POST /v1/team/invites` and `.../reset-link` are shown once
   in a dialog with a copy button; closing it discards the link, and the pending list shows only the address, kind,
   role and expiry. A lost link is revoked and recreated.
7. **Tables.** Plain `<table>` markup with explicit ARIA roles, a screen-reader caption and column headers. Below `sm`
   each row becomes a stacked block whose cells show their column name. Controls inside rows have accessible names
   that include the file or member. Tables live directly in a glass-1 container; no cards inside cards.
8. **Status without colour.** `StatusMark` is a pill with a shape (filled dot, dashed ring, hollow circle, check,
   cross, slash), weight, a dashed underline for failures, and always the word.
9. **Shape.** Following design feedback, containers and dialogs are `rounded-3xl`, buttons, tags and filter chips are
   pills, fields are `rounded-xl`, with generous row padding. This supersedes the "small radius" rule in the plan; the
   glass tokens themselves are shared with the chat screens.

## Consequences
- **Positive:** every change shows at once and recovers cleanly from a refusal; the inbox, knowledge and team pages
  need no new dependency; the failure reason survives a reload.
- **Negative:** the document list does not carry job ids, so a stage label appears only for jobs started in this
  session (a reloaded in-flight document shows its coarse status); the inbox shows the 100 most recently updated
  conversations and says so when there are more; there is no assignment of conversations to agents (plan assumption).
- **Testing:** Vitest for the pure logic, the optimistic hook and upload validation; mocked Playwright specs (no
  backend) for each flow at phone and desktop width in light and dark. The mocked event stream closes after every
  response, so a "live" frame is delivered on the next reconnect (about a second); the screen refetches after both a
  frame and a reconnect, so the specs prove the update arrives without user action, not which of the two caused it.

## Consulted
Installed package type declarations and behaviour were checked directly (TanStack Query v5 mutation callbacks and
`cancelQueries`/`setQueryData`, Radix Dialog focus handling and `onCloseAutoFocus`, React Router `useSearchParams`,
Playwright route interception, `setInputFiles` and `dispatchEvent` with a `DataTransfer`) together with the running
tests, and the backend routers and use cases for escalation, knowledge and team (reply role rule, upload limits and
allowed types, member self-change and last-admin rules). The documentation sites were not re-fetched while writing
this (network access was unreliable), so API usage is verified by types and tests, not by re-reading the docs.
Background: WAI-ARIA Authoring Practices for dialogs and live regions, MDN on the HTML drag and drop API and
`navigator.clipboard`, WCAG 2.2 (1.4.1 use of colour, 2.1.1 keyboard, 4.1.3 status messages).
