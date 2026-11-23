"""Domain schemas and API contracts for cloud provider connections, authentication discovery, and verification."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr

from cloud_recommender.schemas.common import CloudProvider

ConnectionStatus = Literal[
    "connected",
    "ready_to_connect",
    "connecting",
    "validating_access",
    "discovering_scope",
    "auth_failed",
    "permission_denied",
    "scope_not_found",
    "simulation_fixture",
]


class IntegrationState(StrEnum):
    """State of ONE integration of a connection (authentication success never implies the rest)."""

    CONNECTED = "connected"
    PERMISSION_DENIED = "permission_denied"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"
    DEFERRED = "deferred"
    ERROR = "error"


class IntegrationStatus(BaseModel):
    """Validation result for a single integration (ARM, cost, monitor, Databricks, Fabric)."""

    integration: str = Field(
        ..., description="resource_manager | cost_management | monitor | databricks | fabric"
    )
    state: IntegrationState
    message: str | None = Field(default=None, description="Human-readable explanation.")
    required_permission: str | None = Field(default=None, description="Role/permission to grant.")
    details: dict[str, Any] = Field(default_factory=dict, description="Non-secret facts.")


class CloudConnection(BaseModel):
    """Safe metadata representation of a cloud subscription or project connection.

    Strict security boundary: credentials, tokens, secrets, and private keys MUST NEVER be exposed.
    """

    id: str = Field(..., description="Unique connection identifier.")
    name: str = Field(..., description="Human-readable connection name.")
    provider: CloudProvider = Field(..., description="Target cloud provider (azure or gcp).")
    scope_id: str = Field(..., description="Subscription ID or GCP Project ID.")
    display_name: str = Field(..., description="Display title of the subscription or project.")
    tenant_or_org_id: str | None = Field(
        default=None, description="Azure Tenant ID or GCP Organization/Folder ID."
    )
    auth_method: str = Field(
        ...,
        description="Safe label for authentication mechanism (e.g. azure_cli_session, service_principal, gcp_oauth2).",
    )
    status: ConnectionStatus = Field(
        default="ready_to_connect", description="Current connectivity and validation status."
    )
    last_verified_at: datetime | None = Field(
        default=None, description="UTC timestamp of the most recent successful validation check."
    )
    is_live: bool = Field(
        default=False, description="True if backed by live authenticated provider APIs."
    )
    capabilities: list[str] = Field(
        default_factory=list, description="Telemetry and inventory capabilities enabled."
    )
    access_limitations: list[str] = Field(
        default_factory=list,
        description="Explicit security and permission boundaries (strictly read-only).",
    )
    ownership: Literal["owned", "organization"] = Field(
        default="organization",
        description="'owned' = created by the caller (persistent, encrypted); otherwise organization.",
    )
    integrations: list[IntegrationStatus] = Field(
        default_factory=list, description="Per-integration validation results (owned connections)."
    )
    warnings: list[str] = Field(default_factory=list, description="Non-blocking findings.")


class ValidateConnectionRequest(BaseModel):
    """Payload to validate access and discover scope for an existing or target connection."""

    connection_id: str | None = Field(
        default=None, description="Identifier of configured connection to validate."
    )
    provider: CloudProvider = Field(..., description="Cloud provider to validate.")
    scope_id: str = Field(..., description="Subscription ID or GCP Project ID.")


class ConnectionValidationResponse(BaseModel):
    """Results of a real server-side access and discovery validation."""

    success: bool = Field(..., description="Whether validation succeeded.")
    connection_id: str = Field(..., description="Validated connection ID.")
    provider: CloudProvider = Field(..., description="Target cloud provider.")
    scope_id: str = Field(..., description="Validated subscription or project ID.")
    scope_name: str = Field(..., description="Discovered scope name.")
    status: ConnectionStatus = Field(..., description="Resulting status.")
    details: str = Field(..., description="Actionable explanation or error details.")
    discovered_resource_count: int = Field(
        default=0, description="Total resources discovered during validation probe."
    )
    discovered_resource_groups: list[str] = Field(
        default_factory=list, description="Top resource groups discovered."
    )
    permissions_verified: list[str] = Field(
        default_factory=list, description="List of read-only permissions confirmed."
    )
    is_live: bool = Field(default=False, description="Whether live provider APIs were reached.")
    latency_ms: float = Field(default=0.0, description="Validation probe latency in milliseconds.")
    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Validation UTC timestamp."
    )


class CreateConnectionRequest(BaseModel):
    """Payload for adding a new cloud connection with server-side validation.

    Secrets provided are used strictly for validation and secure backend session handling;
    they are NEVER returned in API responses or persisted to public logs.
    """

    provider: CloudProvider = Field(..., description="Cloud provider (azure or gcp).")
    auth_method: Literal["service_principal", "azure_cli", "managed_identity"] | None = Field(
        default=None,
        description=(
            "Azure authentication method. Defaults to service_principal. azure_cli is local "
            "development only; managed_identity needs an Azure-hosted backend identity. The "
            "method is never switched silently."
        ),
    )
    name: str = Field(..., min_length=2, max_length=100, description="Friendly connection name.")
    scope_id: str = Field(
        ..., min_length=2, max_length=150, description="Subscription ID or GCP Project ID."
    )
    # Azure specific fields
    azure_tenant_id: str | None = Field(default=None, description="Azure Tenant ID (GUID).")
    azure_client_id: str | None = Field(
        default=None, description="App / Service Principal Client ID (GUID)."
    )
    azure_client_secret: SecretStr | None = Field(
        default=None, description="Service Principal client secret (never stored in plaintext)."
    )
    # Optional integrations (non-secret configuration; the Azure credential is reused)
    databricks_workspace_url: str | None = Field(
        default=None,
        description="Azure Databricks workspace URL (https://adb-....azuredatabricks.net).",
    )
    databricks_workspace_id: str | None = Field(
        default=None, description="Databricks workspace ID."
    )
    fabric_workspace_id: str | None = Field(
        default=None, description="Microsoft Fabric workspace GUID."
    )
    # GCP specific fields
    gcp_project_id: str | None = Field(default=None, description="GCP Project identifier.")
    gcp_service_account_json: str | None = Field(
        default=None, description="Service account JSON key content."
    )
    gcp_access_token: str | None = Field(
        default=None, description="Short-lived GCP OAuth2 access token."
    )


class UpdateConnectionRequest(BaseModel):
    """Edit / reconnect / rotate. Omitted fields are unchanged; the owner is never client-supplied."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    azure_client_id: str | None = None
    azure_client_secret: SecretStr | None = Field(
        default=None,
        description="New client secret (credential rotation); revalidated before saving.",
    )
    databricks_workspace_url: str | None = None
    databricks_workspace_id: str | None = None
    fabric_workspace_id: str | None = None
