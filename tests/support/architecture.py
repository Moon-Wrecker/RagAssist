"""Static layering checker for the hexagonal / modular-monolith rules in AGENTS.md section 1.

It parses imports with ``ast`` (nothing is imported or executed) and applies these rules:

* ``domain``       imports nothing from application/adapters/api and no framework or SDK.
* ``application``  imports no adapters/api and no framework or SDK; it may use its own domain,
                   ``shared`` and the *public* platform surface (``ports`` / ``service``).
* modules are isolated: a module never imports another module's ``adapters`` or ``api``.
* ``shared``       (the kernel) imports neither ``modules`` nor ``platform``.
* ``platform``     never imports ``modules``.

The checker is pure so ``tests/hygiene`` can prove it catches planted violations before trusting
its verdict on the real source tree.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

ROOT_PACKAGE = "ragassist"

FRAMEWORKS_AND_SDKS = frozenset(
    {
        "fastapi",
        "starlette",
        "uvicorn",
        "sqlalchemy",
        "asyncpg",
        "psycopg",
        "psycopg2",
        "alembic",
        "boto3",
        "botocore",
        "aioboto3",
        "httpx",
        "requests",
        "aiohttp",
        "openai",
        "anthropic",
        "langchain",
        "langchain_core",
        "langchain_openai",
        "langchain_anthropic",
        "langgraph",
        "torch",
        "sentence_transformers",
        "flashrank",
        "transformers",
        "jwt",
    }
)
PLATFORM_PUBLIC_SUFFIXES = ("ports", "service")


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    rule: str
    imported: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}  [{self.rule}]  imports {self.imported}"


def _module_name(path: Path, src_root: Path) -> str:
    relative = path.relative_to(src_root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _absolute_imports(tree: ast.AST, module: str, is_package: bool) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    package_parts = module.split(".") if is_package else module.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - (node.level - 1)]
                target = ".".join([*base, *(node.module.split(".") if node.module else [])])
            else:
                target = node.module or ""
            found.append((node.lineno, target))
            if not node.module:  # ``from . import x``: the names are submodules
                found.extend((node.lineno, f"{target}.{alias.name}") for alias in node.names)
    return found


def _layer(module: str) -> tuple[str | None, str | None, str | None]:
    """Return (area, module name, layer) for e.g. ``ragassist.modules.knowledge.domain.x``."""
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != ROOT_PACKAGE:
        return None, None, None
    area = parts[1]
    if area == "modules" and len(parts) >= 3:
        return "modules", parts[2], parts[3] if len(parts) >= 4 else None
    return area, None, None


def check_file(path: Path, src_root: Path) -> list[Violation]:
    module = _module_name(path, src_root)
    area, mod, layer = _layer(module)
    if area is None:
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[Violation] = []
    rel = str(path.relative_to(src_root)).replace("\\", "/")

    def add(line: int, rule: str, imported: str) -> None:
        violations.append(Violation(rel, line, rule, imported))

    for line, imported in _absolute_imports(tree, module, path.name == "__init__.py"):
        top = imported.split(".")[0]
        i_area, i_mod, i_layer = _layer(imported) if top == ROOT_PACKAGE else (None, None, None)

        if area == "modules" and layer == "domain":
            if top in FRAMEWORKS_AND_SDKS:
                add(line, "domain-no-frameworks", imported)
            if (
                i_area == "modules"
                and i_mod == mod
                and i_layer in {"application", "adapters", "api"}
            ):
                add(line, "domain-points-inward", imported)
        if area == "modules" and layer == "application":
            if top in FRAMEWORKS_AND_SDKS:
                add(line, "application-no-frameworks", imported)
            if i_area == "modules" and i_mod == mod and i_layer in {"adapters", "api"}:
                add(line, "application-points-inward", imported)
            if (
                i_area == "platform"
                and imported.split(".")[-1] not in PLATFORM_PUBLIC_SUFFIXES
                and (".adapters" in imported)
            ):
                add(line, "application-uses-platform-adapters", imported)
        if area == "modules" and i_area == "modules" and i_mod not in (None, mod):
            if i_layer in {"adapters", "api"}:
                add(line, "module-isolation", imported)
        if area == "shared" and i_area in {"modules", "platform"}:
            add(line, "kernel-independence", imported)
        if area == "platform" and i_area == "modules":
            add(line, "platform-below-modules", imported)
    return violations


def check_tree(src_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted((src_root / ROOT_PACKAGE).rglob("*.py")):
        violations.extend(check_file(path, src_root))
    return violations
