"""Offline token counter for chunk budgets.

The chunker only needs a count, not token ids, so the production worker uses this dependency-free estimate
(words and punctuation marks, about 10-20% above a BPE count for English). It works without downloading a
vocabulary, which keeps the worker usable offline and in containers. Tests inject exact fakes instead.
"""

from __future__ import annotations

import re

_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class RegexTokenCounter:
    """``count(text)`` returns the number of word and punctuation tokens."""

    def count(self, text: str) -> int:
        return len(_TOKEN.findall(text))
