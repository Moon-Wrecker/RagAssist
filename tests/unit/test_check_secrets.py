"""The secret scanner refuses credential-shaped text and lets ordinary code through.

Every sample is assembled at run time: the repository bans key-shaped literals, its own tests included.
"""

from __future__ import annotations

import importlib.util
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from support.repo import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "check_secrets", REPO_ROOT / "scripts" / "check_secrets.py"
)
assert _spec and _spec.loader
check_secrets = importlib.util.module_from_spec(_spec)
sys.modules["check_secrets"] = check_secrets
_spec.loader.exec_module(check_secrets)


def _random(n: int) -> str:
    return secrets.token_hex(n)[:n]


SHAPES = {
    "provider API key": lambda: "sk-" + "proj-" + _random(40),
    "Langfuse key": lambda: "sk-lf-" + "-".join(_random(n) for n in (8, 4, 4, 4, 12)),
    "LangSmith key": lambda: "lsv2_" + "pt_" + _random(34),
    "Google API key": lambda: "AIza" + _random(35),
    "AWS access key id": lambda: "AKIA" + _random(16).upper(),
    "GitHub token": lambda: "ghp_" + _random(40),
    "JSON web token": lambda: ".".join("eyJ" + _random(20) for _ in range(3)),
    "credential in a URL": lambda: "postgresql://app:" + _random(16) + "@db.internal/app",
}


@pytest.mark.parametrize("rule", sorted(SHAPES))
def test_a_credential_shape_is_found_by_its_rule(rule: str) -> None:
    hits = check_secrets.scan_line(f"value = {SHAPES[rule]()}")
    assert rule in {name for name, _ in hits}


def test_a_hardcoded_secret_assignment_is_found() -> None:
    assert check_secrets.scan_line(f'api_key = "{secrets.token_urlsafe(30)}"')
    assert check_secrets.scan_line(f"DB_PASSWORD: '{secrets.token_urlsafe(24)}'")


@pytest.mark.parametrize(
    "line",
    [
        "OPENAI_API_KEY=",
        "api_key = os.environ['OPENAI_API_KEY']",
        "token = secrets.token_urlsafe(32)",
        'password = "<your-password>"',
        'secret = "${SECRET_KEY}"',
        'headers = {"Authorization": f"Bearer {token}"}',
        "max_tokens = 4096",
        'name = "access_token_ttl_minutes_for_the_session"',
    ],
)
def test_ordinary_code_and_placeholders_pass(line: str) -> None:
    assert check_secrets.scan_line(line) == []


def test_the_opt_out_marker_silences_one_line() -> None:
    line = f"x = {SHAPES['provider API key']()}  # secret-scan: allow"
    assert check_secrets.scan_line(line) == []


def test_findings_never_contain_the_secret() -> None:
    secret = SHAPES["provider API key"]()
    (finding,) = check_secrets.scan_text("a.py", f"k = {secret}")
    assert secret not in str(finding)
    assert len(finding.hint) == 4


def test_a_diff_scan_reads_added_lines_only() -> None:
    key = SHAPES["provider API key"]()
    diff = f"+++ b/app.py\n@@ -1,2 +1,2 @@\n-old = {key}\n context = {key}\n+new = {key}\n"
    findings = check_secrets.scan_diff(diff)
    assert [(f.path, f.line) for f in findings] == [("app.py", 2)]


def test_lockfiles_are_not_scanned() -> None:
    assert (
        check_secrets.scan_text(
            "frontend/package-lock.json", f'"k": "{SHAPES["provider API key"]()}"'
        )
        == []
    )


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def test_a_key_added_then_removed_in_a_later_commit_is_still_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "f.py").write_text(f"x = '{SHAPES['provider API key']()}'\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "oops")
    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "remove it")
    head = _git(repo, "rev-parse", "HEAD")
    monkeypatch.chdir(repo)

    assert check_secrets.scan_range(f"{base}..{head}"), "history is scanned commit by commit"
    zero = "0" * 40
    assert check_secrets.scan_push([f"refs/heads/b {head} refs/heads/b {base}"])
    assert check_secrets.scan_push([f"refs/heads/b {head} refs/heads/b {zero}"])
    assert check_secrets.scan_push([f"(delete) {zero} refs/heads/b {base}"]) == []
