"""The quality gates are code, so they are tested like code: the coverage ratchet and its policy, the
flake script, the CI wiring and the report plumbing."""

from __future__ import annotations

import json
import re

import pytest
from gates.check_coverage import TOLERANCE, evaluate, group_percent, main, updated_baseline
from support.repo import REPO_ROOT, read

pytestmark = pytest.mark.hygiene

POLICY = {
    "overall_min": 85,
    "groups": {"ragassist/shared/": {"min": 95}, "ragassist/platform/": {"min": 90}},
}


def file_entry(covered: int, statements: int, branches_covered: int = 0, branches: int = 0) -> dict:
    return {
        "summary": {
            "covered_lines": covered,
            "num_statements": statements,
            "covered_branches": branches_covered,
            "num_branches": branches,
        }
    }


def report(files: dict, totals: dict | None = None) -> dict:
    return {"files": files, "totals": totals or {"covered_lines": 0, "num_statements": 0}}


class TestCoverageMath:
    def test_branches_count_towards_the_group_percentage(self) -> None:
        files = {"src/ragassist/shared/a.py": file_entry(8, 10, 2, 4)}
        assert group_percent(files, "ragassist/shared/") == pytest.approx(100.0 * 10 / 14)

    def test_only_files_inside_the_group_are_counted(self) -> None:
        files = {
            "src/ragassist/shared/a.py": file_entry(10, 10),
            "src/ragassist/platform/b.py": file_entry(0, 10),
        }
        assert group_percent(files, "ragassist/shared/") == 100.0

    def test_windows_separators_are_understood(self) -> None:
        files = {"src\\ragassist\\shared\\a.py": file_entry(5, 10)}
        assert group_percent(files, "ragassist/shared/") == 50.0

    def test_an_empty_group_is_none_not_zero(self) -> None:
        assert group_percent({}, "ragassist/worker/") is None


class TestEvaluate:
    def test_a_healthy_run_passes(self) -> None:
        files = {
            "src/ragassist/shared/a.py": file_entry(97, 100),
            "src/ragassist/platform/b.py": file_entry(92, 100),
        }
        totals = {"covered_lines": 189, "num_statements": 200}
        result = evaluate(report(files, totals), POLICY, {})
        assert result.passed

    def test_a_group_below_its_hard_minimum_fails(self) -> None:
        files = {"src/ragassist/shared/a.py": file_entry(90, 100)}
        result = evaluate(report(files, {"covered_lines": 90, "num_statements": 100}), POLICY, {})
        assert any("ragassist/shared/" in f and "hard minimum" in f for f in result.failures)

    def test_overall_below_the_minimum_fails_even_when_groups_pass(self) -> None:
        files = {
            "src/ragassist/shared/a.py": file_entry(96, 100),
            "src/ragassist/platform/b.py": file_entry(91, 100),
        }
        policy = {**POLICY, "overall_min": 99}
        result = evaluate(report(files, {"covered_lines": 187, "num_statements": 200}), policy, {})
        assert any(f.startswith("overall") for f in result.failures)

    def test_a_regression_below_the_ratchet_fails(self) -> None:
        files = {"src/ragassist/shared/a.py": file_entry(96, 100)}
        baseline = {"ragassist/shared/": 98.0}
        result = evaluate(
            report(files, {"covered_lines": 96, "num_statements": 100}), POLICY, baseline
        )
        assert any("regression" in f for f in result.failures)

    def test_a_dip_within_the_tolerance_is_allowed(self) -> None:
        files = {"src/ragassist/shared/a.py": file_entry(96, 100)}
        baseline = {"ragassist/shared/": 96.0 + TOLERANCE / 2}
        result = evaluate(
            report(files, {"covered_lines": 96, "num_statements": 100}), POLICY, baseline
        )
        assert not any("regression" in f for f in result.failures)

    def test_a_group_above_its_baseline_is_a_note_not_a_failure(self) -> None:
        files = {"src/ragassist/shared/a.py": file_entry(99, 100)}
        result = evaluate(
            report(files, {"covered_lines": 99, "num_statements": 100}),
            POLICY,
            {"ragassist/shared/": 90.0},
        )
        assert result.passed and any("raise the baseline" in n for n in result.notes)

    def test_an_empty_group_is_pending_and_never_fails_the_gate(self) -> None:
        policy = {**POLICY, "groups": {**POLICY["groups"], "ragassist/worker/": {"min": 90}}}
        files = {"src/ragassist/shared/a.py": file_entry(100, 100)}
        result = evaluate(report(files, {"covered_lines": 100, "num_statements": 100}), policy, {})
        assert "ragassist/worker/" in result.pending and result.passed

    def test_the_ratchet_only_moves_up(self) -> None:
        result = evaluate(report({"src/ragassist/shared/a.py": file_entry(90, 100)}), POLICY, {})
        assert updated_baseline(result, {"ragassist/shared/": 95.0})["ragassist/shared/"] == 95.0

    def test_the_ratchet_records_a_gain(self) -> None:
        result = evaluate(report({"src/ragassist/shared/a.py": file_entry(99, 100)}), POLICY, {})
        assert updated_baseline(result, {})["ragassist/shared/"] == 99.0


class TestCommandLine:
    def test_the_command_exits_non_zero_on_failure(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        report_path = tmp_path / "coverage.json"
        report_path.write_text(
            json.dumps(report({"src/ragassist/shared/a.py": file_entry(10, 100)})), encoding="utf-8"
        )
        policy_path = tmp_path / "policy.json"
        policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
        assert (
            main(
                [
                    "--report",
                    str(report_path),
                    "--policy",
                    str(policy_path),
                    "--baseline",
                    str(tmp_path / "none.json"),
                ]
            )
            == 1
        )

    def test_the_command_exits_zero_on_success(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        files = {"src/ragassist/shared/a.py": file_entry(100, 100)}
        report_path = tmp_path / "coverage.json"
        report_path.write_text(
            json.dumps(report(files, {"covered_lines": 100, "num_statements": 100})),
            encoding="utf-8",
        )
        policy_path = tmp_path / "policy.json"
        policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
        assert (
            main(
                [
                    "--report",
                    str(report_path),
                    "--policy",
                    str(policy_path),
                    "--baseline",
                    str(tmp_path / "none.json"),
                ]
            )
            == 0
        )

    def test_the_committed_policy_is_valid_json_with_the_plan_targets(self) -> None:
        policy = json.loads(
            (REPO_ROOT / "tests" / "gates" / "coverage_policy.json").read_text(encoding="utf-8")
        )
        assert policy["overall_min"] == 85
        assert policy["groups"]["ragassist/shared/"]["min"] == 95
        assert policy["groups"]["ragassist/platform/"]["min"] == 90


class TestFlakePolicy:
    def test_the_flake_script_exists_and_fails_fast(self) -> None:
        script = read("scripts/flake_check.sh")
        assert script.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in script

    def test_the_flake_script_varies_the_random_seed(self) -> None:
        assert "--randomly-seed" in read("scripts/flake_check.sh")

    def test_the_flake_script_uses_lf_line_endings(self) -> None:
        assert b"\r\n" not in (REPO_ROOT / "scripts" / "flake_check.sh").read_bytes()


class TestCiWiring:
    @pytest.fixture
    def workflow(self) -> str:
        return read(".github/workflows/ci.yml")

    def test_a_coverage_job_runs_the_gate(self, workflow: str) -> None:
        assert re.search(r"^  coverage:", workflow, re.M)
        assert "tests/gates/check_coverage.py" in workflow

    def test_a_nightly_flake_job_is_scheduled(self, workflow: str) -> None:
        assert "schedule:" in workflow and "flake_check.sh" in workflow

    def test_pending_and_drift_fail_the_build_in_ci(self, workflow: str) -> None:
        assert 'RAGASSIST_STRICT_PENDING: "1"' in workflow

    def test_reports_are_uploaded_as_artifacts(self, workflow: str) -> None:
        assert "upload-artifact" in workflow and "reports/" in workflow

    def test_the_integration_job_is_still_present(self, workflow: str) -> None:
        assert re.search(r"^  integration-tests:", workflow, re.M)


class TestReportsAreIgnored:
    @pytest.mark.parametrize("path", ["reports/", "coverage.json"])
    def test_generated_reports_are_not_committed(self, path: str) -> None:
        assert path in read(".gitignore") and path in read(".dockerignore")
