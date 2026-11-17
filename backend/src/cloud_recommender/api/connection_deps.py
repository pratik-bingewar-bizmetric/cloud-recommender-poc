"""Shared FastAPI dependencies for connection management and live Azure data routes."""

import hashlib
from collections.abc import AsyncGenerator, Callable
from typing import Annotated

import httpx
from fastapi import Depends

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.core.secret_vault import CredentialCipher, build_cipher
from cloud_recommender.db.repositories.connection_repo import (
    ConnectionRepository,
    SqlConnectionRepository,
    in_memory_connection_repository,
)
from cloud_recommender.db.session import get_session_factory
from cloud_recommender.services.azure_live.session_store import (
    AzureSessionStore,
    azure_session_store,
)
from cloud_recommender.services.connections.connection_manager import ConnectionManager

_cipher_cache: dict[tuple[str, ...], CredentialCipher] = {}


def reset_cipher_cache() -> None:
    _cipher_cache.clear()


def cipher_factory(settings: Settings) -> Callable[[], CredentialCipher]:
    """Builds (and caches) the cipher lazily, so an unconfigured key only fails when needed."""

    def factory() -> CredentialCipher:
        keys = settings.connection_encryption_keys
        fingerprint = hashlib.sha256((keys.get_secret_value() if keys else "").encode()).hexdigest()
        cache_key = (
            settings.connection_key_provider,
            settings.connection_active_key_id or "",
            settings.key_vault_url or "",
            settings.connection_key_secret_name or "",
            fingerprint,
        )
        if cache_key not in _cipher_cache:
            _cipher_cache[cache_key] = build_cipher(settings)
        return _cipher_cache[cache_key]

    return factory


def get_azure_http_transport() -> httpx.AsyncBaseTransport | None:
    """Transport override point (tests inject a mock; production uses the default)."""
    return None


def get_session_store(settings: Settings = Depends(get_settings)) -> AzureSessionStore:
    azure_session_store.configure(
        settings.azure_live_session_ttl_seconds, settings.azure_live_max_connections_per_user
    )
    return azure_session_store


async def get_connection_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncGenerator[ConnectionRepository, None]:
    """PostgreSQL repository (persistent) or, in development/testing only, the in-memory one."""
    if settings.connection_store == "memory":
        yield in_memory_connection_repository
        return
    async with get_session_factory()() as session:
        yield SqlConnectionRepository(session)


def get_connection_manager(
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[ConnectionRepository, Depends(get_connection_repository)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
    sessions: Annotated[AzureSessionStore, Depends(get_session_store)],
) -> ConnectionManager:
    return ConnectionManager(repo, cipher_factory(settings), settings, transport, sessions)
