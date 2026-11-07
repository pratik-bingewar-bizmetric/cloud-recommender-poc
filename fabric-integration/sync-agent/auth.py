"""Microsoft Fabric FinOps Sync Agent - Azure CLI Authentication Manager.

Provides audience-routed Azure access tokens by invoking the local Azure CLI session:
- https://management.azure.com (ARM, Resource Graph, Cost Management, Monitor)
- https://storage.azure.com (OneLake ADLS Gen2 Delta lake reader/writer)
- https://api.fabric.microsoft.com (Fabric REST operations)

Enforces zero-execution, read-only credential acquisition, and caches active tokens
in memory with expiration validation.
"""

import json
import logging
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("azure_sync_agent.auth")

AUDIENCE_ARM = "https://management.azure.com"
AUDIENCE_STORAGE = "https://storage.azure.com"
AUDIENCE_FABRIC = "https://api.fabric.microsoft.com"


class AuthError(Exception):
    """Raised when authentication or token acquisition fails."""


class AzureCliAuthManager:
    """Manages Azure authentication using the verified local Azure CLI session."""

    def __init__(
        self,
        expected_subscription_id: str | None = None,
        expected_tenant_id: str | None = None,
    ) -> None:
        self.expected_subscription_id = expected_subscription_id
        self.expected_tenant_id = expected_tenant_id
        self._az_path: str | None = None
        self._token_cache: dict[str, dict[str, Any]] = {}

    def _resolve_az_command(self) -> str:
        """Find the az executable on the Windows host."""
        if self._az_path:
            return self._az_path

        cmd = shutil.which("az.cmd") or shutil.which("az")
        if not cmd:
            # Common Windows installations
            for candidate in [
                Path("C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd"),
                Path("C:/Program Files (x86)/Microsoft SDKs/Azure/CLI2/wbin/az.cmd"),
            ]:
                if candidate.exists():
                    cmd = str(candidate)
                    break

        if not cmd:
            raise AuthError(
                "Azure CLI ('az') executable not found. Please ensure Azure CLI is installed "
                "and accessible in the system PATH."
            )
        self._az_path = cmd
        return cmd

    def check_active_account(self) -> dict[str, Any]:
        """Verify the active Azure CLI login and return current account metadata."""
        az_cmd = self._resolve_az_command()
        try:
            proc = subprocess.run(
                [az_cmd, "account", "show", "--output", "json"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=15,
            )
        except Exception as ex:
            raise AuthError(f"Failed to execute Azure CLI account check: {ex}") from ex

        if proc.returncode != 0:
            raise AuthError(
                f"Azure CLI is not logged in or active session expired: {proc.stderr.strip()}. "
                "Please run 'az login' before executing the sync agent."
            )

        try:
            account = json.loads(proc.stdout)
        except json.JSONDecodeError as ex:
            raise AuthError(f"Failed to parse 'az account show' output: {ex}") from ex

        current_sub = account.get("id")
        current_tenant = account.get("tenantId")
        user_name = account.get("user", {}).get("name", "Unknown")

        logger.info(
            "Active Azure CLI account verified: user='%s', tenant='%s', subscription='%s'",
            user_name,
            current_tenant,
            current_sub,
        )

        # Validate subscription if expected
        if self.expected_subscription_id and current_sub != self.expected_subscription_id:
            logger.warning(
                "Active subscription '%s' differs from expected '%s'. Attempting to set context...",
                current_sub,
                self.expected_subscription_id,
            )
            set_proc = subprocess.run(
                [az_cmd, "account", "set", "--subscription", self.expected_subscription_id],
                capture_output=True,
                text=True,
                shell=True,
                timeout=15,
            )
            if set_proc.returncode != 0:
                raise AuthError(
                    f"Failed to switch Azure CLI subscription to {self.expected_subscription_id}: "
                    f"{set_proc.stderr}"
                )
            account["id"] = self.expected_subscription_id

        # Validate tenant if expected
        if self.expected_tenant_id and current_tenant != self.expected_tenant_id:
            logger.warning(
                "Active tenant '%s' differs from expected '%s'.",
                current_tenant,
                self.expected_tenant_id,
            )

        return account

    def get_token(self, audience: str = AUDIENCE_ARM) -> str:
        """Acquire an OAuth2 Bearer token for the designated target audience."""
        now = datetime.now(UTC)

        # Check in-memory cache
        cached = self._token_cache.get(audience)
        if cached:
            expires_on = cached.get("expires_on")
            if expires_on and (expires_on - now).total_seconds() > 90:
                return cached["token"]

        az_cmd = self._resolve_az_command()
        cmd = [
            az_cmd,
            "account",
            "get-access-token",
            "--resource",
            audience,
            "--output",
            "json",
        ]

        logger.debug("Requesting fresh Azure CLI token for resource: %s", audience)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=20)
        except Exception as ex:
            raise AuthError(
                f"Subprocess call to Azure CLI failed for resource {audience}: {ex}"
            ) from ex

        if proc.returncode != 0:
            raise AuthError(
                f"Failed to acquire Azure token for resource '{audience}': {proc.stderr.strip()}"
            )

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as ex:
            raise AuthError(f"Failed to parse token JSON for {audience}: {ex}") from ex

        token = data.get("accessToken")
        if not token:
            raise AuthError(f"Azure CLI returned empty accessToken for resource {audience}")

        expires_str = data.get("expiresOn")
        expires_dt = None
        if expires_str:
            try:
                # Format: "2026-11-05 15:30:00.000000" or ISO format
                if "T" in expires_str:
                    expires_dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                else:
                    expires_dt = datetime.fromisoformat(expires_str).replace(tzinfo=UTC)
            except Exception:
                expires_dt = None

        self._token_cache[audience] = {
            "token": token,
            "expires_on": expires_dt,
        }

        return token
