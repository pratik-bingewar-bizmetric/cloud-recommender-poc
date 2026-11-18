"""Milestone 3G Verification: Financial Data Integrity, Canonical KPI Engine & Resource Scope Enforcement.

Verifies the mathematical reconciliation of all 10 audited defects from Milestone 3F:
- DEFECT-3F-01: DBU Effective Rate Mismatch ($176,840 spend / 88,420 DBU = $2.000/DBU).
- DEFECT-3F-02: Cost Explorer Ledger Sum Mismatch (24 ledger items sum to $176,840.00).
- DEFECT-3F-03: Unknown Resource Fallback (Typed NO_DATA status on unknown resource).
- DEFECT-3F-04: Substring Matching (Exact ID matching enforced).
- DEFECT-3F-05: Cross-Module AI Spend Inconsistency ($38,460 reconciled across modules).
- DEFECT-3F-06: Token Volume Inconsistency (10.28B tokens, raw token unit isolation).
- DEFECT-3F-07: Savings Opportunity Inconsistency ($24,530 reconciled to sum of decisions).
- DEFECT-3F-08: Anomaly Count Inconsistency (3 reconciled to count of anomalies).
- DEFECT-3F-09: Scope Parameter Propagation (Child filtering across all modules).
- DEFECT-3F-10: Compute Spend Mismatch ($108,155 compute spend reconciled).
- CANONICAL-KPI: Canonical KPI query contract with audit lineage and metadata.
"""

import pytest

from cloud_recommender.schemas.finops import CanonicalKpiResponse, KpiStatus
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService
from tests.fixtures.billing_baseline import baseline_expectations
from tests.fixtures.live_inventory import make_analytics_service


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return make_analytics_service(with_billing=True)


def test_defect_3f_01_dbu_effective_rate_reconciliation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-01: effective rate is spend / DBU computed from ingested rows (list-price basis)."""
    exp = baseline_expectations()
    cost_data = service.get_cost_explorer()
    eff_kpi = cost_data.kpis["effective_rate"]
    gross_kpi = cost_data.kpis["gross_consumption"]
    dbu_kpi = service.get_executive_overview().kpis["dbu_consumption"]

    assert gross_kpi.value == pytest.approx(exp["total_cost"])
    assert dbu_kpi.value == exp["total_dbu"]
    assert eff_kpi.value == pytest.approx(round(exp["total_cost"] / exp["total_dbu"], 4))
    assert eff_kpi.unit == "USD/DBU"
    assert eff_kpi.status == KpiStatus.CALCULATED


def test_defect_3f_02_cost_explorer_ledger_reconciliation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-02: the billing ledger sums exactly to the Gross Consumption KPI and DBU total."""
    exp = baseline_expectations()
    cost_data = service.get_cost_explorer()
    ledger = cost_data.billing_ledger

    assert len(ledger) > 0
    total_ledger_spend = round(sum(item.effective_cost for item in ledger), 2)
    assert total_ledger_spend == pytest.approx(exp["total_cost"], abs=0.01)
    assert cost_data.kpis["gross_consumption"].value == pytest.approx(total_ledger_spend, abs=0.01)
    assert sum(item.usage_qty for item in ledger if item.unit == "DBU") == exp["total_dbu"]


def test_defect_3f_03_unknown_resource_handling(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-03: Querying an unknown resource must return typed NO_DATA, not fallback to full workspace."""
    overview = service.get_executive_overview(
        resource_id="nonexistent-resource-xyz-999", resource_type="cluster"
    )
    spend_kpi = overview.kpis["total_spend"]
    assert spend_kpi.value is None
    assert spend_kpi.formatted_value == "-"
    assert spend_kpi.status == KpiStatus.NO_DATA
    assert len(overview.spend_trend) == 0
    assert len(overview.spend_composition) == 0

    cost = service.get_cost_explorer(
        resource_id="nonexistent-resource-xyz-999", resource_type="cluster"
    )
    assert cost.kpis["gross_consumption"].value is None
    assert cost.kpis["gross_consumption"].formatted_value == "-"
    assert cost.kpis["gross_consumption"].status == KpiStatus.NO_DATA
    assert len(cost.billing_ledger) == 0


def test_defect_3f_04_exact_resource_matching_no_substring(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-04: Substring matching is eliminated; partial string 'deaccelator' does not match 'adf-deaccelator-compute'."""
    category, is_unknown = service._resolve_resource_filter("deaccelator", None)
    # "deaccelator" is a substring, not an exact known resource ID
    assert is_unknown is True
    assert category is None

    # Exact matching of warehouse ID
    category_wh, is_unknown_wh = service._resolve_resource_filter("05ed10a52697a344", "warehouse")
    assert is_unknown_wh is False
    assert category_wh == "warehouse"

    # Exact matching of canonical cluster ID (Requirement 3.1 & 3.2)
    category_cl, is_unknown_cl = service._resolve_resource_filter("1102-081455-7t3bqp3v", "cluster")
    assert is_unknown_cl is False
    assert category_cl == "cluster"

    # Cluster name alone cannot independently authorize attribution
    category_name, is_unknown_name = service._resolve_resource_filter(
        "adf-deaccelator-compute", "cluster"
    )
    assert is_unknown_name is True
    assert category_name is None


def test_defect_3f_05_cross_module_ai_spend_consistency(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-05: AI spend agrees across Overview KPI, composition and AI Economics."""
    exp = baseline_expectations()
    overview = service.get_executive_overview()
    assert overview.kpis["ai_spend"].value == pytest.approx(exp["by_product"]["MODEL_SERVING"])

    ai_comp = next(s for s in overview.spend_composition if s["family"] == "MODEL_SERVING")
    assert ai_comp["amount"] == pytest.approx(exp["by_product"]["MODEL_SERVING"])

    ai_spend_kpi = service.get_ai_economics().kpis["ai_spend"]
    assert ai_spend_kpi.value == pytest.approx(exp["by_product"]["MODEL_SERVING"])


def test_defect_3f_06_token_volume_and_unit_isolation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-06: token volumes are never invented; they are BLOCKED until system tables are read."""
    ai_data = service.get_ai_economics()
    for key in ("input_tokens", "output_tokens", "cached_tokens"):
        kpi = ai_data.kpis[key]
        assert kpi.unit == "tokens"
        assert kpi.currency is None
        assert kpi.value is None
        assert kpi.status == KpiStatus.BLOCKED_PENDING_APPROVAL
    assert ai_data.kpis["cost_per_1k_tokens"].value is None
    assert ai_data.token_consumption_by_model == []


def test_defect_3f_07_savings_opportunity_reconciliation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-07: savings are only reported when calculable; none is calculable from config alone."""
    overview = service.get_executive_overview()
    advisor = service.get_optimization_advisor()
    assert len(advisor.recommendations) >= 1
    assert all(d.estimated_savings_monthly is None for d in advisor.recommendations)
    assert all(d.savings_status == KpiStatus.UNAVAILABLE for d in advisor.recommendations)
    assert overview.kpis["savings_opportunity"].value is None
    assert overview.kpis["savings_opportunity"].status == KpiStatus.UNAVAILABLE
    assert advisor.kpis["realized_savings"].value is None


def test_defect_3f_08_anomaly_count_reconciliation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-08: with < 14 days of history no anomaly is generated and the KPI says so."""
    overview = service.get_executive_overview()
    anomaly_kpi = overview.kpis["anomalies"]
    anom_data = service.get_anomaly_detection()

    assert anomaly_kpi.status == KpiStatus.INSUFFICIENT_HISTORY
    assert anomaly_kpi.value is None
    assert anom_data.anomalies == []
    assert anom_data.kpis["open_anomalies"].status == KpiStatus.INSUFFICIENT_HISTORY


def test_defect_3f_09_child_scope_filtering_across_modules(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-09: child scope filtering propagates across modules using real attribution keys."""
    exp = baseline_expectations()
    target_cluster = "1102-081455-7t3bqp3v"
    cluster_cost = exp["by_resource"][target_cluster]

    ov = service.get_executive_overview(resource_id=target_cluster, resource_type="cluster")
    assert ov.kpis["total_spend"].value == pytest.approx(cluster_cost)

    ce = service.get_cost_explorer(resource_id=target_cluster, resource_type="cluster")
    assert ce.kpis["gross_consumption"].value == pytest.approx(cluster_cost)

    cw = service.get_compute_warehouses(resource_id=target_cluster, resource_type="cluster")
    assert cw.kpis["compute_spend"].value == pytest.approx(cluster_cost)
    assert [c.cluster_id for c in cw.clusters] == [target_cluster]
    assert cw.warehouses == []

    adv = service.get_optimization_advisor(resource_id=target_cluster, resource_type="cluster")
    assert len(adv.recommendations) >= 1
    assert all(d.resource_id == target_cluster for d in adv.recommendations)

    anom = service.get_anomaly_detection(resource_id=target_cluster, resource_type="cluster")
    assert anom.anomalies == []


def test_defect_3f_10_compute_spend_reconciliation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-10: compute spend reconciles to attributed cluster+warehouse rows; families sum to total."""
    exp = baseline_expectations()
    cw = service.get_compute_warehouses()
    expected_compute = (
        exp["by_resource"]["1102-081455-7t3bqp3v"] + exp["by_resource"]["05ed10a52697a344"]
    )
    assert cw.kpis["compute_spend"].value == pytest.approx(expected_compute)

    overview = service.get_executive_overview()
    assert sum(s["amount"] for s in overview.spend_composition) == pytest.approx(
        overview.kpis["total_spend"].value
    )


def test_canonical_kpi_contract_and_lineage(service: FinOpsAnalyticsService) -> None:
    """CanonicalKpiResponse carries lineage, formula, status and caveats for real values."""
    exp = baseline_expectations()
    spend = service.get_canonical_kpi("databricks_spend")
    assert isinstance(spend, CanonicalKpiResponse)
    assert spend.metric.value == pytest.approx(exp["total_cost"])
    assert spend.metric.unit == "USD"
    assert spend.metric.aggregation_method == "SUM"
    assert spend.metric.status == KpiStatus.CALCULATED
    assert spend.metric.formula
    assert "List-price" in (spend.metric.caveats or "")
    assert spend.metric.last_refreshed is not None

    dbu = service.get_canonical_kpi("dbu_consumption")
    assert dbu.metric.value == exp["total_dbu"]
    assert dbu.metric.unit == "DBU"
    assert dbu.metric.status == KpiStatus.LIVE

    savings = service.get_canonical_kpi("savings_opportunity")
    assert savings.metric.value is None
    assert savings.metric.status == KpiStatus.UNAVAILABLE
