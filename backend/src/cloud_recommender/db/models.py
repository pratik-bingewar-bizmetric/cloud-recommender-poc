"""SQLAlchemy 2.0 declarative ORM models for WorkloadProfile and Service Catalog."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
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
