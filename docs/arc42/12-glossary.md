# 12. Glossary

**Type:** Architecture · **Audience:** everyone who reads the documentation · **Verified against:** `a989287`

**In plain English:** The full list of terms is in [the glossary](../glossary.md). This page repeats the ten terms that
you need most to read the other arc42 pages.

## 12.1 The ten most important terms

| Term | Meaning in RagAssist |
|---|---|
| Tenant | One company that uses the system. Its data is isolated from all other tenants. |
| Principal | The verified identity in the JWT: `tenant_id`, `user_id` and `role`. |
| RLS (row-level security) | A PostgreSQL feature. The database hides rows that do not belong to the tenant in `app.tenant_id`. |
| Unit of work | The code block that opens a transaction and sets `app.tenant_id` before any query on tenant tables. |
| Chunk | A part of a document with a vector and a keyword index. Retrieval returns chunks. |
| Hybrid retrieval | A search that joins vector search and keyword search with reciprocal rank fusion (RRF). |
| Decider | A component that answers a yes or no question, a choice or a score. A chain of deciders gives a result with a confidence value. |
| Escalation | The handoff of a conversation to a human agent. It opens a ticket. |
| Interrupt | The pause of the graph at a write action. An approval resumes the exact checkpointed call. |
| SSE (server-sent events) | The one-way stream from the API to the browser. It carries chat frames and live events. |

## 12.2 Where to go next

- The full list: [glossary](../glossary.md).
- The reason for each decision: [section 9](09-architecture-decisions.md).
- The stream format: [SSE contract](../api/sse-contract.md).
