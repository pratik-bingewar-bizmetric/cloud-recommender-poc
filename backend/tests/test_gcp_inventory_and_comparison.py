"""Unit tests for GCP project inventory hierarchy and Azure vs. GCP multi-cloud comparator."""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.analysis import WorkloadAssumptions
from cloud_recommender.schemas.common import (
    CloudProvider,
    ServiceCategory,
    WorkloadCategory,
)
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


@pytest.mark.asyncio
async def test_gcp_unauthenticated_custom_project_raises_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify unauthenticated request for custom project returns 401 with required read-only IAM roles."""
    settings = Settings(offline_pricing_mode=True, gcp_access_token=None)
    svc = GcpInventoryService(settings=settings)
    monkeypatch.setattr(
        svc, "get_inventory_access_token", AsyncMock(return_value=(None, "unauthenticated"))
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.analyze_project(project_id="arbitrary-custom-proj-999")

    assert exc_info.value.status_code == 401
    assert "roles/browser" in exc_info.value.detail
    assert "roles/cloudasset.viewer" in exc_info.value.detail
    assert "smart-expense-gcp-prod" in exc_info.value.detail


@pytest.mark.asyncio
async def test_gcp_unauthenticated_reference_fixture_returns_mock_data_source() -> None:
    """Verify reference fixture is strictly labeled as mock_fixture when unauthenticated."""
    settings = Settings(offline_pricing_mode=True, gcp_access_token=None)
    svc = GcpInventoryService(settings=settings)

    analysis = await svc.analyze_project(project_id="smart-expense-gcp-prod")

    assert analysis.data_source == "mock_fixture"
    for r in analysis.resources:
        assert r.origin == "mock_fixture"
        assert r.resource_group is None
        assert r.project_id == "smart-expense-gcp-prod"


@pytest.mark.asyncio
async def test_gcp_live_hierarchy_discovery_handling() -> None:
    """Verify live hierarchy discovery handles 401 and 403 status codes correctly."""
    settings = Settings(offline_pricing_mode=True)
    svc = GcpInventoryService(settings=settings)

    # Test 401 Unauthorized from Cloud Resource Manager
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(401, json={"error": "unauthorized"})
        with pytest.raises(HTTPException) as exc_info:
            await svc._discover_live_hierarchy("test-proj", "fake-token")
        assert exc_info.value.status_code == 401

    # Test 403 Forbidden with required role notice
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(403, json={"error": "forbidden"})
        with pytest.raises(HTTPException) as exc_info:
            await svc._discover_live_hierarchy("test-proj", "fake-token")
        assert exc_info.value.status_code == 403
        assert "roles/browser" in exc_info.value.detail


@pytest.mark.asyncio
async def test_gcp_live_asset_discovery_mapping_and_failures() -> None:
    """Verify asset discovery correctly maps asset types to canonical IDs and enforces 403 permission details."""
    settings = Settings(offline_pricing_mode=True)
    svc = GcpInventoryService(settings=settings)

    # Test 403 Forbidden with roles/cloudasset.viewer detail
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(403, json={"error": "forbidden"})
        with pytest.raises(HTTPException) as exc_info:
            await svc._discover_live_assets("test-proj", "fake-token", "us-central1")
        assert exc_info.value.status_code == 403
        assert "roles/cloudasset.viewer" in exc_info.value.detail

    # Test mapping asset types
    assert (
        svc._map_asset_type_to_canonical("run.googleapis.com/Service", "api")[0] == "gcp-cloud-run"
    )
    assert (
        svc._map_asset_type_to_canonical("sqladmin.googleapis.com/Instance", "db")[0]
        == "gcp-cloud-sql-postgres"
    )
    assert (
        svc._map_asset_type_to_canonical("storage.googleapis.com/Bucket", "bkt")[0]
        == "gcp-cloud-storage"
    )
    assert (
        svc._map_asset_type_to_canonical("compute.googleapis.com/SecurityPolicy", "waf")[0]
        == "gcp-cloud-armor"
    )
    assert (
        svc._map_asset_type_to_canonical("compute.googleapis.com/GlobalForwardingRule", "lb")[0]
        == "gcp-cloud-cdn"
    )
    # Verification of API vs infrastructure vs configuration classification
    su_map = svc._map_asset_type_to_canonical(
        "serviceusage.googleapis.com/Service", "compute.googleapis.com"
    )
    assert su_map[0] == "gcp-service-usage"
    assert su_map[1] == ServiceCategory.INTEGRATION
    assert su_map[4] == "api_service"

    key_map = svc._map_asset_type_to_canonical("apikeys.googleapis.com/Key", "my-key")
    assert key_map[0] == "gcp-api-key"
    assert key_map[1] == ServiceCategory.SECURITY
    assert key_map[4] == "security_credential"

    proj_map = svc._map_asset_type_to_canonical(
        "cloudresourcemanager.googleapis.com/Project", "my-proj"
    )
    assert proj_map[0] == "gcp-project-metadata"
    assert proj_map[1] == ServiceCategory.INTEGRATION
    assert proj_map[4] == "configuration_metadata"

    disk_map = svc._map_asset_type_to_canonical("compute.googleapis.com/Disk", "disk-1")
    assert disk_map[0] == "gcp-compute-disk"
    assert disk_map[1] == ServiceCategory.STORAGE
    assert disk_map[4] == "infrastructure_resource"


@pytest.mark.asyncio
async def test_gcp_rejects_azure_uuid_project_id() -> None:
    """Verify passing an Azure Subscription UUID to GCP analyze_project is rejected with 400."""
    settings = Settings(offline_pricing_mode=True)
    svc = GcpInventoryService(settings=settings)

    with pytest.raises(HTTPException) as exc_info:
        await svc.analyze_project(project_id="f718c261-ab85-49fd-907e-99c022cc2aeb")

    assert exc_info.value.status_code == 400
    assert "Azure Subscription UUID" in exc_info.value.detail
    assert "f718c261-ab85-49fd-907e-99c022cc2aeb" in exc_info.value.detail


@pytest.mark.asyncio
async def test_gcp_token_economics_truthful_403_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that a 403 on GCP project returns unavailable_permission_required with 0 tokens."""
    from cloud_recommender.schemas.monitoring import MonitoringQueryRequest
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
    from cloud_recommender.services.monitoring.monitoring_service import (
        CentralizedMonitoringService,
    )

    settings = Settings(offline_pricing_mode=True)
    az_svc = AzureInventoryService(settings=settings)
    gcp_svc = GcpInventoryService(settings=settings)
    mon_svc = CentralizedMonitoringService(
        settings=settings, azure_service=az_svc, gcp_service=gcp_svc
    )

    # Simulate GCP analyze_project raising 403 Forbidden
    async def mock_analyze(*_args: Any, **_kwargs: Any) -> Any:
        raise HTTPException(
            status_code=403,
            detail="GCP Resource Manager API returned 403 Forbidden: Insufficient IAM permissions.",
        )

    monkeypatch.setattr(gcp_svc, "analyze_project", mock_analyze)

    req = MonitoringQueryRequest(
        provider=CloudProvider.GCP,
        scope_id="my-custom-prod-project",
        time_window="7d",
    )
    result = await mon_svc.get_token_economics(req)

    assert result.data_status == "unavailable_permission_required"
    assert result.total_tokens == 0
    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0
    assert result.estimated_cost_usd == Decimal("0.0000")
    assert "403 Forbidden" in result.status_message
    assert len(result.diagnostic_setup_guide) > 0
