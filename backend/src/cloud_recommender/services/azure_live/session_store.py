"""In-memory, owner-bound store of active Azure connection sessions (demo scope).

Only the short-lived access token is held, in process memory, never the client secret. A session
is visible only to the signed-in user that created it (``owner_key`` derived from the validated
application token); any other caller gets "not found". State is lost on restart and is not shared
between instances, so the demo must run as a single instance.
"""

import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import HTTPException, status

from cloud_recommender.services.azure_live.credentials import AzureToken

MAX_SESSIONS_TOTAL = 500


@dataclass
class AzureSession:
    connection_id: str
    owner_key: str
    tenant_id: str
    client_id: str
    token: AzureToken = field(repr=False)
    created_at: float
    expires_at: float


def not_found() -> HTTPException:
    """Identical response for unknown, expired and foreign sessions (no enumeration)."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error_code": "AZURE_CONNECTION_NOT_FOUND",
            "message": "The Azure connection was not found or has expired. Connect again.",
        },
    )


class AzureSessionStore:
    """Process-local session registry with TTL and per-owner limits."""

    def __init__(
        self,
        ttl_seconds: int = 3300,
        max_per_owner: int = 10,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_per_owner = max_per_owner
        self._clock = clock
        self._sessions: dict[str, AzureSession] = {}

    def configure(self, ttl_seconds: int, max_per_owner: int) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_per_owner = max_per_owner

    def _purge(self) -> None:
        now = self._clock()
        for key in [k for k, s in self._sessions.items() if s.expires_at <= now]:
            del self._sessions[key]

    def create(
        self, owner_key: str, tenant_id: str, client_id: str, token: AzureToken
    ) -> AzureSession:
        self._purge()
        owned = [s for s in self._sessions.values() if s.owner_key == owner_key]
        if len(owned) >= self.max_per_owner or len(self._sessions) >= MAX_SESSIONS_TOTAL:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "CONNECTION_LIMIT_REACHED",
                    "message": "Maximum number of active Azure connections reached. Disconnect one first.",
                },
            )
        now = self._clock()
        session = AzureSession(
            connection_id=secrets.token_urlsafe(24),
            owner_key=owner_key,
            tenant_id=tenant_id,
            client_id=client_id,
            token=token,
            created_at=now,
            expires_at=min(token.expires_at - 60, now + self.ttl_seconds),
        )
        self._sessions[session.connection_id] = session
        return session

    def get(self, connection_id: str, owner_key: str) -> AzureSession:
        self._purge()
        session = self._sessions.get(connection_id)
        if session is None or not secrets.compare_digest(session.owner_key, owner_key):
            raise not_found()
        return session

    def delete(self, connection_id: str, owner_key: str) -> None:
        self.get(connection_id, owner_key)
        del self._sessions[connection_id]

    def clear(self) -> None:
        self._sessions.clear()


class SlidingWindowLimiter:
    """Per-key attempt limiter (credential-testing endpoints are an oracle otherwise)."""

    def __init__(
        self, limit: int = 5, window_seconds: int = 60, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def configure(self, limit: int) -> None:
        self.limit = limit

    def check(self, key: str) -> None:
        now = self._clock()
        events = self._events[key]
        while events and now - events[0] >= self.window_seconds:
            events.popleft()
        if len(events) >= self.limit:
            retry_after = max(1, int(self.window_seconds - (now - events[0])) + 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error_code": "TOO_MANY_ATTEMPTS",
                    "message": f"Too many connection attempts. Retry in {retry_after} seconds.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        events.append(now)


azure_session_store = AzureSessionStore()
connect_attempt_limiter = SlidingWindowLimiter()
