"""OptimizationAudit domain schemas representing cloud waste and modernization assessments."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from cloud_recommender.schemas.common import AuditApprovalStatus


class AuditScope(BaseModel):
    """The targeted boundary and parameters for an optimization audit."""

    azure_subscription_id: str | None = Field(
        default=None,
        description="Target Azure subscription identifier for read-only telemetry analysis.",
    )
    resource_groups: list[str] = Field(
        default_factory=list,
        description="Specific resource groups evaluated (empty for entire subscription).",
    )
    metric_window_days: int = Field(
        default=30,
        ge=7,
        le=90,
        description="Historical window in days for metric telemetry (CPU/Memory/IOPS).",
    )
    source_archive_name: str | None = Field(
        default=None,
        description="Filename of uploaded application source code archive analyzed.",
    )


class AuditEvidence(BaseModel):
    """Concrete telemetry or code evidence supporting an audit finding."""

    evidence_id: str = Field(..., description="Unique evidence reference identifier.")
    source_system: str = Field(
        ...,
        description="Originating telemetry system (e.g. 'Azure Monitor', 'Resource Graph').",
    )
    metric_name: str = Field(
        ..., description="Specific telemetry metric observed (e.g. 'Percentage CPU P95')."
    )
    observed_value: str = Field(
        ..., description="Quantitative value observed (e.g. '2.4% avg over 30d')."
    )
    timestamp_observed: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the evidence record was evaluated.",
    )


class WasteFinding(BaseModel):
    """Identified cloud infrastructure waste item with quantified financial impact."""

    finding_id: str = Field(..., description="Unique slug for this waste finding.")
    resource_id: str = Field(
        ..., description="Full ARM cloud resource ID or name of the flagged resource."
    )
    resource_type: str = Field(
        ...,
        description="Type of resource (e.g. 'Microsoft.Compute/virtualMachines').",
    )
    waste_category: str = Field(
        ...,
        description="Classification: 'idle_vm', 'unattached_disk', 'overprovisioned_db'.",
    )
    description: str = Field(
        ..., description="Detailed explanation of why this resource is classified as waste."
    )
    current_monthly_spend: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        ...,
        ge=Decimal("0.0"),
        description="Current estimated monthly expenditure for this resource.",
    )
    potential_monthly_savings: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        ..., ge=Decimal("0.0"), description="Projected monthly savings if remediated."
    )
    remediation_recommendation: str = Field(
        ...,
        description="Recommended action (e.g. 'Decommission unattached managed disk').",
    )
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="References to AuditEvidence records supporting this finding.",
    )


class ModernizationOpportunity(BaseModel):
    """Architectural modernization proposal (e.g. IaaS to PaaS/Serverless migration)."""

    opportunity_id: str = Field(..., description="Unique identifier for the modernization item.")
    title: str = Field(..., description="Short descriptive title of the modernization.")
    source_architecture: str = Field(
        ..., description="Current legacy architecture (e.g. 'Self-hosted Django on IaaS VM')."
    )
    target_architecture: str = Field(
        ...,
        description="Target PaaS architecture (e.g. 'Azure Container Apps + Managed DB').",
    )
    migration_complexity: str = Field(
        default="medium",
        description="Estimated implementation complexity: 'low', 'medium', 'high'.",
    )
    estimated_implementation_days: int | None = Field(
        default=None,
        ge=1,
        description="Estimated engineering effort in person-days to execute the migration.",
    )
    benefits: list[str] = Field(
        default_factory=list,
        description="Key architectural benefits (e.g. automatic scaling, zero OS maintenance).",
    )


class OptimizationAudit(BaseModel):
    """Advisory optimization assessment report.

    IMPORTANT: This schema represents an ADVISORY assessment. The platform
    strictly requires explicit human approval and possesses zero automated
    execution capabilities against customer infrastructure.
    """

    id: UUID = Field(
        default_factory=uuid4,
        description="Globally unique identifier for this optimization audit.",
    )
    scope: AuditScope = Field(
        ...,
        description="Scope and parameters of the evaluation.",
    )
    waste_findings: list[WasteFinding] = Field(
        default_factory=list,
        description="Itemized cloud waste findings with potential savings.",
    )
    modernization_opportunities: list[ModernizationOpportunity] = Field(
        default_factory=list,
        description="Proposals for cloud-native modernization.",
    )
    evidence: list[AuditEvidence] = Field(
        default_factory=list,
        description="Telemetry evidence supporting all findings.",
    )

    # Quantified financial impacts (when supported by evidence)
    current_monthly_spend: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None = (
        Field(
            default=None,
            ge=Decimal("0.0"),
            description="Total current monthly spend across evaluated scope.",
        )
    )
    projected_monthly_spend: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None = (
        Field(
            default=None,
            ge=Decimal("0.0"),
            description="Projected monthly spend after executing recommended optimizations.",
        )
    )
    estimated_monthly_savings: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None = (
        Field(
            default=None,
            ge=Decimal("0.0"),
            description="Total projected monthly cost reduction.",
        )
    )
    estimated_annual_savings: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None = (
        Field(
            default=None,
            ge=Decimal("0.0"),
            description="Annualized projected cost reduction.",
        )
    )
    total_implementation_effort_days: int | None = Field(
        default=None,
        ge=0,
        description="Aggregate estimated implementation effort across modernization opportunities.",
    )

    # Audit rigor and human approval gate
    confidence_score: Annotated[Decimal, Field(max_digits=4, decimal_places=2)] = Field(
        default=Decimal("0.85"),
        ge=Decimal("0.0"),
        le=Decimal("1.0"),
        description="Confidence factor in telemetry completeness (0.0 to 1.0).",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions applied in waste detection and savings calculations.",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Telemetry gaps, unmonitored resources, or evaluation limitations.",
    )
    approval_status: AuditApprovalStatus = Field(
        default=AuditApprovalStatus.PENDING_REVIEW,
        description="Human governance status: requires explicit customer review and approval.",
    )
    reviewed_by: str | None = Field(
        default=None,
        description="Identity of the cloud architect or stakeholder who reviewed the audit.",
    )
    reviewed_at: datetime | None = Field(
        default=None,
        description="Timestamp when human review was completed.",
    )
    approval_notes: str | None = Field(
        default=None,
        description="Human review notes or modifications.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the audit was generated.",
    )

    model_config = ConfigDict(from_attributes=True)
