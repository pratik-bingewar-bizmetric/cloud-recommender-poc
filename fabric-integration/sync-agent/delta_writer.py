# ruff: noqa: E402
"""Microsoft Fabric FinOps Sync Agent - OneLake Delta Lake Writer.

Encapsulates all write, deduplication, and read-back operations for Microsoft Fabric
OneLake Delta tables using Delta-rs and PyArrow.
Enforces idempotent writes and schema compliance against approved analytical tables:
- resource_inventory
- cost_details
- resource_metrics
- sync_history
"""

import logging
import sys
from pathlib import Path
from typing import Any

import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

# Ensure schemas from fabric-integration/lakehouse can be imported
LAKEHOUSE_DIR = Path(__file__).resolve().parent.parent / "lakehouse"
if str(LAKEHOUSE_DIR) not in sys.path:
    sys.path.insert(0, str(LAKEHOUSE_DIR))

try:
    from schemas import (
        COST_DETAILS_PARTITIONS,
        COST_DETAILS_SCHEMA,
        RESOURCE_INVENTORY_PARTITIONS,
        RESOURCE_INVENTORY_SCHEMA,
        RESOURCE_METRICS_PARTITIONS,
        RESOURCE_METRICS_SCHEMA,
        SYNC_HISTORY_PARTITIONS,
        SYNC_HISTORY_SCHEMA,
        TABLE_REGISTRY,
    )
except ImportError as ex:
    raise ImportError(f"Failed to import analytical schemas from {LAKEHOUSE_DIR}: {ex}") from ex

from auth import AUDIENCE_STORAGE, AzureCliAuthManager
from config import SyncAgentConfig
from models import (
    CostDetailRecord,
    ResourceInventoryRecord,
    ResourceMetricRecord,
    SyncHistoryRecord,
)

logger = logging.getLogger("azure_sync_agent.delta_writer")


class OneLakeDeltaWriter:
    """Manages transactional appends, deduplication, and table queries on OneLake."""

    def __init__(self, auth_manager: AzureCliAuthManager, config: SyncAgentConfig) -> None:
        self.auth_manager = auth_manager
        self.config = config

    def _get_storage_options(self) -> dict[str, str]:
        """Obtain active storage options with fresh OneLake Bearer token."""
        token = self.auth_manager.get_token(AUDIENCE_STORAGE)
        return {
            "bearer_token": token,
            "account_name": "onelake",
        }

    def verify_table_readiness(self) -> dict[str, Any]:
        """Inspect and verify all 5 approved analytical Delta tables on OneLake."""
        options = self._get_storage_options()
        status: dict[str, Any] = {}

        for table_name, _meta in TABLE_REGISTRY.items():
            table_uri = self.config.get_table_uri(table_name)
            try:
                dt = DeltaTable(table_uri, storage_options=options)
                version = dt.version()
                files_count = len(dt.file_uris())
                pa_tbl = dt.to_pyarrow_table()
                row_count = pa_tbl.num_rows

                status[table_name] = {
                    "exists": True,
                    "version": version,
                    "file_count": files_count,
                    "row_count": row_count,
                    "uri": table_uri,
                }
                logger.info(
                    "Table '%s' ready on OneLake: version=%d, files=%d, rows=%d",
                    table_name,
                    version,
                    files_count,
                    row_count,
                )
            except Exception as ex:
                logger.warning("Table '%s' check failed at %s: %s", table_name, table_uri, ex)
                status[table_name] = {
                    "exists": False,
                    "error": str(ex),
                    "uri": table_uri,
                }

        return status

    def write_inventory_snapshot(self, records: list[ResourceInventoryRecord]) -> int:
        """Append an inventory snapshot to resource_inventory Delta table."""
        if not records:
            logger.info("No resource inventory records to write.")
            return 0

        table_uri = self.config.get_table_uri("resource_inventory")
        storage_options = self._get_storage_options()

        dicts = [rec.to_dict() for rec in records]
        arrow_table = pa.Table.from_pylist(dicts, schema=RESOURCE_INVENTORY_SCHEMA)

        logger.info(
            "Writing %d inventory records to OneLake table 'resource_inventory'...",
            arrow_table.num_rows,
        )

        write_deltalake(
            table_uri,
            arrow_table,
            mode="append",
            partition_by=RESOURCE_INVENTORY_PARTITIONS,
            schema_mode="merge",
            storage_options=storage_options,
        )

        logger.info("Successfully appended %d records to resource_inventory.", len(records))
        return len(records)

    def write_cost_details(self, records: list[CostDetailRecord]) -> tuple[int, int]:
        """Deduplicate and append cost details to cost_details Delta table.

        Returns:
            Tuple of (total_extracted, records_written).
        """
        if not records:
            logger.info("No cost detail records provided.")
            return (0, 0)

        table_uri = self.config.get_table_uri("cost_details")
        storage_options = self._get_storage_options()

        # Step 1: Read existing cost_record_id values from OneLake Delta table
        existing_ids: set[str] = set()
        try:
            dt = DeltaTable(table_uri, storage_options=storage_options)
            if dt.version() >= 0:
                cost_id_table = dt.to_pyarrow_table(columns=["cost_record_id"])
                existing_ids = set(cost_id_table.column("cost_record_id").to_pylist())
                logger.info(
                    "Found %d pre-existing cost records in Delta table for deduplication.",
                    len(existing_ids),
                )
        except Exception as ex:
            logger.warning(
                "Could not read pre-existing cost_record_ids (table may be empty): %s", ex
            )

        # Step 2: Deduplicate incoming batch against existing table and against itself
        deduped_records: list[CostDetailRecord] = []
        seen_in_batch: set[str] = set()

        for rec in records:
            rec_id = rec.cost_record_id
            if rec_id in existing_ids:
                continue
            if rec_id in seen_in_batch:
                continue
            seen_in_batch.add(rec_id)
            deduped_records.append(rec)

        new_count = len(deduped_records)
        logger.info(
            "Cost deduplication summary: extracted=%d, duplicates_skipped=%d, new_records_to_write=%d",
            len(records),
            len(records) - new_count,
            new_count,
        )

        if new_count == 0:
            logger.info("All cost records already exist in OneLake. No new rows appended.")
            return (len(records), 0)

        # Step 3: Append new records
        dicts = [rec.to_dict() for rec in deduped_records]
        arrow_table = pa.Table.from_pylist(dicts, schema=COST_DETAILS_SCHEMA)

        write_deltalake(
            table_uri,
            arrow_table,
            mode="append",
            partition_by=COST_DETAILS_PARTITIONS,
            schema_mode="merge",
            storage_options=storage_options,
        )

        logger.info("Successfully appended %d new cost records to OneLake.", new_count)
        return (len(records), new_count)

    def write_metrics(self, records: list[ResourceMetricRecord]) -> tuple[int, int]:
        """Deduplicate and append performance metrics to resource_metrics Delta table.

        Returns:
            Tuple of (total_extracted, records_written).
        """
        if not records:
            logger.info("No resource metrics records provided.")
            return (0, 0)

        table_uri = self.config.get_table_uri("resource_metrics")
        storage_options = self._get_storage_options()

        # Step 1: Read existing metric_record_id values
        existing_ids: set[str] = set()
        try:
            dt = DeltaTable(table_uri, storage_options=storage_options)
            if dt.version() >= 0:
                metric_id_table = dt.to_pyarrow_table(columns=["metric_record_id"])
                existing_ids = set(metric_id_table.column("metric_record_id").to_pylist())
                logger.info(
                    "Found %d pre-existing metric records in Delta table for deduplication.",
                    len(existing_ids),
                )
        except Exception as ex:
            logger.warning("Could not read pre-existing metric_record_ids: %s", ex)

        # Step 2: Deduplicate
        deduped_records: list[ResourceMetricRecord] = []
        seen_in_batch: set[str] = set()

        for rec in records:
            rec_id = rec.metric_record_id
            if rec_id in existing_ids:
                continue
            if rec_id in seen_in_batch:
                continue
            seen_in_batch.add(rec_id)
            deduped_records.append(rec)

        new_count = len(deduped_records)
        logger.info(
            "Metrics deduplication summary: extracted=%d, duplicates_skipped=%d, new_records_to_write=%d",
            len(records),
            len(records) - new_count,
            new_count,
        )

        if new_count == 0:
            logger.info("All metrics records already exist in OneLake. No new rows appended.")
            return (len(records), 0)

        # Step 3: Append new records
        dicts = [rec.to_dict() for rec in deduped_records]
        arrow_table = pa.Table.from_pylist(dicts, schema=RESOURCE_METRICS_SCHEMA)

        write_deltalake(
            table_uri,
            arrow_table,
            mode="append",
            partition_by=RESOURCE_METRICS_PARTITIONS,
            schema_mode="merge",
            storage_options=storage_options,
        )

        logger.info("Successfully appended %d new metric records to OneLake.", new_count)
        return (len(records), new_count)

    def write_sync_history(self, record: SyncHistoryRecord) -> None:
        """Append an audit execution ledger entry to sync_history Delta table."""
        table_uri = self.config.get_table_uri("sync_history")
        storage_options = self._get_storage_options()

        arrow_table = pa.Table.from_pylist([record.to_dict()], schema=SYNC_HISTORY_SCHEMA)

        write_deltalake(
            table_uri,
            arrow_table,
            mode="append",
            partition_by=SYNC_HISTORY_PARTITIONS if SYNC_HISTORY_PARTITIONS else None,
            schema_mode="merge",
            storage_options=storage_options,
        )

        logger.info(
            "Recorded sync execution audit entry: sync_id=%s, type=%s, status=%s, written=%d",
            record.sync_id,
            record.sync_type,
            record.status,
            record.records_written,
        )
