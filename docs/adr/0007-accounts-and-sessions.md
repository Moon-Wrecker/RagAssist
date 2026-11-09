# ADR 0007: Accounts, Passwords, Refresh Sessions and Invite Links

## Context & Problem
The only way to obtain a token was `POST /v1/auth/token`, a development stub that signs whatever identity it is
given. A web app needs real sign-in: people with passwords, sessions that survive a page reload without keeping a
long-lived secret where script can read it, and a way to add people without an email service.

Sign-in has a structural problem with row-level security (ADR 0002): every tenant table is isolated by
`app.tenant_id`, but at sign-in the tenant is not known yet.

## Decision
1. **Identity.** A person signs in with *workspace slug + email + password*. An address names one account per
   workspace (`unique (tenant_id, lower(email))`); the same address may exist in several workspaces.
2. **Passwords.** argon2id through `argon2-cffi` (library defaults, the RFC 9106 low-memory profile), run on the
   bounded CPU executor. Minimum length from settings (default 12), maximum 128, no composition rules (NIST SP
   800-63B). Hashes made with older parameters are upgraded on the next successful sign-in.
3. **Generic failure, constant work.** Unknown workspace, unknown email, disabled account, an account with no
   password yet and a wrong password return the same `401` and each spends exactly one verification (a dummy hash
   on the "not found" paths), so neither the message nor the timing reveals which one it was.
4. **Throttle.** Failed attempts per account and attempts per client address, in a sliding window, from settings.
   Only failures count against an account; a success clears it. Keys are hashed and the tables bounded. The
   limiter is per process; a deployment with several API replicas needs a shared one (the class is small so the swap
   is local). Behind a reverse proxy the proxy address must be trusted (`--proxy-headers`) so the client address,
   not the proxy's, is counted.
5. **Sessions.** Login returns a short-lived access JWT (the same token the rest of the API already verifies) in the
   body, to be kept in memory. A long-lived refresh token travels only in an `httpOnly`, `SameSite=Strict` cookie
   scoped to `/v1/auth`, `Secure` from settings (required outside development and test).
6. **Rotation with replay detection.** Every refresh marks the presented token rotated and issues a new one in the
   same *family*. Presenting a token that was already rotated or revoked means it was copied, so the whole family is
   revoked. The claim is one `UPDATE ... WHERE rotated_at IS NULL AND revoked_at IS NULL RETURNING`, so concurrent
   refreshes cannot both win. Two tabs refreshing at once can therefore end the session; the web client refreshes
   single-flight.
7. **CSRF.** The endpoints that act on the cookie (`refresh`, `logout`) require an `Origin` in `CORS_ORIGINS` or
   `WEB_BASE_URL`, on top of `SameSite=Strict`.
8. **Opaque tokens `{tenant_id}.{random}`.** Refresh, invite and reset tokens carry the tenant id first, so the
   store can open the right RLS scope before looking the token up. The random part is 256 bits; only its SHA-256 is
   stored (a fast hash is correct for a high-entropy secret).
9. **Slug lookup without a tenant.** `tenants` gets one extra read policy exposing the row whose slug equals the
   transaction-local `app.tenant_slug`. The application sets it only for that lookup, so it can resolve a slug but
   still cannot list workspaces. A `SECURITY DEFINER` function was rejected: `FORCE ROW LEVEL SECURITY` binds the
   function owner too, and it would add a privileged code path.
10. **No default passwords, no email service.** Every account starts with no password. `ragassist workspace create`
    creates a workspace and its first administrator and prints a one-time link; administrators add people by
    inviting them and handing over a link; `seed` prints a link per demo account. Links live `AUTH_INVITE_HOURS`,
    work once, and carry the token in the URL fragment (`/accept#token=...`), which browsers never send to servers.
    The server returns a link once and stores only its hash. A password reset is the same mechanism on an existing
    account and ends all of its sessions.
11. **Guard rails.** An administrator cannot change their own role or status, and the last active administrator
    cannot be demoted or disabled (checked against the database, because a demoted administrator's access token
    stays valid until it expires). Disabling a member revokes their refresh sessions and pending links at once;
    already-issued access tokens expire within `AUTH_ACCESS_TOKEN_MINUTES`. `GET /v1/auth/me` checks the account
    is still active.
12. **The dev token stub stays**, restricted to development and test.

## Consequences
- **Positive:** no long-lived secret in script-readable storage; a stolen refresh token is detected on first
  replay; no credential is ever chosen or seen by someone else; isolation still rests on RLS rather than on
  application checks.
- **Negative:** the throttle is per process; two simultaneous refreshes from one browser can end the session; an
  access token outlives a role change or a disable by up to its lifetime; invite links must be delivered by a human.
- **Operational:** run `ragassist db upgrade` (migration `0002`), then `ragassist workspace create` or
  `ragassist seed`. New settings are in `.env.example` (`AUTH_*`, `WEB_BASE_URL`).

## Consulted
OWASP Authentication, Session Management, Password Storage and Forgot Password cheat sheets; NIST SP 800-63B
(memorised secrets); RFC 9106 (Argon2) and the argon2-cffi documentation; the OAuth 2.0 Security Best Current
Practice on refresh-token rotation and replay detection; PostgreSQL row security policies and `set_config`;
FastAPI `Cookie` and security tutorials; MDN on `Set-Cookie` (`HttpOnly`, `SameSite`, `Secure`, `Path`) and on the
URL fragment not being sent in requests.
