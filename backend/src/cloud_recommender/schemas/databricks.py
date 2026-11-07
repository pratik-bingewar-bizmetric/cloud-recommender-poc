"""Pydantic domain schemas for multi-workspace Databricks connectivity and discovery."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DatabricksCloud(StrEnum):
    """Underlying cloud provider hosting the Databricks workspace."""

    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"


class CategoryDiscoveryStatus(StrEnum):
    """Permission and availability status for an individual discovery category."""

    AVAILABLE = "available"
    PERMISSION_DENIED = "permission_denied"
    UNSUPPORTED = "unsupported"
    NO_RESOURCES_FOUND = "no_resources_found"
    CONNECTION_ERROR = "connection_error"
    NOT_YET_DISCOVERED = "not_yet_discovered"


class DatabricksConnectionStatus(StrEnum):
    """Connection authentication and health state."""

    READY_TO_CONNECT = "ready_to_connect"
    CONNECTED = "connected"
    AUTH_FAILED = "auth_failed"
    PERMISSION_DENIED = "permission_denied"
    CONNECTION_ERROR = "connection_error"


class DatabricksConnectionResponse(BaseModel):
    """Public representation of a registered Databricks workspace connection."""

    connection_id: str = Field(
        description="Unique connection identifier (e.g. databricks-azure-dev)"
    )
    workspace_id: str = Field(description="Databricks workspace ID")
    workspace_name: str = Field(description="Human-readable workspace name")
    workspace_url: str = Field(description="Canonical Databricks workspace URL")
    cloud: DatabricksCloud = Field(description="Host cloud provider: azure or aws")
    region: str | None = Field(default=None, description="Cloud region if discoverable")
    auth_method: str = Field(
        description="Authentication method reference (e.g. azure-cli, cli-profile, oauth-sp)"
    )
    profile_name: str | None = Field(default=None, description="Local CLI profile reference name")
    status: DatabricksConnectionStatus = Field(description="Current verified connection status")
    last_connected_at: datetime | None = Field(
        default=None, description="Timestamp of last verified connection"
    )
    last_error: str | None = Field(
        default=None, description="Last recorded connection or auth error message"
    )
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Record last updated timestamp")


class CategoryDiscoveryResult(BaseModel):
    """Granular discovery outcome for a single category."""

    category: str = Field(description="Category name (e.g. clusters, warehouses, jobs)")
    status: CategoryDiscoveryStatus = Field(description="Category discovery status")
    resource_count: int = Field(default=0, description="Count of discovered resources")
    error_message: str | None = Field(
        default=None, description="Error or permission-denied reason if not available"
    )
    discovered_at: datetime | None = Field(
        default=None, description="Timestamp when category was queried"
    )


class DiscoveredResourceItem(BaseModel):
    """Normalized discovered resource entity across all categories."""

    id: str = Field(description="Resource unique ID")
    name: str = Field(description="Resource display name")
    resource_type: str = Field(
        description="Resource type (cluster, warehouse, job, pipeline, app, catalog)"
    )
    workspace_id: str = Field(description="Owning workspace ID")
    status: str | None = Field(
        default=None, description="Current runtime status (RUNNING, STOPPED, etc.)"
    )
    creator: str | None = Field(default=None, description="Creator or owner principal")
    source_api: str = Field(description="Originating Databricks SDK API endpoint")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Normalized source properties"
    )
    discovered_at: datetime = Field(description="Timestamp of extraction")


class DatabricksWorkspaceDiscoveryResponse(BaseModel):
    """Complete discovery payload for a Databricks workspace."""

    connection_id: str
    workspace_id: str
    workspace_name: str
    workspace_url: str
    cloud: DatabricksCloud
    overall_status: str = Field(description="completed, partial_failure, or failed")
    categories: dict[str, CategoryDiscoveryResult] = Field(
        description="Per-category status breakdown"
    )
    resources: list[DiscoveredResourceItem] = Field(
        default_factory=list, description="All discovered resources"
    )
    total_resources_count: int = Field(default=0)
    discovered_at: datetime


class DatabricksConnectionTestResponse(BaseModel):
    """Response returned when probing connection health."""

    connection_id: str
    workspace_id: str
    workspace_url: str
    success: bool
    status: DatabricksConnectionStatus
    current_user: str | None = Field(
        default=None, description="Caller identity returned by Databricks"
    )
    details: str
    tested_at: datetime


class DatabricksConnectionHealthResponse(BaseModel):
    """Detailed health, permissions, and discovery summary for a connection."""

    connection_id: str
    workspace_id: str
    cloud: DatabricksCloud
    status: DatabricksConnectionStatus
    authenticated_user: str | None = None
    last_verified_at: datetime | None = None
    categories_summary: dict[str, CategoryDiscoveryStatus] = Field(default_factory=dict)
    resource_counts_by_type: dict[str, int] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
