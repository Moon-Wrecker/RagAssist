"""A test that never reaches product code proves nothing (test plan section 8, "No tautological tests").

Two rules, both static (AST, nothing is imported or run):

* Module rule. Every test module under tests/unit, tests/graph and tests/security must import a
  *bridge*: product code (ragassist, services), the factories that build real tokens and principals,
  or the spec layer that resolves planned code. A module that imports none of these tests only its own
  fixtures.
* Function rule (tests/e2e). A test function that defines its own models (a BaseModel or dataclass in
  the same module) and never references a production or spec name is a tautology, the exact pattern
  this rule was written for. Such functions are listed in tautology_debt.txt; that list may only
  shrink, so each old test is replaced, not forgotten.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from support.repo import TESTS_ROOT

pytestmark = pytest.mark.hygiene

BRIDGES = (
    "ragassist",
    "services",
    "factories",
    "support.specs",
    "support.graph_harness",
    "support.contracts",
    "support.sse",
    "support.knowledge_builders",
    "support.corpus",
    "support.leakage",
    "support.oracles",
    "support.settings",
    "support.spec",
    "support.fake_openai_server",
    "support.repo",
)
MODULE_RULE_DIRS = ("unit", "graph", "security")
DEBT_FILE = TESTS_ROOT / "hygiene" / "tautology_debt.txt"


def _imports(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _is_bridge(module: str) -> bool:
    return any(module == bridge or module.startswith(bridge + ".") for bridge in BRIDGES)


def module_is_tautological(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return not any(_is_bridge(name) for name in _imports(tree))


def tautological_functions(path: Path) -> list[str]:
    """Test functions that exercise only models defined in this same module (the pattern the rule targets).

    A test that uses fixtures from conftest is not flagged: fixtures are the normal way to reach product code.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bridged: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _is_bridge(node.module):
            bridged.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_bridge(alias.name):
                    bridged.add((alias.asname or alias.name).split(".")[0])
    local_models = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            getattr(base, "id", getattr(base, "attr", "")) in {"BaseModel", "dataclass"}
            for base in node.bases
        )
    }
    if not local_models:
        return []

    def check(func: ast.AST, label: str) -> list[str]:
        used = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
        return [label] if (used & local_models) and not (used & bridged) else []

    flagged: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            flagged += check(node, node.name)
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(
                    item, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and item.name.startswith("test_"):
                    flagged += check(item, f"{node.name}::{item.name}")
    return flagged


class TestModuleRule:
    @pytest.mark.parametrize("area", MODULE_RULE_DIRS)
    def test_every_test_module_reaches_product_code(self, area: str) -> None:
        offenders = [
            str(path.relative_to(TESTS_ROOT))
            for path in sorted((TESTS_ROOT / area).rglob("test_*.py"))
            if module_is_tautological(path)
        ]
        assert not offenders, (
            f"these test modules never import product code or a bridge: {offenders}"
        )


class TestFunctionRuleForE2E:
    def _flagged(self) -> set[str]:
        flagged: set[str] = set()
        for path in sorted((TESTS_ROOT / "e2e").glob("test_*.py")):
            for name in tautological_functions(path):
                flagged.add(f"{path.relative_to(TESTS_ROOT).as_posix()}::{name}")
        return flagged

    def test_no_new_tautological_e2e_test_appears(self) -> None:
        debt = {
            line.strip()
            for line in DEBT_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        new = self._flagged() - debt
        assert not new, f"new tautological e2e tests (replace them with real ones): {sorted(new)}"

    def test_the_debt_list_only_shrinks(self) -> None:
        debt = {
            line.strip()
            for line in DEBT_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        cleared = debt - self._flagged()
        assert not cleared, (
            f"fixed or removed, now delete these lines from tautology_debt.txt: {sorted(cleared)}"
        )
