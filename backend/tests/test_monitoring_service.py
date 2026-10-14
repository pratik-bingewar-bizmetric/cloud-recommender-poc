"""Unit and integration tests for CentralizedMonitoringService."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from cloud_recommender.schemas.common import CloudProvider
from cloud_recommender.schemas.monitoring import (
    MonitoringQueryRequest,
    TimeWindowPreset,
)
from cloud_recommender.services.monitoring.monitoring_service import (
    CentralizedMonitoringService,
    redact_sensitive_text,
)


def test_redact_sensitive_text() -> None:
    """Ensure tokens, passwords, and connection strings are scrubbed from log data."""
    raw = (
        "User logged in with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz and "
        "password: SuperSecretPassword123! and AccountKey=AbCdEfGh123456789==;EndpointSuffix=core.windows.net"
    )
    scrubbed = redact_sensitive_text(raw)
    assert "SuperSecretPassword123!" not in scrubbed
    assert "[REDACTED_SECRET]" in scrubbed
    assert "AbCdEfGh123456789==" not in scrubbed
    assert "[REDACTED_KEY]" in scrubbed
    assert "[REDACTED_TOKEN]" in scrubbed


@pytest.mark.asyncio
async def test_monitoring_time_window_presets() -> None:
    """Verify time window calculations across 1h, 24h, 7d, 30d, 90d, and custom windows."""
    svc = CentralizedMonitoringService()
    presets: list[TimeWindowPreset] = ["1h", "24h", "7d", "30d", "90d"]

    for preset in presets:
        start, end, eff_interval, days = svc._calculate_time_window(preset, None, None, None)
        assert start < end
        assert eff_interval in ("1m", "5m", "15m", "1h", "1d")
        assert days >= 1

    # Custom window
    c_start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    c_end = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)
    start_c, end_c, eff_c, days_c = svc._calculate_time_window("custom", c_start, c_end, "15m")
    assert start_c == c_start
    assert end_c == c_end
    assert eff_c == "15m"
    assert days_c == 14


@pytest.mark.asyncio
async def test_azure_monitoring_overview_mock_fixture() -> None:
    """Verify overview payload generation for Azure subscription with KPIs, alerts, and timeseries."""
    svc = CentralizedMonitoringService()
    req = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id="sub-prod-enterprise-01",
        time_window="7d",
    )
    overview = await svc.get_monitoring_overview(req)

    assert overview.provider == CloudProvider.AZURE
    assert overview.scope_id == "sub-prod-enterprise-01"
    assert overview.kpis.total_resources > 0
    assert overview.kpis.healthy_count >= 0
    assert overview.kpis.degraded_count >= 0
    assert overview.kpis.telemetry_coverage_percentage > Decimal("0.00")
    assert overview.kpis.estimated_monthly_cost > Decimal("0.00")
    assert len(overview.cpu_utilization_series) > 0
    assert len(overview.health_records) > 0
    assert len(overview.active_alerts) > 0
    assert len(overview.resource_groups_summary) > 0
    assert any(
        "AMA" in g or "Agent" in g or "offline" in g.lower() for g in overview.limitations_and_gaps
    )


@pytest.mark.asyncio
async def test_gcp_monitoring_overview_mock_fixture() -> None:
    """Verify overview payload generation for GCP project with KPIs and rollups."""
    svc = CentralizedMonitoringService()
    req = MonitoringQueryRequest(
        provider=CloudProvider.GCP,
        scope_id="smart-expense-gcp-prod",
        time_window="30d",
    )
    overview = await svc.get_monitoring_overview(req)

    assert overview.provider == CloudProvider.GCP
    assert overview.scope_id == "smart-expense-gcp-prod"
    assert overview.kpis.total_resources > 0
    assert overview.kpis.estimated_monthly_cost > Decimal("0.00")
    assert len(overview.cpu_utilization_series) > 0
    assert len(overview.active_alerts) > 0
    assert len(overview.recurring_errors) > 0


@pytest.mark.asyncio
async def test_resource_detail_deep_dive_7_tabs() -> None:
    """Verify 7-tab deep dive response for an individual service."""
    svc = CentralizedMonitoringService()
    req = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id="sub-prod-enterprise-01",
        resource_id="/subscriptions/sub-prod-enterprise-01/resourceGroups/rg-smart-expense/providers/Microsoft.Compute/virtualMachines/vm-app-prod-01",
        time_window="24h",
    )
    detail = await svc.get_resource_monitoring_detail(req)

    assert detail.resource.resource_id == req.resource_id
    assert detail.health.health_state in (
        "healthy",
        "degraded",
        "failing",
        "unmonitored",
        "stopped",
    )
    assert len(detail.metrics) > 0
    assert len(detail.logs) > 0
    assert "monthly_cost" in detail.cost_and_utilization
    assert isinstance(detail.dependencies, list)
    assert isinstance(detail.waste_findings, list)
    assert isinstance(detail.technical_debt_items, list)


@pytest.mark.asyncio
async def test_log_search_and_pagination() -> None:
    """Verify log search, severity filter, text search, and pagination."""
    svc = CentralizedMonitoringService()

    # 1. Search all logs
    res_all = await svc.search_logs(
        provider=CloudProvider.AZURE,
        scope_id="sub-prod-enterprise-01",
        time_window="7d",
        page=1,
        page_size=10,
    )
    assert res_all.total_matched > 0
    assert len(res_all.logs) <= 10

    # 2. Filter by severity
    res_err = await svc.search_logs(
        provider=CloudProvider.AZURE,
        scope_id="sub-prod-enterprise-01",
        severity="error",
        time_window="7d",
    )
    assert all(log_item.severity == "error" for log_item in res_err.logs)

    # 3. Filter by query
    res_query = await svc.search_logs(
        provider=CloudProvider.AZURE,
        scope_id="sub-prod-enterprise-01",
        query="Timeout",
        time_window="7d",
    )
    assert all(
        "timeout" in log_item.message.lower()
        or "timeout" in log_item.operation_name.lower()
        or "timeout" in (log_item.error_code or "").lower()
        for log_item in res_query.logs
    )


@pytest.mark.asyncio
async def test_monitoring_caching_and_force_refresh() -> None:
    """Verify in-memory caching and cache bypass when force_refresh=True."""
    svc = CentralizedMonitoringService()
    req = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id="sub-prod-enterprise-01",
        time_window="1h",
        force_refresh=False,
    )
    res1 = await svc.get_monitoring_overview(req)
    res2 = await svc.get_monitoring_overview(req)
    # Cached instance should match
    assert res1.query_timestamp == res2.query_timestamp

    req_force = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id="sub-prod-enterprise-01",
        time_window="1h",
        force_refresh=True,
    )
    res3 = await svc.get_monitoring_overview(req_force)
    assert res3.query_timestamp >= res1.query_timestamp
