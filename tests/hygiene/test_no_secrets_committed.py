"""No tracked file holds a credential-shaped value (the same scanner the git hooks and CI run)."""

from __future__ import annotations

import importlib.util
import os
import sys

from support.repo import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "check_secrets", REPO_ROOT / "scripts" / "check_secrets.py"
)
assert _spec and _spec.loader
check_secrets = importlib.util.module_from_spec(_spec)
sys.modules["check_secrets"] = check_secrets
_spec.loader.exec_module(check_secrets)


def test_no_tracked_file_contains_a_credential() -> None:
    os.chdir(REPO_ROOT)
    findings = check_secrets.scan_all()
    assert not findings, "credential-shaped text in tracked files:\n" + "\n".join(
        map(str, findings)
    )


def test_the_git_hooks_exist_and_call_the_scanner() -> None:
    for name, flag in (("pre-commit", "--staged"), ("pre-push", "--push")):
        hook = (REPO_ROOT / ".githooks" / name).read_text(encoding="utf-8")
        assert "scripts/check_secrets.py" in hook and flag in hook
