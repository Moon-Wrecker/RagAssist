"""Token usage of one streamed generation, with the share the provider served from its prompt cache (ADR 0015).

Providers cache the *prefix* of a prompt: OpenAI and Gemini do it implicitly (no request flag), Anthropic only for
blocks marked ``cache_control``. They report how much of the input was a cache read in ``usage_metadata``
(``input_token_details.cache_read`` in LangChain's normalised form). This tally adds that up over the chunks of a
stream, counts it on ``/metrics`` and logs it, so the saving is visible. Langfuse shows the same numbers from the
callback handler, which reads ``usage_metadata`` as well.

Usage is only present when the provider streams it (native OpenAI and Anthropic do; an OpenAI-compatible endpoint may
not). Absent usage records nothing rather than a zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from ragassist.shared.observability.metrics import get_metrics_registry

logger = structlog.get_logger(__name__)

_registry = get_metrics_registry()
_registry.register(
    "ragassist_llm_input_tokens_total",
    "counter",
    "Input tokens sent to chat models, split by whether the provider served them from its prompt cache",
)


@dataclass
class UsageTally:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    seen: bool = False

    def add(self, chunk: Any) -> None:
        usage = getattr(chunk, "usage_metadata", None)
        if not isinstance(usage, dict):
            return
        self.seen = True
        self.input_tokens += int(usage.get("input_tokens", 0) or 0)
        details = usage.get("input_token_details") or {}
        if isinstance(details, dict):
            self.cached_input_tokens += int(details.get("cache_read", 0) or 0)

    def record(self, model: str) -> None:
        if not self.seen:
            return
        cached = min(self.cached_input_tokens, self.input_tokens)
        _registry.increment_counter("ragassist_llm_input_tokens_total", float(cached), cached="true")
        _registry.increment_counter(
            "ragassist_llm_input_tokens_total", float(self.input_tokens - cached), cached="false"
        )
        logger.info(
            "llm.usage", model=model, input_tokens=self.input_tokens, cached_input_tokens=cached
        )
