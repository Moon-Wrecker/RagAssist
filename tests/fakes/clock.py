"""A controllable clock. Time only moves when a test says so, so timeouts and visibility windows
are deterministic."""

from __future__ import annotations


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self._now = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("time only moves forward")
        self._now += seconds

    async def sleep(self, seconds: float) -> None:
        """Records the request and advances time; never waits in real time."""
        self.sleeps.append(seconds)
        self.advance(seconds)
