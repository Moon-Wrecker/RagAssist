"""HTTP caching helpers: strong ``ETag``, ``If-None-Match`` matching and ``no-store`` for sensitive endpoints.

Goal: let the browser (and nothing else) reuse a response it already holds, and make sure responses that carry
credentials or live data are never stored anywhere.

Rules (ADR 0015):
- Every cacheable response is ``Cache-Control: private`` (never ``public``) and ``Vary: Authorization``, so a shared
  cache or CDN in front of the API cannot hand one user's response to another.
- A conditional request is answered **after** authentication and authorisation, so a ``304`` never confirms to the
  wrong caller that a resource exists or is unchanged.
- ``/v1/auth/*`` and ``/v1/events`` carry ``Cache-Control: no-store`` (tokens, cookies, a live stream).

Consulted: RFC 9111 (HTTP Caching: ``private``, ``no-cache``, ``no-store``, ``max-age``) and RFC 9110 section 8.8.3
(ETag) and 13.1.2 (If-None-Match uses the *weak* comparison, ``*`` matches any current representation).
https://www.rfc-editor.org/rfc/rfc9111 , https://www.rfc-editor.org/rfc/rfc9110
"""

from __future__ import annotations

import hashlib

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

NO_STORE = "no-store"


def etag_of(body: bytes) -> str:
    """A strong validator: the quoted SHA-256 (first 128 bits) of the exact response body."""
    return '"' + hashlib.sha256(body).hexdigest()[:32] + '"'


def _opaque_tag(value: str) -> str:
    value = value.strip()
    return value[2:] if value.startswith("W/") else value


def if_none_match_matches(header: str | None, etag: str) -> bool:
    """Weak comparison of an ``If-None-Match`` header against the current ``etag`` (RFC 9110 13.1.2)."""
    if not header:
        return False
    header = header.strip()
    if header == "*":
        return True
    current = _opaque_tag(etag)
    return any(_opaque_tag(candidate) == current for candidate in header.split(","))


def private_cache_control(max_age_seconds: int) -> str:
    """``private, max-age=N``; ``private, no-cache`` (revalidate every time) when N is 0."""
    if max_age_seconds <= 0:
        return "private, no-cache"
    return f"private, max-age={max_age_seconds}"


def validator_headers(etag: str, cache_control: str) -> dict[str, str]:
    return {"ETag": etag, "Cache-Control": cache_control, "Vary": "Authorization"}


def is_no_store_path(path: str, prefix: str) -> bool:
    """``/v1/auth`` and everything under it, and ``/v1/events``."""
    auth = f"{prefix}/auth"
    return path == auth or path.startswith(auth + "/") or path == f"{prefix}/events"


class NoStoreMiddleware:
    """Pure ASGI middleware: ``Cache-Control: no-store`` (and ``Pragma: no-cache``) on sign-in, token and event routes.

    It wraps the whole stack, so a 401, a 422 or a rate-limit 429 on those routes is covered too. Pure ASGI (not
    ``BaseHTTPMiddleware``) so a streaming response is not buffered.
    """

    def __init__(self, app: ASGIApp, prefix: str) -> None:
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_no_store_path(scope["path"], self.prefix):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = NO_STORE
                headers["Pragma"] = "no-cache"
                if "etag" in headers:
                    del headers["etag"]
            await send(message)

        await self.app(scope, receive, send_with_headers)

