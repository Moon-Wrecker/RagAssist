# ADR 0002: Row-Level Security (RLS) and Transactional Context Isolation

## Context & Problem
In multi-tenant SaaS RAG applications, relying exclusively on application-level filtering (`WHERE tenant_id = :id`) is prone to human error, missed query conditions, or subtle ORM leakage bugs that can result in catastrophic data cross-contamination.

## Decision
We enforce multi-tenant isolation through **defense-in-depth**:
1. Every tenant-scoped database table has PostgreSQL Row-Level Security enabled (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`).
2. Policies define `tenant_id = current_setting('app.tenant_id', true)::uuid OR tenant_id IS NULL`.
3. Application connections connect as a non-superuser role (`app_user`).
4. All repository access runs inside `UnitOfWork` which opens an explicit transaction and executes `SET LOCAL app.tenant_id = :tenant_id`.
5. Because `SET LOCAL` is scoped strictly to the transaction boundary, connection-pooled asyncpg sessions can never leak tenant state across requests.

## Consequences
- **Positive:** Even if application logic omits a tenant filter in a raw query or join, the database engine guarantees that zero rows from other tenants are returned.
- **Positive:** Unit and security tests can mathematically verify isolation by querying tables without `WHERE` clauses.

