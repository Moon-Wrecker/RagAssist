"""Fixtures for the LangGraph scenarios. The harness itself lives in support/graph_harness.py."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from factories.principals import make_principal
from fakes.decider import FakeDecider  # noqa: F401
from support.graph_harness import TENANT_A, TENANT_B, Kit, ScriptedDecider, make_graph, make_kit  # noqa: F401

from ragassist.shared.security.jwt import UserRole


@pytest.fixture
def principal_a():  # type: ignore[no-untyped-def]
    return make_principal(role=UserRole.USER, tenant_id=TENANT_A)


@pytest.fixture
def principal_b():  # type: ignore[no-untyped-def]
    return make_principal(role=UserRole.USER, tenant_id=TENANT_B)


@pytest.fixture
def kit_factory() -> Callable[..., Kit]:
    return make_kit


@pytest.fixture
def kit(kit_factory):  # type: ignore[no-untyped-def]
    return kit_factory()
