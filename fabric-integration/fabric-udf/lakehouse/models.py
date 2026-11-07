"""Domain models and analytical response envelopes for Microsoft Fabric Lakehouse Reader.

Defines Pydantic v2 schemas for analytical telemetry queried from OneLake Delta tables:
- Resource Inventory (latest snapshots and distribution summaries)
- Cost Details (currency-separated trends and service breakdowns)
- Resource Metrics (deduplicated performance time-series and utilization)
- Token Telemetry (GenAI token consumption and unit economics)
- Sync History (ingestion audit logs and data freshness)
- Lakehouse Health & Diagnostics
"""

from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class AnalyticalResponseEnvelope(BaseModel, Generic[T]):
    """Standardized response envelope enriched with OneLake analytical provenance metadata."""

    status: Literal["success", "error", "degraded"] = Field(
        ..., description="Query execution status: success, error, or degraded."
    )
    data: T | None = Field(default=None, description="Typed analytical payload.")
    data_source: str = Field(
        default="onelake_delta",
        description="Authoritative data source (e.g. onelake_delta, operational_sqlite).",
    )
    is_live: bool = Field(
        default=True,
        description="Indicates whether telemetry represents live persisted cloud records.",
    )
    last_sync_at: str | None = Field(
        default=None,
        description="ISO timestamp of the most recent successful sync run.",
    )
    data_freshness_seconds: int | None = Field(
        default=None,
        description="Age of the underlying Lakehouse analytical snapshot in seconds.",
    )
    records_count: int = Field(
        default=0, description="Total count of relevant records evaluated."
    )
    query_duration_ms: int = Field(
        default=0,
        description="Execution time taken to read and aggregate Delta Lake records.",
    )
    cache_hit: bool = Field(
        default=False,
        description="Whether the response was served from the in-memory TTL query cache.",
    )
    error_code: str | None = Field(
        default=None, description="Machine-readable error identifier if failed."
    )
    error_message: str | None = Field(
        default=None, description="Human-actionable diagnostic message if failed."
    )


# -----------------------------------------------------------------------------
# 1. Resource Inventory Models
# -----------------------------------------------------------------------------
class LakehouseResourceItem(BaseModel):
    """Discovered cloud resource representation from latest Lakehouse snapshot."""

    resource_id: str
    name: str
    provider: str
    resource_type: str
    resource_group: str | None = None
    location: str
    sku_name: str | None = None
    power_state: str | None = None
    tags: dict[str, Any] | None = None
    monthly_retail_cost: Decimal | None = None
    snapshot_timestamp: str


class LakehouseInventorySummary(BaseModel):
    """Aggregated inventory overview from latest snapshot."""

    connection_id: str
    subscription_id: str
    snapshot_timestamp: str
    total_resources: int
    by_provider: dict[str, int] = Field(default_factory=dict)
    by_resource_type: dict[str, int] = Field(default_factory=dict)
    by_region: dict[str, int] = Field(default_factory=dict)
    by_power_state: dict[str, int] = Field(default_factory=dict)
    resources: list[LakehouseResourceItem] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# 2. Cost Analytics Models
# -----------------------------------------------------------------------------
class CurrencyCostTotal(BaseModel):
    """Currency-isolated expenditure aggregation to prevent multi-currency distortion."""

    currency: str
    total_cost: Decimal
    record_count: int


class DailyCostTrendPoint(BaseModel):
    """Daily cost aggregation point for trend charting."""

    usage_date: str
    currency: str
    daily_cost: Decimal
    record_count: int


class ServiceCostItem(BaseModel):
    """Expenditure categorized by cloud service."""

    service_name: str
    currency: str
    total_cost: Decimal
    percentage: float
    record_count: int


class LakehouseCostAnalytics(BaseModel):
    """Multi-dimensional cost breakdown from OneLake cost_details table."""

    connection_id: str
    subscription_id: str
    date_range_start: str
    date_range_end: str
    total_by_currency: list[CurrencyCostTotal] = Field(default_factory=list)
    daily_trend: list[DailyCostTrendPoint] = Field(default_factory=list)
    by_service: list[ServiceCostItem] = Field(default_factory=list)
    by_charge_type: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    total_records: int = 0


# -----------------------------------------------------------------------------
# 3. Resource Metrics Models
# -----------------------------------------------------------------------------
class MetricSeriesPoint(BaseModel):
    """Time-series telemetry point for performance analysis."""

    timestamp: str
    average: float | None = None
    maximum: float | None = None
    minimum: float | None = None


class ResourceMetricSeries(BaseModel):
    """Aggregated metric time-series for a single resource and metric name."""

    resource_id: str
    metric_name: str
    unit: str
    average_utilization: float | None = None
    peak_utilization: float | None = None
    minimum_utilization: float | None = None
    points_count: int = 0
    points: list[MetricSeriesPoint] = Field(default_factory=list)


class LakehouseMetricsSummary(BaseModel):
    """Performance telemetry analysis for resources in a connection."""

    connection_id: str
    subscription_id: str
    series: list[ResourceMetricSeries] = Field(default_factory=list)
    total_points_evaluated: int = 0
    distinct_time_buckets: int = 0
    coverage_percentage: float = 100.0


# -----------------------------------------------------------------------------
# 4. Token Telemetry Models
# -----------------------------------------------------------------------------
class LakehouseTokenSummary(BaseModel):
    """GenAI inference token economics summary."""

    connection_id: str
    has_data: bool = False
    total_events: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: Decimal = Decimal("0.000000")
    message: str = "No token telemetry has been ingested into Lakehouse."


# -----------------------------------------------------------------------------
# 5. Sync History & Audit Models
# -----------------------------------------------------------------------------
class SyncHistoryEntry(BaseModel):
    """Audit ledger record from OneLake sync_history table."""

    sync_id: str
    connection_id: str
    sync_type: str
    status: str
    records_extracted: int
    records_written: int
    duration_ms: int
    started_at: str
    completed_at: str | None = None
    error_details: str | None = None


class LakehouseSyncOverview(BaseModel):
    """Overview of recent Lakehouse synchronization executions."""

    connection_id: str
    latest_status: str | None = None
    last_successful_sync: str | None = None
    data_freshness_seconds: int | None = None
    total_sync_runs: int = 0
    success_runs: int = 0
    failed_runs: int = 0
    recent_history: list[SyncHistoryEntry] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# 6. Health & Diagnostics Models
# -----------------------------------------------------------------------------
class TableHealthStatus(BaseModel):
    """Readiness and metadata for an individual OneLake Delta table."""

    name: str
    accessible: bool
    version: int | None = None
    row_count: int | None = None
    file_count: int | None = None
    error: str | None = None


class LakehouseHealthStatus(BaseModel):
    """Comprehensive readiness diagnostic for Lakehouse storage and reader."""

    overall_status: Literal["READY", "DEGRADED", "UNAVAILABLE"]
    auth_status: str
    auth_method: str
    workspace_id: str
    lakehouse_id: str
    tables: dict[str, TableHealthStatus] = Field(default_factory=dict)
    diagnostic_details: str | None = None
    timestamp: str
