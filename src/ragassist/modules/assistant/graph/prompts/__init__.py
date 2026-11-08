"""Versioned prompt directory export."""

from pathlib import Path

PROMPTS_DIR: Path = Path(__file__).parent

__all__ = ["PROMPTS_DIR"]
