"""Domain schemas and API contracts for Token Economics, AI model consumption, and rate telemetry."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from cloud_recommender.schemas.common import CloudProvider

TokenDataStatus = Literal[
    "live_telemetry",
    "no_data_available",
    "instrumentation_required",
    "simulation_benchmark",
    "unavailable_permission_required",
    "pricing_catalog",
]


class TokenUsageRecord(BaseModel):
    """Canonical detailed log or bucketed interval of AI token consumption."""

    timestamp: datetime = Field(..., description="Observation UTC timestamp.")
    provider: CloudProvider = Field(..., description="Cloud provider hosting the model.")
    subscription_id: str | None = Field(default=None, description="Azure subscription ID or None.")
    project_id: str | None = Field(default=None, description="GCP project ID or None.")
    resource_id: str = Field(..., description="ARM ID or GCP resource name of the AI service.")
    resource_name: str = Field(..., description="Resource display name.")
    resource_group: str = Field(
        default="Unattributed",
        description="Resource group or workload attribution (or 'Unattributed' if not tagged).",
    )
    service_name: str = Field(
        default="Azure OpenAI / Cognitive Services",
        description="Logical cloud service classification (e.g. Azure OpenAI, Vertex AI).",
    )
    model_name: str = Field(default="Unattributed", description="AI model identifier.")
    model_id: str | None = Field(
        default=None,
        description="Nullable model deployment SKU when attribution is unavailable.",
    )
    period_start: datetime | None = Field(default=None, description="Interval window start UTC.")
    period_end: datetime | None = Field(default=None, description="Interval window end UTC.")
    prompt_tokens: int = Field(default=0, ge=0, description="Input / prompt tokens consumed.")
    completion_tokens: int = Field(
        default=0, ge=0, description="Output / completion tokens generated."
    )
    provider_total_tokens: int | None = Field(
        default=None, description="Total tokens reported by provider for validation."
    )
    normalized_total_tokens: int = Field(
        default=0, ge=0, description="Prompt tokens + Completion tokens."
    )
    total_tokens: int = Field(default=0, ge=0, description="Canonical total tokens consumed.")
    prompt_rate_per_million: Annotated[Decimal, Field(max_digits=12, decimal_places=4)] | None = (
        Field(default=None, description="Prompt rate per 1M tokens.")
    )
    completion_rate_per_million: (
        Annotated[Decimal, Field(max_digits=12, decimal_places=4)] | None
    ) = Field(default=None, description="Completion rate per 1M tokens.")
    estimated_cost_usd: Annotated[Decimal, Field(max_digits=12, decimal_places=4)] = Field(
        default=Decimal("0.0000"),
        description="Estimated monetary cost calculated via official provider rate meters.",
    )
    currency: str = Field(default="USD", description="Currency code (USD).")
    telemetry_status: TokenDataStatus = Field(
        default="live_telemetry", description="Telemetry validity status."
    )
    metric_source: str = Field(
        default="Azure Monitor Metrics API (2023-10-01)",
        description="Underlying telemetry source.",
    )
    rate_meter_source: str = Field(
        default="Azure OpenAI Public Tier (GPT-4o Baseline Rate)",
        description="Source of the unit rate used for deterministic cost calculation.",
    )
    pricing_source: str = Field(
        default="Azure Retail Prices API (Public Tier)",
        description="Catalog source for unit pricing.",
    )
    attribution_status: Literal["attributed_to_model", "attributed_to_resource", "unattributed"] = (
        Field(
            default="attributed_to_resource",
            description="Granularity of attribution.",
        )
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Record update timestamp."
    )


class TokenTrendPoint(BaseModel):
    """Timeseries data point for token consumption and spend over time."""

    timestamp: datetime = Field(..., description="Timeseries interval UTC timestamp.")
    prompt_tokens: int = Field(default=0, description="Prompt tokens in interval.")
    completion_tokens: int = Field(default=0, description="Completion tokens in interval.")
    total_tokens: int = Field(default=0, description="Total tokens in interval.")
    estimated_cost_usd: Annotated[Decimal, Field(max_digits=12, decimal_places=4)] = Field(
        default=Decimal("0.0000"), description="Cost incurred in interval."
    )


class ModelTokenBreakdown(BaseModel):
    """Aggregated token consumption and cost rollup by individual AI model."""

    model_name: str = Field(..., description="Model name (e.g. gpt-4o, gpt-4o-mini).")
    provider: str = Field(..., description="Provider hosting the deployment.")
    prompt_tokens: int = Field(default=0, description="Total prompt tokens consumed.")
    completion_tokens: int = Field(default=0, description="Total completion tokens generated.")
    total_tokens: int = Field(default=0, description="Total tokens for this model.")
    prompt_rate_per_million: Annotated[Decimal, Field(max_digits=8, decimal_places=4)] = Field(
        ..., description="Official price per 1,000,000 prompt tokens (USD)."
    )
    completion_rate_per_million: Annotated[Decimal, Field(max_digits=8, decimal_places=4)] = Field(
        ..., description="Official price per 1,000,000 completion tokens (USD)."
    )
    total_cost_usd: Annotated[Decimal, Field(max_digits=12, decimal_places=4)] = Field(
        default=Decimal("0.0000"), description="Total estimated cost for this model."
    )
    percentage_of_total: float = Field(
        default=0.0, description="Percentage of total token volume (0.0 - 100.0)."
    )


class WorkloadTokenBreakdown(BaseModel):
    """Aggregated token consumption grouped by Resource Group or workload name."""

    workload_or_group: str = Field(
        ..., description="Resource group or workload name (or 'Unattributed')."
    )
    resource_count: int = Field(default=1, description="Number of AI accounts in this group.")
    prompt_tokens: int = Field(default=0, description="Total prompt tokens in this group.")
    completion_tokens: int = Field(default=0, description="Total completion tokens in this group.")
    total_tokens: int = Field(default=0, description="Total tokens consumed in this group.")
    total_cost_usd: Annotated[Decimal, Field(max_digits=12, decimal_places=4)] = Field(
        default=Decimal("0.0000"), description="Estimated cost for this group."
    )
    percentage_of_total: float = Field(default=0.0, description="Percentage of total token volume.")
    pricing_source: str = Field(
        default="Azure Retail Prices API (Public Tier)", description="Catalog source."
    )
    telemetry_status: TokenDataStatus = Field(
        default="live_telemetry", description="Telemetry status."
    )
    attribution_status: str = Field(
        default="attributed_to_resource", description="Attribution status."
    )


class ServiceTokenBreakdown(BaseModel):
    """Aggregated token consumption grouped by Service category."""

    service_name: str = Field(..., description="Service name (e.g. Azure OpenAI, Vertex AI).")
    resource_count: int = Field(default=1, description="Number of AI resources in this service.")
    prompt_tokens: int = Field(default=0, description="Prompt tokens in this service.")
    completion_tokens: int = Field(default=0, description="Completion tokens in this service.")
    total_tokens: int = Field(default=0, description="Total tokens in this service.")
    total_cost_usd: Annotated[Decimal, Field(max_digits=12, decimal_places=4)] = Field(
        default=Decimal("0.0000"), description="Estimated cost for this service."
    )
    percentage_of_total: float = Field(default=0.0, description="Percentage of total token volume.")
    pricing_source: str = Field(
        default="Azure Retail Prices API (Public Tier)", description="Pricing catalog source."
    )
    telemetry_status: TokenDataStatus = Field(
        default="live_telemetry", description="Telemetry status."
    )
    attribution_status: str = Field(
        default="attributed_to_resource", description="Attribution status."
    )


class TokenEconomicsSummary(BaseModel):
    """Top-level Token Economics dashboard payload."""

    provider: CloudProvider = Field(..., description="Cloud provider.")
    scope_id: str = Field(..., description="Target subscription or project ID.")
    scope_name: str = Field(..., description="Scope display name.")
    time_window: str = Field(..., description="Selected query time window (e.g. 7d).")
    data_status: TokenDataStatus = Field(
        ...,
        description="Status of token telemetry (live_telemetry, instrumentation_required, etc.).",
    )
    status_message: str = Field(..., description="Truthful explanatory status.")
    total_tokens: int = Field(default=0, description="Total tokens consumed in observation window.")
    prompt_tokens: int = Field(default=0, description="Prompt / input tokens.")
    completion_tokens: int = Field(default=0, description="Completion / output tokens.")
    prompt_cost_usd: Annotated[Decimal, Field(max_digits=12, decimal_places=4)] = Field(
        default=Decimal("0.0000"), description="Prompt token portion of estimated cost."
    )
    completion_cost_usd: Annotated[Decimal, Field(max_digits=12, decimal_places=4)] = Field(
        default=Decimal("0.0000"), description="Completion token portion of estimated cost."
    )
    estimated_cost_usd: Annotated[Decimal, Field(max_digits=12, decimal_places=4)] = Field(
        default=Decimal("0.0000"), description="Total estimated cost in USD."
    )
    unattributed_tokens: int = Field(
        default=0, description="Tokens not attributed to a specific resource group or workload."
    )
    unattributed_percentage: float = Field(
        default=0.0, description="Percentage of tokens unattributed."
    )
    active_models_count: int = Field(default=0, description="Number of distinct AI models active.")
    discovered_ai_resources_count: int = Field(
        default=0, description="Total AI / Cognitive Services accounts detected in scope."
    )
    discovered_ai_resources: list[str] = Field(
        default_factory=list, description="Names of detected AI services."
    )
    trend_points: list[TokenTrendPoint] = Field(
        default_factory=list, description="Chronological token consumption and cost trends."
    )
    model_breakdowns: list[ModelTokenBreakdown] = Field(
        default_factory=list, description="Token consumption by AI model."
    )
    workload_breakdowns: list[WorkloadTokenBreakdown] = Field(
        default_factory=list, description="Token consumption by Resource Group / Workload."
    )
    service_breakdowns: list[ServiceTokenBreakdown] = Field(
        default_factory=list, description="Token consumption by Service category."
    )
    usage_records: list[TokenUsageRecord] = Field(
        default_factory=list, description="Detailed records / log samples for table inspection."
    )
    diagnostic_setup_guide: list[str] = Field(
        default_factory=list,
        description="Actionable steps to enable Azure Diagnostic Settings or Cloud Logging.",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Payload generation timestamp."
    )
