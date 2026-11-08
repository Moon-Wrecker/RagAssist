# DISPATCH — test_writer_e2e_tier3

- **Role**: E2E Test Writer (Tier 3: Multi-Tenant Boundary & Security Isolation)
- **Working Directory**: d:\Coding\RagAssist-1
- **State Folder**: d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier3
- **Original Request**: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
- **Project Index**: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
- **Test Infra**: d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md

## Exclusive Write Ownership
You have exclusive write ownership over:
- `tests/e2e/test_tier3_isolation.py`
- `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier3\`

DO NOT modify files in `src/ragassist/` (source code is owned exclusively by builders).

## Task Instructions
1. Read `TEST_INFRA.md` § 2.1 (Tier 3 definition), § 3 (Features 2, 4, 21, 26, 31).
2. Read existing `tests/e2e/conftest.py` and `tests/e2e/test_tier1_features.py` to match testing idioms and fixtures.
3. Implement `tests/e2e/test_tier3_isolation.py` specifying opaque-box adversarial security and tenant boundary tests for:
   - Tenant Data Isolation & Row-Level Security: Verify that Tenant A queries NEVER leak Tenant B documents, chunks, conversations, or checkpoints under any query permutation or connection pool reuse.
   - JWT Principal & Claim Security: Rejection of forged signatures, expired tokens, missing claims (`tenant_id`, `user_id`, `role`), tampered payloads, and unauthorized role escalations.
   - Role-Based Access Control (RBAC): Enforce that mutating SaaS actions (e.g., `update_billing_email`) require `admin` role, and non-admin callers receive immediate 403 Forbidden / domain permission errors.
   - Guardrails & Input Safety: Adversarial injection test cases (zero-width smuggling, Cyrillic/Greek homoglyphs, delimiter collisions, prompt leak attempts) ensuring fail-closed rejection.
   - Fail-Closed Security: System crashes, timeouts, or unhandled exceptions in safety or grounding checks fail closed (`is_safe=False`, `risk_score=1.0`; `is_grounded=False`, `grounding_score=0.0`).
4. Execute test verification using `BypassSandbox=True`.
5. Write `handoff.md` in `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier3\`.
6. Send a message to orchestrator upon completion.


## 2026-11-08T09:08:02Z
[Message] sender=be9621e6-d3bc-446a-abb9-2d0c46239ab1 priority=MESSAGE_PRIORITY_HIGH
You are test_writer_e2e_tier3 (E2E Test Writer for Tier 3: Multi-Tenant Boundary & Security Isolation) for project RagAssist.

CRITICAL INSTRUCTIONS:
1. You MUST read the original user request at:
   `d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md`
   before beginning work.
2. Read `d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md`, `d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md`, and `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier3\DISPATCH.md`.
3. Check existing files in:
   - `tests/e2e/conftest.py`
   - `tests/e2e/test_tier1_features.py`
4. Your exclusive write ownership is:
   - `tests/e2e/test_tier3_isolation.py`
   DO NOT modify files in `src/` (implementation code is owned by builders).

5. Test Design Requirements for Tier 3 (`test_tier3_isolation.py`):
   - Design at least 25-30 rigorous opaque-box security and isolation tests covering:
     1. Cross-Tenant Data Isolation & PostgreSQL Row-Level Security:
        - Verify Tenant A cannot read Tenant B documents or chunks.
        - Verify connection reuse does not bleed `app.tenant_id`.
        - Verify missing tenant context raises TenantIsolationError or blocks access.
     2. JWT Authentication & Claim Integrity:
        - Signature forgery rejection (tampered signature, wrong secret).
        - Expired token rejection.
        - Missing claims rejection (`tenant_id`, `user_id`, `role`).
        - Token role spoofing rejection.
     3. Role-Based Access Control (RBAC):
        - Admin vs Standard User vs Read-only Agent permissions on Mock SaaS mutating actions (`update_billing_email`).
     4. Prompt Injection & Guardrail Defense:
        - Zero-width character smuggling (`\u200b`, `\ufeff`).
        - Cyrillic/Greek homoglyphs.
        - Delimiter and instruction overriding.
        - Strict fail-closed under timeouts and errors (`is_safe=False`, `risk_score=1.0`).
   - When running pytest commands on Windows, ALWAYS set `BypassSandbox=True`.

6. Deliverables:
   - Save your completed test file to `tests/e2e/test_tier3_isolation.py`.
   - Run the test suite and verify test execution.
   - Write your handoff report in `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier3\handoff.md`.
   - Send completion message to orchestrator via `send_message`.
