"""Domain schemas and API contracts for GCP Service Account authentication, connectivity, and discovery.

Strict Security Invariants:
1. Service Account private keys and generated access tokens are NEVER exposed in response models.
2. Only safe identifiers (project_id, client_email, private_key_id) are serialized to clients.
3. Billing is explicitly DEFERRED / NOT_CONFIGURED (zero-spend calculation is never hallucinated).
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GcpServiceConnectivityState(StrEnum):
    """Independent connectivity status for each Google Cloud service."""

    SUCCESS = "SUCCESS"
    API_DISABLED = "API_DISABLED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DEFERRED = "DEFERRED"
    NOT_TESTED = "NOT_TESTED"


class GcpServiceStatus(BaseModel):
    """Granular connectivity and permission report for a specific GCP service API."""

    model_config = ConfigDict(frozen=True)

    service: str = Field(
        ...,
        description=(
            "Service identifier: cloud_resource_manager | cloud_asset_inventory | "
            "cloud_storage | cloud_sql | compute_engine | cloud_monitoring | "
            "cloud_recommender | service_usage"
        ),
    )
    service_name: str = Field(..., description="Human-readable service title.")
    status: GcpServiceConnectivityState = Field(
        ..., description="Standardized connectivity/permission state."
    )
    api_endpoint: str = Field(..., description="Target API endpoint or hostname.")
    required_role_or_permission: str | None = Field(
        default=None, description="Recommended IAM role or permission needed for access."
    )
    message: str | None = Field(
        default=None, description="Actionable explanation or diagnostic message."
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Safe operational metadata (counts, versions, etc.)."
    )


class GcpServiceAccountInfo(BaseModel):
    """Non-sensitive metadata extracted from a validated GCP Service Account JSON."""

    model_config = ConfigDict(frozen=True)

    project_id: str = Field(..., description="GCP Project ID associated with the Service Account.")
    client_email: str = Field(..., description="Service Account email address.")
    private_key_id: str = Field(..., description="Unique Key ID of the private key pair.")
    client_id: str | None = Field(
        default=None, description="Unique OAuth2 Client ID of the principal."
    )
    auth_uri: str | None = Field(default=None, description="Google OAuth2 authorization URI.")
    token_uri: str = Field(
        default="https://oauth2.googleapis.com/token",
        description="Google OAuth2 token endpoint URI.",
    )


class GcpTestConnectionRequest(BaseModel):
    """Request payload for testing GCP connectivity WITHOUT persisting credentials."""

    connection_name: str = Field(
        default="GCP Production",
        min_length=2,
        max_length=100,
        description="Friendly connection label.",
    )
    project_id: str = Field(
        ...,
        min_length=4,
        max_length=63,
        description="GCP Project ID to validate.",
    )
    service_account_json: str = Field(
        ...,
        min_length=50,
        description="Raw JSON string of the Service Account keyfile.",
    )


class GcpTestConnectionResponse(BaseModel):
    """Safe response from connection test with granular per-service statuses."""

    success: bool = Field(..., description="True if authentication and project access succeeded.")
    project_id: str = Field(..., description="Target GCP Project ID.")
    client_email: str = Field(..., description="Authenticated Service Account email.")
    private_key_id: str = Field(..., description="Key ID of authenticated credentials.")
    overall_status: str = Field(
        ...,
        description="Connected | Partially Connected | Authentication Failed | Permission Denied",
    )
    billing_status: Literal["DEFERRED", "NOT_CONFIGURED"] = Field(
        default="DEFERRED",
        description="Billing is explicitly deferred in this phase (no live billing account).",
    )
    services: list[GcpServiceStatus] = Field(
        default_factory=list,
        description="Independent connectivity check result for each tested GCP service.",
    )
    tested_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of connectivity test.",
    )
    error_summary: str | None = Field(
        default=None,
        description="Summary of errors if authentication or validation failed.",
    )


class GcpCreateConnectionRequest(BaseModel):
    """Request payload to validate, encrypt, and save a persistent GCP connection."""

    name: str = Field(..., min_length=2, max_length=100, description="Connection friendly name.")
    project_id: str = Field(..., min_length=4, max_length=63, description="Target GCP Project ID.")
    service_account_json: str = Field(
        ...,
        min_length=50,
        description="Service account JSON key file content to be encrypted at rest.",
    )


class GcpConnectionResponse(BaseModel):
    """Safe metadata representation of a persisted GCP connection (zero secrets)."""

    id: str = Field(..., description="Unique connection GUID.")
    name: str = Field(..., description="Connection name.")
    provider: Literal["gcp"] = Field(default="gcp", description="Cloud provider identifier.")
    project_id: str = Field(..., description="Configured GCP Project ID.")
    client_email: str = Field(..., description="Authenticated Service Account principal.")
    private_key_id: str = Field(..., description="Service Account private key ID.")
    status: str = Field(
        ...,
        description="Current status: connected | partially_connected | auth_failed | permission_denied.",
    )
    billing_status: str = Field(
        default="DEFERRED",
        description="Billing status: DEFERRED (no live billing configured).",
    )
    ownership: Literal["owned", "organization"] = Field(
        default="owned", description="Ownership classification."
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp."
    )
    last_verified_at: datetime | None = Field(
        default=None, description="Timestamp of latest verification check."
    )
    services: list[GcpServiceStatus] = Field(
        default_factory=list, description="Per-service connectivity reports."
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking warnings (e.g. disabled APIs)."
    )


class GcpProjectMetadata(BaseModel):
    """GCP Project metadata discovered via Cloud Resource Manager."""

    project_id: str
    project_name: str | None = None
    project_number: str | None = None
    project_state: str | None = None
    parent_type: str | None = None
    parent_id: str | None = None


class GcpResourceItem(BaseModel):
    """Single discovered cloud resource across Cloud Asset Inventory, Storage, SQL, Compute, etc."""

    resource_id: str = Field(..., description="Full resource identifier or URL.")
    resource_name: str = Field(..., description="Short name of resource.")
    resource_type: str = Field(..., description="Standard GCP asset type.")
    project_id: str = Field(..., description="GCP Project ID.")
    location: str | None = Field(default=None, description="Region, zone, or global.")
    creation_time: str | None = Field(
        default=None, description="Creation timestamp when available."
    )
    state: str | None = Field(default=None, description="Resource lifecycle state.")
    labels: dict[str, str] = Field(default_factory=dict, description="Resource labels/tags.")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Service-specific non-secret configuration details."
    )


class GcpRecommenderItem(BaseModel):
    """Optimization recommendation from Cloud Recommender API."""

    recommendation_id: str
    category: str
    resource_id: str
    description: str
    state: str = "ACTIVE"
    estimated_impact: dict[str, Any] = Field(default_factory=dict)


class GcpMonitoringSummary(BaseModel):
    """Cloud Monitoring discovery summary."""

    available_monitored_resources: list[str] = Field(default_factory=list)
    metric_descriptors_count: int = 0
    active_time_series_count: int = 0
    message: str | None = None


class GcpDiscoveryResponse(BaseModel):
    """Comprehensive resource discovery result across all supported GCP services."""

    project_id: str
    project_metadata: GcpProjectMetadata | None = None
    total_resources: int = 0
    resources: list[GcpResourceItem] = Field(default_factory=list)
    recommendations: list[GcpRecommenderItem] = Field(default_factory=list)
    monitoring: GcpMonitoringSummary | None = None
    services_status: list[GcpServiceStatus] = Field(default_factory=list)
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    partial_discovery: bool = False
    discovery_notes: list[str] = Field(default_factory=list)
