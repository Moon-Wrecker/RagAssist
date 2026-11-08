# BRIEFING — test_writer_unit_suites (unit, pending, security, integration and gates track)

## Mission
Provide the executable acceptance suites for the M2–M5 implementation that the builders are writing,
plus the security tier, quality gates and the interface appendix. Tests are the spec: builders make them
pass. Tests change only when a contract is genuinely wrong, and then the change is recorded in this
folder first.

## Ownership (exclusive write)
- `tests/unit/modules/{knowledge,retrieval,assistant,actions,escalation}/`
- `tests/unit/platform/{rerank,storage,queue}/`, `tests/unit/evals/`, `tests/unit/services/`
- `tests/graph/`, `tests/security/` (except `test_decision_adversarial.py`, owned by M1), `tests/integration/`
- `tests/hygiene/`, `tests/selfcheck/`, `tests/gates/`, `tests/support/`, `tests/fakes/`, `tests/factories/`, `tests/data/`
- `docs/testing.md`, `scripts/flake_check.sh`, `reports/` (generated)
- `.agents/teamwork/test_writer_unit_suites/`

Not mine: `tests/e2e/` and `TEST_INFRA.md` (E2E track, complete); `src/ragassist/**` (builders and M1);
`tests/unit/platform/{llm,embeddings,decisions}` and `tests/unit/shared` (M1, complete).

## Rules
- Builders do not edit files under `tests/`. A builder who thinks a test is wrong writes the reason in its
  handoff, and this track decides. Fixes to tests land here.
- Run tests with `.venv\Scripts\python.exe -m pytest <path> -p no:cacheprovider -o addopts=""`.
- Every suite for code not written yet skips as PENDING. The list is in `reports/pending.md`.
- DRIFT (a planned symbol was renamed) fails in CI when `RAGASSIST_STRICT_PENDING=1`.
- Known defects are strict xfails (`@defect("DEFECT-nn")`), listed in `reports/defects.md`.
- AGENTS.md section 3.5: research before implementation; cite sources in handoffs.

## Source of truth, in order
1. `PROJECT.md` "Interface Contracts" (the normative API surface).
2. `docs/testing.md` interface appendix (generated from `tests/support/specs/map.py`): the symbols and
   signatures the tests assume. Changing it is a contract change: list it under "Changes" in `handoff.md`
   and in `PROJECT.md`.
3. The domain code that exists, where 1 and 2 say nothing.

## Open conflicts (decide with the orchestrator; do not code around them silently)
- C-R1: `RetrievedChunk.heading_path` is `str | None` (PROJECT.md §4), but `Chunk.heading_path` is `list[str]`
  (domain). Entity tests use the list; the DTO test accepts a string or a list.
- C-R2: `RetrievalService.retrieve(tenant_id, query, top_k)` (PROJECT.md §4) is the public facade. Internal
  retrievers are tested through `search(query, tenant_id, k)`. The facade gets its own conformance test.
- C-P1: `HybridChunker.chunk` returns dicts instead of `ChunkDraft` (DEFECT-34). Tests stay strict.
- C-P2: route prefixes. E2E tier 4 uses `/v1/documents` with the alias `/v1/knowledge/upload`; the map uses
  `/v1/documents`. One canonical path is needed.
- C-D1: `LEGAL_JOB_TRANSITIONS` names `running`, which `JobStatus` lacks (DEFECT-33).
- C-D2: `python-multipart` is used by the knowledge API but not declared (DEFECT-35).
- C-D3: the `/v1/systemone` decision-API wire format is unverified (plan C9).
- C-S1: the ingestion retry counter (`attempts`) is kept by the repository. The production repository must provide it.

## Team dependencies
- Builders (`worker_m2`..`worker_m5`): implement against `PROJECT.md` and the appendix; run
  `pytest -m pending -rs` for what is still missing; report DRIFT or defects in their handoff.
- E2E track (`test_writer_e2e_*`): complete. Its tier files are checked by the tautology rule
  (`tests/hygiene/tautology_debt.txt`).
- Gate reviewers, challengers and auditors: use `reports/` and `tests/gates/check_coverage.py` per milestone.
