"""Unit and integration tests for multi-cloud resource waste detection, technical debt analysis, and hierarchical rollups."""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from cloud_recommender.main import app
from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
from cloud_recommender.schemas.inventory import (
    DiscoveredResource,
    ScopeCostGroup,
)
from cloud_recommender.services.inventory.waste_debt_engine import WasteAndTechnicalDebtEngine


def test_waste_engine_unattached_disk_detection():
    """Verify unattached managed disks are identified with 100% savings and high severity."""
    engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
    disk = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/disks/disk-orphaned-temp",
        resource_name="disk-orphaned-temp",
        native_resource_type="Microsoft.Compute/disks",
        canonical_service_id="azure-managed-disk",
        service_category=ServiceCategory.STORAGE,
        region="eastus",
        sku_or_tier="Premium_LRS P10 (128 GiB)",
        parent_scope_id="/subscriptions/sub1/resourceGroups/rg1",
        resource_group="rg1",
        configuration={"diskState": "Unattached", "managedBy": None},
        estimated_monthly_cost=Decimal("19.71"),
    )
    group = ScopeCostGroup(
        group_id="/subscriptions/sub1/resourceGroups/rg1",
        group_name="rg1",
        group_type="azure_resource_group",
        location="eastus",
        resource_count=1,
        verified_monthly_subtotal=Decimal("19.71"),
        total_monthly=Decimal("19.71"),
        total_five_month=Decimal("98.55"),
        total_annual=Decimal("236.52"),
        resources=[disk],
    )

    waste, debt, tot_monthly, tot_annual, coverage = engine.evaluate_scope(
        CloudProvider.AZURE, "sub1", [disk], [group]
    )

    assert len(waste) == 1
    w = waste[0]
    assert w.category == "unattached_storage"
    assert w.severity == "high"
    assert w.potential_monthly_savings == Decimal("19.71")
    assert "Unattached" in w.evidence
    assert tot_monthly == Decimal("19.71")
    assert tot_annual == Decimal("236.52")
    assert group.potential_monthly_savings == Decimal("19.71")
    assert group.waste_findings_count == 1
    assert group.high_findings_count >= 1


def test_waste_engine_stopped_vm_and_non_double_counting():
    """Verify deallocated VM only counts compute portion and prevents double counting."""
    engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
    vm = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm-idle-batch",
        resource_name="vm-idle-batch",
        native_resource_type="Microsoft.Compute/virtualMachines",
        canonical_service_id="azure-virtual-machine",
        service_category=ServiceCategory.COMPUTE,
        region="eastus",
        sku_or_tier="Standard_B2s",
        parent_scope_id="/subscriptions/sub1/resourceGroups/rg1",
        resource_group="rg1",
        configuration={"powerState": "PowerState/deallocated"},
        estimated_monthly_cost=Decimal("36.50"),
    )
    group = ScopeCostGroup(
        group_id="/subscriptions/sub1/resourceGroups/rg1",
        group_name="rg1",
        group_type="azure_resource_group",
        location="eastus",
        resource_count=1,
        verified_monthly_subtotal=Decimal("36.50"),
        total_monthly=Decimal("36.50"),
        total_five_month=Decimal("182.50"),
        total_annual=Decimal("438.00"),
        resources=[vm],
    )

    waste, _, tot_monthly, tot_annual, _ = engine.evaluate_scope(
        CloudProvider.AZURE, "sub1", [vm], [group]
    )

    assert len(waste) == 1
    assert waste[0].category == "stopped_compute"
    assert waste[0].potential_monthly_savings == Decimal("31.03")  # 85% of compute
    assert tot_monthly == Decimal("31.03")
    assert "compute billing is suspended" in waste[0].description.lower()
    assert "disk" in waste[0].double_counting_prevention_note.lower()


def test_waste_engine_dev_database_high_availability_waste():
    """Verify non-production database with Zone-Redundant / Regional HA is flagged with 50% savings."""
    engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
    db = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-test-cluster",
        resource_name="psql-test-cluster",
        native_resource_type="Microsoft.DBforPostgreSQL/flexibleServers",
        canonical_service_id="azure-postgres-flexible",
        service_category=ServiceCategory.DATABASE,
        region="eastus",
        sku_or_tier="Standard_B2s (ZoneRedundant)",
        parent_scope_id="/subscriptions/sub1/resourceGroups/rg1",
        resource_group="rg1",
        tags_or_labels={"env": "dev"},
        configuration={"highAvailability": {"mode": "ZoneRedundant"}},
        estimated_monthly_cost=Decimal("73.00"),
    )
    group = ScopeCostGroup(
        group_id="/subscriptions/sub1/resourceGroups/rg1",
        group_name="rg1",
        group_type="azure_resource_group",
        location="eastus",
        resource_count=1,
        verified_monthly_subtotal=Decimal("73.00"),
        total_monthly=Decimal("73.00"),
        total_five_month=Decimal("365.00"),
        total_annual=Decimal("876.00"),
        resources=[db],
    )

    waste, _, tot_monthly, _, _ = engine.evaluate_scope(CloudProvider.AZURE, "sub1", [db], [group])

    assert len(waste) == 1
    w = waste[0]
    assert w.category == "overprovisioned_database"
    assert w.potential_monthly_savings == Decimal("36.50")
    assert "non-production" in w.title.lower()


def test_waste_engine_gcp_unattached_ip_and_orphaned_disk():
    """Verify GCP unattached static IP penalty and orphaned persistent disk detection."""
    engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
    ip_res = DiscoveredResource(
        provider=CloudProvider.GCP,
        resource_id="//compute.googleapis.com/projects/p1/regions/us-central1/addresses/ip-unattached",
        resource_name="ip-unattached",
        native_resource_type="compute.googleapis.com/Address",
        canonical_service_id="gcp-generic-service",
        service_category=ServiceCategory.NETWORKING,
        region="us-central1",
        parent_scope_id="projects/p1",
        project_id="p1",
        configuration={"users": [], "status": "RESERVED"},
        estimated_monthly_cost=Decimal("7.30"),
    )
    disk_res = DiscoveredResource(
        provider=CloudProvider.GCP,
        resource_id="//compute.googleapis.com/projects/p1/zones/us-central1-a/disks/disk-orphaned",
        resource_name="disk-orphaned",
        native_resource_type="compute.googleapis.com/Disk",
        canonical_service_id="gcp-storage-generic",
        service_category=ServiceCategory.STORAGE,
        region="us-central1",
        parent_scope_id="projects/p1",
        project_id="p1",
        configuration={"users": []},
        estimated_monthly_cost=Decimal("8.00"),
    )
    group = ScopeCostGroup(
        group_id="projects/p1/domains/infra",
        group_name="Infrastructure",
        group_type="gcp_service_domain",
        location="us-central1",
        resource_count=2,
        verified_monthly_subtotal=Decimal("15.30"),
        total_monthly=Decimal("15.30"),
        total_five_month=Decimal("76.50"),
        total_annual=Decimal("183.60"),
        resources=[ip_res, disk_res],
    )

    waste, _, tot_monthly, tot_annual, _ = engine.evaluate_scope(
        CloudProvider.GCP, "p1", [ip_res, disk_res], [group]
    )

    assert len(waste) == 2
    categories = {w.category for w in waste}
    assert "unattached_ip" in categories
    assert "unattached_storage" in categories
    assert tot_monthly == Decimal("15.30")
    assert tot_annual == Decimal("183.60")


def test_technical_debt_governance_tags_and_security_exposure():
    """Verify detection of missing enterprise governance tags and public storage access."""
    engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
    stg = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Storage/storageAccounts/stgopen",
        resource_name="stgopen",
        native_resource_type="microsoft.storage/storageaccounts",
        canonical_service_id="azure-blob-storage",
        service_category=ServiceCategory.STORAGE,
        region="eastus",
        parent_scope_id="/subscriptions/sub1/resourceGroups/rg1",
        resource_group="rg1",
        tags_or_labels={},  # Missing all tags
        configuration={"publicNetworkAccess": "Enabled", "networkAcls": {"defaultAction": "Allow"}},
        estimated_monthly_cost=Decimal("10.00"),
    )
    group = ScopeCostGroup(
        group_id="/subscriptions/sub1/resourceGroups/rg1",
        group_name="rg1",
        group_type="azure_resource_group",
        location="eastus",
        resource_count=1,
        verified_monthly_subtotal=Decimal("10.00"),
        total_monthly=Decimal("10.00"),
        total_five_month=Decimal("50.00"),
        total_annual=Decimal("120.00"),
        resources=[stg],
    )

    _, debts, _, _, _ = engine.evaluate_scope(CloudProvider.AZURE, "sub1", [stg], [group])

    debt_categories = {d.debt_category for d in debts}
    assert "missing_tagging" in debt_categories
    assert "unrestricted_network" in debt_categories

    # Critical security finding
    crit = next(d for d in debts if d.debt_category == "unrestricted_network")
    assert crit.severity == "critical"
    assert "public internet access" in crit.title.lower()


@pytest.mark.asyncio
async def test_api_azure_analyze_returns_waste_and_technical_debt_rollups(
    monkeypatch: pytest.MonkeyPatch,
):
    """Integration test verifying /api/v1/inventory/azure/analyze includes waste & tech debt rollups."""
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService

    async def mock_no_token(_self):
        return None, "unauthenticated"

    monkeypatch.setattr(AzureInventoryService, "get_access_token", mock_no_token)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/inventory/azure/analyze",
            json={
                "scope_id": "f718c261-ab85-49fd-907e-99c022cc2aeb",
                "metric_window_days": 30,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "total_potential_monthly_savings" in data
        assert "total_potential_annual_savings" in data
        assert "waste_findings" in data
        assert "technical_debt_items" in data
        assert "telemetry_coverage" in data

        assert float(data["total_potential_monthly_savings"]) > 0
        assert len(data["waste_findings"]) > 0
        assert len(data["technical_debt_items"]) > 0

        # Check telemetry coverage structure
        cov = data["telemetry_coverage"]
        assert cov["metric_window_days"] == 30
        assert cov["monitored_resources_count"] > 0
        assert float(cov["confidence_score"]) >= 0.75

        # Check group rollups
        assert len(data["groups"]) >= 1
        for grp in data["groups"]:
            assert "potential_monthly_savings" in grp
            assert "waste_findings_count" in grp
            assert "technical_debt_count" in grp


@pytest.mark.asyncio
async def test_api_gcp_analyze_returns_waste_and_technical_debt_rollups():
    """Integration test verifying /api/v1/inventory/gcp/analyze includes waste & tech debt rollups."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/inventory/gcp/analyze",
            json={
                "scope_id": "smart-expense-gcp-prod",
                "metric_window_days": 30,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "total_potential_monthly_savings" in data
        assert "total_potential_annual_savings" in data
        assert "waste_findings" in data
        assert "technical_debt_items" in data
        assert "telemetry_coverage" in data

        assert float(data["total_potential_monthly_savings"]) > 0
        assert len(data["waste_findings"]) >= 1

        # Check groups rollups
        assert len(data["groups"]) >= 1
        for grp in data["groups"]:
            assert "potential_monthly_savings" in grp
            assert "waste_findings_count" in grp
            assert "technical_debt_count" in grp
