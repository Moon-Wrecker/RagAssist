"""Constants from the approved specs, kept in ONE place.

``implementation_plan.md`` / ``architecture_arc42.md`` and the implementation team's
``.agents/teamwork/PROJECT.md`` disagree in a few places (see the conflict register in the test
plan). Tests read these constants instead of hard-coding literals, so resolving a conflict is a
one-line change here.
"""

from __future__ import annotations

from typing import Final

# --- C1: router labels --------------------------------------------------------------------------
ROUTE_LABELS_PLAN: Final = ("docs", "account", "mixed", "smalltalk", "human", "out_of_scope")
ROUTE_LABELS_TEAM: Final = ("rag_search", "saas_action", "general_chat", "human_escalation")
#: The label set router tests assert against. The code (decisions/ports.py ``RouteTarget``) uses the
#: team labels, and the rule is "code where it exists" -> C1 is resolved in favour of the team's set.
ROUTE_LABELS: Final = ROUTE_LABELS_TEAM

# --- C8: SSE event names ------------------------------------------------------------------------
SSE_EVENTS_PLAN: Final = ("token", "citation", "interrupt", "done")
SSE_EVENTS_TEAM: Final = ("token", "source", "done")
SSE_EVENTS: Final = SSE_EVENTS_PLAN
SSE_HEARTBEAT_SECONDS: Final = 15

# --- Quality targets (arc42 section 10) ---------------------------------------------------------
TARGET_FAITHFULNESS: Final = 0.90
TARGET_CITATION_VALIDITY: Final = 0.95
TARGET_ESCALATION_RECALL: Final = 0.80
TARGET_INJECTION_PASS_RATE: Final = 0.95
TARGET_TENANT_LEAKS: Final = 0

# --- Well-known demo tenants (services/mock_saas seed data) -------------------------------------
DEMO_TENANT_A_ID: Final = "a0000000-0000-0000-0000-000000000001"  # Acme Corp
DEMO_TENANT_B_ID: Final = "b0000000-0000-0000-0000-000000000002"  # Globex Corp

# --- Settings values used by every test run (see tests/conftest.py) -----------------------------
TEST_SECRET_KEY: Final = (
    "unit-test-secret-key-long-enough-even-for-hs512-0123456789-abcdefghijklmnop"
)
