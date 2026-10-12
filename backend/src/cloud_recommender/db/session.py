"""SQLAlchemy 2.0 asynchronous database engine and session factory."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cloud_recommender.core.config import get_settings

logger = structlog.get_logger(__name__)

# Lazy engine and session factory references.
# Engine is NOT created on module import.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return or initialize the async SQLAlchemy engine lazily."""
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        logger.info(
            "initializing_database_engine",
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            echo=settings.db_echo,
            pool_pre_ping=settings.db_pool_pre_ping,
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory, initializing engine if needed."""
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health(timeout_seconds: float = 2.0) -> dict[str, Any]:
    """Asynchronously probe database connectivity with SELECT 1.

    Returns a status dictionary detailing connectivity and any error message.
    Does not raise exceptions.
    """
    settings = get_settings()
    engine = get_engine()

    async def _probe() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_probe(), timeout=timeout_seconds)
        return {
            "status": "connected",
            "url_host": engine.url.host,
            "database": engine.url.database,
            "driver": engine.url.drivername,
        }
    except Exception as exc:
        logger.warning(
            "database_readiness_probe_failed",
            error=str(exc),
            url_host=engine.url.host,
        )
        return {
            "status": "disconnected",
            "error": str(exc),
            "target": f"{engine.url.drivername}://{engine.url.host}:{engine.url.port}/{engine.url.database}",
            "configured_env": settings.app_env,
        }


async def close_db_engine() -> None:
    """Dispose of the database engine and connection pool during application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        logger.info("disposing_database_engine")
        await _engine.dispose()
        _engine = None
        _session_factory = None
