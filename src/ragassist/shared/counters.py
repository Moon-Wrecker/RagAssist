"""Port for counters shared between API replicas (ADR 0015).

The sign-in throttle and the rate limiter keep their counts in process memory, which is exact for one replica and
lets an attacker multiply their allowance by the number of replicas. When a shared store is configured (Redis) they
use this port instead. It lives in the shared kernel so those classes do not depend on the platform layer; the
adapter is ``ragassist.platform.cache.counters``.

Every method may answer ``None``: the store is unreachable. The caller then falls back to its own in-memory counters,
so an outage of the shared store degrades to the per-process behaviour instead of blocking sign-in or every request.
Windows are *fixed*: the first increment starts a window of ``window_seconds`` and the counter disappears with it.
"""

from __future__ import annotations

from typing import Protocol


class SharedCounters(Protocol):
    async def incr(self, name: str, ident: str, window_seconds: int) -> int | None:
        """Add one to the counter ``name``/``ident`` and return its value; ``None`` when the store is down."""
        ...

    async def peek(self, name: str, ident: str) -> int | None:
        """The current value (0 when there is none); ``None`` when the store is down."""
        ...

    async def reset(self, name: str, ident: str) -> None:
        """Forget the counter. Failures are swallowed (the window ends on its own)."""
        ...
