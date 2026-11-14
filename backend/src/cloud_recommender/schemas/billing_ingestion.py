"""Pydantic v2 domain schemas for Databricks Billing Ingestion & Reconciliation.

Defines:
- BillingUsageRecord (matching system.billing.usage schema with complete metadata)
- BillingPriceRecord (matching system.billing.list_prices with validity intervals)
- Ingestion run request/response schemas
- Billing summary and reconciliation contract schemas
- Strict unit separation schemas (DBU, DSU, GB, TOKEN)
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    PlainSerializer,
    computed_field,
    field_validator,
    model_validator,
)

from cloud_recommender.services.databricks.billing_sql import (
    BillingQueryValidationError,
    CostBasis,
    MatchStatus,
    to_decimal,
    to_decimal_or_none,
    validate_iso_date,
    validate_limit,
    validate_workspace_id,
)

# Source numerics are decimal(38,18). Hold them as Decimal; serialise JSON numbers as float for
# existing consumers (an exact string twin is exposed where precision matters).
_json_number = PlainSerializer(lambda v: None if v is None else float(v), when_used="json")
ExactDecimal = Annotated[Decimal, BeforeValidator(to_decimal), _json_number]
OptionalExactDecimal = Annotated[Decimal | None, BeforeValidator(to_decimal_or_none), _json_number]


def _default_window_end() -> str:
    return datetime.now(UTC).date().isoformat()


def _default_window_start() -> str:
    return (datetime.now(UTC).date() - timedelta(days=30)).isoformat()


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
    usage_quantity: ExactDecimal = Field(
        ...,
        description="Metered usage quantity (Decimal, source precision); negative for retractions",
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
    effective_cost: OptionalExactDecimal = Field(
        default=None,
        description=(
            "LIST_PRICE_ESTIMATE: usage_quantity x ingested list price (full precision). "
            "None if unmatched. Never an invoiced amount."
        ),
    )
    pricing_matched: bool = Field(
        default=False, description="True if a valid price record matched this usage"
    )
    currency: str | None = Field(default=None, description="Currency of matched pricing")
    cost_basis: CostBasis = Field(
        default=CostBasis.METERED_USAGE,
        description="METERED_USAGE (no money) or LIST_PRICE_ESTIMATE. Never AZURE_INVOICED here.",
    )
    match_status: MatchStatus = Field(
        default=MatchStatus.NO_PRICE, description="Result of the rate-card join"
    )
    price_tier: str | None = Field(default=None, description="Price tier used for the estimate")
    resource_type: str | None = Field(default=None, description="Attributed resource type")
    resource_id: str | None = Field(default=None, description="Attributed exact resource id")
    source_row_hash: str | None = Field(
        default=None, description="sha256 of the source row identity fields (idempotency)"
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def usage_quantity_exact(self) -> str:
        """Lossless decimal text of usage_quantity."""
        return format(self.usage_quantity, "f")


class BillingPriceRecord(BaseModel):
    """Published list price record extracted from system.billing.list_prices."""

    sku_name: str = Field(..., description="Commercial SKU")
    cloud: str = Field(default="azure", description="Cloud provider")
    currency_code: str = Field(default="USD", description="Currency (USD, EUR, etc.)")
    account_id: str | None = Field(default=None, description="Databricks account ID")
    usage_unit: str = Field(default="DBU", description="Unit of measurement that is monetised")
    price_default: OptionalExactDecimal = Field(
        default=None, description="pricing.default from system.billing.list_prices"
    )
    price_promotional: OptionalExactDecimal = Field(
        default=None, description="pricing.promotional.default"
    )
    price_effective_list: OptionalExactDecimal = Field(
        default=None, description="pricing.effective_list.default"
    )
    price_start_time: str = Field(..., description="Start of price validity interval")
    price_end_time: str | None = Field(
        default=None, description="End of price validity; None if currently active"
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_flat_fields(cls, data: Any) -> Any:
        """Accept the pre-M7.1 flat shape (price_per_unit / pricing_unit)."""
        if isinstance(data, dict):
            data = dict(data)
            if "price_per_unit" in data:
                legacy = data.pop("price_per_unit")
                if data.get("price_default") is None:
                    data["price_default"] = legacy
            if "pricing_unit" in data:
                legacy_unit = data.pop("pricing_unit")
                data.setdefault("usage_unit", legacy_unit)
        return data

    @computed_field  # type: ignore[prop-decorator]
    @property
    def price_per_unit(self) -> float | None:
        """Selected list rate (effective_list, else default); None when the source gave neither."""
        rate = self.selected_price()
        return None if rate is None else float(rate)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pricing_unit(self) -> str:
        """Backward-compatible alias of usage_unit."""
        return self.usage_unit

    @computed_field  # type: ignore[prop-decorator]
    @property
    def price_tier(self) -> str | None:
        """Tier that selected_price() resolves to."""
        if self.price_effective_list is not None:
            return "effective_list"
        if self.price_default is not None:
            return "default"
        return None

    def selected_price(self) -> Decimal | None:
        """Exact selected list rate; promotional prices are never used for the estimate."""
        if self.price_effective_list is not None:
            return self.price_effective_list
        return self.price_default


class BillingUsageEnvelope(BaseModel):
    """Paginated usage response (matches the frontend contract)."""

    total: int = Field(..., description="Matching records before pagination")
    offset: int = Field(default=0)
    limit: int = Field(..., description="Page size applied")
    records: list[BillingUsageRecord] = Field(default_factory=list)


class BillingPriceEnvelope(BaseModel):
    """Rate-card response envelope (matches the frontend contract)."""

    total: int = Field(..., description="Matching price records before limit")
    records: list[BillingPriceRecord] = Field(default_factory=list)


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
    total_dbu_consumed: float | None = Field(
        default=None, description="Cumulative DBU consumption; null when no rows are ingested"
    )
    active_configuration_version: int = Field(
        default=1, description="Active governance configuration version"
    )
    next_action: str = Field(..., description="Actionable next step for operator")


class IngestionRunCreateRequest(BaseModel):
    """Payload to request an ingestion execution."""

    workspace_id: str = Field(
        default="642006393507276", description="Target Databricks workspace ID (digits only)"
    )
    start_date: str = Field(
        default_factory=_default_window_start, description="Start date YYYY-MM-DD"
    )
    end_date: str = Field(default_factory=_default_window_end, description="End date YYYY-MM-DD")
    source_table: Literal["system.billing.usage", "system.billing.list_prices"] = Field(
        default="system.billing.usage", description="Allow-listed billing system table to ingest"
    )
    is_approved: bool = Field(
        default=False, description="Explicit approval to resume warehouse and execute SQL"
    )
    approval_token: str | None = Field(
        default=None, description="Cryptographically signed server-issued authorization token"
    )
    limit: int = Field(default=1000, ge=1, le=50000, description="Bounded pagination limit")

    @field_validator("workspace_id")
    @classmethod
    def _check_workspace(cls, v: str) -> str:
        try:
            return validate_workspace_id(v)
        except BillingQueryValidationError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("start_date", "end_date")
    @classmethod
    def _check_dates(cls, v: str) -> str:
        try:
            return validate_iso_date(v)
        except BillingQueryValidationError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("limit")
    @classmethod
    def _check_limit(cls, v: int) -> int:
        try:
            return validate_limit(v)
        except BillingQueryValidationError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def _check_window(self) -> "IngestionRunCreateRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date.")
        return self


class BillingIngestionRunResponse(BaseModel):
    """Detailed result of an ingestion run attempt."""

    run_id: str = Field(..., description="Unique run identifier")
    workspace_id: str = Field(..., description="Target workspace ID")
    source_table: str = Field(default="system.billing.usage", description="Primary source table")
    requested_period_start: str = Field(..., description="Requested start date")
    requested_period_end: str = Field(..., description="Requested end date")
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = Field(default=None)
    status: str = Field(..., description="completed, incomplete, failed, or approval_required")
    result_complete: bool | None = Field(
        default=None,
        description=(
            "True only when the extract is provably whole (finished statement, no truncation, "
            "all chunks, row count below the requested bound). None when nothing was extracted."
        ),
    )
    error_code: str | None = Field(
        default=None,
        description="STATEMENT_FAILED, STATEMENT_TIMEOUT, RESULT_TRUNCATED, RESULT_INCOMPLETE "
        "or ROW_LIMIT_REACHED when the extract is not whole",
    )
    extracted_count: int = Field(default=0)
    inserted_count: int = Field(default=0)
    duplicate_count: int = Field(default=0)
    retraction_count: int = Field(default=0)
    error_count: int = Field(default=0)
    shared_record_id_count: int = Field(
        default=0,
        description=(
            "Diagnostic: extracted rows whose record_id also appears on another extracted row "
            "(evidence for the final dedup key)"
        ),
    )
    error_message: str | None = Field(default=None)
    approval_request: dict[str, Any] | None = Field(
        default=None, description="Approval payload if gated"
    )


class BillingSummaryResponse(BaseModel):
    """Canonical DBU and financial summary aggregated from normalized billing records."""

    workspace_id: str = Field(..., description="Target workspace ID")
    resource_id: str | None = Field(default=None, description="Exact resource ID if filtered")
    total_dbu: float | None = Field(
        default=None,
        description="Gross metered DBU quantity (aggregated in Decimal, presented as float); null when no rows",
    )
    net_dbu: float | None = Field(
        default=None, description="Net DBU quantity (gross minus retractions); null when no rows"
    )
    retraction_dbu: float | None = Field(default=None, description="Total retracted DBU quantity")
    total_spend_verified: float | None = Field(
        default=None,
        description=(
            "LIST_PRICE_ESTIMATE over priced rows only (see spend_complete); "
            "null if nothing is priced. Not an invoice."
        ),
    )
    spend_complete: bool | None = Field(
        default=None,
        description="True only when every DBU row was priced; False means the estimate is partial",
    )
    pricing_coverage_pct: float | None = Field(
        default=None, description="Share of DBU rows with a matched price (0-100)"
    )
    cost_basis: CostBasis = Field(
        default=CostBasis.METERED_USAGE,
        description="LIST_PRICE_ESTIMATE when total_spend_verified is present, else METERED_USAGE",
    )
    currency: str | None = Field(
        default=None,
        description="Currency of matched spend; null if unpriced or if several currencies are present",
    )
    spend_by_currency: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Priced spend per currency. Currencies are never merged or converted: when more "
            "than one is present total_spend_verified and currency are null."
        ),
    )
    price_card_complete: bool | None = Field(
        default=None,
        description="False when the last rate-card extract was incomplete; None if no rate card ran",
    )
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
        default="NO_BILLING_ROWS", description="INGESTED, NO_DATA, NO_BILLING_ROWS"
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
    gross_dbu: float | None = None
    retraction_dbu: float | None = None
    net_dbu: float | None = None
    gross_cost: float | None = None
    net_cost: float | None = None
    currency: str | None = Field(default=None)
    cost_by_currency: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Gross/net cost per currency; gross_cost/net_cost are null when >1 currency",
    )
    cost_basis: CostBasis = Field(default=CostBasis.METERED_USAGE)
    reconciliation_status: str = Field(
        default="NO_DATA",
        description="RECONCILED, PARTIAL_PRICING, DISCREPANCY_DETECTED or NO_DATA",
    )
    checks: list[dict[str, Any]] = Field(
        default_factory=list, description="Each internal check with name, passed and detail"
    )
    audit_notes: list[str] = Field(default_factory=list)


class IngestionPreviewResponse(BaseModel):
    """Preview of billing records without starting the SQL warehouse."""

    workspace_id: str = Field(..., description="Target workspace ID")
    period_start: str = Field(...)
    period_end: str = Field(...)
    source: str = Field(default="Ingested usage store")
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
    expected_result_size: str = Field(default="Not estimated (bounded by the requested row limit)")
    expected_operational_cost: str = Field(
        default="Not estimated (depends on warehouse size and runtime)"
    )
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
    start_date: str = Field(
        default_factory=_default_window_start, description="Scope period start date"
    )
    end_date: str = Field(default_factory=_default_window_end, description="Scope period end date")
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
