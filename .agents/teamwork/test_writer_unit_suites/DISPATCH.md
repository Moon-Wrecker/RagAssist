# DISPATCH — test_writer_unit_suites

Parent: conversation be9621e6. User directive (2026-11-08): "collaborate to complete this faster".

| # | Item | Owner | State |
|---|------|-------|-------|
| T1 | Spec-adapter layer (`tests/support/specs/`): found / PENDING / DRIFT | test track | DONE |
| T2 | Interface appendix (`docs/testing.md`), generated from `map.py` | test track | DONE; regenerate after each map change |
| T3 | Knowledge suites: parsers, chunker passes, contracts, properties, toggles, upload, worker, job state | test track | WRITTEN (runs as M2 lands) |
| T4 | Retrieval, rerank and eval-metric suites; retrieval integration on Postgres | test track | WRITTEN |
| T5 | LangGraph suites G1–G22, graph shape, prompts | test track | WRITTEN |
| T6 | SSE contract, actions (tools, approval, SaaS client, audit), escalation | test track | WRITTEN |
| T7 | Security tier: auth sweep, injection corpus, leak gate, secrets in logs, authz matrix | test track | WRITTEN (live parts run) |
| T8 | Hygiene: architecture, tautology rule, defect registry, gates, docs | test track | WRITTEN |
| T9 | Quality gates: coverage ratchet, flake script, CI jobs, reports | test track | WRITTEN |
| T10 | Retire own fakes for storage and queue; use production in-memory adapters | test track | DONE |
| T11 | Re-sync map and suites to PROJECT.md (C-R1, C-R2 facade test) | test track | IN PROGRESS |
| T12 | Full run in random order; record counts in handoff | test track | IN PROGRESS |
| T13 | Notice to builders through PROJECT.md (no writes into builder folders) | parent | IN PROGRESS |

Builder items are tracked in their own folders. This track verifies their output against the suites.
