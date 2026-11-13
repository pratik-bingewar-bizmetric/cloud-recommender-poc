"""Tests for FinOps Command Center Analytics Service and FastAPI endpoints.

Verifies all 15 modules, KPI certifications, CSV exports, scenario simulations,
and decision action mutations.
"""

import pytest

from cloud_recommender.api.routes.finops import (
    export_cost_explorer_csv,
    get_ai_economics,
    get_anomaly_detection,
    get_canonical_kpi,
    get_compute_warehouses,
    get_cost_allocation,
    get_cost_explorer,
    get_data_storage,
    get_finops_ai_analysis,
    get_forecast_budgets,
    get_governance_policies,
    get_network_cloud,
    get_optimization_advisor,
    get_overview,
    get_reports_audit,
    get_settings_integrations,
    get_showback_chargeback,
    get_workload_economics,
    record_decision_action,
    simulate_scenario,
    update_finops_anomaly_status,
)
from cloud_recommender.schemas.databricks import DatabricksResourceState, LiveQueryHistoryItem
from cloud_recommender.schemas.finops import (
    AnomalyStatusUpdateRequest,
    KpiStatus,
    RecommendationActionRequest,
    ScenarioSimulationRequest,
)
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService
from tests.fixtures.billing_baseline import add_synthetic_history, baseline_expectations
from tests.fixtures.live_inventory import make_analytics_service, stub_query_history


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return make_analytics_service(with_billing=True)


def test_executive_overview_contracts(service: FinOpsAnalyticsService) -> None:
    exp = baseline_expectations()
    data = service.get_executive_overview(connection_id="databricks-azure-dev")
    for key in (
        "total_spend",
        "databricks_spend",
        "ai_spend",
        "dbu_consumption",
        "savings_opportunity",
        "forecast_spend",
        "anomalies",
    ):
        assert key in data.kpis

    assert data.kpis["total_spend"].value == pytest.approx(exp["total_cost"])
    assert data.kpis["total_spend"].status == KpiStatus.CALCULATED
    assert data.kpis["ai_spend"].value == pytest.approx(exp["by_product"]["MODEL_SERVING"])
    assert data.kpis["dbu_consumption"].value == exp["total_dbu"]
    assert data.kpis["savings_opportunity"].status == KpiStatus.UNAVAILABLE
    assert data.kpis["forecast_spend"].status == KpiStatus.INSUFFICIENT_HISTORY
    assert data.kpis["anomalies"].status == KpiStatus.INSUFFICIENT_HISTORY

    assert len(data.spend_trend) == 4  # one point per ingested usage day
    assert len(data.spend_composition) == 5
    assert len(data.top_cost_drivers) >= 3
    assert len(data.decisions_requiring_attention) >= 1
    assert data.global_filters["live_inventory"]["warehouses"] == 1
    assert data.provenance["spend"].classification == KpiStatus.CALCULATED


def test_dbu_consumption_and_token_isolation(service: FinOpsAnalyticsService) -> None:
    exp = baseline_expectations()
    dbu_kpi = service.get_executive_overview().kpis["dbu_consumption"]
    assert dbu_kpi.unit == "DBU"
    assert dbu_kpi.value == exp["total_dbu"]
    assert dbu_kpi.currency is None

    ai = service.get_ai_economics()
    assert "input_tokens" in ai.kpis
    assert ai.kpis["input_tokens"].unit.lower() == "tokens"
    assert ai.kpis["input_tokens"].value is None


def test_scope_enforcement_and_mismatch_rejection(service: FinOpsAnalyticsService) -> None:
    # Valid workspace passes
    data = service.get_executive_overview(workspace_id="642006393507276")
    assert data.global_filters["workspace_id"] == "642006393507276"

    # Mismatched/unauthorized workspace raises ValueError
    with pytest.raises(ValueError, match="Scope validation failed"):
        service.get_executive_overview(workspace_id="9999999999999999")

    with pytest.raises(ValueError, match="Scope validation failed"):
        service.get_cost_explorer(workspace_id="unauthorized-aws-workspace")


def test_child_resource_filtering_warehouse_and_cluster(
    service: FinOpsAnalyticsService,
) -> None:
    exp = baseline_expectations()
    wh_data = service.get_executive_overview(
        workspace_id="642006393507276", resource_id="05ed10a52697a344", resource_type="warehouse"
    )
    assert wh_data.kpis["total_spend"].value == pytest.approx(
        exp["by_resource"]["05ed10a52697a344"]
    )
    assert wh_data.kpis["dbu_consumption"].value == exp["by_product_dbu"]["SQL"]
    assert len(wh_data.top_cost_drivers) == 1
    assert wh_data.top_cost_drivers[0].driver == "warehouse: 05ed10a52697a344"

    cl_data = service.get_executive_overview(
        workspace_id="642006393507276", resource_id="1102-081455-7t3bqp3v", resource_type="cluster"
    )
    assert cl_data.kpis["total_spend"].value == pytest.approx(
        exp["by_resource"]["1102-081455-7t3bqp3v"]
    )
    assert cl_data.kpis["dbu_consumption"].value == exp["by_product_dbu"]["ALL_PURPOSE"]
    assert cl_data.top_cost_drivers[0].driver == "cluster: 1102-081455-7t3bqp3v"

    # Cluster name alone cannot independently authorize attribution
    cl_name_data = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="adf-deaccelator-compute",
        resource_type="cluster",
    )
    assert cl_name_data.kpis["total_spend"].status == KpiStatus.NO_DATA
    assert cl_name_data.kpis["total_spend"].value is None
    assert cl_name_data.kpis["total_spend"].formatted_value == "-"


def test_unattributed_cost_preservation_for_apps(service: FinOpsAnalyticsService) -> None:
    exp = baseline_expectations()
    app_data = service.get_executive_overview(
        workspace_id="642006393507276", resource_id="cement-demand-forecasting", resource_type="app"
    )
    assert app_data.kpis["total_spend"].value == pytest.approx(
        exp["by_resource"]["cement-demand-forecasting"]
    )
    assert len(app_data.top_cost_drivers) == 1

    purged_app = service.get_executive_overview(
        workspace_id="642006393507276", resource_id="databricks-cost-monitor", resource_type="app"
    )
    assert purged_app.kpis["total_spend"].value is None
    assert purged_app.kpis["total_spend"].formatted_value == "-"
    assert purged_app.kpis["total_spend"].status.value == "NO_DATA"


def test_query_history_retrieval_and_filtering(service: FinOpsAnalyticsService) -> None:
    import asyncio

    items = [
        LiveQueryHistoryItem(
            query_id="q-1",
            status="FINISHED",
            warehouse_id="05ed10a52697a344",
            statement_type="SELECT",
            start_time="2026-11-04T10:00:00+00:00",
            end_time="2026-11-04T10:00:02+00:00",
            duration_ms=1500.0,
            rows_produced=7,
            read_bytes=2048,
            executed_by_masked="pr***@example.com",
            sql_summary="SELECT 1",
        ),
        LiveQueryHistoryItem(
            query_id="q-2",
            status="FAILED",
            warehouse_id="05ed10a52697a344",
            start_time="2026-11-04T11:00:00+00:00",
            duration_ms=70000.0,
            executed_by_masked="zz***@example.com",
            sql_summary="SELECT bad",
            error_message="boom",
        ),
    ]
    calls = stub_query_history(
        service,
        items,
        state=DatabricksResourceState.LIVE,
        has_next_page=True,
        next_page_token="tok-2",
    )
    history = asyncio.run(
        service.get_query_history(
            warehouse_id="05ed10a52697a344",
            status="FINISHED",
            limit=25,
            page_token="tok-1",
            start_time_ms=1_000,
            end_time_ms=2_000,
        )
    )
    # Filters, date range and pagination token are passed to the live API unchanged
    assert calls[0]["warehouse_id"] == "05ed10a52697a344"
    assert calls[0]["status_filter"] == "FINISHED"
    assert calls[0]["max_results"] == 25
    assert calls[0]["page_token"] == "tok-1"
    assert (calls[0]["start_time_ms"], calls[0]["end_time_ms"]) == (1_000, 2_000)

    assert history.total_count == 2 and history.has_next_page and history.next_page_token == "tok-2"
    assert history.provenance is not None and history.provenance.classification == KpiStatus.LIVE
    q0 = history.records[0]
    assert q0.warehouse_name == "Serverless Starter Warehouse"
    assert q0.duration_formatted == "1.50s" and q0.rows_produced == 7 and q0.bytes_written is None
    assert q0.cost_correlation_dbu is None  # never invented
    assert history.records[1].error_message == "boom"
    assert [b["count"] for b in history.duration_histogram] == [0, 1, 0, 0, 1]
    assert {s["status"] for s in history.status_distribution} == {"FINISHED", "FAILED"}

    only_zz = asyncio.run(service.get_query_history(user="zz"))
    assert [r.query_id for r in only_zz.records] == ["q-2"]


def test_system_tables_explorer_and_stopped_warehouse_state(
    service: FinOpsAnalyticsService,
) -> None:
    from datetime import UTC, datetime

    from cloud_recommender.schemas.databricks import (
        CategoryDiscoveryStatus,
        LiveSystemTableItem,
        SystemTablesMetadataResponse,
        UnityCatalogColumnItem,
    )

    def tbl(schema: str, name: str, grant: bool | None) -> LiveSystemTableItem:
        return LiveSystemTableItem(
            schema_name=schema,
            table_name=name,
            full_name=f"system.{schema}.{name}",
            columns_count=1,
            columns=[UnityCatalogColumnItem(name="c")],
            schema_discovered=True,
            table_discovered=True,
            select_grant_verified=grant,
        )

    service.workspace_service._system_tables_cache["databricks-azure-dev"] = (
        SystemTablesMetadataResponse(
            connection_id="databricks-azure-dev",
            workspace_id="642006393507276",
            workspace_url="https://example.invalid",
            status=CategoryDiscoveryStatus.AVAILABLE,
            discovery_state=DatabricksResourceState.LIVE,
            retrieved_at=datetime.now(UTC),
            tables=[tbl("billing", "usage", None), tbl("compute", "clusters", False)],
        )
    )
    sys_tables = service.get_system_tables(workspace_id="642006393507276")
    assert sys_tables.catalog_status == "METADATA_DISCOVERED"
    assert sys_tables.warehouse_state == "STOPPED"
    by_name = {t.table_name: t for t in sys_tables.tables}
    assert by_name["system.billing.usage"].status == "STOPPED_WAREHOUSE"
    assert by_name["system.compute.clusters"].status == "PERMISSION_DENIED"
    # Metadata only: no rows, counts or sample records are ever fabricated
    assert all(t.sample_records == [] and t.row_count is None for t in sys_tables.tables)
    assert "no SQL executed" in by_name["system.billing.usage"].notes


def test_cost_explorer_and_csv_export(service: FinOpsAnalyticsService) -> None:
    data = service.get_cost_explorer()
    assert "gross_consumption" in data.kpis
    assert len(data.billing_ledger) > 0
    # owner_tag only ever comes from real billing tags (Owner/Team); never invented
    assert {r.owner_tag for r in data.billing_ledger} == {
        "Analytics",
        "DataPlatform",
        "SupplyChain",
        "AI-Eng",
        "Research",
        "Search",
    }

    csv_out = service.export_cost_ledger_csv()
    assert "Product,SKU,Workspace" in csv_out
    assert "SERVERLESS_SQL_COMPUTE" in csv_out
    assert "adb-642006393507276" in csv_out

    blocked = make_analytics_service(with_billing=False)
    assert blocked.get_cost_explorer().billing_ledger == []
    assert blocked.export_cost_ledger_csv().count("\n") == 1  # header only, no fabricated rows


def test_compute_warehouses_and_heatmap(service: FinOpsAnalyticsService) -> None:
    exp = baseline_expectations()
    data = service.get_compute_warehouses()
    assert [c.cluster_id for c in data.clusters] == ["1102-081455-7t3bqp3v"]
    cluster = data.clusters[0]
    assert cluster.state == "TERMINATED" and cluster.node_profile.startswith("Standard_D3_v2")
    assert cluster.runtime_hrs is None and "-" in cluster.cpu_utilization
    assert cluster.cost_mtd == pytest.approx(exp["by_resource"]["1102-081455-7t3bqp3v"])
    assert cluster.finding == "No auto-termination configured"

    wh = data.warehouses[0]
    assert (wh.warehouse_id, wh.state, wh.auto_stop_mins, wh.size) == (
        "05ed10a52697a344",
        "STOPPED",
        15,
        "2X-Small",
    )
    assert wh.avg_utilization == "-" and wh.queue_p95 == "-"
    assert data.heatmap_utilization == []  # no utilization telemetry source
    assert data.kpis["idle_capacity"].status == KpiStatus.BLOCKED_PENDING_APPROVAL
    assert data.kpis["active_compute"].formatted_value == "0 of 2 running"
    assert data.jobs == []  # confirmed zero jobs


def test_ai_economics_endpoints(service: FinOpsAnalyticsService) -> None:
    data = service.get_ai_economics()
    assert "ai_spend" in data.kpis and "input_tokens" in data.kpis
    assert [e.endpoint_name for e in data.serving_endpoints] == ["databricks-claude-fable-5"]
    ep = data.serving_endpoints[0]
    assert ep.model == "claude" and ep.availability == "READY"
    assert ep.requests_per_day == "-" and ep.p95_latency == "-"
    assert data.genie_scorecard == [] and data.agents == [] and data.model_economics == []
    assert data.provenance["usage"].classification == KpiStatus.BLOCKED_PENDING_APPROVAL


def test_data_storage_catalogs(service: FinOpsAnalyticsService) -> None:
    data = service.get_data_storage()
    assert [t.catalog_schema_table for t in data.tables] == ["deaccelerator"]
    assert data.tables[0].size == "-" and data.tables[0].monthly_cost is None
    assert data.storage_tiers == [] and data.lifecycle_opportunities == []
    assert data.kpis["total_stored_data"].status == KpiStatus.BLOCKED_PENDING_APPROVAL
    assert data.kpis["total_stored_data"].value is None
    assert data.kpis["storage_spend"].status == KpiStatus.UNAVAILABLE


def test_scenario_simulator(service: FinOpsAnalyticsService) -> None:
    from cloud_recommender.schemas.finops import ScenarioSimulationRequest

    req = ScenarioSimulationRequest(compute_save_pct=20.0, token_save_pct=30.0, growth_pct=0.0)
    # 4 days of history: no baseline, so no scenario is invented
    thin = service.simulate_forecast_scenario(req)
    assert thin.status == KpiStatus.INSUFFICIENT_HISTORY
    assert thin.adjusted_spend is None and thin.baseline_spend is None

    # 20 days x $110/day: forecast = 2,200 MTD + 10 remaining days x 110 = 3,300
    svc = make_analytics_service(with_billing=False)
    add_synthetic_history(svc.billing_service, days=20)
    res = svc.simulate_forecast_scenario(req)
    assert res.status == KpiStatus.ESTIMATED
    assert res.baseline_spend == pytest.approx(3300.0)
    assert res.adjusted_spend == pytest.approx(3300.0 * 0.8)  # all spend is compute (no AI rows)
    assert res.savings_vs_baseline == pytest.approx(660.0) and res.is_favorable is True


def test_decision_action_mutation_and_audit(service: FinOpsAnalyticsService) -> None:
    assert service.get_reports_audit().audit_events == []  # no seeded history
    updated = service.record_decision_action(
        "rec-wh-autostop-05ed10a52697a344", "Approved", notes="Approved for test"
    )
    assert updated.status == "Approved"
    # Approval is a workflow state only: no savings are realized or executed
    assert updated.verified_realized_savings == 0.0

    reports = service.get_reports_audit()
    assert any(a.event == "Recommendation marked Approved" for a in reports.audit_events)


def test_settings_system_tables_readiness(service: FinOpsAnalyticsService) -> None:
    settings_data = service.get_settings_integrations()
    assert len(settings_data.connected_sources) >= 3
    by_name = {c.source_name: c for c in settings_data.connected_sources}
    assert by_name["Databricks Workspace APIs"].status == "Connected"
    assert by_name["Databricks System Tables (SQL)"].status == "Connected"  # fixture has usage rows
    assert by_name["Azure Cost Management"].status == "Unconfigured"
    readiness = settings_data.system_tables_readiness
    assert readiness["catalog"] == "system"
    # No Unity Catalog system-table metadata discovered in this offline test: nothing is claimed
    assert readiness["schemas_verified"] == [] and readiness["key_tables"] == []
    assert readiness["sql_execution_state"] == "STOPPED"

    blocked = make_analytics_service(with_billing=False).get_settings_integrations()
    sql_src = next(c for c in blocked.connected_sources if "System Tables" in c.source_name)
    assert sql_src.status == "Blocked - approval required"
    health = {m.metric_name: m.metric_value for m in blocked.pipeline_health}
    assert health["Billing Rows Ingested"] == "0"
    assert health["Missing Owner Tag Ratio"] == "-"


def test_fastapi_finops_all_routes(service: FinOpsAnalyticsService) -> None:
    exp = baseline_expectations()
    kw = {
        "connection_id": "databricks-azure-dev",
        "workspace_id": None,
        "resource_id": None,
        "resource_type": None,
        "service": service,
    }

    overview = get_overview(**kw)
    assert overview.kpis["total_spend"].value == pytest.approx(exp["total_cost"])

    cost = get_cost_explorer(**kw)
    assert len(cost.billing_ledger) > 0
    csv_res = export_cost_explorer_csv(**kw)
    assert "text/csv" in csv_res.media_type
    assert "SERVERLESS_SQL_COMPUTE" in csv_res.body.decode("utf-8")

    alloc = get_cost_allocation(**kw)
    assert len(alloc.spend_by_bu) > 0
    assert len(get_compute_warehouses(**kw).clusters) > 0
    ai = get_ai_economics(**kw)
    assert ai.kpis["ai_spend"].value == pytest.approx(exp["by_product"]["MODEL_SERVING"])
    assert len(get_data_storage(**kw).tables) > 0
    assert get_network_cloud(**kw).kpis["network_infra_spend"].status == (KpiStatus.NOT_AUTHORIZED)

    adv = get_optimization_advisor(**kw)
    assert len(adv.recommendations) > 0
    dec = record_decision_action(
        decision_id=adv.recommendations[0].id,
        req=RecommendationActionRequest(action="Deferred", notes="Deferred due to test"),
        service=service,
    )
    assert dec.status == "Deferred"

    fc = get_forecast_budgets(**kw)
    assert fc.budget_burn == [] and fc.kpis["forecast_month_end"].value is None
    sim = simulate_scenario(
        req=ScenarioSimulationRequest(compute_save_pct=15.0, token_save_pct=20.0, growth_pct=5.0),
        service=service,
    )
    assert sim.status == KpiStatus.INSUFFICIENT_HISTORY and sim.adjusted_spend is None

    assert get_anomaly_detection(**kw).anomalies == []
    gov = get_governance_policies(**kw)
    assert [p.policy_name for p in gov.policies] == ["Personal Compute"]
    assert len(get_showback_chargeback(**kw).statements) > 0
    assert len(get_workload_economics(**kw).workloads) > 0
    assert len(get_reports_audit(**kw).audit_events) > 0  # the action recorded above
    stg = get_settings_integrations(**kw)
    assert stg.system_tables_readiness["catalog"] == "system"
    assert all(r.source.startswith("Built-in rate card") for r in stg.rate_cards)

    canonical_res = get_canonical_kpi(
        metric_id="databricks_spend",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert canonical_res.metric.value == pytest.approx(exp["total_cost"])
    assert canonical_res.metric.unit == "USD"
    assert canonical_res.metric.aggregation_method == "SUM"


def test_finops_ai_analysis_and_anomaly_status() -> None:
    svc = make_analytics_service(with_billing=False)
    add_synthetic_history(svc.billing_service, days=20, spike_day=18, spike_dbu=600.0)

    analysis = get_finops_ai_analysis(
        module_id="overview",
        connection_id="databricks-azure-dev",
        workspace_id="642006393507276",
        service=svc,
    )
    assert analysis.module_id == "overview"
    assert "backed by live or calculated data" in analysis.executive_summary
    assert "176,840" not in analysis.executive_summary  # no modelled figures in narratives
    assert len(analysis.important_findings) > 0
    assert analysis.is_ai_live is False

    anomalies = svc.get_anomaly_detection()
    assert [a.id for a in anomalies.anomalies] == ["anom-2026-11-18"]
    spike = anomalies.anomalies[0]
    assert spike.baseline == "$110.00 / day" and spike.observed == "$1,320.00 / day"
    assert spike.sku_contribution[0]["sku"] == "SERVERLESS_SQL_COMPUTE"
    assert anomalies.kpis["open_anomalies"].value == 1.0

    update_res = update_finops_anomaly_status(
        anomaly_id="anom-2026-11-18",
        payload=AnomalyStatusUpdateRequest(status="Investigating"),
        service=svc,
    )
    assert update_res["status"] == "Investigating"
    target = next(a for a in svc.get_anomaly_detection().anomalies if a.id == "anom-2026-11-18")
    assert target.status == "Investigating"


def test_savings_reconciliation_hierarchy_and_lifecycle(service: FinOpsAnalyticsService) -> None:
    """Recommendations carry evidence and a timestamp; savings are never claimed without data."""
    advisor = service.get_optimization_advisor(connection_id="databricks-azure-dev")
    kpis = advisor.kpis
    recs = advisor.recommendations

    # fixture config: warehouse auto_stop 15m, cluster w/o auto-termination, endpoint w/o scale-to-zero
    assert {r.id for r in recs} == {
        "rec-wh-autostop-05ed10a52697a344",
        "rec-cl-noterm-1102-081455-7t3bqp3v",
        "rec-srv-s2z-databricks-claude-fable-5",
    }
    for key in ("potential_savings", "estimated_savings", "approved_savings"):
        assert kpis[key].value is None and kpis[key].status == KpiStatus.UNAVAILABLE
    assert kpis["realized_savings"].value is None and kpis["implemented_savings"].value is None
    assert kpis["quick_wins"].value == 3.0 and kpis["awaiting_approval"].value == 3.0

    for r in recs:
        assert r.resource_name and r.resource_id and r.finding and r.recommended_action
        assert r.evidence and r.calculation_methodology and r.confidence_pct > 0
        assert r.source_timestamp.startswith("2026-11-13")
        assert r.estimated_savings_monthly is None and r.savings_status == KpiStatus.UNAVAILABLE
        assert r.status in ("Approval required", "Approved", "Deferred")
        assert r.verified_realized_savings == 0.0


def test_forecast_and_budget_calculations_and_accuracy() -> None:
    """Forecast/budget arithmetic on 20 synthetic days ($110/day) with a configured budget."""
    svc = make_analytics_service(with_billing=False)
    add_synthetic_history(svc.billing_service, days=20)
    svc._budget = lambda: 3000.0  # type: ignore[method-assign]
    kpis = svc.get_forecast_budgets(connection_id="databricks-azure-dev").kpis

    assert (
        kpis["approved_budget"].value == 3000.0 and kpis["approved_budget"].status == KpiStatus.LIVE
    )
    assert kpis["actual_mtd"].value == pytest.approx(2200.0)
    assert kpis["actual_mtd"].status == KpiStatus.CALCULATED
    assert kpis["forecast_month_end"].value == pytest.approx(3300.0)
    assert kpis["forecast_month_end"].status == KpiStatus.ESTIMATED  # distinct from actuals
    assert kpis["budget_utilization"].value == pytest.approx(73.3)
    assert kpis["projected_overrun"].value == pytest.approx(300.0)
    assert kpis["forecast_accuracy"].value is None
    assert kpis["forecast_accuracy"].status == KpiStatus.INSUFFICIENT_HISTORY
    assert kpis["forecast_confidence"].status == KpiStatus.UNAVAILABLE

    fc = svc.get_forecast_budgets(connection_id="databricks-azure-dev")
    assert fc.budget_controls[0].status == "Forecast breach"
    assert fc.budget_burn[-1] == {"day": "Nov 20", "actual": 2200.0, "budget": 3000.0}

    empty_fc = svc.get_forecast_budgets(
        connection_id="databricks-azure-dev",
        resource_id="unknown-resource-999",
        resource_type="cluster",
    )
    assert empty_fc.kpis["approved_budget"].value is None
    assert empty_fc.kpis["actual_mtd"].value is None
    assert len(empty_fc.budget_controls) == 0
