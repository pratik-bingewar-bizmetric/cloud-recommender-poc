"""Unit tests for FinOps Waste Detector algorithms."""

from decimal import Decimal

import pytest
from schemas.models import DiscoveredResource
from services.waste_detector import FinOpsWasteDetector


@pytest.fixture
def detector() -> FinOpsWasteDetector:
    return FinOpsWasteDetector()


def test_detect_unattached_disks(detector: FinOpsWasteDetector) -> None:
    resources = [
        DiscoveredResource(
            resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-orphaned",
            name="disk-orphaned",
            resource_type="Microsoft.Compute/disks",
            location="northcentralus",
            tags={"diskState": "Unattached"},
            power_state="Unattached",
            monthly_cost_usd=Decimal("25.00"),
        ),
        DiscoveredResource(
            resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-active",
            name="disk-active",
            resource_type="Microsoft.Compute/disks",
            location="northcentralus",
            tags={"diskState": "Attached", "managedBy": "vm-prod"},
            power_state="Attached",
            monthly_cost_usd=Decimal("25.00"),
        ),
    ]

    summary = detector.analyze_waste("conn-1", resources)
    assert summary.total_monthly_waste_usd == Decimal("25.00")
    assert summary.total_annual_waste_usd == Decimal("300.00")
    assert len(summary.items) == 1
    assert summary.items[0].waste_category == "unattached_disk"
    assert summary.items[0].name == "disk-orphaned"


def test_detect_idle_virtual_machines(detector: FinOpsWasteDetector) -> None:
    resources = [
        DiscoveredResource(
            resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-idle",
            name="vm-idle",
            resource_type="Microsoft.Compute/virtualMachines",
            location="northcentralus",
            sku_name="Standard_D4s_v5",
            power_state="running",
            monthly_cost_usd=Decimal("140.16"),
        ),
        DiscoveredResource(
            resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-busy",
            name="vm-busy",
            resource_type="Microsoft.Compute/virtualMachines",
            location="northcentralus",
            sku_name="Standard_D4s_v5",
            power_state="running",
            monthly_cost_usd=Decimal("140.16"),
        ),
    ]

    # vm-idle has 2.4% max CPU, vm-busy has 68.0% max CPU
    metrics = {
        "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-idle": 2.4,
        "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-busy": 68.0,
    }

    summary = detector.analyze_waste("conn-1", resources, vm_cpu_metrics=metrics)
    assert len(summary.items) == 1
    assert summary.items[0].waste_category == "idle_compute"
    assert summary.items[0].name == "vm-idle"
    assert summary.items[0].monthly_cost_leakage_usd == Decimal("140.16")


def test_detect_unassociated_public_ips(detector: FinOpsWasteDetector) -> None:
    resources = [
        DiscoveredResource(
            resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip-idle",
            name="pip-idle",
            resource_type="Microsoft.Network/publicIPAddresses",
            location="northcentralus",
            power_state="unassociated",
            monthly_cost_usd=Decimal("3.65"),
        )
    ]

    summary = detector.analyze_waste("conn-1", resources)
    assert len(summary.items) == 1
    assert summary.items[0].waste_category == "unassociated_ip"
    assert summary.items[0].monthly_cost_leakage_usd == Decimal("3.65")


def test_empty_resources_yields_zero_waste(detector: FinOpsWasteDetector) -> None:
    summary = detector.analyze_waste("conn-empty", [])
    assert summary.total_monthly_waste_usd == Decimal("0.00")


def test_unattached_disk_without_pricing_falls_back_to_unavailable(
    detector: FinOpsWasteDetector,
) -> None:
    resources = [
        DiscoveredResource(
            resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-unpriced",
            name="disk-unpriced",
            resource_type="Microsoft.Compute/disks",
            location="northcentralus",
            tags={"diskState": "Unattached"},
            power_state="Unattached",
            monthly_cost_usd=None,
        )
    ]
    summary = detector.analyze_waste("conn-1", resources)
    assert len(summary.items) == 1
    assert summary.items[0].waste_category == "unattached_disk"
    assert summary.items[0].cost_status == "pricing_unavailable"
    assert summary.items[0].monthly_cost_leakage_usd == Decimal("0.00")
    assert summary.total_monthly_waste_usd == Decimal("0.00")
    assert summary.total_annual_waste_usd == Decimal("0.00")
    assert summary.waste_count_by_category == {"unattached_disk": 1}
