"""Pydantic v2 domain schemas for Databricks Billing Ingestion & Reconciliation.

Defines:
- BillingUsageRecord (matching system.billing.usage schema with complete metadata)
- BillingPriceRecord (matching system.billing.list_prices with validity intervals)
- Ingestion run request/response schemas
- Billing summary and reconciliation contract schemas
- Strict unit separation schemas (DBU, DSU, GB, TOKEN)
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class BillingUsageRecord(BaseModel):
    """Normalized usage record extracted from system.billing.usage."""

    record_id: str = Field(..., description="Unique billing event ID; acts as idempotency key")
    workspace_id: str = Field(..., description="Target Databricks workspace identifier")
    account_id: str | None = Field(default=None, description="Databricks account ID")
    sku_name: str = Field(..., description="Commercial SKU e.g. STANDARD_ALL_PURPOSE_COMPUTE")
    cloud: str = Field(default="azure", description="Cloud provider (azure, aws, gcp)")
    usage_start_time: str = Field(..., description="Start of metering window in ISO 8601")
    usage_end_time: str = Field(..., description="End of metering window in ISO 8601")
    usage_date: str = Field(..., description="Date of usage YYYY-MM-DD")
    usage_unit: str = Field(
        ..., description="Unit of measure: DBU, BYTE_HOURS, etc. Never conflated."
    )
    usage_quantity: float = Field(
        ..., description="Metered usage quantity; negative for retractions"
    )
    record_type: str = Field(
        default="original", description="Record type: original, retraction, restatement"
    )
    ingestion_date: str | None = Field(default=None, description="System tables ingestion date")
    billing_origin_product: str | None = Field(
        default=None, description="Originating product family"
    )
    product_features: dict[str, Any] = Field(
        default_factory=dict, description="Detailed product features"
    )
    usage_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Resource metadata containing cluster_id, warehouse_id, job_id, endpoint_id",
    )
    custom_tags: dict[str, str] = Field(
        default_factory=dict, description="FinOps tags attached to compute"
    )
    identity_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Identity metadata of caller"
    )
    effective_cost: float | None = Field(
        default=None, description="Effective cost computed from exact price join; None if unmatched"
    )
    pricing_matched: bool = Field(
        default=False, description="True if a valid price record matched this usage"
    )
    currency: str | None = Field(default="USD", description="Currency of matched pricing")


class BillingPriceRecord(BaseModel):
    """Published list price record extracted from system.billing.list_prices."""

    sku_name: str = Field(..., description="Commercial SKU")
    cloud: str = Field(default="azure", description="Cloud provider")
    currency_code: str = Field(default="USD", description="Currency (USD, EUR, etc.)")
    price_per_unit: float = Field(..., description="Price rate per unit")
    pricing_unit: str = Field(
        default="DBU", description="Pricing metric unit (DBU, gigabyte_month)"
    )
    price_start_time: str = Field(..., description="Start of price validity interval")
    price_end_time: str | None = Field(
        default=None, description="End of price validity; None if currently active"
    )


class BillingIngestionStatusResponse(BaseModel):
    """Comprehensive status of the Databricks billing ingestion subsystem."""

    connection_status: str = Field(..., description="READY_TO_CONNECT, CONNECTED, or ERROR")
    warehouse_status: str = Field(..., description="WAREHOUSE_STOPPED, AVAILABLE, or ERROR")
    warehouse_id: str = Field(default="05ed10a52697a344", description="Target SQL warehouse ID")
    warehouse_name: str = Field(
        default="Serverless Starter Warehouse", description="SQL warehouse name"
    )
    system_tables_status: str = Field(
        ..., description="STOPPED_WAREHOUSE, AVAILABLE, or APPROVAL_REQUIRED"
    )
    last_successful_ingestion: str | None = Field(
        default=None, description="Timestamp of latest successful run"
    )
    total_usage_records_ingested: int = Field(
        default=0, description="Total normalized records in repository"
    )
    total_dbu_consumed: float = Field(
        default=0.0, description="Cumulative DBU consumption across records"
    )
    active_configuration_version: int = Field(
        default=1, description="Active governance configuration version"
    )
    next_action: str = Field(..., description="Actionable next step for operator")


class IngestionRunCreateRequest(BaseModel):
    """Payload to request an ingestion execution."""

    workspace_id: str = Field(
        default="642006393507276", description="Target Databricks workspace ID"
    )
    start_date: str = Field(default="2026-10-01", description="Start date YYYY-MM-DD")
    end_date: str = Field(default="2026-11-04", description="End date YYYY-MM-DD")
    is_approved: bool = Field(
        default=False, description="Explicit approval to resume warehouse and execute SQL"
    )
    approval_token: str | None = Field(
        default=None, description="Cryptographically signed server-issued authorization token"
    )
    limit: int = Field(default=1000, ge=1, le=50000, description="Bounded pagination limit")


class BillingIngestionRunResponse(BaseModel):
    """Detailed result of an ingestion run attempt."""

    run_id: str = Field(..., description="Unique run identifier")
    workspace_id: str = Field(..., description="Target workspace ID")
    source_table: str = Field(default="system.billing.usage", description="Primary source table")
    requested_period_start: str = Field(..., description="Requested start date")
    requested_period_end: str = Field(..., description="Requested end date")
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = Field(default=None)
    status: str = Field(..., description="completed, failed, or approval_required")
    extracted_count: int = Field(default=0)
    inserted_count: int = Field(default=0)
    duplicate_count: int = Field(default=0)
    retraction_count: int = Field(default=0)
    error_count: int = Field(default=0)
    error_message: str | None = Field(default=None)
    approval_request: dict[str, Any] | None = Field(
        default=None, description="Approval payload if gated"
    )


class BillingSummaryResponse(BaseModel):
    """Canonical DBU and financial summary aggregated from normalized billing records."""

    workspace_id: str = Field(..., description="Target workspace ID")
    resource_id: str | None = Field(default=None, description="Exact resource ID if filtered")
    total_dbu: float = Field(..., description="Gross metered DBU quantity")
    net_dbu: float = Field(..., description="Net DBU quantity (gross minus retractions)")
    retraction_dbu: float = Field(default=0.0, description="Total retracted DBU quantity")
    total_spend_verified: float | None = Field(
        default=None, description="Spend verified through matched pricing; null if unpriced"
    )
    currency: str = Field(default="USD", description="Currency of matched spend")
    dbu_by_product: list[dict[str, Any]] = Field(
        default_factory=list, description="DBU breakdown by product family"
    )
    dbu_by_sku: list[dict[str, Any]] = Field(
        default_factory=list, description="DBU breakdown by SKU"
    )
    daily_trend: list[dict[str, Any]] = Field(
        default_factory=list, description="Daily DBU and spend progression"
    )
    matched_pricing_count: int = Field(
        default=0, description="Count of usage records with exact pricing match"
    )
    unmatched_pricing_count: int = Field(
        default=0, description="Count of usage records without valid pricing match"
    )
    data_status: str = Field(
        default="BASELINE", description="LIVE, BASELINE, NO_DATA, WAREHOUSE_STOPPED"
    )
    last_refreshed: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class BillingReconciliationResponse(BaseModel):
    """Mathematical reconciliation between usage records, list prices, and retractions."""

    workspace_id: str = Field(..., description="Target workspace ID")
    usage_record_count: int = Field(default=0)
    price_record_count: int = Field(default=0)
    matched_records_count: int = Field(default=0)
    unmatched_records_count: int = Field(default=0)
    retraction_records_count: int = Field(default=0)
    gross_dbu: float = Field(default=0.0)
    retraction_dbu: float = Field(default=0.0)
    net_dbu: float = Field(default=0.0)
    gross_cost: float = Field(default=0.0)
    net_cost: float = Field(default=0.0)
    currency: str = Field(default="USD")
    reconciliation_status: str = Field(
        default="RECONCILED", description="RECONCILED or DISCREPANCY_DETECTED"
    )
    audit_notes: list[str] = Field(default_factory=list)


class IngestionPreviewResponse(BaseModel):
    """Preview of billing records without starting the SQL warehouse."""

    workspace_id: str = Field(..., description="Target workspace ID")
    period_start: str = Field(...)
    period_end: str = Field(...)
    source: str = Field(default="System Tables Baseline Fixture")
    preview_records: list[BillingUsageRecord] = Field(default_factory=list)
    total_available_in_preview: int = Field(default=0)
    status: str = Field(default="PREVIEW_READY")


class IngestionValidateResponse(BaseModel):
    """Validation outcome for ingestion parameters and warehouse readiness."""

    valid: bool = Field(..., description="True if parameters and connectivity pass inspection")
    workspace_id: str = Field(...)
    warehouse_id: str = Field(...)
    warehouse_name: str = Field(default="Serverless Starter Warehouse")
    warehouse_state: str = Field(..., description="STOPPED, RUNNING, etc.")
    system_tables_ready: bool = Field(default=False)
    allowed_tables: list[str] = Field(
        default_factory=lambda: ["system.billing.usage", "system.billing.list_prices"]
    )
    query_plan_preview: str = Field(default="")
    expected_result_size: str = Field(default="~11 - 100 records")
    expected_operational_cost: str = Field(default="$0.15 - $0.35 serverless burst")
    approval_status: str = Field(default="APPROVAL_REQUIRED")
    duplicate_handling: str = Field(default="Deduplication via record_id primary key index")
    can_run: bool = Field(
        default=False, description="Run execution strictly disabled until backend authorization"
    )
    diagnostic_messages: list[str] = Field(default_factory=list)


class BillingApprovalTokenRequest(BaseModel):
    """Payload to request issuance of a cryptographically signed approval token."""

    query: str = Field(..., description="Exact read-only SELECT statement against system tables")
    warehouse_id: str = Field(
        default="05ed10a52697a344", description="Target SQL warehouse identifier"
    )
    workspace_id: str = Field(
        default="642006393507276", description="Target Databricks workspace identifier"
    )
    start_date: str = Field(default="2026-10-01", description="Scope period start date")
    end_date: str = Field(default="2026-11-04", description="Scope period end date")
    max_rows: int = Field(
        default=1000,
        ge=1,
        le=50000,
        description="Upper bound on result rows authorized for this token",
    )
    approval_purpose: str = Field(
        default="Live System Tables Billing Ingestion",
        description="Explicit operational justification for live query execution",
    )
    ttl_seconds: int = Field(
        default=300, ge=60, le=3600, description="Token validity duration in seconds"
    )
    # Untrusted client-supplied identity fields: strictly ignored / validated against server identity
    approver_sub: str | None = Field(
        default=None,
        description="Client-supplied approver identity (ignored: identity is strictly server-derived)",
    )
    approver_roles: list[str] | None = Field(
        default=None,
        description="Client-supplied roles (ignored: roles are strictly server-derived)",
    )


class BillingApprovalTokenResponse(BaseModel):
    """Cryptographically signed approval token result."""

    token: str = Field(..., description="Cryptographically signed authorization token")
    token_id: str = Field(..., description="Unique token identifier")
    kid: str = Field(default="k1-2026", description="Key identifier used for signing")
    approver_sub: str = Field(..., description="Server-verified approver identity")
    approver_roles: list[str] = Field(
        default_factory=list, description="Server-verified approver roles"
    )
    workspace_id: str = Field(..., description="Workspace ID")
    warehouse_id: str = Field(..., description="Warehouse ID")
    query_hash: str = Field(..., description="SHA-256 hash of validated query")
    max_rows: int = Field(default=1000, description="Authorized maximum result rows")
    approval_purpose: str = Field(
        default="Live System Tables Billing Ingestion", description="Authorization purpose"
    )
    expires_at: str = Field(..., description="Expiry timestamp in ISO 8601")
    status: str = Field(default="ISSUED", description="ISSUED, EXPIRED, or CONSUMED")
