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
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
from cloud_recommender.services.inventory.waste_debt_engine import WasteAndTechnicalDebtEngine


def test_waste_engine_unattached_disk_detection() -> None:
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


def test_waste_engine_stopped_vm_and_non_double_counting() -> None:
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
    assert waste[0].double_counting_prevention_note is not None
    assert "disk" in waste[0].double_counting_prevention_note.lower()


def test_waste_engine_dev_database_high_availability_waste() -> None:
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


def test_waste_engine_gcp_unattached_ip_and_orphaned_disk() -> None:
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


def test_technical_debt_governance_tags_and_security_exposure() -> None:
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
) -> None:
    """Integration test verifying /api/v1/inventory/azure/analyze includes waste & tech debt rollups."""

    async def mock_no_token(_self: AzureInventoryService) -> tuple[str | None, str]:
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
async def test_api_gcp_analyze_returns_waste_and_technical_debt_rollups() -> None:
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


def test_waste_engine_false_positive_dr_standby_exempt() -> None:
    """Verify disaster-recovery / standby VM is exempted from stopped compute waste."""
    engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
    dr_vm = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm-prod-secondary-dr",
        resource_name="vm-prod-secondary-dr",
        native_resource_type="Microsoft.Compute/virtualMachines",
        canonical_service_id="azure-virtual-machine",
        service_category=ServiceCategory.COMPUTE,
        region="eastus",
        sku_or_tier="Standard_D4s_v5",
        parent_scope_id="/subscriptions/sub1/resourceGroups/rg1",
        resource_group="rg1",
        tags_or_labels={"role": "disaster-recovery", "env": "prod"},
        configuration={"powerState": "PowerState/deallocated"},
        estimated_monthly_cost=Decimal("150.00"),
    )
    group = ScopeCostGroup(
        group_id="/subscriptions/sub1/resourceGroups/rg1",
        group_name="rg1",
        group_type="azure_resource_group",
        location="eastus",
        resource_count=1,
        verified_monthly_subtotal=Decimal("150.00"),
        total_monthly=Decimal("150.00"),
        total_five_month=Decimal("750.00"),
        total_annual=Decimal("1800.00"),
        resources=[dr_vm],
    )

    waste, _, tot_monthly, _, _ = engine.evaluate_scope(
        CloudProvider.AZURE, "sub1", [dr_vm], [group]
    )

    # Standby DR VM should NOT be flagged as waste
    stopped_waste = [w for w in waste if w.category == "stopped_compute"]
    assert len(stopped_waste) == 0
    assert tot_monthly == Decimal("0.00")


def test_waste_engine_false_positive_batch_workload() -> None:
    """Verify scheduled batch / worker host is identified with batch_scheduling advice rather than SKU downsizing."""
    engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
    batch_vm = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm-etl-pipeline-worker",
        resource_name="vm-etl-pipeline-worker",
        native_resource_type="Microsoft.Compute/virtualMachines",
        canonical_service_id="azure-virtual-machine",
        service_category=ServiceCategory.COMPUTE,
        region="eastus",
        sku_or_tier="Standard_F4s_v2",
        parent_scope_id="/subscriptions/sub1/resourceGroups/rg1",
        resource_group="rg1",
        tags_or_labels={"workload-type": "batch-nightly"},
        configuration={"powerState": "PowerState/running", "avg_cpu_percent": 3.4},
        estimated_monthly_cost=Decimal("120.00"),
    )
    group = ScopeCostGroup(
        group_id="/subscriptions/sub1/resourceGroups/rg1",
        group_name="rg1",
        group_type="azure_resource_group",
        location="eastus",
        resource_count=1,
        verified_monthly_subtotal=Decimal("120.00"),
        total_monthly=Decimal("120.00"),
        total_five_month=Decimal("600.00"),
        total_annual=Decimal("1440.00"),
        resources=[batch_vm],
    )

    waste, _, _, _, _ = engine.evaluate_scope(CloudProvider.AZURE, "sub1", [batch_vm], [group])

    assert len(waste) == 1
    w = waste[0]
    assert w.category == "idle_compute"
    assert w.severity == "low"
    assert "batch" in w.title.lower()
    assert "runbooks" in w.remediation_recommendation.lower()


def test_waste_engine_compliance_hold_disk_provisional() -> None:
    """Verify unattached disk with compliance/retention hold has provisional confidence and $0 automated savings."""
    engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
    retained_disk = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/disks/disk-audit-archive-2025",
        resource_name="disk-audit-archive-2025",
        native_resource_type="Microsoft.Compute/disks",
        canonical_service_id="azure-managed-disk",
        service_category=ServiceCategory.STORAGE,
        region="eastus",
        sku_or_tier="Standard_LRS (512 GiB)",
        parent_scope_id="/subscriptions/sub1/resourceGroups/rg1",
        resource_group="rg1",
        tags_or_labels={"retention": "7-years-compliance", "legal-hold": "true"},
        configuration={"diskState": "Unattached", "managedBy": None},
        estimated_monthly_cost=Decimal("20.48"),
    )
    group = ScopeCostGroup(
        group_id="/subscriptions/sub1/resourceGroups/rg1",
        group_name="rg1",
        group_type="azure_resource_group",
        location="eastus",
        resource_count=1,
        verified_monthly_subtotal=Decimal("20.48"),
        total_monthly=Decimal("20.48"),
        total_five_month=Decimal("102.40"),
        total_annual=Decimal("245.76"),
        resources=[retained_disk],
    )

    waste, _, tot_monthly, _, _ = engine.evaluate_scope(
        CloudProvider.AZURE, "sub1", [retained_disk], [group]
    )

    assert len(waste) == 1
    w = waste[0]
    assert w.confidence == "provisional"
    assert w.potential_monthly_savings == Decimal("0.00")
    assert "retention" in w.title.lower() or "archived" in w.title.lower()
    assert tot_monthly == Decimal("0.00")


def test_waste_engine_reservation_commitment_zero_savings() -> None:
    """Verify active reservation on deallocated VM prevents claiming phantom compute savings."""
    engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
    reserved_vm = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm-prepaid-db",
        resource_name="vm-prepaid-db",
        native_resource_type="Microsoft.Compute/virtualMachines",
        canonical_service_id="azure-virtual-machine",
        service_category=ServiceCategory.COMPUTE,
        region="eastus",
        sku_or_tier="Standard_D2s_v5",
        parent_scope_id="/subscriptions/sub1/resourceGroups/rg1",
        resource_group="rg1",
        tags_or_labels={"env": "prod"},
        configuration={"powerState": "PowerState/deallocated", "reservation_id": "res-998811"},
        estimated_monthly_cost=Decimal("70.00"),
    )
    group = ScopeCostGroup(
        group_id="/subscriptions/sub1/resourceGroups/rg1",
        group_name="rg1",
        group_type="azure_resource_group",
        location="eastus",
        resource_count=1,
        verified_monthly_subtotal=Decimal("70.00"),
        total_monthly=Decimal("70.00"),
        total_five_month=Decimal("350.00"),
        total_annual=Decimal("840.00"),
        resources=[reserved_vm],
    )

    waste, _, tot_monthly, _, _ = engine.evaluate_scope(
        CloudProvider.AZURE, "sub1", [reserved_vm], [group]
    )

    assert len(waste) == 1
    w = waste[0]
    assert w.potential_monthly_savings == Decimal("0.00")
    assert w.double_counting_prevention_note is not None
    assert "reservation" in w.double_counting_prevention_note.lower()
    assert tot_monthly == Decimal("0.00")


def test_waste_engine_unmonitored_cognitive_and_app_service_not_flagged_waste() -> None:
    """Verify unmonitored resources without metrics are NOT flagged as waste, but categorized as Technical Debt."""
    engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
    ai_acc = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.CognitiveServices/accounts/cog-doc-intelligence",
        resource_name="cog-doc-intelligence",
        native_resource_type="Microsoft.CognitiveServices/accounts",
        canonical_service_id="azure-openai-foundry",
        service_category=ServiceCategory.AI_ML,
        region="eastus",
        sku_or_tier="S0",
        parent_scope_id="/subscriptions/sub1/resourceGroups/rg1",
        resource_group="rg1",
        tags_or_labels={"env": "prod", "owner": "ai-team"},
        configuration={
            "customSubDomainName": "cog-doc"
        },  # Note: NO token_usage or avg_tpm_utilization
        estimated_monthly_cost=Decimal("25.00"),
    )
    asp = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Web/serverfarms/asp-core-service",
        resource_name="asp-core-service",
        native_resource_type="Microsoft.Web/serverfarms",
        canonical_service_id="azure-app-service",
        service_category=ServiceCategory.COMPUTE,
        region="eastus",
        sku_or_tier="P1v3",
        parent_scope_id="/subscriptions/sub1/resourceGroups/rg1",
        resource_group="rg1",
        tags_or_labels={"env": "prod", "owner": "platform"},
        configuration={"has_metrics": False},  # Note: avg_cpu_percent is None
        estimated_monthly_cost=Decimal("80.00"),
    )
    group = ScopeCostGroup(
        group_id="/subscriptions/sub1/resourceGroups/rg1",
        group_name="rg1",
        group_type="azure_resource_group",
        location="eastus",
        resource_count=2,
        verified_monthly_subtotal=Decimal("105.00"),
        total_monthly=Decimal("105.00"),
        total_five_month=Decimal("525.00"),
        total_annual=Decimal("1260.00"),
        resources=[ai_acc, asp],
    )

    waste, debt, tot_monthly, _, coverage = engine.evaluate_scope(
        CloudProvider.AZURE, "sub1", [ai_acc, asp], [group]
    )

    # Neither should be flagged as financial waste because metrics were absent
    assert len(waste) == 0
    assert tot_monthly == Decimal("0.00")

    # Both should be flagged under Technical Debt for missing diagnostic settings
    missing_diag_debts = [d for d in debt if d.debt_category == "missing_monitoring"]
    assert len(missing_diag_debts) == 2
    assert any("cog-doc-intelligence" in d.title for d in missing_diag_debts)
    assert any("asp-core-service" in d.title for d in missing_diag_debts)

    # Coverage summary should explicitly record unmonitored resources in limitations
    assert any("lack runtime performance metrics" in lim for lim in coverage.limitations_and_gaps)
