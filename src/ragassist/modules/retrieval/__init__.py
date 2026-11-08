"""Retrieval module public exports."""

from ragassist.modules.retrieval.application import ContextBuilder, HybridRetriever
from ragassist.modules.retrieval.domain import Citation, ContextPack, Hit, Passage, reciprocal_rank_fusion
from ragassist.modules.retrieval.fusion import fuse_hit_rankings
from ragassist.modules.retrieval.hybrid_service import HybridRetrievalResult, HybridRetrievalService
from ragassist.modules.retrieval.keyword_retriever import KeywordRetriever
from ragassist.modules.retrieval.vector_retriever import VectorRetriever

__all__ = [
    "Citation",
    "ContextBuilder",
    "ContextPack",
    "Hit",
    "HybridRetrievalResult",
    "HybridRetrievalService",
    "HybridRetriever",
    "KeywordRetriever",
    "Passage",
    "VectorRetriever",
    "fuse_hit_rankings",
    "reciprocal_rank_fusion",
]
