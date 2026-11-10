"""Key rules (ADR 0015): tenant in every key, hashed normalised text, no raw text, no cross-tenant collision."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ragassist.platform.cache import keys as kinds
from ragassist.platform.cache.keys import CacheKeyBuilder, InvalidCacheKey, normalise_text

TENANT_A = "a0000000-0000-0000-0000-00000000000a"
TENANT_B = "b0000000-0000-0000-0000-00000000000b"
SECRET = "test-hash-secret-material"


def builder(secret: str = SECRET) -> CacheKeyBuilder:
    return CacheKeyBuilder(prefix="ragassist", secret=secret)


class TestNormalisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  Reset   my\tPASSWORD \n", "reset my password"),
            ("ＦＵＬＬ width", "full width"),  # NFKC folds full-width letters
            ("Straße", "strasse"),  # case-fold
            ("", ""),
        ],
    )
    def test_normalise(self, raw: str, expected: str) -> None:
        assert normalise_text(raw) == expected

    def test_equivalent_questions_share_a_key(self) -> None:
        b = builder()
        assert b.key(kinds.DECISION, TENANT_A, role="customer", text="Reset  my PASSWORD") == b.key(
            kinds.DECISION, TENANT_A, role="customer", text="reset my password"
        )

    @given(st.text())
    def test_normalisation_is_idempotent(self, text: str) -> None:
        once = normalise_text(text)
        assert normalise_text(once) == once


class TestTheKeyRule:
    def test_the_key_contains_the_tenant_and_not_the_text(self) -> None:
        question = "what is the refund policy for invoice 4711?"
        key = builder().key(kinds.RETRIEVAL, TENANT_A, role="agent", text=question, parts=("k6",))
        assert TENANT_A in key
        assert "refund" not in key and "4711" not in key and "policy" not in key
        assert key.startswith("ragassist:v1:")

    def test_the_variable_part_is_a_64_character_hash(self) -> None:
        key = builder().key(kinds.DECISION, TENANT_A, role="customer", text="hello")
        digest = key.split(":")[5]
        assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")

    def test_same_text_in_two_tenants_never_collides(self) -> None:
        b = builder()
        assert b.key(kinds.RETRIEVAL, TENANT_A, role="agent", text="x") != b.key(
            kinds.RETRIEVAL, TENANT_B, role="agent", text="x"
        )

    def test_same_text_in_two_roles_never_collides(self) -> None:
        b = builder()
        assert b.key(kinds.RETRIEVAL, TENANT_A, role="customer", text="x") != b.key(
            kinds.RETRIEVAL, TENANT_A, role="admin", text="x"
        )

    def test_the_hash_depends_on_the_secret(self) -> None:
        assert builder("one-secret").digest("hello") != builder("another-secret").digest("hello")

    def test_context_changes_the_hash(self) -> None:
        b = builder()
        assert b.digest("q", "openai", "m1") != b.digest("q", "openai", "m2")

    @pytest.mark.parametrize("tenant", [None, "", "a:b", "x" * 65, "t t", "../x"])
    def test_a_missing_or_malformed_tenant_is_refused(self, tenant: object) -> None:
        with pytest.raises(InvalidCacheKey):
            builder().key(kinds.RETRIEVAL, tenant, text="x")

    def test_context_without_text_is_refused(self) -> None:
        with pytest.raises(InvalidCacheKey):
            builder().key(kinds.RETRIEVAL, TENANT_A, context=("raw value",))

    def test_a_malformed_role_is_refused(self) -> None:
        with pytest.raises(InvalidCacheKey):
            builder().key(kinds.RETRIEVAL, TENANT_A, role="a:b", text="x")

    def test_parts_cannot_inject_separators(self) -> None:
        key = builder().key(kinds.RETRIEVAL, TENANT_A, text="x", parts=("a:b/c d",))
        assert key.endswith(":a_b_c_d")

    def test_tenant_prefix_covers_all_of_the_tenants_keys_and_nobody_elses(self) -> None:
        b = builder()
        mine = b.key(kinds.RETRIEVAL, TENANT_A, role="agent", text="x")
        assert mine.startswith(b.tenant_prefix(TENANT_A))
        assert mine.startswith(b.tenant_prefix(TENANT_A, kinds.RETRIEVAL))
        assert not mine.startswith(b.tenant_prefix(TENANT_A, kinds.DECISION))
        assert not b.key(kinds.RETRIEVAL, TENANT_B, role="agent", text="x").startswith(
            b.tenant_prefix(TENANT_A)
        )

    def test_counter_keys_hold_only_a_hash_of_the_identifier(self) -> None:
        key = builder().shared_counter_key("ip", "203.0.113.9")
        assert "203.0.113.9" not in key

    @given(st.text(), st.text())
    def test_different_normalised_texts_get_different_hashes(self, a: str, b: str) -> None:
        keys = builder()
        if normalise_text(a) != normalise_text(b):
            assert keys.digest(a) != keys.digest(b)

    def test_empty_prefix_or_secret_is_refused(self) -> None:
        with pytest.raises(InvalidCacheKey):
            CacheKeyBuilder(prefix="", secret=SECRET)
        with pytest.raises(InvalidCacheKey):
            CacheKeyBuilder(prefix="ragassist", secret="")
