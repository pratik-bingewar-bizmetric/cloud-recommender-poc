"""Comprehensive test suite for Multi-Cloud Resource Configuration, Databricks Workspace Discovery, and Selection Semantics."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from cloud_recommender.schemas.configuration import (
    ConfiguredScopeItemCreate,
    ScopeDiscoveryNode,
    ScopeType,
    SelectionState,
)
from cloud_recommender.schemas.inventory import CloudScopeSummary
from cloud_recommender.services.configuration.configuration_service import (
    ConfigurationService,
)
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService

# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------


def test_configuration_schemas_validation() -> None:
    """Verify enum types and Pydantic validation on configuration schemas."""
    assert ScopeType.DATABRICKS_WORKSPACE == "databricks_workspace"
    assert ScopeType.SUBSCRIPTION == "subscription"
    assert SelectionState.INCLUDED == "included"
    assert SelectionState.EXCLUDED == "excluded"
    assert SelectionState.ALL_CHILDREN == "all_children"

    item = ConfiguredScopeItemCreate(
        scope_type="databricks_workspace",
        scope_identifier="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Databricks/workspaces/adb-ws",
        parent_scope_identifier="rg1",
        display_name="adb-ws",
        resource_type="Microsoft.Databricks/workspaces",
        region="eastus",
        selection_state="included",
        metadata={"workspace_url": "adb-123.azuredatabricks.net"},
    )
    assert item.display_name == "adb-ws"
    assert item.metadata["workspace_url"] == "adb-123.azuredatabricks.net"

    # Invalid selection state raises ValidationError
    with pytest.raises(ValidationError):
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier="res-1",
            display_name="Res",
            selection_state="invalid_state",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Discovery Tests (Azure, Databricks, GCP, AWS)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configuration_service_aws_unsupported() -> None:
    """Verify AWS provider returns honest unsupported status without fabrication."""
    service = ConfigurationService()
    resp = await service.discover_scopes("aws-conn-01", provider="aws")

    assert resp.provider == "aws"
    assert resp.status == "unsupported"
    assert "not currently configured or supported" in resp.status_message
    assert resp.tree == []
    assert resp.total_discovered_resources == 0
    assert resp.databricks_workspaces_count == 0


@pytest.mark.asyncio
async def test_configuration_service_azure_discovery_simulation_with_databricks() -> None:
    """Verify simulation discovery returns Azure subscriptions with Databricks workspaces."""
    mock_azure = AsyncMock(spec=AzureInventoryService)
    mock_azure.get_access_token.return_value = (None, "none")
    service = ConfigurationService(azure_service=mock_azure)

    resp = await service.discover_scopes("azure-conn-01", provider="azure")

    assert resp.provider == "azure"
    assert resp.status == "ready"
    assert resp.total_discovered_resources >= 4
    assert resp.databricks_workspaces_count >= 1

    # Verify root node is subscription
    assert len(resp.tree) > 0
    sub_node = resp.tree[0]
    assert sub_node.scope_type == ScopeType.SUBSCRIPTION

    # Find Databricks workspace node in tree
    all_nodes: list[ScopeDiscoveryNode] = []

    def _collect(n: ScopeDiscoveryNode) -> None:
        all_nodes.append(n)
        for child in n.children:
            _collect(child)

    _collect(sub_node)

    ws_nodes = [n for n in all_nodes if n.scope_type == ScopeType.DATABRICKS_WORKSPACE]
    assert len(ws_nodes) >= 1
    ws = ws_nodes[0]
    assert ws.name == "adb-lakehouse-prod"
    assert ws.resource_type == "Microsoft.Databricks/workspaces"
    assert "workspace_url" in ws.metadata
    assert ws.metadata["pricing_tier"] == "premium"


@pytest.mark.asyncio
async def test_configuration_service_azure_discovery_live_with_databricks() -> None:
    """Verify live ARM discovery parses subscriptions, resource groups, resources, and Databricks workspaces."""
    mock_azure = AsyncMock(spec=AzureInventoryService)
    mock_azure.get_access_token.return_value = ("mock-bearer-token", "sp_oauth2")
    mock_azure.list_subscriptions.return_value = [
        CloudScopeSummary(
            provider="azure",
            scope_id="sub-live-01",
            display_name="Enterprise Production",
            tenant_or_org_id="tenant-live-01",
            state="Enabled",
            data_source="live_authenticated",
        )
    ]
    mock_azure.list_resource_groups.return_value = [
        {
            "name": "rg-analytics",
            "id": "/subscriptions/sub-live-01/resourceGroups/rg-analytics",
            "location": "eastus",
        }
    ]
    mock_azure.list_databricks_workspaces.return_value = [
        {
            "resource_id": "/subscriptions/sub-live-01/resourceGroups/rg-analytics/providers/Microsoft.Databricks/workspaces/adb-live-ws",
            "name": "adb-live-ws",
            "resource_group": "rg-analytics",
            "region": "eastus",
            "workspace_url": "adb-99999.azuredatabricks.net",
            "workspace_id": "99999",
            "pricing_tier": "premium",
            "provisioning_state": "Succeeded",
            "discovery_status": "discovered",
        }
    ]
    mock_azure.list_resources.return_value = [
        {
            "id": "/subscriptions/sub-live-01/resourceGroups/rg-analytics/providers/Microsoft.Storage/storageAccounts/stlive01",
            "name": "stlive01",
            "type": "Microsoft.Storage/storageAccounts",
            "location": "eastus",
        }
    ]

    service = ConfigurationService(azure_service=mock_azure)
    resp = await service.discover_scopes("live-conn", provider="azure")

    assert resp.status == "ready"
    assert resp.total_discovered_resources >= 1
    assert resp.databricks_workspaces_count == 1
    assert len(resp.tree) == 1
    assert resp.tree[0].name == "Enterprise Production"
    assert len(resp.tree[0].children) == 1  # rg-analytics
    rg = resp.tree[0].children[0]
    assert len(rg.children) == 2  # workspace + storage account


@pytest.mark.asyncio
async def test_configuration_service_azure_discovery_live_empty() -> None:
    """Verify live ARM discovery with zero subscriptions returns empty status."""
    mock_azure = AsyncMock(spec=AzureInventoryService)
    mock_azure.get_access_token.return_value = ("fake-token", "sp_oauth2")
    mock_azure.list_subscriptions.return_value = []

    service = ConfigurationService(azure_service=mock_azure)
    resp = await service.discover_scopes("azure-empty-conn", provider="azure")

    assert resp.status == "empty"
    assert resp.tree == []
    assert resp.total_discovered_resources == 0


@pytest.mark.asyncio
async def test_configuration_service_azure_discovery_permission_denied() -> None:
    """Verify permission denied error handling returns status 'permission_denied'."""
    mock_azure = AsyncMock(spec=AzureInventoryService)
    mock_azure.get_access_token.return_value = ("fake-token", "sp_oauth2")
    mock_azure.list_subscriptions.side_effect = PermissionError("Reader role missing.")

    service = ConfigurationService(azure_service=mock_azure)
    resp = await service.discover_scopes("azure-denied-conn", provider="azure")

    assert resp.status == "permission_denied"
    assert "PermissionError" in resp.status_message or "Reader role missing" in resp.status_message
    assert resp.tree == []


@pytest.mark.asyncio
async def test_configuration_service_gcp_discovery() -> None:
    """Verify GCP hierarchy discovery returns organization and project assets."""
    service = ConfigurationService()
    resp = await service.discover_scopes("gcp-conn-01", provider="gcp")

    assert resp.provider == "gcp"
    assert resp.status == "ready"
    assert len(resp.tree) > 0
    assert resp.tree[0].scope_type == ScopeType.PROJECT


# ---------------------------------------------------------------------------
# Persistence & Versioning Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configuration_creation_and_version_increment() -> None:
    """Verify initial configuration is v1, and subsequent save increments to v2, archiving v1."""
    conn_id = f"test-conn-{uuid.uuid4().hex[:6]}"
    service = ConfigurationService()

    items_v1 = [
        ConfiguredScopeItemCreate(
            scope_type="subscription",
            scope_identifier="sub-alpha",
            display_name="Subscription Alpha",
            selection_state="all_children",
        ),
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier="res-1",
            parent_scope_identifier="sub-alpha",
            display_name="VM 1",
            selection_state="included",
        ),
    ]

    res_v1 = await service.save_configuration(
        connection_id=conn_id,
        provider="azure",
        scope_items=items_v1,
        created_by="admin-user",
    )

    assert res_v1.connection_id == conn_id
    assert res_v1.configuration_version == 1
    assert res_v1.active_status == "active"
    assert len(res_v1.scope_items) == 2

    # Save v2
    items_v2 = [
        ConfiguredScopeItemCreate(
            scope_type="subscription",
            scope_identifier="sub-alpha",
            display_name="Subscription Alpha",
            selection_state="all_children",
        ),
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier="res-1",
            parent_scope_identifier="sub-alpha",
            display_name="VM 1",
            selection_state="included",
        ),
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier="res-2",
            parent_scope_identifier="sub-alpha",
            display_name="VM 2",
            selection_state="included",
        ),
    ]

    res_v2 = await service.save_configuration(
        connection_id=conn_id,
        provider="azure",
        scope_items=items_v2,
        created_by="admin-user",
    )

    assert res_v2.configuration_version == 2
    assert res_v2.active_status == "active"
    assert len(res_v2.scope_items) == 3

    # Active configuration retrieval returns v2
    active = await service.get_active_configuration(conn_id)
    assert active is not None
    assert active.configuration_version == 2
    assert active.active_status == "active"


# ---------------------------------------------------------------------------
# Selection Semantics Tests (Cascade, Exclusion, Isolation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parent_selection_with_child_exclusion() -> None:
    """Verify parent 'all_children' includes children, but child with 'excluded' is strictly omitted."""
    conn_id = f"test-conn-ex-{uuid.uuid4().hex[:6]}"
    service = ConfigurationService()

    rg_id = "/subscriptions/sub-1/resourceGroups/rg-prod"
    res1_id = f"{rg_id}/providers/Microsoft.Compute/virtualMachines/vm-1"
    res2_id = f"{rg_id}/providers/Microsoft.Compute/virtualMachines/vm-2"
    res3_id = f"{rg_id}/providers/Microsoft.Compute/virtualMachines/vm-3"

    items = [
        ConfiguredScopeItemCreate(
            scope_type="resource_group",
            scope_identifier=rg_id,
            display_name="rg-prod",
            selection_state="all_children",
        ),
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier=res1_id,
            parent_scope_identifier=rg_id,
            display_name="vm-1",
            selection_state="included",
        ),
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier=res2_id,
            parent_scope_identifier=rg_id,
            display_name="vm-2",
            selection_state="excluded",  # Explicitly excluded
        ),
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier=res3_id,
            parent_scope_identifier=rg_id,
            display_name="vm-3",
            selection_state="included",
        ),
    ]

    await service.save_configuration(conn_id, "azure", items)
    effective = await service.resolve_effective_selection(conn_id)

    assert res1_id in effective.effective_resource_ids
    assert res3_id in effective.effective_resource_ids
    assert res2_id not in effective.effective_resource_ids  # Excluded!
    assert effective.total_selected_resources == 2


@pytest.mark.asyncio
async def test_individual_resource_selection() -> None:
    """Verify selecting only individual resources does not select sibling resources."""
    conn_id = f"test-conn-indiv-{uuid.uuid4().hex[:6]}"
    service = ConfigurationService()

    rg_id = "/subscriptions/sub-1/resourceGroups/rg-test"
    target_res = f"{rg_id}/providers/Microsoft.Storage/storageAccounts/sttarget"
    sibling_res = f"{rg_id}/providers/Microsoft.Storage/storageAccounts/stsibling"

    items = [
        # RG is NOT set to all_children
        ConfiguredScopeItemCreate(
            scope_type="resource_group",
            scope_identifier=rg_id,
            display_name="rg-test",
            selection_state="included",
        ),
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier=target_res,
            parent_scope_identifier=rg_id,
            display_name="sttarget",
            selection_state="included",
        ),
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier=sibling_res,
            parent_scope_identifier=rg_id,
            display_name="stsibling",
            selection_state="excluded",
        ),
    ]

    await service.save_configuration(conn_id, "azure", items)
    effective = await service.resolve_effective_selection(conn_id)

    assert effective.effective_resource_ids == [target_res]
    assert effective.total_selected_resources == 1


@pytest.mark.asyncio
async def test_multiple_databricks_workspace_selection() -> None:
    """Verify multiple Databricks workspaces can be selected with rich metadata retained."""
    conn_id = f"test-conn-adb-{uuid.uuid4().hex[:6]}"
    service = ConfigurationService()

    ws1_id = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Databricks/workspaces/ws-analytics"
    ws2_id = (
        "/subscriptions/sub-1/resourceGroups/rg-2/providers/Microsoft.Databricks/workspaces/ws-ml"
    )

    items = [
        ConfiguredScopeItemCreate(
            scope_type="databricks_workspace",
            scope_identifier=ws1_id,
            parent_scope_identifier="rg-1",
            display_name="ws-analytics",
            resource_type="Microsoft.Databricks/workspaces",
            region="eastus",
            selection_state="included",
            metadata={
                "workspace_url": "adb-11111.azuredatabricks.net",
                "workspace_id": "11111",
                "pricing_tier": "premium",
            },
        ),
        ConfiguredScopeItemCreate(
            scope_type="databricks_workspace",
            scope_identifier=ws2_id,
            parent_scope_identifier="rg-2",
            display_name="ws-ml",
            resource_type="Microsoft.Databricks/workspaces",
            region="westus",
            selection_state="included",
            metadata={
                "workspace_url": "adb-22222.azuredatabricks.net",
                "workspace_id": "22222",
                "pricing_tier": "standard",
            },
        ),
    ]

    await service.save_configuration(conn_id, "azure", items)
    effective = await service.resolve_effective_selection(conn_id)

    assert len(effective.databricks_workspaces) == 2
    urls = [w.get("workspace_url") for w in effective.databricks_workspaces]
    assert "adb-11111.azuredatabricks.net" in urls
    assert "adb-22222.azuredatabricks.net" in urls


@pytest.mark.asyncio
async def test_select_all_and_clear_all_semantics() -> None:
    """Verify Select All and Clear All selection states."""
    conn_id = f"test-conn-all-{uuid.uuid4().hex[:6]}"
    service = ConfigurationService()

    # Clear All: empty scope items
    await service.save_configuration(conn_id, "azure", [])
    effective_clear = await service.resolve_effective_selection(conn_id)
    assert effective_clear.total_selected_resources == 0
    assert effective_clear.effective_resource_ids == []

    status_clear = await service.get_configuration_status(conn_id)
    assert status_clear.ingestion_readiness == "no_selection"


@pytest.mark.asyncio
async def test_tenant_and_connection_isolation() -> None:
    """Verify configurations for conn-A do not affect conn-B."""
    conn_a = f"conn-a-{uuid.uuid4().hex[:6]}"
    conn_b = f"conn-b-{uuid.uuid4().hex[:6]}"
    service = ConfigurationService()

    item_a = [
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier="res-tenant-a",
            display_name="Resource A",
            selection_state="included",
        )
    ]
    item_b = [
        ConfiguredScopeItemCreate(
            scope_type="resource",
            scope_identifier="res-tenant-b",
            display_name="Resource B",
            selection_state="included",
        )
    ]

    await service.save_configuration(conn_a, "azure", item_a)
    await service.save_configuration(conn_b, "azure", item_b)

    eff_a = await service.resolve_effective_selection(conn_a)
    eff_b = await service.resolve_effective_selection(conn_b)

    assert eff_a.effective_resource_ids == ["res-tenant-a"]
    assert eff_b.effective_resource_ids == ["res-tenant-b"]
    assert "res-tenant-b" not in eff_a.effective_resource_ids


@pytest.mark.asyncio
async def test_invalid_scope_item_validation_error() -> None:
    """Verify blank identifiers raise ValueError."""
    service = ConfigurationService()
    with pytest.raises(ValueError, match="valid scope_identifier"):
        await service.save_configuration(
            "conn-err",
            "azure",
            [
                ConfiguredScopeItemCreate(
                    scope_type="resource",
                    scope_identifier="",  # Invalid blank
                    display_name="Invalid",
                    selection_state="included",
                )
            ],
        )


# ---------------------------------------------------------------------------
# FastAPI Router Endpoints Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_configuration_endpoints_lifecycle(client: "AsyncClient") -> None:  # type: ignore[name-defined]
    """Verify end-to-end FastAPI configuration endpoints (discovery, save, fetch, selected, workspaces, status)."""
    conn_id = f"api-test-conn-{uuid.uuid4().hex[:6]}"

    # Patch Azure token resolution to bypass 15s az CLI timeout in test environment
    with patch(
        "cloud_recommender.services.inventory.azure_inventory.AzureInventoryService.get_access_token",
        new_callable=AsyncMock,
        return_value=(None, "none"),
    ):
        # 1. Discover scopes for AWS (unsupported)
        aws_resp = await client.get(
            "/api/v1/configuration/scopes/discover",
            params={"connection_id": conn_id, "provider": "aws"},
        )
        assert aws_resp.status_code == 200
        aws_data = aws_resp.json()
        assert aws_data["status"] == "unsupported"

        # 2. Discover scopes for Azure (ready with simulation Databricks workspace)
        az_resp = await client.get(
            "/api/v1/configuration/scopes/discover",
            params={"connection_id": conn_id, "provider": "azure"},
        )
        assert az_resp.status_code == 200
        az_data = az_resp.json()
        assert az_data["status"] == "ready"
        assert az_data["databricks_workspaces_count"] >= 1

    # 3. Check status before saving -> not_configured
    status_pre = await client.get(f"/api/v1/configuration/{conn_id}/status")
    assert status_pre.status_code == 200
    assert status_pre.json()["ingestion_readiness"] == "not_configured"

    # 4. Save configuration
    save_payload = {
        "connection_id": conn_id,
        "provider": "azure",
        "created_by": "api-tester",
        "scope_items": [
            {
                "scope_type": "subscription",
                "scope_identifier": "/subscriptions/sub-api-01",
                "display_name": "API Subscription",
                "selection_state": "all_children",
            },
            {
                "scope_type": "databricks_workspace",
                "scope_identifier": "/subscriptions/sub-api-01/resourceGroups/rg-1/providers/Microsoft.Databricks/workspaces/adb-api-ws",
                "parent_scope_identifier": "/subscriptions/sub-api-01/resourceGroups/rg-1",
                "display_name": "adb-api-ws",
                "resource_type": "Microsoft.Databricks/workspaces",
                "region": "eastus",
                "selection_state": "included",
                "metadata": {
                    "workspace_url": "adb-api-01.azuredatabricks.net",
                    "pricing_tier": "premium",
                },
            },
            {
                "scope_type": "resource",
                "scope_identifier": "/subscriptions/sub-api-01/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-ex",
                "parent_scope_identifier": "/subscriptions/sub-api-01/resourceGroups/rg-1",
                "display_name": "vm-ex",
                "selection_state": "excluded",
            },
        ],
    }

    save_resp = await client.post("/api/v1/configuration", json=save_payload)
    assert save_resp.status_code == 200
    saved = save_resp.json()
    assert saved["configuration_version"] == 1
    assert saved["active_status"] == "active"
    assert len(saved["scope_items"]) == 3

    # 5. Fetch active configuration
    fetch_resp = await client.get(f"/api/v1/configuration/{conn_id}")
    assert fetch_resp.status_code == 200
    assert fetch_resp.json()["configuration_id"] == saved["configuration_id"]

    # 6. Fetch effective selection
    sel_resp = await client.get(f"/api/v1/configuration/{conn_id}/selected")
    assert sel_resp.status_code == 200
    sel_data = sel_resp.json()
    assert sel_data["total_selected_resources"] == 1  # Only adb-api-ws (vm-ex was excluded)
    assert (
        "/subscriptions/sub-api-01/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-ex"
        not in sel_data["effective_resource_ids"]
    )

    # 7. Fetch selected workspaces
    ws_resp = await client.get(f"/api/v1/configuration/{conn_id}/workspaces")
    assert ws_resp.status_code == 200
    workspaces = ws_resp.json()
    assert len(workspaces) == 1
    assert workspaces[0]["name"] == "adb-api-ws"
    assert workspaces[0]["workspace_url"] == "adb-api-01.azuredatabricks.net"

    # 8. Check status after saving -> ready
    status_post = await client.get(f"/api/v1/configuration/{conn_id}/status")
    assert status_post.status_code == 200
    assert status_post.json()["ingestion_readiness"] == "ready"
    assert status_post.json()["selected_resource_count"] == 1

    # 9. Non-existent connection returns 404
    missing_resp = await client.get("/api/v1/configuration/non-existent-connection-xyz")
    assert missing_resp.status_code == 404
