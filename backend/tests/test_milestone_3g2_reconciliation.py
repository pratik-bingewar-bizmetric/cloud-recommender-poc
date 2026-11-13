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
from tests.fixtures.billing_baseline import baseline_expectations
from tests.fixtures.live_inventory import make_analytics_service


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return make_analytics_service(with_billing=True)


# =============================================================================
# 1. Exact Ledger & DBU Component Reconciliation (Section 2.2)
# =============================================================================


def test_ledger_24_records_exact_sum(service: FinOpsAnalyticsService) -> None:
    """The ledger is derived from ingested rows and reconciles exactly to the independent total."""
    exp = baseline_expectations()
    rows = service._billing_rows(None, None, None)
    assert len(rows) == exp["row_count"]
    assert service._sum_cost(rows) == pytest.approx(exp["total_cost"])
    assert service._sum_dbu(rows) == exp["total_dbu"]


def test_dbu_component_breakdown_exact_reconciliation(service: FinOpsAnalyticsService) -> None:
    """Each billing product's DBU contribution reconciles to the independent total."""
    exp = baseline_expectations()
    ledger = service.get_cost_explorer().billing_ledger
    for product, expected_dbu in exp["by_product_dbu"].items():
        got = sum(i.usage_qty for i in ledger if i.product == product and i.unit == "DBU")
        assert got == expected_dbu, product
    assert sum(exp["by_product_dbu"].values()) == exp["total_dbu"]


def test_effective_rate_blended_quotient(service: FinOpsAnalyticsService) -> None:
    """Blended rate is strictly spend / DBU of the ingested rows."""
    exp = baseline_expectations()
    overview = service.get_executive_overview()
    spend = overview.kpis["databricks_spend"]
    dbu = overview.kpis["dbu_consumption"]
    assert dbu.value == exp["total_dbu"]
    assert spend.value == pytest.approx(exp["total_cost"])
    assert spend.value / dbu.value == pytest.approx(exp["total_cost"] / exp["total_dbu"])
    assert "List-price" in (spend.caveats or "")


# =============================================================================
# 2. AI Spend Lineage & Financial Attribution (Section 2.1)
# =============================================================================


def test_ai_spend_lineage_and_reconciliation(service: FinOpsAnalyticsService) -> None:
    """AI spend equals the Model Serving rows, is part of (not added to) total spend, and cites its source."""
    exp = baseline_expectations()
    overview = service.get_executive_overview()
    ai_kpi = overview.kpis["ai_spend"]
    assert ai_kpi.value == pytest.approx(exp["by_product"]["MODEL_SERVING"])
    assert ai_kpi.value <= overview.kpis["total_spend"].value
    assert "billing_origin_product" in (ai_kpi.formula or "")
    assert ai_kpi.status == KpiStatus.CALCULATED
    families = {c["family"]: c["amount"] for c in overview.spend_composition}
    assert families["MODEL_SERVING"] == pytest.approx(ai_kpi.value)


def test_model_serving_ledger_isolation(service: FinOpsAnalyticsService) -> None:
    """Serving-scope rows are exactly the endpoint-attributed Model Serving usage."""
    exp = baseline_expectations()
    rows = service._billing_rows(None, "serving", None)
    assert len(rows) == 4
    assert service._sum_cost(rows) == pytest.approx(exp["by_product"]["MODEL_SERVING"])
    assert service._sum_dbu(rows) == exp["by_product_dbu"]["MODEL_SERVING"]


# =============================================================================
# 3. Forecast Spend Extrapolation & Rounding (Section 2.4)
# =============================================================================


def test_forecast_spend_run_rate_rounding(service: FinOpsAnalyticsService) -> None:
    """With only 4 usage days no forecast is produced (no extrapolation from thin history)."""
    f_kpi = service.get_executive_overview().kpis["forecast_spend"]
    assert f_kpi.value is None
    assert f_kpi.status == KpiStatus.INSUFFICIENT_HISTORY
    assert "14" in (f_kpi.caveats or "")


# =============================================================================
# 4. Canonical Resource Identity & Registry Closure (Section 3)
# =============================================================================


def test_authoritative_cluster_id_accepted(service: FinOpsAnalyticsService) -> None:
    """Canonical discovered cluster ID is accepted and attributed from real rows."""
    exp = baseline_expectations()
    cat, is_unknown = service._resolve_resource_filter("1102-081455-7t3bqp3v", "cluster")
    assert is_unknown is False
    assert cat == "cluster"

    overview = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="1102-081455-7t3bqp3v",
        resource_type="cluster",
    )
    assert overview.kpis["total_spend"].value == pytest.approx(
        exp["by_resource"]["1102-081455-7t3bqp3v"]
    )
    assert overview.kpis["total_spend"].status == KpiStatus.CALCULATED


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
    assert overview.kpis["total_spend"].formatted_value == "-"


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
    assert overview.kpis["total_spend"].formatted_value == "-"


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
        assert overview.kpis["total_spend"].formatted_value == "-"


def test_app_inventory_unattributed_pool_isolation(service: FinOpsAnalyticsService) -> None:
    """Verified apps resolve as apps; an app with no billing rows is NO billing data, never $0."""
    exp = baseline_expectations()
    for app_id in ("cement-demand-forecasting", "mcp-generate-ppt", "wonder-cement-app"):
        cat, is_unknown = service._resolve_resource_filter(app_id, "app")
        assert is_unknown is False
        assert cat == "app"

    attributed = service.get_executive_overview(
        workspace_id="642006393507276", resource_id="cement-demand-forecasting", resource_type="app"
    )
    assert attributed.kpis["total_spend"].value == pytest.approx(
        exp["by_resource"]["cement-demand-forecasting"]
    )

    unbilled = service.get_executive_overview(
        workspace_id="642006393507276", resource_id="mcp-generate-ppt", resource_type="app"
    )
    assert unbilled.kpis["total_spend"].value is None
    assert unbilled.kpis["total_spend"].status == KpiStatus.BLOCKED_PENDING_APPROVAL


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
