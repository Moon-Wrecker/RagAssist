"""AGENTS.md section 3.7: the development credentials that once shipped as defaults must never come back.

The patterns are assembled at run time, so this file does not contain them and cannot trip itself. The scan
covers every file git tracks (code, tests, docs, workflows, agent notes) but not the untracked local ``.env``.
"""

from __future__ import annotations

import re
import subprocess

import pytest
from support.repo import REPO_ROOT

# Each entry is split so that no literal appears in this file.
RETIRED_DEFAULTS = {
    "former application-role password": "app_" + "password",
    "former admin connection string": "postgres" + ":" + "postgres@",
    "former dev token secret": "dev-stub-" + "secret",
    "former template signing key": "change-this-in-" + "production",
    "former placeholder API key": "dummy-key-" + "for-testing",
    "former placeholder live key": "sk-" + "live-",
}
# Secret-shaped strings that identify a real credential from a provider.
PROVIDER_KEY_SHAPES = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS access key id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "LocalStack auth token": re.compile(r"ls-[A-Za-z0-9]{8}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def tracked_text_files() -> list[tuple[str, str]]:
    listing = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "ls-files", "-z"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if listing.returncode != 0:
        pytest.skip("not a git checkout")
    files: list[tuple[str, str]] = []
    for name in filter(None, listing.stdout.decode("utf-8").split("\0")):
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        try:
            files.append((name, path.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            continue  # binary file
    return files


@pytest.fixture(scope="module")
def corpus() -> list[tuple[str, str]]:
    return tracked_text_files()


@pytest.mark.parametrize("label", sorted(RETIRED_DEFAULTS))
def test_a_retired_default_is_not_reintroduced(label: str, corpus: list[tuple[str, str]]) -> None:
    needle = RETIRED_DEFAULTS[label]
    offenders = [name for name, text in corpus if needle in text]
    assert not offenders, f"{label} found in: {offenders}"


@pytest.mark.parametrize("label", sorted(PROVIDER_KEY_SHAPES))
def test_no_provider_credential_is_committed(label: str, corpus: list[tuple[str, str]]) -> None:
    pattern = PROVIDER_KEY_SHAPES[label]
    offenders = [name for name, text in corpus if pattern.search(text)]
    assert not offenders, f"{label} shape found in: {offenders}"
