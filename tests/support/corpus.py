"""Loads the injection corpus (tests/data/injection/*.yaml) into typed cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from support.repo import TESTS_ROOT

CORPUS_DIR: Path = TESTS_ROOT / "data" / "injection"


@dataclass(frozen=True)
class Case:
    case_id: str
    category: str
    text: str
    label: str  # "attack" | "benign" | "borderline"

    @property
    def is_attack(self) -> bool:
        return self.label == "attack"


def load_categories() -> dict[str, list[Case]]:
    categories: dict[str, list[Case]] = {}
    for path in sorted(CORPUS_DIR.glob("*.yaml")):
        if path.name == "floors.yaml":
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        category = data["category"]
        categories[category] = [
            Case(item["id"], category, item["text"], item["label"]) for item in data["cases"]
        ]
    return categories


def load_floors() -> dict[str, float]:
    data = yaml.safe_load((CORPUS_DIR / "floors.yaml").read_text(encoding="utf-8"))
    return {key: float(value) for key, value in data["rules_floor"].items()}


def all_cases() -> list[Case]:
    return [case for cases in load_categories().values() for case in cases]
