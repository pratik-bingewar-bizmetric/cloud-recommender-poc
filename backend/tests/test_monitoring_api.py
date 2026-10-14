"""Integration tests for centralized monitoring API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from cloud_recommender.main import app


@pytest.mark.asyncio
async def test_api_monitoring_sources() -> None:
    """Verify monitoring data sources status endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/monitoring/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert "azure_monitor" in data
        assert "gcp_monitoring" in data
        assert "Read-Only" in data["policy"]


@pytest.mark.asyncio
async def test_api_monitoring_overview() -> None:
    """Verify overview endpoint returns validated KPIs and timeseries."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "provider": "azure",
            "scope_id": "sub-prod-enterprise-01",
            "time_window": "7d",
            "interval": "1h",
            "force_refresh": False,
        }
        resp = await ac.post("/api/v1/monitoring/overview", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "azure"
        assert data["scope_id"] == "sub-prod-enterprise-01"
        assert "kpis" in data
        assert data["kpis"]["total_resources"] > 0
        assert "cpu_utilization_series" in data
        assert "active_alerts" in data
        assert "recent_failures" in data


@pytest.mark.asyncio
async def test_api_monitoring_resource_detail() -> None:
    """Verify individual resource 7-tab deep dive endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "provider": "azure",
            "scope_id": "sub-prod-enterprise-01",
            "resource_id": "/subscriptions/sub-prod-enterprise-01/resourceGroups/rg-smart-expense/providers/Microsoft.Compute/virtualMachines/vm-app-prod-01",
            "time_window": "24h",
        }
        resp = await ac.post("/api/v1/monitoring/resource", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["resource"]["resource_name"] == "vm-app-prod-01"
        assert "health" in data
        assert "metrics" in data
        assert "logs" in data
        assert "cost_and_utilization" in data
        assert "waste_findings" in data
        assert "technical_debt_items" in data


@pytest.mark.asyncio
async def test_api_monitoring_logs_search() -> None:
    """Verify logs search endpoint with filtering and secret scrubbing."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "provider": "azure",
            "scope_id": "sub-prod-enterprise-01",
            "severity": "error",
            "time_window": "7d",
            "page": 1,
            "page_size": 25,
        }
        resp = await ac.post("/api/v1/monitoring/logs", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_matched" in data
        assert "logs" in data
        assert all(item["severity"] == "error" for item in data["logs"])
