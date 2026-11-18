"""Pydantic domain schemas for multi-workspace Databricks connectivity and discovery."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DatabricksCloud(StrEnum):
    """Underlying cloud provider hosting the Databricks workspace."""

    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"


class DatabricksResourceState(StrEnum):
    """Canonical M2 resource-category discovery state."""

    LIVE = "LIVE"
    NO_DATA = "NO_DATA"
    ACCESS_DENIED = "ACCESS_DENIED"
    AUTH_FAILED = "AUTH_FAILED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    PARTIAL = "PARTIAL"


class CategoryDiscoveryStatus(StrEnum):
    """Permission and availability status for an individual discovery category."""

    AVAILABLE = "available"
    PERMISSION_DENIED = "permission_denied"
    AUTH_FAILED = "auth_failed"
    UNSUPPORTED = "unsupported"
    NO_RESOURCES_FOUND = "no_resources_found"
    CONNECTION_ERROR = "connection_error"
    NOT_YET_DISCOVERED = "not_yet_discovered"


_STATUS_TO_RESOURCE_STATE: dict[CategoryDiscoveryStatus, DatabricksResourceState] = {
    CategoryDiscoveryStatus.AVAILABLE: DatabricksResourceState.LIVE,
    CategoryDiscoveryStatus.NO_RESOURCES_FOUND: DatabricksResourceState.NO_DATA,
    CategoryDiscoveryStatus.PERMISSION_DENIED: DatabricksResourceState.ACCESS_DENIED,
    CategoryDiscoveryStatus.AUTH_FAILED: DatabricksResourceState.AUTH_FAILED,
    CategoryDiscoveryStatus.UNSUPPORTED: DatabricksResourceState.NOT_SUPPORTED,
    CategoryDiscoveryStatus.CONNECTION_ERROR: DatabricksResourceState.UNAVAILABLE,
    CategoryDiscoveryStatus.NOT_YET_DISCOVERED: DatabricksResourceState.UNAVAILABLE,
}


class DatabricksConnectionStatus(StrEnum):
    """Connection authentication and health state."""

    READY_TO_CONNECT = "ready_to_connect"
    CONNECTED = "connected"
    AUTH_FAILED = "auth_failed"
    PERMISSION_DENIED = "permission_denied"
    CONNECTION_ERROR = "connection_error"


class WorkspaceConnectionState(StrEnum):
    """Single normalized workspace REST connectivity state used by every UI surface.

    Independent of SQL warehouse availability: a stopped warehouse never changes it.
    """

    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    ERROR = "ERROR"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class SqlWarehouseStatus(BaseModel):
    """SQL warehouse availability, reported separately from workspace connectivity."""

    warehouse_id: str | None = None
    warehouse_name: str | None = None
    state: str | None = Field(default=None, description="Warehouse state from the REST API")
    sql_available: bool = Field(
        default=False, description="True only when the warehouse is RUNNING (SQL may execute)"
    )
    message: str = ""


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
    warehouse_id: str | None = Field(
        default=None, description="Configured SQL Warehouse ID for this workspace"
    )
    environment: str | None = Field(
        default=None, description="Workspace environment classification (development, production)"
    )
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
    discovery_state: DatabricksResourceState | None = Field(
        default=None,
        description="Normalized M2 category state: LIVE, NO_DATA, ACCESS_DENIED, AUTH_FAILED, UNAVAILABLE, NOT_SUPPORTED",
    )
    resource_count: int = Field(default=0, description="Count of discovered resources")
    workspace_id: str | None = Field(default=None, description="Owning workspace ID")
    source_api: str | None = Field(default=None, description="Databricks SDK/REST API invoked")
    http_status: int | None = Field(default=None, description="HTTP status code when applicable")
    error_code: str | None = Field(default=None, description="Structured error classification code")
    error_message: str | None = Field(
        default=None, description="Error or permission-denied reason if not available"
    )
    empty_confirmed: bool | None = Field(
        default=None,
        description="True only when API response contract confirms zero records exist",
    )
    has_more: bool = Field(default=False, description="Whether additional pages exist")
    next_page_token: str | None = Field(default=None, description="Pagination cursor token")
    discovered_at: datetime | None = Field(
        default=None, description="Timestamp when category was queried"
    )

    @model_validator(mode="after")
    def _populate_discovery_state(self) -> "CategoryDiscoveryResult":
        if self.discovery_state is None:
            self.discovery_state = _STATUS_TO_RESOURCE_STATE.get(
                self.status, DatabricksResourceState.UNAVAILABLE
            )
        return self


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
    environment: str | None = None
    overall_status: str = Field(description="completed, partial_failure, or failed")
    data_status: DatabricksResourceState | None = None
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
    auth_method: str | None = None
    last_error: str | None = None
    last_verified_at: datetime | None = None
    connection_state: WorkspaceConnectionState = WorkspaceConnectionState.DISCONNECTED
    workspace_name: str | None = None
    workspace_url: str | None = None
    environment: str | None = None
    last_connected_at: datetime | None = None
    last_discovery_at: datetime | None = Field(
        default=None, description="When the cached inventory was last retrieved successfully"
    )
    last_discovery_attempt_at: datetime | None = None
    discovery_stale: bool = Field(
        default=False,
        description="True when the latest refresh failed or the cache is older than 3 intervals",
    )
    refresh_interval_seconds: int = 60
    sql_warehouse: SqlWarehouseStatus | None = None
    categories_summary: dict[str, CategoryDiscoveryStatus] = Field(default_factory=dict)
    resource_counts_by_type: dict[str, int] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DatabricksCategoryPageResponse(BaseModel):
    """Paginated response for a single Databricks discovery category."""

    connection_id: str
    workspace_id: str
    workspace_name: str
    workspace_url: str
    environment: str | None = None
    category: str
    status: CategoryDiscoveryStatus
    discovery_state: DatabricksResourceState
    data_status: DatabricksResourceState | None = None
    source_api: str
    retrieved_at: datetime
    items: list[DiscoveredResourceItem] = Field(default_factory=list)
    total_returned: int = 0
    has_more: bool = False
    next_page_token: str | None = None
    empty_confirmed: bool | None = None
    http_status: int | None = None
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def _sync_data_status(self) -> "DatabricksCategoryPageResponse":
        if self.data_status is None:
            self.data_status = self.discovery_state
        return self


class UnityCatalogColumnItem(BaseModel):
    """Column metadata from Unity Catalog Tables API."""

    name: str
    type_text: str = "STRING"
    type_name: str | None = None
    nullable: bool = True
    comment: str | None = None


class UnityCatalogPermissionItem(BaseModel):
    """Effective privilege grant metadata from Unity Catalog Grants API."""

    principal: str
    privileges: list[str] = Field(default_factory=list)
    inherited_from_type: str | None = None
    inherited_from_name: str | None = None


class UnityCatalogTableItem(BaseModel):
    """Table metadata and optional column/permission metadata."""

    catalog_name: str
    schema_name: str
    name: str
    full_name: str
    table_type: str | None = None
    data_source_format: str | None = None
    owner: str | None = None
    storage_location: str | None = None
    comment: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    properties: dict[str, str] = Field(default_factory=dict)
    columns: list[UnityCatalogColumnItem] = Field(default_factory=list)
    permissions: list[UnityCatalogPermissionItem] = Field(default_factory=list)
    permissions_status: DatabricksResourceState = DatabricksResourceState.UNAVAILABLE
    permissions_error: str | None = None


class UnityCatalogSchemaItem(BaseModel):
    """Unity Catalog schema with discovered tables."""

    catalog_name: str
    name: str
    full_name: str
    owner: str | None = None
    comment: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    tables: list[UnityCatalogTableItem] = Field(default_factory=list)
    tables_status: DatabricksResourceState = DatabricksResourceState.UNAVAILABLE
    tables_error: str | None = None


class UnityCatalogCatalogItem(BaseModel):
    """Unity Catalog catalog with discovered schemas."""

    name: str
    owner: str | None = None
    comment: str | None = None
    catalog_type: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    schemas: list[UnityCatalogSchemaItem] = Field(default_factory=list)
    schemas_status: DatabricksResourceState = DatabricksResourceState.UNAVAILABLE
    schemas_error: str | None = None


class UnityCatalogMetadataResponse(BaseModel):
    """Live Unity Catalog hierarchy response (Catalogs -> Schemas -> Tables & Permissions)."""

    connection_id: str
    workspace_id: str
    workspace_name: str | None = None
    workspace_url: str
    environment: str | None = None
    status: CategoryDiscoveryStatus
    discovery_state: DatabricksResourceState
    data_status: DatabricksResourceState | None = None
    source_api: str = "databricks-sdk/catalogs,schemas,tables,grants"
    retrieved_at: datetime
    catalogs: list[UnityCatalogCatalogItem] = Field(default_factory=list)
    total_catalogs: int = 0
    total_schemas: int = 0
    total_tables: int = 0
    has_more: bool = False
    next_page_token: str | None = None
    http_status: int | None = None
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def _sync_data_status(self) -> "UnityCatalogMetadataResponse":
        if self.data_status is None:
            self.data_status = self.discovery_state
        return self


class TypedSystemTableRegistryEntry(BaseModel):
    """Typed registry entry preparing M3 billing ingestion from discovered UC system tables."""

    full_name: str
    domain: str
    exists: bool
    metadata_status: DatabricksResourceState
    select_grant_verified: bool | None = None
    column_types: dict[str, str] = Field(default_factory=dict)
    warehouse_id: str | None = None


class LiveSystemTableItem(BaseModel):
    """Discovered System Table metadata via Unity Catalog REST APIs (zero SQL)."""

    schema_name: str
    table_name: str
    full_name: str
    domain: str | None = None
    table_type: str | None = None
    data_source_format: str | None = None
    owner: str | None = None
    comment: str | None = None
    columns_count: int = 0
    columns: list[UnityCatalogColumnItem] = Field(default_factory=list)
    effective_privileges: list[str] = Field(default_factory=list)
    schema_discovered: bool = False
    table_discovered: bool = False
    metadata_status: DatabricksResourceState = DatabricksResourceState.UNAVAILABLE
    select_grant_verified: bool | None = None
    note: str = ""


class SystemTablesMetadataResponse(BaseModel):
    """Read-only System Tables metadata discovery response (no SQL execution)."""

    connection_id: str
    workspace_id: str
    workspace_name: str | None = None
    workspace_url: str
    environment: str | None = None
    status: CategoryDiscoveryStatus
    discovery_state: DatabricksResourceState
    data_status: DatabricksResourceState | None = None
    source_api: str = "databricks-sdk/schemas.list+tables.list+grants"
    retrieved_at: datetime
    target_schemas: list[str] = Field(default_factory=list)
    discovered_schemas: list[str] = Field(default_factory=list)
    missing_schemas: list[str] = Field(default_factory=list)
    tables: list[LiveSystemTableItem] = Field(default_factory=list)
    billing_ingestion_ready_tables: list[TypedSystemTableRegistryEntry] = Field(
        default_factory=list
    )
    total_tables: int = 0
    has_more: bool = False
    next_page_token: str | None = None
    http_status: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    sql_executed: bool = False
    compute_started: bool = False

    @model_validator(mode="after")
    def _sync_data_status(self) -> "SystemTablesMetadataResponse":
        if self.data_status is None:
            self.data_status = self.discovery_state
        return self


class LiveQueryHistoryItem(BaseModel):
    """Sanitized read-only query history item from Databricks Query History REST API."""

    query_id: str
    status: str
    warehouse_id: str | None = None
    statement_type: str | None = None
    query_source: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    duration_ms: float | None = None
    rows_produced: int | None = None
    read_bytes: int | None = None
    executed_by_masked: str | None = None
    sql_summary: str
    error_message: str | None = None


class LiveQueryHistoryResponse(BaseModel):
    """Paginated read-only Query History response (zero SQL execution)."""

    connection_id: str
    workspace_id: str
    workspace_name: str | None = None
    workspace_url: str
    environment: str | None = None
    status: CategoryDiscoveryStatus
    discovery_state: DatabricksResourceState
    data_status: DatabricksResourceState | None = None
    source_api: str = "databricks-sdk/query_history.list"
    retrieved_at: datetime
    records: list[LiveQueryHistoryItem] = Field(default_factory=list)
    total_returned: int = 0
    has_next_page: bool = False
    next_page_token: str | None = None
    empty_confirmed: bool | None = None
    http_status: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    sql_executed: bool = False
    compute_started: bool = False

    @model_validator(mode="after")
    def _sync_data_status(self) -> "LiveQueryHistoryResponse":
        if self.data_status is None:
            self.data_status = self.discovery_state
        return self
