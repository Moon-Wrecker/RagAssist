# Server-Sent Events (SSE) Streaming API Contract

RagAssist provides real-time streaming of assistant responses and citations using the W3C WHATWG Server-Sent Events standard.

## Headers

The streaming endpoint (`POST /v1/conversations/{conversation_id}/messages` with `Accept: text/event-stream` or `stream: true`) sets the following contract headers:

```http
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

- `X-Accel-Buffering: no` ensures reverse proxies (e.g., NGINX) disable response buffering and flush chunks immediately.
- `Cache-Control: no-cache` prevents HTTP caches and intermediate proxies from storing streaming output.

## Heartbeats (Keep-Alive)

To prevent idle connection timeouts across proxies and load balancers, the server emits a comment frame every 15 seconds when no token is ready:

```sse
: ping
```

Per the WHATWG EventSource specification, lines starting with a colon `:` are ignored by client event parsers and do not trigger DOM events.

## Event Types & Framing

Each event consists of `event: <name>`, followed by `data: <json>`, terminated by an empty line (`\n\n`).

### 1. `token`
Streamed token chunks of the assistant's answer as they are generated.

```sse
event: token
data: {"text": "According"}

event: token
data: {"text": " to the"}
```

When the graph regenerates the answer (for example after a failed grounding check) it first sends a token event with
`"reset": true` and empty text. The client discards the text it has shown so far and starts again from the next token.

```sse
event: token
data: {"text": "", "reset": true}
```

### 2. `citation`
Emitted as citations for retrieved document chunks are finalized (prior to `done`).

```sse
event: citation
data: {"chunk_id": "chunk-102", "document_id": "doc-45", "title": "Billing FAQ", "page": 3, "heading_path": ["Billing", "Refunds"]}
```

### 3. `tool_call`
Emitted when an agent invokes a registered tool.

```sse
event: tool_call
data: {"tool": "get_subscription", "arguments": {}}
```

### 4. `interrupt`
Emitted when the turn pauses on a write action that needs human approval. The frame carries the id of the
interrupt the conversation is paused on and the call the human is asked to approve. The stream then ends with
`done` and `"status": "interrupted"`.

```sse
event: interrupt
data: {"interrupt_id": "9f2c...", "action": "approval_required", "tool": "update_billing_email", "arguments": {"new_email": "new@example.com"}, "call_id": "call_1"}
```

Resolve it with `POST /v1/conversations/{conversation_id}/actions/{interrupt_id}` and a body of
`{"approved": true}` or `{"approved": false}` (optional `reason`):

- The decision is bound to the pending interrupt. An `interrupt_id` that is not the one the conversation is
  paused on (or a conversation with nothing pending, or one already decided) answers `409`.
- What runs on approval is the tool and arguments stored with the interrupt, never anything in the request.
- Only the conversation's owner or an admin may decide: another user of the tenant gets `404`, an agent who
  is not the owner gets `403`.
- `200` with `"status": "resumed"` carries the assistant's `answer` (also saved to the conversation). A new
  pause answers `"status": "interrupted"` with the next `interrupt`. If resuming fails the answer is `502`.

### 5. `escalated`
Emitted when query confidence is below threshold or when the conversation is escalated to human support.

```sse
event: escalated
data: {"ticket_id": "TICK-0001", "status": "open", "priority": "high"}
```

### 6. `done`
Emitted as the terminal event of every completed stream.

```sse
event: done
data: {"conversation_id": "conv-uuid", "status": "completed"}
```

### 7. `error`
Emitted upon an unhandled exception. The error payload is sanitized and never exposes stack traces or secret keys.

```sse
event: error
data: {"code": "internal_error", "message": "An error occurred during processing."}
```

## Client Disconnect and Persistence

Closing the connection (for example the Stop button aborting the request) does **not** cancel the turn. The graph runs
in a task that is detached from the HTTP response: it finishes, saves the assistant message, opens the helpdesk ticket
when the turn escalated, and then publishes a `message.created` event (see `GET /v1/events`). The client that stopped
watching refetches `GET /v1/conversations/{conversation_id}` to see the saved answer. If the turn itself fails, the
failure is logged and nothing partial is saved.

## Human Handoff

While a conversation is `escalated` (a ticket is open) the assistant is silent: `POST
/v1/conversations/{conversation_id}/messages` saves the customer message, does **not** run the graph, and answers
with a defined result. A support agent replies through `POST /v1/escalations/{id}/reply`. Resolving the escalation
(`POST /v1/escalations/{id}/resolve`) sets the status to `resolved`; the next customer message goes to the assistant
again, and a new escalation then opens a new ticket.

- Streaming (`Accept: text/event-stream`): no `token` events; one `escalated` event with the open ticket (when the
  ticket id is known), then `done`.

```sse
event: escalated
data: {"ticket_id": "TICK-0001", "status": "open", "priority": "high"}

event: done
data: {"conversation_id": "conv-uuid", "status": "escalated"}
```

- JSON: `200` with `{"conversation_id": "...", "answer": "", "citations": [], "route": "human_handoff", "status": "escalated"}`.

The agents and the customer's other tabs learn about the new message through `message.created` and
`escalation.changed` on `GET /v1/events`.

## Passages: `GET /v1/chunks/{chunk_id}`

Loads the passage behind a citation. Any signed-in user of the tenant may read a chunk of their tenant or a global one
(shared knowledge, `tenant_id` is null). A chunk of another tenant and an unknown id are both `404`.

```json
{
  "chunk_id": "chunk-102",
  "document_id": "doc-45",
  "document_title": "Billing FAQ",
  "title": "Refunds",
  "text": "Refunds are issued within 5 business days...",
  "page": 3,
  "heading_path": ["Billing", "Refunds"],
  "is_global": false
}
```

`page` is `null` when the source has no pages; `heading_path` may be empty.

## Live Events: `GET /v1/events`

A long-lived SSE stream of change notifications. `Authorization: Bearer <access token>` is required, so use a
fetch-based reader (`EventSource` cannot send the header). Headers are the same as the streaming endpoint above;
`: ping` comments arrive every 15 seconds.

**Events carry only a type and ids, never content.** On an event the client refetches the resource through the normal
API (which enforces tenant, owner and role again). There is no replay: events published while a client was
disconnected are lost, so the client must invalidate everything after every reconnect.

Frame format is the same as everywhere else: `event: <type>`, `data: <json>`, blank line.

| Event | Payload | Sent to | Meaning |
|---|---|---|---|
| `ready` | `{}` | the connection | The subscription is active. Sent first on every connection. |
| `job.updated` | `{"job_id", "document_id"}` | admins of the tenant | An ingestion job changed state (queued, running, retried, completed, failed). |
| `document.changed` | `{"document_id"}` | admins of the tenant | A document was added, deleted or finished (re)indexing. |
| `message.created` | `{"conversation_id"}` | the conversation owner, agents and admins of the tenant | A message was saved that the client may not have: an agent reply, a customer message during handoff, or an assistant turn that finished (also after the client stopped watching). |
| `conversation.updated` | `{"conversation_id"}` | the conversation owner, agents and admins of the tenant | The conversation status changed (`open`, `escalated`, `resolved`). |
| `escalation.changed` | `{"conversation_id"}` (plus `"ticket_id"` when a ticket was opened) | agents and admins of the tenant | The escalation inbox changed: new escalation, new customer message in an escalated thread, or resolved. |
| `resync` | `{}` | the connection | The server may have dropped events (slow reader or lost database listener). Invalidate everything and refetch. The stream stays open. |
| `reauth` | `{}` | the connection | The access token has expired. The server ends the stream right after this frame. Refresh the token and reconnect. |

```sse
event: ready
data: {}

event: message.created
data: {"conversation_id": "conv-uuid"}

: ping

event: reauth
data: {}
```

Rules:

- The server filters by tenant, owner and role before anything is written to the stream; a client never receives an
  event for another tenant, or for another user's conversation unless it is an agent or admin.
- The stream ends with `reauth` at the exact expiry of the access token it was opened with.
- Each user may hold a limited number of concurrent streams per API process (default 5); more answer `429`.
- The endpoint is exempt from the per-address rate limit.
- Each subscriber has a bounded queue. If it overflows (slow client) or the server loses its database listener, the
  queue is dropped and the client receives `resync`.
