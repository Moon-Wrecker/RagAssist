"""JWT creation / verification (feature 4). Quality goal #1: tokens must be unforgeable and
every failure must surface as one predictable error type."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from factories import forge_token, make_token, new_tenant, new_user
from support.defects import defect
from support.spec import TEST_SECRET_KEY

from ragassist.shared.config import settings as settings_module
from ragassist.shared.domain import TenantId, UserId
from ragassist.shared.security.jwt import (
    Principal,
    UserRole,
    create_access_token,
    decode_access_token,
)


def _decode_raw(token: str) -> dict:
    return jwt.decode(token, TEST_SECRET_KEY, algorithms=["HS256"])


class TestRoundTrip:
    @pytest.mark.parametrize("role", list(UserRole))
    def test_principal_matches_what_was_encoded(self, role: UserRole) -> None:
        tenant, user = new_tenant(), new_user()
        token = create_access_token(user_id=user, tenant_id=tenant, role=role)

        principal = decode_access_token(token)

        assert isinstance(principal, Principal)
        assert principal.user_id == user
        assert principal.tenant_id == tenant
        assert principal.role is role
        assert principal.raw_token == token
        assert isinstance(principal.user_id, UUID)

    @pytest.mark.parametrize(
        ("role", "is_admin", "is_agent"),
        [
            (UserRole.USER, False, False),
            (UserRole.ADMIN, True, False),
            (UserRole.AGENT, False, True),
        ],
    )
    def test_role_flags(self, role: UserRole, is_admin: bool, is_agent: bool) -> None:
        principal = decode_access_token(make_token(role=role))
        assert (principal.is_admin, principal.is_agent) == (is_admin, is_agent)

    def test_claims_are_the_documented_set(self) -> None:
        tenant, user = new_tenant(), new_user()
        claims = _decode_raw(make_token(role=UserRole.ADMIN, tenant_id=tenant, user_id=user))
        assert claims["sub"] == str(user)
        assert claims["tenant_id"] == str(tenant)
        assert claims["role"] == "admin"
        assert {"iat", "exp"} <= claims.keys()
        assert claims["exp"] > claims["iat"]

    def test_default_expiry_comes_from_settings(self) -> None:
        claims = _decode_raw(make_token())
        assert claims["exp"] - claims["iat"] == 1440 * 60  # JWT_ACCESS_TOKEN_EXPIRE_MINUTES default

    def test_custom_expiry_is_honoured(self) -> None:
        claims = _decode_raw(make_token(expires_delta=timedelta(minutes=5)))
        assert claims["exp"] - claims["iat"] == 300

    def test_principal_is_immutable(self) -> None:
        principal = decode_access_token(make_token())
        with pytest.raises(AttributeError):
            principal.role = UserRole.ADMIN  # type: ignore[misc]

    def test_tenant_comes_only_from_the_signed_claim(self) -> None:
        """A token for tenant A can never decode to tenant B."""
        tenant_a, tenant_b = new_tenant(), new_tenant()
        assert decode_access_token(make_token(tenant_id=tenant_a)).tenant_id != tenant_b


class TestRejection:
    """Every way to break a token must raise ValueError (one error type for callers to handle)."""

    def test_expired_token(self) -> None:
        with pytest.raises(ValueError, match="Invalid or expired"):
            decode_access_token(make_token(expires_delta=timedelta(seconds=-1)))

    def test_forged_with_wrong_key(self) -> None:
        with pytest.raises(ValueError):
            decode_access_token(forge_token(key="some-other-secret-that-is-long-enough-xx"))

    def test_algorithm_none(self) -> None:
        with pytest.raises(ValueError):
            decode_access_token(forge_token(algorithm="none"))

    def test_algorithm_confusion_hs512_with_correct_key(self) -> None:
        """Only the configured algorithm is accepted, even when the key is right."""
        with pytest.raises(ValueError):
            decode_access_token(forge_token(algorithm="HS512"))

    def test_tampered_payload_keeps_old_signature(self) -> None:
        original = make_token(role=UserRole.USER)
        header, payload, signature = original.split(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        claims["role"] = "admin"
        forged_payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        with pytest.raises(ValueError):
            decode_access_token(f"{header}.{forged_payload}.{signature}")

    def test_tampered_signature(self) -> None:
        header, payload, signature = make_token().split(".")
        flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
        with pytest.raises(ValueError):
            decode_access_token(f"{header}.{payload}.{flipped}")

    @pytest.mark.parametrize("claim", ["sub", "tenant_id"])
    def test_missing_identity_claim(self, claim: str) -> None:
        with pytest.raises(ValueError):
            decode_access_token(forge_token(drop=(claim,)))

    @pytest.mark.parametrize("claim", ["sub", "tenant_id"])
    def test_identity_claim_not_a_uuid(self, claim: str) -> None:
        with pytest.raises(ValueError):
            decode_access_token(forge_token(claims={claim: "not-a-uuid"}))

    @pytest.mark.parametrize("role", ["superadmin", "ADMIN ", "", "root"])
    def test_unknown_role(self, role: str) -> None:
        with pytest.raises(ValueError):
            decode_access_token(forge_token(claims={"role": role}))

    def test_not_yet_valid(self) -> None:
        future = datetime.now(UTC) + timedelta(hours=1)
        with pytest.raises(ValueError):
            decode_access_token(forge_token(claims={"nbf": future}))

    @pytest.mark.parametrize("garbage", ["", " ", "abc", "a.b.c", "Bearer x.y.z", "....", "é.ü.ñ"])
    def test_garbage_input(self, garbage: str) -> None:
        with pytest.raises(ValueError):
            decode_access_token(garbage)

    def test_rotating_the_secret_invalidates_existing_tokens(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token = make_token()
        monkeypatch.setenv("SECRET_KEY", "rotated-secret-key-that-is-long-enough-for-hs256-xyz")
        settings_module._settings = None  # force re-read
        with pytest.raises(ValueError):
            decode_access_token(token)

    def test_missing_role_defaults_to_least_privileged(self) -> None:
        """Pins current behaviour: no role claim -> USER (never ADMIN)."""
        principal = decode_access_token(forge_token(drop=("role",)))
        assert principal.role is UserRole.USER

    @defect("DEFECT-15")
    def test_token_without_expiry_is_rejected(self) -> None:
        """A token that never expires is a standing credential; `exp` must be required."""
        with pytest.raises(ValueError):
            decode_access_token(forge_token(drop=("exp",)))


class TestIdentifiers:
    def test_ids_are_unique(self) -> None:
        assert len({make_token() for _ in range(20)}) == 20

    def test_types_are_uuid_newtypes(self) -> None:
        principal = decode_access_token(
            make_token(tenant_id=TenantId(uuid4()), user_id=UserId(uuid4()))
        )
        assert isinstance(principal.tenant_id, UUID)
