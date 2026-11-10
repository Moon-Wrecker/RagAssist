# RagAssist documentation

**Type:** Reference · **Audience:** everyone who reads or writes RagAssist documentation · **Verified against:** `a989287`

**In plain English:** This is the front page of the documentation. Find the kind of help you need in the first table. Then follow the link. If you are new, start with the tutorial "Run the stack locally".

RagAssist is a support assistant for many customer companies. A customer asks a question. The assistant answers from that company's own documents and shows its sources. A person on the support team can take over. An administrator manages the documents and the team.

## Find the right page

The pages follow the Diátaxis method. Each page has one job. Pick the folder that matches what you need now.

| I want to… | Go to | What you get |
|---|---|---|
| **Learn** by doing, from the start | [Tutorials](tutorials/) | Numbered lessons. Each one ends with a result you can see. |
| **Do** one task | [How-to guides](how-to/) | Short steps for one goal. |
| **Look up** a fact | [Reference](reference/README.md) | Exact names, endpoints, settings, tables and rules. |
| **Understand** why it is built this way | [Explanation](explanation/) | Discussion, trade-offs and rejected options. |

## Tutorials

1. [Run the stack locally](tutorials/01-run-the-stack-locally.md)
2. [Create a workspace and sign in](tutorials/02-create-a-workspace-and-sign-in.md)
3. [Upload a document and ask a question](tutorials/03-upload-a-document-and-ask-a-question.md)
4. [Handle an escalation as an agent](tutorials/04-handle-an-escalation-as-an-agent.md)
5. [Follow a turn in Langfuse](tutorials/05-follow-a-turn-in-langfuse.md)

## How-to guides

**Operate**
[Configure LLM providers and fallbacks](how-to/configure-llm-providers-and-fallbacks.md) ·
[Configure tracing](how-to/configure-tracing.md) ·
[Manage the team and invites](how-to/manage-team-and-invites.md) ·
[Manage the knowledge base](how-to/manage-the-knowledge-base.md) ·
[Rotate secrets and use the secret guards](how-to/rotate-secrets-and-use-secret-guards.md) ·
[Deploy the web container](how-to/deploy-the-web-container.md) ·
[Troubleshoot common problems](how-to/troubleshoot-common-problems.md)

**Develop**
[Run the tests](how-to/run-the-tests.md) ·
[Develop the frontend](how-to/develop-the-frontend.md) ·
[Regenerate API types and OpenAPI](how-to/regenerate-api-types-and-openapi.md) ·
[Add an API endpoint](how-to/add-an-api-endpoint.md) ·
[Add a database migration with row-level security](how-to/add-a-database-migration-with-rls.md) ·
[Add an action tool with approval](how-to/add-an-action-tool-with-approval.md) ·
[Add a decider or a reranker](how-to/add-a-decider-or-reranker.md) ·
[Add an LLM provider](how-to/add-an-llm-provider.md)

## Reference

[API endpoints](reference/api-endpoints.md) ·
[Error responses](reference/error-responses.md) ·
[Configuration](reference/configuration.md) ·
[Models catalog](reference/models-catalog.md) ·
[Data model](reference/data-model.md) ·
[Command-line interface](reference/cli.md) ·
[Roles and permissions](reference/roles-and-permissions.md) ·
[Assistant graph](reference/assistant-graph.md) ·
[Ports and adapters](reference/ports-and-adapters.md) ·
[Frontend structure](reference/frontend-structure.md) ·
[CI and quality gates](reference/ci-and-quality-gates.md) ·
[Observability](reference/observability.md) ·
[Security controls](reference/security-controls.md)

Two older reference documents stay where they are: the [live-event and chat stream contract](api/sse-contract.md) and the [OpenAPI schema](api/openapi.json).

## Explanation

[Why a modular monolith](explanation/why-a-modular-monolith.md) ·
[Tenant isolation in depth](explanation/tenant-isolation-defence-in-depth.md) ·
[How an answer is made](explanation/how-an-answer-is-made.md) ·
[The decision layer](explanation/the-decision-layer.md) ·
[Retrieval and chunking](explanation/retrieval-and-chunking.md) ·
[Accounts, sessions and tokens](explanation/accounts-sessions-and-tokens.md) ·
[Human handoff and live events](explanation/human-handoff-and-live-events.md) ·
[Approvals and actions](explanation/approvals-and-actions.md) ·
[Provider abstraction and fallbacks](explanation/provider-abstraction-and-fallbacks.md) ·
[Observability and privacy](explanation/observability-and-privacy.md) ·
[The web app and its design system](explanation/the-web-app-and-design-system.md) ·
[Testing strategy](explanation/testing-strategy.md) ·
[Known limitations and roadmap](explanation/known-limitations-and-roadmap.md)

## Architecture description

The architecture is described twice. Use the one that fits your question.

- **[arc42](arc42/01-introduction-and-goals.md)** answers "what is the whole design?" in twelve fixed sections: goals, constraints, context, strategy, building blocks, runtime, deployment, crosscutting concepts, decisions, quality, risks and a glossary.
- **[C4 model](c4/README.md)** answers "what does it look like at this zoom level?" The pages go from system context, to containers, to components, to code, then to dynamic and deployment views. All diagrams are Mermaid, so they render on GitHub.
- **[Excalidraw drawings](diagrams/README.md)** are four hand-style overview pictures: system overview, tenant isolation, one assistant turn and the ingestion pipeline.
- **[Architecture decision records](adr/README.md)** hold the formal decisions, one file each.

## Words and meaning

The [glossary](glossary.md) is the single source for what each project word means. Read it first if a word is new.

## Write documentation

Follow the [writing style](contributing/writing-style.md). It joins ASD-STE100 (Simplified Technical English), Plain English, Diátaxis, arc42 and C4. This project writes in the style of ASD-STE100. It does not claim certification.

## Other documents

| Document | Use |
|---|---|
| [Testing notes](testing.md) | The tester's role and the test tiers |
| [Frontend to-do list](frontend/TODO.md) | The status of each frontend slice |
| [Repository rules](../AGENTS.md) | The mandatory rules for people and AI assistants |
| [Project README](../README.md) | The short project overview |
