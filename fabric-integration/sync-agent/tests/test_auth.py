"""Unit tests for FinOps Sync Agent Azure CLI Authentication Manager."""

import json
from unittest.mock import MagicMock, patch

import pytest
from auth import AUDIENCE_ARM, AuthError, AzureCliAuthManager


def test_resolve_az_command_found():
    with patch("shutil.which", return_value="C:/Program Files/Azure/az.cmd"):
        mgr = AzureCliAuthManager()
        cmd = mgr._resolve_az_command()
        assert "az" in cmd


def test_resolve_az_command_missing():
    with patch("shutil.which", return_value=None), patch("pathlib.Path.exists", return_value=False):
        mgr = AzureCliAuthManager()
        with pytest.raises(AuthError, match="executable not found"):
            mgr._resolve_az_command()


def test_check_active_account_success():
    account_data = {
        "id": "sub-123",
        "tenantId": "tenant-456",
        "user": {"name": "user@example.com"},
    }
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(account_data)

    with (
        patch.object(AzureCliAuthManager, "_resolve_az_command", return_value="az"),
        patch("subprocess.run", return_value=mock_proc),
    ):
        mgr = AzureCliAuthManager(expected_subscription_id="sub-123")
        acc = mgr.check_active_account()
        assert acc["id"] == "sub-123"
        assert acc["user"]["name"] == "user@example.com"


def test_check_active_account_not_logged_in():
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "Please run 'az login' to setup account"

    with (
        patch.object(AzureCliAuthManager, "_resolve_az_command", return_value="az"),
        patch("subprocess.run", return_value=mock_proc),
    ):
        mgr = AzureCliAuthManager()
        with pytest.raises(AuthError, match="not logged in"):
            mgr.check_active_account()


def test_get_token_caching():
    token_response = {
        "accessToken": "secret-token-xyz",
        "expiresOn": "2099-01-01 12:00:00.000000",
    }
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(token_response)

    with (
        patch.object(AzureCliAuthManager, "_resolve_az_command", return_value="az"),
        patch("subprocess.run", return_value=mock_proc) as mock_sub,
    ):
        mgr = AzureCliAuthManager()
        # First call: hits subprocess
        t1 = mgr.get_token(AUDIENCE_ARM)
        assert t1 == "secret-token-xyz"
        assert mock_sub.call_count == 1

        # Second call: served from in-memory cache
        t2 = mgr.get_token(AUDIENCE_ARM)
        assert t2 == "secret-token-xyz"
        assert mock_sub.call_count == 1  # No additional subprocess call
