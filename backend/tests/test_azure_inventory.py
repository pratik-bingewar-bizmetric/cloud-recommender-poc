"""Unit and integration tests for Azure read-only subscription hierarchy and inventory discovery."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.analysis import WorkloadAssumptions
from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService


@pytest.fixture
def mock_azure_service() -> AzureInventoryService:
    settings = Settings(offline_pricing_mode=True)
    return AzureInventoryService(settings=settings)


@pytest.mark.asyncio
async def test_azure_inventory_unauthenticated_connection_status() -> None:
    """Verify connection status reports clear unauthenticated diagnostic when no credentials present."""
    settings = Settings(
        azure_tenant_id=None,
        azure_client_id=None,
        azure_client_secret=None,
        offline_pricing_mode=True,
    )
    svc = AzureInventoryService(settings=settings)
    with patch.object(svc, "get_access_token", AsyncMock(return_value=(None, "none"))):
        status = await svc.get_connection_status()
        assert status.provider == CloudProvider.AZURE
        assert status.inventory_auth_ready is False
        assert status.pricing_api_ready is True
        assert "unauthenticated" in status.inventory_auth_method.lower()
        assert any("strictly read-only" in lim.lower() for lim in status.access_limitations)


@pytest.mark.asyncio
async def test_azure_inventory_demo_fixture_fallback_when_unauthenticated(
    mock_azure_service: AzureInventoryService,
) -> None:
    """Verify analyze_subscription provides an explicitly labeled mock fixture when unauthenticated."""
    with patch.object(
        mock_azure_service, "get_access_token", AsyncMock(return_value=(None, "none"))
    ):
        result = await mock_azure_service.analyze_subscription(
            subscription_id="f718c261-ab85-49fd-907e-99c022cc2aeb"
        )
        assert result.provider == CloudProvider.AZURE
        assert result.data_source == "mock_fixture"
        assert result.scope_type == "azure_subscription"
        assert result.spend_label == "estimated_public_list_pricing"
        assert len(result.groups) > 0
        assert len(result.resources) > 0
        assert result.cost_breakdown.subtotal > Decimal("0.00")
        assert "flowchart TD" in result.architecture_mermaid


@pytest.mark.asyncio
async def test_azure_resource_normalization_and_pricing(
    mock_azure_service: AzureInventoryService,
) -> None:
    """Verify accurate mapping and deterministic pricing for real ARM resource types."""
    assumptions = WorkloadAssumptions(customer_count=51)

    # 1. Cognitive Services S0 (Provisional token usage)
    (
        m_s0,
        status_s0,
        expl_s0,
        warn_s0,
        pref_s0,
    ) = await mock_azure_service._price_discovered_resource(
        canonical_id="azure-openai-foundry",
        service_name="Azure OpenAI Service",
        category=ServiceCategory.AI_ML,
        region="eastus",
        sku_str="S0",
        kind="OpenAI",
        native_type="Microsoft.CognitiveServices/accounts",
        assumptions=assumptions,
        same_rg_server_farms=[],
    )
    assert status_s0 == "provisional"
    assert m_s0 > Decimal("0.00")

    # 2. Cognitive Services F0 Free Tier (Verified $0.00)
    (
        m_f0,
        status_f0,
        expl_f0,
        warn_f0,
        _,
    ) = await mock_azure_service._price_discovered_resource(
        canonical_id="azure-openai-foundry",
        service_name="Azure Document Intelligence",
        category=ServiceCategory.AI_ML,
        region="eastus",
        sku_str="F0",
        kind="FormRecognizer",
        native_type="Microsoft.CognitiveServices/accounts",
        assumptions=assumptions,
        same_rg_server_farms=[],
    )
    assert status_f0 == "verified"
    assert m_f0 == Decimal("0.00")
    assert "$0.00/month included free quota" in expl_f0

    # 3. Child Project Resource (Bundled $0.00)
    (
        m_proj,
        status_proj,
        expl_proj,
        _,
        _,
    ) = await mock_azure_service._price_discovered_resource(
        canonical_id="azure-openai-foundry-project",
        service_name="Azure AI Foundry Project",
        category=ServiceCategory.AI_ML,
        region="eastus",
        sku_str="S0",
        kind="AIServices",
        native_type="Microsoft.CognitiveServices/accounts/projects",
        assumptions=assumptions,
        same_rg_server_farms=[],
    )
    assert status_proj == "bundled"
    assert m_proj == Decimal("0.00")
    assert "incremental charge" in expl_proj

    # 4. Web App (Sites) hosted on App Service Plan (Bundled $0.00)
    (
        m_site,
        status_site,
        expl_site,
        _,
        _,
    ) = await mock_azure_service._price_discovered_resource(
        canonical_id="azure-app-service-site",
        service_name="Azure Web App",
        category=ServiceCategory.COMPUTE,
        region="centralindia",
        sku_str="Basic B1",
        kind="app,linux",
        native_type="Microsoft.Web/sites",
        assumptions=assumptions,
        same_rg_server_farms=["ASP-rgsmartexpensestaging-a04f"],
    )
    assert status_site == "bundled"
    assert m_site == Decimal("0.00")
    assert "bundled into its hosting App Service Plan" in expl_site

    # 5. User-Assigned Managed Identity (Verified $0.00)
    (
        m_id,
        status_id,
        expl_id,
        _,
        _,
    ) = await mock_azure_service._price_discovered_resource(
        canonical_id="azure-managed-identity",
        service_name="Azure User-Assigned Managed Identity",
        category=ServiceCategory.SECURITY,
        region="centralindia",
        sku_str=None,
        kind=None,
        native_type="Microsoft.ManagedIdentity/userAssignedIdentities",
        assumptions=assumptions,
        same_rg_server_farms=[],
    )
    assert status_id == "verified"
    assert m_id == Decimal("0.00")


@pytest.mark.asyncio
async def test_azure_inventory_live_token_simulation_and_rollups(
    mock_azure_service: AzureInventoryService,
) -> None:
    """Simulate a complete 5-resource-group Azure subscription and verify hierarchical rollups."""
    sub_id = "f718c261-ab85-49fd-907e-99c022cc2aeb"
    mock_token = "fake-valid-access-token"

    mock_rgs = [
        {
            "id": f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense",
            "name": "rg-smart-expense",
            "location": "eastus",
        },
        {
            "id": f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-staging",
            "name": "rg-smart-expense-staging",
            "location": "centralindia",
        },
        {
            "id": f"/subscriptions/{sub_id}/resourceGroups/DefaultResourceGroup-CID",
            "name": "DefaultResourceGroup-CID",
            "location": "centralindia",
        },
    ]

    mock_resources = [
        # RG 1 (East US)
        {
            "id": f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense/providers/Microsoft.CognitiveServices/accounts/smart-expense-ai-bizmetric",
            "name": "smart-expense-ai-bizmetric",
            "type": "Microsoft.CognitiveServices/accounts",
            "location": "eastus",
            "kind": "OpenAI",
            "sku": {"name": "S0"},
        },
        {
            "id": f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense/providers/Microsoft.CognitiveServices/accounts/smart-expense-ai-bizmetric/projects/proj-1",
            "name": "smart-expense-ai-bizmetric/proj-1",
            "type": "Microsoft.CognitiveServices/accounts/projects",
            "location": "eastus",
            "kind": "OpenAI",
        },
        # RG 2 (Central India & Canada Central)
        {
            "id": f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-staging/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-smart-expense-staging",
            "name": "psql-smart-expense-staging",
            "type": "Microsoft.DBforPostgreSQL/flexibleServers",
            "location": "canadacentral",
            "sku": {"name": "Standard_B2s", "tier": "Burstable"},
        },
        {
            "id": f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-staging/providers/Microsoft.Web/serverFarms/ASP-staging",
            "name": "ASP-staging",
            "type": "Microsoft.Web/serverFarms",
            "location": "centralindia",
            "sku": {"name": "B1", "tier": "Basic"},
        },
        {
            "id": f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-staging/providers/Microsoft.Web/sites/smart-expense-api-staging",
            "name": "smart-expense-api-staging",
            "type": "Microsoft.Web/sites",
            "location": "centralindia",
            "kind": "app,linux",
        },
    ]

    with (
        patch.object(
            mock_azure_service,
            "get_access_token",
            AsyncMock(return_value=(mock_token, "azure_cli_session")),
        ),
        patch.object(mock_azure_service, "list_management_groups", AsyncMock(return_value=[])),
        patch.object(mock_azure_service, "list_resource_groups", AsyncMock(return_value=mock_rgs)),
        patch.object(mock_azure_service, "list_resources", AsyncMock(return_value=mock_resources)),
    ):
        result = await mock_azure_service.analyze_subscription(subscription_id=sub_id)

        assert result.provider == CloudProvider.AZURE
        assert result.scope_id == sub_id
        assert result.data_source == "live_authenticated"
        assert result.resource_count == 5
        assert result.group_count == 3  # 3 Resource Groups

        # Find RG staging
        rg_staging = next(g for g in result.groups if g.group_name == "rg-smart-expense-staging")
        assert rg_staging.resource_count == 3
        assert rg_staging.total_monthly > Decimal("0.00")
        assert rg_staging.total_annual == rg_staging.total_monthly * Decimal("12.00")

        # Verify relationships
        proj_res = next(
            r for r in result.resources if r.resource_name == "smart-expense-ai-bizmetric/proj-1"
        )
        assert len(proj_res.relationships) == 1
        assert proj_res.relationships[0].relationship_type == "verified_arm_hierarchy"
        assert proj_res.relationships[0].is_verified is True

        site_res = next(
            r for r in result.resources if r.resource_name == "smart-expense-api-staging"
        )
        assert any(
            rel.relationship_type == "verified_hosting_plan" and rel.is_verified is True
            for rel in site_res.relationships
        )

        # Verify recommendations
        rec_ids = [rec.id for rec in result.recommendations]
        assert any("cross-region" in rid for rid in rec_ids)  # Canadacentral DB vs Centralindia App
        assert any("empty-rg" in rid for rid in rec_ids)  # DefaultResourceGroup-CID
