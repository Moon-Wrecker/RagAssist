"""Identity domain errors. The API layer maps each to one HTTP status; none carries a secret."""

from __future__ import annotations

from ragassist.shared.domain import DomainError


class AuthenticationError(DomainError):
    """Sign-in failed. The message is deliberately generic: it never says which part was wrong."""


class InvalidTokenError(DomainError):
    """A refresh, invite or reset token is unknown, expired, used, revoked or malformed."""


class RateLimitedError(DomainError):
    """Too many attempts; ``retry_after`` is the number of seconds until one is allowed again."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many attempts. Try again later.")
        self.retry_after = max(1, int(retry_after))


class PasswordPolicyError(DomainError):
    """The chosen password does not meet the policy; the message is safe to show the person."""


class AccountConflictError(DomainError):
    """An account (or a pending invite) already exists for that address in the workspace."""


class WorkspaceExistsError(DomainError):
    """A workspace with that slug already exists."""


class LastAdminError(DomainError):
    """The change would leave the workspace without an active administrator."""


class SelfChangeError(DomainError):
    """An administrator tried to change their own role or status, which could lock them out."""
