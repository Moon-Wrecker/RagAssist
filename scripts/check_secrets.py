#!/usr/bin/env python3
"""Refuse to commit or push credentials.

Standard library only, so it runs in a git hook, in CI and on a fresh clone alike.

Modes (exactly one):
    --staged            added lines of the staged diff (pre-commit)
    --push              read ``git push`` ref lines from stdin; scan each commit about to be sent
    --range A..B        added lines of every commit in a revision range (CI on a pull request)
    --all               every tracked file as it is in the working tree (CI, and the hygiene test)

A line may opt out with the marker ``secret-scan: allow`` (only for a documented, non-secret value).
The output names the file, line and rule and the first four characters of a match, never the match.
Exit status: 0 clean, 1 findings, 2 usage or git error.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

ALLOW_MARKER = "secret-scan: allow"

#: Files whose content is hashes or machine output, not authored text.
SKIPPED_FILES = re.compile(
    r"(?:^|/)(?:package-lock\.json|uv\.lock|poetry\.lock|.*\.min\.(?:js|css)|.*\.(?:png|jpg|jpeg|gif|webp|ico|woff2?|pdf|onnx|bin))$"
)

#: Rules whose shape alone identifies a credential.
SHAPED_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key block", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "GitHub token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b"),
    ),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe live key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}\b")),
    (
        "Langfuse key",
        re.compile(r"\b[sp]k-lf-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    ),
    ("LangSmith key", re.compile(r"\blsv2_(?:pt|sk)_[A-Za-z0-9]{20,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b|\bAQ\.[A-Za-z0-9_-]{30,}")),
    (
        "provider API key",
        re.compile(r"\bsk-(?:proj-|ant-|or-v1-|svcacct-)?[A-Za-z0-9][A-Za-z0-9_-]{24,}"),
    ),
    (
        "JSON web token",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    (
        "credential in a URL",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@'\"]+:[^\s/@'\"{}$<>]{6,}@[^\s/'\"]+"),
    ),
)

#: ``name = "value"`` where the name says credential and the value looks random.
_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?P<name>[\w.-]*(?:api[_-]?key|secret|passw(?:or)?d|passphrase|token|credential)[\w.-]*)
    \s*[:=]\s*
    (?P<quote>["'])(?P<value>[A-Za-z0-9_\-./+=]{20,})(?P=quote)
    """
)
_PLACEHOLDER = re.compile(
    r"(?i)^(?:x+|\*+|<.*>|\$\{.*\}|your[-_].*|example.*|changeme|dummy.*|placeholder.*|test[-_].*|fake[-_].*)$"
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    hint: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} ({self.hint}...)"


def _entropy(text: str) -> float:
    counts = {c: text.count(c) for c in set(text)}
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def scan_line(line: str) -> list[tuple[str, str]]:
    """The ``(rule, matched text)`` pairs found on one line of text."""
    if ALLOW_MARKER in line:
        return []
    hits = [(rule, m.group(0)) for rule, pattern in SHAPED_RULES for m in pattern.finditer(line)]
    for m in _ASSIGNMENT.finditer(line):
        value = m.group("value")
        if (
            not _PLACEHOLDER.match(value)
            and _entropy(value) >= 3.6
            and not value.startswith(("http", "/"))
        ):
            hits.append((f"hardcoded {m.group('name').lower()}", value))
    return hits


def scan_text(path: str, text: str, first_line: int = 1) -> list[Finding]:
    if SKIPPED_FILES.search(path):
        return []
    return [
        Finding(path, number, rule, matched[:4])
        for number, line in enumerate(text.splitlines(), start=first_line)
        for rule, matched in scan_line(line)
    ]


def _git(*args: str, stdin: str | None = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def scan_diff(diff: str) -> list[Finding]:
    """Findings on the added lines of a unified diff (never removed or context lines)."""
    findings: list[Finding] = []
    path, line_no = "", 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].removeprefix("b/")
        elif raw.startswith("@@"):
            match = re.search(r"\+(\d+)", raw)
            line_no = int(match.group(1)) if match else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            if path != "/dev/null" and not SKIPPED_FILES.search(path):
                findings.extend(
                    Finding(path, line_no, rule, matched[:4])
                    for rule, matched in scan_line(raw[1:])
                )
            line_no += 1
        elif not raw.startswith("-"):
            line_no += 1
    return findings


def scan_staged() -> list[Finding]:
    return scan_diff(_git("diff", "--cached", "--unified=0", "--no-color", "--diff-filter=ACMR"))


def _scan_log(*revisions: str) -> list[Finding]:
    """Scan each commit's own diff, so a key added then removed in a later commit is still found."""
    return scan_diff(
        _git(
            "log", "-p", "--unified=0", "--no-color", "--format=", "--diff-filter=ACMR", *revisions
        )
    )


def scan_range(revision_range: str) -> list[Finding]:
    return _scan_log(revision_range)


def scan_all() -> list[Finding]:
    findings: list[Finding] = []
    for path in _git("ls-files", "-z").split("\0"):
        if not path or SKIPPED_FILES.search(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                findings.extend(scan_text(path, handle.read()))
        except (OSError, UnicodeDecodeError):
            continue
    return findings


def _push_revisions(lines: Iterable[str]) -> Iterator[list[str]]:
    """Revision arguments for the ref lines ``git push`` feeds a pre-push hook."""
    zero = "0" * 40
    for line in lines:
        parts = line.split()
        if len(parts) != 4 or parts[1] == zero:  # a deletion sends nothing
            continue
        _, local_sha, _, remote_sha = parts
        if remote_sha == zero:  # a new branch: every commit not already on a remote
            yield [local_sha, "--not", "--remotes"]
        else:
            yield [f"{remote_sha}..{local_sha}"]


def scan_push(lines: Iterable[str]) -> list[Finding]:
    return [f for revisions in _push_revisions(lines) for f in _scan_log(*revisions)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--push", action="store_true")
    mode.add_argument("--range", dest="revision_range")
    mode.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.staged:
            findings = scan_staged()
        elif args.push:
            findings = scan_push(sys.stdin.read().splitlines())
        elif args.revision_range:
            findings = scan_range(args.revision_range)
        else:
            findings = scan_all()
    except RuntimeError as exc:
        print(f"check_secrets: {exc}", file=sys.stderr)
        return 2
    if not findings:
        return 0
    print("check_secrets: credential-shaped text found, nothing was sent:", file=sys.stderr)
    for finding in dict.fromkeys(findings):
        print(f"  {finding}", file=sys.stderr)
    print(
        "Move the value into the git-ignored .env and read it from settings. If it is real, "
        "treat it as leaked and rotate it. A documented non-secret value may carry "
        "'secret-scan: allow'.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
