"""WorkloadProfile domain schemas with financial precision and validation."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cloud_recommender.schemas.common import ComplianceStandard, WorkloadCategory


class WorkloadProfileBase(BaseModel):
    """Base workload specifications common to creation and reading."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the application or workload project.",
        examples=["Healthcare Imaging Service"],
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Detailed functional overview or requirements narrative.",
    )
    category: WorkloadCategory = Field(
        default=WorkloadCategory.WEB_APP,
        description="Primary architectural classification of the workload.",
    )

    # Traffic and throughput (optional until extracted or provided)
    target_traffic_rps: int | None = Field(
        default=None,
        ge=1,
        description="Expected average requests per second at steady state.",
    )
    monthly_active_users: int | None = Field(
        default=None,
        ge=0,
        description="Projected monthly active user count.",
    )
    peak_multiplier: Annotated[Decimal, Field(max_digits=5, decimal_places=2)] | None = Field(
        default=None,
        ge=Decimal("1.0"),
        le=Decimal("50.0"),
        description="Ratio of peak traffic to average traffic.",
    )

    # Availability and resilience
    target_sla_percentage: Annotated[Decimal, Field(max_digits=5, decimal_places=3)] | None = Field(
        default=None,
        ge=Decimal("90.0"),
        le=Decimal("99.999"),
        description="Target availability service level agreement (e.g. 99.9%).",
    )
    high_availability: bool = Field(
        default=True,
        description="Require multi-availability-zone redundancy.",
    )
    multi_region: bool = Field(
        default=False,
        description="Require active-passive or active-active multi-region deployment.",
    )
    rpo_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Recovery Point Objective in minutes.",
    )
    rto_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Recovery Time Objective in minutes.",
    )

    # Security and compliance
    compliance_frameworks: list[ComplianceStandard] = Field(
        default_factory=list,
        description="Regulatory frameworks the workload must strictly adhere to.",
    )
    data_classification: str | None = Field(
        default=None,
        max_length=100,
        description="Sensitivity tier (e.g. 'Public', 'Confidential', 'Restricted/PII').",
    )

    # Storage and data transfer
    storage_volume_gb: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None = Field(
        default=None,
        ge=Decimal("0.0"),
        description="Expected primary persistent storage volume in Gigabytes.",
    )
    monthly_data_egress_gb: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None = (
        Field(
            default=None,
            ge=Decimal("0.0"),
            description="Expected outbound internet data transfer in Gigabytes per month.",
        )
    )
    database_type: str | None = Field(
        default=None,
        max_length=50,
        description="Preferred persistence engine category ('relational', 'document', 'cache').",
    )

    # Target geographic regions
    primary_region: str | None = Field(
        default=None,
        max_length=100,
        description="Target primary cloud region (e.g. 'eastus', 'us-east-1').",
    )
    target_regions: list[str] = Field(
        default_factory=list,
        description="Secondary deployment regions for failover or edge distribution.",
    )

    # Financial and estimation assumptions
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="Three-letter ISO 4217 currency code for estimations.",
    )
    max_monthly_budget: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None = Field(
        default=None,
        ge=Decimal("0.0"),
        description="Hard monthly budget ceiling in specified currency.",
    )
    cost_buffer_percentage: Annotated[Decimal, Field(max_digits=5, decimal_places=2)] = Field(
        default=Decimal("15.00"),
        ge=Decimal("0.0"),
        le=Decimal("100.0"),
        description="Standard FinOps safety buffer applied to baseline estimation.",
    )
    estimation_assumptions: dict[str, str] = Field(
        default_factory=dict,
        description="Key-value assumptions documented during requirements gathering.",
    )

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        return v.upper()


class WorkloadProfileCreate(WorkloadProfileBase):
    """Payload schema for creating a new workload profile."""

    pass


class WorkloadProfileUpdate(BaseModel):
    """Payload schema for updating an existing workload profile incrementally."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category: WorkloadCategory | None = None
    target_traffic_rps: int | None = None
    monthly_active_users: int | None = None
    peak_multiplier: Decimal | None = None
    target_sla_percentage: Decimal | None = None
    high_availability: bool | None = None
    multi_region: bool | None = None
    rpo_minutes: int | None = None
    rto_minutes: int | None = None
    compliance_frameworks: list[ComplianceStandard] | None = None
    data_classification: str | None = None
    storage_volume_gb: Decimal | None = None
    monthly_data_egress_gb: Decimal | None = None
    database_type: str | None = None
    primary_region: str | None = None
    target_regions: list[str] | None = None
    currency: str | None = None
    max_monthly_budget: Decimal | None = None
    cost_buffer_percentage: Decimal | None = None
    estimation_assumptions: dict[str, str] | None = None


class WorkloadProfile(WorkloadProfileBase):
    """Complete WorkloadProfile entity representation with stable UUID and timestamps."""

    id: UUID = Field(
        default_factory=uuid4,
        description="Globally unique stable identifier for this workload profile.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the workload profile was recorded.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the most recent profile modification.",
    )

    model_config = ConfigDict(from_attributes=True)
