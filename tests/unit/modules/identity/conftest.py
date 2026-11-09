"""Fixtures for the identity unit tests."""

from __future__ import annotations

import pytest
from support.identity_world import World, new_world


@pytest.fixture
def world() -> World:
    return new_world()
