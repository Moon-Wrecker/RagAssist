"""Canary-based cross-tenant leak detection.

Every tenant's data is seeded with a canary: a unique token that can only appear in that tenant's
output if data crossed a tenant boundary. A scenario runs as tenant B and returns everything B can
observe; any canary belonging to tenant A found in that output is a leak.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable


def canary(label: str, scope: str) -> str:
    """A unique, lowercase token that is also valid in an e-mail local part."""
    return f"canary-{label.lower()}-{scope}-{uuid.uuid4().hex[:10]}"


def leaked(observable_output: str, foreign_canaries: Iterable[str]) -> list[str]:
    """The foreign canaries that appear in B's observable output (sorted, without duplicates)."""
    return sorted({token for token in foreign_canaries if token and token in observable_output})
