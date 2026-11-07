"""Domain schemas and API contracts for Microsoft Fabric User Data Functions.

Strict adherence to:
1. Real Data Only - Zero mock / synthetic fallbacks in production.
2. Least-Privilege Read-Only permissions on customer clouds.
3. Explicit typing with Pydantic v2.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class UdfResponse(BaseModel, Generic[T]):
    """Standard RPC response envelope for Microsoft Fabric User Data Functions."""

    status: Literal["success", "error"] = Field(
        ..., description="Execution status: success or error."
    )
    data: T | None = Field(default=None, description="Typed payload if successful.")
    error_code: str | None = Field(
        default=None, description="Machine-readable error identifier if failed."
    )
    error_message: str | None = Field(
        default=None, description="Human-actionable diagnostic message if failed."
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of response generation.",
    )


class CloudConnection(BaseModel):
    """Metadata representing an authorized cloud subscription or project."""

    id: str = Field(..., description="Unique connection ID (e.g. azure-sub-11223344).")
    name: str = Field(..., description="Display name for the connection.")
    provider: Literal["azure", "aws", "gcp"] = Field(
        ..., description="Target cloud provider."
    )
    scope_id: str = Field(
        ..., description="Azure Subscription ID, AWS Account ID, or GCP Project ID."
    )
    tenant_or_org_id: str | None = Field(
        default=None, description="Entra ID Tenant ID or GCP Org ID."
    )
    client_id: str | None = Field(
        default=None,
        description="Client ID / App ID for Service Principal authentication.",
    )
    secret_vault_ref: str | None = Field(
        default=None,
        description="Secure vault reference or encrypted key identifier for secret.",
    )
    auth_method: str = Field(
        ...,
        description="Safe description of auth method (e.g. service_principal, cli_token).",
    )
    status: Literal["connected", "auth_failed", "permission_denied", "disconnected"] = (
        Field(default="connected", description="Current verified status.")
    )
    last_verified_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of last successful probe.",
    )
    is_live: bool = Field(
        default=True, description="True if backed by verified live provider APIs."
    )
    capabilities: list[str] = Field(
        default_factory=lambda: [
            "inventory",
            "waste_detection",
            "metrics",
            "token_economics",
        ],
        description="Enabled telemetry and scan capabilities.",
    )
    access_limitations: list[str] = Field(
        default_factory=lambda: [
            "Strictly read-only access (Reader, Cost Management Reader, Monitoring Reader).",
            "Zero automated infrastructure mutations permitted.",
        ],
        description="Bound security constraints.",
    )


class DiscoveredResource(BaseModel):
    """Normalized snapshot of a cloud resource discovered via live provider APIs."""

    resource_id: str = Field(..., description="Canonical ARM Resource ID or cloud URI.")
    name: str = Field(..., description="Resource name.")
    resource_type: str = Field(
        ...,
        description="Normalized resource type (e.g. Microsoft.Compute/virtualMachines).",
    )
    resource_group: str | None = Field(
        default=None, description="Azure Resource Group name if applicable."
    )
    location: str = Field(..., description="Cloud region / datacenter location.")
    sku_name: str | None = Field(
        default=None, description="Assigned hardware/tier SKU."
    )
    tags: dict[str, str] = Field(default_factory=dict, description="Resource tags.")
    power_state: str | None = Field(
        default=None,
        description="Power / runtime state (running, stopped, deallocated).",
    )
    monthly_cost_usd: Decimal | None = Field(
        default=None, description="Deterministic monthly cost based on official rates."
    )


class WasteItem(BaseModel):
    """Identified FinOps cloud waste candidate with deterministic cost leakage calculation."""

    resource_id: str = Field(
        ..., description="ARM ID or URI of the resource generating waste."
    )
    name: str = Field(..., description="Resource name.")
    resource_type: str = Field(
        ..., description="Type of resource (VirtualMachine, Disk, PublicIP)."
    )
    waste_category: Literal[
        "unattached_disk", "idle_compute", "unassociated_ip", "oversized_compute"
    ] = Field(..., description="FinOps classification of the waste.")
    evidence: str = Field(
        ..., description="Objective telemetry rationale (e.g. CPU < 5% over 7 days)."
    )
    current_sku: str | None = Field(default=None, description="Current assigned SKU.")
    recommended_sku: str | None = Field(
        default=None, description="Target rightsized SKU if applicable."
    )
    monthly_cost_leakage_usd: Decimal = Field(
        ..., description="Deterministic monthly cost currently being wasted."
    )
    projected_monthly_savings_usd: Decimal = Field(
        ..., description="Monthly financial savings achieved upon manual remediation."
    )
    cost_status: Literal[
        "verified_rate", "estimated_sku_rate", "pricing_unavailable"
    ] = Field(
        default="verified_rate", description="Provenance of monthly cost figure."
    )


class WasteSummary(BaseModel):
    """Aggregated FinOps waste detection findings for a cloud scope."""

    connection_id: str = Field(..., description="Connection ID evaluated.")
    scan_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC time of waste evaluation.",
    )
    total_monthly_waste_usd: Decimal = Field(
        default=Decimal("0.00"),
        description="Sum of monthly waste across all categories.",
    )
    total_annual_waste_usd: Decimal = Field(
        default=Decimal("0.00"), description="12-month projected waste."
    )
    waste_count_by_category: dict[str, int] = Field(
        default_factory=dict, description="Count of candidate resources per category."
    )
    items: list[WasteItem] = Field(
        default_factory=list, description="Detailed list of detected waste candidates."
    )


class MetricPoint(BaseModel):
    """Single timestamped observation point from Azure Monitor."""

    timestamp: datetime = Field(..., description="UTC observation timestamp.")
    average: float | None = Field(
        default=None, description="Average metric value in interval."
    )
    maximum: float | None = Field(
        default=None, description="Peak metric value in interval."
    )
    minimum: float | None = Field(
        default=None, description="Minimum metric value in interval."
    )


class MetricSeries(BaseModel):
    """Timeseries for a specific resource metric."""

    metric_name: str = Field(
        ..., description="Metric identifier (e.g. Percentage CPU)."
    )
    unit: str = Field(..., description="Measurement unit (Percent, Bytes, Count).")
    points: list[MetricPoint] = Field(
        default_factory=list, description="Ordered time series."
    )


class ResourceMetricsResponse(BaseModel):
    """Container for monitoring metrics retrieved for a given resource."""

    resource_id: str = Field(..., description="ARM ID evaluated.")
    time_grain: str = Field(..., description="Aggregation grain (e.g. PT1H, P1D).")
    start_time: datetime = Field(..., description="Start of window.")
    end_time: datetime = Field(..., description="End of window.")
    series: list[MetricSeries] = Field(
        default_factory=list, description="Metric series collected."
    )


class TokenUsageRecord(BaseModel):
    """Canonical log of real GenAI token consumption and deterministic cost."""

    event_id: str = Field(..., description="Unique event identifier.")
    connection_id: str = Field(..., description="Associated connection ID.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the model inference event.",
    )
    model_name: str = Field(
        ..., description="Model identifier (e.g. gpt-4o, gpt-4o-mini)."
    )
    deployment_name: str | None = Field(
        default=None, description="Azure OpenAI deployment name."
    )
    prompt_tokens: int = Field(
        default=0, ge=0, description="Actual prompt tokens consumed."
    )
    completion_tokens: int = Field(
        default=0, ge=0, description="Actual completion tokens generated."
    )
    total_tokens: int = Field(
        default=0, ge=0, description="Sum of prompt and completion tokens."
    )
    latency_ms: int | None = Field(
        default=None, ge=0, description="Inference response duration in ms."
    )
    estimated_cost_usd: Decimal = Field(
        default=Decimal("0.0000"),
        description="Deterministic cost calculated via official provider unit rate.",
    )
    source: Literal["direct_inference_intercept", "azure_monitor_metric"] = Field(
        default="direct_inference_intercept",
        description="Source of the token telemetry.",
    )
    pricing_status: Literal["published_rate", "unknown_model_rate"] = Field(
        default="published_rate",
        description="Provenance of model rate pricing.",
    )


class TokenEconomicsSummary(BaseModel):
    """Aggregated token economics summary across models."""

    connection_id: str = Field(..., description="Target connection ID.")
    window_days: int = Field(default=30, description="Days covered in summary.")
    total_prompt_tokens: int = Field(default=0, ge=0)
    total_completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    total_cost_usd: Decimal = Field(default=Decimal("0.0000"))
    token_efficiency_ratio: float = Field(
        default=0.0, description="Ratio of completion tokens to prompt tokens."
    )
    models_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    daily_timeseries: list[dict[str, Any]] = Field(default_factory=list)


# --- UDF Function Argument Schemas ---


class ListConnectionsArgs(BaseModel):
    provider_filter: Literal["azure", "aws", "gcp"] | None = None


class CreateConnectionArgs(BaseModel):
    provider: Literal["azure", "aws", "gcp"] = "azure"
    name: str = Field(..., min_length=1, max_length=120)
    tenant_id: str = Field(..., min_length=1)
    subscription_id: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)


class ValidateConnectionArgs(BaseModel):
    connection_id: str | None = None
    provider: Literal["azure", "aws", "gcp"] = "azure"
    tenant_id: str | None = None
    subscription_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


class GetInventoryArgs(BaseModel):
    connection_id: str = Field(..., min_length=1)
    resource_type_filter: str | None = None


class GetWasteArgs(BaseModel):
    connection_id: str = Field(..., min_length=1)
    force_refresh: bool = False


class GetMetricsArgs(BaseModel):
    connection_id: str = Field(..., min_length=1)
    resource_id: str = Field(..., min_length=1)
    metric_names: list[str] = Field(default_factory=lambda: ["Percentage CPU"])
    time_grain: str = "PT1H"
    days: int = 7


class GetTokenEconomicsArgs(BaseModel):
    connection_id: str = Field(..., min_length=1)
    days: int = 30


class RecordTokenArgs(BaseModel):
    connection_id: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    deployment_name: str | None = None
    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    latency_ms: int | None = None


class PricingCalculationArgs(BaseModel):
    arm_sku_name: str = Field(..., min_length=1)
    region: str = "northcentralus"
    hours_per_month: Decimal = Decimal("730.0")
