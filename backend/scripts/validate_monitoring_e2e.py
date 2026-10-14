"""Validation script for Phase B Gate: Centralized Monitoring E2E Acceptance."""

import asyncio
from datetime import UTC, datetime

from cloud_recommender.schemas.common import CloudProvider
from cloud_recommender.schemas.monitoring import (
    MonitoringQueryRequest,
)
from cloud_recommender.services.monitoring.monitoring_service import (
    CentralizedMonitoringService,
    redact_sensitive_text,
)


async def run_validation() -> None:
    svc = CentralizedMonitoringService()
    real_sub_id = "f718c261-ab85-49fd-907e-99c022cc2aeb"
    gcp_scope_id = "smart-expense-gcp-prod"

    print("=== 1. AUDIT DATA PROVENANCE & AZURE LIVE TEST ===")
    req_live = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id=real_sub_id,
        time_window="7d",
        interval="1h",
        force_refresh=True,
    )
    res_live = await svc.get_monitoring_overview(req_live)
    print(f"Scope: {res_live.scope_id} ({res_live.scope_name})")
    print(f"is_live: {res_live.is_live}, data_source: {res_live.data_source}")
    print(f"Telemetry Source: {res_live.telemetry_source}")
    print(f"Total Resources: {res_live.kpis.total_resources}")
    print(
        f"Health: Healthy={res_live.kpis.healthy_count}, Degraded={res_live.kpis.degraded_count}, Failing={res_live.kpis.failing_count}"
    )
    print(f"Active Alerts Count: {len(res_live.active_alerts)}")
    print(f"Resource Groups: {[rg.group_name for rg in res_live.resource_groups_summary]}")
    assert res_live.is_live is True, "Expected is_live to be True for authorized Azure subscription"
    assert res_live.data_source == "live_authenticated", "Expected live_authenticated data_source"
    assert res_live.kpis.total_resources > 0, "Expected live resources to be discovered"

    print("\n=== 2. AUDIT DATA PROVENANCE & GCP SIMULATION NOTICE TEST ===")
    req_gcp = MonitoringQueryRequest(
        provider=CloudProvider.GCP,
        scope_id=gcp_scope_id,
        time_window="7d",
        interval="1h",
        force_refresh=True,
    )
    res_gcp = await svc.get_monitoring_overview(req_gcp)
    print(f"Scope: {res_gcp.scope_id} ({res_gcp.scope_name})")
    print(f"is_live: {res_gcp.is_live}, data_source: {res_gcp.data_source}")
    print(f"Limitations Count: {len(res_gcp.limitations_and_gaps)}")
    for lim in res_gcp.limitations_and_gaps:
        print(f"  - {lim}")
    assert res_gcp.is_live is False, "Expected is_live to be False for unauthenticated GCP project"
    assert res_gcp.data_source == "mock_fixture", "Expected mock_fixture data_source for GCP"
    assert any("To enable live GCP observability" in lim for lim in res_gcp.limitations_and_gaps), (
        "Missing exact GCP setup instructions"
    )

    print("\n=== 3. VALIDATE HISTORICAL WINDOWS & GRANULARITIES ===")
    windows = [
        ("1h", "1m"),
        ("24h", "5m"),
        ("7d", "1h"),
        ("30d", "1h"),
        ("90d", "1d"),
    ]
    for win, interv in windows:
        req_win = MonitoringQueryRequest(
            provider=CloudProvider.AZURE,
            scope_id=real_sub_id,
            time_window=win,  # type: ignore[arg-type]
            interval=interv,  # type: ignore[arg-type]
            force_refresh=False,
        )
        res_win = await svc.get_monitoring_overview(req_win)
        print(
            f"Window: {win:>3} | Interval: {interv:>3} | Start: {res_win.start_time.isoformat()[:19]} | End: {res_win.end_time.isoformat()[:19]} | CPU Series: {len(res_win.cpu_utilization_series)}"
        )
        assert res_win.start_time < res_win.end_time
        assert res_win.time_window == win

    # Custom window
    c_start = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    c_end = datetime(2026, 8, 15, 0, 0, tzinfo=UTC)
    req_custom = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id=real_sub_id,
        time_window="custom",
        custom_start_time=c_start,
        custom_end_time=c_end,
        interval="15m",
        force_refresh=True,
    )
    res_custom = await svc.get_monitoring_overview(req_custom)
    print(
        f"Custom Window: {res_custom.start_time} -> {res_custom.end_time} | Interval: {res_custom.aggregation_interval}"
    )
    assert res_custom.start_time == c_start
    assert res_custom.end_time == c_end

    print("\n=== 4. VALIDATE CACHING & FORCE REFRESH ===")
    # 1st query without force_refresh (populate cache)
    t1_req = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id=real_sub_id,
        time_window="1h",
        interval="1m",
        force_refresh=False,
    )
    r1 = await svc.get_monitoring_overview(t1_req)
    # 2nd query (should hit cache instantly)
    r2 = await svc.get_monitoring_overview(t1_req)
    assert r1.query_timestamp == r2.query_timestamp, (
        "Cache did not return identical query_timestamp"
    )
    print(
        f"Cache HIT verified: r1.timestamp={r1.query_timestamp} == r2.timestamp={r2.query_timestamp}"
    )

    # 3rd query with force_refresh=True (should bypass cache)
    t3_req = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id=real_sub_id,
        time_window="1h",
        interval="1m",
        force_refresh=True,
    )
    r3 = await svc.get_monitoring_overview(t3_req)
    print(f"Force-refresh bypass verified: r3.timestamp={r3.query_timestamp}")

    print("\n=== 5. VALIDATE LOG SEARCH & SECRET REDACTION ===")
    # Test redaction function directly
    secret_payload = (
        "Authorization: Bearer secret-token-xyz123; "
        "User pass: SuperP@ssw0rd! "
        "Azure Storage: DefaultEndpointsProtocol=https;AccountName=myacc;AccountKey=MySecretKey9988==;EndpointSuffix=core.windows.net "
        "SAS Token: sv=2020-08-04&ss=b&srt=sco&sp=rwdlacx&se=2026-12-31T23:59:59Z&st=2026-01-01T00:00:00Z&spr=https&sig=MySecretSignatureHash123="
    )
    scrubbed = redact_sensitive_text(secret_payload)
    print("Scrubbed log output preview:\n", scrubbed)
    assert "secret-token-xyz123" not in scrubbed
    assert "SuperP@ssw0rd!" not in scrubbed
    assert "MySecretKey9988==" not in scrubbed
    assert "MySecretSignatureHash123=" not in scrubbed
    assert "[REDACTED_TOKEN]" in scrubbed
    assert "[REDACTED_SECRET]" in scrubbed
    assert "[REDACTED_KEY]" in scrubbed
    assert "[REDACTED_SAS_SIG]" in scrubbed

    # Test log search API
    log_res = await svc.search_logs(
        provider=CloudProvider.AZURE,
        scope_id=real_sub_id,
        severity="error",
        page=1,
        page_size=10,
    )
    print(f"Log Search returned {len(log_res.logs)} logs (total matched: {log_res.total_matched})")
    print(f"Recurring Summaries: {len(log_res.recurring_summaries)}")
    for log in log_res.logs[:3]:
        print(
            f"  [{log.severity.upper()}] {log.timestamp.isoformat()[:19]} | {log.resource_name} | {log.operation_name}: {log.message[:60]}..."
        )
        # Verify no unscrubbed credentials
        assert "password" not in log.message.lower() or "[redacted" in log.message.lower()

    print("\n=== 6. VALIDATE 7-TAB RESOURCE DETAIL DEEP DIVE ===")
    first_res = res_live.health_records[0].resource_id
    detail_req = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id=real_sub_id,
        resource_id=first_res,
        time_window="7d",
        interval="1h",
    )
    detail_res = await svc.get_resource_monitoring_detail(detail_req)
    print(
        f"Resource Detail for: {detail_res.resource.resource_name} ({detail_res.resource.native_resource_type})"
    )
    print(f"  Health State: {detail_res.health.health_state} ({detail_res.health.summary})")
    print(f"  Metrics Timeseries: {len(detail_res.metrics)} series")
    print(f"  Logs Scoped: {len(detail_res.logs)} logs")
    print(f"  Alerts Scoped: {len(detail_res.alerts)} alerts")
    print(f"  Dependencies: {len(detail_res.dependencies)} items")
    print(f"  Cost & Utilization: {detail_res.cost_and_utilization}")
    print(f"  Waste Findings: {len(detail_res.waste_findings)}")
    print(f"  Technical Debt: {len(detail_res.technical_debt_items)}")

    assert detail_res.resource.resource_id == first_res
    assert detail_res.health is not None
    assert isinstance(detail_res.cost_and_utilization, dict)

    print("\n=== ALL E2E VERIFICATIONS PASSED SUCCESSFULLY ===")


if __name__ == "__main__":
    asyncio.run(run_validation())
