"""E2E Test Runner script for RagAssist.

Supports running tests directly via Python while setting up
necessary import paths and environment stubs.
"""

import sys
from pathlib import Path

import pytest

# Ensure src/ and repo root are in python search path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Greenlet stub if binary wheel is not present in environment
if "greenlet" not in sys.modules:
    try:
        import greenlet  # type: ignore # noqa: F401
    except ImportError:
        import types

        greenlet_stub = types.ModuleType("greenlet")

        class Greenlet:
            def __init__(self, *args: object, **kwargs: object) -> None:
                self.dead = False
                self.gr_context = None

        greenlet_stub.greenlet = Greenlet  # type: ignore[attr-defined]
        greenlet_stub.getcurrent = lambda: Greenlet()  # type: ignore[attr-defined]
        greenlet_stub.GreenletExit = Exception  # type: ignore[attr-defined]
        sys.modules["greenlet"] = greenlet_stub


def main() -> int:
    args = sys.argv[1:] or ["tests/e2e", "-v"]
    return pytest.main(args)


if __name__ == "__main__":
    sys.exit(main())
