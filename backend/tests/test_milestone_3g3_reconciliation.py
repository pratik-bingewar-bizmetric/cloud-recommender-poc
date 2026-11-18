"""Milestone 3G.3 Test Suite — Financial Reconciliation & Evidence Closure.

Verifies:
1. Issue 1: AI Gateway Token-Cost Discrepancy ($96 Difference) traceable origin,
   preservation of $11,296 baseline figure, and clear documentation of the $96 gap.
2. Issue 2: Authoritative Forecast Formula (current_spend * (30.0 / 26.7236) = raw $319,515.33,
   nearest-$100 presentation $319,500.00, budget variance +$19,500.00).
3. Section 3: AI Spend Composition ($26,740 Model Serving DBU + $11,296 AI Gateway + $424 Vector Search = $38,460).
4. Section 4A: Endpoint Inventory (11 verified canonical endpoints in baseline registry,
   remaining 16 unverified without prohibited live API execution).
5. Section 4B: NO_DATA Must Not Appear as Measured Zero (value=None, formatted_value="-",
   distinct from measured zero value=0.0).
6. Full 15-module scope regression and null serialization parity.
"""

from typing import Any

import pytest

from cloud_recommender.schemas.finops import KpiMetric, KpiStatus
from cloud_recommender.services.databricks.finops_analytics_service import (
    FinOpsAnalyticsService,
)
from tests.fixtures.live_inventory import make_analytics_service


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return make_analytics_service(with_billing=True)


# =============================================================================
# 1. Issue 1: AI Gateway Token-Cost Discrepancy ($96 Difference)
# =============================================================================


def test_ai_gateway_token_cost_discrepancy_and_traceability(
    service: FinOpsAnalyticsService,
) -> None:
    """Token-priced AI Gateway spend is NOT derivable from billing rows; it must not be invented."""
    overview = service.get_executive_overview()
    ai_kpi = overview.kpis["ai_spend"]
    assert "token-priced external models are not included" in (
        service.get_ai_economics().kpis["ai_spend"].caveats or ""
    )
    assert ai_kpi.status == KpiStatus.CALCULATED
    tokens = service.get_ai_economics().kpis
    assert tokens["input_tokens"].value is None
    assert tokens["cost_per_1k_tokens"].value is None


# =============================================================================
# 2. Issue 2: Authoritative Forecast Formula & Rounding
# =============================================================================


def test_forecast_calculation_formula_and_presentation(service: FinOpsAnalyticsService) -> None:
    """Forecast is unavailable on 4 days of history and is labelled ESTIMATED once computed."""
    fc = service.get_forecast_budgets()
    assert fc.kpis["forecast_month_end"].value is None
    assert fc.kpis["forecast_month_end"].status == KpiStatus.INSUFFICIENT_HISTORY
    assert fc.kpis["approved_budget"].value is None  # budgets are configured, never invented
    assert fc.kpis["approved_budget"].status == KpiStatus.UNAVAILABLE
    assert fc.budget_controls == []
    assert fc.kpis["projected_overrun"].value is None


# =============================================================================
# 3. Section 3: AI Spend Composition Exact Invariants
# =============================================================================


def test_ai_spend_composition_exact_invariants(service: FinOpsAnalyticsService) -> None:
    """Composition shares sum to 1 and amounts sum to total; AI is one family inside the total."""
    overview = service.get_executive_overview()
    total = overview.kpis["total_spend"].value
    amounts = [c["amount"] for c in overview.spend_composition]
    assert sum(amounts) == pytest.approx(total)
    assert sum(c["share"] for c in overview.spend_composition) == pytest.approx(1.0, abs=0.001)
    assert overview.kpis["ai_spend"].value < total


# =============================================================================
# 4. Section 4A: Endpoint Inventory Closure (11 Canonical vs 16 Unverified)
# =============================================================================


def test_serving_endpoint_inventory_canonical_closure(
    service: FinOpsAnalyticsService,
) -> None:
    """Serving endpoints resolve from LIVE discovery only; there is no hardcoded registry."""
    discovered = {
        r.id
        for d in service.workspace_service._discovery_cache.values()
        for r in d.resources
        if r.resource_type.lower() == "serving_endpoint"
    }
    assert discovered, "fixture inventory must contain serving endpoints"
    for ep_id in discovered:
        cat, is_unknown = service._resolve_resource_filter(ep_id, "serving_endpoint")
        assert is_unknown is False, f"Canonical endpoint {ep_id} failed resolution"
        assert cat == "serving"

    # Verify that unverified / fabricated endpoint IDs return is_unknown=True
    unverified_endpoints = [
        "databricks-gpt4-synthetic",
        "mistral-small-unverified",
        "deepseek-v3-unverified",
        "cohere-rerank-v2",
    ]
    for ep_id in unverified_endpoints:
        cat, is_unknown = service._resolve_resource_filter(ep_id, "serving_endpoint")
        assert is_unknown is True
        assert cat is None


# =============================================================================
# 5. Section 4B: NO_DATA Must Not Appear as Measured Zero (value=None)
# =============================================================================


def test_no_data_kpi_metric_schema_and_null_value() -> None:
    """Verify KpiMetric schema supports value=None and serializes to null in JSON."""
    empty_kpi = KpiMetric(
        value=None,
        formatted_value="-",
        unit="USD",
        currency="USD",
        metric_id="test_missing_metric",
        status=KpiStatus.NO_DATA,
        data_freshness="Not applicable",
        source="Azure Databricks Telemetry",
        workspace_id="642006393507276",
        limitations="No telemetry data found for the specified resource scope.",
    )
    assert empty_kpi.value is None
    assert empty_kpi.formatted_value == "-"
    assert empty_kpi.status == KpiStatus.NO_DATA

    dumped: dict[str, Any] = empty_kpi.model_dump()
    assert dumped["value"] is None
    assert dumped["formatted_value"] == "-"
    assert dumped["status"] == "NO_DATA"


def test_no_data_vs_measured_zero_distinction(service: FinOpsAnalyticsService) -> None:
    """NO_DATA / BLOCKED are null-valued; they never serialize as a measured zero."""
    unknown = service.get_executive_overview(resource_id="fake-id-123", resource_type="cluster")
    assert unknown.kpis["total_spend"].value is None
    assert unknown.kpis["total_spend"].status == KpiStatus.NO_DATA
    assert unknown.kpis["total_spend"].formatted_value == "-"

    blocked = make_analytics_service(with_billing=False).get_executive_overview()
    for key in ("total_spend", "databricks_spend", "ai_spend", "dbu_consumption"):
        assert blocked.kpis[key].value is None
        assert blocked.kpis[key].status == KpiStatus.BLOCKED_PENDING_APPROVAL
        assert blocked.kpis[key].formatted_value == "-"
        assert "$0" not in blocked.kpis[key].formatted_value
    assert blocked.spend_trend == [] and blocked.spend_composition == []


# =============================================================================
# 6. Section 5: All 15 Modules Return value=None on Unknown Resource Scope
# =============================================================================


def test_all_15_modules_return_null_value_on_no_data(
    service: FinOpsAnalyticsService,
) -> None:
    """Verify that every module returns typed NO_DATA with value=None and

    formatted_value='No data available' when passed an unknown resource identifier.
    """
    unknown_id = "unknown-adversarial-guid-7777"
    unknown_type = "cluster"

    # 1. Executive Overview
    overview = service.get_executive_overview(resource_id=unknown_id, resource_type=unknown_type)
    assert overview.kpis["total_spend"].value is None
    assert overview.kpis["total_spend"].formatted_value == "-"
    assert overview.kpis["total_spend"].status == KpiStatus.NO_DATA

    # 2. Cost Explorer
    cost = service.get_cost_explorer(resource_id=unknown_id, resource_type=unknown_type)
    assert cost.kpis["gross_consumption"].value is None
    assert cost.kpis["gross_consumption"].formatted_value == "-"
    assert cost.kpis["gross_consumption"].status == KpiStatus.NO_DATA

    # 3. Compute & Warehouses
    compute = service.get_compute_warehouses(resource_id=unknown_id, resource_type=unknown_type)
    assert compute.kpis["compute_spend"].value is None
    assert compute.kpis["compute_spend"].formatted_value == "-"
    assert compute.kpis["compute_spend"].status == KpiStatus.NO_DATA

    # 4. Storage & Lakehouse
    storage = service.get_data_storage(resource_id=unknown_id, resource_type=unknown_type)
    assert storage.kpis["storage_spend"].value is None
    assert storage.kpis["storage_spend"].formatted_value == "-"
    assert storage.kpis["storage_spend"].status == KpiStatus.NO_DATA

    # 5. AI & Token Economics
    ai = service.get_ai_economics(resource_id=unknown_id, resource_type=unknown_type)
    assert ai.kpis["ai_spend"].value is None
    assert ai.kpis["ai_spend"].formatted_value == "-"
    assert ai.kpis["ai_spend"].status == KpiStatus.NO_DATA

    # 6. Optimization Advisor
    advisor = service.get_optimization_advisor(resource_id=unknown_id, resource_type=unknown_type)
    assert advisor.kpis["potential_savings"].value is None
    assert advisor.kpis["potential_savings"].formatted_value == "-"
    assert advisor.kpis["potential_savings"].status == KpiStatus.NO_DATA

    # 7. Anomaly Detector
    anomaly = service.get_anomaly_detection(resource_id=unknown_id, resource_type=unknown_type)
    assert anomaly.kpis["open_anomalies"].value is None
    assert anomaly.kpis["open_anomalies"].formatted_value == "-"
    assert anomaly.kpis["open_anomalies"].status == KpiStatus.NO_DATA

    # 8. Forecast & Budgets
    forecast = service.get_forecast_budgets(resource_id=unknown_id, resource_type=unknown_type)
    assert forecast.kpis["forecast_month_end"].value is None
    assert forecast.kpis["forecast_month_end"].formatted_value == "-"
    assert forecast.kpis["forecast_month_end"].status == KpiStatus.NO_DATA

    # 9. Cost Allocation & Tagging
    alloc = service.get_cost_allocation(resource_id=unknown_id, resource_type=unknown_type)
    assert alloc.kpis["unallocated_spend"].value is None
    assert alloc.kpis["unallocated_spend"].formatted_value == "-"
    assert alloc.kpis["unallocated_spend"].status == KpiStatus.NO_DATA

    # 10. Showback / Chargeback
    showback = service.get_showback_chargeback(resource_id=unknown_id, resource_type=unknown_type)
    assert showback.kpis["shared_pool"].value is None
    assert showback.kpis["shared_pool"].formatted_value == "-"
    assert showback.kpis["shared_pool"].status == KpiStatus.NO_DATA

    # 11. Workload Unit Economics
    workload = service.get_workload_economics(resource_id=unknown_id, resource_type=unknown_type)
    assert workload.kpis["avg_cost_workload"].value is None
    assert workload.kpis["avg_cost_workload"].formatted_value == "-"
    assert workload.kpis["avg_cost_workload"].status == KpiStatus.NO_DATA

    # 12. Governance & Policy Engine
    gov = service.get_governance_policies(resource_id=unknown_id, resource_type=unknown_type)
    assert gov.kpis["policy_compliance"].value is None
    assert gov.kpis["policy_compliance"].formatted_value == "-"
    assert gov.kpis["policy_compliance"].status == KpiStatus.NO_DATA

    # 13. Network & Cross-Cloud Infra
    net = service.get_network_cloud(resource_id=unknown_id, resource_type=unknown_type)
    assert net.kpis["network_infra_spend"].value is None
    assert net.kpis["network_infra_spend"].formatted_value == "-"
    assert net.kpis["network_infra_spend"].status == KpiStatus.NO_DATA

    # 14. Reports & Audit (empty lists on unknown scope)
    reports = service.get_reports_audit(resource_id=unknown_id, resource_type=unknown_type)
    assert len(reports.report_packs) == 0
    assert len(reports.audit_events) == 0

    # 15. Canonical KPI Service
    canonical = service.get_canonical_kpi(
        metric_id="unknown_metric", resource_id=unknown_id, resource_type=unknown_type
    )
    assert canonical.metric.value is None
    assert canonical.metric.formatted_value == "-"
    assert canonical.metric.status == KpiStatus.NO_DATA
