"""The defect registry stays honest: every marker refers to a registered defect, every registered defect
is asserted by at least one test, and the generated report lists them all."""

from __future__ import annotations

import re

import pytest
from support.defects import DEFECTS, render_markdown
from support.repo import TESTS_ROOT

pytestmark = pytest.mark.hygiene

MARKER = re.compile(r'(?:@defect|defect_marks|@defect_marks)\(\s*"(DEFECT-\d+)"')


def referenced_in_tests() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if path.name == "defects.py" and path.parent.name == "support":
            continue
        text = path.read_text(encoding="utf-8")
        for defect_id in MARKER.findall(text):
            found.setdefault(defect_id, []).append(str(path.relative_to(TESTS_ROOT)))
    return found


class TestRegistry:
    def test_every_marker_names_a_registered_defect(self) -> None:
        unknown = sorted(set(referenced_in_tests()) - set(DEFECTS))
        assert not unknown, f"markers for unregistered defects: {unknown}"

    def test_every_registered_defect_is_asserted_by_a_test(self) -> None:
        orphans = sorted(set(DEFECTS) - set(referenced_in_tests()))
        assert not orphans, f"registered but untested defects: {orphans}"

    def test_ids_follow_the_numbering_scheme(self) -> None:
        assert all(re.fullmatch(r"DEFECT-\d{2}", defect_id) for defect_id in DEFECTS)

    def test_every_defect_has_a_one_line_summary(self) -> None:
        assert all(summary.strip() and "\n" not in summary for summary in DEFECTS.values())


class TestReport:
    def test_the_report_lists_every_registered_defect(self) -> None:
        text = render_markdown({})
        assert all(defect_id in text for defect_id in DEFECTS)

    def test_the_report_counts_the_tests_that_assert_each_defect(self) -> None:
        text = render_markdown({"DEFECT-04": ["tests/a.py::t1", "tests/b.py::t2"]})
        assert "| DEFECT-04 |" in text and "2 test(s)" in text

    def test_undetected_defects_are_flagged(self) -> None:
        assert "none in this run" in render_markdown({})

    def test_the_report_is_stable_for_the_same_input(self) -> None:
        occurrences = {"DEFECT-04": ["x.py::a"]}
        assert render_markdown(occurrences) == render_markdown(occurrences)
