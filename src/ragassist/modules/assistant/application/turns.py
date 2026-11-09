"""Detached execution of an assistant turn, so a client that goes away cannot interrupt it.

Goal: when the browser aborts the request (the Stop button, a closed tab, a dropped network) the turn must still finish:
the answer is saved, the helpdesk ticket is opened when the turn escalated, and the change is announced. The HTTP
handler therefore never runs the graph itself; it starts a task here and, at most, waits for it.

Why a task and not only ``asyncio.shield``: shielding protects an inner await from the *outer* cancellation, but a
streaming response is cancelled by Starlette at an arbitrary ``yield`` of the generator, which would abandon the code
after it. A task owned by this module is not a child of the request, so cancelling the request cannot reach it. The
set of running tasks keeps a strong reference (the event loop only holds weak ones) and lets shutdown wait for them.

Consulted: Python ``asyncio`` docs (``create_task`` keeps only a weak reference; ``shield``), Starlette
``StreamingResponse`` (a client disconnect cancels the response task).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_running: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any], *, name: str = "assistant-turn") -> asyncio.Task[Any]:
    """Run ``coro`` as a task that outlives the request that started it."""
    task = asyncio.create_task(coro, name=name)
    _running.add(task)
    task.add_done_callback(_finished)
    return task


def _finished(task: asyncio.Task[Any]) -> None:
    _running.discard(task)
    if not task.cancelled() and task.exception() is not None:
        # Nobody may be awaiting it any more (the client left); make sure the failure is not silent.
        logger.error("assistant.turn_failed", error=str(task.exception()))


def running_turns() -> int:
    return len(_running)


async def drain(timeout: float = 30.0) -> None:
    """Wait for in-flight turns (shutdown); anything still running after ``timeout`` seconds is cancelled."""
    pending = {t for t in _running if not t.done()}
    if not pending:
        return
    _, still = await asyncio.wait(pending, timeout=timeout)
    for task in still:
        task.cancel()
    if still:
        await asyncio.gather(*still, return_exceptions=True)
