"""The mock SaaS ships in its own image, which holds only ``services/mock_saas``: it must not import the app."""

from __future__ import annotations

import ast

from support.repo import REPO_ROOT


def test_the_mock_saas_service_does_not_import_the_application_package() -> None:
    imported: set[str] = set()
    for path in (REPO_ROOT / "services" / "mock_saas").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert "ragassist" not in imported, "its Docker image does not contain the ragassist package"
