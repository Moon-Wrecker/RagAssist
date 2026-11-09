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

## Client Disconnect & Cleanup

When a client closes the HTTP connection, the server's async generator catches `GeneratorExit` / `asyncio.CancelledError`, cancels the underlying LangGraph task, and releases resources without leaking internal state.
