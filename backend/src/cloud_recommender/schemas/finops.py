"""FinOps domain schemas for Azure Databricks FinOps Command Center.

Defines certified KPI structures, module responses, and audit records matching
the 15-module FinOps Command Center specification.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class KpiStatus(StrEnum):
    """Certified status of a KPI metric."""

    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    NO_DATA = "NO_DATA"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNSUPPORTED = "UNSUPPORTED"
    STALE = "STALE"
    ERROR = "ERROR"
    LIVE = "LIVE"
    BASELINE = "BASELINE"
    ESTIMATED = "ESTIMATED"
    STOPPED_WAREHOUSE = "STOPPED_WAREHOUSE"
    UNAVAILABLE = "UNAVAILABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    NO_DATA_AVAILABLE = "NO_DATA_AVAILABLE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    NOT_ATTRIBUTABLE = "NOT_ATTRIBUTABLE"


class KpiMetric(BaseModel):
    """Canonical structure for any FinOps KPI metric with lineage, unit governance, and limitations."""

    value: float | None = Field(
        default=None, description="Numerical value of the metric; null when no measurement exists"
    )
    formatted_value: str = Field(..., description="Display string e.g. '$176,840' or '22%'")
    unit: str = Field(..., description="Metric unit: USD, DBU, %, TB, items, tokens, etc.")
    currency: str | None = Field(
        default="USD", description="Currency if applicable (None for DBUs, tokens, counts)"
    )
    metric_id: str | None = Field(default=None, description="Canonical metric identifier")
    period_start: str | None = Field(default=None, description="Start date of metric period")
    period_end: str | None = Field(default=None, description="End date of metric period")
    comparison_value: float | None = Field(default=None, description="Prior period value")
    change_absolute: float | None = Field(default=None, description="Absolute difference")
    change_percentage: float | None = Field(default=None, description="Percentage change")
    delta_label: str | None = Field(
        default=None, description="Label e.g. '↑ 8.4% vs previous period'"
    )
    is_favorable: bool | None = Field(
        default=None, description="True if green, False if red, None if neutral"
    )
    status: KpiStatus = Field(default=KpiStatus.BASELINE, description="Data availability status")
    data_freshness: str = Field(default="Historical Baseline", description="Freshness summary")
    source: str = Field(..., description="Lineage source e.g. 'Azure Databricks SDK'")
    workspace_id: str = Field(..., description="Workspace ID associated with calculation")
    resource_type: str | None = Field(default=None, description="Resource type scope filter")
    resource_id: str | None = Field(default=None, description="Child resource ID scope filter")
    data_source: str | None = Field(default=None, description="Underlying telemetry data source")
    last_refreshed: str | None = Field(
        default=None, description="ISO timestamp of last calculation"
    )
    aggregation_method: str | None = Field(
        default=None, description="Aggregation function (SUM, AVG, BLENDED)"
    )
    formula: str | None = Field(default=None, description="Formula used for derived calculations")
    record_count: int | None = Field(
        default=None, description="Number of underlying records aggregated"
    )
    caveats: str | None = Field(default=None, description="Known exclusions or data caveats")
    configuration_version: int = Field(
        default=1, description="Resource scope configuration version"
    )
    calculation_version: str = Field(default="v2.0.0-canonical", description="Algorithm version")
    coverage: float = Field(default=1.0, ge=0.0, le=1.0, description="Completeness ratio 0-1")
    limitations: str | None = Field(default=None, description="Known exclusions or data caveats")


class CanonicalKpiResponse(BaseModel):
    """Certified canonical KPI query response."""

    metric_id: str = Field(..., description="Canonical KPI identifier")
    metric: KpiMetric = Field(..., description="Canonical metric details")


# 1. Executive Cost Overview
class CostDriverItem(BaseModel):
    driver: str
    workspace_owner: str
    spend: float
    formatted_spend: str
    change: str
    signal: str  # Review, High, Stable


class DecisionItem(BaseModel):
    id: str
    priority: int
    title: str
    description: str
    estimated_savings_monthly: float
    formatted_savings: str
    impact: str  # High impact, Medium risk, Low risk
    status: str  # Approval required, Approved, Deferred, Implemented
    confidence_pct: int
    effort: str
    owner: str
    evidence: str
    # Master Roadmap Lifecycle & Governance Enhancements
    category: str = Field(default="Compute", description="Optimization category")
    resource_name: str = Field(default="", description="Target resource name")
    resource_id: str = Field(default="", description="Target resource ID")
    finding: str = Field(default="", description="Detailed inefficiency finding")
    current_cost: str = Field(default="", description="Current observed spend")
    potential_savings_range: str = Field(
        default="", description="Estimated potential savings range"
    )
    verified_realized_savings: float = Field(
        default=0.0,
        description="Post-implementation verified realized savings (strictly zero until post-implementation audit)",
    )
    formatted_realized_savings: str = Field(
        default="$0.00 (Unverified)", description="Formatted verified savings"
    )
    performance_impact: str = Field(default="None", description="Expected performance impact")
    risk: str = Field(default="Low", description="Risk level (Low, Medium, High)")
    complexity: str = Field(default="Low", description="Implementation complexity")
    validation_method: str = Field(default="", description="Procedure to verify savings")
    lifecycle_stage: str = Field(
        default="Detected",
        description="Lifecycle: Detected, Analyzed, Approved, Scheduled, Implemented, Verified, Rejected, Deferred",
    )
    calculation_methodology: str = Field(
        default="", description="Formula and telemetry source used to calculate estimated savings"
    )
    recommended_action: str = Field(
        default="", description="Specific procedural action recommended"
    )


class ExecutiveOverviewResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    spend_trend: list[dict[str, Any]]
    spend_composition: list[dict[str, Any]]
    top_cost_drivers: list[CostDriverItem]
    decisions_requiring_attention: list[DecisionItem]
    global_filters: dict[str, Any]


# 2. Cost Explorer
class CostExplorerItem(BaseModel):
    date: str
    product: str
    sku: str
    workspace: str
    usage_qty: float
    unit: str
    list_cost: float
    effective_cost: float
    owner_tag: str
    allocation_status: str  # Allocated, Partial, Unallocated


class CostExplorerResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    daily_trend: list[dict[str, Any]]
    cost_by_product_family: list[dict[str, Any]]
    billing_ledger: list[CostExplorerItem]


# 3. Cost Allocation
class AllocationRuleItem(BaseModel):
    priority: int
    rule_name: str
    match_condition: str
    allocation_target: str
    method: str
    status: str


class CostAllocationResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    spend_by_bu: list[dict[str, Any]]
    allocation_completeness: dict[str, int]
    rulebook: list[AllocationRuleItem]


# 4. Compute & Warehouses
class ClusterInventoryItem(BaseModel):
    cluster_id: str
    name: str
    type: str  # Job, All-purpose
    owner: str
    node_profile: str
    runtime_hrs: float
    cpu_utilization: str
    dbu_mtd: float
    cost_mtd: float
    state: str
    finding: str  # Oversized, Idle windows, Efficient, Healthy


class WarehouseInventoryItem(BaseModel):
    warehouse_id: str
    name: str
    warehouse_class: str  # Serverless, Pro, Classic
    size: str
    uptime: str
    avg_utilization: str
    queue_p95: str
    auto_stop_mins: int
    cost_mtd: float
    state: str
    recommendation: str


class JobEfficiencyItem(BaseModel):
    job_id: str
    name: str
    runs: int
    success_rate: str
    retries: int
    avg_duration: str
    dbu_per_run: float
    cost_per_run: float
    cost_per_tb: float
    signal: str


class ComputeWarehousesResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    clusters: list[ClusterInventoryItem]
    warehouses: list[WarehouseInventoryItem]
    jobs: list[JobEfficiencyItem]
    heatmap_utilization: list[int]  # 168 integers for hourly 7-day heatmap


# 5. AI & Token Economics
class ModelEconomicsItem(BaseModel):
    model_name: str
    serving_mode: str
    input_tokens: str
    output_tokens: str
    cached_tokens: str
    requests: str
    cost_mtd: float
    avg_latency: str
    cost_per_1k_output: str


class ModelServingEndpointItem(BaseModel):
    endpoint_name: str
    model: str
    serving_type: str
    requests_per_day: str
    capacity_utilization: str
    p95_latency: str
    availability: str
    monthly_cost: float
    action: str


class GenieSpaceScorecardItem(BaseModel):
    space_name: str
    business_owner: str
    questions: int
    answer_rate: str
    warehouse: str
    spend: float
    cost_per_success: str
    quality_score: int


class AgentEconomicsItem(BaseModel):
    agent_name: str
    runs: int
    success_rate: str
    avg_steps: float
    llm_cost: float
    tool_cost: float
    total_cost: float
    cost_per_success: str
    outcome: str


class TrainingEvaluationItem(BaseModel):
    experiment_name: str
    workload: str
    compute_hrs: str
    runs: int
    artifact_storage: str
    spend: float
    quality_lift: str
    decision: str


class AiEconomicsResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    token_consumption_by_model: list[dict[str, Any]]
    token_cost_drivers: list[dict[str, Any]]
    model_economics: list[ModelEconomicsItem]
    serving_endpoints: list[ModelServingEndpointItem]
    genie_scorecard: list[GenieSpaceScorecardItem]
    agents: list[AgentEconomicsItem]
    training: list[TrainingEvaluationItem]
    unit_economics: list[dict[str, Any]]


# 6. Data & Storage
class StorageInventoryItem(BaseModel):
    catalog_schema_table: str
    storage_type: str
    size: str
    last_read: str
    retention: str
    growth_month: str
    monthly_cost: float
    recommendation: str


class DataStorageResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    storage_tiers: list[dict[str, Any]]
    lifecycle_opportunities: list[dict[str, Any]]
    tables: list[StorageInventoryItem]


# 7. Network & Cloud Infrastructure
class CloudInfrastructureItem(BaseModel):
    provider: str
    service: str
    resource: str
    region: str
    usage_driver: str
    cost_mtd: float
    allocation: str
    opportunity: str


class NetworkCloudResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    components: list[CloudInfrastructureItem]


# 8. Optimization Advisor
class RecommendationActionRequest(BaseModel):
    action: str = Field(..., description="Action: Approved, Deferred, New, Implemented")
    notes: str | None = Field(default=None, description="Review notes or justification")


class OptimizationAdvisorResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    recommendations: list[DecisionItem]


# 9. Forecast & Budgets
class ScenarioSimulationRequest(BaseModel):
    compute_save_pct: float = Field(default=10.0, ge=0.0, le=50.0)
    token_save_pct: float = Field(default=15.0, ge=0.0, le=70.0)
    growth_pct: float = Field(default=8.0, ge=-20.0, le=100.0)


class ScenarioSimulationResponse(BaseModel):
    baseline_spend: float
    adjusted_spend: float
    formatted_spend: str
    savings_vs_baseline: float
    delta_label: str
    is_favorable: bool
    budget_variance: float


class BudgetControlItem(BaseModel):
    budget_scope: str
    owner: str
    budget: float
    actual: float
    forecast: float
    threshold: str
    burn_pct: int
    status: str


class ForecastBudgetsResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    budget_burn: list[dict[str, Any]]
    budget_controls: list[BudgetControlItem]
    default_scenario: ScenarioSimulationResponse


# 10. Anomaly Detection
class AnomalyItem(BaseModel):
    id: str
    detected: str
    severity: str  # Critical, High, Medium, Low
    signal: str
    resource: str
    baseline: str
    observed: str
    estimated_impact: str
    likely_cause: str
    evidence_detail: str
    # Master Roadmap Forensic Investigation Enhancements
    resource_type: str = Field(
        default="cluster",
        description="Resource type (cluster, warehouse, model_serving, app, job)",
    )
    workspace_id: str = Field(default="642006393507276", description="Databricks workspace ID")
    metric: str = Field(default="Spend / Day", description="Deviating metric")
    absolute_deviation: str = Field(default="", description="Absolute numerical deviation")
    percentage_deviation: str = Field(default="", description="Percentage deviation from baseline")
    detection_methodology: str = Field(
        default="Statistical Z-Score (>2.5 SD from historical baseline)",
        description="Detection method",
    )
    confidence: str = Field(default="High (92%)", description="Detection confidence")
    status: str = Field(
        default="New",
        description="Lifecycle state: New, Investigating, Acknowledged, Resolved, False positive",
    )
    root_cause_hypotheses: list[str] = Field(
        default_factory=list, description="Candidate root causes"
    )
    ai_explanation: str = Field(default="", description="Grounded AI explanation")
    recommended_action: str = Field(default="", description="Corrective action recommendation")
    potential_savings: str = Field(default="", description="Potential savings from resolution")
    verification_procedure: str = Field(default="", description="Verification procedure")
    historical_trend: list[dict[str, Any]] = Field(
        default_factory=list, description="Historical data points"
    )
    sku_contribution: list[dict[str, Any]] = Field(
        default_factory=list, description="SKU breakdown of anomaly"
    )
    related_workloads: list[str] = Field(
        default_factory=list, description="Attributable jobs/notebooks/queries"
    )


class AnomalyStatusUpdateRequest(BaseModel):
    status: str = Field(
        ...,
        description="Updated anomaly state: New, Investigating, Acknowledged, Resolved, False positive",
    )


class AnomalyDetectionResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    anomalies: list[AnomalyItem]


# -----------------------------------------------------------------------------
# Module AI Analysis & Optimization Intelligence Layer
# -----------------------------------------------------------------------------


class FinOpsAiOpportunity(BaseModel):
    title: str = Field(..., description="Opportunity title")
    description: str = Field(..., description="Actionable description")
    resource_id: str = Field(default="", description="Affected resource ID")
    estimated_savings: str = Field(..., description="Estimated monthly savings")
    effort: str = Field(default="Low", description="Implementation effort")
    risk: str = Field(default="Low", description="Risk level")
    confidence_pct: int = Field(default=85, description="Confidence percentage")


class FinOpsAiAnalysis(BaseModel):
    """Structured, evidence-grounded AI analysis for a FinOps module."""

    module_id: str = Field(..., description="FinOps module identifier")
    workspace_id: str = Field(..., description="Databricks workspace identifier")
    executive_summary: str = Field(..., description="Executive narrative summary")
    important_findings: list[str] = Field(
        default_factory=list, description="Key operational findings"
    )
    cost_drivers: list[str] = Field(default_factory=list, description="Primary cost drivers")
    unusual_changes: list[str] = Field(
        default_factory=list, description="Unusual spikes or pattern changes"
    )
    optimization_opportunities: list[FinOpsAiOpportunity] = Field(
        default_factory=list, description="Targeted optimization actions"
    )
    expected_savings: str = Field(..., description="Total projected monthly savings")
    risk_assessment: str = Field(..., description="Comprehensive risk evaluation")
    data_quality_warnings: list[str] = Field(
        default_factory=list, description="Data availability or attribution warnings"
    )
    suggested_investigations: list[str] = Field(
        default_factory=list, description="Recommended next investigations"
    )
    confidence_score: float = Field(
        default=0.92, description="Algorithmic confidence score (0.0 to 1.0)"
    )
    source_references: list[str] = Field(
        default_factory=list, description="Authoritative data sources"
    )
    analysis_timestamp: str = Field(..., description="ISO 8601 analysis generation timestamp")
    is_ai_live: bool = Field(
        default=False,
        description="Whether generated by live LLM or deterministic rule-engine fallback",
    )


# 11. Governance & Policies
class PolicyCatalogueItem(BaseModel):
    policy_name: str
    scope: str
    control: str
    enforcement: str
    owner: str
    exceptions: int
    status: str


class GovernancePoliciesResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    policies: list[PolicyCatalogueItem]
    checklist: list[dict[str, Any]]
    workflow_steps: list[str]


# 12. Showback & Chargeback
class ChargebackStatementItem(BaseModel):
    business_unit: str
    direct_compute: float
    ai_tokens: float
    storage: float
    shared_allocation: float
    total: float
    budget_variance: str
    trend: str


class ShowbackChargebackResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    statements: list[ChargebackStatementItem]


# 13. Workload Economics
class WorkloadUnitEconomicsItem(BaseModel):
    workload: str
    workload_type: str
    owner: str
    monthly_spend: float
    volume: str
    unit_cost: str
    sla_quality: str
    business_outcome: str
    efficiency_trend: str


class WorkloadEconomicsResponse(BaseModel):
    kpis: dict[str, KpiMetric]
    workloads: list[WorkloadUnitEconomicsItem]


# 14. Reports & Audit
class ReportPackItem(BaseModel):
    report_id: str
    title: str
    subtitle: str
    format: str


class AuditEventItem(BaseModel):
    timestamp: str
    actor: str
    event: str
    resource: str
    before: str
    after: str
    approval_ref: str


class ReportsAuditResponse(BaseModel):
    report_packs: list[ReportPackItem]
    audit_events: list[AuditEventItem]


# 15. Settings & Integrations
class ConnectedSourceItem(BaseModel):
    source_name: str
    status: str  # Connected, Partial, Needs validation, Unconfigured
    last_verified: str
    details: str


class PipelineHealthMetric(BaseModel):
    metric_name: str
    metric_value: str


class RateCardItem(BaseModel):
    provider: str
    sku_family: str
    region: str
    list_rate: str
    contract_rate: str
    discount: str
    effective_date: str
    source: str


class SettingsIntegrationsResponse(BaseModel):
    connected_sources: list[ConnectedSourceItem]
    pipeline_health: list[PipelineHealthMetric]
    rate_cards: list[RateCardItem]
    system_tables_readiness: dict[str, Any]


# 16. Query History Explorer (system.query.history)
class QueryHistoryRecordItem(BaseModel):
    query_id: str
    start_time: str
    duration_ms: float
    duration_formatted: str
    status: str  # FINISHED, FAILED, CANCELLED
    warehouse_id: str
    warehouse_name: str
    rows_produced: int
    bytes_read: int
    bytes_written: int
    user: str
    sql_statement: str
    query_type: str
    cost_correlation_dbu: float | None = None
    error_message: str | None = None


class QueryHistoryResponse(BaseModel):
    records: list[QueryHistoryRecordItem]
    total_count: int
    duration_histogram: list[dict[str, Any]]
    status_distribution: list[dict[str, Any]]
    daily_volume: list[dict[str, Any]]
    active_filters: dict[str, Any]


# 17. System Tables Explorer
class SystemTableProbeItem(BaseModel):
    table_name: str
    catalog: str
    schema_name: str
    description: str
    status: str  # SCHEMA_VERIFIED, QUERY_ACCESSIBLE, DATA_AVAILABLE, NO_DATA, PERMISSION_DENIED, STOPPED_WAREHOUSE
    columns_count: int
    columns: list[dict[str, str]]
    row_count: int | None = None
    latest_record_time: str | None = None
    query_duration_ms: float | None = None
    notes: str
    sample_records: list[dict[str, Any]] = []


class SystemTablesExplorerResponse(BaseModel):
    tables: list[SystemTableProbeItem]
    catalog_status: str
    warehouse_state: str
    governance_model: str
