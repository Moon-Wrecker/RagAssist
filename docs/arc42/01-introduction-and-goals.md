# 1. Introduction and goals

**Type:** Architecture · **Audience:** architects, new engineers, reviewers · **Verified against:** `a989287`

**In plain English:** RagAssist answers customer-support questions for many companies in one system. Each answer comes from
that company's own documents. This page says what the system must do, who uses it, and which goals come first.

## 1.1 What the system does

RagAssist is a multi-tenant customer-support assistant. A [tenant](../glossary.md) is one company that uses the system.
Each tenant uploads its own documents. The assistant answers questions from those documents and cites its sources.

The assistant can also read and change account data in a SaaS product. A change needs approval from a person first.
When the assistant cannot answer, it hands the conversation to a human agent.

The system has these main functions:

| Function | What it does | Detail |
|---|---|---|
| Sign in and team management | Accounts, sessions, invite links, roles | [ADR 0007](../adr/0007-accounts-and-sessions.md) |
| Knowledge ingestion | Upload a file, parse it, split it into chunks, embed it, index it | [ADR 0003](../adr/0003-hybrid-chunking.md) |
| Retrieval | Find the best chunks with vector and keyword search, then rerank | [ADR 0005](../adr/0005-reranker-chain.md) |
| Assistant chat | A graph that guards, routes, retrieves, grades, generates and verifies | [ADR 0004](../adr/0004-decision-layer.md) |
| Account actions | Read account data. Change it after an admin approves. | [ADR 0006](../adr/0006-conversation-access-and-approval-binding.md) |
| Human handoff | Open a ticket, show the inbox, let an agent reply | [ADR 0008](../adr/0008-live-events-handoff-and-detached-turns.md) |
| Live events | Push changes to open browser tabs | [SSE contract](../api/sse-contract.md) |
| Web app | A React single-page app for chat, inbox, knowledge and team | [ADR 0009](../adr/0009-web-app.md) |

## 1.2 Users and roles

The system has three roles. The role comes from the signed token of the user.

| Role | Who | Can do |
|---|---|---|
| `user` | A customer of the tenant | Chat. See only the conversations of this user. |
| `agent` | A support person of the tenant | Use the inbox. Reply to escalated conversations. Resolve them. |
| `admin` | A manager of the tenant | Upload and delete documents. Manage the team. Approve account changes. Read `/metrics`. |

An `admin` can resolve an escalation but cannot reply to one. Only an `agent` can reply.

## 1.3 Quality goals

The table lists the top goals in priority order. Section [10](10-quality-requirements.md) gives the measures.

| Priority | Goal | What it means here |
|---|---|---|
| 1 | Tenant isolation | One tenant never sees the data of another tenant. Tenant leaks must be 0. |
| 2 | Grounded answers | The assistant answers from the documents. It does not invent facts. It escalates when it is not sure. |
| 3 | Safe actions | The assistant never changes account data without an approval that is bound to the exact call. |
| 4 | Resilience | A failed model, reranker or cache must not stop the system. The system uses a fallback. |
| 5 | Operability | A new engineer can start the full stack with one command. Logs, metrics and traces exist. |

## 1.4 Stakeholders

| Stakeholder | Expectation |
|---|---|
| Tenant admin | Easy upload, correct answers, control of the team and of the actions |
| Support agent | A clear inbox and a full conversation history before the first reply |
| Customer | Fast answers with sources. A human when the assistant cannot help. |
| Engineer | A layered code base with rules that tests enforce |
| Operator | Health checks, metrics, no secrets in the repository |
| Security reviewer | Isolation in the database, short-lived tokens, an audit trail for tool calls |

## 1.5 Scope of this description

This description covers the API, the worker, the database design, the platform adapters and the web delivery. It follows
[arc42](https://arc42.org) and uses the C4 views in the `c4/` folder. The words follow the [glossary](../glossary.md) and the
rules in the writing style guide.

The sections of this description:

1. Introduction and goals (this page)
2. [Constraints](02-constraints.md)
3. [Context and scope](03-context-and-scope.md)
4. [Solution strategy](04-solution-strategy.md)
5. [Building block view](05-building-block-view.md)
6. [Runtime view](06-runtime-view.md)
7. [Deployment view](07-deployment-view.md)
8. [Crosscutting concepts](08-crosscutting-concepts.md)
9. [Architecture decisions](09-architecture-decisions.md)
10. [Quality requirements](10-quality-requirements.md)
11. [Risks and technical debt](11-risks-and-technical-debt.md)
12. [Glossary](12-glossary.md)
