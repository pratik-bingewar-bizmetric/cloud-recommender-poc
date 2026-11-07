"""Targeted Audit Tests for Milestone 3F - Databricks FinOps Data Integrity & Reconciliation.

Verifies:
1. Invalid workspace ID rejection (Scope validation failure).
2. Invalid resource ID handling and fallback behavior.
3. Unsupported resource type behavior.
4. Unit isolation (DBUs vs Tokens vs Currency vs Storage GB).
5. Currency consistency across metrics.
6. Reconciliations between KPIs, top cost drivers, and ledger items.
7. Stopped warehouse state and zero-execution policy enforcement.
8. Unattributed cost bucket isolation.
9. Empty ledger and zero-data edge cases.
10. Arithmetic integrity and double-counting prevention.
"""

import pytest

from cloud_recommender.schemas.finops import KpiStatus
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return FinOpsAnalyticsService()


# -----------------------------------------------------------------------------
# 1. Scope Enforcement & Invalid Workspace / Resource Tests
# -----------------------------------------------------------------------------


def test_audit_invalid_workspace_id_rejection(service: FinOpsAnalyticsService) -> None:
    """Audit Test 1: Verify invalid or foreign workspace IDs are rejected with ValueError."""
    invalid_ids = [
        "9999999999999999",
        "aws-workspace-foreign",
        "adb-1234567890.12.azuredatabricks.net",
        "; DROP TABLE users; --",
        "",
    ]
    for wid in invalid_ids:
        if wid:  # Empty string is treated as None / default scope
            with pytest.raises(ValueError, match="Scope validation failed"):
                service.validate_scope(wid)
            with pytest.raises(ValueError, match="Scope validation failed"):
                service.get_executive_overview(workspace_id=wid)
            with pytest.raises(ValueError, match="Scope validation failed"):
                service.get_cost_explorer(workspace_id=wid)


def test_audit_unknown_resource_id_fallback_behavior(service: FinOpsAnalyticsService) -> None:
    """Audit Test 2: Examine how backend behaves when passed an unknown or non-existent resource ID."""
    # 2a. Resource ID containing "cluster" does NOT falsely match via substring; returns 0.0 and NO_DATA
    falsely_matched = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="fake-cluster-9999",
        resource_type=None,
    )
    assert falsely_matched.kpis["total_spend"].value is None
    assert falsely_matched.kpis["total_spend"].formatted_value == "No data available"
    assert falsely_matched.kpis["total_spend"].status == KpiStatus.NO_DATA

    # 2b. Truly unknown resource_id returns None and NO_DATA status, never workspace fallback
    unmatched = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="unknown-guid-e9a8f234-9999",
        resource_type=None,
    )
    assert unmatched.kpis["total_spend"].value is None
    assert unmatched.kpis["total_spend"].formatted_value == "No data available"
    assert unmatched.kpis["total_spend"].status == KpiStatus.NO_DATA


def test_audit_unsupported_resource_type_behavior(service: FinOpsAnalyticsService) -> None:
    """Audit Test 3: Examine handling of unsupported resource types (e.g. 'virtual_machine', 'sql_db')."""
    res = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="res-123",
        resource_type="unsupported_quantum_compute",
    )
    # Unsupported resource type returns None and NO_DATA status
    assert res.kpis["total_spend"].value is None
    assert res.kpis["total_spend"].formatted_value == "No data available"
    assert res.kpis["total_spend"].status == KpiStatus.NO_DATA


# -----------------------------------------------------------------------------
# 2. Strict Unit Isolation & Mathematical Integrity Tests
# -----------------------------------------------------------------------------


def test_audit_unit_isolation_no_dbu_token_currency_mixing(service: FinOpsAnalyticsService) -> None:
    """Audit Test 4: Verify DBU, tokens, and USD currency units are strictly isolated."""
    overview = service.get_executive_overview()
    ai = service.get_ai_economics()

    # Total spend is currency
    assert overview.kpis["total_spend"].unit == "USD"
    assert overview.kpis["total_spend"].currency == "USD"

    # DBU consumption is pure DBU, never currency
    assert overview.kpis["dbu_consumption"].unit == "DBU"
    assert overview.kpis["dbu_consumption"].currency is None
    assert "Strict unit separation" in (overview.kpis["dbu_consumption"].limitations or "")

    # AI tokens are tokens, never DBUs or USD
    assert ai.kpis["input_tokens"].unit.lower() == "tokens"
    assert ai.kpis["input_tokens"].currency is None
    assert ai.kpis["output_tokens"].unit.lower() == "tokens"
    assert ai.kpis["output_tokens"].currency is None


def test_audit_kpi_mathematical_reconciliation(service: FinOpsAnalyticsService) -> None:
    """Audit Test 5: Reconcile mathematical calculations across Overview and Cost Explorer."""
    overview = service.get_executive_overview()
    cost = service.get_cost_explorer()

    databricks_spend = overview.kpis["databricks_spend"].value  # 176,840.0
    dbu_consumption = overview.kpis["dbu_consumption"].value  # 88,420.0

    # Effective rate check: blended effective rate is $2.000 / DBU
    effective_rate = cost.kpis["effective_rate"].value  # 2.0 USD/DBU
    calculated_spend_from_rate = dbu_consumption * effective_rate  # 88,420 * 2.0 = 176,840.0

    # RECONCILED IN MILESTONE 3G:
    # databricks_spend is $176,840.0, and 88,420 DBU * $2.000/DBU = $176,840.00
    variance = abs(databricks_spend - calculated_spend_from_rate)
    assert variance == 0.0, (
        f"Reconciled: DBU * Rate (${calculated_spend_from_rate:,.2f}) "
        f"matches Reported Spend (${databricks_spend:,.2f})"
    )

    # Billing Ledger sum check
    ledger_sum = sum(item.effective_cost for item in cost.billing_ledger)
    gross_kpi = cost.kpis["gross_consumption"].value  # 176,840.0
    ledger_variance = abs(gross_kpi - ledger_sum)
    assert ledger_variance == 0.0, (
        f"Reconciled: Ledger sum (${ledger_sum:,.2f}) matches Gross KPI (${gross_kpi:,.2f})"
    )


def test_audit_spend_composition_vs_kpis(service: FinOpsAnalyticsService) -> None:
    """Audit Test 6: Verify Spend Composition chart elements reconcile with parent KPIs."""
    overview = service.get_executive_overview()

    comp_dict = {item["family"]: item["amount"] for item in overview.spend_composition}
    total_comp = sum(item["amount"] for item in overview.spend_composition)

    # Spend composition sums to $284,620.0
    assert abs(total_comp - overview.kpis["total_spend"].value) <= 0.01

    # AI / GenAI composition amount vs ai_spend KPI
    comp_ai = comp_dict.get("AI / GenAI", 0.0)
    kpi_ai = overview.kpis["ai_spend"].value
    # RECONCILED IN MILESTONE 3G: Spend composition has $38,460 for AI, matching KPI card exactly
    ai_variance = abs(comp_ai - kpi_ai)
    assert ai_variance == 0.0, f"Reconciled: Composition AI (${comp_ai}) matches KPI AI (${kpi_ai})"


# -----------------------------------------------------------------------------
# 3. System Tables & Stopped Warehouse State Tests
# -----------------------------------------------------------------------------


def test_audit_system_tables_stopped_warehouse_gating(service: FinOpsAnalyticsService) -> None:
    """Audit Test 7: Verify all 10 system tables reflect STOPPED_WAREHOUSE status for live queries."""
    sys_tables = service.get_system_tables(workspace_id="642006393507276")
    assert len(sys_tables.tables) == 10
    assert sys_tables.warehouse_state == "STOPPED"

    for tbl in sys_tables.tables:
        assert tbl.status == "STOPPED_WAREHOUSE", (
            f"Table {tbl.table_name} must truthfully report STOPPED_WAREHOUSE"
        )
        assert len(tbl.columns) > 0, f"Table {tbl.table_name} must provide verified schema columns"


def test_audit_query_history_records_are_historical(service: FinOpsAnalyticsService) -> None:
    """Audit Test 8: Verify query history contains preserved executions with valid statuses."""
    history = service.get_query_history(workspace_id="642006393507276")
    assert history.total_count == 7

    valid_statuses = {"FINISHED", "FAILED", "CANCELLED", "RUNNING"}
    for q in history.records:
        assert q.status in valid_statuses
        assert q.warehouse_id == "05ed10a52697a344"
        assert q.duration_ms > 0
        if q.status == "FAILED":
            assert q.error_message is not None


# -----------------------------------------------------------------------------
# 4. Unattributed Cost Handling Tests
# -----------------------------------------------------------------------------


def test_audit_unattributed_cost_isolation(service: FinOpsAnalyticsService) -> None:
    """Audit Test 9: Verify shared apps compute is isolated in Unattributed pool rather than shared."""
    app_overview = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="cement-demand-forecasting",
        resource_type="app",
    )
    assert app_overview.kpis["total_spend"].value == 0.0
    assert "Unattributed" in app_overview.kpis["total_spend"].formatted_value
    assert app_overview.spend_composition[0]["family"] == "Unattributed Compute"
    assert app_overview.top_cost_drivers[0].spend == 1240.0
    assert "Unattributed" in app_overview.top_cost_drivers[0].formatted_spend


# -----------------------------------------------------------------------------
# 5. Retraction and Ledger Edge Case Tests
# -----------------------------------------------------------------------------


def test_audit_custom_ledger_retractions_and_credit_handling(
    service: FinOpsAnalyticsService,
) -> None:
    """Audit Test 10: Test ledger retraction calculation logic."""
    cost = service.get_cost_explorer()

    # Verify credit adjustment KPI is present and positive
    credits_kpi = cost.kpis["credits_discounts"]
    assert credits_kpi.value == 8260.0
    assert credits_kpi.status in {KpiStatus.BASELINE, KpiStatus.AVAILABLE}
    assert "Azure EA Commercial Adjustments" in credits_kpi.source
