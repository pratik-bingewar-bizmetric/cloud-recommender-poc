"""Adversarial and Forensic Verification Tests for Milestone 3G.1.

Validates:
1. Exact resource ID membership and matching resource type.
2. Complete elimination of substring, fuzzy, and partial-name matching.
3. Adversarial test cases:
   - fake-adf-deaccelator-compute-123
   - adf-deaccelator-compute-fake
   - fake-cluster-999
   - fake-warehouse-05ed10a52697a344
   - unknown GUIDs
   - valid ID paired with incorrect resource type
4. Purged fabricated/sample entries.
5. All-module scope enforcement and typed NO_DATA return.
"""

import pytest

from cloud_recommender.schemas.finops import KpiStatus
from cloud_recommender.services.databricks.finops_analytics_service import (
    FinOpsAnalyticsService,
)


@pytest.fixture
def service() -> FinOpsAnalyticsService:
    return FinOpsAnalyticsService()


# -----------------------------------------------------------------------------
# 1. Adversarial Substring & Partial Match Attack Tests
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fake_id,res_type",
    [
        ("fake-adf-deaccelator-compute-123", "cluster"),
        ("fake-adf-deaccelator-compute-123", None),
        ("adf-deaccelator-compute-fake", "cluster"),
        ("adf-deaccelator-compute-fake", None),
        ("fake-cluster-999", "cluster"),
        ("fake-cluster-999", None),
        ("fake-warehouse-05ed10a52697a344", "warehouse"),
        ("fake-warehouse-05ed10a52697a344", None),
        ("05ed10a52697a344-fake", "warehouse"),
        ("cluster", None),
        ("warehouse", None),
        ("deaccelator", None),
        ("9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d", None),
        ("00000000-0000-0000-0000-000000000000", "cluster"),
    ],
)
def test_adversarial_invalid_identifiers_return_no_data(
    service: FinOpsAnalyticsService, fake_id: str, res_type: str | None
) -> None:
    """Ensure that all partial, prefixed, suffixed, or random GUID identifiers are rejected."""
    cat, is_unknown = service._resolve_resource_filter(fake_id, res_type)
    assert is_unknown is True, f"Failed for {fake_id} (type={res_type}): must be marked unknown."
    assert cat is None

    # Overview must return NO_DATA and 0.0 values, never workspace totals
    overview = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id=fake_id,
        resource_type=res_type,
    )
    assert overview.kpis["total_spend"].value is None
    assert overview.kpis["total_spend"].status == KpiStatus.NO_DATA
    assert overview.kpis["total_spend"].formatted_value == "-"
    assert len(overview.spend_trend) == 0
    assert len(overview.top_cost_drivers) == 0


# -----------------------------------------------------------------------------
# 2. Valid ID Paired with Incorrect Resource Type Tests
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valid_id,wrong_type",
    [
        ("05ed10a52697a344", "cluster"),  # Warehouse paired with cluster
        ("05ed10a52697a344", "app"),  # Warehouse paired with app
        ("05ed10a52697a344", "serving_endpoint"),  # Warehouse paired with serving
        ("Serverless Starter Warehouse", "cluster"),  # Warehouse name paired with cluster
        ("1102-081455-7t3bqp3v", "warehouse"),  # Cluster paired with warehouse
        ("1102-081455-7t3bqp3v", "serving_endpoint"),  # Cluster paired with serving
        ("adf-deaccelator-compute", "warehouse"),  # Cluster name paired with warehouse
        ("adf-deaccelator-compute", "app"),  # Cluster name paired with app
        ("cement-demand-forecasting", "cluster"),  # App paired with cluster
        ("cement-demand-forecasting", "warehouse"),  # App paired with warehouse
        ("databricks-claude-fable-5", "warehouse"),  # Serving paired with warehouse
        ("databricks-claude-fable-5", "cluster"),  # Serving paired with cluster
    ],
)
def test_valid_id_with_mismatched_resource_type_rejected(
    service: FinOpsAnalyticsService, valid_id: str, wrong_type: str
) -> None:
    """Ensure that valid IDs paired with the WRONG resource type are strictly rejected."""
    cat, is_unknown = service._resolve_resource_filter(valid_id, wrong_type)
    assert is_unknown is True, (
        f"Failed for valid ID '{valid_id}' paired with mismatched type '{wrong_type}'"
    )
    assert cat is None

    overview = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id=valid_id,
        resource_type=wrong_type,
    )
    assert overview.kpis["total_spend"].status == KpiStatus.NO_DATA
    assert overview.kpis["total_spend"].value is None
    assert overview.kpis["total_spend"].formatted_value == "-"


# -----------------------------------------------------------------------------
# 3. Purged Fabricated / Sample Resources Tests
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "purged_id,res_type",
    [
        ("databricks-cost-monitor", "app"),  # Sample app purged from production registry
        ("finops-optimizer-app", "app"),  # Sample app purged from production registry
        ("0612-120000-sample1", "cluster"),  # Sample cluster purged
        ("0920-050000-sample2", "cluster"),  # Sample cluster purged
        ("1015-080000-sample3", "cluster"),  # Sample cluster purged
    ],
)
def test_purged_sample_resources_return_no_data(
    service: FinOpsAnalyticsService, purged_id: str, res_type: str
) -> None:
    """Ensure that sample/fabricated resources purged from production registries return NO_DATA."""
    cat, is_unknown = service._resolve_resource_filter(purged_id, res_type)
    assert is_unknown is True, f"Purged resource '{purged_id}' must not be recognized."
    assert cat is None

    res = service.get_executive_overview(
        workspace_id="642006393507276",
        resource_id=purged_id,
        resource_type=res_type,
    )
    assert res.kpis["total_spend"].status == KpiStatus.NO_DATA


# -----------------------------------------------------------------------------
# 4. Valid Production Discovered Resources Tests
# -----------------------------------------------------------------------------


def test_valid_authenticated_discovered_resources(service: FinOpsAnalyticsService) -> None:
    """Verify that real authenticated discovered assets are accepted and properly categorized."""
    # 1. Warehouse
    wh_cat, wh_unknown = service._resolve_resource_filter("05ed10a52697a344", "warehouse")
    assert wh_unknown is False
    assert wh_cat == "warehouse"

    # 2. Cluster
    cl_cat, cl_unknown = service._resolve_resource_filter("1102-081455-7t3bqp3v", "cluster")
    assert cl_unknown is False
    assert cl_cat == "cluster"

    # Cluster name alone cannot independently authorize attribution (Requirement 3.1 & 3.2)
    cl_name_cat, cl_name_unknown = service._resolve_resource_filter(
        "adf-deaccelator-compute", "cluster"
    )
    assert cl_name_unknown is True
    assert cl_name_cat is None

    # 3. Serving Endpoint
    sv_cat, sv_unknown = service._resolve_resource_filter(
        "databricks-claude-fable-5", "serving_endpoint"
    )
    assert sv_unknown is False
    assert sv_cat == "serving"

    # 4. Live Discovered App
    app_cat, app_unknown = service._resolve_resource_filter("cement-demand-forecasting", "app")
    assert app_unknown is False
    assert app_cat == "app"


# -----------------------------------------------------------------------------
# 5. All-Module Scope Enforcement Under Adversarial Input
# -----------------------------------------------------------------------------


def test_adversarial_scope_across_all_modules(service: FinOpsAnalyticsService) -> None:
    """Verify that when passed an adversarial invalid ID, all modules return empty/NO_DATA states."""
    fake_id = "fake-cluster-999"
    wid = "642006393507276"

    # Module 1: Overview
    overview = service.get_executive_overview(
        workspace_id=wid, resource_id=fake_id, resource_type="cluster"
    )
    assert overview.kpis["total_spend"].status == KpiStatus.NO_DATA
    assert len(overview.spend_trend) == 0

    # Module 2: Cost Explorer
    cost = service.get_cost_explorer(workspace_id=wid, resource_id=fake_id, resource_type="cluster")
    assert cost.kpis["gross_consumption"].status == KpiStatus.NO_DATA
    assert len(cost.billing_ledger) == 0

    # Module 4: Compute & Warehouses
    compute = service.get_compute_warehouses(
        workspace_id=wid, resource_id=fake_id, resource_type="cluster"
    )
    assert compute.kpis["compute_spend"].status == KpiStatus.NO_DATA

    # Module 5: AI Economics
    ai = service.get_ai_economics(
        workspace_id=wid, resource_id=fake_id, resource_type="serving_endpoint"
    )
    assert ai.kpis["ai_spend"].status == KpiStatus.NO_DATA
    assert len(ai.model_economics) == 0

    # Module 8: Optimization Advisor
    advisor = service.get_optimization_advisor(
        workspace_id=wid, resource_id=fake_id, resource_type="cluster"
    )
    assert advisor.kpis["potential_savings"].status == KpiStatus.NO_DATA
    assert len(advisor.recommendations) == 0

    # Module 10: Anomaly Detection
    anom = service.get_anomaly_detection(
        workspace_id=wid, resource_id=fake_id, resource_type="cluster"
    )
    assert anom.kpis["open_anomalies"].status == KpiStatus.NO_DATA
    assert len(anom.anomalies) == 0
