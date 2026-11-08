"""AGENTS.md section 1: layering rules, enforced from the import graph.

First the checker is shown to catch every kind of violation in a planted tree (so a green result on
the real tree means something), then it is run on ``src/``.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from support.architecture import check_file, check_tree
from support.defects import defect
from support.repo import REPO_ROOT, SRC_ROOT, read


def write(root: Path, relative: str, source: str) -> Path:
    path = root / "ragassist" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source), encoding="utf-8")
    return path


def rules_for(root: Path, relative: str, source: str) -> set[str]:
    path = write(root, relative, source)
    return {v.rule for v in check_file(path, root)}


class TestTheCheckerHasTeeth:
    @pytest.mark.parametrize(
        ("relative", "source", "rule"),
        [
            (
                "modules/kb/domain/x.py",
                "from ragassist.modules.kb.adapters import y",
                "domain-points-inward",
            ),
            (
                "modules/kb/domain/x.py",
                "from ragassist.modules.kb.application import y",
                "domain-points-inward",
            ),
            (
                "modules/kb/domain/x.py",
                "from ragassist.modules.kb.api import y",
                "domain-points-inward",
            ),
            (
                "modules/kb/domain/x.py",
                "from . import adapters\n",
                None,
            ),  # relative import of a sibling name: not a layer
            ("modules/kb/domain/x.py", "import sqlalchemy", "domain-no-frameworks"),
            ("modules/kb/domain/x.py", "from fastapi import APIRouter", "domain-no-frameworks"),
            ("modules/kb/domain/x.py", "import openai", "domain-no-frameworks"),
            (
                "modules/kb/domain/x.py",
                "from langchain_core.messages import BaseMessage",
                "domain-no-frameworks",
            ),
            (
                "modules/kb/application/uc.py",
                "from ragassist.modules.kb.adapters.persistence import Repo",
                "application-points-inward",
            ),
            (
                "modules/kb/application/uc.py",
                "from ragassist.modules.kb.api.router import router",
                "application-points-inward",
            ),
            ("modules/kb/application/uc.py", "import httpx", "application-no-frameworks"),
            (
                "modules/kb/application/uc.py",
                "from ragassist.platform.llm.adapters.openai_adapter import X",
                "application-uses-platform-adapters",
            ),
            (
                "modules/kb/application/uc.py",
                "from ..adapters import repo",
                "application-points-inward",
            ),
            (
                "modules/a/application/uc.py",
                "from ragassist.modules.b.adapters.persistence import Row",
                "module-isolation",
            ),
            (
                "modules/a/api/router.py",
                "from ragassist.modules.b.api import router",
                "module-isolation",
            ),
            ("shared/x.py", "from ragassist.modules.kb.domain import Doc", "kernel-independence"),
            ("shared/x.py", "from ragassist.platform.llm.ports import Port", "kernel-independence"),
            (
                "platform/llm/x.py",
                "from ragassist.modules.kb.application import uc",
                "platform-below-modules",
            ),
        ],
    )
    def test_each_forbidden_import_is_reported(
        self, tmp_path: Path, relative: str, source: str, rule: str | None
    ) -> None:
        found = rules_for(tmp_path, relative, source)
        assert (rule in found) if rule else not found

    @pytest.mark.parametrize(
        ("relative", "source"),
        [
            (
                "modules/kb/domain/x.py",
                "from pydantic import BaseModel\nfrom ragassist.shared.domain import Entity",
            ),
            ("modules/kb/domain/x.py", "from ragassist.modules.kb.domain.other import Y"),
            (
                "modules/kb/application/uc.py",
                "from ragassist.modules.kb.domain import Doc\nfrom ragassist.shared.db.uow import UnitOfWork",
            ),
            (
                "modules/kb/application/uc.py",
                "from ragassist.platform.llm.ports import ChatModelProvider\nfrom ragassist.platform.llm.service import LLMService",
            ),
            (
                "modules/kb/application/uc.py",
                "from ragassist.modules.other.application.facade import Facade",
            ),
            (
                "modules/kb/adapters/repo.py",
                "import sqlalchemy\nfrom ragassist.modules.kb.domain import Doc",
            ),
            (
                "modules/kb/api/router.py",
                "from fastapi import APIRouter\nfrom ragassist.modules.kb.application import uc",
            ),
            ("platform/llm/service.py", "from ragassist.shared.config.settings import Settings"),
            ("shared/db/uow.py", "from ragassist.shared.domain import TenantId\nimport sqlalchemy"),
        ],
    )
    def test_legitimate_imports_are_not_flagged(
        self, tmp_path: Path, relative: str, source: str
    ) -> None:
        assert rules_for(tmp_path, relative, source) == set()

    def test_violations_carry_file_line_and_rule(self, tmp_path: Path) -> None:
        write(tmp_path, "modules/kb/domain/x.py", "import os\nimport sqlalchemy\n")
        (violation,) = check_tree(tmp_path)
        assert violation.file.endswith("modules/kb/domain/x.py") and violation.line == 2
        assert "domain-no-frameworks" in str(violation)

    def test_syntax_free_files_and_packages_are_handled(self, tmp_path: Path) -> None:
        write(tmp_path, "modules/kb/domain/__init__.py", "")
        write(tmp_path, "shared/__init__.py", "")
        assert check_tree(tmp_path) == []


class TestRealSourceTree:
    def test_source_tree_exists(self) -> None:
        assert (SRC_ROOT / "ragassist").is_dir()

    def test_no_layering_violations(self) -> None:
        violations = check_tree(SRC_ROOT)
        assert not violations, "Layering violations:\n" + "\n".join(str(v) for v in violations)

    def test_every_declared_module_has_the_four_layers_or_is_still_a_stub(self) -> None:
        """A module that has started (any layer present) should have its layers named correctly."""
        allowed = {"domain", "application", "adapters", "api", "graph", "tools", "__pycache__"}
        for module in (SRC_ROOT / "ragassist" / "modules").iterdir():
            if module.is_dir() and module.name != "__pycache__":
                unknown = {p.name for p in module.iterdir() if p.is_dir()} - allowed
                assert not unknown, f"module {module.name} has unexpected folders {sorted(unknown)}"

    @defect("DEFECT-11")
    def test_import_linter_contracts_are_configured(self) -> None:
        assert "[tool.importlinter]" in read("pyproject.toml")

    @defect("DEFECT-11")
    def test_ci_runs_lint_imports(self) -> None:
        workflows = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (REPO_ROOT / ".github" / "workflows").glob("*.yml")
        )
        assert "lint-imports" in workflows
