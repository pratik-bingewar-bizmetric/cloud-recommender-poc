"""SQLAlchemy 2.0 declarative ORM models for WorkloadProfile and Service Catalog."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM entities."""

    pass


# Cross-dialect JSON type: uses JSONB on PostgreSQL, standard JSON elsewhere (e.g. SQLite tests)
JSONType = JSON().with_variant(JSONB, "postgresql")


class GUID(TypeDecorator[uuid.UUID]):
    """Platform-independent GUID/UUID type.

    Uses PostgreSQL native UUID type, falls back to CHAR(36) on SQLite.
    """

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return str(value) if dialect.name != "postgresql" else value
        return str(value) if dialect.name != "postgresql" else uuid.UUID(str(value))

    def process_result_value(self, value: Any, _dialect: Any) -> uuid.UUID | None:
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class WorkloadProfileModel(Base):
    """PostgreSQL entity for storing user-submitted workload requirement profiles."""

    __tablename__ = "workload_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        doc="Globally unique stable UUID for the workload profile.",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Name of the application project.",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Detailed functional description or requirement text.",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Workload archetype category (e.g. 'web_app', 'microservices').",
    )

    # Traffic and throughput
    target_traffic_rps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_active_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peak_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Availability and resilience
    target_sla_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 3), nullable=True)
    high_availability: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    multi_region: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rpo_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rto_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Compliance and data
    compliance_frameworks: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    data_classification: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_volume_gb: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    monthly_data_egress_gb: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    database_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Geographic region targeting
    primary_region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_regions: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)

    # Financial bounds
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    max_monthly_budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cost_buffer_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("15.00"), nullable=False
    )
    estimation_assumptions: Mapped[dict[str, str]] = mapped_column(
        JSONType, default=dict, nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (Index("ix_workload_category_created", "category", "created_at"),)


class CloudServiceCatalogModel(Base):
    """PostgreSQL entity for normalized cloud service catalog entries (Azure, AWS, GCP)."""

    __tablename__ = "cloud_service_catalog"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        doc="Internal primary key UUID.",
    )
    provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="Cloud provider ('azure', 'aws', 'gcp').",
    )
    service_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Provider-native service identifier (e.g. 'azure-container-apps').",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Official marketing display name.",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Service architectural category ('compute', 'database', etc.).",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Service architectural description.",
    )
    supported_regions: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    supported_compliance: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    sla_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_serverless: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    pricing_unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    measurement_metric: Mapped[str | None] = mapped_column(String(100), nullable=True)
    documentation_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    pricing_source_type: Mapped[str] = mapped_column(
        String(100), default="curated_fixture", nullable=False
    )
    pricing_reference_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    dataset_version: Mapped[str] = mapped_column(String(50), default="1.0.0", nullable=False)
    retrieval_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    provenance: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="fixture", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("provider", "service_id", name="uq_provider_service_id"),
        Index("ix_catalog_provider_category", "provider", "category"),
    )


class ResourceConfigurationModel(Base):
    """SQLAlchemy entity for persisting multi-cloud resource selection configurations."""

    __tablename__ = "resource_configurations"

    configuration_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this configuration instance.",
    )
    connection_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Associated cloud connection identifier.",
    )
    provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="Cloud provider ('azure', 'gcp', 'aws').",
    )
    configuration_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        doc="Monotonically increasing version number for this connection.",
    )
    active_status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
        index=True,
        doc="Lifecycle status: 'active', 'archived', 'draft'.",
    )
    created_by: Mapped[str] = mapped_column(
        String(100),
        default="system",
        nullable=False,
        doc="User or service identity creating this configuration.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    scope_items: Mapped[list["ConfiguredScopeItemModel"]] = relationship(
        "ConfiguredScopeItemModel",
        back_populates="configuration",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_config_conn_active", "connection_id", "active_status"),
        Index("ix_config_conn_version", "connection_id", "configuration_version"),
    )


class ConfiguredScopeItemModel(Base):
    """SQLAlchemy entity for individual hierarchical scope items within a configuration."""

    __tablename__ = "configured_scope_items"

    item_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this scope item record.",
    )
    configuration_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("resource_configurations.configuration_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key referencing the parent configuration.",
    )
    scope_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Hierarchical scope type (subscription, resource_group, resource, databricks_workspace).",
    )
    scope_identifier: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        doc="Full provider-native resource or scope identifier.",
    )
    parent_scope_identifier: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
        doc="Direct parent scope identifier in hierarchy.",
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human-readable label for this scope.",
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
        doc="Provider resource type classification.",
    )
    region: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Deployment region.",
    )
    selection_state: Mapped[str] = mapped_column(
        String(20),
        default="included",
        nullable=False,
        doc="Selection directive: 'included', 'excluded', 'all_children'.",
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        default=dict,
        nullable=False,
        doc="Provider metadata including Databricks workspace URL, sku, and properties.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    configuration: Mapped["ResourceConfigurationModel"] = relationship(
        "ResourceConfigurationModel",
        back_populates="scope_items",
    )

    __table_args__ = (
        Index("ix_scope_item_config_scope", "configuration_id", "scope_identifier"),
        Index("ix_scope_item_parent", "configuration_id", "parent_scope_identifier"),
    )


class IngestionRunModel(Base):
    """SQLAlchemy entity for tracking scope-aware ingestion runs with configuration lineage."""

    __tablename__ = "ingestion_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this ingestion execution run.",
    )
    connection_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Associated cloud connection identifier.",
    )
    provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="Cloud provider ('azure', 'gcp', 'aws').",
    )
    configuration_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        nullable=False,
        index=True,
        doc="Configuration revision ID governing this ingestion run.",
    )
    configuration_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Configuration revision version number enforced during this run.",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
        index=True,
        doc="Execution lifecycle status: pending, running, completed, partial_failure, failed.",
    )
    triggered_by: Mapped[str] = mapped_column(
        String(100),
        default="user",
        nullable=False,
        doc="Trigger source: user, schedule, or api.",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when ingestion run completed or terminated.",
    )
    total_resources_scoped: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Count of resources scoped for this run.",
    )
    successful_resources_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Count of resources successfully ingested.",
    )
    failed_resources_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Count of resources that encountered extraction errors.",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Top-level error message or diagnostics if run failed.",
    )
    scope_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        default=dict,
        nullable=False,
        doc="Snapshot of selected resource IDs and workspace IDs at run initialization.",
    )

    resource_records: Mapped[list["IngestionResourceRecordModel"]] = relationship(
        "IngestionResourceRecordModel",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_ingest_run_conn_status", "connection_id", "status"),
        Index("ix_ingest_run_conn_version", "connection_id", "configuration_version"),
    )


class IngestionResourceRecordModel(Base):
    """SQLAlchemy entity for per-resource execution records within an ingestion run."""

    __tablename__ = "ingestion_resource_records"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this resource ingestion record.",
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("ingestion_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to the parent ingestion run.",
    )
    resource_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        doc="Provider-native resource identifier (e.g. ARM ID).",
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        doc="ARM or cloud resource type.",
    )
    region: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Deployment region.",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="success",
        nullable=False,
        doc="Per-resource extraction outcome: success, failed, skipped.",
    )
    inventory_extracted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether configuration/inventory was extracted.",
    )
    cost_extracted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether cost telemetry was extracted.",
    )
    metrics_extracted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether performance metrics were extracted.",
    )
    extracted_records_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Count of metrics/cost records extracted.",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Error message if this resource failed extraction.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped["IngestionRunModel"] = relationship(
        "IngestionRunModel",
        back_populates="resource_records",
    )

    __table_args__ = (Index("ix_ingest_res_run_status", "run_id", "status"),)


class BillingUsageRecordModel(Base):
    """Normalized usage record from system.billing.usage with exact idempotency key."""

    __tablename__ = "billing_usage_records"

    record_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        doc="Unique billing event ID serving as strict idempotency key.",
    )
    workspace_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Databricks workspace ID.",
    )
    account_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Databricks account ID.",
    )
    sku_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        doc="Commercial billing SKU name.",
    )
    cloud: Mapped[str] = mapped_column(
        String(50),
        default="azure",
        nullable=False,
        doc="Cloud provider ('azure', 'aws', 'gcp').",
    )
    usage_start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Start of the metering interval.",
    )
    usage_end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="End of the metering interval.",
    )
    usage_date: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="Usage date YYYY-MM-DD.",
    )
    usage_unit: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="DBU",
        doc="Usage measurement unit (DBU, BYTE_HOURS). Strict unit separation.",
    )
    usage_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        doc="Metered quantity; negative values indicate retractions.",
    )
    record_type: Mapped[str] = mapped_column(
        String(50),
        default="original",
        nullable=False,
        doc="Record type: original, retraction, correction.",
    )
    ingestion_date: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        doc="System Tables ingestion date YYYY-MM-DD.",
    )
    billing_origin_product: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Originating product family e.g. JOBS, SQL, ALL_PURPOSE.",
    )
    product_features_json: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        default=dict,
        nullable=False,
        doc="Detailed product features payload.",
    )
    usage_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        default=dict,
        nullable=False,
        doc="Resource metadata including cluster_id, warehouse_id, job_id, endpoint_id.",
    )
    custom_tags_json: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        default=dict,
        nullable=False,
        doc="FinOps tags attached to compute resource.",
    )
    effective_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4),
        nullable=True,
        doc="Effective cost computed from exact price match; null if unmatched.",
    )
    pricing_matched: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether an exact price interval matched this usage record.",
    )
    currency: Mapped[str | None] = mapped_column(
        String(10),
        default="USD",
        nullable=True,
        doc="Currency of matched pricing.",
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_billing_usage_ws_date", "workspace_id", "usage_date"),
        Index("ix_billing_usage_sku_unit", "sku_name", "usage_unit"),
    )


class BillingPriceRecordModel(Base):
    """Published list price record from system.billing.list_prices."""

    __tablename__ = "billing_price_records"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    sku_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        doc="Commercial SKU name.",
    )
    cloud: Mapped[str] = mapped_column(
        String(50),
        default="azure",
        nullable=False,
        doc="Cloud provider ('azure', 'aws', 'gcp').",
    )
    currency_code: Mapped[str] = mapped_column(
        String(10),
        default="USD",
        nullable=False,
        doc="Currency code (USD, EUR, GBP).",
    )
    price_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        doc="Published list price per unit.",
    )
    pricing_unit: Mapped[str] = mapped_column(
        String(50),
        default="DBU",
        nullable=False,
        doc="Unit of pricing (DBU, gigabyte_month).",
    )
    price_start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Start of price validity interval.",
    )
    price_end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="End of price validity interval; null if currently active.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_billing_price_sku_cloud", "sku_name", "cloud", "currency_code"),)


class BillingIngestionRunModel(Base):
    """Historical execution record of a billing ingestion run."""

    __tablename__ = "billing_ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
        doc="Authoritative run identifier.",
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    source_table: Mapped[str] = mapped_column(
        String(128),
        default="system.billing.usage",
        nullable=False,
    )
    requested_period_start: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    requested_period_end: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
        index=True,
        doc="Run status: pending, running, completed, failed, approval_required.",
    )
    extracted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retraction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )


class BillingReconciliationResultModel(Base):
    """Audit record capturing mathematical reconciliation between usage and pricing."""

    __tablename__ = "billing_reconciliation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    reconciliation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    reconciliation_status: Mapped[str] = mapped_column(
        String(32),
        default="RECONCILED",
        nullable=False,
    )
    usage_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    price_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_records_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unmatched_records_count: Mapped[int] = mapped_column(Integer, nullable=False)
    retraction_records_count: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_dbu: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    retraction_dbu: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    net_dbu: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    gross_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    net_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    audit_notes_json: Mapped[list[str]] = mapped_column(
        JSONType,
        default=list,
        nullable=False,
    )


class BillingSourceCheckpointModel(Base):
    """Watermark checkpoint tracking ingestion progress across System Tables."""

    __tablename__ = "billing_source_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    table_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    high_watermark_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    latest_usage_date: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    records_ingested_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_checkpoint_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "table_name", name="uq_billing_checkpoint_ws_tbl"),
    )


class BillingScopeSnapshotModel(Base):
    """Point-in-time snapshot of discovered resources for scope attribution."""

    __tablename__ = "billing_scope_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    snapshot_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    resource_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_clusters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_warehouses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_endpoints: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    snapshot_data_json: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        default=dict,
        nullable=False,
    )


class BillingCalculationVersionModel(Base):
    """Audit table for FinOps formula versions, rate card profiles and rounding rules."""

    __tablename__ = "billing_calculation_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    version_tag: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        doc="Version identifier e.g. 'v3H.1-canonical-decimal'.",
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    formula_definition: Mapped[str] = mapped_column(Text, nullable=False)
    rounding_policy: Mapped[str] = mapped_column(
        String(64),
        default="ROUND_HALF_UP_2DP",
        nullable=False,
    )
    currency_conversion_method: Mapped[str] = mapped_column(
        String(64),
        default="EXACT_SOURCE_CURRENCY",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BillingApprovalTokenModel(Base):
    """Audit and replay-prevention ledger for cryptographically signed Databricks execution tokens."""

    __tablename__ = "billing_approval_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    token_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
        doc="Cryptographic token identifier / nonce hash",
    )
    approver_sub: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        doc="Subject identifier of authorized administrator approving live query execution",
    )
    approver_roles: Mapped[list[str]] = mapped_column(
        JSONType,
        default=list,
        nullable=False,
        doc="Roles held by approver (must include Admin, FinOpsAdministrator, or PlatformAdministrator)",
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    query_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="SHA-256 hash of exact approved read-only SQL query",
    )
    date_start: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date_end: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allowed_tables: Mapped[list[str]] = mapped_column(
        JSONType,
        default=list,
        nullable=False,
    )
    requested_operation: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="READ_ONLY_SYSTEM_TABLES_SELECT",
    )
    nonce: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    kid: Mapped[str] = mapped_column(
        String(64),
        default="k1-2026",
        nullable=False,
    )
    max_rows: Mapped[int] = mapped_column(
        Integer,
        default=1000,
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_consumed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    approval_purpose: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        default="Ingest verified billing usage and price records into FinOps Command Center",
    )

    __table_args__ = (
        Index("ix_billing_approval_token_status", "is_consumed", "expires_at"),
        Index("ix_billing_approval_token_wh_qhash", "warehouse_id", "query_hash"),
        UniqueConstraint("nonce", name="uq_billing_approval_tokens_nonce"),
    )
