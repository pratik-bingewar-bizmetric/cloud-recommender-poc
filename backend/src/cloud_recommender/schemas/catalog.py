"""Normalized multi-cloud service catalog domain schemas supporting Azure, AWS, and GCP."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cloud_recommender.schemas.common import (
    CatalogRecordStatus,
    CloudProvider,
    ComplianceStandard,
    ServiceCategory,
)


class CatalogServiceBase(BaseModel):
    """Normalized multi-cloud service definition common to all providers."""

    provider: CloudProvider = Field(
        ...,
        description="Hyperscaler hosting this service ('azure', 'aws', 'gcp').",
    )
    service_id: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Provider-native normalized service identifier.",
        examples=["azure-container-apps", "aws-ecs-fargate", "gcp-cloud-run"],
    )
    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Official marketing and display name of the cloud service.",
        examples=["Azure Container Apps", "Amazon ECS on AWS Fargate", "Google Cloud Run"],
    )
    category: ServiceCategory = Field(
        ...,
        description="Architectural domain category.",
    )
    description: str = Field(
        ...,
        max_length=2000,
        description="Functional summary and primary architectural role of the service.",
    )
    supported_regions: list[str] = Field(
        default_factory=list,
        description="Cloud regions where this service is officially generally available.",
        examples=[["eastus", "westeurope"], ["us-east-1", "eu-west-1"]],
    )
    supported_compliance: list[ComplianceStandard] = Field(
        default_factory=list,
        description="Compliance and regulatory certifications verified for this service.",
    )
    sla_percentage: float | None = Field(
        default=None,
        ge=90.0,
        le=100.0,
        description="Documented availability SLA percentage (e.g. 99.95).",
    )
    is_serverless: bool = Field(
        default=False,
        description="Indicates whether the service exhibits serverless scaling characteristics.",
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible provider-specific architectural attributes.",
    )
    pricing_unit: str | None = Field(
        default=None,
        description="Billing unit description (e.g. 'vCPU-second', 'GiB-month', 'execution').",
    )
    measurement_metric: str | None = Field(
        default=None,
        description="Primary cost driver metric (e.g. 'compute_duration', 'capacity').",
    )
    documentation_url: str | None = Field(
        default=None,
        description="Official hyperscaler documentation reference link.",
    )
    pricing_source_type: str = Field(
        default="curated_fixture",
        description="Origin of pricing metadata: 'curated_fixture', 'azure_retail_api', etc.",
    )
    pricing_reference_url: str | None = Field(
        default=None,
        description="Official pricing page or pricing API reference link.",
    )
    dataset_version: str = Field(
        default="1.0.0",
        description="Catalog dataset schema and release version.",
    )
    retrieval_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the catalog record was retrieved or validated.",
    )
    provenance: str = Field(
        default="Curated official cloud architecture documentation fixture",
        description="Detailed provenance and audit trail for this catalog entry.",
    )
    status: CatalogRecordStatus = Field(
        default=CatalogRecordStatus.FIXTURE,
        description="Record verification status: 'verified', 'fixture', 'deprecated'.",
    )


class CatalogService(CatalogServiceBase):
    """Complete catalog service entity with relational persistence metadata."""

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when record was added to catalog.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of last catalog record update.",
    )

    model_config = ConfigDict(from_attributes=True)


class CatalogServiceFilter(BaseModel):
    """Query filters for catalog listing and search."""

    provider: CloudProvider | None = None
    category: ServiceCategory | None = None
    region: str | None = None
    compliance: ComplianceStandard | None = None
    is_serverless: bool | None = None
    search: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class CatalogServiceListResponse(BaseModel):
    """Paginated response containing catalog service entries."""

    items: list[CatalogService]
    total: int = Field(ge=0, description="Total count matching filter criteria.")
    limit: int = Field(ge=1, description="Page size limit applied.")
    offset: int = Field(ge=0, description="Page offset applied.")
