"""Milestone 3G.2 Forensic Baseline Financial Reconciliation & Canonical Resource Inventory Tests.

Validates:
1. Exact ledger DBU and financial reconciliation (zero discrepancy: 88,420.0 DBU and $176,840.00).
2. AI Spend lineage: $26,740 Model Serving Compute in DBU consumption ledger vs $38,460 total AI spend.
3. Model Serving ($26,740) + AI Gateway external tokens ($11,296) + Vector Search ($424) = $38,460.
4. Forecast Run-rate extrapolation: $284,620 MTD extrapolated and rounded to $319,500 ($19.5K over budget).
5. Effective blended rate: $2.0000/DBU is strictly a blended baseline quotient ($176,840 / 88,420 DBU).
6. Authoritative cluster ID (1102-081455-7t3bqp3v) accepted; mock cluster ID (1105-132712-k0qfl59u) rejected.
7. Cluster name (adf-deaccelator-compute) cannot independently authorize cluster attribution.
8. Historical endpoint fixtures (deepseek-r1-endpoint, mistral-large-endpoint) separated and rejected as live assets.
9. Databricks Apps (cement-demand-forecasting, mcp-generate-ppt, wonder-cement-app) isolated in unattributed pool ($1,240).
10. Full scope isolation across all 15 modules: unknown or mismatched resources return NO_DATA.
"""

import pytest

from cloud_recommender.schemas.finops import KpiStatus
from cloud_recommender.services.databricks.finops_analytics_service import (
    FinOpsAnalyticsService,
)


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return FinOpsAnalyticsService()


# =============================================================================
# 1. Exact Ledger & DBU Component Reconciliation (Section 2.2)
# =============================================================================


def test_ledger_24_records_exact_sum(service: FinOpsAnalyticsService) -> None:
    """Validate that the canonical billing ledger contains exactly 24 records summing to $176,840.00 and 88,420.0 DBU."""
    ledger = service._get_canonical_ledger()
    assert len(ledger) == 24, f"Expected exactly 24 ledger items, got {len(ledger)}"

    total_cost = sum(item.effective_cost for item in ledger)
    total_dbu = sum(item.usage_qty for item in ledger if item.unit == "DBU")

    # Exact financial sum: zero delta
    assert total_cost == 176840.0, f"Expected total cost $176,840.00, got ${total_cost:.2f}"
    # Exact DBU sum: zero delta (reconciles the reported 7.28 DBU error)
    assert total_dbu == 88420.0, f"Expected total DBU 88,420.0, got {total_dbu}"


def test_dbu_component_breakdown_exact_reconciliation(service: FinOpsAnalyticsService) -> None:
    """Verify each component's exact contribution to the 88,420.0 DBU total."""
    ledger = service._get_canonical_ledger()

    sql_dbu = sum(i.usage_qty for i in ledger if i.product == "SQL Warehouse" and i.unit == "DBU")
    cluster_dbu = sum(i.usage_qty for i in ledger if i.product == "Compute" and i.unit == "DBU")
    jobs_dbu = sum(i.usage_qty for i in ledger if i.product == "Automated Jobs" and i.unit == "DBU")
    serving_dbu = sum(
        i.usage_qty for i in ledger if i.product == "Model Serving" and i.unit == "DBU"
    )
    apps_dbu = sum(
        i.usage_qty for i in ledger if i.product == "Databricks Apps" and i.unit == "DBU"
    )

    assert sql_dbu == 19172.0, f"Expected SQL DBU 19,172.0, got {sql_dbu}"
    assert cluster_dbu == 11180.0, f"Expected Cluster DBU 11,180.0, got {cluster_dbu}"
    assert jobs_dbu == 51073.0, f"Expected Jobs DBU 51,073.0, got {jobs_dbu}"
    assert serving_dbu == 6685.0, f"Expected Model Serving DBU 6,685.0, got {serving_dbu}"
    assert apps_dbu == 310.0, f"Expected Apps DBU 310.0, got {apps_dbu}"

    computed_total_dbu = sql_dbu + cluster_dbu + jobs_dbu + serving_dbu + apps_dbu
    assert computed_total_dbu == 88420.0, f"Expected sum 88,420.0 DBU, got {computed_total_dbu}"


def test_effective_rate_blended_quotient(service: FinOpsAnalyticsService) -> None:
    """Validate that the effective rate of $2.0000/DBU is strictly a blended baseline quotient."""
    overview = service.get_executive_overview()
    dbu_kpi = overview.kpis["dbu_consumption"]
    databricks_spend_kpi = overview.kpis["databricks_spend"]

    assert dbu_kpi.value == 88420.0
    assert databricks_spend_kpi.value == 176840.0

    blended_rate = databricks_spend_kpi.value / dbu_kpi.value
    assert blended_rate == 2.0, f"Expected blended quotient $2.00/DBU, got {blended_rate}"
    assert "$2.0000/DBU" in (dbu_kpi.limitations or "")
    assert "not a retail list price" in (dbu_kpi.limitations or "")


# =============================================================================
# 2. AI Spend Lineage & Financial Attribution (Section 2.1)
# =============================================================================


def test_ai_spend_lineage_and_reconciliation(service: FinOpsAnalyticsService) -> None:
    """Verify that Total AI Spend ($38,460) reconciles with Model Serving compute ($26,740) + AI Gateway ($11,296) + Vector Search ($424)."""
    overview = service.get_executive_overview()
    ai_kpi = overview.kpis["ai_spend"]

    assert ai_kpi.value == 38460.0
    assert ai_kpi.formatted_value == "$38,460"

    # Lineage formula in KPI metadata verifies components
    formula = ai_kpi.formula or ""
    assert "26,740" in formula
    assert "11,296" in formula
    assert "424" in formula
    assert "double-counting" in (ai_kpi.limitations or "").lower()

    # Total cloud spend composition includes AI / GenAI = $38,460
    ai_comp = [c for c in overview.spend_composition if c["family"] == "AI / GenAI"]
    assert len(ai_comp) == 1
    assert ai_comp[0]["amount"] == 38460


def test_model_serving_ledger_isolation(service: FinOpsAnalyticsService) -> None:
    """Verify that the ledger Model Serving items sum to $26,740.00 and 6,685.0 DBU."""
    serving_ledger = service._get_canonical_ledger(resource_type="serving")
    assert len(serving_ledger) == 4
    total_serving_cost = sum(i.effective_cost for i in serving_ledger)
    total_serving_dbu = sum(i.usage_qty for i in serving_ledger)

    assert total_serving_cost == 26740.0
    assert total_serving_dbu == 6685.0


# =============================================================================
# 3. Forecast Spend Extrapolation & Rounding (Section 2.4)
# =============================================================================


def test_forecast_spend_run_rate_rounding(service: FinOpsAnalyticsService) -> None:
    """Validate forecast spend calculation: $284,620 extrapolated at current run-rate to $319,500."""
    overview = service.get_executive_overview()
    f_kpi = overview.kpis["forecast_spend"]

    assert f_kpi.value == 319500.0
    assert f_kpi.formatted_value == "$319,500"
    assert f_kpi.change_absolute == 19500.0
    assert "19.5K above budget" in (f_kpi.delta_label or "")

    # Extrapolation formula check
    assert "30.0 / 26.7236" in (f_kpi.formula or "")
    assert "319,515.33" in (f_kpi.limitations or "")


# =============================================================================
# 4. Canonical Resource Identity & Registry Closure (Section 3)
# =============================================================================


def test_authoritative_cluster_id_accepted(service: FinOpsAnalyticsService) -> None:
    """Canonical discovered cluster ID 1102-081455-7t3bqp3v is accepted and attributed."""
    cat, is_unknown = service._resolve_resource_filter("1102-081455-7t3bqp3v", "cluster")
    assert is_unknown is False
    assert cat == "cluster"

    overview = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="1102-081455-7t3bqp3v",
        resource_type="cluster",
    )
    assert overview.kpis["total_spend"].value == 24600.0
    assert overview.kpis["total_spend"].status in (KpiStatus.AVAILABLE, KpiStatus.BASELINE)


def test_purged_ui_mock_cluster_id_rejected(service: FinOpsAnalyticsService) -> None:
    """UI mock cluster ID 1105-132712-k0qfl59u is completely purged and returns NO_DATA."""
    cat, is_unknown = service._resolve_resource_filter("1105-132712-k0qfl59u", "cluster")
    assert is_unknown is True
    assert cat is None

    overview = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="1105-132712-k0qfl59u",
        resource_type="cluster",
    )
    assert overview.kpis["total_spend"].status == KpiStatus.NO_DATA
    assert overview.kpis["total_spend"].value is None
    assert overview.kpis["total_spend"].formatted_value == "No data available"


def test_cluster_name_cannot_authorize_attribution(service: FinOpsAnalyticsService) -> None:
    """Cluster name adf-deaccelator-compute is display metadata and CANNOT authorize attribution."""
    cat, is_unknown = service._resolve_resource_filter("adf-deaccelator-compute", "cluster")
    assert is_unknown is True
    assert cat is None

    overview = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="adf-deaccelator-compute",
        resource_type="cluster",
    )
    assert overview.kpis["total_spend"].status == KpiStatus.NO_DATA
    assert overview.kpis["total_spend"].value is None
    assert overview.kpis["total_spend"].formatted_value == "No data available"


def test_historical_endpoint_fixtures_rejected_from_live_scope(
    service: FinOpsAnalyticsService,
) -> None:
    """Historical fixtures (deepseek-r1-endpoint, mistral-large-endpoint) are rejected in live workspace scope."""
    for fixture_id in ("deepseek-r1-endpoint", "mistral-large-endpoint"):
        assert fixture_id in service.HISTORICAL_FIXTURE_ENDPOINTS
        assert fixture_id not in service.KNOWN_SERVING_ENDPOINTS

        cat, is_unknown = service._resolve_resource_filter(fixture_id, "serving_endpoint")
        assert is_unknown is True
        assert cat is None

        overview = service.get_executive_overview(
            workspace_id="642006393507276",
            resource_id=fixture_id,
            resource_type="serving_endpoint",
        )
        assert overview.kpis["total_spend"].status == KpiStatus.NO_DATA
        assert overview.kpis["total_spend"].value is None
        assert overview.kpis["total_spend"].formatted_value == "No data available"


def test_app_inventory_unattributed_pool_isolation(service: FinOpsAnalyticsService) -> None:
    """Verified apps (cement-demand-forecasting, mcp-generate-ppt, wonder-cement-app) isolate in unattributed pool."""
    for app_id in ("cement-demand-forecasting", "mcp-generate-ppt", "wonder-cement-app"):
        cat, is_unknown = service._resolve_resource_filter(app_id, "app")
        assert is_unknown is False
        assert cat == "app"

        overview = service.get_executive_overview(
            workspace_id="642006393507276",
            resource_id=app_id,
            resource_type="app",
        )
        assert overview.kpis["total_spend"].value == 0.0
        assert "Unattributed" in overview.kpis["total_spend"].formatted_value
        assert "$1,240 in Unattributed pool" in (overview.kpis["total_spend"].delta_label or "")


# =============================================================================
# 5. All-Module Scope Regression & NO_DATA Integrity (Section 4)
# =============================================================================


def test_unknown_resource_across_all_15_modules(service: FinOpsAnalyticsService) -> None:
    """Verify that every module returns NO_DATA or empty datasets for unknown resource scopes."""
    fake_rid = "fake-resource-xyz-999"
    fake_rt = "cluster"

    # 1. Executive Overview
    overview = service.get_executive_overview(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert overview.kpis["total_spend"].status == KpiStatus.NO_DATA

    # 2. Cost Explorer
    cost_exp = service.get_cost_explorer(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert len(cost_exp.billing_ledger) == 0

    # 3. Compute Warehouses
    comp_wh = service.get_compute_warehouses(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert len(comp_wh.warehouses) == 0

    # 4. AI Economics
    ai_econ = service.get_ai_economics(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert ai_econ.kpis["ai_spend"].status == KpiStatus.NO_DATA

    # 5. Data Storage
    storage = service.get_data_storage(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert storage.kpis["storage_spend"].status == KpiStatus.NO_DATA

    # 6. Optimization Advisor
    advisor = service.get_optimization_advisor(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert len(advisor.recommendations) == 0

    # 7. Anomaly Detection
    anomalies = service.get_anomaly_detection(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert len(anomalies.anomalies) == 0

    # 8. Forecast & Budgets
    forecast = service.get_forecast_budgets(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert forecast.kpis["forecast_month_end"].status == KpiStatus.NO_DATA

    # 9. Cost Allocation
    alloc = service.get_cost_allocation(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert alloc.kpis["unallocated_spend"].status == KpiStatus.NO_DATA

    # 10. Showback / Chargeback
    showback = service.get_showback_chargeback(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert len(showback.statements) == 0

    # 11. Workload Economics
    workload = service.get_workload_economics(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert len(workload.workloads) == 0

    # 12. Governance & Policies
    gov = service.get_governance_policies(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert gov.kpis["policy_compliance"].status == KpiStatus.NO_DATA

    # 13. Network & Cloud
    net = service.get_network_cloud(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert len(net.components) == 0

    # 14. Reports & Audit
    reports = service.get_reports_audit(
        workspace_id="642006393507276", resource_id=fake_rid, resource_type=fake_rt
    )
    assert len(reports.report_packs) == 0

    # 15. Settings & Integrations
    settings = service.get_settings_integrations(workspace_id="642006393507276")
    assert len(settings.connected_sources) > 0  # Workspace level settings remains available
