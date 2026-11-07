"""Milestone 3G.3 Test Suite — Financial Reconciliation & Evidence Closure.

Verifies:
1. Issue 1: AI Gateway Token-Cost Discrepancy ($96 Difference) traceable origin,
   preservation of $11,296 baseline figure, and clear documentation of the $96 gap.
2. Issue 2: Authoritative Forecast Formula (current_spend * (30.0 / 26.7236) = raw $319,515.33,
   nearest-$100 presentation $319,500.00, budget variance +$19,500.00).
3. Section 3: AI Spend Composition ($26,740 Model Serving DBU + $11,296 AI Gateway + $424 Vector Search = $38,460).
4. Section 4A: Endpoint Inventory (11 verified canonical endpoints in baseline registry,
   remaining 16 unverified without prohibited live API execution).
5. Section 4B: NO_DATA Must Not Appear as Measured Zero (value=None, formatted_value="No data available",
   distinct from measured zero value=0.0).
6. Full 15-module scope regression and null serialization parity.
"""

from typing import Any

import pytest

from cloud_recommender.schemas.finops import KpiMetric, KpiStatus
from cloud_recommender.services.databricks.finops_analytics_service import (
    FinOpsAnalyticsService,
)


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return FinOpsAnalyticsService()


# =============================================================================
# 1. Issue 1: AI Gateway Token-Cost Discrepancy ($96 Difference)
# =============================================================================


def test_ai_gateway_token_cost_discrepancy_and_traceability(
    service: FinOpsAnalyticsService,
) -> None:
    """Validate that AI Gateway spend ($11,296) and bottom-up token pricing ($11,200)

    are reconciled with the $96 difference explicitly documented as unverified baseline variance.
    """
    overview = service.get_executive_overview()
    ai_spend_kpi = overview.kpis["ai_spend"]

    # 1. Top-down AI spend composition: $26,740 (Serving DBU) + $11,296 (Gateway) + $424 (Vector) = $38,460
    assert ai_spend_kpi.value == 38460.0
    serving_dbu_spend = 26740.0
    ai_gateway_spend = 11296.0
    vector_search_spend = 424.0
    assert serving_dbu_spend + ai_gateway_spend + vector_search_spend == 38460.0

    # 2. Bottom-up token calculation: 8.42B prompt tokens ($0.0008/1K) + 1.86B completion tokens ($0.0024/1K)
    prompt_tokens = 8_420_000_000
    completion_tokens = 1_860_000_000
    rate_prompt = 0.0008 / 1000.0  # $0.0008 per 1K
    rate_completion = 0.0024 / 1000.0  # $0.0024 per 1K

    calculated_prompt_cost = prompt_tokens * rate_prompt  # $6,736.00
    calculated_completion_cost = completion_tokens * rate_completion  # $4,464.00
    calculated_bottom_up_token_cost = (
        calculated_prompt_cost + calculated_completion_cost
    )  # $11,200.00

    assert calculated_prompt_cost == pytest.approx(6736.0)
    assert calculated_completion_cost == pytest.approx(4464.0)
    assert calculated_bottom_up_token_cost == pytest.approx(11200.0)

    # 3. Discrepancy calculation: $11,296.00 - $11,200.00 = $96.00
    discrepancy = ai_gateway_spend - round(calculated_bottom_up_token_cost, 2)
    assert discrepancy == 96.0

    # 4. Verification that reported figure ($11,296.00) is NOT artificially mutated
    assert "ai_gateway_external_tokens ($11,296.00)" in (ai_spend_kpi.formula or "")
    assert "$96 difference" in (ai_spend_kpi.limitations or "")
    assert "$11,200.00" in (ai_spend_kpi.limitations or "")

    # 5. Token module consistency
    token_module = service.get_ai_economics()
    assert token_module.kpis["ai_spend"].value == 38460.0
    assert "$96 unverified baseline variance" in (token_module.kpis["ai_spend"].limitations or "")
    assert token_module.kpis["input_tokens"].value == 8_420_000_000.0
    assert token_module.kpis["output_tokens"].value == 1_860_000_000.0


# =============================================================================
# 2. Issue 2: Authoritative Forecast Formula & Rounding
# =============================================================================


def test_forecast_calculation_formula_and_presentation(
    service: FinOpsAnalyticsService,
) -> None:
    """Validate authoritative forecast formula: current_spend * (30.0 / 26.7236)

    yielding raw $319,515.33, rounded to nearest $100 milestone $319,500.00,
    with +$19,500.00 budget variance against $300,000 budget.
    """
    current_spend = 284620.0
    obs_days = 26.7236
    forecast_days = 30.0
    approved_budget = 300000.0

    # 1. Authoritative mathematical calculation
    multiplier = forecast_days / obs_days
    assert multiplier == pytest.approx(1.122603242, rel=1e-6)
    # Confirm old inconsistent multiplier 1.1225423 is eliminated
    assert abs(multiplier - 1.1225423) > 5e-5

    raw_forecast = current_spend * multiplier
    assert raw_forecast == pytest.approx(319515.334, rel=1e-4)

    rounded_forecast = round(raw_forecast / 100.0) * 100.0
    assert rounded_forecast == 319500.0

    budget_variance = rounded_forecast - approved_budget
    assert budget_variance == 19500.0

    # 2. Executive Overview verification
    overview = service.get_executive_overview()
    forecast_kpi = overview.kpis["forecast_spend"]

    assert forecast_kpi.value == 319500.0
    assert forecast_kpi.formatted_value == "$319,500"
    assert forecast_kpi.change_absolute == 19500.0
    assert "19.5K above budget" in (forecast_kpi.delta_label or "")
    assert "30.0 / 26.7236" in (forecast_kpi.formula or "")
    assert "319,515.33" in (forecast_kpi.formula or "")
    assert "319,515.33" in (forecast_kpi.limitations or "")
    assert "319,500" in (forecast_kpi.limitations or "")

    # 3. Forecast & Budgets module verification
    forecast_module = service.get_forecast_budgets()
    f_kpi = forecast_module.kpis["forecast_month_end"]
    assert f_kpi.value == 319500.0
    assert f_kpi.formatted_value == "$319,500"
    assert f_kpi.change_absolute == 19500.0
    assert "$19,500 over budget" in (f_kpi.delta_label or "")
    assert "319,515.33" in (f_kpi.formula or "")
    assert "319,515.33" in (f_kpi.limitations or "")


# =============================================================================
# 3. Section 3: AI Spend Composition Exact Invariants
# =============================================================================


def test_ai_spend_composition_exact_invariants(
    service: FinOpsAnalyticsService,
) -> None:
    """Verify AI spend composition:

    $26,740 (Model Serving DBU) + $11,296 (AI Gateway external) + $424 (Vector Search) = $38,460.
    """
    overview = service.get_executive_overview()
    ai_kpi = overview.kpis["ai_spend"]

    serving_component = 26740.0
    gateway_component = 11296.0
    vector_search_component = 424.0
    total_ai_spend = serving_component + gateway_component + vector_search_component

    assert total_ai_spend == 38460.0
    assert ai_kpi.value == total_ai_spend
    assert ai_kpi.formatted_value == "$38,460"

    # Cross-reference with Model Serving DBU ledger records (4 windows summing to $26,740)
    cost = service.get_cost_explorer()
    serving_ledger_items = [item for item in cost.billing_ledger if "Model Serving" in item.product]
    assert len(serving_ledger_items) == 4
    assert sum(item.effective_cost for item in serving_ledger_items) == 26740.0


# =============================================================================
# 4. Section 4A: Endpoint Inventory Closure (11 Canonical vs 16 Unverified)
# =============================================================================


def test_serving_endpoint_inventory_canonical_closure(
    service: FinOpsAnalyticsService,
) -> None:
    """Validate that KNOWN_SERVING_ENDPOINTS contains exactly 11 canonical endpoints.

    The 16 remaining endpoints from the earlier 27 discovery count cannot be queried
    live due to the Zero-Execution policy and are documented as an unverified baseline.
    """
    assert len(service.KNOWN_SERVING_ENDPOINTS) == 11

    # Verify all 11 canonical endpoints are accepted
    for ep_id in service.KNOWN_SERVING_ENDPOINTS:
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
        formatted_value="No data available",
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
    assert empty_kpi.formatted_value == "No data available"
    assert empty_kpi.status == KpiStatus.NO_DATA

    dumped: dict[str, Any] = empty_kpi.model_dump()
    assert dumped["value"] is None
    assert dumped["formatted_value"] == "No data available"
    assert dumped["status"] == "NO_DATA"


def test_no_data_vs_measured_zero_distinction(
    service: FinOpsAnalyticsService,
) -> None:
    """Verify that missing telemetry produces value=None, formatted_value='No data available',

    whereas true zero telemetry produces value=0.0 (measured zero) with AVAILABLE status.
    """
    # 1. Unknown / missing telemetry scope -> NO_DATA, value=None
    unknown_scope = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="fake-resource-xyz-9999",
        resource_type="cluster",
    )
    missing_kpi = unknown_scope.kpis["total_spend"]
    assert missing_kpi.status == KpiStatus.NO_DATA
    assert missing_kpi.value is None
    assert missing_kpi.formatted_value == "No data available"

    # 2. Known resource with measured zero (cement-demand-forecasting app in unattributed pool)
    app_scope = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="cement-demand-forecasting",
        resource_type="app",
    )
    measured_zero_kpi = app_scope.kpis["total_spend"]
    assert measured_zero_kpi.status == KpiStatus.AVAILABLE
    assert measured_zero_kpi.value == 0.0
    assert measured_zero_kpi.value is not None
    assert "$0 (Unattributed)" in measured_zero_kpi.formatted_value


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
    assert overview.kpis["total_spend"].formatted_value == "No data available"
    assert overview.kpis["total_spend"].status == KpiStatus.NO_DATA

    # 2. Cost Explorer
    cost = service.get_cost_explorer(resource_id=unknown_id, resource_type=unknown_type)
    assert cost.kpis["gross_consumption"].value is None
    assert cost.kpis["gross_consumption"].formatted_value == "No data available"
    assert cost.kpis["gross_consumption"].status == KpiStatus.NO_DATA

    # 3. Compute & Warehouses
    compute = service.get_compute_warehouses(resource_id=unknown_id, resource_type=unknown_type)
    assert compute.kpis["compute_spend"].value is None
    assert compute.kpis["compute_spend"].formatted_value == "No data available"
    assert compute.kpis["compute_spend"].status == KpiStatus.NO_DATA

    # 4. Storage & Lakehouse
    storage = service.get_data_storage(resource_id=unknown_id, resource_type=unknown_type)
    assert storage.kpis["storage_spend"].value is None
    assert storage.kpis["storage_spend"].formatted_value == "No data available"
    assert storage.kpis["storage_spend"].status == KpiStatus.NO_DATA

    # 5. AI & Token Economics
    ai = service.get_ai_economics(resource_id=unknown_id, resource_type=unknown_type)
    assert ai.kpis["ai_spend"].value is None
    assert ai.kpis["ai_spend"].formatted_value == "No data available"
    assert ai.kpis["ai_spend"].status == KpiStatus.NO_DATA

    # 6. Optimization Advisor
    advisor = service.get_optimization_advisor(resource_id=unknown_id, resource_type=unknown_type)
    assert advisor.kpis["potential_savings"].value is None
    assert advisor.kpis["potential_savings"].formatted_value == "No data available"
    assert advisor.kpis["potential_savings"].status == KpiStatus.NO_DATA

    # 7. Anomaly Detector
    anomaly = service.get_anomaly_detection(resource_id=unknown_id, resource_type=unknown_type)
    assert anomaly.kpis["open_anomalies"].value is None
    assert anomaly.kpis["open_anomalies"].formatted_value == "No data available"
    assert anomaly.kpis["open_anomalies"].status == KpiStatus.NO_DATA

    # 8. Forecast & Budgets
    forecast = service.get_forecast_budgets(resource_id=unknown_id, resource_type=unknown_type)
    assert forecast.kpis["forecast_month_end"].value is None
    assert forecast.kpis["forecast_month_end"].formatted_value == "No data available"
    assert forecast.kpis["forecast_month_end"].status == KpiStatus.NO_DATA

    # 9. Cost Allocation & Tagging
    alloc = service.get_cost_allocation(resource_id=unknown_id, resource_type=unknown_type)
    assert alloc.kpis["unallocated_spend"].value is None
    assert alloc.kpis["unallocated_spend"].formatted_value == "No data available"
    assert alloc.kpis["unallocated_spend"].status == KpiStatus.NO_DATA

    # 10. Showback / Chargeback
    showback = service.get_showback_chargeback(resource_id=unknown_id, resource_type=unknown_type)
    assert showback.kpis["shared_pool"].value is None
    assert showback.kpis["shared_pool"].formatted_value == "No data available"
    assert showback.kpis["shared_pool"].status == KpiStatus.NO_DATA

    # 11. Workload Unit Economics
    workload = service.get_workload_economics(resource_id=unknown_id, resource_type=unknown_type)
    assert workload.kpis["avg_cost_workload"].value is None
    assert workload.kpis["avg_cost_workload"].formatted_value == "No data available"
    assert workload.kpis["avg_cost_workload"].status == KpiStatus.NO_DATA

    # 12. Governance & Policy Engine
    gov = service.get_governance_policies(resource_id=unknown_id, resource_type=unknown_type)
    assert gov.kpis["policy_compliance"].value is None
    assert gov.kpis["policy_compliance"].formatted_value == "No data available"
    assert gov.kpis["policy_compliance"].status == KpiStatus.NO_DATA

    # 13. Network & Cross-Cloud Infra
    net = service.get_network_cloud(resource_id=unknown_id, resource_type=unknown_type)
    assert net.kpis["network_infra_spend"].value is None
    assert net.kpis["network_infra_spend"].formatted_value == "No data available"
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
    assert canonical.metric.formatted_value == "No data available"
    assert canonical.metric.status == KpiStatus.NO_DATA
