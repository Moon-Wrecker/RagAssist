"""Re-export for spec mapping."""

import sentence_transformers  # noqa: F401 - ensures need() detects missing optional dependency
from ragassist.platform.rerank.adapters.cross_encoder_adapter import CrossEncoderReranker

__all__ = ["CrossEncoderReranker"]
