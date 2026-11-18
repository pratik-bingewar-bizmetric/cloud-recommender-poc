"""Databricks authentication service using official Databricks SDK.

Supports:
- Local development through supported Databricks CLI profile authentication.
- Azure CLI native authentication for Azure Databricks workspaces.
- Production authentication through OAuth service-principal credentials via environment variables.
- Connection validation and detailed error handling without credential leakage.
"""

import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Literal

import httpx
import structlog
from databricks.sdk import WorkspaceClient

from cloud_recommender.core.config import (
    Settings,
    has_valid_sp_credentials,
    reload_settings,
)

logger = structlog.get_logger(__name__)

DATABRICKS_RESOURCE_APP_ID = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"

_RE_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE)
_RE_DAPI_TOKEN = re.compile(r"\bdapi[a-f0-9]{16,}\b", re.IGNORECASE)
_RE_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")


class DatabricksAuthError(Exception):
    """Raised when Databricks authentication or connection fails."""

    def __init__(self, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(message)
        self.raw_error = raw_error


class AzureCliCredentialProvider:
    """Acquires, caches, and refreshes Azure CLI delegated bearer tokens dynamically for Databricks.

    - In-memory caching only with TTL buffer; never persists tokens to disk, .env, or database.
    - Redacts all sensitive credentials and tokens from logs and error strings.
    - Provides CLI detection, session validation, dynamic token acquisition, and HTTP header generation.
    """

    def __init__(
        self,
        resource: str = DATABRICKS_RESOURCE_APP_ID,
        ttl_buffer_seconds: int = 300,
    ) -> None:
        self.resource = resource
        self.ttl_buffer_seconds = ttl_buffer_seconds
        self._cached_token: str | None = None
        self._cached_expires_on: int = 0  # epoch seconds

    @staticmethod
    def _find_az_executable() -> str | None:
        """Locate az or az.cmd executable in PATH."""
        return shutil.which("az") or shutil.which("az.cmd")

    def is_cli_installed(self) -> bool:
        """Check whether Azure CLI is installed on the host system."""
        return self._find_az_executable() is not None

    def validate_cli_session(self) -> tuple[bool, str, dict[str, Any] | None]:
        """Validate whether the user is logged into an active Azure CLI session.

        Returns:
            (is_authenticated: bool, user_name_or_error: str, account_info: dict | None)
        """
        az_bin = self._find_az_executable()
        if not az_bin:
            return (
                False,
                "Azure CLI ('az') is not installed or not found in system PATH. Please install Azure CLI.",
                None,
            )

        try:
            res = subprocess.run(
                [az_bin, "account", "show", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if res.returncode != 0:
                raw_err = (res.stderr or res.stdout or "").strip()
                scrubbed = DatabricksAuthService.scrub_sensitive(raw_err)
                return (
                    False,
                    f"Azure CLI session is not authenticated or has expired ({scrubbed}). Please run 'az login'.",
                    None,
                )

            data = json.loads(res.stdout)
            user_data = data.get("user") or {}
            user_name = user_data.get("name") or "authenticated_user"
            return True, user_name, data

        except subprocess.TimeoutExpired:
            return (
                False,
                "Azure CLI timed out verifying session. Please ensure 'az login' is active.",
                None,
            )
        except Exception as exc:
            scrubbed = DatabricksAuthService.scrub_sensitive(str(exc))
            return False, f"Failed to validate Azure CLI session: {scrubbed}", None

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Acquire an Azure CLI bearer token dynamically with in-memory caching.

        Tokens are refreshed when within ttl_buffer_seconds (default 300s) of expiry.
        Never persists tokens to disk, .env, or logs.
        """
        now = int(time.time())
        if (
            not force_refresh
            and self._cached_token
            and now < (self._cached_expires_on - self.ttl_buffer_seconds)
        ):
            return self._cached_token

        az_bin = self._find_az_executable()
        if not az_bin:
            raise DatabricksAuthError(
                "Azure CLI ('az') is not installed or not found in system PATH. Cannot acquire delegated token."
            )

        try:
            res = subprocess.run(
                [
                    az_bin,
                    "account",
                    "get-access-token",
                    "--resource",
                    self.resource,
                    "--output",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if res.returncode != 0:
                raw_err = (res.stderr or res.stdout or "").strip()
                scrubbed = DatabricksAuthService.scrub_sensitive(raw_err)
                raise DatabricksAuthError(
                    f"Azure CLI token acquisition failed: {scrubbed}. Please run 'az login'."
                )

            payload = json.loads(res.stdout)
            token = payload.get("accessToken")
            if not token:
                raise DatabricksAuthError("Azure CLI returned an empty access token.")

            expires_on = payload.get("expires_on")
            if isinstance(expires_on, (int, float)):
                self._cached_expires_on = int(expires_on)
            else:
                self._cached_expires_on = now + 3600

            self._cached_token = str(token)
            return self._cached_token

        except subprocess.TimeoutExpired as exc:
            raise DatabricksAuthError("Azure CLI token acquisition timed out after 20s.") from exc
        except DatabricksAuthError:
            raise
        except Exception as exc:
            scrubbed = DatabricksAuthService.scrub_sensitive(str(exc))
            raise DatabricksAuthError(f"Azure CLI token acquisition error: {scrubbed}") from exc

    def get_auth_headers(self, force_refresh: bool = False) -> dict[str, str]:
        """Return Authorization Bearer header for HTTP requests without exposing the token to callers."""
        token = self.get_access_token(force_refresh=force_refresh)
        return {"Authorization": f"Bearer {token}"}


def classify_http_and_sdk_error(
    error: Exception | str,
) -> tuple[
    Literal["auth_failed", "permission_denied", "not_supported", "rate_limited", "unavailable"],
    int | None,
    str,
]:
    """Classify Databricks SDK/REST errors across 401, 403, 404, 429, 5xx, and transport failures."""
    if isinstance(error, DatabricksAuthError):
        return "auth_failed", 401, "HTTP_401"

    status_code: int | None = getattr(error, "status_code", None)
    if status_code is None:
        resp = getattr(error, "response", None)
        if resp is not None:
            status_code = getattr(resp, "status_code", None)

    msg = str(error).lower()

    if status_code == 401 or (
        "401" in msg
        or "invalid_client" in msg
        or "unauthorized_client" in msg
        or "aadsts" in msg
        or "cannot configure default credentials" in msg
        or "invalid_grant" in msg
        or "invalid token" in msg
        or "expired token" in msg
        or "databricksautherror" in msg
        or ("oauth" in msg and ("missing" in msg or "invalid" in msg or "secret" in msg))
    ):
        return "auth_failed", status_code or 401, "HTTP_401"

    if status_code == 403 or (
        "403" in msg
        or "access_denied" in msg
        or "inaccessible" in msg
        or "permission" in msg
        or "forbidden" in msg
        or "lacks" in msg
        or "not authorized" in msg
    ):
        return "permission_denied", status_code or 403, "HTTP_403"

    if status_code == 429 or "429" in msg or "too many requests" in msg or "rate limit" in msg:
        return "rate_limited", status_code or 429, "HTTP_429"

    if status_code == 404 or (
        "404" in msg
        or "not found" in msg
        or "not enabled" in msg
        or "unsupported" in msg
        or "feature_disabled" in msg
        or "does not exist" in msg
    ):
        return "not_supported", status_code or 404, "HTTP_404"

    if status_code is not None and 500 <= status_code < 600:
        return "unavailable", status_code, "HTTP_5XX"

    for code in ("500", "502", "503", "504"):
        if code in msg:
            return "unavailable", int(code), "HTTP_5XX"

    return "unavailable", status_code, "CONNECTION_ERROR"


def classify_databricks_error(
    error: Exception | str,
) -> Literal["auth_failed", "permission_denied", "connection_error"]:
    """Classify a Databricks SDK/HTTP error into auth_failed, permission_denied, or connection_error."""
    kind, _, _ = classify_http_and_sdk_error(error)
    if kind == "auth_failed":
        return "auth_failed"
    if kind == "permission_denied":
        return "permission_denied"
    return "connection_error"


class DatabricksAuthService:
    """Service resolving authenticated Databricks WorkspaceClient instances."""

    def __init__(
        self,
        settings: Settings | None = None,
        azure_cli_provider: AzureCliCredentialProvider | None = None,
    ) -> None:
        self.settings = settings
        self.azure_cli_provider = azure_cli_provider or AzureCliCredentialProvider()

    @staticmethod
    def scrub_sensitive(text: str) -> str:
        """Ensure tokens, secret keys, or passwords are never exposed in logs or API errors."""
        if not text:
            return ""
        # Redact common token patterns
        scrubbed = str(text)
        candidates: list[str] = []
        for env_key in (
            "DATABRICKS_TOKEN",
            "DATABRICKS_CLIENT_SECRET",
            "ARM_CLIENT_SECRET",
            "AZURE_CLIENT_SECRET",
        ):
            val = os.environ.get(env_key, "").strip()
            if val:
                candidates.append(val)
        try:
            active_settings = reload_settings()
            for attr in ("databricks_client_secret", "azure_client_secret"):
                val = (getattr(active_settings, attr, None) or "").strip()
                if val:
                    candidates.append(val)
        except Exception:
            pass
        for secret in candidates:
            if len(secret) >= 4 and secret in scrubbed:
                scrubbed = scrubbed.replace(secret, "[REDACTED_SECRET]")
        scrubbed = _RE_BEARER.sub(r"\1[REDACTED_TOKEN]", scrubbed)
        scrubbed = _RE_DAPI_TOKEN.sub("[REDACTED_TOKEN]", scrubbed)
        scrubbed = _RE_JWT.sub("[REDACTED_TOKEN]", scrubbed)
        return scrubbed

    def _resolve_sp_credentials(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> tuple[str | None, str | None, Settings]:
        """Resolve Databricks OAuth SP client_id and client_secret from args, env, or .env."""
        active_settings = self.settings if self.settings is not None else reload_settings()
        sp_id = (
            client_id
            or os.environ.get("DATABRICKS_CLIENT_ID")
            or active_settings.databricks_client_id
        )
        sp_secret = (
            client_secret
            or os.environ.get("DATABRICKS_CLIENT_SECRET")
            or active_settings.databricks_client_secret
        )
        return (
            sp_id.strip() if sp_id else None,
            sp_secret.strip() if sp_secret else None,
            active_settings,
        )

    def acquire_oauth_m2m_token(
        self,
        host: str,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> tuple[bool, int | None, str]:
        """Verify Databricks OAuth M2M token acquisition directly against /oidc/v1/token.

        Returns (success, http_status_code, sanitized_detail). Never logs or returns tokens.
        """
        host_clean = host.strip().rstrip("/")
        sp_id, sp_secret, _ = self._resolve_sp_credentials(client_id, client_secret)
        if not has_valid_sp_credentials(sp_id, sp_secret):
            return (
                False,
                None,
                "DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET are missing or placeholders.",
            )

        assert sp_id is not None and sp_secret is not None
        token_url = f"{host_clean}/oidc/v1/token"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    token_url,
                    data={"grant_type": "client_credentials", "scope": "all-apis"},
                    auth=(sp_id, sp_secret),
                )
            if resp.status_code == 200 and resp.json().get("access_token"):
                return True, 200, "Databricks OAuth M2M token acquired successfully."
            detail = self.scrub_sensitive(resp.text.strip())
            return False, resp.status_code, detail or f"HTTP {resp.status_code}"
        except Exception as exc:
            return False, None, self.scrub_sensitive(str(exc))

    def create_workspace_client(
        self,
        host: str,
        cloud: str = "azure",
        profile: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        auth_type: str | None = None,
        environment: str | None = None,
    ) -> WorkspaceClient:
        """Instantiate an official Databricks WorkspaceClient using explicit environment separation.

        Strategy hierarchy:
        1. PROD Mode / Explicit OAuth M2M SP:
           - In production (environment='production' or app_env='production') or when auth_type='oauth-m2m',
             require valid Service Principal credentials (DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET).
           - Fails closed: NEVER silently falls back to personal developer Azure CLI credentials.
        2. DEV_LOCAL / Azure CLI Delegated Auth:
           - In development/local environment or when auth_type='azure-cli' or targeting Azure Dev workspace,
             prefers Azure CLI delegated authentication.
           - Validates Azure CLI installation and active session before proceeding.
           - Fails with actionable message if Azure CLI is missing or expired.
           - Fails closed: NEVER silently falls back to Service Principal authentication.
        3. Databricks CLI Profile:
           - When profile is specified (e.g. AWS Databricks or explicit profile).
        4. Explicit SP args:
           - If caller explicitly passed non-empty client_id and client_secret in function call.
        5. Default SDK ambient resolution fallback.
        """
        host_clean = host.strip().rstrip("/")
        sp_id, sp_secret, active_settings = self._resolve_sp_credentials(client_id, client_secret)

        # Resolve effective environment
        effective_env = (
            (environment or os.environ.get("APP_ENV") or active_settings.app_env or "development")
            .strip()
            .lower()
        )
        is_production = effective_env in ("production", "prod")
        is_dev = effective_env in ("development", "dev", "local", "dev_local")
        is_azure = cloud.lower() == "azure" or "azuredatabricks.net" in host_clean

        # Resolve configured auth_type
        configured_auth = (
            (
                auth_type
                or os.environ.get("DATABRICKS_AUTH_TYPE")
                or active_settings.databricks_auth_type
                or ""
            )
            .strip()
            .lower()
        )

        dev_ws_id = (
            active_settings.databricks_dev_workspace_id
            or active_settings.databricks_workspace_id
            or "642006393507276"
        ).strip()
        is_dev_workspace = dev_ws_id in host_clean or "642006393507276" in host_clean

        # Priority 1: Production Mode or explicit OAuth M2M SP requested
        if is_production or configured_auth in ("oauth", "oauth-m2m"):
            if not has_valid_sp_credentials(sp_id, sp_secret):
                raise DatabricksAuthError(
                    "Databricks OAuth M2M Service Principal credentials (DATABRICKS_CLIENT_ID / "
                    "DATABRICKS_CLIENT_SECRET) are missing, incomplete, or placeholders; refusing "
                    "silent fallback to personal Azure CLI credentials in production mode."
                )
            assert sp_id is not None and sp_secret is not None
            logger.info("databricks_auth_using_oauth_m2m_sp", host=host_clean)
            return WorkspaceClient(
                host=host_clean,
                client_id=sp_id,
                client_secret=sp_secret,
                auth_type="oauth-m2m",
            )

        # Priority 2: DEV_LOCAL / Azure CLI Delegated Auth
        wants_azure_cli = (
            configured_auth in ("azure-cli", "azure_cli", "cli")
            or (
                is_dev
                and is_azure
                and configured_auth not in ("oauth", "oauth-m2m")
                and not profile
            )
            or (
                is_dev_workspace
                and not is_production
                and configured_auth not in ("oauth", "oauth-m2m")
            )
        )

        if wants_azure_cli and is_azure:
            if not self.azure_cli_provider.is_cli_installed():
                raise DatabricksAuthError(
                    "Azure CLI ('az') is not installed or not found in system PATH. "
                    "Cannot authenticate to Databricks Dev workspace via Azure CLI."
                )
            is_logged_in, user_or_err, _ = self.azure_cli_provider.validate_cli_session()
            if not is_logged_in:
                raise DatabricksAuthError(
                    f"Azure CLI authentication required for Dev workspace: {user_or_err} "
                    "Please run 'az login' in your terminal."
                )
            logger.info("databricks_auth_using_azure_cli", host=host_clean, user=user_or_err)
            return WorkspaceClient(host=host_clean, auth_type="azure-cli")

        # Priority 3: Databricks CLI Profile
        if profile:
            try:
                logger.info("databricks_auth_using_profile", host=host_clean, profile=profile)
                return WorkspaceClient(host=host_clean, profile=profile.strip())
            except Exception as exc:
                logger.debug("databricks_profile_init_fallback", profile=profile, error=str(exc))

        # Priority 4: Explicit SP credentials passed directly in function call
        if client_id and client_secret and has_valid_sp_credentials(sp_id, sp_secret):
            assert sp_id is not None and sp_secret is not None
            logger.info("databricks_auth_using_explicit_sp_args", host=host_clean)
            return WorkspaceClient(
                host=host_clean,
                client_id=sp_id,
                client_secret=sp_secret,
                auth_type="oauth-m2m",
            )

        # Priority 5: Fallback to ambient default auth
        logger.info("databricks_auth_using_default_config", host=host_clean)
        return WorkspaceClient(host=host_clean)

    def test_connection(
        self,
        host: str,
        cloud: str = "azure",
        profile: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        auth_type: str | None = None,
        environment: str | None = None,
    ) -> tuple[bool, str, str | None]:
        """Validate live connectivity and authentication against the workspace.

        Returns (success: bool, details: str, current_user: str | None).
        Never throws unhandled exceptions or leaks secrets.
        """
        try:
            client = self.create_workspace_client(
                host=host,
                cloud=cloud,
                profile=profile,
                client_id=client_id,
                client_secret=client_secret,
                auth_type=auth_type,
                environment=environment,
            )
            me = client.current_user.me()
            username = me.user_name or me.display_name or "authenticated_user"
            return True, f"Successfully authenticated as '{username}'.", username

        except Exception as exc:
            scrubbed = self.scrub_sensitive(str(exc))
            logger.warning("databricks_connection_test_failed", host=host, error=scrubbed)
            kind = classify_databricks_error(exc)

            if "cannot configure default credentials" in scrubbed.lower():
                guidance = (
                    "No valid credentials found. For Azure Databricks Dev, run 'az login'. "
                    "For production workspaces, provide valid DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET. "
                    "For AWS Databricks, configure the CLI profile with 'databricks auth login --profile <name>'."
                )
            elif "azure cli" in scrubbed.lower() and (
                "login" in scrubbed.lower() or "not installed" in scrubbed.lower()
            ):
                guidance = scrubbed
            elif kind == "permission_denied":
                if "inaccessible" in scrubbed.lower() or "access_denied" in scrubbed.lower():
                    guidance = (
                        "Permission denied: Caller is not assigned to this workspace or lacks access "
                        f"({scrubbed})."
                    )
                else:
                    guidance = f"Permission denied: caller lacks workspace access or required admin roles ({scrubbed})."
            elif kind == "auth_failed":
                guidance = f"Service Principal / credential authentication failed: {scrubbed}"
            else:
                guidance = f"Workspace connection unavailable: {scrubbed}"

            return False, guidance, None
