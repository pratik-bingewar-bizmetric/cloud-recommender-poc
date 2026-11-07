"""Microsoft Fabric Lakehouse - Repeatable Delta Schema Initialization.

Initializes the 5 approved analytical Delta tables on OneLake using Delta-rs:
1. resource_inventory (partitioned by provider, subscription_id)
2. cost_details (partitioned by subscription_id, billing_year_month)
3. resource_metrics (partitioned by subscription_id)
4. token_telemetry (partitioned by connection_id)
5. sync_history (unpartitioned audit ledger)

Idempotency & Integrity Guarantees:
- Never inserts mock, synthetic, or fake business records.
- Detects existing tables before creation.
- Verifies schema parity on existing tables rather than overwriting.
- Validates Delta transaction log creation and table read-back.
"""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import deltalake
import pyarrow as pa
from deltalake.exceptions import TableNotFoundError

# Import approved analytical schemas
from schemas import TABLE_REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("init_delta_schemas")

CONFIG_PATH = Path(__file__).resolve().parent / "lakehouse_config.json"


def get_storage_token() -> str:
    """Acquire storage token for OneLake ADLS Gen2 DFS endpoint via Azure CLI."""
    az_cmd = shutil.which("az.cmd") or shutil.which("az") or "az"
    cmd = [
        az_cmd,
        "account",
        "get-access-token",
        "--resource",
        "https://storage.azure.com",
        "--output",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Azure CLI failed to obtain OneLake storage token: {proc.stderr}")
    data = json.loads(proc.stdout)
    token = data.get("accessToken")
    if not token:
        raise RuntimeError("Empty storage token returned by Azure CLI.")
    return token


def load_lakehouse_config() -> dict[str, Any]:
    """Load lakehouse_config.json generated during provisioning."""
    if not CONFIG_PATH.exists():
        from provision_lakehouse import provision_or_get_lakehouse

        return provision_or_get_lakehouse()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def initialize_analytical_tables() -> dict[str, Any]:
    """Initialize all 5 approved analytical Delta tables idempotently."""
    config = load_lakehouse_config()
    workspace_id = config["workspaceId"]
    lakehouse_id = config["lakehouseId"]

    token = get_storage_token()
    storage_options = {
        "bearer_token": token,
        "account_name": "onelake",
    }

    results: dict[str, Any] = {}

    for table_name, table_spec in TABLE_REGISTRY.items():
        schema: pa.Schema = table_spec["schema"]
        partition_cols: list[str] = table_spec["partition_cols"]
        primary_key: str = table_spec["primary_key"]

        table_path = f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/{lakehouse_id}/Tables/{table_name}"
        logger.info("Processing table '%s' at: %s", table_name, table_path)

        # Step 1: Check if table already exists
        try:
            dt = deltalake.DeltaTable(table_path, storage_options=storage_options)
            logger.info(
                "Table '%s' already exists (version: %d). Validating schema...",
                table_name,
                dt.version(),
            )

            # Validate schema field names match
            existing_fields = [f.name for f in dt.schema().fields]
            expected_fields = schema.names
            if set(existing_fields) != set(expected_fields):
                raise ValueError(
                    f"Schema mismatch on existing table '{table_name}'. "
                    f"Expected fields: {expected_fields}, Found: {existing_fields}"
                )
            # Validate partition columns match
            existing_partitions = dt.metadata().partition_columns
            if set(existing_partitions) != set(partition_cols):
                raise ValueError(
                    f"Partition mismatch on existing table '{table_name}'. "
                    f"Expected: {partition_cols}, Found: {existing_partitions}"
                )
            action = "reused_existing"
        except (TableNotFoundError, FileNotFoundError):
            # Step 2: Initialize empty Delta table with approved schema
            logger.info(
                "Table '%s' not found. Initializing empty Delta table with approved schema...",
                table_name,
            )
            empty_table = pa.Table.from_batches([], schema=schema)
            deltalake.write_deltalake(
                table_path,
                empty_table,
                partition_by=partition_cols if partition_cols else None,
                mode="error",  # Fail if another process created it concurrently
                storage_options=storage_options,
            )
            dt = deltalake.DeltaTable(table_path, storage_options=storage_options)
            action = "created_new"

        # Step 3: Verification & Read-back
        dt_meta = dt.metadata()
        pa_table = dt.to_pyarrow_table()
        row_count = pa_table.num_rows

        if row_count > 0:
            logger.warning("Table '%s' contains %d existing rows.", table_name, row_count)
        else:
            logger.info(
                "Verified table '%s' is clean with 0 synthetic business records.", table_name
            )

        table_info = {
            "tableName": table_name,
            "action": action,
            "tablePath": table_path,
            "version": dt.version(),
            "rowCount": row_count,
            "fieldCount": len(schema.names),
            "partitionColumns": dt_meta.partition_columns,
            "primaryKey": primary_key,
            "description": table_spec["description"],
            "hasValidDeltaLog": True,
        }
        results[table_name] = table_info
        logger.info(
            "Table '%s' verified successfully: version=%d, partitions=%s, rows=%d",
            table_name,
            dt.version(),
            dt_meta.partition_columns,
            row_count,
        )

    return {
        "workspaceId": workspace_id,
        "lakehouseId": lakehouse_id,
        "tablesInitialized": len(results),
        "tables": results,
    }


if __name__ == "__main__":
    summary = initialize_analytical_tables()
    print("\n=== Analytical Delta Tables Initialized Successfully ===")
    print(json.dumps(summary, indent=2))
