# Known limitations and roadmap

**Type:** Explanation · **Audience:** engineers, reviewers and product owners who want an honest list of what is missing, weak or unproven · **Verified against:** `a989287`

**In plain English:** Every system has gaps. This page lists the ones that the documentation team found at this commit.
It groups them by how much they matter and says which are facts, which need checking and which are only plans. A
roadmap here is a list of candidates in a sensible order. It is not a promise.

## How to read this page

Each item has a source. Items marked **Unverified** came from reading code and were not run. The full tables of risks (R1
to R13) and debt (D1 to D22) live in [arc42 section 11](../arc42/11-risks-and-technical-debt.md). This page explains the
ones that change how you should use or trust the system, and links back for the rest.

## Open items that the team named

These four items are open on purpose and the team knows them.

| Item | What is open | Effect |
|---|---|---|
| Real-stack smoke run | The redesigned web app passes its mocked end-to-end tests. A run against the real API, database, queue and model providers is still owed. | A defect that only the real stack shows may be hidden. |
| Embeddings in the container | When the call to the first embedding provider fails and the optional `[ml]` extra is not installed, the local fallback cannot load. Embeddings are then unavailable. (D20) | Vector search stops. The retriever may continue with keyword search only. |
| Logo | Three concepts sit in `docs/frontend/logo-concepts/`. None is chosen. | The app uses a plain wordmark component for now. |
| CSP `style-src 'unsafe-inline'` | The content security policy still allows inline styles. (R11) | A weaker policy for styles. Scripts are still restricted. |

## Safety and trust

- **Personal data goes to providers and, with tracing on, to the tracing service.** Credential masking exists. Masking of
  personal data does not. See [observability and privacy](observability-and-privacy.md). (R2)
- **A disabled user keeps a valid access token until it expires.** The default is 15 minutes. The signing key is
  symmetric, so every verifier holds it. See [accounts, sessions and tokens](accounts-sessions-and-tokens.md). (R1)
- **No multi-factor authentication and no self-service reset.** An admin issues each reset link. (R3)
- **The rate limit is fixed in code** at 300 requests per 60 seconds, and login throttle counters are per process unless
  the cache is Redis. (R4)
- **API documentation routes are always on.** nginx hides them, but a direct call to the API shows them. (R5)
- **The decider floor is weak.** The `rules` decider cannot make a real grounding judgement, and it cannot stop a
  clever injection. The design relies on the walls behind it. See [the decision layer](the-decision-layer.md).
- **An answer that failed grounding can stay visible.** After two failed checks the `escalate` node keeps the existing
  text. This is a code observation. Unverified at runtime.

## Correctness that needs checking

These are reading-based findings. Each needs a run to confirm.

- **The agent may never receive its tools.** In `runtime.build_runtime`, tools are bound into `agent_tiers` and passed to
  `build_graph`. The function takes `**kwargs` and ignores that name. The `account_agent` node uses `generator_tiers`,
  which have no tools, and only the first model. If true, the approval path is reached only in tests that supply their
  own tiers. See [approvals and actions](approvals-and-actions.md). This is the most important item on this page to confirm.
- **The complexity scale may not match the tier line.** The question names levels 1, 3 and 5. The model-backed adapter
  returns a number up to 1.0. The tier rule uses 2.0 as the line. Every question may then pick the cheap tier. See
  [the decision layer](the-decision-layer.md).
- **Role temperature and token limits are not applied to generation.** The graph builds chat models with only the model
  id. See [provider abstraction and fallbacks](provider-abstraction-and-fallbacks.md).
- **A fallback embedding lives in another vector space.** Projection to the column size keeps it running and lowers
  quality. See [retrieval and chunking](retrieval-and-chunking.md).

## Settings and code that do nothing

The documentation team found settings and code that look active and are not. Treat them as not working.

| Item | Detail |
|---|---|
| `CHUNK_OVERLAP_TOKENS` | Stored by the chunker and used by no pass. There is no overlap. |
| `CHUNK_STRATEGY`, `VECTOR_SEARCH_TOP_K`, `KEYWORD_SEARCH_TOP_K` | Not read. The graph uses fixed sizes: retrieve 6, keep 4. (D7, D14) |
| `rewrite` node | Counts attempts and appends a word. It makes no model call. |
| `RegexTokenCounter` | An estimate, about 10 to 20 percent above a byte-pair count. ADR 0003 says "exact tokenizer". (D8) |
| `thread_guard` helpers | Used only by tests. The router builds the thread id inline. (D9) |
| `decision` reranker name | Not known to the chain builder. (D10) |
| `query_dataset` tool | A stub that raises. (D19) |
| `claude-haiku-5-5` pricing | The YAML has two `pricing` keys. (D12) |
| Memory container | Asks for roles that do not exist and falls back to hard-coded values. (D4, D5) |

## Operations

- **CPU work on the event loop.** The PDF parser, the chunker and the token counter run inline, against the rule in
  `AGENTS.md`. A large upload can slow the worker. (D1)
- **Job stages.** The worker never writes the `chunking`, `embedding` and `indexing` statuses, so the admin screen shows
  fewer stages than ADR 0011 describes. (D2)
- **No signal handling in the worker.** A stop ends the process at once. SQS delivers an unfinished message again. (R12)
- **Compose holds deployment values and open ports.** This conflicts with the no-hardcoded-values rule, and two ports bind
  without the loopback address. (D15, R7)
- **A clean image build may fail** because the `api` image copies a folder that is not in git. Unverified. (R8)
- **The development token command has no environment gate.** (R10)

## Quality and testing

- **Offline evals are a simulation.** The perfect scores in `evals/reports/eval_summary.md` are not evidence of real
  quality. See [testing strategy](testing-strategy.md).
- **The `docs/testing.md` baseline is stale.** It names 70 expected failures, but the defect registry is empty at this
  commit. A stale integration docstring still mentions DEFECT-09.
- **Coverage is below the gate.** The measured value was 82.4 percent against 85, and the gate is advisory.
- **Frontend CI is suspended** unless `RUN_FRONTEND_CI` is `true`. (D21)
- **The generic row-level security matrix covers two tables.** The rest rely on store tests.
- **The `import-linter` contract is narrow.** The real layer rules run as a hygiene test. (D16)
- **A cycle between two modules.** Assistant and escalation depend on each other. (R9)

## Web app

From the redesign branch and [the web app page](the-web-app-and-design-system.md):

- no real-stack run of the new pages and no performance numbers for real devices
- `staleTime` and prefetch are not tuned
- the refraction effect and the edge fade were dropped
- long tables are not virtualised
- the per-user event cap is per process when Redis serves the cache
- a pending approval card is lost on a page reload (the checkpoint still waits)

## Documentation mismatches

These are places where two documents, or a document and the code, disagree. This documentation follows the code.

| Where | Mismatch |
|---|---|
| `README.md` | Old node names, tools that do not exist, JSON and TXT uploads that the API rejects, and 768-dimension embeddings. The code uses 1536. (D22) |
| ADR 0016 | Names the display font Geist Serif. The code, `package.json` and ADR 0009 say Instrument Serif. |
| ADR 0003 | Says exact tokenizer and a chunking library. The code uses an estimate and its own passes. |
| `docs/testing.md` | The baseline does not match the empty defect registry. |

## Roadmap candidates

The order follows risk, not effort. Nothing here is scheduled.

1. **Confirm the agent tool path.** Run a live turn for the `saas_action` route. Fix the `agent_tiers` hand-over if the
   reading is right. Add a graph test that fails when tools are missing.
2. **Run the real-stack smoke test** for the sign-in, chat, approval, handoff and inbox flows. Record the result.
3. **Decide the privacy posture for traces.** Add personal-data masking, or document a rule to keep tracing off for
   regulated tenants.
4. **Fix the complexity scale** so the tier rule and the score agree. Add a test that picks both tiers.
5. **Clean the silent settings.** Remove the unused ones or wire them in. Wire overlap into the chunker or remove the
   setting. Keep `.env.example` in step.
6. **Move CPU work to the bounded executor** for the parser, the chunker and the counter.
7. **Account hardening.** Multi-factor sign-in, a self-service reset flow, rate limits as settings, and a way to cut off
   a disabled user at once if the risk needs it.
8. **Worker robustness.** Signal handling, the missing job stages and a claim timeout setting.
9. **Close the test gaps.** Run the frontend job again, raise coverage over the gate and extend the isolation matrix to
   every tenant table. Refresh `docs/testing.md`.
10. **Finish the web app.** Choose the logo, tune the query cache, measure performance and tighten the CSP.
11. **Real evals.** Run the evaluation set against the real pipeline and track the numbers.

## What is not a limitation

A few things look like gaps and are deliberate:

- **No email service.** Invites and reset links are shown once. See [accounts, sessions and tokens](accounts-sessions-and-tokens.md).
- **No event replay.** Events only mean "refetch". See [human handoff and live events](human-handoff-and-live-events.md).
- **One process and one database.** See [why a modular monolith](why-a-modular-monolith.md).
- **Approval for every write.** It is the cost of a safe agent.

## Related pages

- [arc42 section 11: risks and technical debt](../arc42/11-risks-and-technical-debt.md)
- [Testing strategy](testing-strategy.md)
- [Frontend TODO](../frontend/TODO.md)
- [Security controls reference](../reference/security-controls.md)
- [Glossary](../glossary.md)
