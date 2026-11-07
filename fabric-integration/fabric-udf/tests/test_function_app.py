"""Integration tests for Microsoft Fabric User Data Functions entrypoint."""

from decimal import Decimal

from function_app import (
    dispatch_udf_function,
    get_cost_waste,
    get_store,
    get_token_economics,
    list_connections,
    record_token_usage,
)
from schemas.models import CloudConnection, DiscoveredResource


def test_dispatch_unknown_function() -> None:
    res = dispatch_udf_function("non_existent_func", {})
    assert res["status"] == "error"
    assert res["error_code"] == "FUNCTION_NOT_FOUND"


def test_list_connections_rpc() -> None:
    res = list_connections()
    assert res["status"] == "success"
    assert isinstance(res["data"], list)


def test_token_economics_rpc_lifecycle() -> None:
    store = get_store()
    store.delete_connection("conn-rpc-test")
    conn = CloudConnection(
        id="conn-rpc-test",
        name="RPC Test Scope",
        provider="azure",
        scope_id="sub-rpc",
        auth_method="service_principal",
    )
    store.save_connection(conn)

    # 1. Record usage via RPC
    rec_res = record_token_usage(
        connectionId="conn-rpc-test",
        modelName="gpt-4o",
        promptTokens=4000,
        completionTokens=1500,
        latencyMs=210,
    )
    assert rec_res["status"] == "success"
    assert rec_res["data"]["total_tokens"] == 5500

    # 2. Get economics summary via RPC
    econ_res = get_token_economics(connectionId="conn-rpc-test", days=30)
    assert econ_res["status"] == "success"
    assert econ_res["data"]["total_tokens"] == 5500
    assert econ_res["data"]["total_prompt_tokens"] == 4000
    assert econ_res["data"]["total_completion_tokens"] == 1500


def test_waste_detection_rpc() -> None:
    store = get_store()
    store.delete_connection("conn-waste-rpc")
    conn = CloudConnection(
        id="conn-waste-rpc",
        name="Waste Test Scope",
        provider="azure",
        scope_id="sub-waste",
        auth_method="service_principal",
    )
    store.save_connection(conn)

    # Seed an unattached disk
    disk = DiscoveredResource(
        resource_id="/subscriptions/sub-waste/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-w1",
        name="disk-w1",
        resource_type="Microsoft.Compute/disks",
        location="northcentralus",
        tags={"diskState": "Unattached"},
        power_state="Unattached",
        monthly_cost_usd=Decimal("19.71"),
    )
    store.save_inventory("conn-waste-rpc", [disk])

    waste_res = get_cost_waste(connectionId="conn-waste-rpc")
    assert waste_res["status"] == "success"
    data = waste_res["data"]
    assert float(data["total_monthly_waste_usd"]) == 19.71
    assert len(data["items"]) == 1
    assert data["items"][0]["waste_category"] == "unattached_disk"


def test_dispatch_rpc_wrapper() -> None:
    res = dispatch_udf_function(
        "list_connections",
        {"provider_filter": "azure"},
    )
    assert res["status"] == "success"
    assert isinstance(res["data"], list)


def test_validate_connection_rpc_unauthenticated() -> None:
    from function_app import validate_connection

    res = validate_connection(
        tenantId="00000000-0000-0000-0000-000000000000",
        clientId="00000000-0000-0000-0000-000000000000",
        clientSecret="dummy-invalid-secret",
        subscriptionId="00000000-0000-0000-0000-000000000000",
    )
    assert res["status"] == "error"
    assert res["error_code"] in ("AUTHENTICATION_FAILED", "AUTHORIZATION_FAILED")


def test_validate_arm_connection_mocked(monkeypatch) -> None:
    import asyncio
    from function_app import AzureRealClient

    client = AzureRealClient()

    # Mock get_access_token
    async def mock_token(*args, **kwargs):
        return "mock-bearer-token", "service_principal_oauth2"

    monkeypatch.setattr(client, "get_access_token", mock_token)

    # Mock _sync_http_request
    def mock_http(method, url, **kwargs):
        if "/subscriptions/sub-123?" in url:
            return 200, {"displayName": "FinOps Test Subscription", "state": "Enabled"}
        if "/resourcegroups?" in url:
            return 200, {"value": [{"name": "rg-test-1"}, {"name": "rg-test-2"}]}
        if "/Microsoft.CostManagement/query" in url:
            return 200, {"properties": {"rows": []}}
        return 200, {}

    import function_app
    monkeypatch.setattr(function_app, "_sync_http_request", mock_http)
    import services.azure_real_client
    monkeypatch.setattr(services.azure_real_client, "_sync_http_request", mock_http)

    async def mock_rg(token, sub_id):
        return [
            DiscoveredResource(
                resource_id="/subscriptions/sub-123/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-1",
                name="vm-1",
                resource_type="Microsoft.Compute/virtualMachines",
                location="northcentralus",
            )
        ]

    monkeypatch.setattr(client, "query_resource_graph", mock_rg)

    result = asyncio.run(
        client.validate_arm_connection(
            tenant_id="tenant-123",
            client_id="client-123",
            client_secret="secret-123",
            subscription_id="sub-123",
        )
    )

    assert result["valid"] is True
    assert result["subscription_name"] == "FinOps Test Subscription"
    assert result["subscription_state"] == "Enabled"
    assert result["roles"]["reader"] is True
    assert result["roles"]["cost_management_reader"] is True
    assert result["roles"]["resource_graph"] is True
    assert result["resource_groups_count"] == 2
    assert result["discovered_resources_count"] == 1


def test_query_cost_management_mocked(monkeypatch) -> None:
    import asyncio
    from function_app import AzureRealClient

    client = AzureRealClient()

    def mock_cm_http(method, url, **kwargs):
        return 200, {
            "properties": {
                "columns": [
                    {"name": "Cost", "type": "Number"},
                    {"name": "ServiceName", "type": "String"},
                    {"name": "ResourceGroupName", "type": "String"},
                    {"name": "Currency", "type": "String"},
                ],
                "rows": [
                    [125.50, "Virtual Machines", "rg-compute", "USD"],
                    [42.25, "Storage", "rg-data", "USD"],
                ],
            }
        }

    import function_app
    monkeypatch.setattr(function_app, "_sync_http_request", mock_cm_http)
    import services.azure_real_client
    monkeypatch.setattr(services.azure_real_client, "_sync_http_request", mock_cm_http)

    res = asyncio.run(client.query_cost_management("dummy-token", "sub-123"))
    assert res["total_cost"] == 167.75
    assert res["currency"] == "USD"
    assert res["service_breakdown"]["Virtual Machines"] == 125.50
    assert res["service_breakdown"]["Storage"] == 42.25
    assert res["resource_group_breakdown"]["rg-compute"] == 125.50
    assert res["row_count"] == 2


def test_query_arm_resources_direct_mocked(monkeypatch) -> None:
    import asyncio
    from function_app import AzureRealClient

    client = AzureRealClient()

    def mock_arm_http(method, url, **kwargs):
        return 200, {
            "value": [
                {
                    "id": "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/disks/disk-os",
                    "name": "disk-os",
                    "type": "Microsoft.Compute/disks",
                    "location": "northcentralus",
                    "sku": {"name": "Premium_LRS"},
                    "tags": {"env": "prod"},
                }
            ]
        }

    import function_app
    monkeypatch.setattr(function_app, "_sync_http_request", mock_arm_http)
    import services.azure_real_client
    monkeypatch.setattr(services.azure_real_client, "_sync_http_request", mock_arm_http)

    items = asyncio.run(client.query_arm_resources_direct("dummy-token", "sub-123"))
    assert len(items) == 1
    assert items[0].name == "disk-os"
    assert items[0].resource_group == "rg-prod"
    assert items[0].sku_name == "Premium_LRS"
    assert items[0].tags == {"env": "prod"}

