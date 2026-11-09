"""Sign-in throttle: failed attempts per account and attempts per client address, inside a sliding window.

Two limits, because each stops a different attack: the per-account limit stops password guessing against one
person (from any number of addresses); the per-address limit stops one client from walking many accounts. Only
*failures* count against an account, so a legitimate user is never locked out by their own successful sign-ins,
and a success clears the account's count. Keys are hashed, so no address or email is kept in memory, and the table
is bounded, so spraying random identifiers cannot grow it without limit.

This is per process. A deployment with several API replicas needs a shared limiter (documented in ADR 0007); the
class is small on purpose so that swap is local.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from collections.abc import Callable

from ragassist.modules.identity.domain import RateLimitedError

_MAX_KEYS = 20_000


def _key(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).lower().encode("utf-8")).hexdigest()


class LoginThrottle:
    def __init__(
        self,
        *,
        max_failures: int,
        max_per_ip: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = _MAX_KEYS,
    ) -> None:
        self._max_failures = max_failures
        self._max_per_ip = max_per_ip
        self._window = float(window_seconds)
        self._clock = clock
        self._max_keys = max_keys
        self._ip: dict[str, deque[float]] = {}
        self._failures: dict[str, deque[float]] = {}

    def check(self, ip: str, workspace: str, email: str) -> None:
        """Count this attempt against the address and refuse it when either limit is already reached."""
        now = self._clock()
        ip_events = self._events(self._ip, _key("ip", ip), now)
        if len(ip_events) >= self._max_per_ip:
            raise RateLimitedError(self._retry_after(ip_events, now))
        failures = self._events(self._failures, _key(workspace, email), now)
        if len(failures) >= self._max_failures:
            raise RateLimitedError(self._retry_after(failures, now))
        ip_events.append(now)

    def record_failure(self, workspace: str, email: str) -> None:
        now = self._clock()
        self._events(self._failures, _key(workspace, email), now).append(now)

    def record_success(self, workspace: str, email: str) -> None:
        self._failures.pop(_key(workspace, email), None)

    # ------------------------------------------------------------------------------------------
    def _events(self, table: dict[str, deque[float]], key: str, now: float) -> deque[float]:
        events = table.get(key)
        if events is None:
            if len(table) >= self._max_keys:
                self._evict(table, now)
            events = table[key] = deque()
        while events and events[0] <= now - self._window:
            events.popleft()
        return events

    def _evict(self, table: dict[str, deque[float]], now: float) -> None:
        for key in [k for k, v in table.items() if not v or v[-1] <= now - self._window]:
            del table[key]
        while len(table) >= self._max_keys:  # still full of live keys: drop the oldest insertions
            del table[next(iter(table))]

    def _retry_after(self, events: deque[float], now: float) -> int:
        return int(events[0] + self._window - now) + 1
