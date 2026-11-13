"""Pytest global configuration, test fixtures, and mock clients."""

import os
from collections.abc import AsyncGenerator

# Configure fail-closed cryptographic signing key for test environment
os.environ.setdefault("FINOPS_SIGNING_SECRET", "finops-test-signing-secret-2026-min-32-chars-long")
os.environ.setdefault("FINOPS_SIGNING_KID", "k1-2026")
# Tests opt in to labelled demo fixtures; production code fails closed when Azure auth is missing.
os.environ.setdefault("ALLOW_DEMO_FIXTURES", "true")

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
        catalog_offline_mode=True,
        llm_provider="mock",
        fabric_enabled=False,
        offline_pricing_mode=True,
        allow_demo_fixtures=True,  # tests opt in to labelled fixtures; production fails closed
        finops_signing_secret="finops-test-signing-secret-2026-min-32-chars-long",
        finops_signing_kid="k1-2026",
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
