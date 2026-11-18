"""Pydantic v2 schemas for multi-cloud resource configuration and discovery.

Supports hierarchical resource selection, Databricks workspace discovery,
deterministic selection resolution, and future ingestion boundaries.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ScopeType(StrEnum):
    """Hierarchical scope categories across cloud providers."""

    TENANT = "tenant"
    SUBSCRIPTION = "subscription"
    RESOURCE_GROUP = "resource_group"
    RESOURCE = "resource"
    DATABRICKS_WORKSPACE = "databricks_workspace"
    ORGANIZATION = "organization"
    FOLDER = "folder"
    PROJECT = "project"
    ACCOUNT = "account"


class SelectionState(StrEnum):
    """Selection resolution states for scope items."""

    INCLUDED = "included"
    EXCLUDED = "excluded"
    ALL_CHILDREN = "all_children"


class ScopeDiscoveryNode(BaseModel):
    """Hierarchical node in a discovered cloud resource tree."""

    id: str = Field(
        ..., description="Unique stable node identifier (e.g. ARM resource ID or Project ID)."
    )
    name: str = Field(..., description="Human-readable display name of the node.")
    scope_type: str = Field(
        ...,
        description="Category of scope (subscription, resource_group, resource, databricks_workspace, etc.).",
    )
    scope_identifier: str = Field(
        ..., description="Full provider-native resource or scope identifier."
    )
    parent_scope_identifier: str | None = Field(
        default=None, description="Identifier of the direct parent node in hierarchy."
    )
    resource_type: str | None = Field(
        default=None, description="Provider resource type (e.g. 'Microsoft.Databricks/workspaces')."
    )
    region: str | None = Field(default=None, description="Deployment region or location.")
    is_leaf: bool = Field(default=False, description="Whether this node is a terminal resource.")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific properties (e.g. workspace_url, sku)."
    )
    children: list["ScopeDiscoveryNode"] = Field(
        default_factory=list, description="Child scope nodes."
    )


class ScopeDiscoveryResponse(BaseModel):
    """Multi-cloud discovery payload returning hierarchical resource topology."""

    provider: str = Field(..., description="Target cloud provider ('azure', 'gcp', 'aws').")
    connection_id: str = Field(..., description="Cloud connection ID used for discovery.")
    tenant_or_org_id: str | None = Field(
        default=None, description="Tenant, Organization, or Account ID."
    )
    status: Literal[
        "ready", "permission_denied", "unsupported", "empty", "authentication_required", "error"
    ] = Field(
        default="ready",
        description=(
            "Discovery status code. authentication_required = no valid identity (401 / not logged "
            "in); permission_denied = identity lacks a role (403); error = any other failure."
        ),
    )
    data_source: Literal["live", "demo_fixture", "none"] = Field(
        default="live",
        description=(
            "live = retrieved from the cloud API; demo_fixture = fabricated demo data "
            "(only with ALLOW_DEMO_FIXTURES); none = nothing could be retrieved."
        ),
    )
    status_message: str = Field(
        default="Scope discovery completed successfully.",
        description="Status narrative or diagnostic info.",
    )
    last_discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Timestamp of discovery execution."
    )
    tree: list[ScopeDiscoveryNode] = Field(
        default_factory=list,
        description="Top-level hierarchy nodes (e.g. Subscriptions or Projects).",
    )
    completeness: Literal["COMPLETE", "INCOMPLETE", "UNKNOWN"] = Field(
        default="UNKNOWN",
        description=(
            "COMPLETE only when every paginated read finished; INCOMPLETE when any read stopped "
            "early (see source_errors); UNKNOWN when nothing was read."
        ),
    )
    source_errors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Exact failed reads: endpoint, HTTP status and error text (for access requests).",
    )
    total_discovered_resources: int = Field(
        default=0, description="Total count of discovered resources."
    )
    databricks_workspaces_count: int = Field(
        default=0, description="Total Databricks workspaces discovered."
    )


class ConfiguredScopeItemCreate(BaseModel):
    """Payload to create or persist a configured scope item."""

    scope_type: str = Field(
        ...,
        description="Scope type (subscription, resource_group, resource, databricks_workspace, etc.).",
    )
    scope_identifier: str = Field(
        ..., description="Full resource identifier (ARM ID, GCP asset name, etc.)."
    )
    parent_scope_identifier: str | None = Field(
        default=None, description="Parent resource identifier if nested."
    )
    display_name: str = Field(..., description="Human-readable label for this scope.")
    resource_type: str | None = Field(default=None, description="Resource type classification.")
    region: str | None = Field(default=None, description="Resource location/region.")
    selection_state: Literal["included", "excluded", "all_children"] = Field(
        default="included", description="Selection directive."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Safe metadata (no credentials)."
    )


class ConfiguredScopeItemResponse(BaseModel):
    """Persisted scope item representation."""

    model_config = ConfigDict(from_attributes=True)

    item_id: uuid.UUID
    configuration_id: uuid.UUID
    scope_type: str
    scope_identifier: str
    parent_scope_identifier: str | None = None
    display_name: str
    resource_type: str | None = None
    region: str | None = None
    selection_state: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ResourceConfigurationCreate(BaseModel):
    """Request payload to create or update a resource configuration."""

    connection_id: str = Field(..., description="Target cloud connection identifier.")
    provider: str = Field(default="azure", description="Cloud provider ('azure', 'gcp', 'aws').")
    created_by: str = Field(
        default="system", description="User or service identity creating the configuration."
    )
    scope_items: list[ConfiguredScopeItemCreate] = Field(
        default_factory=list, description="List of scope items and selections to persist."
    )


class ResourceConfigurationResponse(BaseModel):
    """Full persisted resource configuration entity."""

    model_config = ConfigDict(from_attributes=True)

    configuration_id: uuid.UUID
    connection_id: str
    provider: str
    configuration_version: int
    active_status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    scope_items: list[ConfiguredScopeItemResponse] = Field(default_factory=list)
    total_items: int = 0


class EffectiveSelectionResponse(BaseModel):
    """Resolved deterministic resource selection for a connection."""

    configuration_id: uuid.UUID
    connection_id: str
    provider: str
    configuration_version: int
    effective_resource_ids: list[str] = Field(
        default_factory=list, description="Resolved flat list of all selected resource IDs."
    )
    effective_subscriptions: list[str] = Field(
        default_factory=list, description="Resolved list of target subscription IDs."
    )
    effective_resource_groups: list[str] = Field(
        default_factory=list, description="Resolved list of target resource group names/IDs."
    )
    databricks_workspaces: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Detailed metadata for all selected Databricks workspaces.",
    )
    total_selected_resources: int = Field(
        default=0, description="Total count of resolved resources."
    )


class ConfigurationStatusResponse(BaseModel):
    """Ingestion readiness and configuration status for a cloud connection."""

    connection_id: str
    has_configuration: bool
    configuration_id: uuid.UUID | None = None
    configuration_version: int | None = None
    active_status: str | None = None
    selected_resource_count: int = 0
    databricks_workspaces_count: int = 0
    ingestion_readiness: Literal["ready", "not_configured", "no_selection"] = "not_configured"
    updated_at: datetime | None = None
