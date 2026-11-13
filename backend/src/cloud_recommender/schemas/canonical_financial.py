"""Canonical multi-cloud financial data model schemas.

Implements consistent, FOCUS-aligned representations for all supported cloud providers:
- Billing usage and price records with strict idempotency keys
- Data freshness classifications (LIVE, CACHED, ESTIMATED, SOURCE_UNAVAILABLE, NOT_AUTHORIZED, INSUFFICIENT_HISTORY)
- Budget records, forecast snapshots, cost allocations, and optimization decisions
- Strict Decimal arithmetic compatibility and unit separation
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DataFreshnessStatus(StrEnum):
    """Authoritative data freshness classification for financial telemetry."""

    LIVE = "LIVE"
    INGESTED_HISTORICAL = "INGESTED_HISTORICAL"
    CACHED = "CACHED"
    ESTIMATED = "ESTIMATED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    NOT_ATTRIBUTABLE = "NOT_ATTRIBUTABLE"


class FinancialLifecycleStage(StrEnum):
    """Lifecycle stage for FinOps optimization savings."""

    POTENTIAL = "POTENTIAL"
    ESTIMATED = "ESTIMATED"
    APPROVED = "APPROVED"
    IMPLEMENTED = "IMPLEMENTED"
    REALIZED = "REALIZED"
    VERIFIED = "VERIFIED"


class CanonicalBillingRecord(BaseModel):
    """Universal normalized billing record preserving provider source identity and lineage."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    record_id: str = Field(..., description="Unique provider billing event ID; idempotency key")
    provider: str = Field(..., description="Cloud provider ('databricks', 'azure', 'aws', 'gcp')")
    billing_account_id: str | None = Field(default=None, description="Billing account / enrollment")
    subscription_id: str | None = Field(default=None, description="Cloud subscription ID")
    workspace_id: str | None = Field(default=None, description="Databricks workspace ID")
    resource_id: str = Field(..., description="Cloud resource URI / identifier")
    resource_name: str | None = Field(default=None, description="Human-readable resource name")
    service_category: str = Field(
        ..., description="Standardized category: Compute, Storage, Network, AI, Database, Other"
    )
    service_name: str = Field(
        ..., description="Provider service e.g. 'Azure Databricks', 'Storage'"
    )
    sku_name: str = Field(..., description="Commercial SKU e.g. 'SERVERLESS_SQL_COMPUTE'")
    usage_start_time: datetime = Field(..., description="Start of metering window in UTC")
    usage_end_time: datetime = Field(..., description="End of metering window in UTC")
    usage_date: str = Field(..., description="Billing date YYYY-MM-DD")
    usage_quantity: Decimal = Field(..., description="Metered usage; negative indicates retraction")
    usage_unit: str = Field(..., description="Measurement unit (DBU, TB-month, GB, Requests)")
    list_unit_price: Decimal | None = Field(default=None, description="Rate card price per unit")
    billed_cost: Decimal | None = Field(default=None, description="Raw unadjusted invoice cost")
    effective_cost: Decimal = Field(
        ..., description="Reconciled effective cost after rate matching"
    )
    currency: str = Field(default="USD", description="Currency code (ISO 4217)")
    pricing_matched: bool = Field(
        default=True, description="True if matched to authoritative rates"
    )
    is_retraction: bool = Field(default=False, description="True if usage_quantity < 0")
    is_embedded_in_platform: bool = Field(
        default=False,
        description="True if already accounted for in Databricks DBU spend (e.g. Model Serving)",
    )
    tags: dict[str, str] = Field(default_factory=dict, description="Resource / FinOps tags")
    source_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp recorded by cloud provider",
    )
    ingestion_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp record was ingested into FinOps store",
    )
    data_quality_status: DataFreshnessStatus = Field(
        default=DataFreshnessStatus.CACHED,
        description="Freshness and reliability classification",
    )


class CanonicalBudgetRecord(BaseModel):
    """Configured budget allocation with period, scope, and threshold policies."""

    budget_id: str = Field(..., description="Unique budget identifier")
    scope_level: str = Field(..., description="Scope tier: Organization, Workspace, Resource")
    scope_id: str = Field(..., description="Identifier of the scoped entity")
    period_start: str = Field(..., description="Start of budget cycle YYYY-MM-DD")
    period_end: str = Field(..., description="End of budget cycle YYYY-MM-DD")
    budget_amount: Decimal = Field(..., description="Approved budget ceiling")
    currency: str = Field(default="USD", description="Currency code")
    owner: str = Field(..., description="Responsible team or business unit")
    alert_thresholds: list[float] = Field(
        default_factory=lambda: [80.0, 90.0, 100.0],
        description="Notification trigger thresholds in percentage",
    )


class CanonicalForecastSnapshot(BaseModel):
    """Persisted forecast snapshot for auditable historical MAPE accuracy tracking."""

    snapshot_id: str = Field(..., description="Unique forecast snapshot identifier")
    workspace_id: str = Field(..., description="Target workspace ID")
    snapshot_date: str = Field(..., description="Date snapshot was taken YYYY-MM-DD")
    target_billing_period: str = Field(
        ..., description="Billing period forecast applies to YYYY-MM"
    )
    projected_amount: Decimal = Field(..., description="Forecasted month-end expenditure")
    actual_final_amount: Decimal | None = Field(
        default=None, description="Actual closed expenditure after period completes"
    )
    currency: str = Field(default="USD", description="Currency code")
    model_methodology: str = Field(
        default="Linear Velocity Regression", description="Algorithm applied"
    )
    is_period_closed: bool = Field(
        default=False, description="True once actual billing period has concluded"
    )

    @property
    def absolute_percentage_error(self) -> float | None:
        """Calculate MAPE for closed billing period."""
        if not self.is_period_closed or self.actual_final_amount is None:
            return None
        if self.actual_final_amount == Decimal("0"):
            return 0.0
        err = abs(self.projected_amount - self.actual_final_amount)
        return float((err / self.actual_final_amount) * 100)


class CanonicalAnomalyRecord(BaseModel):
    """Spending anomaly detected via statistical distribution deviation."""

    anomaly_id: str = Field(..., description="Unique anomaly identifier")
    workspace_id: str = Field(..., description="Affected workspace ID")
    resource_id: str = Field(..., description="Affected cloud resource ID")
    resource_name: str = Field(..., description="Display name of resource")
    detected_at: datetime = Field(..., description="Timestamp anomaly was flagged in UTC")
    metric_name: str = Field(..., description="Observed metric e.g. DBU/hr, Tokens/hr")
    baseline_value: float = Field(..., description="Expected baseline level")
    observed_value: float = Field(..., description="Actual spike value")
    z_score: float = Field(..., description="Number of standard deviations from mean")
    estimated_daily_impact_usd: Decimal = Field(..., description="Daily financial exposure")
    status: str = Field(default="OPEN", description="OPEN, ACKNOWLEDGED, RESOLVED")
    root_cause_diagnosis: str = Field(..., description="Technical telemetry explanation")


class CanonicalOptimizationDecision(BaseModel):
    """Optimization initiative with verifiable telemetry and strict savings lifecycle."""

    decision_id: str = Field(..., description="Unique recommendation identifier")
    workspace_id: str = Field(..., description="Target workspace ID")
    resource_id: str = Field(..., description="Target resource ID")
    resource_name: str = Field(..., description="Human-readable resource label")
    recommendation_type: str = Field(
        ..., description="RIGHTSIZING, IDLE_SHUTDOWN, CACHING, TIERING"
    )
    efficiency_gap: str = Field(..., description="Identified telemetry inefficiency")
    recommended_action: str = Field(..., description="Actionable change runbook")
    estimated_monthly_savings: Decimal = Field(
        ..., description="Projected monthly savings if applied"
    )
    realized_monthly_savings: Decimal = Field(
        default=Decimal("0.00"),
        description="Actual verified savings post-implementation (starts strictly at $0.00)",
    )
    currency: str = Field(default="USD", description="Currency code")
    lifecycle_stage: FinancialLifecycleStage = Field(
        default=FinancialLifecycleStage.POTENTIAL,
        description="POTENTIAL -> ESTIMATED -> APPROVED -> IMPLEMENTED -> REALIZED",
    )
    requires_approval: bool = Field(default=True, description="Strict human gate enforcement")


class ComponentSpendCoverage(BaseModel):
    """Spend component coverage, eligibility, and lineage status."""

    component_name: str = Field(
        ..., description="e.g., 'Databricks Compute', 'Azure Storage', 'Azure Network'"
    )
    reported_amount: Decimal | None = Field(
        default=None, description="Reported or baseline amount; None if unknown"
    )
    currency: str = Field(default="USD", description="Currency code (ISO 4217)")
    freshness_status: DataFreshnessStatus = Field(..., description="Source freshness status")
    is_eligible_for_actuals: bool = Field(
        ...,
        description="True ONLY if verified LIVE or INGESTED_HISTORICAL record evidence exists",
    )
    lineage_source: str = Field(..., description="Authoritative origin table, API, or ledger")
    record_count: int = Field(default=0, description="Number of underlying billing records")
    notes: str = Field(default="", description="Audit disclosure or rationale for exclusion")


class SubscriptionSpendAggregation(BaseModel):
    """Rigorous subscription expenditure aggregation with explicit partial total accounting."""

    period_start: str = Field(..., description="Billing window start YYYY-MM-DD")
    period_end: str = Field(..., description="Billing window end YYYY-MM-DD")
    currency: str = Field(default="USD", description="Currency code (ISO 4217)")

    verified_actual_spend: Decimal = Field(
        ...,
        description="Strict sum of verified eligible records only; excludes unverified and unavailable",
    )
    is_partial_total: bool = Field(
        ...,
        description="True when any component is SOURCE_UNAVAILABLE, ESTIMATED, or unverified",
    )
    completeness_percentage: float = Field(
        ..., description="Percentage of components or estimated total verified (0.0 to 100.0)"
    )
    components: list[ComponentSpendCoverage] = Field(
        default_factory=list, description="Per-component status and lineage breakdown"
    )
    audit_notes: list[str] = Field(
        default_factory=list, description="Explicit accounting disclosures and coverage caveats"
    )


def generate_canonical_idempotency_key(
    provider: str,
    record_id: str | None = None,
    subscription_id: str | None = None,
    resource_id: str | None = None,
    usage_date: str | None = None,
    sku_name: str | None = None,
    meter_category: str | None = None,
) -> str:
    """Generate collision-resistant idempotency key preferring provider-native stable record identifiers.

    Why provider-native IDs are mandatory:
    Two legitimate transactions in cloud billing can share identical timestamp, SKU, resource,
    and usage quantity (e.g. concurrent serverless queries, identical micro-tasks). A hash of
    financial attributes alone would cause false-positive collision and drop valid transactions.
    When a stable provider event ID exists (Databricks record_id, Azure usage event ID), it
    MUST be the primary key.
    """
    if record_id and str(record_id).strip():
        return f"{provider.lower()}:{str(record_id).strip()}"

    parts = [
        provider.lower(),
        (subscription_id or "nosub").lower(),
        (resource_id or "nores").lower(),
        usage_date or "nodate",
        (sku_name or meter_category or "nosku").lower(),
    ]
    import hashlib

    composite_str = ":".join(parts)
    digest = hashlib.sha256(composite_str.encode("utf-8")).hexdigest()[:16]
    return f"{provider.lower()}:composite:{digest}"
