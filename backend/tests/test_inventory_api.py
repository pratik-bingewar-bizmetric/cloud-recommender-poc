"""API integration tests for subscription/project-level inventory and multi-cloud comparison routes."""

import pytest
from httpx import ASGITransport, AsyncClient

from cloud_recommender.main import app


@pytest.mark.asyncio
async def test_api_providers_status() -> None:
    """Verify GET /api/v1/inventory/providers/status returns statuses for Azure and GCP."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/inventory/providers/status")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        providers = [item["provider"] for item in data]
        assert "azure" in providers
        assert "gcp" in providers


@pytest.mark.asyncio
async def test_api_azure_subscriptions_and_analysis() -> None:
    """Verify Azure subscriptions listing and subscription analysis endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List Subscriptions
        sub_resp = await client.get("/api/v1/inventory/azure/subscriptions")
        assert sub_resp.status_code == 200
        subs = sub_resp.json()
        assert len(subs) >= 1
        sub_id = subs[0]["scope_id"]

        # 2. Analyze Subscription
        analyze_payload = {
            "scope_id": sub_id,
            "workload_assumptions": {
                "customer_count": 51,
                "monthly_active_users": 30,
            },
            "safety_buffer_percentage": "10.00",
        }
        resp = await client.post("/api/v1/inventory/azure/analyze", json=analyze_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "azure"
        assert data["scope_id"] == sub_id
        assert data["scope_type"] == "azure_subscription"
        assert data["cost_breakdown"]["total_monthly"] is not None
        assert "flowchart TD" in data["architecture_mermaid"]
        assert len(data["groups"]) >= 1


@pytest.mark.asyncio
async def test_api_gcp_projects_and_analysis() -> None:
    """Verify GCP projects listing and project analysis endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List Projects
        proj_resp = await client.get("/api/v1/inventory/gcp/projects")
        assert proj_resp.status_code == 200
        projects = proj_resp.json()
        assert len(projects) >= 1
        project_id = projects[0]["scope_id"]

        # 2. Analyze Project
        analyze_payload = {
            "scope_id": project_id,
            "workload_assumptions": {
                "customer_count": 10000,
                "target_region": "us-central1",
            },
            "safety_buffer_percentage": "15.00",
        }
        resp = await client.post("/api/v1/inventory/gcp/analyze", json=analyze_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "gcp"
        assert data["scope_type"] == "gcp_project"
        assert data["cost_breakdown"]["total_monthly"] is not None
        assert "flowchart TD" in data["architecture_mermaid"]
        assert len(data["groups"]) >= 1
        # Assert GCP resources never have an Azure resource group
        for r in data["resources"]:
            assert r["resource_group"] is None
            assert r["project_id"] == project_id


@pytest.mark.asyncio
async def test_api_multi_cloud_compare() -> None:
    """Verify POST /api/v1/inventory/compare generates side-by-side Azure vs. GCP report."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        compare_payload = {
            "workload_profile": {
                "name": "E-Commerce Microservices",
                "description": "Multi-tenant e-commerce platform",
                "category": "web_app",
                "target_traffic_rps": 20,
                "monthly_active_users": 1000,
                "primary_region": "eastus",
                "cost_buffer_percentage": "15.00",
            },
            "workload_assumptions": {
                "customer_count": 51,
                "monthly_active_users": 1000,
                "peak_rps": 20.0,
                "db_storage_gb": 50.0,
                "blob_storage_gb": 100.0,
                "ai_support_monthly_tokens": 1000000,
                "ha_required": True,
            },
            "azure_region": "eastus",
            "gcp_region": "us-central1",
        }
        resp = await client.post("/api/v1/inventory/compare", json=compare_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["azure_report"]["provider"] == "azure"
        assert data["gcp_report"]["provider"] == "gcp"
        assert float(data["azure_total_monthly"]) > 0.0
        assert float(data["gcp_total_monthly"]) > 0.0
        assert len(data["service_mappings"]) == 8
        assert data["trade_off_summary"] is not None
