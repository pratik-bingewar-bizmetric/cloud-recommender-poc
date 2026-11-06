"""Unit tests for FinOps Sync Agent CLI and Pipeline Orchestrator."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from azure_sync_agent import execute_check, run_sync
from config import SyncAgentConfig
from models import (
    ResourceInventoryRecord,
    SyncMode,
    SyncStatus,
)


def test_execute_check():
    mock_auth = MagicMock()
    mock_auth.check_active_account.return_value = {
        "id": "sub-123",
        "tenantId": "tenant-456",
        "user": {"name": "test-user"},
    }
    mock_writer = MagicMock()
    mock_writer.verify_table_readiness.return_value = {
        "resource_inventory": {"exists": True, "version": 0, "row_count": 0},
        "cost_details": {"exists": True, "version": 0, "row_count": 0},
    }

    mock_logger = MagicMock()
    config = SyncAgentConfig()

    ok = execute_check(mock_auth, mock_writer, config, mock_logger)
    assert ok is True


def test_run_sync_full_dry_run():
    config = SyncAgentConfig(subscription_id="sub-abc")
    mock_logger = MagicMock()

    now = datetime.now(UTC)
    mock_inv_rec = ResourceInventoryRecord(
        resource_id="/subscriptions/sub-abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        connection_id="conn-1",
        subscription_id="sub-abc",
        tenant_id="tenant-1",
        provider="azure",
        name="vm1",
        resource_type="Microsoft.Compute/virtualMachines",
        resource_group="rg",
        location="eastus",
        sku_name="Standard_B2s",
        power_state="Running",
        tags=None,
        monthly_retail_cost=None,
        source_api="ARG",
        snapshot_timestamp=now,
        ingestion_timestamp=now,
    )

    with (
        patch(
            "azure_sync_agent.AzureInventoryExtractor.extract_inventory",
            return_value=[mock_inv_rec],
        ),
        patch("azure_sync_agent.AzureCostExtractor.extract_costs", return_value=[]),
        patch(
            "azure_sync_agent.AzureMonitorMetricsExtractor.extract_metrics_for_resources",
            return_value=[],
        ),
        patch("azure_sync_agent.OneLakeDeltaWriter.write_inventory_snapshot") as mock_write_inv,
        patch("azure_sync_agent.OneLakeDeltaWriter.write_sync_history") as mock_write_hist,
    ):
        res = run_sync(mode=SyncMode.FULL, config=config, dry_run=True, logger=mock_logger)

        assert res.overall_status == SyncStatus.SUCCESS.value
        assert res.total_extracted == 1
        assert res.total_written == 0  # Dry-run
        mock_write_inv.assert_not_called()
        mock_write_hist.assert_not_called()


def test_run_sync_full_execution():
    config = SyncAgentConfig(subscription_id="sub-abc")
    mock_logger = MagicMock()

    now = datetime.now(UTC)
    mock_inv_rec = ResourceInventoryRecord(
        resource_id="/subscriptions/sub-abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        connection_id="conn-1",
        subscription_id="sub-abc",
        tenant_id="tenant-1",
        provider="azure",
        name="vm1",
        resource_type="Microsoft.Compute/virtualMachines",
        resource_group="rg",
        location="eastus",
        sku_name="Standard_B2s",
        power_state="Running",
        tags=None,
        monthly_retail_cost=None,
        source_api="ARG",
        snapshot_timestamp=now,
        ingestion_timestamp=now,
    )

    with (
        patch(
            "azure_sync_agent.AzureInventoryExtractor.extract_inventory",
            return_value=[mock_inv_rec],
        ),
        patch("azure_sync_agent.AzureCostExtractor.extract_costs", return_value=[]),
        patch(
            "azure_sync_agent.AzureMonitorMetricsExtractor.extract_metrics_for_resources",
            return_value=[],
        ),
        patch(
            "azure_sync_agent.OneLakeDeltaWriter.write_inventory_snapshot", return_value=1
        ) as mock_write_inv,
        patch("azure_sync_agent.OneLakeDeltaWriter.write_cost_details", return_value=(0, 0)),
        patch("azure_sync_agent.OneLakeDeltaWriter.write_metrics", return_value=(0, 0)),
        patch("azure_sync_agent.OneLakeDeltaWriter.write_sync_history") as mock_write_hist,
    ):
        res = run_sync(mode=SyncMode.FULL, config=config, dry_run=False, logger=mock_logger)

        assert res.overall_status == SyncStatus.SUCCESS.value
        assert res.total_extracted == 1
        assert res.total_written == 1
        mock_write_inv.assert_called_once()
        mock_write_hist.assert_called_once()
