"""Create a working ``.env`` from ``.env.example`` with freshly generated secrets.

Goal: keep every credential out of the repository while still giving a new checkout a one-command setup. The template
documents each variable; the fields that ``Settings`` requires but the template leaves blank are the secrets, and
this module fills exactly those with cryptographically random values (``secrets.token_urlsafe``). Existing values in
the template are copied untouched, and a ``.env`` that already exists is never overwritten without ``force``.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from dotenv import dotenv_values

from ragassist.shared.config.settings import Settings

_ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def blank_required_fields(example: Path) -> list[str]:
    """Settings fields that must be provided but are blank in the template: these are the secrets."""
    values = dotenv_values(example)
    return [
        name
        for name, field in Settings.model_fields.items()
        if field.is_required() and not (values.get(name) or "").strip()
    ]


def generate_value(name: str) -> str:
    """A random value suited to the field: long for signing keys, shorter for passwords."""
    if name.endswith("KEY") and name.startswith("AWS"):
        return secrets.token_hex(10).upper()
    return secrets.token_urlsafe(48 if name == "SECRET_KEY" else 24)


def render_env(example: Path, extra: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """Return the new file's text and the names of the variables that were generated."""
    blanks = set(blank_required_fields(example))
    overrides = dict(extra or {})
    generated: list[str] = []
    lines: list[str] = []
    for line in example.read_text(encoding="utf-8").splitlines():
        match = _ASSIGNMENT.match(line)
        if match:
            name, rest = match.groups()
            if name in overrides:
                line = f"{name}={overrides[name]}"
            elif name in blanks and not rest.split("#", 1)[0].strip():
                line = f"{name}={generate_value(name)}"
                generated.append(name)
        lines.append(line)
    return "\n".join(lines) + "\n", generated


def write_env(example: Path, target: Path, *, force: bool = False) -> list[str]:
    """Write ``target`` from ``example``; returns the generated variable names (never their values)."""
    if target.exists() and not force:
        raise FileExistsError(f"{target} already exists; pass force=True to overwrite it.")
    text, generated = render_env(example)
    target.write_text(text, encoding="utf-8")
    try:
        target.chmod(0o600)  # owner-only where the platform honours it
    except OSError:
        pass
    return generated
