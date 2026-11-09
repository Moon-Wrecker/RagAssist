"""Helpers for HTTP routes that may not be mounted yet."""

from __future__ import annotations

import re
from uuid import uuid4

import pytest

from support.specs.map import ROUTES


def _walk(routes: object):  # type: ignore[no-untyped-def]
    """Every concrete route, descending into routers that FastAPI wraps when they are included."""
    for route in routes:  # type: ignore[attr-defined]
        if hasattr(route, "methods") and hasattr(route, "path"):
            yield route
        elif hasattr(route, "effective_candidates"):
            yield from _walk(route.effective_candidates())
        elif hasattr(route, "routes"):
            yield from _walk(route.routes)


def mounted_routes(app: object) -> set[tuple[str, str]]:
    """Every (method, path template) the application serves, without HEAD/OPTIONS."""
    found: set[tuple[str, str]] = set()
    for route in _walk(app.routes):  # type: ignore[attr-defined]
        for method in route.methods - {"HEAD", "OPTIONS"}:
            found.add((method, route.path))
    return found


def require_route(app: object, key: str) -> tuple[str, str]:
    """Return (method, path) for a named route, or skip as PENDING when it is not mounted."""
    method, path = ROUTES[key]
    if (method, path) not in mounted_routes(app):
        pytest.skip(f"PENDING: route {method} {path} ({key}) is not mounted yet")
    return method, path


def concrete(path_template: str) -> str:
    """Fill every ``{param}`` with a fresh UUID so the request reaches the route."""
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid4()), path_template)
