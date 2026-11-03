"""Unit and integration tests for FastAPI CORS policy and origin verification."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cloud_recommender.core.config import Settings
from cloud_recommender.main import create_app

FABRIC_HOSTING_ORIGIN = "https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net"
FABRIC_PORTAL_ORIGIN = "https://app.fabric.microsoft.com"
LOCAL_DEV_ORIGIN_3000 = "http://localhost:3000"
LOCAL_DEV_ORIGIN_5173 = "http://localhost:5173"
DISALLOWED_ORIGIN = "https://malicious-attacker.com"


@pytest.fixture
def default_app() -> FastAPI:
    """Create FastAPI application with default production-ready CORS origin list."""
    s = Settings(catalog_offline_mode=True)
    return create_app(settings=s)


def test_cors_origins_env_string_parsing() -> None:
    """Verify comma-separated CORS_ORIGINS string is parsed and stripped into clean list."""
    s = Settings(
        cors_origins="https://portal.fabric.microsoft.com, https://my-custom-app.com , http://localhost:8080"
    )
    assert s.cors_origins == [
        "https://portal.fabric.microsoft.com",
        "https://my-custom-app.com",
        "http://localhost:8080",
    ]


def test_cors_origins_default_list() -> None:
    """Verify default origin list contains required local dev and Fabric cloud origins."""
    s = Settings()
    assert LOCAL_DEV_ORIGIN_3000 in s.cors_origins
    assert LOCAL_DEV_ORIGIN_5173 in s.cors_origins
    assert FABRIC_PORTAL_ORIGIN in s.cors_origins
    assert FABRIC_HOSTING_ORIGIN in s.cors_origins
    assert "*" not in s.cors_origins


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "allowed_origin",
    [
        LOCAL_DEV_ORIGIN_3000,
        LOCAL_DEV_ORIGIN_5173,
        FABRIC_PORTAL_ORIGIN,
        FABRIC_HOSTING_ORIGIN,
    ],
)
async def test_cors_allowed_origins_preflight(default_app: FastAPI, allowed_origin: str) -> None:
    """Verify OPTIONS preflight request from allowed origins receives CORS headers."""
    transport = ASGITransport(app=default_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": allowed_origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == allowed_origin
    assert "GET" in response.headers.get("access-control-allow-methods", "")


@pytest.mark.asyncio
async def test_cors_rejected_origin_preflight(default_app: FastAPI) -> None:
    """Verify disallowed origins do not receive access-control-allow-origin in preflight."""
    transport = ASGITransport(app=default_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": DISALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )

    # Starlette CORS middleware omits access-control-allow-origin for unauthorized origins
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_cors_rejected_origin_simple_request(default_app: FastAPI) -> None:
    """Verify disallowed origins do not receive access-control-allow-origin on simple requests."""
    transport = ASGITransport(app=default_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/health",
            headers={"Origin": DISALLOWED_ORIGIN},
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
