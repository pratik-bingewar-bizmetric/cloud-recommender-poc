"""Azure App Service (Linux, Python 3.12) deployment readiness checks. No cloud access."""

import tomllib
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from security_fixtures import PRODUCTION_SECURITY, build_app, new_rsa_key

from cloud_recommender.core.config import Settings
from cloud_recommender.main import lifespan

BACKEND = Path(__file__).resolve().parent.parent


def test_startup_command_is_single_worker_uvicorn_bound_to_all_interfaces() -> None:
    script = (BACKEND / "startup.sh").read_text(encoding="utf-8")
    assert "cloud_recommender.main:app" in script
    assert "--workers 1" in script  # in-memory sessions: one worker only
    assert "--host 0.0.0.0" in script
    assert "WEBSITES_PORT" in script
    assert "--reload" not in script
    assert "\r" not in script  # LF line endings: CRLF breaks bash on Linux


def test_python_runtime_matches_app_service_target() -> None:
    assert (BACKEND / ".python-version").read_text().strip() == "3.12"
    pyproject = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["requires-python"].startswith(">=3.12")


def test_requirements_cover_the_runtime_imports() -> None:
    names = {
        line.split("[")[0].split(">")[0].split("=")[0].strip().lower()
        for line in (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert {"fastapi", "uvicorn", "httpx", "pydantic-settings", "pyjwt"} <= names
    assert "azure-cli" not in names  # the Azure CLI is never a runtime dependency


def documented_demo_settings(**overrides: object) -> Settings:
    """The documented minimum production configuration for the stateless demo (no database)."""
    return Settings(
        _env_file=None,
        app_env="production",
        catalog_offline_mode=True,
        databricks_inventory_refresh_seconds=0,  # Databricks background refresher off for the demo
        **{**PRODUCTION_SECURITY, **overrides},
    )


@pytest.mark.asyncio
async def test_production_app_starts_without_a_database_and_serves_health() -> None:
    settings = documented_demo_settings()
    app = build_app(settings, new_rsa_key()[1])
    async with lifespan(app):  # startup/shutdown hooks run without any DB connection
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            health = await client.get("/health")
            docs = await client.get("/docs")
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert "environment" in health.json() and health.json()["environment"] is None
    assert docs.status_code == 404


@pytest.mark.asyncio
async def test_cors_allows_only_the_configured_fabric_origin() -> None:
    fabric = "https://true-holly-e4e36b6da6-northcentralus.webapp.fabricapps.net"
    app: FastAPI = build_app(documented_demo_settings(cors_origins=[fabric]), new_rsa_key()[1])
    headers = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        allowed = await client.options(
            "/api/v1/azure/connections", headers={"Origin": fabric, **headers}
        )
        allowed_delete = await client.options(
            "/api/v1/azure/connections",
            headers={
                "Origin": fabric,
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        allowed_patch = await client.options(
            "/api/v1/azure/connections",
            headers={
                "Origin": fabric,
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        other = await client.options(
            "/api/v1/azure/connections", headers={"Origin": "https://evil.example.org", **headers}
        )
    assert allowed.status_code == 200 and allowed.headers["access-control-allow-origin"] == fabric
    assert (
        allowed_delete.status_code == 200
        and allowed_delete.headers["access-control-allow-origin"] == fabric
    )
    assert (
        allowed_patch.status_code == 200
        and allowed_patch.headers["access-control-allow-origin"] == fabric
    )
    assert other.status_code == 400
