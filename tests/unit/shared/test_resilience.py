"""Resilience (features 6 and 7): FallbackChain and the bounded CPU executor."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import pytest

from ragassist.shared.resilience import FallbackChain, run_cpu_bound


@dataclass
class Member:
    name: str
    behaviour: object = "ok"  # str result, or an Exception instance to raise
    calls: list[str] = field(default_factory=list)

    async def run(self) -> object:
        self.calls.append(self.name)
        if isinstance(self.behaviour, BaseException):
            raise self.behaviour
        return self.behaviour


def op(member: Member) -> Awaitable[object]:
    return member.run()


class TestFallbackChainSelection:
    async def test_first_healthy_member_wins_and_later_ones_are_not_called(self) -> None:
        a, b = Member("a", "A"), Member("b", "B")
        result, used = await FallbackChain("t", [a, b]).execute(op)
        assert (result, used) == ("A", a)
        assert b.calls == []

    async def test_fails_over_in_declared_order(self) -> None:
        members = [
            Member("a", RuntimeError("a down")),
            Member("b", TimeoutError("b slow")),
            Member("c", "C"),
            Member("d", "D"),
        ]
        result, used = await FallbackChain("t", members).execute(op)
        assert result == "C" and used is members[2]
        assert [bool(m.calls) for m in members] == [True, True, True, False]

    async def test_members_are_tried_sequentially_not_concurrently(self) -> None:
        order: list[str] = []

        async def tracked(member: Member) -> str:
            order.append(f"start-{member.name}")
            await asyncio.sleep(0)
            order.append(f"end-{member.name}")
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await FallbackChain("t", [Member("a"), Member("b")]).execute(tracked)  # type: ignore[arg-type]
        assert order == ["start-a", "end-a", "start-b", "end-b"]

    async def test_acceptance_predicate_skips_unacceptable_results(self) -> None:
        a, b = Member("a", "low-confidence"), Member("b", "good")
        result, used = await FallbackChain("t", [a, b]).execute(
            op, is_acceptable=lambda r: r != "low-confidence"
        )
        assert (result, used) == ("good", b)
        assert a.calls == ["a"]  # a was called, its answer rejected

    async def test_returns_the_member_object_so_callers_can_record_who_answered(self) -> None:
        a = Member("primary", "x")
        _, used = await FallbackChain("t", [a]).execute(op)
        assert used.name == "primary"

    async def test_works_with_a_single_member(self) -> None:
        result, _ = await FallbackChain("t", [Member("only", 1)]).execute(op)
        assert result == 1

    async def test_falsy_results_are_valid_when_no_predicate_is_given(self) -> None:
        for value in (0, "", [], None, False):
            result, used = await FallbackChain("t", [Member("a", value), Member("b", "B")]).execute(
                op
            )
            assert result == value and used.name == "a"


class TestFallbackChainFailure:
    async def test_all_members_failing_raises_with_chain_name_and_cause(self) -> None:
        last = RuntimeError("b exploded")
        chain = FallbackChain("answers", [Member("a", ValueError("a")), Member("b", last)])
        with pytest.raises(RuntimeError, match="answers") as excinfo:
            await chain.execute(op)
        assert excinfo.value.__cause__ is last
        assert "b exploded" in str(excinfo.value)

    async def test_all_results_unacceptable_raises(self) -> None:
        chain = FallbackChain("t", [Member("a", "bad"), Member("b", "bad")])
        with pytest.raises(RuntimeError, match="failed"):
            await chain.execute(op, is_acceptable=lambda r: False)

    def test_empty_chain_is_rejected_at_construction(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            FallbackChain("t", [])

    async def test_cancellation_is_never_swallowed(self) -> None:
        chain = FallbackChain("t", [Member("a", asyncio.CancelledError()), Member("b", "B")])
        with pytest.raises(asyncio.CancelledError):
            await chain.execute(op)

    async def test_keyboard_interrupt_is_never_swallowed(self) -> None:
        chain = FallbackChain("t", [Member("a", KeyboardInterrupt()), Member("b", "B")])
        with pytest.raises(KeyboardInterrupt):
            await chain.execute(op)

    async def test_error_in_acceptance_predicate_moves_to_next_member(self) -> None:
        def flaky(result: object) -> bool:
            if result == "a-result":
                raise ValueError("predicate bug")
            return True

        chain = FallbackChain("t", [Member("a", "a-result"), Member("b", "b-result")])
        result, _ = await chain.execute(op, is_acceptable=flaky)
        assert result == "b-result"


class TestFallbackChainConstruction:
    def test_members_are_copied(self) -> None:
        members = [Member("a")]
        chain = FallbackChain("t", members)
        members.append(Member("b"))
        assert len(chain.members) == 1

    def test_exposes_name_and_members(self) -> None:
        a = Member("a")
        chain = FallbackChain("llm", [a])
        assert chain.name == "llm" and chain.members == [a]

    async def test_members_without_a_name_attribute_are_supported(self) -> None:
        async def op_int(member: int) -> int:
            if member < 2:
                raise ValueError
            return member

        result, used = await FallbackChain("t", [0, 1, 2]).execute(op_int)
        assert (result, used) == (2, 2)


class TestRunCpuBound:
    async def test_returns_the_result_with_positional_and_keyword_arguments(self) -> None:
        assert await run_cpu_bound(pow, 2, 10) == 1024
        assert await run_cpu_bound(lambda base, *, exp: base**exp, 3, exp=3) == 27

    async def test_exceptions_propagate_to_the_caller(self) -> None:
        def boom() -> None:
            raise ZeroDivisionError("cpu job failed")

        with pytest.raises(ZeroDivisionError, match="cpu job failed"):
            await run_cpu_bound(boom)

    async def test_runs_off_the_event_loop_thread_in_the_named_pool(self) -> None:
        loop_thread = threading.get_ident()
        worker_thread, worker_name = await run_cpu_bound(
            lambda: (threading.get_ident(), threading.current_thread().name)
        )
        assert worker_thread != loop_thread
        assert worker_name.startswith("ragassist-cpu")

    async def test_event_loop_stays_responsive_during_cpu_work(self) -> None:
        """If the work ran inline the heartbeat would not tick at all."""
        ticks = 0
        stop = asyncio.Event()

        async def heartbeat() -> None:
            nonlocal ticks
            while not stop.is_set():
                ticks += 1
                await asyncio.sleep(0.005)

        beat = asyncio.create_task(heartbeat())
        await run_cpu_bound(time.sleep, 0.25)
        stop.set()
        await beat
        assert ticks >= 10

    async def test_concurrency_is_bounded_but_parallel(self) -> None:
        lock = threading.Lock()
        running = peak = 0

        def job() -> None:
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.03)
            with lock:
                running -= 1

        await asyncio.gather(*(run_cpu_bound(job) for _ in range(32)))
        assert 2 <= peak < 32  # parallel, yet never one thread per task

    async def test_many_concurrent_callers_get_their_own_results(self) -> None:
        results = await asyncio.gather(*(run_cpu_bound(lambda n=n: n * n) for n in range(50)))
        assert results == [n * n for n in range(50)]


Operation = Callable[[Member], Awaitable[object]]
