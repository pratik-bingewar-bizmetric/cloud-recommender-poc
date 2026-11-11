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
from cloud_recommender.schemas.finops import (
    AnomalyStatusUpdateRequest,
    KpiStatus,
    RecommendationActionRequest,
    ScenarioSimulationRequest,
)
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return FinOpsAnalyticsService()


def test_executive_overview_contracts(service: FinOpsAnalyticsService) -> None:
    data = service.get_executive_overview(connection_id="databricks-azure-dev")
    # Verify all 7 required KPI cards
    assert "total_spend" in data.kpis
    assert "databricks_spend" in data.kpis
    assert "ai_spend" in data.kpis
    assert "dbu_consumption" in data.kpis
    assert "savings_opportunity" in data.kpis
    assert "forecast_spend" in data.kpis
    assert "anomalies" in data.kpis

    assert data.kpis["total_spend"].formatted_value == "$284,620"
    assert data.kpis["databricks_spend"].formatted_value == "$176,840"
    assert data.kpis["ai_spend"].formatted_value == "$38,460"
    assert data.kpis["dbu_consumption"].formatted_value == "88,420 DBU"
    assert data.kpis["savings_opportunity"].formatted_value == "$24,530"
    assert data.kpis["forecast_spend"].formatted_value == "$319,500"
    assert data.kpis["anomalies"].formatted_value == "3"

    assert len(data.spend_trend) == 20
    assert len(data.spend_composition) == 5
    assert len(data.top_cost_drivers) >= 3
    assert len(data.decisions_requiring_attention) >= 1


def test_dbu_consumption_and_token_isolation(service: FinOpsAnalyticsService) -> None:
    overview = service.get_executive_overview()
    dbu_kpi = overview.kpis["dbu_consumption"]
    assert dbu_kpi.unit == "DBU"
    assert dbu_kpi.value == 88420.0
    assert "Strict unit separation" in (dbu_kpi.limitations or "")

    # Token economics from AI service must have raw tokens, not DBUs
    ai = service.get_ai_economics()
    assert "input_tokens" in ai.kpis
    assert ai.kpis["input_tokens"].unit.lower() == "tokens"


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
    # 1. Filter by SQL Warehouse
    wh_data = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="05ed10a52697a344",
        resource_type="warehouse",
    )
    assert wh_data.kpis["total_spend"].value == 42180.0
    assert wh_data.kpis["dbu_consumption"].value == 19172.0
    assert len(wh_data.top_cost_drivers) == 1
    assert wh_data.top_cost_drivers[0].driver == "Serverless Starter Warehouse"

    # 2. Filter by Compute Cluster using canonical cluster ID (Requirement 3.1 & 3.2)
    cl_data = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="1102-081455-7t3bqp3v",
        resource_type="cluster",
    )
    assert cl_data.kpis["total_spend"].value == 24600.0
    assert cl_data.kpis["dbu_consumption"].value == 11180.0
    assert len(cl_data.top_cost_drivers) == 1
    assert cl_data.top_cost_drivers[0].driver == "adf-deaccelator-compute"

    # Cluster name alone cannot independently authorize attribution
    cl_name_data = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="adf-deaccelator-compute",
        resource_type="cluster",
    )
    assert cl_name_data.kpis["total_spend"].status == KpiStatus.NO_DATA
    assert cl_name_data.kpis["total_spend"].value is None
    assert cl_name_data.kpis["total_spend"].formatted_value == "No data available"


def test_unattributed_cost_preservation_for_apps(service: FinOpsAnalyticsService) -> None:
    # 1. When filtering by a verified discovered app lacking direct billing attribution tags
    app_data = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="cement-demand-forecasting",
        resource_type="app",
    )
    assert app_data.kpis["total_spend"].value == 0.0
    assert "Unattributed" in app_data.kpis["total_spend"].formatted_value
    assert "$1,240 in Unattributed pool" in (app_data.kpis["total_spend"].delta_label or "")
    assert len(app_data.top_cost_drivers) == 1
    assert "Unattributed" in app_data.top_cost_drivers[0].workspace_owner

    # 2. Adversarial test: purged/fabricated app identifier returns NO_DATA
    purged_app = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="databricks-cost-monitor",
        resource_type="app",
    )
    assert purged_app.kpis["total_spend"].value is None
    assert purged_app.kpis["total_spend"].formatted_value == "No data available"
    assert purged_app.kpis["total_spend"].status.value == "NO_DATA"


def test_query_history_retrieval_and_filtering(service: FinOpsAnalyticsService) -> None:
    history = service.get_query_history(workspace_id="642006393507276")
    assert history.total_count == 7
    assert len(history.records) == 7
    assert len(history.duration_histogram) == 5
    assert len(history.status_distribution) == 3

    # Check query attributes
    q0 = history.records[0]
    assert q0.warehouse_name == "Serverless Starter Warehouse"
    assert q0.status == "FINISHED"
    assert q0.sql_statement.startswith("SELECT")
    assert q0.cost_correlation_dbu is not None

    # Filter by status
    failed = service.get_query_history(status="FAILED")
    assert failed.total_count == 1
    assert failed.records[0].status == "FAILED"
    assert failed.records[0].error_message is not None


def test_system_tables_explorer_and_stopped_warehouse_state(
    service: FinOpsAnalyticsService,
) -> None:
    sys_tables = service.get_system_tables(workspace_id="642006393507276")
    assert len(sys_tables.tables) == 10
    assert sys_tables.catalog_status == "SCHEMA_VERIFIED"
    assert sys_tables.warehouse_state == "STOPPED"

    table_names = [t.table_name for t in sys_tables.tables]
    assert "system.billing.usage" in table_names
    assert "system.billing.list_prices" in table_names
    assert "system.access.audit" in table_names
    assert "system.compute.clusters" in table_names
    assert "system.compute.warehouses" in table_names
    assert "system.query.history" in table_names

    # Check that system.billing.usage has columns verified
    usage_tbl = next(t for t in sys_tables.tables if t.table_name == "system.billing.usage")
    assert usage_tbl.columns_count == 28
    assert usage_tbl.status == "STOPPED_WAREHOUSE"
    assert len(usage_tbl.columns) > 0


def test_cost_explorer_and_csv_export(service: FinOpsAnalyticsService) -> None:
    data = service.get_cost_explorer()
    assert "gross_consumption" in data.kpis
    assert len(data.billing_ledger) > 0

    csv_out = service.export_cost_ledger_csv()
    assert "Product,SKU,Workspace" in csv_out
    assert "SQL Warehouse" in csv_out
    assert "adb-642006393507276" in csv_out


def test_compute_warehouses_and_heatmap(service: FinOpsAnalyticsService) -> None:
    data = service.get_compute_warehouses()
    assert len(data.clusters) >= 1
    assert len(data.warehouses) >= 1
    # 7 days x 24 hours heatmap
    assert len(data.heatmap_utilization) == 168


def test_ai_economics_endpoints(service: FinOpsAnalyticsService) -> None:
    data = service.get_ai_economics()
    assert "ai_spend" in data.kpis
    assert "input_tokens" in data.kpis
    assert len(data.serving_endpoints) >= 1
    assert len(data.genie_scorecard) >= 1
    assert len(data.agents) >= 1


def test_data_storage_catalogs(service: FinOpsAnalyticsService) -> None:
    data = service.get_data_storage()
    assert "total_stored_data" in data.kpis
    assert len(data.storage_tiers) == 4
    assert len(data.tables) >= 1


def test_scenario_simulator(service: FinOpsAnalyticsService) -> None:
    from cloud_recommender.schemas.finops import ScenarioSimulationRequest

    # Test baseline adjustment: compute save 20%, token save 30%, growth 0%
    req = ScenarioSimulationRequest(compute_save_pct=20.0, token_save_pct=30.0, growth_pct=0.0)
    res = service.simulate_forecast_scenario(req)
    assert res.adjusted_spend < res.baseline_spend
    assert res.savings_vs_baseline > 0
    assert res.is_favorable is True


def test_decision_action_mutation_and_audit(service: FinOpsAnalyticsService) -> None:
    updated = service.record_decision_action("dec-01", "Approved", notes="Approved for test")
    assert updated.status == "Approved"

    # Verify audit event logged
    reports = service.get_reports_audit()
    assert any(a.event == "Recommendation marked Approved" for a in reports.audit_events)


def test_settings_system_tables_readiness(service: FinOpsAnalyticsService) -> None:
    settings_data = service.get_settings_integrations()
    assert len(settings_data.connected_sources) >= 3
    readiness = settings_data.system_tables_readiness
    assert readiness["catalog"] == "system"
    assert "billing" in readiness["schemas_verified"]
    assert len(readiness["key_tables"]) >= 5


def test_fastapi_finops_all_routes(service: FinOpsAnalyticsService) -> None:
    # 1. Overview
    overview = get_overview(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert "total_spend" in overview.kpis

    # 2. Cost Explorer
    cost = get_cost_explorer(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(cost.billing_ledger) > 0

    # CSV Download
    csv_res = export_cost_explorer_csv(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert "text/csv" in csv_res.media_type
    assert "SQL Warehouse" in csv_res.body.decode("utf-8")

    # 3. Cost Allocation
    alloc = get_cost_allocation(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(alloc.spend_by_bu) > 0

    # 4. Compute & Warehouses
    comp = get_compute_warehouses(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(comp.clusters) > 0

    # 5. AI Economics
    ai = get_ai_economics(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert "ai_spend" in ai.kpis
    assert ai.kpis["ai_spend"].value == 38460.0

    # 6. Data Storage
    storage = get_data_storage(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(storage.tables) > 0

    # 7. Network Cloud
    net = get_network_cloud(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert "network_infra_spend" in net.kpis

    # 8. Optimization Advisor
    adv = get_optimization_advisor(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(adv.recommendations) > 0

    # Action on recommendation
    dec = record_decision_action(
        decision_id="dec-02",
        req=RecommendationActionRequest(action="Deferred", notes="Deferred due to test"),
        service=service,
    )
    assert dec.status == "Deferred"

    # 9. Forecast & Budgets
    fc = get_forecast_budgets(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(fc.budget_burn) > 0

    # Simulate scenario
    sim = simulate_scenario(
        req=ScenarioSimulationRequest(compute_save_pct=15.0, token_save_pct=20.0, growth_pct=5.0),
        service=service,
    )
    assert sim.adjusted_spend > 0

    # 10. Anomaly Detection
    anom = get_anomaly_detection(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(anom.anomalies) > 0

    # 11. Governance Policies
    gov = get_governance_policies(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(gov.policies) > 0

    # 12. Showback Chargeback
    sb = get_showback_chargeback(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(sb.statements) > 0

    # 13. Workload Economics
    wk = get_workload_economics(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(wk.workloads) > 0

    # 14. Reports Audit
    rpt = get_reports_audit(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert len(rpt.audit_events) > 0

    # 15. Settings Integrations
    stg = get_settings_integrations(
        connection_id="databricks-azure-dev",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert stg.system_tables_readiness["catalog"] == "system"

    # Canonical KPI endpoint test
    canonical_res = get_canonical_kpi(
        metric_id="databricks_spend",
        workspace_id=None,
        resource_id=None,
        resource_type=None,
        service=service,
    )
    assert canonical_res.metric.value == 176840.0
    assert canonical_res.metric.unit == "USD"
    assert canonical_res.metric.aggregation_method == "SUM"


def test_finops_ai_analysis_and_anomaly_status(service: FinOpsAnalyticsService) -> None:
    # 1. Test AI Analysis for overview module
    analysis = get_finops_ai_analysis(
        module_id="overview",
        connection_id="databricks-azure-dev",
        workspace_id="642006393507276",
        service=service,
    )
    assert analysis.module_id == "overview"
    assert "176,840.00" in analysis.executive_summary
    assert len(analysis.important_findings) > 0
    assert len(analysis.cost_drivers) > 0
    assert len(analysis.optimization_opportunities) > 0
    assert analysis.expected_savings != ""

    # 2. Test Anomaly status update
    update_res = update_finops_anomaly_status(
        anomaly_id="anom-01",
        payload=AnomalyStatusUpdateRequest(status="Investigating"),
        service=service,
    )
    assert update_res["status"] == "Investigating"

    # Verify updated in anomaly detection endpoint
    anomalies = service.get_anomaly_detection()
    target_anom = next(a for a in anomalies.anomalies if a.id == "anom-01")
    assert target_anom.status == "Investigating"
    assert target_anom.percentage_deviation == "+180.9%"
    assert len(target_anom.root_cause_hypotheses) > 0


def test_savings_reconciliation_hierarchy_and_lifecycle(service: FinOpsAnalyticsService) -> None:
    """Verify exact 5-tier savings reconciliation according to FinOps standards.

    Checks:
    - Potential savings ($31,340) is NOT conflated with approved savings ($24,530).
    - Estimated savings ($31,280) is NOT conflated with approved savings ($24,530).
    - Realized savings is strictly $0.00 under zero-execution.
    - Implemented savings is strictly $0.00 under zero-execution.
    - All 5 recommendations contain full evidence, methodology, and action descriptions.
    """
    advisor = service.get_optimization_advisor(connection_id="databricks-azure-dev")
    kpis = advisor.kpis

    # 1. Verify exact reconciled values
    assert kpis["potential_savings"].value == 31340.0
    assert kpis["potential_savings"].formatted_value == "$31,340"

    assert kpis["estimated_savings"].value == 31280.0
    assert kpis["estimated_savings"].formatted_value == "$31,280"

    assert kpis["approved_savings"].value == 24530.0
    assert kpis["approved_savings"].formatted_value == "$24,530"

    assert kpis["implemented_savings"].value == 0.0
    assert kpis["implemented_savings"].formatted_value == "$0.00"

    assert kpis["realized_savings"].value == 0.0
    assert kpis["realized_savings"].formatted_value == "$0.00"

    # 2. Strict non-conflation assertions
    assert kpis["potential_savings"].value != kpis["approved_savings"].value
    assert kpis["estimated_savings"].value != kpis["approved_savings"].value
    assert kpis["realized_savings"].value == 0.0
    assert kpis["approved_savings"].value != kpis["realized_savings"].value

    # 3. Sum of all 5 recommendations must exactly equal approved savings ($24,530)
    recs = advisor.recommendations
    assert len(recs) == 5
    assert sum(r.estimated_savings_monthly for r in recs) == 24530.0

    # 4. Forensic verification of each recommendation's 10 required attributes
    for r in recs:
        assert r.resource_name, f"Recommendation {r.id} missing resource_name"
        assert r.resource_id, f"Recommendation {r.id} missing resource_id"
        assert r.finding, f"Recommendation {r.id} missing finding"
        assert r.recommended_action, f"Recommendation {r.id} missing recommended_action"
        assert r.calculation_methodology, f"Recommendation {r.id} missing calculation_methodology"
        assert r.confidence_pct > 0, f"Recommendation {r.id} missing confidence_pct"
        assert r.effort in ("Low", "Medium", "High"), f"Recommendation {r.id} invalid effort"
        assert r.risk in ("Low", "Medium", "High"), f"Recommendation {r.id} invalid risk"
        assert r.status in ("Approval required", "New", "Approved", "Deferred")
        assert r.verified_realized_savings == 0.0, f"Recommendation {r.id} non-zero realized savings"


def test_forecast_and_budget_calculations_and_accuracy(service: FinOpsAnalyticsService) -> None:
    """Verify budget utilization, overrun calculation, scenario simulator, and accuracy metrics."""
    fc = service.get_forecast_budgets(connection_id="databricks-azure-dev")
    kpis = fc.kpis

    # 1. Budget utilization arithmetic: 284,620 / 300,000 = 94.873% -> 94.9%
    assert kpis["approved_budget"].value == 300000.0
    assert kpis["actual_mtd"].value == 284620.0
    assert kpis["budget_utilization"].value == 94.9
    assert kpis["budget_utilization"].formatted_value == "94.9%"

    # 2. Overrun calculation: 319,500 - 300,000 = 19,500
    assert kpis["forecast_month_end"].value == 319500.0
    assert kpis["projected_overrun"].value == 19500.0
    assert kpis["projected_overrun"].formatted_value == "+$19,500"
    assert kpis["projected_overrun"].is_favorable is False

    # 3. Forecast accuracy metric: MUST display NOT AVAILABLE when insufficient 90d baseline
    assert kpis["forecast_accuracy"].value is None
    assert kpis["forecast_accuracy"].formatted_value == "NOT AVAILABLE"
    assert kpis["forecast_accuracy"].status == KpiStatus.UNAVAILABLE
    assert "Insufficient 90-day" in str(kpis["forecast_accuracy"].limitations)

    # 4. Statistical confidence metric
    assert kpis["forecast_confidence"].value == 87.0
    assert kpis["forecast_confidence"].formatted_value == "87%"

    # 5. Scenario simulator dynamic arithmetic
    from cloud_recommender.schemas.finops import ScenarioSimulationRequest

    # Test Case A: Aggressive optimization (30% compute, 50% token, 0% growth)
    # 319500 - (91420 * 0.3) - (38460 * 0.5) = 319500 - 27426 - 19230 = 272844
    sim_a = service.simulate_forecast_scenario(
        ScenarioSimulationRequest(compute_save_pct=30.0, token_save_pct=50.0, growth_pct=0.0)
    )
    assert sim_a.adjusted_spend == 272844
    assert sim_a.savings_vs_baseline == 46656
    assert sim_a.is_favorable is True
    assert "Under budget" in sim_a.delta_label

    # Test Case B: High growth without optimization (0% compute, 0% token, +20% growth)
    # 319500 * 1.2 = 383400
    sim_b = service.simulate_forecast_scenario(
        ScenarioSimulationRequest(compute_save_pct=0.0, token_save_pct=0.0, growth_pct=20.0)
    )
    assert sim_b.adjusted_spend == 383400
    assert sim_b.savings_vs_baseline == -63900
    assert sim_b.is_favorable is False
    assert "Over budget" in sim_b.delta_label

    # 6. Scope propagation: Unknown resource filter returns graceful empty states
    empty_fc = service.get_forecast_budgets(
        connection_id="databricks-azure-dev",
        resource_id="unknown-resource-999",
        resource_type="cluster",
    )
    assert empty_fc.kpis["approved_budget"].value is None
    assert empty_fc.kpis["actual_mtd"].value is None
    assert len(empty_fc.budget_controls) == 0

