"""The in-memory storage and queue adapters are for tests and offline runs, so they must not need the AWS
SDK. They currently share a module with the AWS adapters, which imports aioboto3 at module level (DEFECT-32)."""

from __future__ import annotations

import importlib
import sys

import pytest
from support.defects import defect
from support.specs import need


@pytest.fixture
def without_aws_sdk(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Simulate an environment where aioboto3 is not installed."""
    for name in list(sys.modules):
        if name.startswith("ragassist.platform.storage") or name.startswith(
            "ragassist.platform.queue"
        ):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "aioboto3", None)  # any import of aioboto3 now fails
    yield


class TestInMemoryAdaptersWithoutTheAwsSdk:
    @defect("DEFECT-32")
    @pytest.mark.parametrize(
        "module", ["ragassist.platform.storage.s3_adapter", "ragassist.platform.queue.sqs_adapter"]
    )
    def test_the_in_memory_adapters_import_without_aioboto3(
        self, without_aws_sdk, module: str
    ) -> None:  # type: ignore[no-untyped-def]
        importlib.import_module(module)  # must not raise ImportError for aioboto3

    def test_the_in_memory_store_is_reachable_through_the_spec_map(self) -> None:
        assert need("storage.memory") is not None
