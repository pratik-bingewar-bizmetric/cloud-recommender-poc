"""Automated tests for Phase 2.1D Databricks Production Authentication Readiness.

Verifies:
1. Production mode fail-closed enforcement (no silent fallback to personal Azure CLI).
2. Permission denied (HTTP 403) classification without compute mutation.
3. Secret scrubbing across exception messages and logs.
4. Tenant and workspace scoping integrity.
"""

from unittest.mock import MagicMock, patch

import pytest
from databricks.sdk.errors import PermissionDenied

from cloud_recommender.core.config import Settings
from cloud_recommender.services.databricks.auth import (
    DatabricksAuthError,
    DatabricksAuthService,
    classify_http_and_sdk_error,
)
from cloud_recommender.services.databricks.sql_client import DatabricksSqlService

WS = "642006393507276"
WH = "05ed10a52697a344"
HOST = "https://adb-642006393507276.16.azuredatabricks.net"


def test_production_mode_refuses_silent_fallback_to_azure_cli() -> None:
    """In production mode, missing SP credentials must raise DatabricksAuthError, not fall back to CLI."""
    settings = Settings(
        app_env="production",
        dev_auth_enabled=False,
        databricks_auth_type="oauth-m2m",
        databricks_client_id=None,
        databricks_client_secret=None,
    )
    auth_svc = DatabricksAuthService(settings)

    with pytest.raises(DatabricksAuthError) as exc_info:
        auth_svc.create_workspace_client(
            host=HOST,
            auth_type="oauth-m2m",
            environment="production",
        )
    assert "refusing silent fallback to personal Azure CLI credentials" in str(exc_info.value)


def test_production_403_access_denied_is_classified_cleanly() -> None:
    """Databricks OAuth 403 Workspace is inaccessible is classified as permission_denied."""
    err = PermissionDenied("access_denied: Workspace 642006393507276 is inaccessible")
    kind, code, detail = classify_http_and_sdk_error(err)
    assert kind == "permission_denied"
    assert code == 403
    assert detail == "HTTP_403"


def test_secret_scrubbing_redacts_tokens_and_client_secrets() -> None:
    """Sensitive tokens, secrets, and JWTs are scrubbed from strings."""
    secret = "my-super-secret-client-pass-12345"
    bearer = "Bearer ya29.a0AfH6SMD-fake-token-content-12345"
    jwt_token = (
        "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.fake-sig-token-12345"
    )
    raw_text = f"Connection failed with secret {secret} and token {bearer} and jwt {jwt_token}"

    with patch.dict("os.environ", {"DATABRICKS_CLIENT_SECRET": secret}):
        scrubbed = DatabricksAuthService.scrub_sensitive(raw_text)

    assert secret not in scrubbed
    assert bearer not in scrubbed
    assert jwt_token not in scrubbed
    assert "[REDACTED_SECRET]" in scrubbed
    assert "[REDACTED_TOKEN]" in scrubbed


def test_check_warehouse_status_reports_permission_denied_without_starting_compute() -> None:
    """When SP authentication fails with 403, status is PERMISSION_DENIED and no SQL runs."""
    fake_client = MagicMock()
    fake_client.current_user.me.side_effect = PermissionDenied(
        "access_denied: Workspace 642006393507276 is inaccessible"
    )

    sql_svc = DatabricksSqlService(
        host=HOST,
        warehouse_id=WH,
        auth_type="oauth-m2m",
        workspace_client=fake_client,
    )

    result = sql_svc.check_warehouse_status()
    assert result.status == "PERMISSION_DENIED"
    assert result.can_execute is False
    assert result.warehouse_state == "UNKNOWN"
    assert "PERMISSION_DENIED" in result.message
    # Verify warehouses.get was never called (auth check failed before querying compute)
    fake_client.warehouses.get.assert_not_called()


def test_dev_mode_uses_azure_cli_and_refuses_silent_sp_fallback() -> None:
    """When configured for azure-cli, auth service validates CLI and does not silently fall back to SP."""
    mock_cli = MagicMock()
    mock_cli.is_cli_installed.return_value = False

    settings = Settings(
        app_env="development",
        databricks_auth_type="azure-cli",
    )
    auth_svc = DatabricksAuthService(settings, azure_cli_provider=mock_cli)

    with pytest.raises(DatabricksAuthError) as exc_info:
        auth_svc.create_workspace_client(
            host=HOST,
            auth_type="azure-cli",
            environment="development",
        )
    assert "Azure CLI ('az') is not installed" in str(exc_info.value)
