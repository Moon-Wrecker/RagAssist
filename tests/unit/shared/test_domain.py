"""Shared-kernel domain objects: identifiers, entities, error hierarchy."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from ragassist.shared.domain import (
    DomainError,
    Entity,
    EntityNotFoundError,
    TenantIsolationError,
    ValidationError,
    new_tenant_id,
    new_user_id,
)


def test_new_ids_are_unique_uuids() -> None:
    ids = {new_tenant_id() for _ in range(100)} | {new_user_id() for _ in range(100)}
    assert len(ids) == 200
    assert all(isinstance(i, UUID) for i in ids)


class TestDomainErrors:
    @pytest.mark.parametrize("cls", [EntityNotFoundError, TenantIsolationError, ValidationError])
    def test_specific_errors_are_domain_errors(self, cls: type[DomainError]) -> None:
        assert issubclass(cls, DomainError)
        assert issubclass(DomainError, Exception)

    def test_message_and_details(self) -> None:
        err = TenantIsolationError("breach", details={"tenant": "t1"})
        assert str(err) == "breach" == err.message
        assert err.details == {"tenant": "t1"}

    def test_details_default_to_an_independent_empty_dict(self) -> None:
        first, second = DomainError("a"), DomainError("b")
        first.details["x"] = 1
        assert second.details == {}

    def test_can_be_caught_as_the_base_class(self) -> None:
        with pytest.raises(DomainError):
            raise EntityNotFoundError("missing")


class TestEntity:
    def test_is_immutable(self) -> None:
        entity = Entity(id=uuid4(), created_at=datetime.now(UTC))
        with pytest.raises(FrozenInstanceError):
            entity.id = uuid4()  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        eid, ts = uuid4(), datetime.now(UTC)
        assert Entity(eid, ts) == Entity(eid, ts)
        assert Entity(eid, ts) != Entity(uuid4(), ts)
