# Handoff — test_writer_unit_suites (status for the parent and the builders)

## How to run
```
.venv\Scripts\python.exe -m pytest tests/unit tests/graph tests/security tests/hygiene tests/selfcheck -p no:cacheprovider -o addopts=""
.venv\Scripts\python.exe -m pytest -m pending -rs          # what is not built yet
.venv\Scripts\python.exe -m pytest -m defect --runxfail     # open defects, failing as the spec requires
```
Generated reports: `reports/pending.md`, `reports/defects.md`, `reports/injection.json`, `reports/leak_gate.json`.

## Per-milestone acceptance (builders)
- M2 Ingestion: `tests/unit/modules/knowledge`, `tests/integration/test_localstack_init.py`, `tests/integration/test_rls_and_uow.py`.
- M3 Retrieval and reranker: `tests/unit/modules/retrieval`, `tests/unit/platform/rerank`, `tests/integration/test_retrieval_postgres.py`, `tests/unit/evals`.
- M4 Agent and actions: `tests/graph`, `tests/unit/modules/actions`, `tests/unit/modules/escalation`, `tests/security`.
- M5 API and SSE: `tests/unit/modules/assistant` (SSE), `tests/security/test_route_auth_sweep.py`, `tests/hygiene/test_testing_doc.py`.

## Changes to the interface (listed for PROJECT.md)
- Storage and queue: ports are `ObjectStore.put_object/get_object/delete_object` and
  `MessageQueue.send_message/receive_messages/delete_message` (as implemented in `platform/storage/ports.py`).
- Knowledge domain: `Block`, `ParsedDocument`, `IngestionJob` (`job_id`, `attempts`), `transition_job`,
  `LEGAL_JOB_TRANSITIONS`; `Parser.parse(content, *, mime, filename) -> ParsedDocument`;
  `Chunker.chunk(parsed, *, title) -> list[ChunkDraft]`.
- Retrieval facade (PROJECT.md §4) gets a conformance test (T11).

## Open conflicts
See BRIEFING.md "Open conflicts" (C-R1, C-R2, C-P1, C-P2, C-D1, C-D2, C-D3, C-S1).

## Latest full run
Recorded below after the run completes.
