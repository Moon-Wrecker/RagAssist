"""Identity domain: accounts, workspaces, sessions, one-time links, and the rules about them.

Pure Python. No framework, no database, no hashing library: those sit behind the ports in ``application``.
"""

from ragassist.modules.identity.domain.errors import (
    AccountConflictError,
    AuthenticationError,
    InvalidTokenError,
    LastAdminError,
    PasswordPolicyError,
    RateLimitedError,
    SelfChangeError,
    WorkspaceExistsError,
)
from ragassist.modules.identity.domain.models import (
    InviteKind,
    InviteRecord,
    SessionRecord,
    UserRecord,
    UserStatus,
    Workspace,
)
from ragassist.modules.identity.domain.rules import (
    MAX_PASSWORD_LENGTH,
    normalise_email,
    validate_password,
    validate_slug,
)
from ragassist.modules.identity.domain.tokens import hash_secret, issue_token, parse_token

__all__ = [
    "MAX_PASSWORD_LENGTH",
    "AccountConflictError",
    "AuthenticationError",
    "InvalidTokenError",
    "InviteKind",
    "InviteRecord",
    "LastAdminError",
    "PasswordPolicyError",
    "RateLimitedError",
    "SelfChangeError",
    "SessionRecord",
    "UserRecord",
    "UserStatus",
    "Workspace",
    "WorkspaceExistsError",
    "hash_secret",
    "issue_token",
    "normalise_email",
    "parse_token",
    "validate_password",
    "validate_slug",
]
