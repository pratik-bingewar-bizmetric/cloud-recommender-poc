"""Schemas for subscription/project-level cloud inventory, hierarchy, cost rollups, and comparison."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from cloud_recommender.schemas.analysis import ClarifyingAnswer, WorkloadAssumptions
from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
from cloud_recommender.schemas.recommendation import (
    CostBreakdown,
    PricingReference,
    RecommendationReport,
)
from cloud_recommender.schemas.workload import WorkloadProfileCreate


class HierarchyNode(BaseModel):
    """A node in a provider-native cloud hierarchy (Tenant/MG/Sub/RG or Org/Folder/Project)."""

    node_id: str = Field(..., description="Provider-native identifier of the scope node.")
    name: str = Field(..., description="Display name of the scope node.")
    node_type: Literal[
        "azure_tenant",
        "azure_management_group",
        "azure_subscription",
        "azure_resource_group",
        "gcp_organization",
        "gcp_folder",
        "gcp_project",
    ] = Field(..., description="Provider-specific hierarchy level.")
    parent_id: str | None = Field(default=None, description="Parent scope node identifier.")
    state_or_status: str = Field(default="Active", description="Lifecycle state of the scope.")
    location: str | None = Field(default=None, description="Primary location if applicable.")


class ResourceRelationship(BaseModel):
    """Evidence-based or explicitly inferred architectural relationship between resources."""

    source_resource_id: str = Field(..., description="Origin resource ID.")
    target_resource_id: str = Field(..., description="Target resource ID.")
    target_resource_name: str = Field(..., description="Target resource display name.")
    relationship_type: Literal[
        "verified_arm_hierarchy",
        "verified_property_reference",
        "verified_hosting_plan",
        "inferred_co_located",
    ] = Field(..., description="Provenance classification of the relationship.")
    is_verified: bool = Field(
        ...,
        description="True when backed by explicit ARM/GCP parent ID or resource property reference; False when inferred.",
    )
    direction: Literal["parent_to_child", "hosted_on", "depends_on", "secures", "co_located"] = (
        Field(default="depends_on", description="Directional semantics of the connection.")
    )
    evidence: str = Field(
        ...,
        description="Concrete metadata field or co-location rule that established this edge.",
    )


class ResourceWasteFinding(BaseModel):
    """Evidence-backed cloud waste finding with quantified financial impact."""

    id: str = Field(..., description="Unique finding identifier.")
    resource_id: str = Field(..., description="Provider native resource ID.")
    resource_name: str = Field(..., description="Resource display name.")
    native_resource_type: str = Field(..., description="Native provider resource type.")
    provider: CloudProvider = Field(..., description="Target cloud provider.")
    scope_id: str = Field(..., description="Parent subscription or project ID.")
    group_name: str = Field(..., description="Resource group or service domain name.")
    category: Literal[
        "idle_compute",
        "oversized_compute",
        "stopped_compute",
        "unattached_storage",
        "stale_snapshot",
        "unattached_ip",
        "idle_database",
        "overprovisioned_database",
        "redundant_network",
        "unutilized_service",
    ] = Field(..., description="Standardized waste category.")
    severity: Literal["critical", "high", "medium", "low"] = Field(
        ..., description="FinOps severity rating."
    )
    title: str = Field(..., description="Concise finding headline.")
    description: str = Field(..., description="Detailed description of the inefficiency.")
    evidence: str = Field(
        ..., description="Observable telemetry metric, state, or property evidence."
    )
    metric_observed: str | None = Field(
        default=None, description="Key metric value (e.g. 'CPU avg: 1.8% over 30d')."
    )
    current_monthly_spend: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.0"),
        description="Current monthly cost for this resource.",
    )
    potential_monthly_savings: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), ge=Decimal("0.0"), description="Net achievable monthly savings."
    )
    spend_basis: Literal["observed_billing", "catalog_estimate", "unpriced"] = Field(
        default="catalog_estimate", description="Pricing provenance basis."
    )
    confidence: Literal["high", "medium", "provisional"] = Field(
        default="high", description="Confidence level based on telemetry completeness."
    )
    remediation_recommendation: str = Field(
        ..., description="Actionable advisory remediation step."
    )
    pre_remediation_considerations: list[str] = Field(
        default_factory=list,
        description="Dependency, downtime, data retention, or compliance considerations.",
    )
    double_counting_prevention_note: str | None = Field(
        default=None,
        description="Verification that savings do not duplicate associated resource savings.",
    )


class TechnicalDebtItem(BaseModel):
    """Evaluated architectural, security, or maintainability technical debt item."""

    id: str = Field(..., description="Unique technical debt item identifier.")
    resource_id: str = Field(..., description="Provider native resource ID.")
    resource_name: str = Field(..., description="Resource display name.")
    native_resource_type: str = Field(..., description="Native provider resource type.")
    provider: CloudProvider = Field(..., description="Target cloud provider.")
    scope_id: str = Field(..., description="Parent subscription or project ID.")
    group_name: str = Field(..., description="Resource group or service domain name.")
    debt_category: Literal[
        "missing_monitoring",
        "missing_backup",
        "missing_tagging",
        "legacy_runtime_or_os",
        "legacy_sku",
        "unrestricted_network",
        "single_point_of_failure",
    ] = Field(..., description="Standardized technical debt category.")
    severity: Literal["critical", "high", "medium", "low"] = Field(
        ..., description="Risk severity rating."
    )
    title: str = Field(..., description="Headline describing the technical debt.")
    description: str = Field(
        ..., description="Detailed explanation of the technical debt and its impact."
    )
    evidence: str = Field(
        ..., description="Specific configuration, property, or missing setting observed."
    )
    remediation_steps: list[str] = Field(
        default_factory=list, description="Concrete modernization and remediation steps."
    )
    architectural_risk: str = Field(
        ...,
        description="Consequences if unaddressed (e.g. data loss, breach risk, operational outage).",
    )


class DiscoveredResource(BaseModel):
    """Normalized cloud resource record preserving native hierarchy and pricing provenance."""

    provider: CloudProvider = Field(..., description="Cloud provider ('azure' or 'gcp').")
    resource_id: str = Field(
        ..., description="Provider-native resource identifier (ARM ID or GCP Asset name)."
    )
    resource_name: str = Field(..., description="Resource display name.")
    native_resource_type: str = Field(
        ...,
        description="Provider-native type (e.g. 'Microsoft.DBforPostgreSQL/flexibleServers' or 'run.googleapis.com/Service').",
    )
    canonical_service_id: str = Field(
        ...,
        description="Normalized catalog service identifier used for deterministic pricing.",
    )
    service_category: ServiceCategory = Field(..., description="Architectural category.")
    region: str = Field(..., description="Deployment region or location.")
    sku_or_tier: str | None = Field(
        default=None, description="Discovered SKU name, tier, or machine type."
    )
    kind: str | None = Field(default=None, description="Resource kind or sub-flavor.")
    parent_scope_id: str = Field(
        ..., description="Immediate parent scope ID (Resource Group ID or GCP Project ID)."
    )
    subscription_id: str | None = Field(
        default=None, description="Azure subscription ID (None for GCP)."
    )
    resource_group: str | None = Field(
        default=None,
        description="Azure Resource Group name (strictly None for GCP; GCP uses Projects/Folders).",
    )
    project_id: str | None = Field(
        default=None, description="GCP Project ID (strictly None for Azure)."
    )
    folder_id: str | None = Field(default=None, description="GCP Folder ID when available.")
    organization_id: str | None = Field(
        default=None, description="GCP Organization ID when available."
    )
    tags_or_labels: dict[str, str] = Field(
        default_factory=dict, description="Resource tags (Azure) or labels (GCP)."
    )
    configuration: dict[str, Any] = Field(
        default_factory=dict, description="Sanitized configuration properties."
    )
    relationships: list[ResourceRelationship] = Field(
        default_factory=list,
        description="Verified and explicitly labeled inferred relationships.",
    )
    origin: Literal["discovered", "ai_proposed", "mock_fixture"] = Field(
        default="discovered",
        description="Whether this resource was discovered from a live cloud scope, proposed by AI, or loaded from a labeled fixture.",
    )
    pricing_status: Literal["verified", "provisional", "bundled", "unpriced"] = Field(
        default="verified",
        description="Pricing verification classification.",
    )
    estimated_monthly_cost: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.0"),
        description="Deterministic monthly cost estimate from public list pricing.",
    )
    actual_monthly_spend: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None = Field(
        default=None,
        description="Actual billed spend from Cost Management / Billing Export when authorized (None if unavailable).",
    )
    workload_quantity: Annotated[Decimal, Field(max_digits=14, decimal_places=4)] | None = Field(
        default=None, description="Estimated usage quantity applied for pricing."
    )
    workload_unit: str | None = Field(default=None, description="Billing unit of measure.")
    calculation_explanation: str = Field(
        default="",
        description="Explicit formula and assumptions used to compute estimated_monthly_cost.",
    )
    missing_price_warning: str | None = Field(
        default=None,
        description="Warning if official pricing could not be verified for this resource type/SKU.",
    )
    pricing_reference: PricingReference | None = Field(
        default=None, description="Retained official pricing API reference."
    )
    discovery_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the resource was discovered.",
    )
    waste_findings: list[ResourceWasteFinding] = Field(
        default_factory=list, description="Detected waste findings specific to this resource."
    )
    technical_debt_items: list[TechnicalDebtItem] = Field(
        default_factory=list, description="Detected technical debt items specific to this resource."
    )


class ScopeCostGroup(BaseModel):
    """Hierarchical cost rollup for an Azure Resource Group or GCP Project Service Domain."""

    group_id: str = Field(..., description="Scope or group identifier.")
    group_name: str = Field(
        ..., description="Resource Group name (Azure) or Service Domain / Folder (GCP)."
    )
    group_type: Literal["azure_resource_group", "gcp_service_domain", "gcp_folder"] = Field(
        ..., description="Provider-accurate grouping type."
    )
    location: str = Field(default="global", description="Primary location of the group.")
    resource_count: int = Field(default=0, ge=0, description="Total resources in this group.")
    verified_monthly_subtotal: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), ge=Decimal("0.0")
    )
    total_monthly: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), ge=Decimal("0.0")
    )
    total_five_month: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), ge=Decimal("0.0")
    )
    total_annual: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), ge=Decimal("0.0")
    )
    unpriced_resource_count: int = Field(default=0, ge=0)
    is_complete: bool = Field(default=True)
    potential_monthly_savings: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.0"),
        description="Aggregate potential monthly savings in this group.",
    )
    waste_findings_count: int = Field(default=0, ge=0)
    technical_debt_count: int = Field(default=0, ge=0)
    critical_findings_count: int = Field(default=0, ge=0)
    high_findings_count: int = Field(default=0, ge=0)
    medium_findings_count: int = Field(default=0, ge=0)
    low_findings_count: int = Field(default=0, ge=0)
    resources: list[DiscoveredResource] = Field(default_factory=list)


class SubscriptionRecommendation(BaseModel):
    """Evidence-based subscription or project optimization and architectural recommendation."""

    id: str = Field(..., description="Unique recommendation identifier.")
    category: Literal[
        "right_sizing",
        "redundancy_consolidation",
        "cost_optimization",
        "resilience_security_observability",
        "architecture_modernization",
    ] = Field(..., description="Optimization category.")
    title: str = Field(..., description="Concise recommendation headline.")
    target_resource_ids: list[str] = Field(
        default_factory=list, description="Specific discovered resource IDs affected."
    )
    target_resource_names: list[str] = Field(
        default_factory=list, description="Human-readable names of affected resources."
    )
    evidence: str = Field(
        ...,
        description="Concrete configuration, SKU, region, or hierarchy evidence observed in the inventory.",
    )
    rationale: str = Field(..., description="Architectural and financial justification.")
    estimated_monthly_impact: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"),
        description="Estimated monthly cost change (negative for savings, positive for resilience investment).",
    )
    impact_type: Literal["monthly_savings", "cost_neutral", "resilience_investment"] = Field(
        default="monthly_savings"
    )
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ProviderConnectionStatus(BaseModel):
    """Live authentication and API readiness status for a cloud provider."""

    provider: CloudProvider
    inventory_auth_ready: bool = Field(
        ..., description="Whether read-only credentials are available for live resource discovery."
    )
    inventory_auth_method: str = Field(
        ..., description="Active authentication mechanism or missing credential summary."
    )
    pricing_api_ready: bool = Field(
        ..., description="Whether official public pricing API access is operational."
    )
    pricing_api_source: str = Field(..., description="Official pricing source name.")
    authorized_scopes_count: int = Field(default=0, ge=0)
    status_message: str = Field(..., description="Human-readable connection diagnostic.")
    access_limitations: list[str] = Field(default_factory=list)


class CloudScopeSummary(BaseModel):
    """Summary of an authorized Azure Subscription or GCP Project available for selection."""

    provider: CloudProvider
    scope_id: str = Field(..., description="Subscription ID (Azure) or Project ID (GCP).")
    display_name: str = Field(..., description="Subscription or Project display name.")
    tenant_or_org_id: str | None = Field(default=None)
    parent_scope_id: str | None = Field(default=None)
    state: str = Field(default="Enabled")
    data_source: Literal["live_authenticated", "mock_fixture"] = Field(default="live_authenticated")


class ScopeAnalysisRequest(BaseModel):
    """Request payload to discover and analyze an Azure Subscription or GCP Project."""

    scope_id: str | None = Field(
        default=None,
        description="Target Azure Subscription ID or GCP Project ID. Uses default authorized scope if omitted.",
    )
    resource_group_filter: str | None = Field(
        default=None,
        description="Optional Azure Resource Group name filter.",
    )
    workload_assumptions: WorkloadAssumptions = Field(
        default_factory=WorkloadAssumptions,
        description="Workload volume assumptions used to price consumption/token meters when telemetry is unavailable.",
    )
    safety_buffer_percentage: Annotated[Decimal, Field(max_digits=5, decimal_places=2)] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.0"),
        le=Decimal("100.0"),
        description="Optional contingency buffer percentage (defaults to 0% for inventory rollup).",
    )
    include_demo_fixture_if_unauthenticated: bool = Field(
        default=True,
        description="If live inventory auth is unavailable (e.g. GCP ADC not configured), return an explicitly labeled mock_fixture project hierarchy priced with live API rates.",
    )
    metric_window_days: int = Field(
        default=30,
        ge=7,
        le=90,
        description="Historical telemetry evaluation window in days (default: 30).",
    )
    refresh_telemetry: bool = Field(
        default=False,
        description="Whether to refresh live telemetry from cloud provider rather than using cached metrics.",
    )


class TelemetryCoverageSummary(BaseModel):
    """Summary of telemetry availability, metric sampling window, and evaluation confidence."""

    metric_window_days: int = Field(
        default=30, description="Evaluation observation window in days."
    )
    telemetry_source: str = Field(..., description="Primary telemetry and monitoring provider.")
    monitored_resources_count: int = Field(default=0, ge=0)
    unmonitored_resources_count: int = Field(default=0, ge=0)
    coverage_percentage: Annotated[Decimal, Field(max_digits=5, decimal_places=2)] = Field(
        default=Decimal("100.00")
    )
    last_telemetry_sync: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_cached: bool = Field(default=True)
    confidence_score: Annotated[Decimal, Field(max_digits=4, decimal_places=2)] = Field(
        default=Decimal("0.90"), ge=Decimal("0.0"), le=Decimal("1.0")
    )
    limitations_and_gaps: list[str] = Field(default_factory=list)


class SubscriptionOrProjectAnalysis(BaseModel):
    """Complete subscription-level (Azure) or project-level (GCP) inventory, graph, and cost report."""

    provider: CloudProvider
    scope_id: str
    scope_name: str
    scope_type: Literal["azure_subscription", "gcp_project"]
    tenant_or_org_id: str | None = None
    hierarchy_nodes: list[HierarchyNode] = Field(default_factory=list)
    data_source: Literal["live_authenticated", "ai_proposed", "mock_fixture"]
    spend_label: Literal["estimated_public_list_pricing", "actual_billed_spend", "hybrid"] = (
        "estimated_public_list_pricing"
    )
    actual_billed_monthly_spend: (
        Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None
    ) = None
    resource_count: int = Field(default=0, ge=0)
    group_count: int = Field(
        default=0,
        ge=0,
        description="Number of Azure Resource Groups or GCP Service Domains.",
    )
    groups: list[ScopeCostGroup] = Field(default_factory=list)
    resources: list[DiscoveredResource] = Field(default_factory=list)
    cost_breakdown: CostBreakdown
    pricing_provenance: list[PricingReference] = Field(default_factory=list)
    architecture_mermaid: str = Field(
        ...,
        description="Renderable Mermaid diagram generated from discovered hierarchy and relationships.",
    )
    recommendations: list[SubscriptionRecommendation] = Field(default_factory=list)
    total_potential_monthly_savings: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = (
        Field(
            default=Decimal("0.00"),
            ge=Decimal("0.0"),
            description="Total non-double-counted potential monthly savings across scope.",
        )
    )
    total_potential_annual_savings: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = (
        Field(
            default=Decimal("0.00"),
            ge=Decimal("0.0"),
            description="Annualized projected savings.",
        )
    )
    waste_findings: list[ResourceWasteFinding] = Field(
        default_factory=list, description="All itemized resource waste findings across scope."
    )
    technical_debt_items: list[TechnicalDebtItem] = Field(
        default_factory=list, description="All itemized technical debt items across scope."
    )
    telemetry_coverage: TelemetryCoverageSummary | None = Field(
        default=None,
        description="Summary of telemetry observation window, monitored ratio, and confidence.",
    )
    access_limitations: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    completeness_warning: str | None = None
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CrossCloudServiceMapping(BaseModel):
    """Explicit architectural and cost comparison row between an Azure service and its GCP equivalent."""

    capability: str = Field(
        ..., description="Architectural capability (e.g. 'Managed Container Compute')."
    )
    category: ServiceCategory
    azure_service_id: str
    azure_service_name: str
    azure_sku: str
    azure_monthly_cost: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
    azure_pricing_status: str
    gcp_service_id: str
    gcp_service_name: str
    gcp_sku: str
    gcp_monthly_cost: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
    gcp_pricing_status: str
    monthly_delta_gcp_minus_azure: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
    notes: str = Field(..., description="SKU parity and billing model notes.")


class MultiCloudComparisonRequest(BaseModel):
    """Request payload to generate and compare Azure and GCP architectures for identical requirements."""

    workload_profile: WorkloadProfileCreate
    workload_assumptions: WorkloadAssumptions
    clarifications: list[ClarifyingAnswer] = Field(default_factory=list)
    azure_region: str = Field(default="eastus", description="Target Azure region.")
    gcp_region: str = Field(default="us-central1", description="Target GCP region.")


class MultiCloudComparisonResponse(BaseModel):
    """Side-by-side Azure vs. GCP architecture and deterministic cost comparison."""

    azure_report: RecommendationReport
    gcp_report: RecommendationReport
    service_mappings: list[CrossCloudServiceMapping] = Field(default_factory=list)
    azure_total_monthly: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
    gcp_total_monthly: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
    monthly_delta_gcp_minus_azure: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
    annual_delta_gcp_minus_azure: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
    cheaper_provider: CloudProvider | None = None
    comparison_assumptions: list[str] = Field(default_factory=list)
    trade_off_summary: str = Field(
        ..., description="Executive comparison of Azure vs. GCP trade-offs."
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
