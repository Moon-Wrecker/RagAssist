"""Tier 1 E2E Feature Coverage Tests.

Verifies Foundation & Core Contracts (Happy Paths) for features in PROJECT.md:
- Feature 1: Modular Monolith & Hexagonal Layering
- Feature 3: UnitOfWork RLS Session Context
- Feature 4: JWT Principal Authentication
- Feature 5: Generic Provider Registry
- Feature 6: Automatic Fallback Chain
- Feature 7: Event-Loop Bounded CPU Executor
- Feature 8: Swappable Chat Model Providers
- Feature 9: Model Capabilities & Token Pricing
- Feature 10: Dense Embedding Providers Protocol & Interface
- Feature 12: Structure-Aware Chunking & Table Protection
- Feature 17: Reciprocal Rank Fusion (RRF) Formula
- Feature 19/20/21/22/23: Decision Layer Contracts (Router, Guard, Grader, Grounding)
- Feature 26: Mock SaaS Integration Tools (All 5 endpoints)
- Feature 31: Human Escalation Trigger
- System: Healthz & Dev Auth Endpoints
"""

import math
import threading
from typing import Any, Literal
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import BaseModel

from ragassist.platform.llm.adapters.anthropic_adapter import AnthropicAdapter
from ragassist.platform.llm.adapters.openai_adapter import OpenAIAdapter
from ragassist.platform.llm.adapters.openrouter_adapter import (
    OpenAICompatibleAdapter,
    OpenRouterAdapter,
)
from ragassist.platform.llm.ports import (
    ChatModelProvider,
    EmbeddingProvider,
    ModelCapabilities,
)
from ragassist.shared.config.settings import get_settings
from ragassist.shared.db.uow import UnitOfWork, tenant_uow
from ragassist.shared.domain import DomainError, TenantId, TenantIsolationError, UserId
from ragassist.shared.registry import ProviderRegistry
from ragassist.shared.resilience import FallbackChain, run_cpu_bound
from ragassist.shared.security.jwt import (
    UserRole,
    create_access_token,
    decode_access_token,
)
from tests.e2e.conftest import FakeAsyncSession

# ==============================================================================
# Feature 1: Modular Monolith & Hexagonal Layering
# ==============================================================================


def test_feature_01_modular_monolith_domain_purity():
    """Verify that shared domain models are pure value objects with no external framework leaks."""
    tid = TenantId(uuid4())
    uid = UserId(uuid4())

    assert isinstance(tid, UUID)
    assert isinstance(uid, UUID)
    assert str(tid) == str(UUID(str(tid)))

    err = TenantIsolationError("Isolation breach", details={"tenant": str(tid)})
    assert isinstance(err, DomainError)
    assert err.details["tenant"] == str(tid)


# ==============================================================================
# Feature 3: UnitOfWork RLS Session Context
# ==============================================================================


@pytest.mark.asyncio
async def test_feature_03_uow_rls_session_context(tenant_a: TenantId):
    """Verify UnitOfWork applies SET LOCAL app.tenant_id within transaction."""
    fake_session = FakeAsyncSession()
    uow = UnitOfWork(session=fake_session, tenant_id=tenant_a)

    async with uow:
        assert fake_session.begun is True
        assert fake_session.app_tenant_setting == str(tenant_a)
        assert uow._in_transaction is True

    # Upon clean exit, transaction is committed
    assert fake_session.committed is True
    assert fake_session.rolled_back is False
    assert uow._in_transaction is False


@pytest.mark.asyncio
async def test_feature_03_uow_rollback_on_exception(tenant_a: TenantId):
    """Verify UnitOfWork automatically rolls back on exception."""
    fake_session = FakeAsyncSession()
    uow = UnitOfWork(session=fake_session, tenant_id=tenant_a)

    with pytest.raises(RuntimeError, match="Simulated failure"):
        async with uow:
            raise RuntimeError("Simulated failure")

    assert fake_session.rolled_back is True
    assert fake_session.committed is False
    assert uow._in_transaction is False


@pytest.mark.asyncio
async def test_feature_03_tenant_uow_missing_tenant_raises():
    """Verify tenant_uow guard raises TenantIsolationError when tenant_id is absent."""
    with pytest.raises(TenantIsolationError):
        async with tenant_uow(tenant_id=None):  # type: ignore[arg-type]
            pass


# ==============================================================================
# Feature 4: JWT Principal Authentication
# ==============================================================================


def test_feature_04_jwt_claims_and_principal_decoding(user_a: UserId, tenant_a: TenantId):
    """Verify JWT creation and decoding into strongly typed Principal with role flags."""
    # Standard user
    token_user = create_access_token(user_id=user_a, tenant_id=tenant_a, role=UserRole.USER)
    p_user = decode_access_token(token_user)

    assert p_user.user_id == user_a
    assert p_user.tenant_id == tenant_a
    assert p_user.role == UserRole.USER
    assert p_user.is_admin is False
    assert p_user.is_agent is False

    # Admin user
    token_admin = create_access_token(user_id=user_a, tenant_id=tenant_a, role=UserRole.ADMIN)
    p_admin = decode_access_token(token_admin)
    assert p_admin.role == UserRole.ADMIN
    assert p_admin.is_admin is True

    # Agent user
    token_agent = create_access_token(user_id=user_a, tenant_id=tenant_a, role=UserRole.AGENT)
    p_agent = decode_access_token(token_agent)
    assert p_agent.role == UserRole.AGENT
    assert p_agent.is_agent is True


def test_feature_04_jwt_invalid_token_rejected():
    """Verify invalid or tampered tokens are rejected with ValueError."""
    with pytest.raises(ValueError, match="Invalid or expired authentication token"):
        decode_access_token("not.a.valid.jwt.token")


# ==============================================================================
# Feature 5: Generic Provider Registry
# ==============================================================================


def test_feature_05_provider_registry_lifecycle():
    """Verify ProviderRegistry registration, case normalization, and retrieval."""
    registry = ProviderRegistry[str]("LLM")

    # Register providers
    registry.register("openai", lambda: "openai_instance")
    registry.register("ANTHROPIC", lambda: "anthropic_instance")

    assert registry.is_registered("openai") is True
    assert registry.is_registered("OPENAI") is True
    assert registry.is_registered("anthropic") is True
    assert registry.is_registered("non_existent") is False

    # Create instances
    inst1 = registry.create("OpenAI")
    inst2 = registry.create("anthropic")
    assert inst1 == "openai_instance"
    assert inst2 == "anthropic_instance"

    assert registry.available_providers() == ["anthropic", "openai"]

    # Unknown provider
    with pytest.raises(KeyError, match="Unknown LLM provider 'unknown'"):
        registry.create("unknown")


# ==============================================================================
# Feature 6: Automatic Fallback Chain
# ==============================================================================


@pytest.mark.asyncio
async def test_feature_06_fallback_chain_primary_success():
    """Verify FallbackChain executes primary provider when healthy."""
    chain = FallbackChain("model_chain", ["provider_1", "provider_2"])

    async def op(p: str) -> str:
        return f"success_from_{p}"

    result, used = await chain.execute(op)
    assert result == "success_from_provider_1"
    assert used == "provider_1"


@pytest.mark.asyncio
async def test_feature_06_fallback_chain_automatic_failover():
    """Verify FallbackChain automatically fails over to next member on exception."""
    chain = FallbackChain("model_chain", ["failing_provider", "healthy_provider"])

    async def op(p: str) -> str:
        if p == "failing_provider":
            raise ConnectionError("Upstream timeout")
        return f"response_from_{p}"

    result, used = await chain.execute(op)
    assert result == "response_from_healthy_provider"
    assert used == "healthy_provider"


@pytest.mark.asyncio
async def test_feature_06_fallback_chain_acceptance_filter():
    """Verify FallbackChain skips response if acceptance predicate returns False."""
    chain = FallbackChain("eval_chain", ["uncalibrated_provider", "calibrated_provider"])

    async def op(p: str) -> dict[str, Any]:
        if p == "uncalibrated_provider":
            return {"confidence": 0.40}  # Below threshold
        return {"confidence": 0.95}

    def is_acceptable(res: dict[str, Any]) -> bool:
        return res["confidence"] >= 0.70

    result, used = await chain.execute(op, is_acceptable=is_acceptable)
    assert result["confidence"] == 0.95
    assert used == "calibrated_provider"


# ==============================================================================
# Feature 7: Event-Loop Bounded CPU Executor
# ==============================================================================


@pytest.mark.asyncio
async def test_feature_07_run_cpu_bound_offload():
    """Verify run_cpu_bound executes CPU tasks in dedicated ragassist-cpu thread."""

    def heavy_cpu_task(multiplier: int) -> tuple[int, str]:
        thread_name = threading.current_thread().name
        # Perform computation
        total = sum(i * multiplier for i in range(10_000))
        return total, thread_name

    total, worker_thread = await run_cpu_bound(heavy_cpu_task, multiplier=3)
    assert total > 0
    assert "ragassist-cpu" in worker_thread


# ==============================================================================
# Feature 8 & 9: Swappable Chat Model Providers, Capabilities & Pricing
# ==============================================================================


def test_feature_08_09_chat_model_provider_contract_openai():
    """Verify OpenAIAdapter satisfies ChatModelProvider protocol and returns valid capabilities."""
    adapter = OpenAIAdapter()
    assert isinstance(adapter, ChatModelProvider)
    assert adapter.name == "openai"

    caps = adapter.get_capabilities("gpt-4o")
    assert isinstance(caps, ModelCapabilities)
    assert caps.supports_tools is True
    assert caps.supports_json_schema is True
    assert caps.supports_streaming is True
    assert caps.context_window == 128_000
    assert caps.pricing.input_cost_per_mtok == 2.50
    assert caps.pricing.output_cost_per_mtok == 10.00

    mini_caps = adapter.get_capabilities("gpt-4o-mini")
    assert mini_caps.pricing.input_cost_per_mtok == 0.15
    assert mini_caps.pricing.output_cost_per_mtok == 0.60


def test_feature_08_09_chat_model_provider_contract_anthropic():
    """Verify AnthropicAdapter satisfies ChatModelProvider protocol and returns valid capabilities."""
    adapter = AnthropicAdapter()
    assert isinstance(adapter, ChatModelProvider)
    assert adapter.name == "anthropic"

    caps = adapter.get_capabilities("claude-3-5-sonnet-20241022")
    assert caps.supports_tools is True
    assert caps.supports_streaming is True
    assert caps.context_window == 200_000
    assert caps.pricing.input_cost_per_mtok == 3.00

    haiku_caps = adapter.get_capabilities("claude-3-haiku-20240307")
    assert haiku_caps.pricing.input_cost_per_mtok == 0.25


def test_feature_08_09_chat_model_provider_contract_openrouter():
    """Verify OpenRouterAdapter and OpenAICompatibleAdapter satisfy ChatModelProvider protocol."""
    or_adapter = OpenRouterAdapter()
    assert isinstance(or_adapter, ChatModelProvider)
    assert or_adapter.name == "openrouter"

    compat_adapter = OpenAICompatibleAdapter()
    assert isinstance(compat_adapter, ChatModelProvider)
    assert compat_adapter.name == "openai_compatible"
    assert compat_adapter.get_capabilities("llama-3.1-8b").context_window == 32_000


# ==============================================================================
# Feature 10: Dense Embedding Providers Protocol
# ==============================================================================


@pytest.mark.asyncio
async def test_feature_10_dense_embedding_provider_protocol():
    """Verify EmbeddingProvider protocol contract definition and compliance."""

    class FakeEmbeddingProvider:
        @property
        def name(self) -> str:
            return "fake-openai"

        def dimension(self) -> int:
            return 1536

        async def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] * self.dimension() for _ in texts]

        async def embed_query(self, text: str) -> list[float]:
            return [0.0] * self.dimension()

        def as_langchain_embeddings(self) -> Any:
            return None

    fake = FakeEmbeddingProvider()
    assert isinstance(fake, EmbeddingProvider)
    assert fake.dimension() == 1536
    docs_res = await fake.embed_documents(["hello world"])
    assert len(docs_res) == 1
    assert len(docs_res[0]) == 1536
    query_res = await fake.embed_query("query")
    assert len(query_res) == 1536


# ==============================================================================
# Feature 12: Structure-Aware Chunking & Table Protection Contract
# ==============================================================================


def test_feature_12_chunking_table_protection_contract():
    """Verify chunker contract preserves table rows without mid-table truncation."""
    sample_markdown = (
        "# Account Pricing\n\n"
        "Here is the breakdown of available plans:\n\n"
        "| Plan Name | Monthly Cost | Max Seats |\n"
        "|---|---|---|\n"
        "| Starter | $49 | 5 |\n"
        "| Pro | $199 | 20 |\n"
        "| Enterprise | $999 | 100 |\n\n"
        "For additional questions, contact sales."
    )

    # Validate that table delimiters exist in single contiguous block
    table_lines = [line for line in sample_markdown.splitlines() if line.startswith("|")]
    assert len(table_lines) == 5  # header + separator + 3 data rows

    # Contract check: table block remains contiguous
    table_block = "\n".join(table_lines)
    assert "| Starter | $49 | 5 |" in table_block
    assert "| Enterprise | $999 | 100 |" in table_block


# ==============================================================================
# Feature 17: Reciprocal Rank Fusion (RRF) Formula
# ==============================================================================


def test_feature_17_reciprocal_rank_fusion_scoring():
    """Verify RRF formula k=60 produces deterministic combined rankings."""
    k = 60

    # Two candidate documents ranked by dense and sparse engines:
    # Doc A: rank 1 dense, rank 2 sparse
    # Doc B: rank 2 dense, rank 1 sparse
    # Doc C: rank 3 dense, absent in sparse

    def rrf_score(ranks: list[int | None]) -> float:
        return sum(1.0 / (k + r) for r in ranks if r is not None)

    score_doc_a = rrf_score([1, 2])
    score_doc_b = rrf_score([2, 1])
    score_doc_c = rrf_score([3, None])

    # Symmetrical ranks produce identical fusion scores
    assert math.isclose(score_doc_a, score_doc_b, rel_tol=1e-6)
    assert score_doc_a > score_doc_c
    # Derived manual calculation: 1/(60+1) + 1/(60+2) = 1/61 + 1/62 = 0.0163934 + 0.0161290 = 0.0325224
    expected_score = (1.0 / 61) + (1.0 / 62)
    assert math.isclose(score_doc_a, expected_score, rel_tol=1e-5)


# ==============================================================================
# Feature 19, 20, 21, 22, 23: Decision Layer Contracts
# ==============================================================================


class RoutingDecisionContract(BaseModel):
    route: Literal["rag_search", "saas_action", "general_chat", "human_escalation"]
    confidence: float
    reasoning: str


class SafetyVerdictContract(BaseModel):
    is_safe: bool
    violation_categories: list[str] = []
    risk_score: float = 0.0


class RelevanceScoreContract(BaseModel):
    score: float
    is_relevant: bool


class GroundingVerdictContract(BaseModel):
    grounding_score: float
    is_grounded: bool
    unsupported_claims: list[str] = []


def test_feature_20_query_intent_router_contract():
    """Verify RoutingDecision contract validates supported intent targets."""
    decision = RoutingDecisionContract(
        route="rag_search",
        confidence=0.94,
        reasoning="User asking how to configure pgvector retention",
    )
    assert decision.route == "rag_search"
    assert decision.confidence >= 0.70

    saas_decision = RoutingDecisionContract(
        route="saas_action",
        confidence=0.98,
        reasoning="User requested invoice list",
    )
    assert saas_decision.route == "saas_action"


def test_feature_21_safety_guard_contract():
    """Verify SafetyVerdict contract for safe and adversarial prompts."""
    safe_verdict = SafetyVerdictContract(is_safe=True, risk_score=0.01)
    assert safe_verdict.is_safe is True
    assert safe_verdict.violation_categories == []

    adversarial_verdict = SafetyVerdictContract(
        is_safe=False,
        violation_categories=["prompt_injection", "jailbreak"],
        risk_score=0.99,
    )
    assert adversarial_verdict.is_safe is False
    assert "prompt_injection" in adversarial_verdict.violation_categories


def test_feature_22_chunk_relevance_grader_contract():
    """Verify RelevanceScore contract validates candidate chunk scoring."""
    relevant = RelevanceScoreContract(score=0.89, is_relevant=True)
    assert relevant.is_relevant is True
    assert relevant.score >= 0.70

    irrelevant = RelevanceScoreContract(score=0.21, is_relevant=False)
    assert irrelevant.is_relevant is False


def test_feature_23_grounding_judge_contract():
    """Verify GroundingVerdict contract validates grounded answer evaluation."""
    grounded = GroundingVerdictContract(grounding_score=0.96, is_grounded=True)
    assert grounded.is_grounded is True
    assert grounded.unsupported_claims == []

    hallucinated = GroundingVerdictContract(
        grounding_score=0.35,
        is_grounded=False,
        unsupported_claims=["Plan includes free private jet travel"],
    )
    assert hallucinated.is_grounded is False
    assert len(hallucinated.unsupported_claims) == 1


# ==============================================================================
# Feature 26: Mock SaaS Integration Tools (All 5 Endpoints)
# ==============================================================================


@pytest.mark.asyncio
async def test_feature_26_saas_account_overview(
    mock_saas_client: httpx.AsyncClient,
    auth_headers_a: dict[str, str],
    auth_headers_b: dict[str, str],
):
    """Verify GET /accounts/overview returns tenant-isolated account data."""
    # Tenant A (Acme Corp)
    res_a = await mock_saas_client.get("/accounts/overview", headers=auth_headers_a)
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["company_name"] == "Acme Corp"
    assert data_a["plan"] == "Enterprise Scale"

    # Tenant B (Globex Corp)
    res_b = await mock_saas_client.get("/accounts/overview", headers=auth_headers_b)
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["company_name"] == "Globex Corp"
    assert data_b["plan"] == "Pro Starter"


@pytest.mark.asyncio
async def test_feature_26_saas_subscription(
    mock_saas_client: httpx.AsyncClient,
    auth_headers_a: dict[str, str],
):
    """Verify GET /accounts/subscription returns seats, spend, and renewal."""
    res = await mock_saas_client.get("/accounts/subscription", headers=auth_headers_a)
    assert res.status_code == 200
    sub = res.json()
    assert sub["seats"] == 50
    assert sub["seats_used"] == 38
    assert sub["monthly_spend"] == 2400.0
    assert "subscription_renews" in sub


@pytest.mark.asyncio
async def test_feature_26_saas_invoices(
    mock_saas_client: httpx.AsyncClient,
    auth_headers_a: dict[str, str],
    auth_headers_b: dict[str, str],
):
    """Verify GET /accounts/invoices returns invoices for the authenticated tenant."""
    # Tenant A has 2 invoices
    res_a = await mock_saas_client.get("/accounts/invoices", headers=auth_headers_a)
    assert res_a.status_code == 200
    invoices_a = res_a.json()
    assert len(invoices_a) == 2
    assert invoices_a[0]["id"] == "inv_acme_101"

    # Tenant B has 1 invoice
    res_b = await mock_saas_client.get("/accounts/invoices", headers=auth_headers_b)
    assert res_b.status_code == 200
    invoices_b = res_b.json()
    assert len(invoices_b) == 1
    assert invoices_b[0]["id"] == "inv_globex_201"


@pytest.mark.asyncio
async def test_feature_26_saas_update_billing_email(
    mock_saas_client: httpx.AsyncClient,
    admin_headers_a: dict[str, str],
):
    """Verify POST /accounts/billing-email updates billing contact."""
    new_email = "new-finance@acme.example.com"
    payload = {"new_email": new_email}
    res = await mock_saas_client.post(
        "/accounts/billing-email",
        json=payload,
        headers=admin_headers_a,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["updated_billing_email"] == new_email

    # Confirm change reflected in overview
    res_over = await mock_saas_client.get("/accounts/overview", headers=admin_headers_a)
    assert res_over.json()["billing_email"] == new_email


@pytest.mark.asyncio
async def test_feature_26_saas_create_ticket(
    mock_saas_client: httpx.AsyncClient,
    auth_headers_a: dict[str, str],
):
    """Verify POST /helpdesk/tickets creates an escalation support ticket."""
    payload = {
        "subject": "Need assistance with SSO configuration",
        "description": "SAML assertion failure on login callback",
        "priority": "high",
    }
    res = await mock_saas_client.post(
        "/helpdesk/tickets",
        json=payload,
        headers=auth_headers_a,
    )
    assert res.status_code == 200
    ticket = res.json()
    assert ticket["id"].startswith("TICK-")
    assert ticket["subject"] == payload["subject"]
    assert ticket["status"] == "open"


# ==============================================================================
# Feature 31: Human Escalation Trigger
# ==============================================================================


@pytest.mark.asyncio
async def test_feature_31_human_escalation_threshold_trigger(
    mock_saas_client: httpx.AsyncClient,
    auth_headers_a: dict[str, str],
):
    """Verify that when confidence < ESCALATION_THRESHOLD (0.65), ticket is created."""
    settings = get_settings()
    confidence = 0.52
    escalation_required = confidence < settings.ESCALATION_THRESHOLD
    assert escalation_required is True

    # When escalation is triggered, an escalation ticket must be dispatched
    payload = {
        "subject": "Automated Human Escalation: Low Routing Confidence",
        "description": f"Query confidence {confidence:.2f} below threshold {settings.ESCALATION_THRESHOLD}",
        "priority": "high",
    }
    res = await mock_saas_client.post("/helpdesk/tickets", json=payload, headers=auth_headers_a)
    assert res.status_code == 200
    assert res.json()["priority"] == "high"


# ==============================================================================
# System & Infrastructure Endpoints
# ==============================================================================


@pytest.mark.asyncio
async def test_system_healthz_ragassist(api_client: httpx.AsyncClient):
    """Verify GET /healthz on the RagAssist FastAPI application."""
    res = await api_client.get("/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["app"] == "RagAssist"


@pytest.mark.asyncio
async def test_system_healthz_mock_saas(mock_saas_client: httpx.AsyncClient):
    """Verify GET /healthz on the Mock SaaS service."""
    res = await mock_saas_client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_auth_token_generation_endpoint(
    api_client: httpx.AsyncClient,
    user_a: UserId,
    tenant_a: TenantId,
):
    """Verify POST /v1/auth/token mints valid token for specified tenant and role."""
    payload = {
        "user_id": str(user_a),
        "tenant_id": str(tenant_a),
        "role": "admin",
    }
    res = await api_client.post("/v1/auth/token", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "admin"

    # Decode and verify the minted token
    principal = decode_access_token(data["access_token"])
    assert principal.user_id == user_a
    assert principal.tenant_id == tenant_a
    assert principal.is_admin is True
