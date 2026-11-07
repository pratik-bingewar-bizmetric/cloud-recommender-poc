"""Unit tests for FinOps Sync Agent Models and DTOs."""

from datetime import UTC, date, datetime
from decimal import Decimal

from models import (
    CostDetailRecord,
    OverallSyncResult,
    ResourceInventoryRecord,
    ResourceMetricRecord,
    SyncHistoryRecord,
    SyncMode,
    SyncStageSummary,
    SyncStatus,
)


def test_resource_inventory_record_to_dict():
    now = datetime.now(UTC)
    rec = ResourceInventoryRecord(
        resource_id="/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm1",
        connection_id="conn-1",
        subscription_id="sub-1",
        tenant_id="tenant-1",
        provider="azure",
        name="vm1",
        resource_type="Microsoft.Compute/virtualMachines",
        resource_group="rg-1",
        location="eastus",
        sku_name="Standard_B2s",
        power_state="VM running",
        tags='{"env": "poc"}',
        monthly_retail_cost=Decimal("45.5000"),
        source_api="Azure Resource Graph",
        snapshot_timestamp=now,
        ingestion_timestamp=now,
    )
    d = rec.to_dict()
    assert d["resource_id"] == rec.resource_id
    assert d["name"] == "vm1"
    assert d["power_state"] == "VM running"
    assert d["monthly_retail_cost"] == Decimal("45.5000")
    assert d["snapshot_timestamp"] == now


def test_cost_detail_record_to_dict():
    now = datetime.now(UTC)
    u_date = date(2026, 10, 19)
    rec = CostDetailRecord(
        cost_record_id="hash-1234",
        connection_id="conn-1",
        subscription_id="sub-1",
        billing_year_month="2026-10",
        usage_date=u_date,
        resource_id="/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm1",
        service_name="Virtual Machines",
        meter_category="Virtual Machines",
        meter_name="B2s",
        cost_in_billing_currency=Decimal("12.3456"),
        currency="USD",
        charge_type="Usage",
        source_api="Azure Cost Management Query API",
        ingestion_timestamp=now,
    )
    d = rec.to_dict()
    assert d["cost_record_id"] == "hash-1234"
    assert d["billing_year_month"] == "2026-10"
    assert d["usage_date"] == u_date
    assert d["cost_in_billing_currency"] == Decimal("12.3456")


def test_resource_metric_record_to_dict():
    now = datetime.now(UTC)
    rec = ResourceMetricRecord(
        metric_record_id="metric-1234",
        resource_id="/subscriptions/sub-1/rg/db",
        subscription_id="sub-1",
        metric_name="cpu_percent",
        timestamp=now,
        average=12.5,
        maximum=35.0,
        minimum=2.1,
        unit="Percent",
        source_api="Azure Monitor Metrics API",
        ingestion_timestamp=now,
    )
    d = rec.to_dict()
    assert d["metric_record_id"] == "metric-1234"
    assert d["average"] == 12.5
    assert d["maximum"] == 35.0
    assert d["unit"] == "Percent"


def test_sync_history_record_to_dict():
    now = datetime.now(UTC)
    rec = SyncHistoryRecord(
        sync_id="sync-abc",
        connection_id="conn-1",
        sync_type="full",
        status="SUCCESS",
        records_extracted=50,
        records_written=45,
        duration_ms=2500,
        error_details=None,
        started_at=now,
        completed_at=now,
    )
    d = rec.to_dict()
    assert d["sync_id"] == "sync-abc"
    assert d["status"] == "SUCCESS"
    assert d["records_extracted"] == 50
    assert d["records_written"] == 45


def test_overall_sync_result():
    res = OverallSyncResult(
        sync_id="test-run",
        connection_id="conn-1",
        mode=SyncMode.FULL.value,
        overall_status=SyncStatus.SUCCESS.value,
    )
    res.stages["inventory"] = SyncStageSummary(
        stage_name="inventory", records_extracted=10, records_written=10, duration_ms=500
    )
    res.total_extracted += 10
    res.total_written += 10
    assert res.total_extracted == 10
    assert res.stages["inventory"].records_written == 10
