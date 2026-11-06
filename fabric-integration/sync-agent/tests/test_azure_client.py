"""Unit tests for Azure Resource Graph Inventory Extractor."""

from unittest.mock import MagicMock, patch

from auth import AzureCliAuthManager
from azure_client import AzureInventoryExtractor
from config import SyncAgentConfig


def test_extract_power_state_vm():
    extractor = AzureInventoryExtractor(MagicMock(), SyncAgentConfig())
    props = {"extended": {"instanceView": {"powerState": {"code": "PowerState/running"}}}}
    state = extractor._extract_power_state(props)
    assert state == "PowerState/running"


def test_extract_power_state_db():
    extractor = AzureInventoryExtractor(MagicMock(), SyncAgentConfig())
    props = {"state": "Ready"}
    assert extractor._extract_power_state(props) == "Ready"


def test_extract_sku_name():
    extractor = AzureInventoryExtractor(MagicMock(), SyncAgentConfig())
    assert extractor._extract_sku_name({"name": "Standard_B2s"}) == "Standard_B2s"
    assert extractor._extract_sku_name("Basic") == "Basic"
    assert extractor._extract_sku_name(None) is None


def test_extract_inventory_pagination_and_mapping():
    mock_auth = MagicMock(spec=AzureCliAuthManager)
    mock_auth.get_token.return_value = "mock-token"

    config = SyncAgentConfig(subscription_id="sub-abc", connection_id="conn-test")
    extractor = AzureInventoryExtractor(mock_auth, config)

    # Page 1 with skipToken
    page1 = {
        "$skipToken": "skip-token-123",
        "data": [
            {
                "id": "/subscriptions/sub-abc/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1",
                "name": "vm1",
                "type": "Microsoft.Compute/virtualMachines",
                "location": "eastus",
                "resourceGroup": "rg1",
                "sku": {"name": "Standard_D2s_v3"},
                "tags": {"project": "finops"},
                "properties": {
                    "extended": {"instanceView": {"powerState": {"code": "PowerState/running"}}}
                },
            }
        ],
    }
    # Page 2 without skipToken
    page2 = {
        "data": [
            {
                "id": "/subscriptions/sub-abc/resourceGroups/rg1/providers/Microsoft.Storage/storageAccounts/stg1",
                "name": "stg1",
                "type": "Microsoft.Storage/storageAccounts",
                "location": "eastus",
                "resourceGroup": "rg1",
                "sku": "Standard_LRS",
                "tags": None,
                "properties": {"provisioningState": "Succeeded"},
            }
        ]
    }

    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = page1

    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.json.return_value = page2

    with patch("httpx.Client.post", side_effect=[resp1, resp2]):
        records = extractor.extract_inventory()
        assert len(records) == 2
        r1, r2 = records[0], records[1]

        assert r1.name == "vm1"
        assert r1.resource_type == "Microsoft.Compute/virtualMachines"
        assert r1.sku_name == "Standard_D2s_v3"
        assert r1.power_state == "PowerState/running"
        assert '{"project": "finops"}' in (r1.tags or "")
        assert r1.connection_id == "conn-test"

        assert r2.name == "stg1"
        assert r2.resource_type == "Microsoft.Storage/storageAccounts"
        assert r2.sku_name == "Standard_LRS"
        assert r2.power_state == "Succeeded"
