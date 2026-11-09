"""Input rules for accounts: addresses, passwords and workspace slugs.

Password policy follows NIST SP 800-63B: a minimum length, a generous maximum (so hashing cost cannot be used to
exhaust the server), no composition rules and no forced rotation.
"""

from __future__ import annotations

import re

from ragassist.modules.identity.domain.errors import PasswordPolicyError
from ragassist.shared.domain import ValidationError

#: Upper bound on what we will hash. Long passphrases are fine; megabyte bodies are not.
MAX_PASSWORD_LENGTH = 128

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


def normalise_email(value: str) -> str:
    """Trim and lower-case an address, rejecting anything that is not plausibly one."""
    email = (value or "").strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        raise ValidationError("Enter a valid email address.")
    return email


def validate_password(password: str, *, min_length: int, email: str = "") -> None:
    """Raise ``PasswordPolicyError`` with a message fit to show the person."""
    if len(password) < min_length:
        raise PasswordPolicyError(f"Use at least {min_length} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Use at most {MAX_PASSWORD_LENGTH} characters.")
    if email and password.strip().lower() == email.strip().lower():
        raise PasswordPolicyError("The password must not be your email address.")


def validate_slug(value: str) -> str:
    """A workspace slug: lower-case letters, digits and hyphens, 2 to 63 characters, not starting with a hyphen."""
    slug = (value or "").strip().lower()
    if not _SLUG.match(slug):
        raise ValidationError(
            "A workspace slug uses lower-case letters, digits and hyphens (2 to 63 characters)."
        )
    return slug
