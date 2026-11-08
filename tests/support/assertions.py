"""Reusable assertions with useful failure messages."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from uuid import UUID


def assert_no_tenant_leak(
    rows: Iterable[Mapping[str, Any]],
    allowed_tenant: UUID | str,
    *,
    key: str = "tenant_id",
    allow_global: bool = True,
) -> None:
    """Fail if any row belongs to a tenant other than ``allowed_tenant``.

    ``allow_global`` accepts rows whose tenant is ``None`` (global documents).
    """
    allowed = str(allowed_tenant)
    leaked = [
        dict(row)
        for row in rows
        if not (row.get(key) is None and allow_global) and str(row.get(key)) != allowed
    ]
    assert not leaked, f"{len(leaked)} row(s) leaked outside tenant {allowed}: {leaked[:3]}"


def assert_probabilities(
    distribution: Sequence[float] | Mapping[str, float], *, tol: float = 1e-6
) -> None:
    """Fail unless ``distribution`` is a valid probability distribution (each in [0, 1], sum 1)."""
    values = (
        list(distribution.values()) if isinstance(distribution, Mapping) else list(distribution)
    )
    assert values, "probability distribution is empty"
    assert all(0.0 <= v <= 1.0 for v in values), f"probability outside [0, 1]: {values}"
    total = sum(values)
    assert math.isclose(total, 1.0, abs_tol=tol), f"probabilities sum to {total}, expected 1.0"


def assert_sorted_descending(scores: Sequence[float]) -> None:
    """Fail unless ``scores`` is non-increasing."""
    assert all(a >= b for a, b in zip(scores, scores[1:], strict=False)), (
        f"scores are not in descending order: {list(scores)}"
    )
