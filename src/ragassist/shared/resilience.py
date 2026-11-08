"""Resilience utilities: FallbackChain, retry policies, and bounded thread execution."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Generic, TypeVar
import structlog

T = TypeVar("T")
R = TypeVar("R")

logger = structlog.get_logger(__name__)

# Bounded global thread pool executor for CPU-bound tasks
# (Tokenization, parsing, onnx inference) to prevent starving the async event loop.
_BOUNDED_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ragassist-cpu")


async def run_cpu_bound(func: Callable[..., R], *args: Any, **kwargs: Any) -> R:
    """Run a CPU-bound function in the bounded thread pool executor."""
    loop = asyncio.get_running_loop()
    if kwargs:
        # functools.partial avoids closure issues
        from functools import partial
        call = partial(func, *args, **kwargs)
        return await loop.run_in_executor(_BOUNDED_EXECUTOR, call)
    return await loop.run_in_executor(_BOUNDED_EXECUTOR, func, *args)


class FallbackChain(Generic[T]):
    """Orchestrates an ordered list of providers with automatic fallback on failure."""

    def __init__(self, name: str, members: Sequence[T]) -> None:
        if not members:
            raise ValueError(f"FallbackChain '{name}' must have at least one member.")
        self.name = name
        self.members = list(members)

    async def execute(
        self,
        operation: Callable[[T], Awaitable[R]],
        is_acceptable: Callable[[R], bool] | None = None,
    ) -> tuple[R, T]:
        """Execute operation across members in order until one succeeds and passes acceptance."""
        last_error: Exception | None = None

        for idx, member in enumerate(self.members):
            member_name = getattr(member, "name", f"{type(member).__name__}#{idx}")
            try:
                result = await operation(member)
                if is_acceptable is not None and not is_acceptable(result):
                    logger.warning(
                        "fallback_chain.unacceptable_result",
                        chain=self.name,
                        member=member_name,
                        index=idx,
                    )
                    continue
                return result, member
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "fallback_chain.member_failed",
                    chain=self.name,
                    member=member_name,
                    index=idx,
                    error=str(exc),
                )

        raise RuntimeError(
            f"All {len(self.members)} members of FallbackChain '{self.name}' failed. "
            f"Last error: {last_error}"
        ) from last_error

