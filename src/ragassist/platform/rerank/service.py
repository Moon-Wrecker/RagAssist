"""Reranker service and chain construction."""

from collections.abc import Mapping
import structlog
from ragassist.platform.rerank.adapters.noop_adapter import NoopReranker
from ragassist.platform.rerank.adapters.reranker_chain import RerankerChain
from ragassist.platform.rerank.ports import Reranker
from ragassist.shared.config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)


def build_reranker_chain(
    settings: Settings | None = None,
    instances: Mapping[str, Reranker] | None = None,
) -> RerankerChain:
    """Build a configured RerankerChain with fallbacks based on settings and optional injected instances."""
    if settings is None:
        settings = get_settings()

    chain_names = [
        name.strip().lower()
        for name in settings.RERANKER_CHAIN.split(",")
        if name.strip()
    ]

    normalized_instances: dict[str, Reranker] = {}
    if instances is not None:
        normalized_instances = {
            k.strip().lower(): v for k, v in instances.items()
        }

    members: list[Reranker] = []

    for name in chain_names:
        if name in normalized_instances:
            members.append(normalized_instances[name])
            continue

        if name == "none":
            members.append(NoopReranker())
        elif name == "cross_encoder":
            try:
                from ragassist.platform.rerank.adapters.cross_encoder_adapter import CrossEncoderReranker
                members.append(
                    CrossEncoderReranker(
                        model_name=getattr(settings, "RERANK_CROSS_ENCODER_MODEL", "BAAI/bge-reranker-v2-m3"),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("reranker.cross_encoder_unavailable", error=str(exc))
        elif name == "flashrank":
            try:
                from ragassist.platform.rerank.adapters.flashrank_adapter import FlashRankReranker
                members.append(
                    FlashRankReranker(
                        model_name=getattr(settings, "RERANK_FLASHRANK_MODEL", "ms-marco-TinyBERT-L-2-v2"),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("reranker.flashrank_unavailable", error=str(exc))
        elif name == "api":
            try:
                from ragassist.platform.rerank.adapters.api_reranker_adapter import ApiReranker
                members.append(
                    ApiReranker(
                        base_url=getattr(settings, "RERANK_API_BASE_URL", "https://api.cohere.com/v1"),
                        api_key=getattr(settings, "RERANK_API_KEY", ""),
                        model=getattr(settings, "RERANK_API_MODEL", "rerank-english-v3.0"),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("reranker.api_unavailable", error=str(exc))
        else:
            logger.warning("reranker.unknown_name_skipped", name=name)

    # Always guarantee at least a NoopReranker if all member instantiation failed
    if not members:
        members.append(NoopReranker())

    return RerankerChain(
        members=members,
        timeout_ms=getattr(settings, "RERANK_TIMEOUT_MS", 1500),
        enabled=getattr(settings, "RERANK_ENABLED", True),
        default_top_n=getattr(settings, "RETRIEVAL_TOP_N", 6),
    )


__all__ = ["build_reranker_chain"]
