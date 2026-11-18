"""Self-tests for the bounded concurrency helper (the guarantees the contention tests rely on)."""

import threading
import time

import pytest

from tests.thread_utils import run_concurrently


def test_returns_every_worker_result() -> None:
    assert sorted(run_concurrently(8, lambda: 1)) == [1] * 8


def test_workers_really_start_together() -> None:
    arrived: list[float] = []
    lock = threading.Lock()

    def work() -> int:
        with lock:
            arrived.append(time.monotonic())
        return 0

    run_concurrently(6, work)
    assert max(arrived) - min(arrived) < 5.0


def test_a_worker_exception_is_reported_not_swallowed() -> None:
    def work() -> int:
        raise ValueError("boom")

    with pytest.raises(AssertionError, match="raised.*boom"):
        run_concurrently(3, work)


def test_a_hung_worker_fails_the_test_instead_of_hanging_it() -> None:
    release = threading.Event()
    try:
        started = time.monotonic()
        with pytest.raises(AssertionError, match="still running"):
            run_concurrently(2, lambda: release.wait(30), join_timeout=0.5)
        assert time.monotonic() - started < 10
    finally:
        release.set()


def test_a_broken_barrier_is_a_clear_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    real_barrier = threading.Barrier

    class _ShortBarrier(real_barrier):  # type: ignore[valid-type,misc]
        def __init__(self, parties: int) -> None:
            super().__init__(parties + 1)  # one party can never arrive

    monkeypatch.setattr(threading, "Barrier", _ShortBarrier)
    with pytest.raises(AssertionError, match="Barrier broken or timed out"):
        run_concurrently(3, lambda: 1, barrier_timeout=0.3)
