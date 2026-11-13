"""M2.5 regression pins: Databricks and Azure ARM credential paths stay separate.

DEV_LOCAL uses the delegated Azure CLI identity even when unrelated service-principal secrets
exist; production stays fail-closed on the Databricks service principal; Azure Resource Group
discovery never touches the Databricks credential path.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cloud_recommender.core.config import Settings
from cloud_recommender.services.databricks.auth import (
    AzureCliCredentialProvider,
    DatabricksAuthError,
    DatabricksAuthService,
)

DEV_HOST = "https://adb-642006393507276.16.azuredatabricks.net"
SP_ID = "11111111-2222-3333-4444-555555555555"
SP_SECRET = "dummy-secret-value-0123456789abcdef0123"  # not a real credential


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "APP_ENV",
        "DATABRICKS_AUTH_TYPE",
        "DATABRICKS_CLIENT_ID",
        "DATABRICKS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)


def _cli(installed: bool = True, logged_in: bool = True) -> AzureCliCredentialProvider:
    provider = MagicMock(spec=AzureCliCredentialProvider)
    provider.is_cli_installed.return_value = installed
    provider.validate_cli_session.return_value = (logged_in, "dev.user@example.com", {})
    return provider  # type: ignore[no-any-return]


def _settings(**kw: Any) -> Settings:
    base: dict[str, Any] = {"app_env": "development", "offline_pricing_mode": True}
    base.update(kw)
    return Settings(**base)


def _build(settings: Settings, provider: AzureCliCredentialProvider, **kw: Any) -> MagicMock:
    svc = DatabricksAuthService(settings=settings, azure_cli_provider=provider)
    with patch("cloud_recommender.services.databricks.auth.WorkspaceClient") as ws:
        svc.create_workspace_client(DEV_HOST, cloud="azure", **kw)
    return ws  # type: ignore[no-any-return]


def test_dev_uses_azure_cli_even_when_databricks_sp_secret_is_populated() -> None:
    """Populating DATABRICKS_CLIENT_ID/SECRET must not silently switch Dev to the SP."""
    ws = _build(_settings(databricks_client_id=SP_ID, databricks_client_secret=SP_SECRET), _cli())
    kwargs = ws.call_args.kwargs
    assert kwargs["auth_type"] == "azure-cli"
    assert "client_id" not in kwargs and "client_secret" not in kwargs


def test_dev_ignores_azure_arm_service_principal_credentials() -> None:
    """AZURE_CLIENT_ID/SECRET (ARM) must never become Databricks credentials."""
    ws = _build(
        _settings(
            azure_tenant_id="fe82a67c-faa7-4d9a-bbfa-7d25b7047b41",
            azure_client_id=SP_ID,
            azure_client_secret=SP_SECRET,
        ),
        _cli(),
    )
    kwargs = ws.call_args.kwargs
    assert kwargs["auth_type"] == "azure-cli"
    assert SP_SECRET not in repr(kwargs) and SP_ID not in repr(kwargs)


def test_dev_without_cli_session_fails_closed_instead_of_using_sp() -> None:
    settings = _settings(databricks_client_id=SP_ID, databricks_client_secret=SP_SECRET)
    svc = DatabricksAuthService(settings=settings, azure_cli_provider=_cli(logged_in=False))
    with patch("cloud_recommender.services.databricks.auth.WorkspaceClient") as ws:
        with pytest.raises(DatabricksAuthError, match="az login"):
            svc.create_workspace_client(DEV_HOST, cloud="azure")
    ws.assert_not_called()


def test_production_without_sp_credentials_never_falls_back_to_azure_cli() -> None:
    provider = _cli()
    svc = DatabricksAuthService(
        settings=_settings(app_env="production"), azure_cli_provider=provider
    )
    with patch("cloud_recommender.services.databricks.auth.WorkspaceClient") as ws:
        with pytest.raises(DatabricksAuthError, match="refusing silent fallback"):
            svc.create_workspace_client(DEV_HOST, cloud="azure")
    ws.assert_not_called()
    provider.validate_cli_session.assert_not_called()


def test_production_environment_argument_uses_databricks_sp_not_azure_credentials() -> None:
    settings = _settings(
        databricks_client_id=SP_ID,
        databricks_client_secret=SP_SECRET,
        azure_client_id="99999999-8888-7777-6666-555555555555",
        azure_client_secret="another-dummy-secret-0123456789abcdef01234",
    )
    ws = _build(settings, _cli(), environment="production")
    kwargs = ws.call_args.kwargs
    assert kwargs["auth_type"] == "oauth-m2m"
    assert kwargs["client_id"] == SP_ID and kwargs["client_secret"] == SP_SECRET


def test_azure_resource_group_discovery_does_not_touch_databricks_credentials() -> None:
    src = Path(__file__).parents[1] / "src" / "cloud_recommender" / "services" / "azure"
    text = (src / "discovery_service.py").read_text(encoding="utf-8").lower()
    assert "databricks" not in text
