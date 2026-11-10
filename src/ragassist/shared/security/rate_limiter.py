"""In-memory rate limiting middleware and dependencies for RagAssist API.

Consulted References:
- RFC 6585 (Additional HTTP Status Codes - 429 Too Many Requests).
- IETF Draft RateLimit Headers (RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset):
  https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-ratelimit-headers
- Token Bucket / Sliding Window in-memory rate limiting patterns.
"""

from __future__ import annotations

import time
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from ragassist.shared.config.settings import get_settings
from ragassist.shared.counters import SharedCounters


class SlidingWindowRateLimiter:
    """Sliding-window in-memory rate limiter per client key."""

    def __init__(self, limit: int = 300, window_seconds: float = 60.0, max_keys: int = 50_000) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._max_keys = max_keys
        self._history: dict[str, list[float]] = defaultdict(list)

    def _make_room(self, now: float) -> None:
        """Drop keys with no request inside the window; if the table is still full, drop the oldest keys."""
        cutoff = now - self.window_seconds
        for key in [k for k, v in self._history.items() if not v or v[-1] <= cutoff]:
            del self._history[key]
        while len(self._history) >= self._max_keys:
            del self._history[next(iter(self._history))]

    def is_allowed(self, key: str) -> tuple[bool, int, float]:
        """Check if request for key is permitted under rate limit.

        Returns (allowed, remaining, reset_seconds).
        """
        now = time.time()
        window_start = now - self.window_seconds
        if key not in self._history and len(self._history) >= self._max_keys:
            self._make_room(now)
        # Evict timestamps outside current sliding window
        self._history[key] = [t for t in self._history[key] if t > window_start]

        count = len(self._history[key])
        if count >= self.limit:
            oldest = self._history[key][0]
            reset_seconds = max(1.0, (oldest + self.window_seconds) - now)
            return False, 0, reset_seconds

        self._history[key].append(now)
        remaining = self.limit - (count + 1)
        reset_seconds = self.window_seconds
        return True, remaining, reset_seconds


    async def is_allowed_shared(self, shared: SharedCounters, key: str) -> tuple[bool, int, float] | None:
        """The same decision from counters shared between replicas (a fixed window, one counter per client).

        ``None`` when the shared store is unreachable: the caller then uses ``is_allowed`` on its own counts.
        ``reset_seconds`` is the whole window, an upper bound (the shared counter's remaining time is not read).
        """
        count = await shared.incr("ratelimit", key, int(self.window_seconds))
        if count is None:
            return None
        if count > self.limit:
            return False, 0, self.window_seconds
        return True, self.limit - count, self.window_seconds


_global_limiter = SlidingWindowRateLimiter(limit=300, window_seconds=60.0)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces per-client rate limits and injects rate limit headers."""

    def __init__(
        self,
        app: ASGIApp,
        limiter: SlidingWindowRateLimiter | None = None,
        exempt_paths: set[str] | None = None,
        shared: SharedCounters | None = None,
    ) -> None:
        super().__init__(app)
        self.limiter = limiter or _global_limiter
        self.shared = shared
        # The events stream is one long-lived request per tab, not a flood of requests; the per-user stream cap
        # (``EVENTS_MAX_STREAMS_PER_USER``) bounds it instead.
        self.exempt_paths = exempt_paths or {
            "/healthz",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            f"{get_settings().API_V1_PREFIX}/events",
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        # Key on the client address. The Authorization header is unverified at this point, so keying on it would
        # give every forged value its own fresh bucket (no limit at all) and an ever-growing table.
        key = request.client.host if request.client else "unknown"

        decision = await self.limiter.is_allowed_shared(self.shared, key) if self.shared else None
        allowed, remaining, reset_seconds = decision if decision is not None else self.limiter.is_allowed(key)
        if not allowed:
            return Response(
                content='{"detail": "Too Many Requests: Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(int(reset_seconds)),
                    "X-RateLimit-Limit": str(self.limiter.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_seconds)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_seconds))
        return response
