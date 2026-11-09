"""Resolve planned production symbols for the pending suites.

A test asks for a logical key (``need("knowledge.chunker.hybrid")``). The key maps to a module and
a symbol in ``map.py``. There are three outcomes:

* the symbol exists          -> it is returned and the test runs;
* ``PENDING``                -> the module, or a package above it, is not written yet, or it needs
                                an optional dependency that is not installed: the test is skipped;
* ``DRIFT``                  -> the symbol was renamed (the map lists its old name in ``renamed_from``
                                and the module still defines the old one), or a ragassist import inside
                                the module is broken. The test is skipped locally. In CI
                                (``RAGASSIST_STRICT_PENDING=1``) it FAILS, so a rename cannot hide.

A module that exists but does not define the planned symbol yet is PENDING, and the reason lists the
public names it does define, so a rename that was not declared is still visible in reports/pending.md.

Every skip reason starts with ``PENDING:`` or ``DRIFT:`` so the pending report can list them.
"""

from __future__ import annotations

import difflib
import importlib
import os
from typing import Any

import pytest

from support.specs.map import TARGETS


class Unresolved(Exception):
    """Base for planned-but-not-available symbols."""

    status = "UNRESOLVED"


class Pending(Unresolved):
    status = "PENDING"


class Drift(Unresolved):
    status = "DRIFT"


def strict_mode() -> bool:
    return os.environ.get("RAGASSIST_STRICT_PENDING") == "1"


def _import(module: str) -> Any:
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as exc:
        name = exc.name or ""
        if not name.startswith("ragassist"):
            raise Pending(f"{module} needs the optional dependency {name!r}") from exc
        if module == name or module.startswith(name + "."):
            raise Pending(f"{name} does not exist yet") from exc
        raise Drift(f"{module} imports the missing module {name!r}") from exc
    except ImportError as exc:
        raise Drift(f"{module} fails to import: {exc}") from exc


def resolve(key: str) -> Any:
    """Return the planned symbol for ``key`` or raise :class:`Unresolved`."""
    try:
        target = TARGETS[key]
    except KeyError:
        raise KeyError(f"unknown spec key {key!r}: add it to tests/support/specs/map.py") from None
    module = _import(target.module)
    obj: Any = module
    for part in target.symbol.split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError as exc:
            public = sorted(n for n in dir(obj) if not n.startswith("_") and n != "annotations")
            for old in target.renamed_from:
                if hasattr(obj, old):
                    raise Drift(
                        f"{target.module} renamed {old!r} to {part!r}; update the code or the map"
                    ) from exc
            # A near-identical public name is almost always a rename: report it as DRIFT, not PENDING.
            near = difflib.get_close_matches(part, public, n=1, cutoff=0.8)
            if near:
                raise Drift(
                    f"{target.module} defines {near[0]!r}, not {part!r}: a rename? update the map or the code"
                ) from exc
            hint = f"; it defines {', '.join(public[:8])}" if public else " (empty stub)"
            raise Pending(f"{target.module} does not define {part!r} yet{hint}") from exc
    return obj


def _stop(key: str, exc: Unresolved, *, module_level: bool) -> None:
    reason = f"{exc.status}: {key}: {exc}"
    if isinstance(exc, Drift) and strict_mode():
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason, allow_module_level=module_level)


def need(key: str) -> Any:
    """Inside a test or fixture: return the symbol, or skip (fail on DRIFT in strict mode)."""
    try:
        return resolve(key)
    except Unresolved as exc:
        _stop(key, exc, module_level=False)
        raise  # unreachable: pytest.skip / pytest.fail always raise


def load(key: str) -> Any:
    """At module level of a pending test module: return the symbol or skip the whole module."""
    try:
        return resolve(key)
    except Unresolved as exc:
        _stop(key, exc, module_level=True)
        raise


def available(key: str) -> bool:
    try:
        resolve(key)
    except Unresolved:
        return False
    return True
