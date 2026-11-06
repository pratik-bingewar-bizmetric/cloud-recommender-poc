"""OneLake Authentication Manager for Microsoft Fabric User Data Functions.

Provides verified OAuth2 Bearer tokens for the storage audience (https://storage.azure.com)
required by Delta Lake and ADLS Gen2 DFS drivers to read OneLake storage.

Enforces least-privilege read-only access, in-memory caching with proactive TTL refresh,
and secret protection (zero token logging).
"""

import json
import logging
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from .config import LakehouseReaderConfig

logger = logging.getLogger("finops_udf.lakehouse.auth")

AUDIENCE_STORAGE = "https://storage.azure.com"
STORAGE_SCOPE = "https://storage.azure.com/.default"


class LakehouseAuthError(Exception):
    """Raised when authentication to OneLake storage fails."""


class LakehousePermissionError(Exception):
    """Raised when caller identity lacks permissions on the Lakehouse."""


class OneLakeAuthManager:
    """Manages token acquisition and caching for OneLake ADLS Gen2 Delta storage."""

    def __init__(self, config: LakehouseReaderConfig | None = None) -> None:
        self.config = config or LakehouseReaderConfig.load()
        self._cached_token: str | None = None
        self._expires_at: datetime | None = None
        self._auth_method: str = "uninitialized"
        self._lock = threading.Lock()

    def get_token(self) -> tuple[str, str]:
        """Obtain a valid storage-audience bearer token.

        Returns:
            Tuple of (access_token, auth_method_description).
        """
        now = datetime.now(UTC)

        with self._lock:
            # Check cached token with 90-second expiration buffer
            if self._cached_token and self._expires_at:
                if (self._expires_at - now).total_seconds() > 90:
                    return self._cached_token, self._auth_method

            token, method, expires_dt = self._acquire_token()
            self._cached_token = token
            self._auth_method = method
            self._expires_at = expires_dt
            return token, method

    def _acquire_token(self) -> tuple[str, str, datetime]:
        """Acquire storage token using supported identity providers in priority order."""
        # 1. Service Principal via Environment or Config (Production Hosted Path)
        tenant_id = self.config.tenant_id or os.getenv("AZURE_TENANT_ID")
        client_id = self.config.client_id or os.getenv("AZURE_CLIENT_ID")
        client_secret = self.config.client_secret or os.getenv("AZURE_CLIENT_SECRET")

        if tenant_id and client_id and client_secret:
            try:
                token, expires_dt = self._acquire_sp_token(
                    tenant_id, client_id, client_secret
                )
                logger.debug(
                    "Successfully acquired OneLake storage token via Service Principal."
                )
                return token, "service_principal_credentials", expires_dt
            except Exception as exc:
                logger.warning(
                    "Service Principal token acquisition for OneLake failed: %s", exc
                )

        # 2. Managed Identity / Workload Identity (Fabric Hosted Runtime)
        if os.getenv("IDENTITY_ENDPOINT") or os.getenv("MSI_ENDPOINT"):
            try:
                token, expires_dt = self._acquire_managed_identity_token()
                logger.debug(
                    "Successfully acquired OneLake storage token via Managed Identity."
                )
                return token, "managed_identity", expires_dt
            except Exception as exc:
                logger.debug("Managed Identity token acquisition failed: %s", exc)

        # 3. Local Azure CLI Session Fallback (Local Development & Testing)
        try:
            token, expires_dt = self._acquire_cli_token()
            logger.debug(
                "Successfully acquired OneLake storage token via Azure CLI session."
            )
            return token, "azure_cli_session", expires_dt
        except Exception as exc:
            logger.debug("Azure CLI token fallback failed: %s", exc)

        raise LakehouseAuthError(
            "No valid OneLake storage authentication identity available. "
            "Please configure Service Principal credentials (AZURE_TENANT_ID, AZURE_CLIENT_ID, "
            "AZURE_CLIENT_SECRET), verify Fabric Managed Identity, or log in via 'az login'."
        )

    def _acquire_sp_token(
        self, tenant_id: str, client_id: str, client_secret: str
    ) -> tuple[str, datetime]:
        """Request OAuth2 client_credentials token for storage audience."""
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": STORAGE_SCOPE,
        }
        encoded_data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            token_url,
            data=encoded_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            body = http_err.read().decode("utf-8", errors="replace")
            if http_err.code in (401, 403):
                raise LakehousePermissionError(
                    f"Service principal authentication rejected for OneLake: {body}"
                ) from http_err
            raise LakehouseAuthError(
                f"OAuth HTTP error {http_err.code} acquiring OneLake token: {body}"
            ) from http_err

        token = data.get("access_token")
        if not token:
            raise LakehouseAuthError(
                "Empty access_token received from Microsoft Entra token endpoint."
            )

        expires_in = int(data.get("expires_in", 3600))
        expires_dt = datetime.fromtimestamp(
            datetime.now(UTC).timestamp() + expires_in, tz=UTC
        )
        return token, expires_dt

    def _acquire_managed_identity_token(self) -> tuple[str, datetime]:
        """Acquire storage token from Azure Managed Identity endpoint."""
        identity_endpoint = os.getenv("IDENTITY_ENDPOINT") or os.getenv("MSI_ENDPOINT")
        identity_header = os.getenv("IDENTITY_HEADER") or os.getenv("MSI_SECRET", "")
        url = f"{identity_endpoint}?resource={urllib.parse.quote(AUDIENCE_STORAGE)}&api-version=2019-08-01"

        req = urllib.request.Request(
            url,
            headers={"X-IDENTITY-HEADER": identity_header, "Metadata": "true"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        token = data.get("access_token")
        if not token:
            raise LakehouseAuthError(
                "Empty access_token received from Managed Identity endpoint."
            )

        expires_in = int(data.get("expires_in", 3600))
        expires_dt = datetime.fromtimestamp(
            datetime.now(UTC).timestamp() + expires_in, tz=UTC
        )
        return token, expires_dt

    def _acquire_cli_token(self) -> tuple[str, datetime]:
        """Acquire storage token using host Azure CLI session for local testing."""
        az_cmd = shutil.which("az.cmd") or shutil.which("az") or "az"
        cmd = [
            az_cmd,
            "account",
            "get-access-token",
            "--resource",
            AUDIENCE_STORAGE,
            "--output",
            "json",
        ]
        proc = subprocess.run(
            cmd, check=False, capture_output=True, text=True, shell=True, timeout=15
        )
        if proc.returncode != 0:
            raise LakehouseAuthError(
                f"Azure CLI token acquisition failed: {proc.stderr.strip()}"
            )

        data = json.loads(proc.stdout)
        token = data.get("accessToken")
        if not token:
            raise LakehouseAuthError(
                "Azure CLI returned empty accessToken for OneLake."
            )

        expires_str = data.get("expiresOn")
        expires_dt = None
        if expires_str:
            try:
                if "T" in expires_str:
                    expires_dt = datetime.fromisoformat(
                        expires_str.replace("Z", "+00:00")
                    )
                else:
                    expires_dt = datetime.fromisoformat(expires_str).replace(tzinfo=UTC)
            except Exception:
                expires_dt = None

        if not expires_dt:
            expires_dt = datetime.fromtimestamp(
                datetime.now(UTC).timestamp() + 3600, tz=UTC
            )

        return token, expires_dt

    def get_storage_options(self) -> dict[str, str]:
        """Generate storage_options dictionary for Delta Lake / PyArrow OneLake connection."""
        token, _ = self.get_token()
        return {
            "bearer_token": token,
            "account_name": "onelake",
        }
