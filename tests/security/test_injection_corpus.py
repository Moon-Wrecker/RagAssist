"""Prompt-injection corpus against the production safety check (plan section 7 and arc42 section 10).

Runs today against the rules decider through ``DecisionService.check_safety``. It reports detection by
category to ``reports/injection.json`` and enforces three things:

* benign cases are never flagged (zero false positives);
* borderline cases (security discussions that look like attacks) are reported, not gated;
* each attack category meets the floor in ``tests/data/injection/floors.yaml``.

The model-backed decider is gated at 0.95 in ``tests/live/test_injection_live.py``.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict

import pytest
from support.corpus import all_cases, load_categories, load_floors
from support.defects import defect
from support.repo import REPO_ROOT
from support.settings import make_settings

from ragassist.platform.decisions.adapters.rules_decider_adapter import RulesDeciderAdapter
from ragassist.platform.decisions.service import DecisionService
from ragassist.shared.resilience import FallbackChain

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def guard() -> DecisionService:
    rules = RulesDeciderAdapter()
    cfg = make_settings()
    return DecisionService(
        settings=cfg,
        router_chain=FallbackChain(name="router_chain", members=[rules]),
        decider_chain=FallbackChain(name="decider_chain", members=[rules]),
    )


async def _verdicts(guard: DecisionService) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for case in all_cases():
        verdict = await guard.check_safety(case.text)
        results[case.case_id] = not verdict.is_safe
    return results


@pytest.fixture(scope="module")
def verdicts(guard: DecisionService) -> dict[str, bool]:
    """Case id -> True when the guard blocked it. Computed once for the whole module."""
    return asyncio.run(_verdicts(guard))


def rates(verdicts: dict[str, bool]) -> dict[str, float]:
    by_category: dict[str, list[bool]] = defaultdict(list)
    for category, cases in load_categories().items():
        for case in cases:
            if case.is_attack:
                by_category[category].append(verdicts[case.case_id])
    return {
        category: (sum(hits) / len(hits) if hits else 0.0) for category, hits in by_category.items()
    }


class TestBenignTraffic:
    def test_no_benign_case_is_blocked(self, verdicts: dict[str, bool]) -> None:
        benign = list(load_categories()["benign"])
        flagged = [c.case_id for c in benign if verdicts[c.case_id]]
        assert not flagged, f"false positives on ordinary questions: {flagged}"

    def test_borderline_security_discussion_is_reported_not_gated(
        self, verdicts: dict[str, bool]
    ) -> None:
        """Known weak spot: these are legitimate questions that a keyword rule may flag. They are
        reported in reports/injection.json for the decider owners; they do not fail the build."""
        assert all(isinstance(verdicts[c.case_id], bool) for c in load_categories()["borderline"])


class TestAttacks:
    @defect("DEFECT-31")
    def test_every_attack_category_meets_its_floor(self, verdicts: dict[str, bool]) -> None:
        measured = rates(verdicts)
        misses = {
            category: round(measured.get(category, 0.0), 3)
            for category, floor in load_floors().items()
            if measured.get(category, 0.0) < floor
        }
        assert not misses, f"detection below floor (category: rate): {misses}"

    def test_the_report_is_written_for_the_decider_owners(self, verdicts: dict[str, bool]) -> None:
        report = {
            "rates": rates(verdicts),
            "floors": load_floors(),
            "false_positives": [
                c.case_id for c in load_categories()["benign"] if verdicts[c.case_id]
            ],
            "borderline_flagged": [
                c.case_id for c in load_categories()["borderline"] if verdicts[c.case_id]
            ],
        }
        target = REPO_ROOT / "reports" / "injection.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        assert target.exists()
