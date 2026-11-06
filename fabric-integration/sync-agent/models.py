"""Microsoft Fabric FinOps Sync Agent - Data Transfer Objects and Domain Models.

Defines typed dataclasses and structures representing the extracted Azure
entities and synchronization audit records, matching the analytical Delta schemas.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class SyncMode(StrEnum):
    """Synchronization operation modes."""

    CHECK = "check"
    INVENTORY = "inventory"
    COST = "cost"
    METRICS = "metrics"
    FULL = "full"


class SyncStatus(StrEnum):
    """Execution status for a synchronization run."""

    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


@dataclass
class ResourceInventoryRecord:
    """Discovered Azure cloud resource snapshot."""

    resource_id: str
    connection_id: str
    subscription_id: str
    tenant_id: str | None
    provider: str
    name: str
    resource_type: str
    resource_group: str | None
    location: str
    sku_name: str | None
    power_state: str | None
    tags: str | None  # JSON-encoded dictionary
    monthly_retail_cost: Decimal | None
    source_api: str
    snapshot_timestamp: datetime
    ingestion_timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary matching PyArrow schema types."""
        return {
            "resource_id": self.resource_id,
            "connection_id": self.connection_id,
            "subscription_id": self.subscription_id,
            "tenant_id": self.tenant_id,
            "provider": self.provider,
            "name": self.name,
            "resource_type": self.resource_type,
            "resource_group": self.resource_group,
            "location": self.location,
            "sku_name": self.sku_name,
            "power_state": self.power_state,
            "tags": self.tags,
            "monthly_retail_cost": self.monthly_retail_cost,
            "source_api": self.source_api,
            "snapshot_timestamp": self.snapshot_timestamp,
            "ingestion_timestamp": self.ingestion_timestamp,
        }


@dataclass
class CostDetailRecord:
    """Historical Azure Cost Management consumption or billing record."""

    cost_record_id: str
    connection_id: str
    subscription_id: str
    billing_year_month: str
    usage_date: date
    resource_id: str | None
    service_name: str
    meter_category: str
    meter_name: str
    cost_in_billing_currency: Decimal
    currency: str
    charge_type: str
    source_api: str
    ingestion_timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary matching PyArrow schema types."""
        return {
            "cost_record_id": self.cost_record_id,
            "connection_id": self.connection_id,
            "subscription_id": self.subscription_id,
            "billing_year_month": self.billing_year_month,
            "usage_date": self.usage_date,
            "resource_id": self.resource_id,
            "service_name": self.service_name,
            "meter_category": self.meter_category,
            "meter_name": self.meter_name,
            "cost_in_billing_currency": self.cost_in_billing_currency,
            "currency": self.currency,
            "charge_type": self.charge_type,
            "source_api": self.source_api,
            "ingestion_timestamp": self.ingestion_timestamp,
        }


@dataclass
class ResourceMetricRecord:
    """Azure Monitor performance time-series telemetry record."""

    metric_record_id: str
    resource_id: str
    subscription_id: str
    metric_name: str
    timestamp: datetime
    average: float | None
    maximum: float | None
    minimum: float | None
    unit: str
    source_api: str
    ingestion_timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary matching PyArrow schema types."""
        return {
            "metric_record_id": self.metric_record_id,
            "resource_id": self.resource_id,
            "subscription_id": self.subscription_id,
            "metric_name": self.metric_name,
            "timestamp": self.timestamp,
            "average": self.average,
            "maximum": self.maximum,
            "minimum": self.minimum,
            "unit": self.unit,
            "source_api": self.source_api,
            "ingestion_timestamp": self.ingestion_timestamp,
        }


@dataclass
class SyncHistoryRecord:
    """Audit ledger entry for a synchronization cycle."""

    sync_id: str
    connection_id: str
    sync_type: str
    status: str
    records_extracted: int
    records_written: int
    duration_ms: int
    error_details: str | None
    started_at: datetime
    completed_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary matching PyArrow schema types."""
        return {
            "sync_id": self.sync_id,
            "connection_id": self.connection_id,
            "sync_type": self.sync_type,
            "status": self.status,
            "records_extracted": self.records_extracted,
            "records_written": self.records_written,
            "duration_ms": self.duration_ms,
            "error_details": self.error_details,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class SyncStageSummary:
    """Detailed summary of a single sync stage."""

    stage_name: str
    status: str = SyncStatus.SUCCESS.value
    records_extracted: int = 0
    records_written: int = 0
    duration_ms: int = 0
    error_details: str | None = None


@dataclass
class OverallSyncResult:
    """Aggregate result of a synchronization execution run."""

    sync_id: str
    connection_id: str
    mode: str
    overall_status: str
    total_extracted: int = 0
    total_written: int = 0
    total_duration_ms: int = 0
    stages: dict[str, SyncStageSummary] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
