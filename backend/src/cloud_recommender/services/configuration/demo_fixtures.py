"""Labelled DEMO fixtures for configuration scope discovery.

Isolated from the live discovery code on purpose: nothing here is reachable unless
``Settings.allow_demo_fixtures`` is explicitly enabled (default ``False``; the tests opt in).
The identifiers below are fabricated and must never be shown as real tenant data.
"""

from datetime import UTC, datetime

from cloud_recommender.schemas.configuration import (
    ScopeDiscoveryNode,
    ScopeDiscoveryResponse,
    ScopeType,
)


def azure_demo_scope_discovery(connection_id: str) -> ScopeDiscoveryResponse:
    """Return the fabricated Azure topology used only for explicit demos and tests."""
    tree: list[ScopeDiscoveryNode] = []
    total_resources = 0
    databricks_workspaces_count = 0
    sub_id = "f718c261-ab85-49fd-907e-99c022cc2aeb"
    tenant_id = "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41"

    # Resource Group 1: Analytics & Databricks
    rg1_id = f"/subscriptions/{sub_id}/resourceGroups/rg-analytics-databricks"
    ws1_id = f"{rg1_id}/providers/Microsoft.Databricks/workspaces/adb-lakehouse-prod"
    ws1_node = ScopeDiscoveryNode(
        id=ws1_id,
        name="adb-lakehouse-prod",
        scope_type=ScopeType.DATABRICKS_WORKSPACE,
        scope_identifier=ws1_id,
        parent_scope_identifier=rg1_id,
        resource_type="Microsoft.Databricks/workspaces",
        region="eastus",
        is_leaf=True,
        metadata={
            "workspace_url": "adb-7840192837.14.azuredatabricks.net",
            "workspace_id": "7840192837148901",
            "pricing_tier": "premium",
            "managed_resource_group_id": f"/subscriptions/{sub_id}/resourceGroups/rg-adb-managed-01",
            "provisioning_state": "Succeeded",
            "discovery_status": "discovered",
        },
    )
    sa1_id = f"{rg1_id}/providers/Microsoft.Storage/storageAccounts/stlakehouseprod01"
    sa1_node = ScopeDiscoveryNode(
        id=sa1_id,
        name="stlakehouseprod01",
        scope_type=ScopeType.RESOURCE,
        scope_identifier=sa1_id,
        parent_scope_identifier=rg1_id,
        resource_type="Microsoft.Storage/storageAccounts",
        region="eastus",
        is_leaf=True,
        metadata={"sku": "Standard_GRS", "kind": "StorageV2"},
    )
    rg1_node = ScopeDiscoveryNode(
        id=rg1_id,
        name="rg-analytics-databricks",
        scope_type=ScopeType.RESOURCE_GROUP,
        scope_identifier=rg1_id,
        parent_scope_identifier=sub_id,
        region="eastus",
        is_leaf=False,
        children=[ws1_node, sa1_node],
    )

    # Resource Group 2: Core Compute & Database
    rg2_id = f"/subscriptions/{sub_id}/resourceGroups/rg-finops-core"
    vm1_id = f"{rg2_id}/providers/Microsoft.Compute/virtualMachines/vm-app-server-01"
    vm1_node = ScopeDiscoveryNode(
        id=vm1_id,
        name="vm-app-server-01",
        scope_type=ScopeType.RESOURCE,
        scope_identifier=vm1_id,
        parent_scope_identifier=rg2_id,
        resource_type="Microsoft.Compute/virtualMachines",
        region="eastus",
        is_leaf=True,
        metadata={"vm_size": "Standard_D4s_v5", "os_type": "Linux"},
    )
    db1_id = f"{rg2_id}/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-finops-db"
    db1_node = ScopeDiscoveryNode(
        id=db1_id,
        name="psql-finops-db",
        scope_type=ScopeType.RESOURCE,
        scope_identifier=db1_id,
        parent_scope_identifier=rg2_id,
        resource_type="Microsoft.DBforPostgreSQL/flexibleServers",
        region="eastus",
        is_leaf=True,
        metadata={"sku": "Standard_D4ds_v4", "storage_gb": 128},
    )
    rg2_node = ScopeDiscoveryNode(
        id=rg2_id,
        name="rg-finops-core",
        scope_type=ScopeType.RESOURCE_GROUP,
        scope_identifier=rg2_id,
        parent_scope_identifier=sub_id,
        region="eastus",
        is_leaf=False,
        children=[vm1_node, db1_node],
    )

    sub_node = ScopeDiscoveryNode(
        id=sub_id,
        name="Azure Production Subscription",
        scope_type=ScopeType.SUBSCRIPTION,
        scope_identifier=sub_id,
        parent_scope_identifier=tenant_id,
        is_leaf=False,
        metadata={"tenant_id": tenant_id, "state": "Enabled"},
        children=[rg1_node, rg2_node],
    )
    tree.append(sub_node)
    total_resources = 4
    databricks_workspaces_count = 1

    return ScopeDiscoveryResponse(
        provider="azure",
        connection_id=connection_id,
        tenant_or_org_id=tenant_id,
        status="ready",
        status_message=(
            "DEMO FIXTURE: fabricated Azure topology (ALLOW_DEMO_FIXTURES=true). "
            "This is not data from your tenant."
        ),
        data_source="demo_fixture",
        last_discovered_at=datetime.now(UTC),
        tree=tree,
        total_discovered_resources=total_resources,
        databricks_workspaces_count=databricks_workspaces_count,
    )
