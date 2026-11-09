"""Pure identity rules: opaque tokens, addresses, passwords, workspace slugs."""

from __future__ import annotations

from uuid import uuid4

import pytest

from ragassist.modules.identity.domain import (
    MAX_PASSWORD_LENGTH,
    InvalidTokenError,
    PasswordPolicyError,
    hash_secret,
    issue_token,
    normalise_email,
    parse_token,
    validate_password,
    validate_slug,
)
from ragassist.shared.domain import ValidationError


class TestOpaqueTokens:
    def test_a_token_leads_with_its_tenant_and_parses_back(self) -> None:
        tenant = uuid4()
        token, token_hash = issue_token(tenant)
        assert token.startswith(f"{tenant}.")
        assert parse_token(token) == (tenant, token_hash)

    def test_only_the_hash_of_the_random_part_is_kept(self) -> None:
        token, token_hash = issue_token(uuid4())
        random_part = token.split(".", 1)[1]
        assert token_hash == hash_secret(random_part)
        assert random_part not in token_hash

    def test_two_tokens_never_collide(self) -> None:
        tenant = uuid4()
        assert len({issue_token(tenant)[0] for _ in range(200)}) == 200

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "no-dot",
            "a.b.c",
            "not-a-uuid.abc",
            f"{uuid4()}.",
            "." + "x" * 10,
            f"{uuid4()}." + "x" * 400,
        ],
    )
    def test_a_malformed_token_is_refused(self, bad: str) -> None:
        with pytest.raises(InvalidTokenError):
            parse_token(bad)


class TestEmail:
    def test_it_is_trimmed_and_lower_cased(self) -> None:
        assert normalise_email("  Ada@Example.COM ") == "ada@example.com"

    @pytest.mark.parametrize(
        "bad", ["", "plain", "a@b", "@x.com", "a b@x.com", "a@@x.com", "x" * 260 + "@x.com"]
    )
    def test_a_non_address_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            normalise_email(bad)


class TestPassword:
    def test_a_long_enough_password_passes_without_composition_rules(self) -> None:
        validate_password("a" * 12, min_length=12)  # NIST 800-63B: length, not character classes

    def test_too_short_is_refused_with_a_message_to_show(self) -> None:
        with pytest.raises(PasswordPolicyError, match="at least 12"):
            validate_password("short", min_length=12)

    def test_the_upper_bound_stops_hashing_cost_abuse(self) -> None:
        with pytest.raises(PasswordPolicyError, match="at most"):
            validate_password("a" * (MAX_PASSWORD_LENGTH + 1), min_length=12)
        validate_password("a" * MAX_PASSWORD_LENGTH, min_length=12)

    def test_the_email_address_is_not_a_password(self) -> None:
        with pytest.raises(PasswordPolicyError):
            validate_password("Ada.Lovelace@x.com", min_length=12, email="ada.lovelace@x.com")


class TestSlug:
    @pytest.mark.parametrize("ok", ["acme", "a1", "my-team-2", "x" * 63])
    def test_valid_slugs(self, ok: str) -> None:
        assert validate_slug(ok) == ok

    def test_it_is_lower_cased(self) -> None:
        assert validate_slug(" Acme ") == "acme"

    @pytest.mark.parametrize("bad", ["", "a", "-acme", "ac me", "acme_inc", "ünï", "x" * 64, "a/b"])
    def test_invalid_slugs(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            validate_slug(bad)
