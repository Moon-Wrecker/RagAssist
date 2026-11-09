"""Skip helpers for code the implementation team has not landed yet.

A *pending* suite is written against the planned port/contract and switches on by itself when the
module and the named public symbols appear. Every skip reason starts with ``PENDING:`` so that

    pytest -rs | grep PENDING

is a live to-do list for the other team.
"""

from __future__ import annotations

import importlib
from types import ModuleType

import pytest


def import_pending(module: str, *symbols: str) -> ModuleType:
    """Import ``module`` or skip the *whole test module* until it (and ``symbols``) exist.

    Use at the top of a test module::

        ports = import_pending("ragassist.platform.decisions.ports", "Decider", "Choice")
    """
    try:
        mod = importlib.import_module(module)
    except ImportError as exc:
        pytest.skip(f"PENDING: {module} is not importable yet ({exc})", allow_module_level=True)
    missing = [name for name in symbols if not hasattr(mod, name)]
    if missing:
        pytest.skip(
            f"PENDING: {module} does not define {', '.join(missing)} yet",
            allow_module_level=True,
        )
    return mod


def symbol_available(module: str, *symbols: str) -> bool:
    """True when ``module`` imports and defines every name in ``symbols`` (for skipif use)."""
    try:
        mod = importlib.import_module(module)
    except ImportError:
        return False
    return all(hasattr(mod, name) for name in symbols)
