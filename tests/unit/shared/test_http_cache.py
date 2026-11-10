"""HTTP caching helpers (ADR 0015): validators, ``If-None-Match`` matching and the ``no-store`` middleware."""

from __future__ import annotations

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from ragassist.shared.http_cache import (
    NoStoreMiddleware,
    etag_of,
    if_none_match_matches,
    is_no_store_path,
    private_cache_control,
)


class TestEtag:
    def test_the_validator_is_a_quoted_strong_tag_of_the_exact_bytes(self) -> None:
        tag = etag_of(b'{"a":1}')
        assert tag.startswith('"') and tag.endswith('"') and not tag.startswith("W/")
        assert tag == etag_of(b'{"a":1}')
        assert tag != etag_of(b'{"a":2}')


class TestIfNoneMatch:
    TAG = '"abc"'

    @pytest.mark.parametrize(
        "header",
        ['"abc"', 'W/"abc"', '"x", "abc"', '"x",W/"abc" , "y"', "*", "  *  "],
    )
    def test_matching_forms(self, header: str) -> None:
        assert if_none_match_matches(header, self.TAG)

    @pytest.mark.parametrize("header", [None, "", '"abd"', '"x", "y"', "abc", '""'])
    def test_non_matching_forms(self, header: str | None) -> None:
        assert not if_none_match_matches(header, self.TAG)

    def test_a_weak_current_tag_matches_a_strong_candidate(self) -> None:
        assert if_none_match_matches('"abc"', 'W/"abc"')


class TestCacheControl:
    def test_private_with_max_age(self) -> None:
        assert private_cache_control(60) == "private, max-age=60"

    def test_zero_means_revalidate_every_time_and_is_still_private(self) -> None:
        assert private_cache_control(0) == "private, no-cache"
        assert "public" not in private_cache_control(60)


class TestNoStorePaths:
    @pytest.mark.parametrize(
        "path",
        ["/v1/auth", "/v1/auth/login", "/v1/auth/token", "/v1/auth/invites/accept", "/v1/events"],
    )
    def test_covered(self, path: str) -> None:
        assert is_no_store_path(path, "/v1")

    @pytest.mark.parametrize(
        "path",
        [
            "/v1/authentic",
            "/v1/chunks/x",
            "/v1/documents",
            "/healthz",
            "/v1/events/x",
            "/auth/login",
        ],
    )
    def test_not_covered(self, path: str) -> None:
        assert not is_no_store_path(path, "/v1")


async def _ok(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok", headers={"Cache-Control": "public, max-age=999", "ETag": '"x"'})


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    routes = [Route(p, _ok) for p in ("/v1/auth/login", "/v1/events", "/v1/chunks/1", "/healthz")]
    app = NoStoreMiddleware(Starlette(routes=routes), prefix="/v1")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


class TestNoStoreMiddleware:
    @pytest.mark.parametrize("path", ["/v1/auth/login", "/v1/events"])
    async def test_sensitive_routes_are_no_store_whatever_the_handler_said(
        self, client, path
    ) -> None:  # type: ignore[no-untyped-def]
        response = await client.get(path)
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"
        assert "etag" not in response.headers

    @pytest.mark.parametrize("path", ["/v1/chunks/1", "/healthz"])
    async def test_other_routes_are_left_alone(self, client, path) -> None:  # type: ignore[no-untyped-def]
        response = await client.get(path)
        assert response.headers["cache-control"] == "public, max-age=999"
        assert response.headers["etag"] == '"x"'
