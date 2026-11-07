"""Microsoft Fabric FinOps Analytical Lakehouse - PyArrow & Delta Schemas.

Defines the 5 approved analytical Delta table schemas for the Cloud FinOps Recommender:
1. resource_inventory - Discovered Azure cloud infrastructure snapshots
2. cost_details - Historical usage & billed records from Azure Cost Management
3. resource_metrics - Performance telemetry from Azure Monitor
4. token_telemetry - AI model inference token consumption & economics
5. sync_history - Ingestion audit ledger

Operational Storage Rule:
Operational connection management (CRUD on cloud_connections with credentials)
is explicitly kept out of Delta Lake and retained in the secure operational store.
"""

from typing import Any

import pyarrow as pa

# -----------------------------------------------------------------------------
# 1. resource_inventory Schema
# -----------------------------------------------------------------------------
RESOURCE_INVENTORY_SCHEMA = pa.schema(
    [
        pa.field("resource_id", pa.string(), nullable=False),
        pa.field("connection_id", pa.string(), nullable=False),
        pa.field("subscription_id", pa.string(), nullable=False),
        pa.field("tenant_id", pa.string(), nullable=True),
        pa.field("provider", pa.string(), nullable=False),
        pa.field("name", pa.string(), nullable=False),
        pa.field("resource_type", pa.string(), nullable=False),
        pa.field("resource_group", pa.string(), nullable=True),
        pa.field("location", pa.string(), nullable=False),
        pa.field("sku_name", pa.string(), nullable=True),
        pa.field("power_state", pa.string(), nullable=True),
        pa.field("tags", pa.string(), nullable=True),  # JSON serialized dictionary
        pa.field("monthly_retail_cost", pa.decimal128(12, 4), nullable=True),
        pa.field("source_api", pa.string(), nullable=False),
        pa.field("snapshot_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("ingestion_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

RESOURCE_INVENTORY_PARTITIONS = ["provider", "subscription_id"]

# -----------------------------------------------------------------------------
# 2. cost_details Schema
# -----------------------------------------------------------------------------
COST_DETAILS_SCHEMA = pa.schema(
    [
        pa.field("cost_record_id", pa.string(), nullable=False),
        pa.field("connection_id", pa.string(), nullable=False),
        pa.field("subscription_id", pa.string(), nullable=False),
        pa.field("billing_year_month", pa.string(), nullable=False),  # YYYY-MM
        pa.field("usage_date", pa.date32(), nullable=False),
        pa.field("resource_id", pa.string(), nullable=True),
        pa.field("service_name", pa.string(), nullable=False),
        pa.field("meter_category", pa.string(), nullable=False),
        pa.field("meter_name", pa.string(), nullable=False),
        pa.field("cost_in_billing_currency", pa.decimal128(14, 4), nullable=False),
        pa.field("currency", pa.string(), nullable=False),
        pa.field("charge_type", pa.string(), nullable=False),
        pa.field("source_api", pa.string(), nullable=False),
        pa.field("ingestion_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

COST_DETAILS_PARTITIONS = ["subscription_id", "billing_year_month"]

# -----------------------------------------------------------------------------
# 3. resource_metrics Schema
# -----------------------------------------------------------------------------
RESOURCE_METRICS_SCHEMA = pa.schema(
    [
        pa.field("metric_record_id", pa.string(), nullable=False),
        pa.field("resource_id", pa.string(), nullable=False),
        pa.field("subscription_id", pa.string(), nullable=False),
        pa.field("metric_name", pa.string(), nullable=False),
        pa.field("timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("average", pa.float64(), nullable=True),
        pa.field("maximum", pa.float64(), nullable=True),
        pa.field("minimum", pa.float64(), nullable=True),
        pa.field("unit", pa.string(), nullable=False),
        pa.field("source_api", pa.string(), nullable=False),
        pa.field("ingestion_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

RESOURCE_METRICS_PARTITIONS = ["subscription_id"]

# -----------------------------------------------------------------------------
# 4. token_telemetry Schema
# -----------------------------------------------------------------------------
TOKEN_TELEMETRY_SCHEMA = pa.schema(
    [
        pa.field("event_id", pa.string(), nullable=False),
        pa.field("connection_id", pa.string(), nullable=False),
        pa.field("model_name", pa.string(), nullable=False),
        pa.field("deployment_name", pa.string(), nullable=True),
        pa.field("timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("prompt_tokens", pa.int64(), nullable=False),
        pa.field("completion_tokens", pa.int64(), nullable=False),
        pa.field("total_tokens", pa.int64(), nullable=False),
        pa.field("latency_ms", pa.int64(), nullable=True),
        pa.field("estimated_cost_usd", pa.decimal128(10, 6), nullable=False),
        pa.field("pricing_status", pa.string(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("ingestion_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

TOKEN_TELEMETRY_PARTITIONS = ["connection_id"]

# -----------------------------------------------------------------------------
# 5. sync_history Schema
# -----------------------------------------------------------------------------
SYNC_HISTORY_SCHEMA = pa.schema(
    [
        pa.field("sync_id", pa.string(), nullable=False),
        pa.field("connection_id", pa.string(), nullable=False),
        pa.field("sync_type", pa.string(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
        pa.field("records_extracted", pa.int64(), nullable=False),
        pa.field("records_written", pa.int64(), nullable=False),
        pa.field("duration_ms", pa.int64(), nullable=False),
        pa.field("error_details", pa.string(), nullable=True),
        pa.field("started_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("completed_at", pa.timestamp("us", tz="UTC"), nullable=True),
    ]
)

SYNC_HISTORY_PARTITIONS: list[str] = []  # Small audit log; unpartitioned

# -----------------------------------------------------------------------------
# Table Registry Definition
# -----------------------------------------------------------------------------
TABLE_REGISTRY: dict[str, dict[str, Any]] = {
    "resource_inventory": {
        "schema": RESOURCE_INVENTORY_SCHEMA,
        "partition_cols": RESOURCE_INVENTORY_PARTITIONS,
        "primary_key": "resource_id",
        "description": "Discovered Azure infrastructure resource snapshots",
    },
    "cost_details": {
        "schema": COST_DETAILS_SCHEMA,
        "partition_cols": COST_DETAILS_PARTITIONS,
        "primary_key": "cost_record_id",
        "description": "Historical Azure Cost Management consumption records",
    },
    "resource_metrics": {
        "schema": RESOURCE_METRICS_SCHEMA,
        "partition_cols": RESOURCE_METRICS_PARTITIONS,
        "primary_key": "metric_record_id",
        "description": "Performance metrics from Azure Monitor",
    },
    "token_telemetry": {
        "schema": TOKEN_TELEMETRY_SCHEMA,
        "partition_cols": TOKEN_TELEMETRY_PARTITIONS,
        "primary_key": "event_id",
        "description": "AI model inference token consumption and unit costs",
    },
    "sync_history": {
        "schema": SYNC_HISTORY_SCHEMA,
        "partition_cols": SYNC_HISTORY_PARTITIONS,
        "primary_key": "sync_id",
        "description": "Audit log for batch sync runs",
    },
}
