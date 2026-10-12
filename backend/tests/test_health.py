"""Integration tests for application health, readiness, and routing."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from cloud_recommender import __version__
from cloud_recommender.core.config import Settings


@pytest.mark.asyncio
async def test_liveness_endpoint(client: httpx.AsyncClient) -> None:
    """Verify GET /health returns 200 OK and expected structure."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "cloud-recommender-test"
    assert data["environment"] == "testing"
    assert data["version"] == __version__
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_versioned_liveness_endpoint(client: httpx.AsyncClient) -> None:
    """Verify GET /api/v1/health returns 200 OK under versioned route."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_endpoint_when_db_connected(client: httpx.AsyncClient) -> None:
    """Verify GET /health/ready returns 200 when database probe succeeds."""
    mock_db_status = {
        "status": "connected",
        "url_host": "localhost",
        "database": "cloud_recommender_test",
        "driver": "postgresql+asyncpg",
    }

    with patch(
        "cloud_recommender.api.routes.health.check_db_health",
        new_callable=AsyncMock,
        return_value=mock_db_status,
    ):
        response = await client.get("/health/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"
        assert data["dependencies"]["database"]["status"] == "connected"

        # Verify other components are NOT falsely claimed as healthy
        assert data["dependencies"]["azure_integration"]["checked"] is False
        assert data["dependencies"]["microsoft_fabric"]["checked"] is False
        assert data["dependencies"]["llm_orchestration"]["checked"] is False


@pytest.mark.asyncio
async def test_readiness_endpoint_when_db_disconnected(client: httpx.AsyncClient) -> None:
    """Verify GET /health/ready returns 503 when database is unreachable."""
    mock_db_status = {
        "status": "disconnected",
        "error": "Connection refused to PostgreSQL host localhost:5432",
        "target": "postgresql+asyncpg://localhost:5432/cloud_recommender_test",
    }

    with patch(
        "cloud_recommender.api.routes.health.check_db_health",
        new_callable=AsyncMock,
        return_value=mock_db_status,
    ):
        response = await client.get("/health/ready")
        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "not_ready"
        assert data["dependencies"]["database"]["status"] == "disconnected"
        assert "error" in data["dependencies"]["database"]


@pytest.mark.asyncio
async def test_root_endpoint(client: httpx.AsyncClient) -> None:
    """Verify GET / returns basic service discovery payload."""
    response = await client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "online"
    assert data["docs"] == "/docs"


@pytest.mark.asyncio
async def test_structured_404_error_handler(client: httpx.AsyncClient) -> None:
    """Verify requesting an unknown route returns formatted error JSON."""
    response = await client.get("/non-existent-route")
    assert response.status_code == 404

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == 404
    assert data["error"]["type"] == "http_error"


@pytest.mark.asyncio
async def test_unhandled_500_error_handler(app: FastAPI) -> None:
    """Verify unhandled exceptions trigger 500 JSON error handler."""

    @app.get("/test-error")
    async def trigger_error() -> None:
        raise RuntimeError("Simulated internal fault")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        response = await test_client.get("/test-error")
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == 500
        assert data["error"]["type"] == "internal_error"


@pytest.mark.asyncio
async def test_validation_error_handler(app: FastAPI) -> None:
    """Verify pydantic validation errors return structured 422 JSON."""
    from pydantic import BaseModel

    class PayloadModel(BaseModel):
        count: int

    @app.post("/test-validation")
    async def trigger_validation(payload: PayloadModel) -> dict[str, int]:
        return {"count": payload.count}

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        response = await test_client.post("/test-validation", json={"count": "not-an-int"})
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == 422
        assert data["error"]["type"] == "validation_error"


@pytest.mark.asyncio
async def test_app_lifespan_startup_and_shutdown(test_settings: Settings) -> None:
    """Verify lifespan context manager executes startup and cleanup without error."""
    from cloud_recommender.main import create_app, lifespan

    test_app = create_app(settings=test_settings)
    async with lifespan(test_app):
        pass
