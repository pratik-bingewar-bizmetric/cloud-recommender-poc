"""Pytest global configuration, test fixtures, and mock clients."""

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    """Provide isolated testing settings."""
    return Settings(
        app_name="cloud-recommender-test",
        app_env="testing",
        debug=True,
        api_port=8000,
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/cloud_recommender_test",
        llm_provider="mock",
        fabric_enabled=False,
        offline_pricing_mode=True,
    )


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    """Create a FastAPI application instance for testing."""
    test_app = create_app(settings=test_settings)
    # Override dependency settings
    test_app.dependency_overrides[get_settings] = lambda: test_settings
    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client bound to the ASGI application."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
