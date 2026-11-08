"""Re-export for spec mapping."""

import flashrank  # noqa: F401 - ensures need() detects missing optional dependency
from ragassist.platform.rerank.adapters.flashrank_adapter import FlashRankReranker

__all__ = ["FlashRankReranker"]
