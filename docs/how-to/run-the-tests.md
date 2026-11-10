# Run the tests

**Type:** How-to · **Audience:** a developer who changes code · **Verified against:** `a989287`

**In plain English:** This page shows how to run the tests that cover your change. Run the related tests on your
machine. The CI system runs the full suite. The page also lists the markers that pick a group of tests and the usual
problems on Windows.

## Goal

Run the right tests for a change, quickly, and know what the markers mean.

## Before you start

- You installed the project with `uv pip install -e ".[dev]"` and you activated the virtual environment.
- For the integration tests, Docker runs on your machine. The tests start their own Postgres with testcontainers.
- You read [the testing guide](../testing.md) for the test design. This page is only about the commands.

## Steps

1. Open a terminal in the root folder of the repository.
2. Optional: set the import path. The `pythonpath` option of `pytest` in `pyproject.toml` already holds `src`, `.` and
   `tests`, so a plain `pytest` run needs no variable. Set it when a tool outside `pytest` cannot import `support`. In
   PowerShell run:

   ```powershell
   $env:PYTHONPATH = "src;tests"
   ```

   In a POSIX shell run `export PYTHONPATH="src:tests"`.

3. Run the tests that are near your change. For example, for the provider code:

   ```bash
   pytest tests/unit/platform/llm
   ```

4. Run the whole fast group when you are ready:

   ```bash
   pytest tests/unit
   ```

   The task `poe test` does the same.

5. Run a group by marker:

   ```bash
   pytest -m security
   pytest -m graph
   ```

6. Run the checks that CI also runs. The blocking CI checks are these:

   ```bash
   ruff check tests scripts
   ruff format --check tests
   lint-imports
   python scripts/check_secrets.py --all
   ```

   CI also runs `ruff check src services evals`, `ruff format --check src services evals` and `mypy src`. These
   steps are advisory (`continue-on-error`) at this commit. The task `poe lint` runs `ruff check .` and
   `ruff format --check .` over the whole tree.

   `lint-imports` enforces the layer rules. The hygiene tests also check layers, the template `.env.example` and secrets.

7. Run the integration tests only when you change database code or RLS:

   ```bash
   pytest tests/integration
   ```

   > **CAUTION.** The integration conftest refuses to wipe a database whose name does not contain `test`. Set
   > `RAGASSIST_TEST_DB_ALLOW_WIPE=1` only for a database that you may erase. Never point the tests at a real database.

8. Leave the full suite to CI (`poe test-all` runs `pytest tests`).

## Markers

| Marker | Meaning |
|---|---|
| `unit` | Fast tests that use fakes only. Applied to `tests/unit`. |
| `graph` | Assistant-graph paths with scripted fake models |
| `security` | Tenant isolation, authentication and prompt injection |
| `integration` | Needs Docker (Postgres, LocalStack) |
| `e2e` | HTTP and SSE tests through the public API |
| `hygiene` | The rules of `AGENTS.md` as tests |
| `selfcheck` | Proves that fakes match their contracts |
| `eval` | Tests of the evaluation helpers |
| `live` | Needs a real model endpoint. Opt in with `--run-live` or `RAGASSIST_LIVE=1`. |
| `gpu` | Needs a CUDA GPU. Skipped when none exists. |
| `slow` | Slower than about 5 seconds |
| `defect` | Asserts correct behavior that the code does not have yet (strict xfail) |
| `network` | Opts out of the guard against external network access |
| `pending` | Tests for code that is not written yet. They skip with a reason. |
| `real_assistant_graph` | Keeps the real graph wiring of the container. No scripted fake graph replaces it. |

Useful commands:

- `pytest tests/unit -p randomly` runs the tests in random order.
- `pytest -m pending -rs` shows the pending tests and their reasons.
- `pytest -m defect --runxfail` shows the known defects as real failures.
- `RAGASSIST_STRICT_PENDING=1 pytest -m pending` makes a pending test fail instead of skip.
- `bash scripts/flake_check.sh 10` runs the suite repeatedly to find flaky tests.
- `python tests/gates/check_coverage.py --report coverage.json` checks the coverage gate (advisory in CI).

## Check

- The command ends with `passed` and no `failed` or `error` in the summary.
- `lint-imports` and `ruff check tests scripts` exit with 0.

## Troubleshooting

- `ModuleNotFoundError` for `support`: run `pytest` from the repository root, or set `PYTHONPATH` as in step 2.
- A shell script test fails on Windows with a bad interpreter. The file has CRLF line endings. `.gitattributes` forces LF
  for shell scripts. Check the file out again.
- The integration tests hang on stop. The integration conftest sets `TESTCONTAINERS_RYUK_DISABLED=true` when the variable is
  unset. If your shell sets it to `false`, remove that value.
- A live test is skipped. This is normal without `--run-live`.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Testing guide](../testing.md)
- [CI and quality gates](../reference/ci-and-quality-gates.md)
