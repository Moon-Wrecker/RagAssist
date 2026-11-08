"""Coverage gate (implementation plan section 8; the test plan's quality gates).

Reads the JSON report written by ``pytest --cov=src/ragassist --cov-branch --cov-report=json:coverage.json``
and enforces three rules:

1. a hard minimum per package group, once the group has code (``coverage_policy.json``);
2. an overall minimum;
3. a ratchet: a group may not fall below its recorded baseline (``coverage_baseline.json``, minus a small
   tolerance). Run with ``--update-baseline`` after coverage rises to lock the gain in.

A group with no statements yet is reported as pending and never fails the gate.

    python tests/gates/check_coverage.py --report coverage.json
    python tests/gates/check_coverage.py --report coverage.json --update-baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_POLICY = HERE / "coverage_policy.json"
DEFAULT_BASELINE = HERE / "coverage_baseline.json"
TOLERANCE = 0.5  # percentage points a group may dip below its baseline without failing


@dataclass
class GateResult:
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    measured: dict[str, float] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _percent(covered: int, total: int) -> float | None:
    return None if total == 0 else 100.0 * covered / total


def _summary_counts(summary: dict[str, Any]) -> tuple[int, int]:
    """Lines and branches together, so branch coverage (plan section 8) counts."""
    covered = int(summary.get("covered_lines", 0)) + int(summary.get("covered_branches", 0))
    total = int(summary.get("num_statements", 0)) + int(summary.get("num_branches", 0))
    return covered, total


def group_percent(files: dict[str, dict[str, Any]], group: str) -> float | None:
    """Combined percentage for every file under ``group`` (e.g. ``ragassist/shared/``)."""
    covered = total = 0
    needle = "/" + group.strip("/") + "/"
    for name, data in files.items():
        normalised = "/" + name.replace("\\", "/")
        if needle in normalised:
            file_covered, file_total = _summary_counts(data["summary"])
            covered += file_covered
            total += file_total
    return _percent(covered, total)


def evaluate(
    report: dict[str, Any], policy: dict[str, Any], baseline: dict[str, float]
) -> GateResult:
    result = GateResult()
    files = report.get("files", {})

    for group, rule in policy.get("groups", {}).items():
        pct = group_percent(files, group)
        if pct is None:
            result.pending.append(group)
            continue
        result.measured[group] = round(pct, 2)
        if pct < rule["min"]:
            result.failures.append(
                f"{group}: {pct:.1f}% is below the hard minimum of {rule['min']}%"
            )
        recorded = baseline.get(group)
        if recorded is not None:
            if pct < recorded - TOLERANCE:
                result.failures.append(
                    f"{group}: {pct:.1f}% fell below the ratchet baseline {recorded:.1f}% (regression)"
                )
            elif pct > recorded + TOLERANCE:
                result.notes.append(
                    f"{group}: {pct:.1f}% is above baseline {recorded:.1f}%; raise the baseline"
                )

    overall = _percent(*_summary_counts(report.get("totals", {})))
    if overall is not None:
        result.measured["overall"] = round(overall, 2)
        if overall < policy.get("overall_min", 0):
            result.failures.append(
                f"overall: {overall:.1f}% is below the minimum of {policy['overall_min']}%"
            )
    return result


def updated_baseline(result: GateResult, baseline: dict[str, float]) -> dict[str, float]:
    """Raise each recorded baseline to the measured value; never lower one."""
    updated = dict(baseline)
    for group, pct in result.measured.items():
        if group == "overall":
            continue
        updated[group] = round(max(pct, baseline.get(group, 0.0)), 2)
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--report", required=True, type=Path, help="coverage.json from coverage json"
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--update-baseline", action="store_true", help="raise the ratchet to the measured values"
    )
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    baseline = (
        json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline.exists() else {}
    )

    result = evaluate(report, policy, baseline)
    for group, pct in sorted(result.measured.items()):
        print(f"{group:<24} {pct:6.2f}%")
    for group in result.pending:
        print(f"{group:<24}  pending (no statements yet; not gated)")
    for note in result.notes:
        print(f"note: {note}")
    for failure in result.failures:
        print(f"FAIL: {failure}")

    if args.update_baseline and result.passed:
        args.baseline.write_text(
            json.dumps(updated_baseline(result, baseline), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"baseline written to {args.baseline}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
