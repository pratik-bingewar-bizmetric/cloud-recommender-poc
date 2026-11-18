"""Cooldown and concurrency protection for refreshes of shared state.

Used for operations that any authenticated user may trigger but that mutate shared state or call
upstream services (e.g. the pricing cache refresh). State is per process; with more than one
API replica use a shared store (planned with the persistent connection layer).
"""

import math
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import structlog
from fastapi import HTTPException, status

logger = structlog.get_logger(__name__)


class RefreshGuard:
    """Reject a refresh when one is running for the key or the cooldown has not elapsed."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._last_started: dict[str, float] = {}
        self._in_flight: set[str] = set()

    def acquire(self, key: str, cooldown_seconds: int) -> None:
        """Start a refresh for ``key`` or raise 409 (in progress) / 429 (cooldown).

        The check and the state change contain no ``await``, so on the asyncio event loop they are
        atomic: two concurrent requests cannot both pass.
        """
        if key in self._in_flight:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "REFRESH_IN_PROGRESS",
                    "message": "A refresh for this scope is already running.",
                },
            )
        now = self._clock()
        last = self._last_started.get(key)
        if cooldown_seconds > 0 and last is not None and now - last < cooldown_seconds:
            retry_after = max(1, math.ceil(cooldown_seconds - (now - last)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error_code": "REFRESH_COOLDOWN",
                    "message": f"This scope was refreshed recently; retry in {retry_after} seconds.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        self._in_flight.add(key)
        self._last_started[key] = now

    def release(self, key: str) -> None:
        self._in_flight.discard(key)

    @contextmanager
    def guard(self, key: str, cooldown_seconds: int) -> Iterator[None]:
        self.acquire(key, cooldown_seconds)
        try:
            yield
        finally:
            self.release(key)


pricing_refresh_guard = RefreshGuard()


def get_pricing_refresh_guard() -> RefreshGuard:
    """FastAPI dependency returning the process-wide pricing refresh guard."""
    return pricing_refresh_guard
