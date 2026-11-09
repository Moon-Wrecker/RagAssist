"""Repository-level paths and helpers for the hygiene tier."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
TESTS_ROOT = REPO_ROOT / "tests"

# Directories that are never part of the project's own files.
IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".hypothesis",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".cache",
}


def project_files(*patterns: str) -> list[Path]:
    """Files matching any glob pattern, excluding virtualenvs, caches and VCS metadata."""
    found: set[Path] = set()
    for pattern in patterns:
        for path in REPO_ROOT.rglob(pattern):
            if path.is_file() and not (set(path.relative_to(REPO_ROOT).parts) & IGNORED_DIRS):
                found.add(path)
    return sorted(found)


def read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def active_lines(relative: str) -> list[str]:
    """Non-empty, non-comment lines of an ignore/attribute style file."""
    return [
        line.strip()
        for line in read(relative).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
