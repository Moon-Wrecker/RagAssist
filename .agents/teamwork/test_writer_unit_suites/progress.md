# Progress — test_writer_unit_suites

## Done
- Spec layer with three outcomes: found / PENDING (missing or empty module, optional dependency) / DRIFT
  (renamed symbol, close-name match, broken ragassist import). A close-name match counts as DRIFT.
- Production in-memory storage and queue adapters are used directly. Fakes stand in only for model and
  decision providers, as the user decided. `aioboto3` installed to match `pyproject.toml`.
- `python-multipart` installed in the venv (not declared in `pyproject.toml`: DEFECT-35).
- Domain re-aligned to the code that exists: `Block`/`ParsedDocument`, `ChunkDraft`, `IngestionJob`
  (`job_id`, `attempts`), `transition_job`, `LEGAL_JOB_TRANSITIONS`, `Parser` and `Chunker` protocols.
- New defects asserted: DEFECT-32 (in-memory adapters import the AWS SDK), DEFECT-33 (`running` in the legal
  table), DEFECT-34 (hybrid chunker returns dicts), DEFECT-35 (multipart not declared).
- DEFECT-14 and DEFECT-20 removed after the M1 remediation fixed them; regression tests kept.

## Lessons for the team
- A suite for a module under construction is PENDING, so a half-built module is never a silent pass.
  `pytest -m pending -rs` lists what is missing.
- Interface changes go into `PROJECT.md` first. The appendix follows from `map.py`.
