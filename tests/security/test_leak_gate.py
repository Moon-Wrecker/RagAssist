"""The cross-tenant leak gate (plan section 5.9 "Leak gate"; arc42 section 10: tenant leakage = 0).

Each scenario seeds tenant A with canaries, reads everything tenant B can observe, and records any
A-canary that shows up. The gate fails the build on any leak. Scenarios whose planned code is not
written yet are skipped and listed in reports/pending.md; the gate still runs every scenario that is
available, and the self-test proves the detector really fails on a leak.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
import pytest
from factories.principals import make_principal
from support.leakage import canary, leaked
from support.repo import REPO_ROOT
from support.spec import DEMO_TENANT_A_ID, DEMO_TENANT_B_ID
from support.specs import need

from ragassist.shared.security.jwt import UserRole
from services.mock_saas.main import app as mock_saas_app

pytestmark = pytest.mark.security


@dataclass
class Scenario:
    name: str
    run: Callable[
        [list[str]], Awaitable[str]
    ]  # receives A's canaries, returns B's observable output
    foreign: list[str] = field(default_factory=list)


async def saas_scenario(foreign: list[str]) -> str:
    """Tenant A's billing e-mail is a canary; tenant B reads its own account and nothing else."""
    token = canary("a", "billing")
    foreign.append(token)
    admin_a = make_principal(tenant_id=DEMO_TENANT_A_ID, role=UserRole.ADMIN)
    user_b = make_principal(tenant_id=DEMO_TENANT_B_ID)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_saas_app), base_url="http://mocksaas.test"
    ) as http:
        await http.post(
            "/accounts/billing-email",
            json={"new_email": f"{token}@acme.example"},
            headers={"Authorization": f"Bearer {admin_a.raw_token}"},
        )
        observed: list[str] = []
        for path in ("/accounts/overview", "/accounts/subscription", "/accounts/invoices"):
            response = await http.get(path, headers={"Authorization": f"Bearer {user_b.raw_token}"})
            observed.append(response.text)
    return "\n".join(observed)


async def retrieval_scenario(foreign: list[str]) -> str:
    """Tenant A's private chunk must never come back for tenant B's search."""
    retriever_cls = need("retrieval.HybridRetriever")  # pending until retrieval lands
    from fakes.retriever import InMemoryRetriever

    token = canary("a", "chunk")
    foreign.append(token)
    dense, sparse = InMemoryRetriever(), InMemoryRetriever()
    for index in (dense, sparse):
        index.add(
            chunk_id="a1", document_id="doc-a", tenant_id=DEMO_TENANT_A_ID, text=f"private {token}"
        )
    retriever = retriever_cls(dense=dense, sparse=sparse, rrf_k=60)
    hits = await retriever.search(token, tenant_id=DEMO_TENANT_B_ID, k=10)
    return json.dumps([h.text for h in hits])


async def audit_scenario(foreign: list[str]) -> str:
    """Tenant A's audit rows must not be listed for tenant B."""
    audit_cls = need("actions.AuditLog")
    from fakes.audit import InMemoryAuditStore

    token = canary("a", "audit")
    foreign.append(token)
    store = InMemoryAuditStore()
    log = audit_cls(store)
    await log.record(
        make_principal(tenant_id=DEMO_TENANT_A_ID),
        tool="t",
        arguments={"note": token},
        approved=True,
        outcome="success",
        uow=object(),
    )
    return json.dumps(await log.list_for_tenant(DEMO_TENANT_B_ID), default=str)


async def graph_scenario(foreign: list[str]) -> str:
    """Tenant A's answer text must not appear in a turn that tenant B runs on the same conversation id."""
    from support.graph_harness import TENANT_B, make_graph, make_kit, run_turn

    token = canary("a", "answer")
    foreign.append(token)
    kit = make_kit()
    kit.strong.script = [f"Your code is {token}."]
    kit.retriever.add(
        chunk_id="a9",
        document_id="doc-a9",
        tenant_id=DEMO_TENANT_A_ID,
        text=f"the code is {token}",
        title="Secret codes",
    )
    graph = make_graph(kit)
    await run_turn(
        graph,
        question="what is the code?",
        principal=make_principal(tenant_id=DEMO_TENANT_A_ID),
        conversation_id="shared",
    )
    turn = await run_turn(
        graph,
        question="what is the code?",
        principal=make_principal(tenant_id=TENANT_B),
        conversation_id="shared",
    )
    return json.dumps(
        {"answer": turn.state.get("answer", ""), "citations": turn.state.get("citations", [])},
        default=str,
    )


SCENARIOS: list[Scenario] = [
    Scenario("saas billing account", saas_scenario),
    Scenario("hybrid retrieval", retrieval_scenario),
    Scenario("audit listing", audit_scenario),
    Scenario("assistant turn on a shared conversation id", graph_scenario),
]


class TestTheDetector:
    """The gate must be able to fail. A detector that never fires proves nothing."""

    def test_a_leaked_canary_is_reported(self) -> None:
        token = canary("a", "demo")
        assert leaked(f"hello {token} world", [token]) == [token]

    def test_clean_output_reports_nothing(self) -> None:
        assert leaked("nothing to see here", [canary("a", "demo")]) == []

    def test_the_canaries_are_unique_per_call(self) -> None:
        assert canary("a", "x") != canary("a", "x")

    def test_canaries_are_valid_email_local_parts(self) -> None:
        token = canary("a", "billing")
        assert token.replace("-", "").isalnum() and token == token.lower()


class TestTheGate:
    async def test_no_tenant_b_output_contains_a_tenant_a_canary(self) -> None:
        ran = 0
        total_leaks: dict[str, list[str]] = {}
        skipped: list[str] = []
        for scenario in SCENARIOS:
            foreign: list[str] = []
            try:
                output = await scenario.run(foreign)
            except pytest.skip.Exception as exc:  # planned code not written yet
                skipped.append(f"{scenario.name}: {exc}")
                continue
            ran += 1
            found = leaked(output, foreign)
            if found:
                total_leaks[scenario.name] = found
        report = {"ran": ran, "skipped": skipped, "leaks": total_leaks, "target": 0}
        target = REPO_ROOT / "reports" / "leak_gate.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        assert ran > 0, "no leak scenario could run; see reports/pending.md"
        assert not total_leaks, f"cross-tenant leaks (target 0): {total_leaks}"
