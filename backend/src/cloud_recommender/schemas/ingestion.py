"""Domain schemas for scope-aware ingestion, readiness validation, and version lineage.

Governs server-side scope enforcement, ingestion run tracking, and Databricks workspace integration.
Strict human approval and zero-mutation policies apply.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IngestionReadinessState(StrEnum):
    """Ingestion readiness states."""

    READY = "ready"
    NOT_CONFIGURED = "not_configured"
    NO_RESOURCES_SELECTED = "no_resources_selected"
    CONNECTION_ERROR = "connection_error"
    PERMISSION_DENIED = "permission_denied"
    CONFIGURATION_INVALID = "configuration_invalid"


class IngestionRunStatus(StrEnum):
    """Lifecycle status of an ingestion run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


class ResourceIngestionStatus(StrEnum):
    """Per-resource ingestion outcome."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class IngestionScope(BaseModel):
    """Calculated effective ingestion scope for a run."""

    model_config = ConfigDict(frozen=True)

    connection_id: str = Field(..., description="Cloud connection identifier")
    provider: str = Field(..., description="Cloud provider (azure, gcp, aws)")
    configuration_id: UUID = Field(..., description="Active configuration revision ID")
    configuration_version: int = Field(..., description="Active configuration revision number")
    effective_resource_ids: list[str] = Field(
        default_factory=list, description="Explicitly resolved resource IDs to ingest"
    )
    effective_workspace_ids: list[str] = Field(
        default_factory=list, description="Resolved Databricks workspace ARM IDs"
    )
    subscriptions: list[str] = Field(
        default_factory=list, description="Subscriptions in effective scope"
    )
    resource_groups: list[str] = Field(
        default_factory=list, description="Resource groups in effective scope"
    )


class IngestionReadinessResponse(BaseModel):
    """Readiness validation response before starting an ingestion run."""

    model_config = ConfigDict(from_attributes=True)

    connection_id: str
    provider: str
    readiness_state: IngestionReadinessState
    can_start_ingestion: bool = Field(..., description="True if readiness_state is strictly READY")
    has_configuration: bool = False
    configuration_id: UUID | None = None
    configuration_version: int | None = None
    selected_resource_count: int = 0
    selected_workspace_count: int = 0
    effective_resource_ids: list[str] = Field(default_factory=list)
    effective_workspace_ids: list[str] = Field(default_factory=list)
    details: str = Field(..., description="Actionable explanation of the readiness state")
    missing_requirements: list[str] = Field(
        default_factory=list, description="Actionable list of missing requirements or permissions"
    )
    checked_at: datetime


class IngestionRunCreate(BaseModel):
    """Payload to trigger an ingestion run."""

    force_resync: bool = Field(
        default=False, description="Whether to re-extract without cached telemetry"
    )
    triggered_by: str = Field(default="user", description="Trigger source: user, schedule, or api")


class IngestionResourceStatusResponse(BaseModel):
    """Per-resource execution record within an ingestion run."""

    model_config = ConfigDict(from_attributes=True)

    resource_id: str
    resource_type: str | None = None
    region: str | None = None
    status: ResourceIngestionStatus
    inventory_extracted: bool = False
    cost_extracted: bool = False
    metrics_extracted: bool = False
    error_message: str | None = None
    extracted_records_count: int = 0


class IngestionRunResponse(BaseModel):
    """Detailed response for an ingestion run."""

    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    connection_id: str
    provider: str
    configuration_id: UUID
    configuration_version: int
    status: IngestionRunStatus
    triggered_by: str
    started_at: datetime
    completed_at: datetime | None = None
    total_resources_scoped: int
    successful_resources_count: int = 0
    failed_resources_count: int = 0
    error_message: str | None = None
    scope_snapshot: dict[str, Any] = Field(
        default_factory=dict, description="Captured scope IDs and workspace IDs"
    )
    resource_statuses: list[IngestionResourceStatusResponse] = Field(
        default_factory=list, description="Per-resource execution records"
    )


class IngestionRunSummaryResponse(BaseModel):
    """Lightweight summary of an ingestion run for listing views."""

    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    connection_id: str
    provider: str
    configuration_version: int
    status: IngestionRunStatus
    triggered_by: str
    started_at: datetime
    completed_at: datetime | None = None
    total_resources_scoped: int
    successful_resources_count: int
    failed_resources_count: int
    error_message: str | None = None
