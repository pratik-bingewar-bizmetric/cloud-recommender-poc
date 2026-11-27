"""Domain schemas and API contracts for AWS authentication, connectivity, resource discovery, and findings.

Strict Security Invariants:
1. Secret Access Keys, Session Tokens, and SigV4 signing keys are NEVER exposed in response models.
2. Only safe identifiers (account_id, arn, role_name, key_id_suffix) are serialized to clients.
3. Billing is explicitly DEFERRED / READ-ONLY (zero-mutation; never hallucinates or modifies cloud resources).
4. All findings are strictly advisory with explicit severity, evidence, and verification status.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AwsServiceConnectivityState(StrEnum):
    """Standardized connectivity status for each AWS service API."""

    SUCCESS = "SUCCESS"
    API_DISABLED = "API_DISABLED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DEFERRED = "DEFERRED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_TESTED = "NOT_TESTED"


class AwsFindingSeverity(StrEnum):
    """Severity classification for architectural and FinOps findings."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


class AwsEvidenceClassification(StrEnum):
    """Explicit evidence classification standard for findings."""

    VERIFIED_LIVE = "VERIFIED_LIVE"
    VERIFIED_MOCK = "VERIFIED_MOCK"
    INFERRED = "INFERRED"
    NOT_VERIFIED = "NOT_VERIFIED"


class AwsServiceStatus(BaseModel):
    """Granular connectivity and permission report for a specific AWS service API."""

    model_config = ConfigDict(frozen=True)

    service: str = Field(
        ...,
        description=(
            "Service identifier: sts | iam | ec2 | s3 | rds | lambda | ecs | eks | "
            "elb | cloudwatch | cost_explorer | pricing"
        ),
    )
    service_name: str = Field(..., description="Human-readable service title.")
    status: AwsServiceConnectivityState = Field(
        ..., description="Standardized connectivity/permission state."
    )
    api_endpoint: str = Field(..., description="Target AWS endpoint or service domain.")
    required_role_or_permission: str | None = Field(
        default=None, description="Recommended IAM action or policy required for access."
    )
    message: str | None = Field(
        default=None, description="Actionable explanation or diagnostic message."
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Safe operational metadata (counts, regions, versions)."
    )


class AwsAccountIdentity(BaseModel):
    """Non-sensitive caller identity and account metadata extracted from AWS STS."""

    model_config = ConfigDict(frozen=True)

    account_id: str = Field(..., description="12-digit AWS Account ID.")
    arn: str = Field(..., description="Authenticated IAM Principal ARN.")
    user_id: str = Field(..., description="Unique AWS principal identifier.")
    account_alias: str | None = Field(default=None, description="Friendly account alias if set.")
    default_region: str = Field(default="eu-north-1", description="Default configured AWS region.")
    auth_method: str = Field(..., description="Authentication method (profile, role_arn, keys).")


class AwsRegionInfo(BaseModel):
    """Discovered AWS region information."""

    region_name: str = Field(..., description="Region code (e.g. eu-north-1, us-east-1).")
    opt_in_status: str = Field(
        default="opt-in-not-required",
        description="opt-in-not-required | opted-in | not-opted-in",
    )
    is_default: bool = Field(default=False, description="True if this is the default region.")


class AwsTestConnectionRequest(BaseModel):
    """Request payload for testing AWS connectivity WITHOUT persisting credentials."""

    connection_name: str = Field(
        default="AWS Production",
        min_length=2,
        max_length=100,
        description="Friendly connection label.",
    )
    account_id: str = Field(
        ...,
        min_length=12,
        max_length=12,
        pattern=r"^\d{12}$",
        description="12-digit AWS Account ID.",
    )
    default_region: str = Field(
        default="eu-north-1",
        description="Default AWS region to test.",
    )
    auth_method: Literal["profile", "role_arn", "access_keys", "instance_role"] = Field(
        default="profile",
        description="Authentication mechanism.",
    )
    profile_name: str | None = Field(
        default=None,
        description="AWS CLI profile name (e.g. finops-dev) for local development.",
    )
    role_arn: str | None = Field(
        default=None,
        description="IAM Role ARN for AssumeRole authentication.",
    )
    external_id: str | None = Field(
        default=None,
        description="External ID for IAM role assumption.",
    )
    access_key_id: str | None = Field(
        default=None,
        description="Temporary AWS Access Key ID.",
    )
    secret_access_key: str | None = Field(
        default=None,
        description="Temporary AWS Secret Access Key.",
    )
    session_token: str | None = Field(
        default=None,
        description="AWS Session Token for temporary credentials.",
    )


class AwsTestConnectionResponse(BaseModel):
    """Safe response from connection test with granular per-service statuses."""

    success: bool = Field(..., description="True if authentication and STS identity succeeded.")
    account_id: str = Field(..., description="Target AWS Account ID.")
    arn: str = Field(..., description="Authenticated IAM Principal ARN.")
    default_region: str = Field(..., description="Target default region.")
    overall_status: str = Field(
        ...,
        description="Connected | Partially Connected | Authentication Failed | Access Denied",
    )
    billing_status: Literal["DEFERRED", "READ_ONLY", "NOT_CONFIGURED"] = Field(
        default="DEFERRED",
        description="Billing status: DEFERRED or READ_ONLY.",
    )
    services: list[AwsServiceStatus] = Field(
        default_factory=list,
        description="Independent connectivity check result for each tested AWS service.",
    )
    tested_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of connectivity test.",
    )
    error_summary: str | None = Field(
        default=None,
        description="Summary of errors if authentication or validation failed.",
    )


class AwsCreateConnectionRequest(BaseModel):
    """Request payload to validate, encrypt, and save a persistent AWS connection."""

    name: str = Field(..., min_length=2, max_length=100, description="Connection friendly name.")
    account_id: str = Field(
        ...,
        min_length=12,
        max_length=12,
        pattern=r"^\d{12}$",
        description="12-digit AWS Account ID.",
    )
    default_region: str = Field(default="eu-north-1", description="Default AWS region.")
    auth_method: Literal["profile", "role_arn", "access_keys", "instance_role"] = Field(
        default="profile",
        description="Authentication mechanism.",
    )
    profile_name: str | None = None
    role_arn: str | None = None
    external_id: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None


class AwsConnectionResponse(BaseModel):
    """Safe metadata representation of a persisted AWS connection (zero secrets)."""

    id: str = Field(..., description="Unique connection GUID.")
    name: str = Field(..., description="Connection name.")
    provider: Literal["aws"] = Field(default="aws", description="Cloud provider identifier.")
    account_id: str = Field(..., description="Configured AWS Account ID.")
    arn: str = Field(..., description="Authenticated Principal ARN.")
    default_region: str = Field(..., description="Configured default region.")
    auth_method: str = Field(..., description="Authentication method.")
    status: str = Field(
        ...,
        description="Current status: connected | partially_connected | auth_failed | access_denied.",
    )
    billing_status: str = Field(
        default="DEFERRED",
        description="Billing status: DEFERRED or READ_ONLY.",
    )
    ownership: Literal["owned", "organization"] = Field(
        default="owned", description="Ownership classification."
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp."
    )
    last_verified_at: datetime | None = Field(
        default=None, description="Timestamp of latest verification check."
    )
    services: list[AwsServiceStatus] = Field(
        default_factory=list, description="Per-service connectivity reports."
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking findings or warnings."
    )


class AwsResourceItem(BaseModel):
    """Single discovered cloud resource across Compute, Storage, Networking, Databases, etc."""

    resource_id: str = Field(..., description="Canonical ARN or resource ID.")
    resource_name: str = Field(..., description="Short name or tag-derived name.")
    resource_type: str = Field(
        ...,
        description="Standard AWS asset type (e.g. AWS::EC2::Instance, AWS::S3::Bucket, AWS::Lambda::Function).",
    )
    category: str = Field(
        ...,
        description="compute | storage | networking | database | monitoring | security",
    )
    account_id: str = Field(..., description="12-digit AWS Account ID.")
    region: str = Field(..., description="AWS region where resource is located (or global).")
    creation_time: str | None = Field(
        default=None, description="Creation timestamp when available."
    )
    state: str | None = Field(
        default=None, description="Resource lifecycle state (running, active, etc.)."
    )
    tags: dict[str, str] = Field(default_factory=dict, description="Resource tags.")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Service-specific non-secret configuration details."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Alias for details to ensure complete parity with reporting models.",
    )

    @model_validator(mode="before")
    @classmethod
    def _sync_details_and_metadata(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "details" in data and "metadata" not in data:
                data["metadata"] = data["details"]
            elif "metadata" in data and "details" not in data:
                data["details"] = data["metadata"]
        return data


class AwsFindingItem(BaseModel):
    """Architectural, security, or FinOps finding discovered during read-only inspection."""

    id: str = Field(..., description="Unique finding identifier.")
    title: str = Field(..., description="Clear summary of finding.")
    severity: AwsFindingSeverity = Field(..., description="Severity classification.")
    category: str = Field(
        ...,
        description="networking | security_iam | compute | storage | cost_optimization",
    )
    resource_id: str = Field(..., description="Affected resource identifier or ARN.")
    account_id: str = Field(default="435305479688", description="12-digit AWS Account ID.")
    region: str = Field(default="eu-north-1", description="AWS Region.")
    source_api: str = Field(
        default="unknown", description="Source AWS API that provided the observation."
    )
    description: str = Field(..., description="Detailed explanation of the condition.")
    evidence: dict[str, Any] = Field(
        default_factory=dict, description="Factual evidence data supporting this finding."
    )
    relevant_source_fields: dict[str, Any] = Field(
        default_factory=dict, description="Raw source fields from AWS API response."
    )
    remediation_guidance: str = Field(
        ...,
        description="Actionable guidance for cloud administrators (strictly advisory; no auto-remediation).",
    )
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Detection timestamp."
    )
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Observation timestamp."
    )
    evidence_classification: Literal[
        "VERIFIED_LIVE", "VERIFIED_MOCK", "INFERRED", "NOT_VERIFIED"
    ] = Field(default="NOT_VERIFIED", description="Explicit evidence classification.")
    verification_status: Literal[
        "VERIFIED_LIVE", "VERIFIED_MOCK", "INFERRED", "NOT_VERIFIED", "VERIFIED", "UNCONFIRMED"
    ] = Field(default="NOT_VERIFIED", description="Verification state of this finding.")


class AwsMonitoringSummary(BaseModel):
    """CloudWatch discovery summary."""

    available_metrics_count: int = 0
    alarms_count: int = 0
    sampled_metrics: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


class AwsDiscoveryResponse(BaseModel):
    """Comprehensive resource discovery result across all supported AWS services."""

    account_id: str
    identity: AwsAccountIdentity | None = None
    default_region: str
    scanned_regions: list[str] = Field(default_factory=list)
    total_resources: int = 0
    resources: list[AwsResourceItem] = Field(default_factory=list)
    findings: list[AwsFindingItem] = Field(default_factory=list)
    monitoring: AwsMonitoringSummary | None = None
    services_status: list[AwsServiceStatus] = Field(default_factory=list)
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    partial_discovery: bool = False
    discovery_notes: list[str] = Field(default_factory=list)


# ==============================================================================
# AWS Phase 2: Cost Intelligence, Telemetry, Pricing & CUR Readiness Contracts
# ==============================================================================


class AwsCostMetricType(StrEnum):
    """Supported AWS Cost Explorer financial metrics."""

    UNBLENDED_COST = "UnblendedCost"
    AMORTIZED_COST = "AmortizedCost"
    NET_UNBLENDED_COST = "NetUnblendedCost"
    NET_AMORTIZED_COST = "NetAmortizedCost"


class AwsCostGranularity(StrEnum):
    """Cost Explorer time granularity."""

    DAILY = "DAILY"
    MONTHLY = "MONTHLY"


class AwsCostRecord(BaseModel):
    """Daily or monthly cost record from AWS Cost Explorer."""

    start_date: str = Field(..., description="Start date (YYYY-MM-DD).")
    end_date: str = Field(..., description="End date (YYYY-MM-DD).")
    amount: float = Field(..., description="Cost figure in configured currency.")
    currency: str = Field(default="USD", description="Currency code (e.g. USD).")
    metric_type: AwsCostMetricType = Field(default=AwsCostMetricType.UNBLENDED_COST)
    is_estimated: bool = Field(default=False, description="True if marked as estimated by AWS.")


class AwsCostBreakdownItem(BaseModel):
    """Aggregated cost grouped by service, region, usage type, or tag."""

    key: str = Field(..., description="Grouping key (service name, region code, tag value).")
    amount: float = Field(..., description="Aggregated spend amount.")
    percentage: float = Field(
        default=0.0, description="Percentage of total spend represented by this item."
    )
    unit: str = Field(default="USD", description="Currency unit.")


class AwsCostForecast(BaseModel):
    """Projected end-of-month or future cost forecast from AWS Cost Explorer."""

    remaining_forecast_amount: float = Field(
        ..., description="Forecasted expenditure for the remaining days of the month."
    )
    actual_month_to_date_cost: float = Field(
        default=0.0, description="Actual accrued spend prior to forecast start."
    )
    projected_month_end_cost: float = Field(
        ..., description="Total projected month-end spend (Actual MTD + Remaining Forecast)."
    )
    prediction_interval_lower_bound: float | None = Field(
        default=None, description="Projected lower bound (Actual MTD + Forecast Lower Bound)."
    )
    prediction_interval_upper_bound: float | None = Field(
        default=None, description="Projected upper bound (Actual MTD + Forecast Upper Bound)."
    )
    start_date: str = Field(..., description="Forecast start date.")
    end_date: str = Field(..., description="Forecast end date.")
    currency: str = Field(default="USD")
    confidence_level: int = Field(default=95, description="Statistical confidence level percent.")
    is_prediction_interval_symmetric: bool = Field(
        default=False,
        description="True only if upper and lower intervals are equidistant from mean.",
    )
    forecast_observed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Observation timestamp when forecast was retrieved.",
    )


class AwsCostSummary(BaseModel):
    """Comprehensive Cost Intelligence summary."""

    account_id: str = Field(..., description="12-digit AWS Account ID.")
    metric_type: AwsCostMetricType = Field(default=AwsCostMetricType.UNBLENDED_COST)
    currency: str = Field(default="USD")
    current_month_to_date_cost: float | None = Field(
        default=None, description="Month-to-date expenditure."
    )
    previous_month_cost: float | None = Field(
        default=None, description="Total expenditure for previous calendar month."
    )
    comparable_previous_month_to_date_cost: float | None = Field(
        default=None, description="Expenditure for the same calendar days in previous month."
    )
    month_over_month_percentage_change: float | None = Field(
        default=None, description="MoM trend percentage."
    )
    forecast: AwsCostForecast | None = Field(
        default=None, description="Month-end forecast if available."
    )
    daily_trend: list[AwsCostRecord] = Field(
        default_factory=list, description="Chronological daily spend records."
    )
    monthly_trend: list[AwsCostRecord] = Field(
        default_factory=list, description="Monthly aggregated spend records."
    )
    top_services: list[AwsCostBreakdownItem] = Field(
        default_factory=list, description="Top spending services."
    )
    region_breakdown: list[AwsCostBreakdownItem] = Field(
        default_factory=list, description="Spend grouped by AWS region."
    )
    tag_breakdown: list[AwsCostBreakdownItem] = Field(
        default_factory=list, description="Spend grouped by Cost Allocation Tag."
    )
    data_availability: str = Field(
        default="AVAILABLE",
        description="AVAILABLE | NO_DATA_AVAILABLE | PERMISSION_REQUIRED | DEFERRED | PARTIAL_DATA",
    )
    is_estimated: bool = Field(default=False)
    is_partial: bool = Field(
        default=False, description="True if results were truncated by page safety cap."
    )
    truncation_reason: str | None = Field(
        default=None, description="Reason for partial truncation if applicable."
    )
    actual_cost_period_start: str | None = Field(
        default=None, description="Start date of actual MTD spend."
    )
    actual_cost_period_end: str | None = Field(
        default=None, description="Exclusive end date of actual MTD spend."
    )
    forecast_period_start: str | None = Field(
        default=None, description="Start date of remaining-month forecast."
    )
    forecast_period_end: str | None = Field(
        default=None, description="Exclusive end date of forecast."
    )
    notes: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AwsMetricDataPoint(BaseModel):
    """Single time-series metric data point from CloudWatch."""

    timestamp: str = Field(..., description="ISO 8601 observation timestamp.")
    value: float = Field(..., description="Metric value.")
    unit: str = Field(default="Count", description="Unit of measurement.")
    statistic: str = Field(default="Average", description="Average, Maximum, Minimum, Sum.")


class AwsResourceMetricSeries(BaseModel):
    """CloudWatch metric time-series for a specific resource."""

    resource_id: str = Field(..., description="Target AWS resource ID or ARN.")
    resource_type: str = Field(..., description="Resource type (e.g. AWS::Lambda::Function).")
    metric_name: str = Field(..., description="CloudWatch metric name.")
    namespace: str = Field(..., description="AWS/EC2, AWS/Lambda, AWS/RDS, AWS/S3, etc.")
    unit: str = Field(default="Percent")
    data_points: list[AwsMetricDataPoint] = Field(default_factory=list)
    latest_value: float | None = None
    average_value: float | None = None
    peak_value: float | None = None
    period_seconds: int = Field(default=300)
    status: str = Field(
        default="AVAILABLE",
        description="AVAILABLE | NO_DATA | PERMISSION_REQUIRED | INSTRUMENTATION_REQUIRED",
    )
    notes: str | None = None


class AwsResourceUtilizationSummary(BaseModel):
    """Utilization summary for all discovered resources."""

    account_id: str
    region: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resources_metrics: list[AwsResourceMetricSeries] = Field(default_factory=list)
    total_metrics_evaluated: int = 0
    instrumentation_required_count: int = 0


class AwsPricingEstimate(BaseModel):
    """Standardized on-demand rate estimate for a discovered cloud resource."""

    service: str = Field(..., description="AmazonEC2, AWSLambda, AmazonRDS, AmazonS3, etc.")
    resource_type: str = Field(..., description="Standard AWS resource type.")
    sku: str | None = Field(default=None, description="AWS Price List SKU code.")
    region: str = Field(..., description="AWS Region code.")
    pricing_location: str = Field(
        ..., description="Standard AWS Pricing Location attribute (e.g. EU (Stockholm))."
    )
    instance_type_or_tier: str | None = Field(default=None)
    hourly_rate: float = Field(..., description="Hourly list price rate in currency.")
    monthly_estimated_rate: float = Field(
        ..., description="Monthly estimated cost (hourly_rate * 730)."
    )
    pricing_unit: str = Field(default="Hrs")
    currency: str = Field(default="USD")
    observation_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_list_price: bool = Field(default=True, description="True for public on-demand list price.")
    pricing_source: str = Field(
        default="LIVE_AWS_PRICE_LIST",
        description="LIVE_AWS_PRICE_LIST | CACHED_AWS_PRICE_LIST | OFFLINE_REFERENCE_CATALOG | NOT_AVAILABLE",
    )
    operating_hours_assumption: int = Field(
        default=730,
        description="Standard operating hours per month used for monthly estimates (730 hrs).",
    )
    is_partial_estimate: bool = Field(
        default=False,
        description="True if estimate covers only a subset of dimensions (e.g. IOPS excluded).",
    )


class AwsCurReadiness(BaseModel):
    """Assessment of AWS Cost and Usage Report (CUR) and Data Exports readiness."""

    account_id: str
    destination_bucket: str | None = Field(
        default=None, description="Configured S3 destination bucket."
    )
    bucket_exists: bool = Field(default=False)
    bucket_accessible: bool = Field(
        default=False, description="True if bucket is accessible via current credentials."
    )
    bucket_region: str | None = Field(
        default=None, description="Actual region of destination bucket."
    )
    has_cur: bool = Field(
        default=False, description="True if a CUR report definition was detected."
    )
    has_data_exports: bool = Field(
        default=False, description="True if AWS Data Exports is configured."
    )
    has_manifest: bool = Field(
        default=False, description="True if a manifest file was discovered in bucket prefix."
    )
    manifest_validated: bool = Field(
        default=False,
        description="True only if manifest JSON was retrieved and validated via GetObject.",
    )
    report_name: str | None = None
    report_format: str | None = Field(default=None, description="Parquet, CSV, GZIP.")
    delivery_frequency: str | None = Field(default=None, description="HOURLY, DAILY.")
    status: str = Field(
        default="NOT_CONFIGURED",
        description="CONFIGURED | NOT_CONFIGURED | PERMISSION_REQUIRED | DEFERRED",
    )
    notes: list[str] = Field(default_factory=list)
    bulk_ingestion_status: str = Field(
        default="DEFERRED",
        description="Bulk ingestion remains strictly deferred per FinOps zero-mutation boundary.",
    )


class AwsSyncHealthStatus(BaseModel):
    """Data freshness, synchronization history, and data coverage indicators."""

    account_id: str
    last_sync_time: datetime | None = None
    last_sync_attempt: datetime = Field(default_factory=lambda: datetime.now(UTC))
    services_synced: list[str] = Field(default_factory=list)
    services_skipped: list[str] = Field(default_factory=list)
    services_failed: list[str] = Field(default_factory=list)
    data_freshness_status: str = Field(
        default="FRESH", description="FRESH | STALE | PENDING | ERROR"
    )
    data_coverage_percentage: float = Field(default=100.0)
    chargeable_api_calls_executed: int = Field(
        default=0, description="Count of paid API calls executed (strictly bounded)."
    )
