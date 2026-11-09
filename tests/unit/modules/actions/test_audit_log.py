"""Audit log (plan section 7, "Audit log"): one row per decision, secrets masked, tenant-scoped, and
written inside the caller's unit of work."""

from __future__ import annotations

import copy

import pytest
from factories.principals import make_principal
from fakes.audit import InMemoryAuditStore
from support.specs import need

SECRET_KEYS = ("password", "api_key", "token", "authorization", "secret")


def audit_log(store: InMemoryAuditStore):  # type: ignore[no-untyped-def]
    return need("actions.AuditLog")(store)


async def record(log, principal, **overrides):  # type: ignore[no-untyped-def]
    kwargs = {
        "tool": "update_billing_email",
        "arguments": {"new_email": "ap@acme.example"},
        "approved": True,
        "outcome": "success",
        "uow": object(),
    }
    kwargs.update(overrides)
    return await log.record(principal, **kwargs)


class TestRows:
    async def test_one_row_is_written_per_decision(self) -> None:
        store = InMemoryAuditStore()
        await record(audit_log(store), make_principal())
        assert len(store.rows) == 1

    async def test_the_row_names_who_what_and_the_decision(self) -> None:
        store = InMemoryAuditStore()
        principal = make_principal()
        await record(audit_log(store), principal, approved=False, outcome="denied")
        row = store.rows[0]
        assert row["tenant_id"] == str(principal.tenant_id)
        assert row["user_id"] == str(principal.user_id)
        assert row["tool"] == "update_billing_email"
        assert row["approved"] is False and row["outcome"] == "denied"

    async def test_each_row_has_its_own_identifier(self) -> None:
        store = InMemoryAuditStore()
        log = audit_log(store)
        principal = make_principal()
        await record(log, principal)
        await record(log, principal)
        ids = [row["id"] for row in store.rows]
        assert len(set(ids)) == 2

    async def test_rows_are_listed_only_for_their_own_tenant(self) -> None:
        store = InMemoryAuditStore()
        log = audit_log(store)
        mine, theirs = make_principal(), make_principal()
        await record(log, mine)
        await record(log, theirs)
        listed = await log.list_for_tenant(mine.tenant_id)
        assert len(listed) == 1 and listed[0]["tenant_id"] == str(mine.tenant_id)


class TestSecrets:
    @pytest.mark.parametrize("key", SECRET_KEYS)
    async def test_secret_values_are_masked(self, key: str) -> None:
        store = InMemoryAuditStore()
        await record(
            audit_log(store),
            make_principal(),
            arguments={key: "super-secret-value", "month": "2026-10"},
        )
        stored = store.rows[0]["arguments"]
        assert "super-secret-value" not in str(stored)
        assert stored["month"] == "2026-10"

    async def test_secrets_are_masked_inside_nested_structures(self) -> None:
        store = InMemoryAuditStore()
        await record(
            audit_log(store),
            make_principal(),
            arguments={"outer": [{"api_key": "nested-secret"}], "ok": 1},
        )
        assert "nested-secret" not in str(store.rows[0]["arguments"])

    async def test_the_callers_arguments_are_not_mutated(self) -> None:
        store = InMemoryAuditStore()
        arguments = {"password": "keep-me-in-caller", "month": "2026-10"}
        original = copy.deepcopy(arguments)
        await record(audit_log(store), make_principal(), arguments=arguments)
        assert arguments == original


class TestUnitOfWork:
    async def test_the_row_is_written_in_the_callers_unit_of_work(self) -> None:
        store = InMemoryAuditStore()
        uow = object()
        await record(audit_log(store), make_principal(), uow=uow)
        assert store.received_units_of_work == [uow]

    async def test_recording_without_a_unit_of_work_is_refused(self) -> None:
        store = InMemoryAuditStore()
        with pytest.raises((ValueError, TypeError)):
            await record(audit_log(store), make_principal(), uow=None)
        assert store.rows == []
