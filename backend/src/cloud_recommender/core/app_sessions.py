"""Application session storage for Service Principal-Only authentication.

Generates high-entropy session tokens, stores only their SHA-256 hashes in memory,
and manages session lifecycle, TTL expiration, and revocation.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

DEFAULT_SESSION_TTL_SECONDS = 28800  # 8 hours


class AppSession(BaseModel):
    """Active application session representation."""

    session_id: str = Field(description="Unique session identifier (sess-...)")
    token_hash: str = Field(description="SHA-256 hash of the bearer session token")
    account_id: str = Field(description="Internal account identifier (acc-...)")
    account_name: str = Field(description="User-friendly name of the cloud account")
    tenant_id: str = Field(description="Microsoft Entra tenant GUID")
    subscription_id: str = Field(description="Azure subscription GUID")
    subscription_name: str = Field(description="Azure subscription display name")
    client_id: str = Field(description="Azure application / client GUID")
    connection_id: str = Field(description="Live Azure connection identifier (conn-...)")
    roles: list[str] = Field(
        default_factory=lambda: ["FinOpsAdmin"],
        description="Assigned platform application roles",
    )
    permissions: dict[str, bool] = Field(
        default_factory=lambda: {
            "reader": True,
            "cost_management_reader": True,
            "monitoring_reader": True,
        },
        description="Verified Azure RBAC permissions",
    )
    created_at: datetime = Field(description="Session creation timestamp (UTC)")
    expires_at: datetime = Field(description="Session expiration timestamp (UTC)")
    last_used_at: datetime = Field(description="Timestamp of last authenticated API call (UTC)")
    revoked_at: datetime | None = Field(
        default=None, description="Timestamp of explicit revocation (UTC) or None"
    )

    @property
    def is_active(self) -> bool:
        """True if session is neither expired nor revoked."""
        now = datetime.now(UTC)
        return self.revoked_at is None and now < self.expires_at


class AppSessionStore:
    """Thread-safe, in-memory registry of active application sessions.

    Stores only SHA-256 hashes of session tokens to protect against memory disclosure.
    """

    def __init__(
        self,
        default_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._sessions_by_hash: dict[str, AppSession] = {}
        self._sessions_by_id: dict[str, AppSession] = {}

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Compute deterministic SHA-256 digest of session token."""
        return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()

    def _purge_expired_locked(self) -> None:
        """Internal helper to purge expired sessions while holding the lock."""
        now = self._clock()
        expired_hashes = [h for h, s in self._sessions_by_hash.items() if s.expires_at <= now]
        for h in expired_hashes:
            sess = self._sessions_by_hash.pop(h, None)
            if sess:
                self._sessions_by_id.pop(sess.session_id, None)

    def create_session(
        self,
        *,
        account_name: str,
        tenant_id: str,
        subscription_id: str,
        subscription_name: str,
        client_id: str,
        connection_id: str,
        account_id: str | None = None,
        roles: list[str] | None = None,
        permissions: dict[str, bool] | None = None,
        ttl_seconds: int | None = None,
    ) -> tuple[str, AppSession]:
        """Create a new session, storing only the token hash and returning (raw_token, session)."""
        raw_token = f"finops_sess_{secrets.token_urlsafe(32)}"
        token_hash = self.hash_token(raw_token)
        session_id = f"sess-{secrets.token_hex(8)}"
        resolved_account_id = account_id or f"acc-{secrets.token_hex(6)}"

        now = self._clock()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = now + timedelta(seconds=ttl)

        session = AppSession(
            session_id=session_id,
            token_hash=token_hash,
            account_id=resolved_account_id,
            account_name=account_name,
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            subscription_name=subscription_name,
            client_id=client_id,
            connection_id=connection_id,
            roles=roles or ["FinOpsAdmin"],
            permissions=permissions
            or {
                "reader": True,
                "cost_management_reader": True,
                "monitoring_reader": True,
            },
            created_at=now,
            expires_at=expires_at,
            last_used_at=now,
            revoked_at=None,
        )

        with self._lock:
            self._purge_expired_locked()
            self._sessions_by_hash[token_hash] = session
            self._sessions_by_id[session_id] = session

        return raw_token, session

    def get_session_by_token(self, raw_token: str) -> AppSession | None:
        """Resolve an active session by raw bearer token, verifying hash and active status."""
        token_hash = self.hash_token(raw_token)
        now = self._clock()

        with self._lock:
            session = self._sessions_by_hash.get(token_hash)
            if session is None:
                return None

            # Verify session is neither expired nor revoked
            if session.revoked_at is not None or now >= session.expires_at:
                return None

            # Update last_used_at
            session.last_used_at = now
            return session

    def get_session_by_hash(self, token_hash: str) -> AppSession | None:
        """Resolve a session by token hash without active check (used for diagnostic error codes)."""
        with self._lock:
            return self._sessions_by_hash.get(token_hash)

    def get_session_by_id(self, session_id: str) -> AppSession | None:
        """Retrieve a session by session ID."""
        with self._lock:
            return self._sessions_by_id.get(session_id)

    def revoke_session(self, session_id: str) -> bool:
        """Explicitly revoke an active session by session ID."""
        now = self._clock()
        with self._lock:
            session = self._sessions_by_id.get(session_id)
            if session and session.revoked_at is None:
                session.revoked_at = now
                return True
            return False

    def revoke_by_token(self, raw_token: str) -> bool:
        """Explicitly revoke an active session by raw bearer token."""
        token_hash = self.hash_token(raw_token)
        now = self._clock()
        with self._lock:
            session = self._sessions_by_hash.get(token_hash)
            if session and session.revoked_at is None:
                session.revoked_at = now
                return True
            return False

    def list_active_sessions(self) -> list[AppSession]:
        """Return all unexpired, unrevoked active sessions."""
        now = self._clock()
        with self._lock:
            self._purge_expired_locked()
            return [
                s
                for s in self._sessions_by_id.values()
                if s.revoked_at is None and s.expires_at > now
            ]

    def clear(self) -> None:
        """Clear all sessions (testing utility)."""
        with self._lock:
            self._sessions_by_hash.clear()
            self._sessions_by_id.clear()


# Global in-memory instance
app_session_store = AppSessionStore()


def get_app_session_store() -> AppSessionStore:
    """Dependency provider for the application session store."""
    return app_session_store
