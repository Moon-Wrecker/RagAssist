"""Contract for the ``ObjectStore`` port (S3 in production; the in-memory adapter in unit tests).

The port: ``put_object(key, data, content_type=..., metadata=None) -> str``, ``get_object(key) -> bytes``,
``delete_object(key) -> bool``. Subclasses provide ``store`` and may set ``missing_error`` to the
exception a missing key raises (the in-memory adapter raises ``KeyError``)."""

from __future__ import annotations

import pytest


class ObjectStoreContract:
    missing_error: type[Exception] = KeyError

    @pytest.fixture
    def store(self):  # type: ignore[no-untyped-def]  # pragma: no cover - overridden
        raise NotImplementedError

    async def test_put_then_get_round_trips_bytes(self, store) -> None:  # type: ignore[no-untyped-def]
        await store.put_object("tenants/a/doc.txt", b"hello")
        assert await store.get_object("tenants/a/doc.txt") == b"hello"

    async def test_put_returns_a_location_string(self, store) -> None:  # type: ignore[no-untyped-def]
        location = await store.put_object("loc/key", b"x")
        assert isinstance(location, str) and location

    async def test_binary_content_round_trips_unchanged(self, store) -> None:  # type: ignore[no-untyped-def]
        payload = bytes(range(256)) * 4096  # 1 MiB, every byte value
        await store.put_object("bin/all-bytes", payload, content_type="application/octet-stream")
        assert await store.get_object("bin/all-bytes") == payload

    async def test_missing_key_raises_the_documented_error(self, store) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(self.missing_error):
            await store.get_object("never/written")

    async def test_overwrite_replaces_the_content(self, store) -> None:  # type: ignore[no-untyped-def]
        await store.put_object("k", b"first")
        await store.put_object("k", b"second")
        assert await store.get_object("k") == b"second"

    async def test_delete_removes_the_object(self, store) -> None:  # type: ignore[no-untyped-def]
        await store.put_object("d", b"x")
        assert await store.delete_object("d") is True
        with pytest.raises(self.missing_error):
            await store.get_object("d")

    async def test_deleting_a_missing_key_reports_false_without_raising(self, store) -> None:  # type: ignore[no-untyped-def]
        assert await store.delete_object("never/written") is False

    async def test_keys_with_slashes_unicode_and_spaces_are_supported(self, store) -> None:  # type: ignore[no-untyped-def]
        key = "tenants/a/documents/报告 2026/Q3 summary.pdf"
        await store.put_object(key, b"pdf-bytes")
        assert await store.get_object(key) == b"pdf-bytes"

    async def test_tenant_prefixed_keys_are_independent(self, store) -> None:  # type: ignore[no-untyped-def]
        await store.put_object("tenants/a/x", b"from-a")
        await store.put_object("tenants/b/x", b"from-b")
        assert await store.get_object("tenants/a/x") == b"from-a"
        assert await store.get_object("tenants/b/x") == b"from-b"

    async def test_an_empty_object_is_stored(self, store) -> None:  # type: ignore[no-untyped-def]
        await store.put_object("empty", b"")
        assert await store.get_object("empty") == b""

    async def test_metadata_and_content_type_are_accepted(self, store) -> None:  # type: ignore[no-untyped-def]
        await store.put_object("meta", b"x", content_type="text/markdown", metadata={"tenant": "a"})
        assert await store.get_object("meta") == b"x"
