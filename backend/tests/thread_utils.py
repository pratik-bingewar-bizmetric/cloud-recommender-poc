"""Bounded helpers for concurrency tests.

A test that starts N threads must never be able to block the suite forever: an unbounded
``threading.Barrier.wait()`` or ``Thread.join()`` turns one missing thread (a failed ``start``, a
worker that died before the barrier) into a CI run that hangs until the job is killed.
"""

import threading
from collections.abc import Callable

# Generous on purpose: these are ceilings for a stuck run, not expected durations (the work
# itself takes milliseconds), so a slow or heavily loaded runner does not make the test flaky.
DEFAULT_BARRIER_TIMEOUT_SECONDS = 30.0
DEFAULT_JOIN_TIMEOUT_SECONDS = 60.0


def run_concurrently[T](
    count: int,
    work: Callable[[], T],
    *,
    barrier_timeout: float = DEFAULT_BARRIER_TIMEOUT_SECONDS,
    join_timeout: float = DEFAULT_JOIN_TIMEOUT_SECONDS,
) -> list[T]:
    """Run ``work`` in ``count`` threads that are released together; return their results.

    All threads are daemon threads, wait on a barrier with a timeout, and are joined with a
    bounded timeout. Any worker exception, a broken barrier or a thread that is still alive
    raises ``AssertionError`` with an explicit message instead of hanging.
    """
    barrier = threading.Barrier(count)
    results: list[T] = []
    failures: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait(timeout=barrier_timeout)
        except threading.BrokenBarrierError as exc:
            with lock:
                failures.append(exc)
            return
        try:
            outcome = work()
        except BaseException as exc:  # reported to the caller, never swallowed
            with lock:
                failures.append(exc)
            return
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(count)]
    started = 0
    try:
        for thread in threads:
            thread.start()
            started += 1
    finally:
        if started < count:
            barrier.abort()  # release already-started workers instead of leaving them blocked

    for thread in threads[:started]:
        thread.join(timeout=join_timeout)
    stuck = [t.name for t in threads[:started] if t.is_alive()]

    if started < count:
        raise AssertionError(f"Only {started} of {count} threads could be started.")
    if stuck:
        barrier.abort()
        raise AssertionError(f"{len(stuck)} worker thread(s) still running after {join_timeout}s.")
    broken = [f for f in failures if isinstance(f, threading.BrokenBarrierError)]
    if broken:
        raise AssertionError(
            f"Barrier broken or timed out after {barrier_timeout}s: not all {count} workers "
            "reached the start line, so the contention was not exercised."
        )
    if failures:
        raise AssertionError(f"{len(failures)} worker(s) raised: {failures[0]!r}") from failures[0]
    return results
