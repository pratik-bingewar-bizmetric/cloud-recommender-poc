"""Domain schemas and API contracts for centralized infrastructure monitoring, historical telemetry, and operational intelligence."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from cloud_recommender.schemas.common import CloudProvider
from cloud_recommender.schemas.inventory import (
    DiscoveredResource,
    ResourceWasteFinding,
    TechnicalDebtItem,
)

TimeWindowPreset = Literal["1h", "24h", "7d", "30d", "90d", "custom"]
MetricInterval = Literal["1m", "5m", "15m", "1h", "1d"]
LogSeverity = Literal["critical", "error", "warning", "informational", "verbose"]
AlertSeverity = Literal["critical", "high", "medium", "low", "info"]
ResourceHealthState = Literal["healthy", "degraded", "failing", "unmonitored", "stopped"]


class MonitoringQueryRequest(BaseModel):
    """Request payload for querying monitoring telemetry across a cloud scope or resource."""

    provider: CloudProvider = Field(..., description="Cloud provider (azure or gcp).")
    scope_id: str = Field(..., description="Target subscription or project identifier.")
    resource_id: str | None = Field(
        default=None,
        description="Optional target ARM ID or GCP resource name for single resource deep-dive.",
    )
    resource_group_filter: str | None = Field(
        default=None, description="Optional resource group or service filter."
    )
    time_window: TimeWindowPreset = Field(
        default="7d", description="Selectable historical time window."
    )
    custom_start_time: datetime | None = Field(
        default=None, description="Custom start timestamp when time_window='custom'."
    )
    custom_end_time: datetime | None = Field(
        default=None, description="Custom end timestamp when time_window='custom'."
    )
    interval: MetricInterval | None = Field(
        default=None, description="Metric aggregation interval (1m, 5m, 15m, 1h, 1d)."
    )
    force_refresh: bool = Field(
        default=False, description="Bypass cached telemetry and execute fresh provider query."
    )


class MetricDataPoint(BaseModel):
    """Individual timeseries metric observation."""

    timestamp: datetime = Field(..., description="Observation UTC timestamp.")
    value: float = Field(..., description="Observed average value.")
    min_value: float | None = Field(default=None, description="Minimum observed value in interval.")
    max_value: float | None = Field(default=None, description="Peak observed value in interval.")
    sample_count: int = Field(default=1, description="Number of aggregated samples.")


class MetricSummary(BaseModel):
    """Aggregate statistics for a metric timeseries over the query window."""

    avg: float | None = Field(default=None, description="Mean value across window.")
    max: float | None = Field(default=None, description="Peak value across window.")
    min: float | None = Field(default=None, description="Minimum value across window.")
    current: float | None = Field(default=None, description="Most recent sample value.")
    p95: float | None = Field(default=None, description="95th percentile value.")


class MetricTimeSeries(BaseModel):
    """Named timeseries sequence for a resource metric."""

    metric_name: str = Field(..., description="Native metric name (e.g. CpuPercentage).")
    display_name: str = Field(
        ..., description="Human-readable metric label (e.g. CPU Utilization)."
    )
    unit: str = Field(..., description="Unit of measurement (Percent, Bytes, Count, Seconds).")
    resource_id: str = Field(..., description="Target resource identifier.")
    resource_name: str = Field(..., description="Target resource display name.")
    data_points: list[MetricDataPoint] = Field(
        default_factory=list, description="Chronological samples."
    )
    summary: MetricSummary = Field(default_factory=MetricSummary, description="Summary statistics.")


class LogEntry(BaseModel):
    """Normalized structured log entry from Azure Activity Logs or GCP Cloud Logging."""

    id: str = Field(..., description="Unique log event identifier.")
    timestamp: datetime = Field(..., description="UTC timestamp of the log event.")
    severity: LogSeverity = Field(..., description="Standardized severity level.")
    resource_id: str = Field(..., description="Associated resource identifier.")
    resource_name: str = Field(..., description="Resource display name.")
    service_type: str = Field(..., description="Resource or service category.")
    operation_name: str = Field(..., description="Operation or action performed.")
    status: str = Field(..., description="Outcome status (e.g. Succeeded, Failed, Started).")
    message: str = Field(..., description="Human-readable log or error description.")
    error_code: str | None = Field(default=None, description="Native error code or HTTP status.")
    caller: str | None = Field(default=None, description="Initiating identity or principal.")
    correlation_id: str | None = Field(
        default=None, description="Distributed correlation / trace ID."
    )
    raw_details: dict[str, Any] = Field(
        default_factory=dict, description="Sanitized raw payload properties."
    )


class ActiveAlertItem(BaseModel):
    """Evidence-backed operational failure, threshold alert, or capacity bottleneck."""

    id: str = Field(..., description="Unique alert identifier.")
    title: str = Field(..., description="Alert headline.")
    category: Literal[
        "capacity_exhaustion",
        "high_utilization",
        "elevated_error_rate",
        "elevated_latency",
        "service_failure",
        "connection_saturation",
        "unhealthy_replica",
        "security_risk",
        "unmonitored_service",
    ] = Field(..., description="Standard operational alert category.")
    severity: AlertSeverity = Field(..., description="Alert priority level.")
    affected_resource_id: str = Field(..., description="Target resource identifier.")
    affected_resource_name: str = Field(..., description="Target resource display name.")
    hierarchy_path: str = Field(
        ..., description="Hierarchy location path (e.g. Sub / RG / Resource)."
    )
    status: Literal["active", "resolved", "acknowledged"] = Field(
        default="active", description="Operational alert status."
    )
    observation_window: str = Field(..., description="Time window evaluated.")
    supporting_evidence: str = Field(
        ..., description="Metric values or log excerpts proving the condition."
    )
    threshold_rule: str = Field(..., description="Evaluated threshold condition.")
    confidence: Literal["high", "medium", "provisional"] = Field(
        default="high", description="Assessment confidence."
    )
    urgency: Literal["urgent", "action_required", "informational"] = Field(
        default="action_required", description="Triage priority for operations teams."
    )
    first_observed: datetime = Field(..., description="Timestamp when condition first occurred.")
    last_observed: datetime = Field(..., description="Timestamp of most recent occurrence.")
    recommendation: str = Field(..., description="Recommended engineer investigation actions.")
    remediation_steps: list[str] = Field(
        default_factory=list, description="Next steps to resolve or mitigate."
    )


class ResourceHealthRecord(BaseModel):
    """Health classification for a discovered cloud resource."""

    resource_id: str = Field(..., description="Target resource identifier.")
    resource_name: str = Field(..., description="Target resource display name.")
    native_type: str = Field(..., description="Native resource type.")
    health_state: ResourceHealthState = Field(..., description="Operational health status.")
    summary: str = Field(..., description="Short explanation of current health state.")
    reason: str | None = Field(
        default=None, description="Diagnostic root reason if degraded or failing."
    )
    last_checked: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Timestamp of health check."
    )
    telemetry_source: str = Field(..., description="Source of health data.")
    resource_kind: Literal[
        "infrastructure_resource",
        "api_service",
        "configuration_metadata",
        "security_credential",
    ] = Field(
        default="infrastructure_resource",
        description="Distinction between provisioned infrastructure (VMs, DBs, Disks) and API/configuration records.",
    )


class MonitoringKPIStrip(BaseModel):
    """High-level infrastructure health and FinOps metrics for the dashboard header."""

    total_resources: int = Field(default=0, description="Total resources in scope.")
    infrastructure_resources_count: int = Field(
        default=0,
        description="Count of actual provisioned infrastructure resources (compute, databases, disks, storage).",
    )
    api_services_count: int = Field(
        default=0,
        description="Count of enabled API and service management records.",
    )
    configuration_records_count: int = Field(
        default=0,
        description="Count of project metadata, logging sinks/buckets, and credential records.",
    )
    healthy_count: int = Field(default=0, description="Resources verified healthy.")
    degraded_count: int = Field(default=0, description="Resources operating in degraded state.")
    failing_count: int = Field(default=0, description="Resources experiencing critical failures.")
    unmonitored_count: int = Field(default=0, description="Resources lacking telemetry.")
    active_alerts_count: int = Field(default=0, description="Number of currently active alerts.")
    error_event_count: int = Field(default=0, description="Total errors observed in time window.")
    error_rate_percentage: Annotated[Decimal, Field(max_digits=5, decimal_places=2)] | None = Field(
        default=None, description="Observed error rate as percentage of total operations."
    )
    telemetry_coverage_percentage: Annotated[Decimal, Field(max_digits=5, decimal_places=2)] = (
        Field(default=Decimal("0.00"), description="Percentage of resources reporting metrics.")
    )
    observed_monthly_spend: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] | None = (
        Field(default=None, description="Actual billed spend when Cost Management is linked.")
    )
    estimated_monthly_cost: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), description="Catalog-estimated monthly cost."
    )
    potential_monthly_savings: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), description="FinOps optimization savings opportunity."
    )
    technical_debt_items_count: int = Field(default=0, description="Total technical debt items.")


class ResourceGroupMonitoringSummary(BaseModel):
    """Aggregated monitoring status for a Resource Group or GCP Project."""

    group_id: str = Field(..., description="Scope identifier.")
    group_name: str = Field(..., description="Display name.")
    resource_count: int = Field(default=0, description="Total resources.")
    healthy_count: int = Field(default=0, description="Healthy resources.")
    failing_count: int = Field(default=0, description="Failing resources.")
    active_alerts_count: int = Field(default=0, description="Active alerts in group.")
    total_monthly_cost: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), description="Monthly spend/estimate."
    )
    potential_monthly_savings: Annotated[Decimal, Field(max_digits=12, decimal_places=2)] = Field(
        default=Decimal("0.00"), description="Potential savings."
    )
    telemetry_coverage_pct: Annotated[Decimal, Field(max_digits=5, decimal_places=2)] = Field(
        default=Decimal("0.00"), description="Telemetry coverage percentage."
    )


class RecurringErrorSummary(BaseModel):
    """Aggregated summary of repeated errors across the scope."""

    error_signature: str = Field(..., description="Normalized error message or operation failure.")
    error_code: str | None = Field(default=None, description="Error code.")
    affected_resources: list[str] = Field(
        default_factory=list, description="Resource names affected."
    )
    frequency: int = Field(default=1, description="Total occurrences in window.")
    first_seen: datetime = Field(..., description="Earliest occurrence in window.")
    last_seen: datetime = Field(..., description="Latest occurrence in window.")
    severity: LogSeverity = Field(default="error", description="Highest severity.")


class MonitoringOverviewResponse(BaseModel):
    """Top-level dashboard payload for centralized cloud infrastructure monitoring."""

    provider: CloudProvider = Field(..., description="Cloud provider.")
    scope_id: str = Field(..., description="Scope ID.")
    scope_name: str = Field(..., description="Scope display name.")
    time_window: str = Field(..., description="Selected query time window (e.g. 7d).")
    aggregation_interval: str = Field(
        default="1h", description="Effective metric aggregation interval used."
    )
    start_time: datetime = Field(..., description="Effective query start UTC.")
    end_time: datetime = Field(..., description="Effective query end UTC.")
    query_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Query execution UTC."
    )
    is_live: bool = Field(..., description="True if backed by live authenticated provider API.")
    data_source: str = Field(
        ..., description="Provenance label (live_authenticated or mock_fixture)."
    )
    telemetry_source: str = Field(..., description="Telemetry source explanation.")
    kpis: MonitoringKPIStrip = Field(..., description="KPI strip data.")
    cpu_utilization_series: list[MetricTimeSeries] = Field(
        default_factory=list, description="CPU utilization timeseries for top compute resources."
    )
    memory_utilization_series: list[MetricTimeSeries] = Field(
        default_factory=list, description="Memory utilization timeseries where supported."
    )
    error_rate_series: list[MetricTimeSeries] = Field(
        default_factory=list, description="Chronological error occurrence counts."
    )
    active_alerts: list[ActiveAlertItem] = Field(
        default_factory=list, description="Active alerts and bottlenecks."
    )
    recent_failures: list[LogEntry] = Field(
        default_factory=list, description="Chronological error and failure events."
    )
    recurring_errors: list[RecurringErrorSummary] = Field(
        default_factory=list, description="Top recurring error clusters."
    )
    health_records: list[ResourceHealthRecord] = Field(
        default_factory=list, description="Health records for discovered resources."
    )
    resource_groups_summary: list[ResourceGroupMonitoringSummary] = Field(
        default_factory=list, description="Resource group level monitoring rollups."
    )
    limitations_and_gaps: list[str] = Field(
        default_factory=list, description="Explicit monitoring limitations and missing settings."
    )


class ResourceDetailMonitoringResponse(BaseModel):
    """Comprehensive 7-tab operational and FinOps deep dive for an individual cloud service."""

    resource: DiscoveredResource = Field(
        ..., description="Normalized resource configuration and metadata."
    )
    health: ResourceHealthRecord = Field(..., description="Authoritative health status.")
    time_window: str = Field(..., description="Evaluated time window.")
    aggregation_interval: str = Field(..., description="Metric interval used.")
    start_time: datetime = Field(..., description="Start of window.")
    end_time: datetime = Field(..., description="End of window.")
    metrics: list[MetricTimeSeries] = Field(
        default_factory=list, description="Resource-specific metric timeseries."
    )
    logs: list[LogEntry] = Field(
        default_factory=list, description="Resource-scoped logs and audit events."
    )
    alerts: list[ActiveAlertItem] = Field(
        default_factory=list, description="Alerts specifically targeting this resource."
    )
    dependencies: list[dict[str, Any]] = Field(
        default_factory=list, description="Topology relationships and architectural dependencies."
    )
    cost_and_utilization: dict[str, Any] = Field(
        default_factory=dict, description="Spend attribution and sizing metrics."
    )
    waste_findings: list[ResourceWasteFinding] = Field(
        default_factory=list, description="FinOps waste findings for this resource."
    )
    technical_debt_items: list[TechnicalDebtItem] = Field(
        default_factory=list, description="Technical debt items for this resource."
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Missing telemetry signals or unconfigured diagnostic settings.",
    )


class LogSearchResponse(BaseModel):
    """Paginated and filtered log search response."""

    total_matched: int = Field(..., description="Total matching log events.")
    page_size: int = Field(..., description="Max results returned.")
    logs: list[LogEntry] = Field(default_factory=list, description="Filtered log entries.")
    recurring_summaries: list[RecurringErrorSummary] = Field(
        default_factory=list, description="Top recurring error patterns."
    )
    query_window: str = Field(..., description="Time window evaluated.")
    limitations: list[str] = Field(default_factory=list, description="Logging limitations or gaps.")
