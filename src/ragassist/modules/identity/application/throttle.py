"""Sign-in throttle: failed attempts per account and attempts per client address, inside a sliding window.

Two limits, because each stops a different attack: the per-account limit stops password guessing against one
person (from any number of addresses); the per-address limit stops one client from walking many accounts. Only
*failures* count against an account, so a legitimate user is never locked out by their own successful sign-ins,
and a success clears the account's count. Keys are hashed, so no address or email is kept in memory, and the table
is bounded, so spraying random identifiers cannot grow it without limit.

By default this is per process. With ``shared`` counters (Redis, ADR 0015) the same two limits hold across API
replicas, using fixed windows of ``window_seconds`` (the first failure starts the account's window); when the shared
store is unreachable each call falls back to the exact in-process logic below.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from collections.abc import Callable

from ragassist.modules.identity.domain import RateLimitedError
from ragassist.shared.counters import SharedCounters

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
        shared: SharedCounters | None = None,
    ) -> None:
        self._max_failures = max_failures
        self._max_per_ip = max_per_ip
        self._window = float(window_seconds)
        self._clock = clock
        self._max_keys = max_keys
        self._shared = shared
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

    # -- the same three operations for the async caller: shared counters first, local as the fallback ---------
    async def acheck(self, ip: str, workspace: str, email: str) -> None:
        shared = self._shared
        if shared is not None:
            window = int(self._window)
            ip_count = await shared.incr("loginip", _key("ip", ip), window)
            if ip_count is not None:
                if ip_count > self._max_per_ip:
                    raise RateLimitedError(window)
                failures = await shared.peek("loginfail", _key(workspace, email))
                if failures is not None:
                    if failures >= self._max_failures:
                        raise RateLimitedError(window)
                    return
        self.check(ip, workspace, email)

    async def arecord_failure(self, workspace: str, email: str) -> None:
        if self._shared is not None:
            if await self._shared.incr("loginfail", _key(workspace, email), int(self._window)) is not None:
                return
        self.record_failure(workspace, email)

    async def arecord_success(self, workspace: str, email: str) -> None:
        if self._shared is not None:
            await self._shared.reset("loginfail", _key(workspace, email))
        self.record_success(workspace, email)

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
