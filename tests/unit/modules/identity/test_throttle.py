"""The sign-in throttle: per-account failures, per-address attempts, a sliding window, bounded memory."""

from __future__ import annotations

import pytest

from ragassist.modules.identity.application import LoginThrottle
from ragassist.modules.identity.domain import RateLimitedError


class Ticker:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(
    ticker: Ticker, *, failures: int = 3, per_ip: int = 10, window: int = 60, keys: int = 1000
) -> LoginThrottle:
    return LoginThrottle(
        max_failures=failures, max_per_ip=per_ip, window_seconds=window, clock=ticker, max_keys=keys
    )


def test_failures_lock_one_account_after_the_limit() -> None:
    ticker = Ticker()
    throttle = make(ticker, failures=3)
    for _ in range(3):
        throttle.check("1.1.1.1", "acme", "a@x.com")
        throttle.record_failure("acme", "a@x.com")
    with pytest.raises(RateLimitedError):
        throttle.check("1.1.1.1", "acme", "a@x.com")


def test_the_lock_follows_the_account_not_the_address() -> None:
    ticker = Ticker()
    throttle = make(ticker, failures=2)
    for ip in ("1.1.1.1", "2.2.2.2"):
        throttle.check(ip, "acme", "a@x.com")
        throttle.record_failure("acme", "a@x.com")
    with pytest.raises(RateLimitedError):
        throttle.check("3.3.3.3", "acme", "a@x.com")  # a third address cannot keep guessing


def test_another_account_is_unaffected() -> None:
    ticker = Ticker()
    throttle = make(ticker, failures=1)
    throttle.check("1.1.1.1", "acme", "a@x.com")
    throttle.record_failure("acme", "a@x.com")
    throttle.check("1.1.1.1", "acme", "b@x.com")


def test_account_keys_are_case_insensitive() -> None:
    ticker = Ticker()
    throttle = make(ticker, failures=1)
    throttle.check("1.1.1.1", "Acme", "A@x.com")
    throttle.record_failure("Acme", "A@x.com")
    with pytest.raises(RateLimitedError):
        throttle.check("1.1.1.1", "acme", "a@x.com")


def test_a_success_clears_the_failure_count() -> None:
    ticker = Ticker()
    throttle = make(ticker, failures=2)
    throttle.check("1.1.1.1", "acme", "a@x.com")
    throttle.record_failure("acme", "a@x.com")
    throttle.record_success("acme", "a@x.com")
    throttle.record_failure("acme", "a@x.com")
    throttle.check("1.1.1.1", "acme", "a@x.com")  # one failure since the success: still allowed


def test_one_address_is_limited_across_many_accounts() -> None:
    ticker = Ticker()
    throttle = make(ticker, per_ip=3)
    for i in range(3):
        throttle.check("9.9.9.9", "acme", f"user{i}@x.com")
    with pytest.raises(RateLimitedError):
        throttle.check("9.9.9.9", "acme", "user3@x.com")
    throttle.check("8.8.8.8", "acme", "user3@x.com")  # a different address is fine


def test_the_window_slides() -> None:
    ticker = Ticker()
    throttle = make(ticker, failures=1, window=60)
    throttle.check("1.1.1.1", "acme", "a@x.com")
    throttle.record_failure("acme", "a@x.com")
    with pytest.raises(RateLimitedError):
        throttle.check("1.1.1.1", "acme", "a@x.com")
    ticker.now += 61
    throttle.check("1.1.1.1", "acme", "a@x.com")


def test_retry_after_says_when_to_come_back() -> None:
    ticker = Ticker()
    throttle = make(ticker, failures=1, window=60)
    throttle.check("1.1.1.1", "acme", "a@x.com")
    throttle.record_failure("acme", "a@x.com")
    ticker.now += 20
    with pytest.raises(RateLimitedError) as caught:
        throttle.check("1.1.1.1", "acme", "a@x.com")
    assert 39 <= caught.value.retry_after <= 41


def test_spraying_random_accounts_cannot_grow_memory_without_bound() -> None:
    ticker = Ticker()
    throttle = make(ticker, per_ip=10**9, keys=50)
    for i in range(500):
        throttle.record_failure("acme", f"user{i}@x.com")
        throttle.check(f"10.0.{i // 250}.{i % 250}", "acme", f"user{i}@x.com")
    assert len(throttle._failures) <= 50  # noqa: SLF001
    assert len(throttle._ip) <= 50  # noqa: SLF001
