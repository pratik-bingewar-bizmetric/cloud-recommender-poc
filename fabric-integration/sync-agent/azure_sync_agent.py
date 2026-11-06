# ruff: noqa: E402
"""Microsoft Fabric FinOps Sync Agent - Command Line Interface & Orchestrator.

Orchestrates Azure Resource Graph extraction, Cost Management ingestion,
Azure Monitor telemetry retrieval, and transactional writes to Microsoft Fabric OneLake Delta tables.

Usage:
    python azure_sync_agent.py --check
    python azure_sync_agent.py --inventory
    python azure_sync_agent.py --cost
    python azure_sync_agent.py --metrics
    python azure_sync_agent.py --full
    python azure_sync_agent.py --full --dry-run
"""

import argparse
import logging
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Set up local import resolution
AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from auth import AuthError, AzureCliAuthManager
from azure_client import AzureInventoryExtractor
from config import SyncAgentConfig
from cost_client import AzureCostExtractor
from delta_writer import OneLakeDeltaWriter
from models import (
    OverallSyncResult,
    SyncHistoryRecord,
    SyncMode,
    SyncStageSummary,
    SyncStatus,
)
from monitor_client import AzureMonitorMetricsExtractor
from sync_logger import setup_logger


def execute_check(
    auth_mgr: AzureCliAuthManager,
    writer: OneLakeDeltaWriter,
    config: SyncAgentConfig,
    logger: logging.Logger,
) -> bool:
    """Validate Azure CLI authentication and OneLake Delta table accessibility."""
    logger.info("=== Running FinOps Sync Agent Pre-flight Verification ===")
    all_ok = True

    # 1. Verify Azure CLI session
    try:
        account = auth_mgr.check_active_account()
        logger.info(
            "Azure CLI Session: OK [User: %s, Subscription: %s, Tenant: %s]",
            account.get("user", {}).get("name"),
            account.get("id"),
            account.get("tenantId"),
        )
    except AuthError as ex:
        logger.error("Azure CLI Session: FAILED - %s", ex)
        return False

    # 2. Verify OneLake connectivity and Delta tables
    logger.info("Checking Microsoft Fabric Lakehouse '%s' on OneLake...", config.lakehouse_name)
    try:
        table_statuses = writer.verify_table_readiness()
        for name, info in table_statuses.items():
            if info.get("exists"):
                logger.info(
                    "OneLake Delta Table '%s': OK (version=%d, rows=%d)",
                    name,
                    info.get("version", 0),
                    info.get("row_count", 0),
                )
            else:
                logger.error(
                    "OneLake Delta Table '%s': MISSING or UNREADABLE (%s)", name, info.get("error")
                )
                all_ok = False
    except Exception as ex:
        logger.error("OneLake Delta Storage Verification: FAILED - %s", ex)
        return False

    if all_ok:
        logger.info("Pre-flight verification completed successfully: READY TO SYNC")
    else:
        logger.warning("Pre-flight verification found issues that may impede synchronization.")

    return all_ok


def run_sync(
    mode: SyncMode,
    config: SyncAgentConfig,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
) -> OverallSyncResult:
    """Execute the designated synchronization pipeline."""
    log = logger or logging.getLogger("finops_sync")
    sync_id = str(uuid.uuid4())
    start_time = time.time()
    started_at = datetime.now(UTC)

    result = OverallSyncResult(
        sync_id=sync_id,
        connection_id=config.connection_id,
        mode=mode.value,
        overall_status=SyncStatus.STARTED.value,
    )

    auth_mgr = AzureCliAuthManager(
        expected_subscription_id=config.subscription_id,
        expected_tenant_id=config.tenant_id,
    )
    writer = OneLakeDeltaWriter(auth_mgr, config)

    log.info(
        "Starting FinOps Sync Execution [ID: %s, Mode: %s, DryRun: %s, Subscription: %s]",
        sync_id,
        mode.value,
        dry_run,
        config.subscription_id,
    )

    discovered_resources: list[dict[str, str]] = []

    # -------------------------------------------------------------------------
    # Stage 1: Resource Inventory
    # -------------------------------------------------------------------------
    if mode in (SyncMode.INVENTORY, SyncMode.FULL, SyncMode.METRICS):
        stage = SyncStageSummary(stage_name="inventory")
        stage_start = time.time()
        try:
            log.info("--- Stage 1: Azure Resource Graph Inventory Extraction ---")
            inv_extractor = AzureInventoryExtractor(auth_mgr, config)
            inventory_records = inv_extractor.extract_inventory()
            stage.records_extracted = len(inventory_records)

            # Keep candidate items for metrics extraction
            discovered_resources = [
                {"id": r.resource_id, "type": r.resource_type} for r in inventory_records
            ]

            if mode in (SyncMode.INVENTORY, SyncMode.FULL):
                if not dry_run:
                    written = writer.write_inventory_snapshot(inventory_records)
                    stage.records_written = written
                else:
                    log.info(
                        "[DRY-RUN] Skipping OneLake write for %d inventory records.",
                        len(inventory_records),
                    )
                    stage.records_written = 0

            stage.status = SyncStatus.SUCCESS.value
        except Exception as ex:
            log.error("Stage 'inventory' failed: %s", ex, exc_info=True)
            stage.status = SyncStatus.FAILED.value
            stage.error_details = str(ex)
            result.errors.append(f"Inventory stage error: {ex}")

        stage.duration_ms = int((time.time() - stage_start) * 1000)
        result.stages["inventory"] = stage
        result.total_extracted += stage.records_extracted
        result.total_written += stage.records_written

    # -------------------------------------------------------------------------
    # Stage 2: Azure Cost Management
    # -------------------------------------------------------------------------
    if mode in (SyncMode.COST, SyncMode.FULL):
        stage = SyncStageSummary(stage_name="cost")
        stage_start = time.time()
        try:
            log.info("--- Stage 2: Azure Cost Management Extraction ---")
            cost_extractor = AzureCostExtractor(auth_mgr, config)
            cost_records = cost_extractor.extract_costs()
            stage.records_extracted = len(cost_records)

            if not dry_run:
                total_ext, written = writer.write_cost_details(cost_records)
                stage.records_written = written
            else:
                log.info("[DRY-RUN] Skipping OneLake write for %d cost records.", len(cost_records))
                stage.records_written = 0

            stage.status = SyncStatus.SUCCESS.value
        except Exception as ex:
            log.error("Stage 'cost' failed: %s", ex, exc_info=True)
            stage.status = SyncStatus.FAILED.value
            stage.error_details = str(ex)
            result.errors.append(f"Cost stage error: {ex}")

        stage.duration_ms = int((time.time() - stage_start) * 1000)
        result.stages["cost"] = stage
        result.total_extracted += stage.records_extracted
        result.total_written += stage.records_written

    # -------------------------------------------------------------------------
    # Stage 3: Azure Monitor Metrics
    # -------------------------------------------------------------------------
    if mode in (SyncMode.METRICS, SyncMode.FULL):
        stage = SyncStageSummary(stage_name="metrics")
        stage_start = time.time()
        try:
            log.info("--- Stage 3: Azure Monitor Metrics Extraction ---")
            # If inventory was not run, discover candidate resources directly
            if not discovered_resources:
                inv_extractor = AzureInventoryExtractor(auth_mgr, config)
                inv_recs = inv_extractor.extract_inventory()
                discovered_resources = [
                    {"id": r.resource_id, "type": r.resource_type} for r in inv_recs
                ]

            monitor_extractor = AzureMonitorMetricsExtractor(auth_mgr, config)
            metric_records = monitor_extractor.extract_metrics_for_resources(discovered_resources)
            stage.records_extracted = len(metric_records)

            if not dry_run:
                total_ext, written = writer.write_metrics(metric_records)
                stage.records_written = written
            else:
                log.info(
                    "[DRY-RUN] Skipping OneLake write for %d metric records.", len(metric_records)
                )
                stage.records_written = 0

            stage.status = SyncStatus.SUCCESS.value
        except Exception as ex:
            log.error("Stage 'metrics' failed: %s", ex, exc_info=True)
            stage.status = SyncStatus.FAILED.value
            stage.error_details = str(ex)
            result.errors.append(f"Metrics stage error: {ex}")

        stage.duration_ms = int((time.time() - stage_start) * 1000)
        result.stages["metrics"] = stage
        result.total_extracted += stage.records_extracted
        result.total_written += stage.records_written

    # -------------------------------------------------------------------------
    # Stage 4: Sync Audit Ledger Entry
    # -------------------------------------------------------------------------
    total_elapsed_ms = int((time.time() - start_time) * 1000)
    result.total_duration_ms = total_elapsed_ms

    if all(s.status == SyncStatus.SUCCESS.value for s in result.stages.values()):
        result.overall_status = SyncStatus.SUCCESS.value
    elif any(s.status == SyncStatus.SUCCESS.value for s in result.stages.values()):
        result.overall_status = SyncStatus.PARTIAL.value
    else:
        result.overall_status = SyncStatus.FAILED.value

    completed_at = datetime.now(UTC)

    if not dry_run:
        try:
            history_rec = SyncHistoryRecord(
                sync_id=sync_id,
                connection_id=config.connection_id,
                sync_type=mode.value,
                status=result.overall_status,
                records_extracted=result.total_extracted,
                records_written=result.total_written,
                duration_ms=total_elapsed_ms,
                error_details="; ".join(result.errors) if result.errors else None,
                started_at=started_at,
                completed_at=completed_at,
            )
            writer.write_sync_history(history_rec)
        except Exception as ex:
            log.warning("Failed to record sync history audit record: %s", ex)

    log.info(
        "=== FinOps Sync Execution Completed: Status=%s, Extracted=%d, Written=%d, Duration=%dms ===",
        result.overall_status,
        result.total_extracted,
        result.total_written,
        result.total_duration_ms,
    )

    return result


def main() -> int:
    """CLI Entry point for the FinOps sync agent."""
    parser = argparse.ArgumentParser(
        description="Microsoft Fabric FinOps Sync Agent - Azure Extraction & OneLake Ingestion",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check", action="store_true", help="Run pre-flight connectivity verification"
    )
    group.add_argument(
        "--inventory", action="store_true", help="Synchronize Azure Resource Graph inventory"
    )
    group.add_argument(
        "--cost", action="store_true", help="Synchronize Azure Cost Management consumption"
    )
    group.add_argument("--metrics", action="store_true", help="Synchronize Azure Monitor telemetry")
    group.add_argument("--full", action="store_true", help="Execute complete end-to-end sync cycle")

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and validate data without writing to OneLake",
    )
    parser.add_argument("--subscription-id", type=str, help="Override Azure Subscription ID")
    parser.add_argument("--workspace-id", type=str, help="Override Fabric Workspace ID")
    parser.add_argument("--lakehouse-id", type=str, help="Override Fabric Lakehouse ID")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()
    logger = setup_logger("finops_sync", verbose=args.verbose)

    config = SyncAgentConfig.load()
    if args.subscription_id:
        config.subscription_id = args.subscription_id
    if args.workspace_id:
        config.workspace_id = args.workspace_id
    if args.lakehouse_id:
        config.lakehouse_id = args.lakehouse_id

    auth_mgr = AzureCliAuthManager(
        expected_subscription_id=config.subscription_id,
        expected_tenant_id=config.tenant_id,
    )
    writer = OneLakeDeltaWriter(auth_mgr, config)

    if args.check:
        success = execute_check(auth_mgr, writer, config, logger)
        return 0 if success else 1

    mode = SyncMode.FULL
    if args.inventory:
        mode = SyncMode.INVENTORY
    elif args.cost:
        mode = SyncMode.COST
    elif args.metrics:
        mode = SyncMode.METRICS
    elif args.full:
        mode = SyncMode.FULL

    result = run_sync(mode=mode, config=config, dry_run=args.dry_run, logger=logger)
    return 0 if result.overall_status in (SyncStatus.SUCCESS.value, SyncStatus.PARTIAL.value) else 1


if __name__ == "__main__":
    sys.exit(main())
