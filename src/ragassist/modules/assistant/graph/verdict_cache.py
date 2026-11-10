"""Short-lived cache of the safety and routing verdicts for a question (ADR 0015).

Goal: asking the same question again within a few minutes does not call the decider chain again for the input guard
and the router (including its complexity score).

Rules:
* Key: tenant, the caller's role, a keyed hash of the normalised question and the decider chain configuration
  (so a changed chain never reuses a verdict from the old one). No question text is in the key.
* Only real verdicts are stored. ``DecisionService`` answers a failed check with a fail-closed verdict (safety) or a
  default route; those say "the check did not run", not what the input is, so they are returned to the caller but
  never cached: the next attempt must run the check again.
* Without a principal (no tenant to scope the key to) nothing is cached.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from ragassist.platform.cache import CacheService
from ragassist.platform.cache import keys as cache_kinds
from ragassist.platform.decisions.ports import RoutingDecision, SafetyVerdict

logger = structlog.get_logger(__name__)

#: ``provider_used`` that ``DecisionService`` sets on a verdict it made up because every decider failed.
FALLBACK_PROVIDER = "fallback_default"
_SAFETY_ERROR = "safety_check_error"


def is_real_safety_verdict(verdict: SafetyVerdict) -> bool:
    return verdict.provider_used != FALLBACK_PROVIDER and _SAFETY_ERROR not in verdict.violation_categories


def is_real_route(routing: RoutingDecision) -> bool:
    return routing.provider_used != FALLBACK_PROVIDER


@dataclass(frozen=True)
class RouterVerdict:
    routing: RoutingDecision
    complexity: float


def _scope(state_principal: Any) -> tuple[str, str] | None:
    if state_principal is None:
        return None
    tenant = getattr(state_principal, "tenant_id", None)
    if tenant is None:
        return None
    role = getattr(state_principal, "role", "")
    return str(tenant), str(getattr(role, "value", role))


class VerdictCache:
    def __init__(self, cache: CacheService, *, decider_chain: str = "", router_chain: str = "") -> None:
        self._cache = cache
        self._decider_chain = decider_chain
        self._router_chain = router_chain

    @property
    def enabled(self) -> bool:
        return self._cache.enabled

    def _key(self, scope: tuple[str, str], question: str, which: str, chain: str) -> str:
        return self._cache.keys.key(
            cache_kinds.DECISION,
            scope[0],
            role=scope[1],
            text=question,
            context=(which, chain),
            parts=(which,),
        )

    # -- safety ---------------------------------------------------------------------------------------------
    async def get_safety(self, principal: Any, question: str) -> SafetyVerdict | None:
        scope = _scope(principal)
        if scope is None or not self.enabled:
            return None
        raw = await self._cache.get_json(
            cache_kinds.DECISION, self._key(scope, question, "safety", self._decider_chain)
        )
        try:
            return SafetyVerdict.model_validate(raw) if raw is not None else None
        except ValueError:
            return None

    async def put_safety(self, principal: Any, question: str, verdict: SafetyVerdict) -> bool:
        scope = _scope(principal)
        if scope is None or not self.enabled or not is_real_safety_verdict(verdict):
            return False
        return await self._cache.set_json(
            cache_kinds.DECISION,
            self._key(scope, question, "safety", self._decider_chain),
            verdict.model_dump(),
            self._cache.ttls.decision,
        )

    # -- router (route and complexity together: one entry, one lookup) --------------------------------------
    async def get_route(self, principal: Any, question: str) -> RouterVerdict | None:
        scope = _scope(principal)
        if scope is None or not self.enabled:
            return None
        raw = await self._cache.get_json(
            cache_kinds.DECISION, self._key(scope, question, "route", self._router_chain)
        )
        if raw is None:
            return None
        try:
            return RouterVerdict(RoutingDecision.model_validate(raw["routing"]), float(raw["complexity"]))
        except (KeyError, TypeError, ValueError):
            return None

    async def put_route(
        self, principal: Any, question: str, routing: RoutingDecision, complexity: float | None
    ) -> bool:
        """Store the route with its complexity; ``complexity`` is ``None`` when the score failed (not stored)."""
        scope = _scope(principal)
        if scope is None or not self.enabled or complexity is None or not is_real_route(routing):
            return False
        return await self._cache.set_json(
            cache_kinds.DECISION,
            self._key(scope, question, "route", self._router_chain),
            {"routing": routing.model_dump(), "complexity": complexity},
            self._cache.ttls.decision,
        )
