# 9. Architecture decisions

**Type:** Architecture · **Audience:** architects, engineers, reviewers · **Verified against:** `a989287`

**In plain English:** Each big decision has an ADR (Architecture Decision Record) in `docs/adr/`. This page lists all
16 in one table. Read the ADR to learn the reason. Do not repeat the reason in other pages.

## 9.1 Decision list

| ADR | Decision | Area | Section |
|---|---|---|---|
| [0001](../adr/0001-pgvector-unified-storage.md) | Store rows, vectors and keyword indexes in one PostgreSQL database with pgvector | Storage | [4](04-solution-strategy.md), [5](05-building-block-view.md) |
| [0002](../adr/0002-row-level-security.md) | Enforce tenant isolation with forced row-level security (RLS) | Security | [8.1](08-crosscutting-concepts.md) |
| [0003](../adr/0003-hybrid-chunking.md) | Split documents with a 5-pass hybrid chunker | Ingestion | [6.3](06-runtime-view.md) |
| [0004](../adr/0004-decision-layer.md) | Use a decision layer with confidence-gated chains for routing, safety, grading and grounding | Assistant | [5.7](05-building-block-view.md) |
| [0005](../adr/0005-reranker-chain.md) | Rerank with a toggleable chain that falls back | Retrieval | [8.8](08-crosscutting-concepts.md) |
| [0006](../adr/0006-conversation-access-and-approval-binding.md) | Give each conversation one owner. Bind an approval to the checkpoint. | Security | [6.2](06-runtime-view.md) |
| [0007](../adr/0007-accounts-and-sessions.md) | Use argon2id, short access tokens, rotating refresh tokens and invite links | Identity | [8.2](08-crosscutting-concepts.md) |
| [0008](../adr/0008-live-events-handoff-and-detached-turns.md) | Push events with `LISTEN` and `NOTIFY`. Hand off to humans. Run turns detached. | Assistant | [6.1](06-runtime-view.md), [6.6](06-runtime-view.md), [6.7](06-runtime-view.md) |
| [0009](../adr/0009-web-app.md) | Build a React single-page app | Web | [7](07-deployment-view.md) |
| [0010](../adr/0010-chat-ui.md) | Design the chat UI | Web | none |
| [0011](../adr/0011-admin-screens.md) | Design the admin screens | Web | none |
| [0012](../adr/0012-langfuse-tracing.md) | Trace with Langfuse | Observability | [8.9](08-crosscutting-concepts.md) |
| [0013](../adr/0013-gemini-provider.md) | Add Gemini as a model provider | Models | [8.8](08-crosscutting-concepts.md) |
| [0014](../adr/0014-web-delivery.md) | Serve the app with nginx-unprivileged on one origin | Deployment | [7](07-deployment-view.md) |
| [0015](../adr/0015-caching.md) | Cache embeddings, verdicts and retrieval results. Add `ETag` and shared counters. | Performance | [8.7](08-crosscutting-concepts.md) |
| [0016](../adr/0016-liquid-redesign.md) | Redesign the web app with a "liquid" glass look | Web | none |

## 9.2 Amendments

[ADR 0004](../adr/0004-decision-layer.md) has an amendment. It says:

- A failed predicate raises an error. It does not return a default.
- There is one LLM decider for each model in the role chain.
- Each LLM decider has `max_retries=1`.
- The `rules` decider stays last in the default chains.

## 9.3 Differences between an ADR and the code

The code differs from the text of some ADRs. Section [11](11-risks-and-technical-debt.md) holds the full list.

| ADR | Text says | Code does |
|---|---|---|
| 0002 | The policies allow `OR tenant_id IS NULL` | Only the read policies on `documents` and `chunks` allow it. The write policies are tenant-only. |
| 0003 | An exact tokenizer counts tokens | `RegexTokenCounter` estimates the count. |
| 0009 and 0016 | The serif font is Instrument Serif (0009) or Geist Serif (0016) | `package.json` holds `@fontsource/instrument-serif`. |
| 0011 | The admin screen shows the stage text of a job | The worker saves only `parsing`, `completed` and `failed`. |

## 9.4 How to add a decision

1. Copy the format of an existing ADR.
2. Give the ADR the next number.
3. Add it to `docs/adr/README.md` and to the table above.
4. Update the arc42 sections that the decision changes.
