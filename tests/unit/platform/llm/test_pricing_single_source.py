"""Prices have one source of truth: the model catalog (config/models.yaml). Adapters must not carry
their own price tables (AGENTS.md section 2: no hard-coded models or prices)."""

from __future__ import annotations

import re

import pytest
from support.defects import defect
from support.repo import REPO_ROOT

pytestmark = pytest.mark.unit

ADAPTERS = REPO_ROOT / "src" / "ragassist" / "platform" / "llm" / "adapters"
PRICE_LITERAL = re.compile(r"(input|output)_cost_per_mtok\s*=\s*\d")


class TestSingleSourceOfPrices:
    @defect("DEFECT-17")
    def test_adapters_contain_no_literal_prices(self) -> None:
        offenders = [
            path.name
            for path in sorted(ADAPTERS.glob("*.py"))
            if PRICE_LITERAL.search(path.read_text(encoding="utf-8"))
        ]
        assert not offenders, (
            f"price literals found in adapters (move them to config/models.yaml): {offenders}"
        )

    def test_the_catalog_file_exists_as_the_price_source(self) -> None:
        assert (REPO_ROOT / "config" / "models.yaml").is_file()
