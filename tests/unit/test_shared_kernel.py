"""Unit tests for shared domain, fallback chain, and security."""

from uuid import UUID, uuid4

import pytest

from ragassist.shared.domain import DomainError, TenantId, TenantIsolationError, UserId
from ragassist.shared.resilience import FallbackChain
from ragassist.shared.security.jwt import UserRole, create_access_token, decode_access_token


def test_domain_ids_and_exceptions():
    raw_tid = uuid4()
    raw_uid = uuid4()
    tid = TenantId(raw_tid)
    uid = UserId(raw_uid)
    assert tid == raw_tid
    assert uid == raw_uid
    assert isinstance(tid, UUID)
    assert isinstance(uid, UUID)

    err = TenantIsolationError("Isolation violation", details={"tenant": str(tid)})
    assert isinstance(err, DomainError)
    assert err.details["tenant"] == str(tid)


def test_jwt_create_and_decode(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-long-12345")
    tid = TenantId(uuid4())
    uid = UserId(uuid4())

    token = create_access_token(uid, tid, UserRole.ADMIN)
    principal = decode_access_token(token)

    assert principal.user_id == uid
    assert principal.tenant_id == tid
    assert principal.role == UserRole.ADMIN
    assert principal.is_admin is True
    assert principal.is_agent is False


@pytest.mark.asyncio
async def test_fallback_chain_success():
    chain = FallbackChain("test_chain", ["provider_a", "provider_b"])

    async def op(provider: str) -> str:
        if provider == "provider_a":
            raise ValueError("provider A failed")
        return f"result_from_{provider}"

    result, used_provider = await chain.execute(op)
    assert result == "result_from_provider_b"
    assert used_provider == "provider_b"
