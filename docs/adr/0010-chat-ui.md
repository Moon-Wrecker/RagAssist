# ADR 0010: Chat UI: a Pure Stream Reducer, Sanitised Markdown and Inline Approval

## Context & Problem
The chat screen shows text that nobody on the client side wrote: the model's answer and the document passages behind
it. It must stream without redrawing the page for every token, keep working when the person stops, switches
conversation or an agent takes over, and put an account-changing action in front of the person before it runs.

## Decision
1. **Stream over `fetch`, parse with `eventsource-parser`, feed a pure reducer.** `POST /v1/conversations/{id}/messages`
   is read with `fetch` (so the bearer token and the single-flight refresh still apply) and parsed by
   `createParser` into typed events (`token`, `reset`, `citation`, `tool_call`, `interrupt`, `escalated`, `done`,
   `error`). Unknown events and malformed payloads are dropped, so a newer server cannot break an older client. The
   reducer (`features/chat/turn.ts`) has no React and no I/O and is unit-tested.
2. **Tokens are batched per animation frame.** `createFrameBatcher` collects text and hands it over once per
   `requestAnimationFrame`. Any non-token event flushes first, so state changes always see all text; `reset` discards
   the pending text, as the answer restarts.
3. **The server stays the source of truth for saved messages.** Messages, history and status are TanStack Query
   state, kept fresh by the live-event invalidation of ADR 0009 (`message.created`, `conversation.updated`). The
   reducer holds only the live turn. It is displayed after the first `baseCount` saved messages and gives way once
   the saved list holds what the turn showed (`isSuperseded`), so a refetch during a stream never shows the question
   twice and a stopped turn is replaced by the answer the server finishes. A failed turn stays until the person acts.
4. **Stop only abandons the wait.** It aborts the fetch; the server finishes and saves the turn (ADR 0008). Retry
   resends the question, which may leave the first attempt in the history.
5. **Model and document text is untrusted.** Answers are rendered with `react-markdown` and `rehype-sanitize`
   (default schema), with no `rehype-raw`: raw HTML is never parsed, scripts and event handlers cannot appear,
   links are limited to `http`, `https`, `mailto`, `irc`, `ircs` and `xmpp` (no `javascript:` or `data:`), images are
   disallowed (a remote image is a request the text's author controls) and links open with `noopener noreferrer`.
   Passages from `GET /v1/chunks/{id}` are shown as plain text, never parsed. `[n]` markers become buttons for the
   n-th citation of the message (the generator numbers its context passages from 1); a marker with no matching
   citation stays text.
6. **Approval is inline and exact.** The card shows the tool and every argument as the server stored them with the
   interrupt, and posts only the decision (`approved`) to `POST .../actions/{interrupt_id}`; which action runs is
   fixed server-side (ADR 0006). The composer is read-only while the card is open. The outcome stays in the thread
   as a note. A `409` is shown as "no longer waiting".
7. **Handoff.** While the conversation status is `escalated` the composer addresses the support agent, the assistant
   is silent, and messages use the same endpoint (the server answers `escalated` then `done`, no tokens). Agent
   replies and the return to the assistant after resolving arrive through the existing event invalidation.
8. **A new conversation is created first** (`POST /v1/conversations`, titled from the first line of the message) and
   its id goes into the address (`?c=`), so a reload and the back button keep it.
9. **Look.** The user's turn is a softly rounded translucent block aligned right and the assistant's turn is
   document-like, so the two sides are not mirrored bubbles. Glass panels are rounded (`rounded-3xl`), the composer is
   a pill with a round send button, citation chips and tags are pills, and the citation panel is a floating side
   panel on desktop and a bottom sheet on phones. The shared radius token went from 0.25rem to 0.5rem, the backdrop
   shapes got a little more tonal range and a tighter blur, and the glass shadow is larger and softer, so glass
   reads as glass; the contrast test still passes on both themes.

## Consequences
- **Positive:** the stream logic, batching and sanitisation are testable without a browser; a stream can end any way
  (done, error, drop, abort, switch) without leaving the UI in a half state.
- **Negative:** a pending approval is known only to the tab that received the `interrupt` frame (the API exposes no
  pending-action lookup), so after a reload the card is gone and the person must ask again. Handoff and decision
  notes are kept in memory for the session. History filtering sees only the 50 loaded conversations. Staff who open
  Chat see the tenant's conversations, as the list endpoint returns them.

## Consulted
Installed type declarations and source were read directly: `eventsource-parser` 4.1.2 (`createParser`, `onEvent`),
`react-markdown` 10.1.0 (`components`, `disallowedElements`, handling of `raw` nodes: shown as text unless `skipHtml`),
`rehype-sanitize` 6.0.0 and `hast-util-sanitize` default schema (protocol allow-list, `script` stripped, `id`
clobbering), `remark-gfm` 4.0.1, Radix Dialog (`modal`, `onInteractOutside`, `onCloseAutoFocus`). Behaviour was then
checked by the unit tests (a `<script>` and a `javascript:` link in model text do not render) and the mocked
Playwright specs. The documentation sites were not re-fetched while writing this, so API usage is verified by types
and tests, not by re-reading the docs. Contract: `docs/api/sse-contract.md`; backend behaviour read in
`modules/assistant/api/router.py`.
