# Excalidraw diagrams

**Type:** Reference · **Audience:** anyone who wants a picture of the system, authors who edit a diagram · **Verified against:** `a989287`

**In plain English:** This folder holds four free-form drawings. Each drawing has a text description below, so you can read
the content without opening the file. Each drawing also has a matching page in the [C4 model](../c4/README.md) with Mermaid
diagrams and full text.

## How to open a file

1. Open <https://excalidraw.com> in a browser.
2. Choose **Open** and pick one of the `.excalidraw` files in this folder. You can also open a file in the Excalidraw editor
   extension.
3. Edit the drawing if you need to. Save it in the same place with the same name.

Each file is JSON with `"type": "excalidraw"` and `"version": 2`. The boxes hold their text, and every arrow is bound to the
box at each end. When you move a box, its arrows follow.

## The four files

| File | What it shows | Matching C4 page |
|---|---|---|
| `system-overview.excalidraw` | The containers and what they talk to | [Containers](../c4/02-containers.md) |
| `tenant-isolation.excalidraw` | The path from the browser token to the database row | [Components of the api](../c4/03-components-api.md) and [dynamic views](../c4/08-dynamic-views.md), scenario 8 |
| `assistant-turn.excalidraw` | The graph nodes and edges of one turn | [Components of the assistant graph](../c4/04-components-assistant-graph.md) |
| `ingestion-pipeline.excalidraw` | Upload, queue, worker and live status | [Components of ingestion](../c4/05-components-ingestion.md) |

### `system-overview.excalidraw`

The drawing reads from left to right. On the left are four kinds of people: the customer user, the support agent, the
workspace admin and the operator. The first three reach the `web` container over HTTPS. `web` serves the React app and
proxies `/v1` to the `api` container. The `api` container runs the assistant graph (11 nodes). It calls the LLM and
embedding providers, `mock-saas` (account and helpdesk data) and, if enabled, Langfuse or LangSmith for traces. It reads and
writes `postgres` with pgvector (row-level security is forced on the tables). It puts files in S3 and messages in SQS
(LocalStack in development). The `worker` container receives SQS messages, reads the files, calls an embedding provider and
writes to `postgres`. The operator runs the `migrate` job (`ragassist db upgrade`), which writes the schema to `postgres`
with the owner role. For the container details see [page 02](../c4/02-containers.md).

### `tenant-isolation.excalidraw`

The top row reads from left to right and has seven boxes. The browser keeps the access token in memory only and sends it as a
bearer token. The `get_current_principal` dependency checks the signature and the expiry and builds a `Principal` with
`tenant_id`, `user_id` and `role`, taken from the token only. The use case in the application layer receives the tenant id.
It calls `ScopedDatabase.scope` (or `UnitOfWork`), which opens an explicit transaction. The first statement is
`set_config('app.tenant_id', tid, true)`, which has the same effect as `SET LOCAL`. PostgreSQL then applies the row-level
security policies, and the result holds only rows of that tenant. Five lower boxes show other places that repeat the rule
(defence in depth). Model output and tool arguments never set `tenant_id`. The retrievers repeat the filter
`(tenant_id = :tenant_id OR tenant_id IS NULL)`, so global rows stay visible. The graph `thread_id` is
`<tenant_id>:<conversation_id>`. The event filter `visible_to` checks the tenant first. Cache keys always contain the tenant
id. The drawing says that the thread id is checked against the store. In the code, the router builds the thread id inline and
loads the conversation with the tenant first. A helper `ensure_thread_access` exists in `thread_guard.py` and nothing calls it.
See [dynamic views, scenario 8](../c4/08-dynamic-views.md) and
[tenant isolation in depth](../explanation/tenant-isolation-defence-in-depth.md).

### `assistant-turn.excalidraw`

The drawing shows the 11 graph nodes as boxes and the edges as arrows with their conditions. The turn starts with the
question and the principal. `guard_input` sends a safe input to `router`. It sends an unsafe input straight to `finalize`
("blocked"). `router` chooses one of four routes: `rag_search` goes to `rewrite`, `general_chat` goes to `generate`,
`saas_action` goes to `account_agent` and `human_escalation` goes to `escalate`. The search path runs `rewrite`,
`hybrid_retrieve` (vector and keyword search joined by RRF), `rerank` (top 4) and `grade_relevance`. Relevant passages go to
`generate`. Otherwise the graph retries and then goes to `escalate`. `generate` goes to `verify_grounding`. A grounded answer
goes to `finalize`. An answer that is not grounded goes back to `generate` once more and then to `escalate`. `account_agent`
can call `interrupt()`. The checkpoint store (`AsyncPostgresSaver`) saves the state. A later `POST .../actions/<id>` resumes
the graph with `Command(resume)`. `finalize` sends the `citation` and `done` events. The browser receives `token`,
`citation` and `done` frames. For the full edge table see [page 04](../c4/04-components-assistant-graph.md).

### `ingestion-pipeline.excalidraw`

The top row runs from left to right. The workspace admin chooses a file. The `web` container posts it to
`POST /v1/documents`. The `api` container runs `UploadDocument`. It puts the file in the S3 object store under
`tenants/<id>/documents`, writes the job and document rows to `postgres`, and sends the queue message after the commit. The
`worker` receives the message and runs `ProcessIngestionJob`. The middle row runs from right to left. The worker reads the
file from S3, picks a parser by MIME type (Markdown, HTML, PDF or CSV), cuts the blocks into chunks with `HybridChunker` (5
passes), and gets the vectors from `EmbeddingService` (a fallback chain). It then writes the chunks and vectors to `postgres`
with `replace_chunks`. The last row shows the live status. `postgres` sends a `NOTIFY`. The API listener (`PostgresEventBus`
and its hub) sends an event with ids only to the web app over SSE. The web app refetches the document list. See
[page 05](../c4/05-components-ingestion.md) and [dynamic views, scenario 6](../c4/08-dynamic-views.md).

## Notes for authors

- The files were produced by a small generator script and then checked: each arrow binding points to an existing element, no
  text overflows its box and no arrow crosses an unrelated box. Unverified: the generator script is not in the repository. If
  you edit a drawing in Excalidraw, keep arrows bound to the boxes.
- Keep a drawing to about 10 to 16 boxes. Split it when it grows.
- Do not write secrets, real hosts or ports in a drawing. Use setting names.
- When a drawing changes, update its description in this page and the matching C4 page.
- The writing rules are in [writing style](../contributing/writing-style.md).
