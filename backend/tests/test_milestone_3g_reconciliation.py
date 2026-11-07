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


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return FinOpsAnalyticsService()


def test_defect_3f_01_dbu_effective_rate_reconciliation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-01: Verify DBU effective rate reconciles to $2.000/DBU ($176,840 / 88,420 DBU)."""
    cost_data = service.get_cost_explorer()
    eff_kpi = cost_data.kpis["effective_rate"]
    gross_kpi = cost_data.kpis["gross_consumption"]
    overview_data = service.get_executive_overview()
    dbu_kpi = overview_data.kpis["dbu_consumption"]

    assert gross_kpi.value == 176840.0
    assert dbu_kpi.value == 88420.0
    # $176,840 / 88,420 DBU = $2.000 / DBU
    expected_rate = round(gross_kpi.value / dbu_kpi.value, 3)
    assert eff_kpi.value == 2.0
    assert eff_kpi.value == expected_rate
    assert eff_kpi.formatted_value == "$2.000"
    assert eff_kpi.unit == "USD/DBU"


def test_defect_3f_02_cost_explorer_ledger_reconciliation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-02: Verify 24-item billing ledger sums exactly to $176,840.00 Gross Consumption."""
    cost_data = service.get_cost_explorer()
    ledger = cost_data.billing_ledger

    assert len(ledger) == 24
    total_ledger_spend = sum(item.effective_cost for item in ledger)
    assert total_ledger_spend == 176840.0
    assert cost_data.kpis["gross_consumption"].value == total_ledger_spend

    # Verify DBU sum from ledger
    total_dbus = sum(item.usage_qty for item in ledger if item.unit == "DBU")
    assert total_dbus == 88420.0


def test_defect_3f_03_unknown_resource_handling(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-03: Querying an unknown resource must return typed NO_DATA, not fallback to full workspace."""
    overview = service.get_executive_overview(
        resource_id="nonexistent-resource-xyz-999", resource_type="cluster"
    )
    spend_kpi = overview.kpis["total_spend"]
    assert spend_kpi.value is None
    assert spend_kpi.formatted_value == "No data available"
    assert spend_kpi.status == KpiStatus.NO_DATA
    assert len(overview.spend_trend) == 0
    assert len(overview.spend_composition) == 0

    cost = service.get_cost_explorer(
        resource_id="nonexistent-resource-xyz-999", resource_type="cluster"
    )
    assert cost.kpis["gross_consumption"].value is None
    assert cost.kpis["gross_consumption"].formatted_value == "No data available"
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
    """DEFECT-3F-05: AI spend ($38,460) must be consistent across Overview KPI, Composition, and AI Economics."""
    overview = service.get_executive_overview()
    overview_ai_kpi = overview.kpis["ai_spend"]
    assert overview_ai_kpi.value == 38460.0

    # Spend composition AI family
    ai_comp = next((s for s in overview.spend_composition if s["family"] == "AI / GenAI"), None)
    assert ai_comp is not None
    assert ai_comp["amount"] == 38460.0
    assert ai_comp["share"] == 0.135

    # AI Economics total AI spend KPI
    ai_data = service.get_ai_economics()
    ai_spend_kpi = ai_data.kpis["ai_spend"]
    assert ai_spend_kpi.value == 38460.0


def test_defect_3f_06_token_volume_and_unit_isolation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-06: Token volumes reconcile to 10.28B total (8.42B prompt, 1.86B completion), strict unit isolation."""
    ai_data = service.get_ai_economics()
    input_tokens_kpi = ai_data.kpis["input_tokens"]
    output_tokens_kpi = ai_data.kpis["output_tokens"]

    assert input_tokens_kpi.value == 8_420_000_000.0
    assert input_tokens_kpi.unit == "tokens"
    assert output_tokens_kpi.value == 1_860_000_000.0
    assert output_tokens_kpi.unit == "tokens"

    total_tokens = input_tokens_kpi.value + output_tokens_kpi.value
    assert total_tokens == 10_280_000_000.0  # 10.28B tokens

    # Average cost per 1K tokens across 10.28B tokens with $38,460 spend = $0.0037
    avg_cost_kpi = ai_data.kpis["cost_per_1k_tokens"]
    assert avg_cost_kpi.value == 0.0037
    assert avg_cost_kpi.unit == "USD/1K"


def test_defect_3f_07_savings_opportunity_reconciliation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-07: Savings opportunity KPI ($24,530) equals exact sum of recommendation decisions."""
    overview = service.get_executive_overview()
    savings_kpi = overview.kpis["savings_opportunity"]

    advisor = service.get_optimization_advisor()
    decisions_sum = sum(d.estimated_savings_monthly for d in advisor.recommendations)

    assert savings_kpi.value == 24530.0
    assert decisions_sum == 24530.0
    assert savings_kpi.value == decisions_sum


def test_defect_3f_08_anomaly_count_reconciliation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-08: Anomaly count KPI (3) equals exact count of detected anomalies."""
    overview = service.get_executive_overview()
    anomaly_kpi = overview.kpis["anomalies"]

    anom_data = service.get_anomaly_detection()
    anomalies_count = len(anom_data.anomalies)

    assert anomaly_kpi.value == 3.0
    assert anomalies_count == 3
    assert int(anomaly_kpi.value) == anomalies_count


def test_defect_3f_09_child_scope_filtering_across_modules(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-09: Child scope filtering propagates across all modules returning scoped figures."""
    target_cluster = "1102-081455-7t3bqp3v"
    target_type = "cluster"

    # Module 1 Overview scoped
    ov = service.get_executive_overview(resource_id=target_cluster, resource_type=target_type)
    assert ov.kpis["total_spend"].value == 24600.0

    # Module 2 Cost Explorer scoped
    ce = service.get_cost_explorer(resource_id=target_cluster, resource_type=target_type)
    assert ce.kpis["gross_consumption"].value == 24600.0

    # Module 4 Compute scoped
    cw = service.get_compute_warehouses(resource_id=target_cluster, resource_type=target_type)
    assert cw.kpis["compute_spend"].value == 24600.0

    # Module 8 Optimization Advisor scoped
    adv = service.get_optimization_advisor(resource_id=target_cluster, resource_type=target_type)
    assert len(adv.recommendations) >= 1
    assert any("adf-deaccelator-compute" in d.title for d in adv.recommendations)

    # Module 10 Anomaly Detection scoped
    anom = service.get_anomaly_detection(resource_id=target_cluster, resource_type=target_type)
    assert len(anom.anomalies) == 1
    assert anom.anomalies[0].resource == "adf-deaccelator-compute"


def test_defect_3f_10_compute_spend_reconciliation(service: FinOpsAnalyticsService) -> None:
    """DEFECT-3F-10: Module 4 Compute spend reconciles to $108,155 for workspace scope."""
    cw = service.get_compute_warehouses()
    compute_spend_kpi = cw.kpis["compute_spend"]
    assert compute_spend_kpi.value == 108155.0
    assert compute_spend_kpi.formatted_value == "$108,155"

    overview = service.get_executive_overview()
    compute_comp = next((s for s in overview.spend_composition if s["family"] == "Compute"), None)
    assert compute_comp is not None
    assert compute_comp["amount"] == 108155.0


def test_canonical_kpi_contract_and_lineage(service: FinOpsAnalyticsService) -> None:
    """Verify CanonicalKpiResponse contains complete audit lineage, formula, and caveats."""
    canonical_spend = service.get_canonical_kpi("databricks_spend")
    assert isinstance(canonical_spend, CanonicalKpiResponse)
    assert canonical_spend.metric_id == "databricks_spend"
    assert canonical_spend.metric.value == 176840.0
    assert canonical_spend.metric.unit == "USD"
    assert canonical_spend.metric.currency == "USD"
    assert canonical_spend.metric.aggregation_method == "SUM"
    assert canonical_spend.metric.formula == "dbu_consumption * blended_rate"
    assert canonical_spend.metric.status == KpiStatus.BASELINE
    assert canonical_spend.metric.workspace_id == "642006393507276"
    assert canonical_spend.metric.last_refreshed is not None

    canonical_dbu = service.get_canonical_kpi("dbu_consumption")
    assert canonical_dbu.metric_id == "dbu_consumption"
    assert canonical_dbu.metric.value == 88420.0
    assert canonical_dbu.metric.unit == "DBU"
    assert canonical_dbu.metric.formula == "sum(system.billing.usage.usage_quantity)"

    canonical_savings = service.get_canonical_kpi("savings_opportunity")
    assert canonical_savings.metric_id == "savings_opportunity"
    assert canonical_savings.metric.value == 24530.0
    assert canonical_savings.metric.formula == "sum(decisions.estimated_savings_monthly)"
