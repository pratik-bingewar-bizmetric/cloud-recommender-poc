"""Unit tests for GCP project inventory hierarchy and Azure vs. GCP multi-cloud comparator."""

from decimal import Decimal

import pytest

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.analysis import WorkloadAssumptions
from cloud_recommender.schemas.common import CloudProvider, WorkloadCategory
from cloud_recommender.schemas.inventory import MultiCloudComparisonRequest
from cloud_recommender.schemas.workload import WorkloadProfileCreate
from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
from cloud_recommender.services.inventory.multi_cloud_comparator import (
    MultiCloudComparatorService,
)


@pytest.mark.asyncio
async def test_gcp_inventory_hierarchy_and_resource_groups_rule() -> None:
    """Verify GCP hierarchy correctly models Org -> Folder -> Project and NEVER invents Resource Groups."""
    settings = Settings(offline_pricing_mode=True)
    svc = GcpInventoryService(settings=settings)

    analysis = await svc.analyze_project(project_id="smart-expense-gcp-prod")

    assert analysis.provider == CloudProvider.GCP
    assert analysis.scope_type == "gcp_project"
    assert analysis.scope_id == "smart-expense-gcp-prod"

    # Hierarchy verification
    node_types = [n.node_type for n in analysis.hierarchy_nodes]
    assert "gcp_organization" in node_types
    assert "gcp_folder" in node_types
    assert "gcp_project" in node_types
    assert "azure_resource_group" not in node_types

    # Ensure EVERY discovered GCP resource has resource_group=None and project_id populated!
    for r in analysis.resources:
        assert r.resource_group is None, (
            f"Resource {r.resource_name} incorrectly assigned an Azure resource group!"
        )
        assert r.project_id == "smart-expense-gcp-prod"
        assert r.provider == CloudProvider.GCP

    # Groups must be GCP service domains, not Azure resource groups
    for g in analysis.groups:
        assert g.group_type == "gcp_service_domain"
        assert g.total_monthly >= Decimal("0.00")


@pytest.mark.asyncio
async def test_multi_cloud_comparator_azure_vs_gcp() -> None:
    """Verify side-by-side comparative architecture and deterministic cost delta generation."""
    settings = Settings(offline_pricing_mode=True)
    comparator = MultiCloudComparatorService(settings=settings)

    request = MultiCloudComparisonRequest(
        workload_profile=WorkloadProfileCreate(
            name="Smart Expense Microservices",
            description="Expense management platform",
            category=WorkloadCategory.WEB_APP,
            target_traffic_rps=50,
            monthly_active_users=2500,
            primary_region="eastus",
        ),
        workload_assumptions=WorkloadAssumptions(
            customer_count=10000,
            monthly_active_users=2500,
            peak_rps=50.0,
            db_storage_gb=100.0,
            blob_storage_gb=250.0,
            ai_support_monthly_tokens=5000000,
            ha_required=True,
        ),
        azure_region="eastus",
        gcp_region="us-central1",
    )

    resp = await comparator.compare_azure_and_gcp(request)

    assert resp.azure_report.provider == CloudProvider.AZURE
    assert resp.gcp_report.provider == CloudProvider.GCP
    assert resp.azure_total_monthly > Decimal("0.00")
    assert resp.gcp_total_monthly > Decimal("0.00")

    # Verify deltas
    assert resp.monthly_delta_gcp_minus_azure == resp.gcp_total_monthly - resp.azure_total_monthly
    assert resp.annual_delta_gcp_minus_azure == (
        resp.gcp_report.cost_breakdown.total_annual - resp.azure_report.cost_breakdown.total_annual
    )
    assert resp.cheaper_provider in (CloudProvider.AZURE, CloudProvider.GCP, None)

    # Verify cross-cloud service mappings
    assert len(resp.service_mappings) == 8
    caps = [m.capability for m in resp.service_mappings]
    assert any("Edge Routing" in c for c in caps)
    assert any("WAF" in c for c in caps)
    assert any("Container Compute" in c for c in caps)
    assert any("PostgreSQL" in c for c in caps)
    assert any("AI Inference" in c for c in caps)

    # Verify comparison assumptions and trade-off summary
    assert len(resp.comparison_assumptions) > 0
    assert "AWS" in resp.comparison_assumptions[-1]  # Confirms AWS deferred note
    assert len(resp.trade_off_summary) > 50
