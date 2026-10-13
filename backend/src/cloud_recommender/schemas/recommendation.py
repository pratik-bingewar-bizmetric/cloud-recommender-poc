"""RecommendationReport domain schemas defining cloud architectural proposal contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cloud_recommender.schemas.common import (
    CloudProvider,
    RecommendationStatus,
    ServiceCategory,
)


class ArchitectureComponent(BaseModel):
    """A discrete cloud service component within a recommended architecture."""

    component_id: str = Field(
        ...,
        description="Internal component slug within the blueprint (e.g. 'primary-api-compute').",
    )
    category: ServiceCategory = Field(
        ...,
        description="Architectural service category.",
    )
    service_id: str = Field(
        ...,
        description="Catalog identifier matching official provider service.",
        examples=["azure-container-apps", "aws-ecs-fargate"],
    )
    service_name: str = Field(
        ...,
        description="Display name of the cloud service.",
    )
    sku_or_tier: str | None = Field(
        default=None,
        description="Recommended instance size, compute tier, or SKU.",
        examples=["0.5 vCPU, 1.0 GiB RAM", "Standard_D2s_v5"],
    )
    quantity: int = Field(
        default=1,
        ge=1,
        description="Quantity of service instances or operational units.",
    )
    rationale: str = Field(
        ...,
        description="Technical justification for choosing this component for the workload.",
    )
    monthly_cost: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        ...,
        ge=Decimal("0.0"),
        description="Estimated component monthly cost in specified currency.",
    )
    region: str = Field(
        default="eastus",
        description="Target deployment region for this service component.",
    )
    workload_quantity: Annotated[Decimal, Field(max_digits=14, decimal_places=4)] | None = Field(
        default=None,
        description="Estimated usage quantity (e.g. vCPU-hours, GB storage, API calls, tokens).",
    )
    workload_unit: str | None = Field(
        default=None,
        description="Unit of measurement for the workload quantity (e.g. 'Hours', 'GB', 'Tokens').",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Component IDs this component connects to or depends upon.",
    )
    security_considerations: str | None = Field(
        default=None,
        description="Security controls, private endpoints, or identity configurations.",
    )
    reliability_considerations: str | None = Field(
        default=None,
        description="Availability zone, replication, and failover characteristics.",
    )
    scaling_considerations: str | None = Field(
        default=None,
        description="Autoscaling triggers, min/max replica boundaries, or SKU limits.",
    )
    pricing_assumptions: str | None = Field(
        default=None,
        description="Explicit billing assumptions used to calculate this component's cost.",
    )
    known_risks: list[str] = Field(
        default_factory=list,
        description="Identified architectural risks, service quotas, or limitations.",
    )
    missing_price_warning: str | None = Field(
        default=None,
        description="Warning notice if official pricing could not be verified.",
    )
    pricing_status: str = Field(
        default="verified",
        description="Pricing classification: 'verified', 'provisional', 'bundled', or 'unpriced'.",
    )


class CostBreakdown(BaseModel):
    """Categorized bill of materials (BOM) cost breakdown with decimal precision."""

    compute: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), ge=Decimal("0.0")
    )
    database: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), ge=Decimal("0.0")
    )
    storage: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), ge=Decimal("0.0")
    )
    networking: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), ge=Decimal("0.0")
    )
    ai: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.0"),
        description="Estimated costs for Azure AI Foundry / OpenAI models.",
    )
    other: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), ge=Decimal("0.0")
    )
    subtotal: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        ..., ge=Decimal("0.0"), description="Raw sum of all service component estimates."
    )
    verified_subtotal: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.0"),
        description="Sum of verified and provisional component estimates only.",
    )
    safety_buffer_amount: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.0"),
        description="Operational buffer added to protect against traffic variance.",
    )
    total_monthly: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        ..., ge=Decimal("0.0"), description="Monthly estimated total including safety buffer."
    )
    total_five_month: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.0"),
        description="Five-month projected total expenditure.",
    )
    total_annual: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        ..., ge=Decimal("0.0"), description="Annualized estimated total."
    )
    is_complete: bool = Field(
        default=True,
        description="False when any required component lacks a verified price.",
    )
    estimate_status: str = Field(
        default="complete",
        description="'complete' when all components are priced; 'incomplete' when any is unpriced.",
    )
    unpriced_component_count: int = Field(
        default=0,
        ge=0,
        description="Count of required components excluded due to missing verified rates.",
    )
    unpriced_service_ids: list[str] = Field(
        default_factory=list,
        description="Identifiers of components lacking verified pricing.",
    )

    @model_validator(mode="after")
    def _sync_verified_subtotal(self) -> "CostBreakdown":
        if (
            self.verified_subtotal == Decimal("0.00")
            and self.subtotal > Decimal("0.00")
            and self.unpriced_component_count == 0
        ):
            self.verified_subtotal = self.subtotal
        return self


class TradeOffDimension(BaseModel):
    """Evaluation score and commentary for a specific architectural pillar."""

    score: int = Field(
        ...,
        ge=1,
        le=100,
        description="Pillar rating on a 1-100 scale.",
    )
    assessment: str = Field(
        ...,
        description="Detailed justification and trade-off commentary.",
    )


class TradeOffAssessment(BaseModel):
    """Multi-dimensional trade-off evaluation across five core architectural pillars."""

    cost_efficiency: TradeOffDimension
    security_compliance: TradeOffDimension
    reliability_resilience: TradeOffDimension
    scalability_performance: TradeOffDimension
    operational_complexity: TradeOffDimension
    summary: str = Field(
        ...,
        description="Executive summary of the balanced architectural trade-offs.",
    )


class PricingReference(BaseModel):
    """Provenance and traceability metadata linking estimates to official pricing sources."""

    provider: CloudProvider
    service_id: str
    meter_or_sku_id: str = Field(..., description="Official provider meter or SKU identifier.")
    rate: Annotated[Decimal, Field(max_digits=16, decimal_places=8)] = Field(
        ..., description="Unit pricing rate."
    )
    unit_description: str = Field(..., description="Unit of charge (e.g. '1 Hour', '1 GB/Month').")
    retrieval_timestamp: datetime = Field(
        ..., description="Timestamp when the official pricing rate was retrieved."
    )
    source_url: str = Field(
        ..., description="Official pricing documentation or API reference endpoint."
    )
    provenance_source: str = Field(
        default="official_azure_pricing_benchmark_dataset",
        description="Pricing source classification (live, cached, benchmark, bundled, unverified).",
    )
    service_name: str | None = Field(
        default=None, description="Matched Azure Retail Prices serviceName."
    )
    product_name: str | None = Field(
        default=None, description="Matched Azure Retail Prices productName."
    )
    sku_name: str | None = Field(default=None, description="Matched Azure Retail Prices skuName.")
    meter_name: str | None = Field(
        default=None, description="Matched Azure Retail Prices meterName."
    )
    arm_region_name: str | None = Field(
        default=None, description="Matched Azure Retail Prices armRegionName or Billing Zone."
    )
    tier_minimum_units: float | None = Field(
        default=None, description="Matched Azure Retail Prices tierMinimumUnits."
    )
    pricing_tier_or_notes: str | None = Field(
        default=None, description="Additional notes on multi-meter or bundled pricing."
    )


class RecommendationReport(BaseModel):
    """Complete specification of a generated cloud architecture recommendation report."""

    id: UUID = Field(
        default_factory=uuid4,
        description="Globally unique identifier for this recommendation report.",
    )
    workload_profile_id: UUID = Field(
        ...,
        description="Foreign identifier of the associated workload profile.",
    )
    provider: CloudProvider = Field(
        ...,
        description="Cloud provider for this architectural proposal.",
    )
    region: str = Field(
        ...,
        description="Primary deployment region for this blueprint.",
        examples=["eastus", "us-east-1", "us-central1"],
    )
    architecture_description: str = Field(
        ...,
        description="Comprehensive architectural overview and topology narrative.",
    )
    components: list[ArchitectureComponent] = Field(
        default_factory=list,
        description="Structured list of recommended cloud service components.",
    )
    cost_breakdown: CostBreakdown = Field(
        ...,
        description="Itemized bill of materials and monthly/annual cost calculation.",
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Explicit assumptions made in sizing, traffic, and replication.",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Known limitations, trade-offs, or constraints of this proposal.",
    )
    trade_offs: TradeOffAssessment = Field(
        ...,
        description="Detailed scoring across the five architectural pillars.",
    )
    pricing_provenance: list[PricingReference] = Field(
        default_factory=list,
        description="Audit references to official pricing records backing all estimates.",
    )
    status: RecommendationStatus = Field(
        default=RecommendationStatus.DRAFT,
        description="Current lifecycle status of the recommendation.",
    )
    mermaid_diagram: str | None = Field(
        default=None,
        description="Renderable Mermaid.js flowchart string representing the architecture.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the recommendation was created.",
    )

    model_config = ConfigDict(from_attributes=True)
