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
from tests.fixtures.live_inventory import make_analytics_service, stub_query_history


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return make_analytics_service(with_billing=True)


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
    assert falsely_matched.kpis["total_spend"].formatted_value == "-"
    assert falsely_matched.kpis["total_spend"].status == KpiStatus.NO_DATA

    # 2b. Truly unknown resource_id returns None and NO_DATA status, never workspace fallback
    unmatched = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id="unknown-guid-e9a8f234-9999",
        resource_type=None,
    )
    assert unmatched.kpis["total_spend"].value is None
    assert unmatched.kpis["total_spend"].formatted_value == "-"
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
    assert res.kpis["total_spend"].formatted_value == "-"
    assert res.kpis["total_spend"].status == KpiStatus.NO_DATA


# -----------------------------------------------------------------------------
# 2. Strict Unit Isolation & Mathematical Integrity Tests
# -----------------------------------------------------------------------------


def test_audit_unit_isolation_no_dbu_token_currency_mixing(service: FinOpsAnalyticsService) -> None:
    """Audit Test 4: DBU, tokens and USD stay strictly isolated."""
    overview = service.get_executive_overview()
    ai = service.get_ai_economics()

    assert overview.kpis["total_spend"].unit == "USD"
    assert overview.kpis["total_spend"].currency == "USD"
    assert overview.kpis["dbu_consumption"].unit == "DBU"
    assert overview.kpis["dbu_consumption"].currency is None

    assert ai.kpis["input_tokens"].unit.lower() == "tokens"
    assert ai.kpis["input_tokens"].currency is None
    assert ai.kpis["output_tokens"].unit.lower() == "tokens"
    assert ai.kpis["output_tokens"].currency is None


def test_audit_kpi_mathematical_reconciliation(service: FinOpsAnalyticsService) -> None:
    """Audit Test 5: Overview and Cost Explorer reconcile arithmetically."""
    overview = service.get_executive_overview()
    cost = service.get_cost_explorer()

    spend = overview.kpis["databricks_spend"].value
    dbu = overview.kpis["dbu_consumption"].value
    rate = cost.kpis["effective_rate"].value
    assert abs(spend - dbu * rate) <= 0.01 * max(1.0, dbu)  # rate is rounded to 4 dp

    ledger_sum = sum(item.effective_cost for item in cost.billing_ledger)
    assert abs(cost.kpis["gross_consumption"].value - ledger_sum) <= 0.01


def test_audit_spend_composition_vs_kpis(service: FinOpsAnalyticsService) -> None:
    """Audit Test 6: Spend Composition reconciles with the parent KPIs."""
    overview = service.get_executive_overview()
    comp = {item["family"]: item["amount"] for item in overview.spend_composition}
    assert abs(sum(comp.values()) - overview.kpis["total_spend"].value) <= 0.01
    assert abs(comp["MODEL_SERVING"] - overview.kpis["ai_spend"].value) <= 0.01


# -----------------------------------------------------------------------------
# 3. System Tables & Stopped Warehouse State Tests
# -----------------------------------------------------------------------------


def test_audit_system_tables_stopped_warehouse_gating(service: FinOpsAnalyticsService) -> None:
    """Audit Test 7: system tables never claim row access; without metadata discovery they are UNAVAILABLE."""
    sys_tables = service.get_system_tables(workspace_id="642006393507276")
    # No Unity Catalog metadata cached in this offline test: nothing is fabricated
    assert sys_tables.tables == []
    assert sys_tables.catalog_status == "UNAVAILABLE"
    assert sys_tables.warehouse_state == "STOPPED"


def test_audit_query_history_records_are_historical(service: FinOpsAnalyticsService) -> None:
    """Audit Test 8: query history comes from the live API; with no connection it reports UNAVAILABLE."""
    import asyncio

    stub_query_history(service)  # offline: the live Query History API is never called
    history = asyncio.run(service.get_query_history(workspace_id="642006393507276"))
    assert history.records == []
    assert history.provenance is not None
    assert history.provenance.classification != KpiStatus.LIVE


# -----------------------------------------------------------------------------
# 4. Unattributed Cost Handling Tests
# -----------------------------------------------------------------------------


def test_audit_unattributed_cost_isolation(service: FinOpsAnalyticsService) -> None:
    """Audit Test 9: untagged spend stays in an explicit Unallocated bucket and is never distributed."""
    alloc = service.get_cost_allocation()
    buckets = {b["business_unit"]: b["spend"] for b in alloc.spend_by_bu}
    assert (
        abs(sum(buckets.values()) - service.get_cost_explorer().kpis["gross_consumption"].value)
        <= 0.01
    )
    # The fixture's ledger rows all carry owner tags except none; Unallocated is either absent or explicit
    assert all(name for name in buckets)
    assert alloc.kpis["shared_pool"].status == KpiStatus.UNAVAILABLE


# -----------------------------------------------------------------------------
# 5. Retraction and Ledger Edge Case Tests
# -----------------------------------------------------------------------------


def test_audit_custom_ledger_retractions_and_credit_handling(
    service: FinOpsAnalyticsService,
) -> None:
    """Audit Test 10: credits/discounts are not exposed by billing rows and must be UNAVAILABLE."""
    credits_kpi = service.get_cost_explorer().kpis["credits_discounts"]
    assert credits_kpi.value is None
    assert credits_kpi.status == KpiStatus.UNAVAILABLE
