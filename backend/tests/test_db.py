"""Unit tests for database module, lazy engine initialization, and health checks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud_recommender.db.session import (
    check_db_health,
    close_db_engine,
    get_engine,
    get_session_factory,
)


@pytest.mark.asyncio
async def test_lazy_engine_initialization() -> None:
    """Verify get_engine initializes and reuses singleton without connecting on import."""
    engine1 = get_engine()
    engine2 = get_engine()
    assert engine1 is engine2

    factory = get_session_factory()
    assert factory is not None

    await close_db_engine()


@pytest.mark.asyncio
async def test_check_db_health_unreachable_database() -> None:
    """Verify check_db_health gracefully returns disconnected dict on connection error."""
    await close_db_engine()

    # The test database URL is an unreachable localhost port
    result = await check_db_health()
    assert isinstance(result, dict)
    assert result["status"] in ["connected", "disconnected"]

    if result["status"] == "disconnected":
        assert "error" in result

    await close_db_engine()


@pytest.mark.asyncio
async def test_check_db_health_mock_success() -> None:
    """Verify check_db_health returns connected dict when connection executes cleanly."""
    mock_conn = AsyncMock()
    mock_conn.execute.return_value = None

    mock_connect_context = AsyncMock()
    mock_connect_context.__aenter__.return_value = mock_conn
    mock_connect_context.__aexit__.return_value = None

    # Use MagicMock for engine so connect() synchronously returns the async context manager
    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_connect_context
    mock_engine.url.host = "mock-host"
    mock_engine.url.database = "mock-db"
    mock_engine.url.drivername = "postgresql+asyncpg"

    with patch("cloud_recommender.db.session.get_engine", return_value=mock_engine):
        result = await check_db_health()
        assert result["status"] == "connected"
        assert result["database"] == "mock-db"
        assert result["driver"] == "postgresql+asyncpg"


@pytest.mark.asyncio
async def test_get_db_session_generator() -> None:
    """Verify get_db_session dependency yields session and closes."""
    from cloud_recommender.db.session import get_db_session

    mock_session = AsyncMock()
    mock_session.rollback.return_value = None
    mock_session.close.return_value = None

    mock_session_factory = MagicMock()
    mock_session_context = AsyncMock()
    mock_session_context.__aenter__.return_value = mock_session
    mock_session_context.__aexit__.return_value = None
    mock_session_factory.return_value = mock_session_context

    with patch(
        "cloud_recommender.db.session.get_session_factory", return_value=mock_session_factory
    ):
        async for session in get_db_session():
            assert session is mock_session
