"""Databricks authentication service using official Databricks SDK.

Supports:
- Local development through supported Databricks CLI profile authentication.
- Azure CLI native authentication for Azure Databricks workspaces.
- Production authentication through OAuth service-principal credentials via environment variables.
- Connection validation and detailed error handling without credential leakage.
"""

import os

import structlog
from databricks.sdk import WorkspaceClient

logger = structlog.get_logger(__name__)


class DatabricksAuthError(Exception):
    """Raised when Databricks authentication or connection fails."""

    def __init__(self, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(message)
        self.raw_error = raw_error


class DatabricksAuthService:
    """Service resolving authenticated Databricks WorkspaceClient instances."""

    @staticmethod
    def scrub_sensitive(text: str) -> str:
        """Ensure tokens, secret keys, or passwords are never exposed in logs or API errors."""
        if not text:
            return ""
        # Redact common token patterns
        scrubbed = str(text)
        for env_key in (
            "DATABRICKS_TOKEN",
            "DATABRICKS_CLIENT_SECRET",
            "ARM_CLIENT_SECRET",
            "AZURE_CLIENT_SECRET",
        ):
            secret = os.environ.get(env_key, "").strip()
            if secret and len(secret) >= 4 and secret in scrubbed:
                scrubbed = scrubbed.replace(secret, "[REDACTED_SECRET]")
        return scrubbed

    def create_workspace_client(
        self,
        host: str,
        cloud: str = "azure",
        profile: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> WorkspaceClient:
        """Instantiate an official Databricks WorkspaceClient using the appropriate strategy.

        Strategy hierarchy:
        1. Production OAuth SP: explicit client_id & client_secret or environment variables.
        2. Azure CLI Auth: for Azure Databricks workspaces when Azure CLI session is available.
        3. Databricks CLI Profile: profile specified and configured in ~/.databrickscfg.
        4. Unified default auth: fallback to Databricks SDK ambient resolution.
        """
        host_clean = host.strip().rstrip("/")

        # Strategy 1: Explicit OAuth Service Principal (Production)
        sp_id = client_id or os.environ.get("DATABRICKS_CLIENT_ID")
        sp_secret = client_secret or os.environ.get("DATABRICKS_CLIENT_SECRET")
        if sp_id and sp_secret:
            logger.info("databricks_auth_using_oauth_sp", host=host_clean)
            return WorkspaceClient(
                host=host_clean,
                client_id=sp_id.strip(),
                client_secret=sp_secret.strip(),
            )

        # Strategy 2: Azure CLI Auth (Azure Databricks workspaces)
        if cloud.lower() == "azure" or "azuredatabricks.net" in host_clean:
            try:
                logger.info("databricks_auth_attempting_azure_cli", host=host_clean)
                return WorkspaceClient(host=host_clean, auth_type="azure-cli")
            except Exception as exc:
                logger.debug("databricks_azure_cli_init_fallback", error=str(exc))

        # Strategy 3: Databricks CLI Profile
        if profile:
            try:
                logger.info("databricks_auth_using_profile", host=host_clean, profile=profile)
                return WorkspaceClient(host=host_clean, profile=profile.strip())
            except Exception as exc:
                logger.debug("databricks_profile_init_fallback", profile=profile, error=str(exc))

        # Strategy 4: Default Unified Auth
        logger.info("databricks_auth_using_default_config", host=host_clean)
        return WorkspaceClient(host=host_clean)

    def test_connection(
        self,
        host: str,
        cloud: str = "azure",
        profile: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
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
            )
            me = client.current_user.me()
            username = me.user_name or me.display_name or "authenticated_user"
            return True, f"Successfully authenticated as '{username}'.", username

        except Exception as exc:
            scrubbed = self.scrub_sensitive(str(exc))
            logger.warning("databricks_connection_test_failed", host=host, error=scrubbed)

            if "cannot configure default credentials" in scrubbed.lower():
                guidance = (
                    "No valid credentials found. For Azure Databricks, run 'az login' or provide "
                    "DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET. For AWS Databricks, configure "
                    "the CLI profile with 'databricks auth login --profile <name>'."
                )
            elif "403" in scrubbed or "permission" in scrubbed.lower():
                guidance = (
                    "Permission denied: caller lacks workspace access or required admin roles."
                )
            else:
                guidance = scrubbed

            return False, guidance, None
