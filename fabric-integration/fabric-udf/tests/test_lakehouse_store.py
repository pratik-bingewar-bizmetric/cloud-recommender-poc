"""Unit tests for Microsoft Fabric Lakehouse Persistent Storage Layer."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from schemas.models import (
    CloudConnection,
    DiscoveredResource,
    TokenUsageRecord,
)
from services.lakehouse_store import FabricLakehouseStore


@pytest.fixture
def temp_store(tmp_path: Path) -> FabricLakehouseStore:
    db_file = tmp_path / "test_lakehouse.db"
    return FabricLakehouseStore(db_path=db_file)


def test_connection_persistence_lifecycle(temp_store: FabricLakehouseStore) -> None:
    conn = CloudConnection(
        id="azure-test-01",
        name="Production Core",
        provider="azure",
        scope_id="00000000-1111-2222-3333-444444444444",
        tenant_or_org_id="tenant-1234",
        auth_method="service_principal_oauth2",
        status="connected",
        is_live=True,
    )

    # 1. Save connection with secret
    temp_store.save_connection(conn, secret="super-secret-key-123")

    # 2. Retrieve connection
    retrieved = temp_store.get_connection("azure-test-01")
    assert retrieved is not None
    assert retrieved.name == "Production Core"
    assert retrieved.scope_id == "00000000-1111-2222-3333-444444444444"
    assert retrieved.status == "connected"
    assert retrieved.is_live is True

    # 3. Retrieve secret
    secret = temp_store.get_connection_secret("azure-test-01")
    assert secret == "super-secret-key-123"

    # 4. List connections
    all_conns = temp_store.list_connections()
    assert len(all_conns) == 1
    assert all_conns[0].id == "azure-test-01"

    # 5. Delete connection
    deleted = temp_store.delete_connection("azure-test-01")
    assert deleted is True
    assert temp_store.get_connection("azure-test-01") is None
    assert len(temp_store.list_connections()) == 0


def test_inventory_snapshot_persistence(temp_store: FabricLakehouseStore) -> None:
    # First save parent connection
    conn = CloudConnection(
        id="azure-inv-01",
        name="Inventory Test Scope",
        provider="azure",
        scope_id="sub-123",
        auth_method="service_principal",
    )
    temp_store.save_connection(conn)

    resources = [
        DiscoveredResource(
            resource_id="/subscriptions/sub-123/resourceGroups/rg-1/providers/Microsoft.Compute/disks/disk-unattached",
            name="disk-unattached",
            resource_type="Microsoft.Compute/disks",
            resource_group="rg-1",
            location="northcentralus",
            sku_name="StandardSSD_LRS",
            tags={"diskState": "Unattached"},
            power_state="Unattached",
            monthly_cost_usd=Decimal("19.71"),
        ),
        DiscoveredResource(
            resource_id="/subscriptions/sub-123/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-prod-01",
            name="vm-prod-01",
            resource_type="Microsoft.Compute/virtualMachines",
            resource_group="rg-1",
            location="northcentralus",
            sku_name="Standard_D4s_v5",
            power_state="running",
            monthly_cost_usd=Decimal("140.16"),
        ),
    ]

    temp_store.save_inventory("azure-inv-01", resources)

    retrieved = temp_store.get_inventory("azure-inv-01")
    assert len(retrieved) == 2
    disk = next(r for r in retrieved if r.name == "disk-unattached")
    assert disk.monthly_cost_usd == Decimal("19.71")
    assert disk.power_state == "Unattached"

    filtered = temp_store.get_inventory(
        "azure-inv-01", resource_type_filter="virtualMachines"
    )
    assert len(filtered) == 1
    assert filtered[0].name == "vm-prod-01"


def test_token_telemetry_persistence(temp_store: FabricLakehouseStore) -> None:
    conn = CloudConnection(
        id="azure-token-01",
        name="Token Scope",
        provider="azure",
        scope_id="sub-ai-1",
        auth_method="service_principal",
    )
    temp_store.save_connection(conn)

    record1 = TokenUsageRecord(
        event_id="evt-1",
        connection_id="azure-token-01",
        timestamp=datetime.now(UTC),
        model_name="gpt-4o",
        prompt_tokens=1000,
        completion_tokens=200,
        total_tokens=1200,
        latency_ms=450,
        estimated_cost_usd=Decimal("0.0045"),
        source="direct_inference_intercept",
    )
    temp_store.append_token_telemetry(record1)

    records = temp_store.get_token_telemetry("azure-token-01")
    assert len(records) == 1
    assert records[0].model_name == "gpt-4o"
    assert records[0].prompt_tokens == 1000
    assert records[0].completion_tokens == 200
    assert records[0].estimated_cost_usd == Decimal("0.0045")
