"""Unit tests for OneLake Delta Lake Writer and Deduplication."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pyarrow as pa
from auth import AzureCliAuthManager
from config import SyncAgentConfig
from delta_writer import OneLakeDeltaWriter
from models import CostDetailRecord, ResourceMetricRecord


def test_write_empty_records():
    mock_auth = MagicMock(spec=AzureCliAuthManager)
    writer = OneLakeDeltaWriter(mock_auth, SyncAgentConfig())

    assert writer.write_inventory_snapshot([]) == 0
    assert writer.write_cost_details([]) == (0, 0)
    assert writer.write_metrics([]) == (0, 0)


def test_write_cost_details_deduplication():
    mock_auth = MagicMock(spec=AzureCliAuthManager)
    mock_auth.get_token.return_value = "mock-token"
    writer = OneLakeDeltaWriter(mock_auth, SyncAgentConfig())

    # Pre-existing cost IDs in the Delta table: {"cost-1"}
    mock_existing_table = pa.Table.from_arrays([pa.array(["cost-1"])], names=["cost_record_id"])
    mock_dt = MagicMock()
    mock_dt.version.return_value = 1
    mock_dt.to_pyarrow_table.return_value = mock_existing_table

    # Incoming records: cost-1 (duplicate), cost-2 (new), cost-2 (intra-batch duplicate)
    now = datetime.now(UTC)
    u_date = date(2026, 10, 1)

    r1 = CostDetailRecord(
        cost_record_id="cost-1",
        connection_id="conn-1",
        subscription_id="sub-1",
        billing_year_month="2026-10",
        usage_date=u_date,
        resource_id=None,
        service_name="Compute",
        meter_category="VM",
        meter_name="D2s",
        cost_in_billing_currency=Decimal("5.0000"),
        currency="USD",
        charge_type="Usage",
        source_api="Azure Cost Management Query API",
        ingestion_timestamp=now,
    )
    r2 = CostDetailRecord(
        cost_record_id="cost-2",
        connection_id="conn-1",
        subscription_id="sub-1",
        billing_year_month="2026-10",
        usage_date=u_date,
        resource_id=None,
        service_name="Storage",
        meter_category="Storage",
        meter_name="LRS",
        cost_in_billing_currency=Decimal("2.0000"),
        currency="USD",
        charge_type="Usage",
        source_api="Azure Cost Management Query API",
        ingestion_timestamp=now,
    )
    r3 = CostDetailRecord(
        cost_record_id="cost-2",  # Intra-batch duplicate
        connection_id="conn-1",
        subscription_id="sub-1",
        billing_year_month="2026-10",
        usage_date=u_date,
        resource_id=None,
        service_name="Storage",
        meter_category="Storage",
        meter_name="LRS",
        cost_in_billing_currency=Decimal("2.0000"),
        currency="USD",
        charge_type="Usage",
        source_api="Azure Cost Management Query API",
        ingestion_timestamp=now,
    )

    with (
        patch("delta_writer.DeltaTable", return_value=mock_dt),
        patch("delta_writer.write_deltalake") as mock_write,
    ):
        total_ext, written = writer.write_cost_details([r1, r2, r3])
        assert total_ext == 3
        assert written == 1  # Only r2 written
        assert mock_write.call_count == 1
        written_arrow = mock_write.call_args[0][1]
        assert written_arrow.num_rows == 1
        assert written_arrow.column("cost_record_id")[0].as_py() == "cost-2"


def test_write_metrics_deduplication():
    mock_auth = MagicMock(spec=AzureCliAuthManager)
    mock_auth.get_token.return_value = "mock-token"
    writer = OneLakeDeltaWriter(mock_auth, SyncAgentConfig())

    mock_existing_table = pa.Table.from_arrays(
        [pa.array(["metric-existing"])], names=["metric_record_id"]
    )
    mock_dt = MagicMock()
    mock_dt.version.return_value = 1
    mock_dt.to_pyarrow_table.return_value = mock_existing_table

    now = datetime.now(UTC)
    m1 = ResourceMetricRecord(
        metric_record_id="metric-existing",
        resource_id="res-1",
        subscription_id="sub-1",
        metric_name="cpu",
        timestamp=now,
        average=10.0,
        maximum=20.0,
        minimum=5.0,
        unit="Percent",
        source_api="Azure Monitor Metrics API",
        ingestion_timestamp=now,
    )
    m2 = ResourceMetricRecord(
        metric_record_id="metric-new",
        resource_id="res-1",
        subscription_id="sub-1",
        metric_name="memory",
        timestamp=now,
        average=40.0,
        maximum=50.0,
        minimum=30.0,
        unit="Percent",
        source_api="Azure Monitor Metrics API",
        ingestion_timestamp=now,
    )

    with (
        patch("delta_writer.DeltaTable", return_value=mock_dt),
        patch("delta_writer.write_deltalake") as mock_write,
    ):
        total_ext, written = writer.write_metrics([m1, m2])
        assert total_ext == 2
        assert written == 1
        assert mock_write.call_count == 1
        written_arrow = mock_write.call_args[0][1]
        assert written_arrow.column("metric_record_id")[0].as_py() == "metric-new"
