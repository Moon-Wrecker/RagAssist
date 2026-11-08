"""FallbackChain for reranking models."""

import asyncio
from collections.abc import Sequence
import structlog
from ragassist.platform.rerank.ports import Candidate, ChainResult, Reranker, Scored

logger = structlog.get_logger(__name__)


class RerankerChain:
    """Orchestrates an ordered chain of rerankers with automatic fallback and timeouts."""

    def __init__(
        self,
        members: Sequence[Reranker],
        timeout_ms: int = 1500,
        enabled: bool = True,
        default_top_n: int = 6,
    ) -> None:
        self.members = list(members)
        self.timeout_ms = timeout_ms
        self.enabled = enabled
        self.default_top_n = default_top_n

    async def rerank(
        self,
        query: str,
        candidates: list[Candidate],
        *,
        top_n: int | None = None,
    ) -> ChainResult:
        """Rerank candidates using the first succeeding member in the chain."""
        n = top_n if top_n is not None else self.default_top_n

        if not candidates or n <= 0:
            default_name = self.members[0].name if self.members else "none"
            return ChainResult(items=[], reranker=default_name)

        if not self.enabled:
            logger.debug("reranker_chain.disabled", count=len(candidates))
            items = [Scored(chunk_id=c.chunk_id, score=c.score) for c in candidates[:n]]
            return ChainResult(items=items, reranker="none")

        timeout_sec = self.timeout_ms / 1000.0

        for member in self.members:
            member_name = member.name.lower()
            if member_name == "none":
                items = [Scored(chunk_id=c.chunk_id, score=c.score) for c in candidates[:n]]
                return ChainResult(items=items, reranker="none")

            try:
                scored = await asyncio.wait_for(
                    member.rerank(query, candidates, top_n=n),
                    timeout=timeout_sec,
                )
                logger.debug(
                    "reranker_chain.succeeded",
                    member=member.name,
                    scored_count=len(scored),
                )
                return ChainResult(items=scored, reranker=member.name)
            except TimeoutError:
                logger.warning(
                    "reranker_chain.timeout",
                    member=member.name,
                    timeout_ms=self.timeout_ms,
                )
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "reranker_chain.failed",
                    member=member.name,
                    error=str(exc),
                )
                continue

        logger.warning(
            "reranker_chain.all_failed_defaulting_to_rrf",
            chain_length=len(self.members),
        )
        fallback_items = [Scored(chunk_id=c.chunk_id, score=c.score) for c in candidates[:n]]
        return ChainResult(items=fallback_items, reranker="none")


__all__ = ["RerankerChain"]
