"""Unit and integration tests for Microsoft Fabric UDF Lakehouse Delta Reader."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pyarrow as pa
import pytest

from lakehouse.auth import LakehouseAuthError, OneLakeAuthManager
from lakehouse.config import LakehouseReaderConfig
from lakehouse.delta_reader import OneLakeDeltaReader
from lakehouse.diagnostics import LakehouseDiagnostics
from lakehouse.health import LakehouseHealthChecker
from lakehouse.models import (
    CurrencyCostTotal,
    LakehouseCostAnalytics,
    LakehouseInventorySummary,
    LakehouseMetricsSummary,
    LakehouseTokenSummary,
)
from lakehouse.repository import AnalyticalRepository


# -----------------------------------------------------------------------------
# 1. Configuration & Auth Tests
# -----------------------------------------------------------------------------
def test_lakehouse_config_defaults():
    cfg = LakehouseReaderConfig()
    assert cfg.workspace_id == "672a6995-4190-4000-befd-5cc6479c3f74"
    assert cfg.lakehouse_id == "4bba3647-0112-4adc-8b18-f7a422461404"
    assert "abfss://" in cfg.onelake_table_root_uri
    assert cfg.get_table_uri("cost_details").endswith("/Tables/cost_details")


def test_auth_manager_caching():
    cfg = LakehouseReaderConfig()
    auth_mgr = OneLakeAuthManager(cfg)

    future_exp = datetime(2099, 1, 1, 12, 0, tzinfo=timezone.utc)
    with patch.object(
        auth_mgr, "_acquire_token", return_value=("mock-token", "service_principal", future_exp)
    ) as mock_acq:
        t1, m1 = auth_mgr.get_token()
        assert t1 == "mock-token"
        assert m1 == "service_principal"
        assert mock_acq.call_count == 1

        # Second call served from cache
        t2, m2 = auth_mgr.get_token()
        assert t2 == "mock-token"
        assert mock_acq.call_count == 1


def test_auth_manager_missing_identity():
    cfg = LakehouseReaderConfig(tenant_id=None, client_id=None, client_secret=None)
    auth_mgr = OneLakeAuthManager(cfg)

    with patch("shutil.which", return_value=None), \
         patch.dict("os.environ", {}, clear=True):
        with pytest.raises(LakehouseAuthError, match="No valid OneLake storage authentication"):
            auth_mgr._acquire_token()


# -----------------------------------------------------------------------------
# 2. Delta Reader & Empty Table Handling
# -----------------------------------------------------------------------------
def test_delta_reader_empty_table():
    mock_auth = MagicMock(spec=OneLakeAuthManager)
    mock_auth.get_storage_options.return_value = {"bearer_token": "mock"}
    reader = OneLakeDeltaReader(auth_manager=mock_auth, config=LakehouseReaderConfig())

    with patch("lakehouse.delta_reader.DeltaTable") as mock_dt:
        mock_instance = MagicMock()
        mock_instance.version.return_value = -1  # Empty
        mock_dt.return_value = mock_instance

        tbl = reader.read_table("empty_table")
        assert tbl.num_rows == 0


def test_delta_reader_missing_table():
    mock_auth = MagicMock(spec=OneLakeAuthManager)
    mock_auth.get_storage_options.return_value = {"bearer_token": "mock"}
    reader = OneLakeDeltaReader(auth_manager=mock_auth, config=LakehouseReaderConfig())

    from deltalake.exceptions import TableNotFoundError
    with patch("lakehouse.delta_reader.DeltaTable", side_effect=TableNotFoundError("Missing")):
        meta = reader.get_table_metadata("non_existent")
        assert meta["accessible"] is False
        assert "does not exist" in meta["error"]


# -----------------------------------------------------------------------------
# 3. Inventory Snapshot Filtering & Deduplication
# -----------------------------------------------------------------------------
def test_inventory_latest_snapshot_selection():
    mock_reader = MagicMock(spec=OneLakeDeltaReader)
    # Return two historical snapshots: 2026-11-01 (old) and 2026-11-05 (latest)
    raw_records = [
        {
            "resource_id": "/sub/rg/vm1",
            "name": "vm1",
            "provider": "azure",
            "resource_type": "Microsoft.Compute/virtualMachines",
            "location": "eastus",
            "power_state": "Stopped",
            "snapshot_timestamp": "2026-11-01T10:00:00Z",
            "subscription_id": "sub-1",
            "connection_id": "conn-1",
        },
        {
            "resource_id": "/sub/rg/vm1",
            "name": "vm1",
            "provider": "azure",
            "resource_type": "Microsoft.Compute/virtualMachines",
            "location": "eastus",
            "power_state": "Running",
            "snapshot_timestamp": "2026-11-05T12:00:00Z",  # Latest snapshot
            "subscription_id": "sub-1",
            "connection_id": "conn-1",
        },
        {
            "resource_id": "/sub/rg/db1",
            "name": "db1",
            "provider": "azure",
            "resource_type": "Microsoft.DBforPostgreSQL/flexibleServers",
            "location": "eastus",
            "power_state": "Ready",
            "snapshot_timestamp": "2026-11-05T12:00:00Z",  # Latest snapshot
            "subscription_id": "sub-1",
            "connection_id": "conn-1",
        },
    ]
    mock_reader.read_records_as_dicts.return_value = raw_records

    repo = AnalyticalRepository(reader=mock_reader)
    env = repo.get_inventory_summary(connection_id="conn-1")

    assert env.status == "success"
    summary = env.data
    assert summary is not None
    # Must only contain the 2 resources from the latest snapshot, not 3!
    assert summary.total_resources == 2
    assert summary.snapshot_timestamp == "2026-11-05T12:00:00Z"
    assert summary.by_resource_type["Microsoft.Compute/virtualMachines"] == 1
    assert summary.by_resource_type["Microsoft.DBforPostgreSQL/flexibleServers"] == 1
    assert summary.by_power_state["Running"] == 1
    assert summary.by_power_state["Ready"] == 1
    # Old snapshot's power state must NOT be counted
    assert "Stopped" not in summary.by_power_state


# -----------------------------------------------------------------------------
# 4. Cost Currency Separation
# -----------------------------------------------------------------------------
def test_cost_analytics_currency_isolation():
    mock_reader = MagicMock(spec=OneLakeDeltaReader)
    raw_costs = [
        {
            "usage_date": "2026-10-01",
            "service_name": "Virtual Machines",
            "cost_in_billing_currency": Decimal("100.00"),
            "currency": "USD",
            "charge_type": "Usage",
            "connection_id": "conn-1",
        },
        {
            "usage_date": "2026-10-01",
            "service_name": "Database",
            "cost_in_billing_currency": Decimal("5000.00"),
            "currency": "INR",  # Different currency!
            "charge_type": "Usage",
            "connection_id": "conn-1",
        },
    ]
    mock_reader.read_records_as_dicts.return_value = raw_costs

    repo = AnalyticalRepository(reader=mock_reader)
    env = repo.get_cost_analytics(connection_id="conn-1")

    assert env.status == "success"
    analytics = env.data
    assert analytics is not None

    # Must contain 2 separate currency totals, NOT a combined 5100 sum!
    curr_totals = {c.currency: c.total_cost for c in analytics.total_by_currency}
    assert curr_totals["USD"] == Decimal("100.00")
    assert curr_totals["INR"] == Decimal("5000.00")
    assert len(analytics.total_by_currency) == 2


# -----------------------------------------------------------------------------
# 5. Metrics Deduplication Across Time Windows
# -----------------------------------------------------------------------------
def test_metrics_hourly_deduplication():
    mock_reader = MagicMock(spec=OneLakeDeltaReader)
    # Simulate two overlapping syncs querying the same hour (13:52 and 13:53)
    raw_metrics = [
        {
            "resource_id": "/sub/rg/vm1",
            "metric_name": "Percentage CPU",
            "timestamp": "2026-10-29 13:52:00.000000Z",
            "average": 10.0,
            "maximum": 20.0,
            "minimum": 5.0,
            "unit": "Percent",
            "ingestion_timestamp": "2026-11-05 13:52:55Z",  # First sync
        },
        {
            "resource_id": "/sub/rg/vm1",
            "metric_name": "Percentage CPU",
            "timestamp": "2026-10-29 13:53:00.000000Z",
            "average": 12.0,
            "maximum": 25.0,
            "minimum": 6.0,
            "unit": "Percent",
            "ingestion_timestamp": "2026-11-05 13:54:31Z",  # Later sync (preferred)
        },
    ]
    mock_reader.read_records_as_dicts.return_value = raw_metrics

    repo = AnalyticalRepository(reader=mock_reader)
    env = repo.get_metrics_summary(connection_id="conn-1", resource_id="/sub/rg/vm1")

    assert env.status == "success"
    summary = env.data
    assert summary is not None
    # 2 raw rows evaluated, but exactly 1 distinct hourly bucket returned!
    assert summary.total_points_evaluated == 2
    assert summary.distinct_time_buckets == 1
    series = summary.series[0]
    assert series.points_count == 1
    # Latest ingestion values should win
    assert series.average_utilization == 12.0
    assert series.peak_utilization == 25.0


# -----------------------------------------------------------------------------
# 6. Token Telemetry Empty Table Handling
# -----------------------------------------------------------------------------
def test_token_telemetry_honest_empty():
    mock_reader = MagicMock(spec=OneLakeDeltaReader)
    mock_reader.read_records_as_dicts.return_value = []

    repo = AnalyticalRepository(reader=mock_reader)
    env = repo.get_token_telemetry_summary(connection_id="conn-1")

    assert env.status == "success"
    token_sum = env.data
    assert token_sum is not None
    assert token_sum.has_data is False
    assert token_sum.total_events == 0
    assert "No GenAI token telemetry" in token_sum.message


# -----------------------------------------------------------------------------
# 7. Lakehouse Health Checker & Diagnostics
# -----------------------------------------------------------------------------
def test_health_checker_all_ready():
    mock_auth = MagicMock()
    mock_auth.get_token.return_value = ("token", "managed_identity")
    mock_reader = MagicMock()
    mock_reader.get_table_metadata.return_value = {
        "accessible": True,
        "version": 2,
        "file_count": 2,
    }

    checker = LakehouseHealthChecker(reader=mock_reader, auth_manager=mock_auth)
    res = checker.check_health()
    assert res.overall_status == "READY"
    assert res.auth_status == "AUTHENTICATED"
    assert len(res.tables) == 5
    assert all(t.accessible for t in res.tables.values())


def test_diagnostics_metrics_quality():
    mock_reader = MagicMock()
    # Create pyarrow table matching resource_metrics
    arrow_tbl = pa.Table.from_arrays(
        [
            pa.array(["m1", "m2"]),
            pa.array(["/res/vm1", "/res/vm1"]),
            pa.array(["cpu", "cpu"]),
            pa.array(["2026-10-29 13:52:00.000000Z", "2026-10-29 13:53:00.000000Z"]),
            pa.array([10.0, 10.0]),
            pa.array([20.0, 20.0]),
            pa.array([5.0, 5.0]),
            pa.array(["Percent", "Percent"]),
            pa.array(["2026-11-05 13:52:55Z", "2026-11-05 13:54:31Z"]),
        ],
        names=[
            "metric_record_id",
            "resource_id",
            "metric_name",
            "timestamp",
            "average",
            "maximum",
            "minimum",
            "unit",
            "ingestion_timestamp",
        ],
    )
    mock_reader.read_table.return_value = arrow_tbl

    diag = LakehouseDiagnostics(reader=mock_reader)
    report = diag.diagnose_metrics_quality()

    assert report["status"] == "success"
    assert report["total_rows"] == 2
    assert report["distinct_metric_record_ids"] == 2
    assert report["exact_duplicate_ids_count"] == 0
    assert report["distinct_hourly_buckets"] == 1
    assert report["overlapping_hourly_buckets_count"] == 1
    assert report["temporal_duplicate_percentage"] == 50.0

