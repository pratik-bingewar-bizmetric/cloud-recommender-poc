"""Regression tests for local-development authentication (401 on /connections and Databricks).

Root causes covered:
1. DEV_AUTH_ENABLED / DEV_AUTH_ROLES were not set in any ``.env`` the backend actually loads, so
   tokenless local requests correctly returned 401.
2. ``.env`` was looked up relative to the launch directory, so starting the API from ``backend/``
   (as startup.bat does) ignored the repository-root ``.env``.

Authentication is never bypassed: production behaviour (401 without/with a bad token, 403 without
the role) is asserted again here.
"""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from security_fixtures import PRODUCTION_SECURITY, build_app, make_token, new_rsa_key

from cloud_recommender.api.routes.connections import get_connection_service
from cloud_recommender.core.auth import describe_auth_mode
from cloud_recommender.core.config import InsecureConfigurationError, Settings, default_env_files
from cloud_recommender.main import lifespan


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_ENV", "DEV_AUTH_ENABLED", "DEV_AUTH_ROLES", "ENTRA_AUTH_ENABLED"):
        monkeypatch.delenv(name, raising=False)


def write_env(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------------------
# Env-file discovery (independent of the launch directory)
# --------------------------------------------------------------------------------------


def test_env_files_are_found_regardless_of_launch_directory(tmp_path: Path) -> None:
    write_env(tmp_path / ".env", "APP_ENV=development\n")
    write_env(tmp_path / "backend" / ".env", "CATALOG_OFFLINE_MODE=true\n")
    files = default_env_files(tmp_path, {})
    assert files == (
        str(tmp_path / ".env"),
        str(tmp_path / "backend" / ".env"),
    )  # root first, backend wins


def test_only_existing_env_files_are_returned(tmp_path: Path) -> None:
    write_env(tmp_path / ".env", "APP_ENV=development\n")
    assert default_env_files(tmp_path, {}) == (str(tmp_path / ".env"),)
    assert default_env_files(tmp_path / "missing", {}) == ()


def test_tests_never_read_a_developers_real_env_files(tmp_path: Path) -> None:
    write_env(tmp_path / ".env", "APP_ENV=development\n")
    assert default_env_files(tmp_path, {"APP_ENV": "testing"}) == ()


@pytest.mark.usefixtures("clean_env")
def test_dev_auth_flags_in_the_root_env_are_loaded(tmp_path: Path) -> None:
    write_env(
        tmp_path / ".env",
        'APP_ENV=development\nDEV_AUTH_ENABLED=true\nDEV_AUTH_ROLES=["FinOpsAdmin"]\n',
    )
    settings = Settings(_env_file=default_env_files(tmp_path, {}))  # type: ignore[call-arg]
    assert settings.dev_auth_enabled is True
    assert settings.dev_auth_roles == ["FinOpsAdmin"]
    assert settings.entra_auth_enabled is False  # dev mode does not turn Entra off in production


@pytest.mark.usefixtures("clean_env")
def test_without_the_flags_dev_auth_stays_off(tmp_path: Path) -> None:
    write_env(tmp_path / ".env", "APP_ENV=development\n")
    settings = Settings(_env_file=default_env_files(tmp_path, {}))  # type: ignore[call-arg]
    assert settings.dev_auth_enabled is False


# --------------------------------------------------------------------------------------
# Local development works end to end (real policy, no mock success responses)
# --------------------------------------------------------------------------------------


def dev_app(roles: list[str], enabled: bool = True) -> Any:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="development",
        catalog_offline_mode=True,
        dev_auth_enabled=enabled,
        dev_auth_roles=roles,
    )
    app = build_app(settings, new_rsa_key()[1])
    # The connection listing would otherwise query the developer's Azure session: stub only the
    # provider call, the authentication and authorization layers stay real.
    service = MagicMock()
    service.list_connections = AsyncMock(return_value=[])
    app.dependency_overrides[get_connection_service] = lambda: service
    return app


async def call(app: Any, method: str, path: str, **kw: Any) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.request(method, path, **kw)


@pytest.mark.asyncio
async def test_local_dev_lists_connections_and_databricks_without_a_token() -> None:
    app = dev_app(["FinOpsAdmin"])
    assert (await call(app, "GET", "/api/v1/connections")).status_code == 200
    assert (await call(app, "GET", "/api/v1/databricks/connections")).status_code == 200


@pytest.mark.asyncio
async def test_local_dev_admin_role_reaches_connection_validation() -> None:
    """Connection routes pass authorization (422 = stopped by the invalid test body)."""
    app = dev_app([])  # ordinary user: connections are owner operations, no admin role needed
    for path in ("/api/v1/connections/validate", "/api/v1/connections"):
        assert (await call(app, "POST", path, json=[])).status_code == 422, path


@pytest.mark.asyncio
async def test_local_dev_without_the_admin_role_gets_an_explanatory_403() -> None:
    app = dev_app([])
    response = await call(app, "POST", "/api/v1/finops/ingestion/run", json={})
    assert response.status_code == 403
    message = response.json()["error"]["message"]
    assert (
        message["error_code"] == "INSUFFICIENT_PERMISSIONS" and "FinOpsAdmin" in message["message"]
    )


@pytest.mark.asyncio
async def test_dev_auth_off_returns_401_with_an_actionable_message() -> None:
    app = dev_app(["FinOpsAdmin"], enabled=False)
    for path in ("/api/v1/connections", "/api/v1/databricks/connections"):
        response = await call(app, "GET", path)
        assert response.status_code == 401
        assert "DEV_AUTH_ENABLED" in response.json()["error"]["message"]["message"]
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_an_invalid_token_is_never_downgraded_to_the_dev_identity() -> None:
    app = dev_app(["FinOpsAdmin"])
    response = await call(
        app, "GET", "/api/v1/connections", headers={"Authorization": "Bearer junk"}
    )
    assert response.status_code == 401


# --------------------------------------------------------------------------------------
# Production authentication is unchanged
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_production_still_returns_401_and_403() -> None:
    keys = new_rsa_key()
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="production",
        catalog_offline_mode=True,
        **PRODUCTION_SECURITY,
    )
    app = build_app(settings, keys[1])
    for path in ("/api/v1/connections", "/api/v1/databricks/connections"):
        assert (await call(app, "GET", path)).status_code == 401
        bad = await call(app, "GET", path, headers={"Authorization": "Bearer not.a.jwt"})
        assert bad.status_code == 401
    user = {"Authorization": f"Bearer {make_token(keys[0], roles=[])}"}
    assert (
        await call(app, "POST", "/api/v1/finops/ingestion/run", headers=user, json={})
    ).status_code == 403  # restricted (billing execution) still needs FinOpsAdmin
    no_scope = {"Authorization": f"Bearer {make_token(keys[0], scp='')}"}
    assert (await call(app, "GET", "/api/v1/connections", headers=no_scope)).status_code == 403


def test_dev_auth_still_cannot_be_enabled_in_production() -> None:
    with pytest.raises(InsecureConfigurationError, match="DEV_AUTH_ENABLED"):
        Settings(_env_file=None, app_env="production", dev_auth_enabled=True)  # type: ignore[call-arg]


# --------------------------------------------------------------------------------------
# Startup diagnostics
# --------------------------------------------------------------------------------------


def test_auth_mode_is_described_for_each_configuration() -> None:
    off = Settings(_env_file=None, app_env="development", dev_auth_enabled=False)  # type: ignore[call-arg]
    dev = Settings(
        _env_file=None, app_env="development", dev_auth_enabled=True, dev_auth_roles=["FinOpsAdmin"]
    )  # type: ignore[call-arg]
    assert describe_auth_mode(off)[0] == "none" and "DEV_AUTH_ENABLED" in describe_auth_mode(off)[1]
    assert describe_auth_mode(dev)[0] == "development_identity"
    entra = Settings(_env_file=None, app_env="production", **PRODUCTION_SECURITY)  # type: ignore[call-arg]
    assert describe_auth_mode(entra)[0] == "entra"


@pytest.mark.asyncio
async def test_startup_warns_when_no_authentication_is_configured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="development",
        catalog_offline_mode=True,
        dev_auth_enabled=False,
    )
    monkeypatch.setattr("cloud_recommender.main.get_settings", lambda: settings)
    app = build_app(settings, new_rsa_key()[1])
    async with lifespan(app):  # lifespan reconfigures logging, so read the emitted log lines
        pass
    out = capsys.readouterr().out
    assert '"event": "authentication_not_configured"' in out
    assert "DEV_AUTH_ENABLED" in out
