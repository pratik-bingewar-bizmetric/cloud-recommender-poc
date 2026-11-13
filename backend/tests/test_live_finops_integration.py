"""Comprehensive validation test suite for live FinOps data integration and canonical models.

Verifies:
- Canonical billing record validation and FOCUS 1.0 alignment
- Authoritative Azure Cost Management integration and SOURCE_UNAVAILABLE handling
- Databricks System Tables billing ingestion, Decimal pricing, and idempotency
- Retraction preservation and strict unit separation
- Double-counting prevention for AI compute
- Forecast accuracy evaluation (< 3 completed cycles yields NOT AVAILABLE)
- Zero-Execution guardrail: warehouse remains stopped with zero mutations
"""

from decimal import Decimal

import pytest

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.billing_ingestion import BillingUsageRecord
from cloud_recommender.schemas.canonical_financial import (
    CanonicalBillingRecord,
    ComponentSpendCoverage,
    DataFreshnessStatus,
    SubscriptionSpendAggregation,
    generate_canonical_idempotency_key,
)
from cloud_recommender.schemas.finops import KpiStatus
from cloud_recommender.services.azure.cost_management_service import (
    AzureCostManagementQueryResult,
    AzureCostManagementService,
)
from cloud_recommender.services.databricks.billing_ingestion_service import BillingIngestionService
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService
from tests.fixtures.billing_baseline import baseline_expectations, load_baseline_usage
from tests.fixtures.live_inventory import make_analytics_service


def test_canonical_billing_record_creation_and_focus_alignment() -> None:
    """Verify CanonicalBillingRecord structure, Decimal precision, and FOCUS properties."""
    rec = CanonicalBillingRecord(
        record_id="rec-test-focus-01",
        provider="databricks",
        billing_account_id="acc-dbx-az-01",
        subscription_id="sub-finops-enterprise-01",
        workspace_id="642006393507276",
        resource_id="/subscriptions/sub-finops-enterprise-01/resourceGroups/rg-dbx/warehouses/05ed10a52697a344",
        service_category="Compute",
        service_name="Azure Databricks",
        sku_name="SERVERLESS_SQL_COMPUTE",
        usage_start_time="2026-11-01T00:00:00Z",
        usage_end_time="2026-11-01T23:59:59Z",
        usage_date="2026-11-01",
        usage_quantity=Decimal("4793.0000"),
        usage_unit="DBU",
        list_unit_price=Decimal("2.200000"),
        effective_cost=Decimal("10544.60"),
        currency="USD",
        pricing_matched=True,
        is_retraction=False,
        is_embedded_in_platform=False,
        data_quality_status=DataFreshnessStatus.LIVE,
    )
    assert rec.record_id == "rec-test-focus-01"
    assert rec.effective_cost == Decimal("10544.60")
    assert rec.usage_unit == "DBU"
    assert rec.data_quality_status == DataFreshnessStatus.LIVE


def test_azure_cost_management_unconfigured_source_unavailable() -> None:
    """Verify Azure Cost Management returns SOURCE_UNAVAILABLE when credentials are unconfigured."""
    s = Settings(catalog_offline_mode=True)
    service = AzureCostManagementService(settings=s)
    result = service.query_subscription_costs(subscription_id="sub-finops-enterprise-01")

    assert isinstance(result, AzureCostManagementQueryResult)
    assert result.status == DataFreshnessStatus.SOURCE_UNAVAILABLE
    assert result.total_cost is None
    assert result.records == []
    assert (
        "SOURCE UNAVAILABLE" in (result.error_message or "").upper()
        or "UNCONFIGURED" in (result.error_message or "").upper()
    )


def test_azure_cost_management_seeded_decimal_calculation() -> None:
    """Verify Azure Cost Management calculates exact Decimal totals when authoritative records exist."""
    s = Settings(catalog_offline_mode=True)
    service = AzureCostManagementService(settings=s)
    recs = [
        CanonicalBillingRecord(
            record_id="rec-az-01",
            provider="azure",
            subscription_id="sub-finops-enterprise-01",
            resource_id="/subscriptions/sub-01/storageAccounts/adlsgen2",
            service_category="Storage",
            service_name="Storage",
            sku_name="Standard Hot",
            usage_start_time="2026-11-01T00:00:00Z",
            usage_end_time="2026-11-01T23:59:59Z",
            usage_date="2026-11-01",
            usage_quantity=Decimal("100.0"),
            usage_unit="GB",
            effective_cost=Decimal("18950.00"),
        ),
        CanonicalBillingRecord(
            record_id="rec-az-02",
            provider="azure",
            subscription_id="sub-finops-enterprise-01",
            resource_id="/subscriptions/sub-01/virtualNetworks/vnet-01",
            service_category="Network",
            service_name="Virtual Network",
            sku_name="Egress Bandwidth",
            usage_start_time="2026-11-01T00:00:00Z",
            usage_end_time="2026-11-01T23:59:59Z",
            usage_date="2026-11-01",
            usage_quantity=Decimal("42.8"),
            usage_unit="TB",
            effective_cost=Decimal("28420.00"),
        ),
    ]
    service.seed_test_records("sub-finops-enterprise-01", recs)
    res = service.query_subscription_costs("sub-finops-enterprise-01")

    assert res.status == DataFreshnessStatus.LIVE
    assert res.total_cost == Decimal("47370.00")
    assert len(res.records) == 2


def test_databricks_ingestion_idempotency_and_no_cost_inflation() -> None:
    """Re-loading the same records must not inflate usage; a fresh service holds no usage rows."""
    service = BillingIngestionService(settings=Settings(databricks_auth_type="mock"))
    assert len(service._usage_store) == 0  # nothing is seeded at runtime

    load_baseline_usage(service)
    assert len(service._usage_store) == 11
    load_baseline_usage(service)  # same record_ids overwrite, never add
    assert len(service._usage_store) == 11

    status = service.get_ingestion_status(workspace_id="642006393507276")
    assert status.total_dbu_consumed == 88420.0
    assert status.warehouse_status == "WAREHOUSE_STOPPED"
    assert status.system_tables_status == "APPROVAL_REQUIRED"


def test_forecast_accuracy_requires_three_closed_cycles() -> None:
    """Forecast accuracy is never fabricated: it stays unavailable with an explicit reason."""
    service = FinOpsAnalyticsService()
    fb = service.get_forecast_budgets(workspace_id="642006393507276")

    acc_kpi = fb.kpis.get("forecast_accuracy")
    assert acc_kpi is not None
    assert acc_kpi.value is None
    assert acc_kpi.status == KpiStatus.INSUFFICIENT_HISTORY
    assert "3 completed" in (acc_kpi.limitations or "")


def test_ai_spend_double_counting_safeguard() -> None:
    """Model Serving DBU compute is a subset of platform spend, never added on top of it."""
    exp = baseline_expectations()
    service = make_analytics_service(with_billing=True, with_inventory=False)
    overview = service.get_executive_overview()
    ai_kpi = overview.kpis["ai_spend"]
    dbx_kpi = overview.kpis["databricks_spend"]
    tot_kpi = overview.kpis["total_spend"]

    assert ai_kpi.value == pytest.approx(exp["by_product"]["MODEL_SERVING"])
    assert dbx_kpi.value == pytest.approx(exp["total_cost"])
    assert tot_kpi.value == dbx_kpi.value  # no Azure infra is added without Cost Management data
    assert ai_kpi.value < dbx_kpi.value
    assert "Azure infrastructure" in (tot_kpi.limitations or "")


def test_child_scope_warehouse_filtering() -> None:
    """Warehouse scope is bounded to the warehouse's attributed rows; AI spend is a measured zero."""
    exp = baseline_expectations()
    service = make_analytics_service(with_billing=True, with_inventory=False)
    wh_data = service.get_executive_overview(
        resource_id="05ed10a52697a344", resource_type="warehouse"
    )

    assert wh_data.kpis["total_spend"].value == pytest.approx(
        exp["by_resource"]["05ed10a52697a344"]
    )
    assert wh_data.kpis["databricks_spend"].value == pytest.approx(
        exp["by_resource"]["05ed10a52697a344"]
    )
    assert wh_data.kpis["ai_spend"].value == 0.0  # rows exist, none are AI: a real measured zero
    assert wh_data.kpis["ai_spend"].status == KpiStatus.CALCULATED
    assert wh_data.kpis["dbu_consumption"].value == exp["by_product_dbu"]["SQL"]


def test_unknown_child_scope_returns_no_data() -> None:
    """Verify unmapped resource ID returns NO_DATA status across all KPIs."""
    service = FinOpsAnalyticsService()
    res = service.get_executive_overview(resource_id="unknown-warehouse-404")

    assert res.kpis["total_spend"].status == KpiStatus.NO_DATA
    assert res.kpis["databricks_spend"].status == KpiStatus.NO_DATA
    assert res.kpis["dbu_consumption"].status == KpiStatus.NO_DATA


def test_zero_execution_policy_warehouse_stays_stopped() -> None:
    """Verify inspecting warehouse readiness does not execute compute or start the warehouse."""
    service = BillingIngestionService(settings=Settings(databricks_auth_type="mock"))
    val = service.validate_ingestion("642006393507276")

    assert "Warehouse is currently STOPPED" in str(val.diagnostic_messages)
    assert "Zero-Execution policy enforced: Run button is locked." in str(val.diagnostic_messages)
    # Warehouse health remains STOPPED
    assert service.sql_service.check_warehouse_status().status == "WAREHOUSE_STOPPED"


def test_identical_legitimate_records_with_different_source_ids_preserved() -> None:
    """Verify that two identical legitimate billing records (same time, SKU, cost) are both preserved when source IDs differ."""
    service = BillingIngestionService()
    initial_count = len(service._usage_store)

    # Two concurrent serverless queries executed at identical second with identical usage
    rec1 = BillingUsageRecord(
        record_id="rec-parallel-001",
        workspace_id="642006393507276",
        account_id="acc-dbx-az-01",
        sku_name="SERVERLESS_SQL_COMPUTE",
        cloud="azure",
        usage_start_time="2026-11-04T12:00:00Z",
        usage_end_time="2026-11-04T12:00:00Z",
        usage_date="2026-11-04",
        usage_unit="DBU",
        usage_quantity=10.0,
        record_type="original",
        ingestion_date="2026-11-05",
        billing_origin_product="SQL",
        usage_metadata={"warehouse_id": "05ed10a52697a344", "query_id": "q-101"},
    )
    rec2 = BillingUsageRecord(
        record_id="rec-parallel-002",  # Distinct provider event ID
        workspace_id="642006393507276",
        account_id="acc-dbx-az-01",
        sku_name="SERVERLESS_SQL_COMPUTE",
        cloud="azure",
        usage_start_time="2026-11-04T12:00:00Z",
        usage_end_time="2026-11-04T12:00:00Z",
        usage_date="2026-11-04",
        usage_unit="DBU",
        usage_quantity=10.0,
        record_type="original",
        ingestion_date="2026-11-05",
        billing_origin_product="SQL",
        usage_metadata={"warehouse_id": "05ed10a52697a344", "query_id": "q-102"},
    )

    res = service.ingest_records([rec1, rec2])
    assert res["inserted_count"] == 2
    assert res["duplicate_count"] == 0
    assert len(service._usage_store) == initial_count + 2

    # Provider-native keys are distinct
    key1 = generate_canonical_idempotency_key("databricks", rec1.record_id)
    key2 = generate_canonical_idempotency_key("databricks", rec2.record_id)
    assert key1 != key2


def test_repeated_ingestion_of_same_source_record() -> None:
    """Verify that repeated ingestion of identical source record does not inflate records or DBU count."""
    service = BillingIngestionService()
    initial_count = len(service._usage_store)

    rec = BillingUsageRecord(
        record_id="rec-idemp-test-01",
        workspace_id="642006393507276",
        account_id="acc-dbx-az-01",
        sku_name="STANDARD_ALL_PURPOSE_COMPUTE",
        cloud="azure",
        usage_start_time="2026-11-04T00:00:00Z",
        usage_end_time="2026-11-04T23:59:59Z",
        usage_date="2026-11-04",
        usage_unit="DBU",
        usage_quantity=25.0,
        record_type="original",
        ingestion_date="2026-11-05",
        billing_origin_product="ALL_PURPOSE",
    )

    # First ingestion inserts
    res1 = service.ingest_records([rec])
    assert res1["inserted_count"] == 1
    assert res1["duplicate_count"] == 0
    assert len(service._usage_store) == initial_count + 1

    # Second ingestion detects duplicate
    res2 = service.ingest_records([rec])
    assert res2["inserted_count"] == 0
    assert res2["duplicate_count"] == 1
    assert len(service._usage_store) == initial_count + 1  # No record inflation


def test_negative_retractions_and_sla_adjustments() -> None:
    """Verify negative usage quantities (retractions) are preserved in ledger and correctly net out spend."""
    service = BillingIngestionService()
    initial_dbu = sum(r.usage_quantity for r in service._usage_store.values())

    retraction_rec = BillingUsageRecord(
        record_id="rec-retract-001",
        workspace_id="642006393507276",
        account_id="acc-dbx-az-01",
        sku_name="SERVERLESS_SQL_COMPUTE",
        cloud="azure",
        usage_start_time="2026-11-04T00:00:00Z",
        usage_end_time="2026-11-04T23:59:59Z",
        usage_date="2026-11-04",
        usage_unit="DBU",
        usage_quantity=-500.0,  # Negative usage
        record_type="retraction",
        ingestion_date="2026-11-05",
        billing_origin_product="SQL",
    )

    res = service.ingest_records([retraction_rec])
    assert res["inserted_count"] == 1
    assert res["retraction_count"] == 1

    new_dbu = sum(r.usage_quantity for r in service._usage_store.values())
    assert new_dbu == initial_dbu - 500.0
    # Effective cost is negative
    assert service._usage_store["rec-retract-001"].effective_cost == -1100.0


def test_revised_billing_records_accounting() -> None:
    """Verify that restatements (retraction + revised record) maintain continuous auditability without double counting."""
    service = BillingIngestionService()

    # Original record was 100 DBU ($220.00)
    orig = BillingUsageRecord(
        record_id="rec-orig-rev-01",
        workspace_id="642006393507276",
        account_id="acc-dbx-az-01",
        sku_name="SERVERLESS_SQL_COMPUTE",
        cloud="azure",
        usage_start_time="2026-11-01T00:00:00Z",
        usage_end_time="2026-11-01T23:59:59Z",
        usage_date="2026-11-01",
        usage_unit="DBU",
        usage_quantity=100.0,
        record_type="original",
        ingestion_date="2026-11-02",
        billing_origin_product="SQL",
    )
    service.ingest_records([orig])

    # Databricks issues retraction for -100 DBU and restatement for revised 80 DBU
    retract = BillingUsageRecord(
        record_id="rec-retract-rev-01",
        workspace_id="642006393507276",
        account_id="acc-dbx-az-01",
        sku_name="SERVERLESS_SQL_COMPUTE",
        cloud="azure",
        usage_start_time="2026-11-01T00:00:00Z",
        usage_end_time="2026-11-01T23:59:59Z",
        usage_date="2026-11-01",
        usage_unit="DBU",
        usage_quantity=-100.0,
        record_type="retraction",
        ingestion_date="2026-11-04",
        billing_origin_product="SQL",
    )
    revised = BillingUsageRecord(
        record_id="rec-revised-01",
        workspace_id="642006393507276",
        account_id="acc-dbx-az-01",
        sku_name="SERVERLESS_SQL_COMPUTE",
        cloud="azure",
        usage_start_time="2026-11-01T00:00:00Z",
        usage_end_time="2026-11-01T23:59:59Z",
        usage_date="2026-11-01",
        usage_unit="DBU",
        usage_quantity=80.0,  # Revised quantity
        record_type="restatement",
        ingestion_date="2026-11-04",
        billing_origin_product="SQL",
    )
    res = service.ingest_records([retract, revised])
    assert res["inserted_count"] == 2
    assert res["retraction_count"] == 1

    # Net contribution of the 3 records = 100 - 100 + 80 = 80 DBU ($176.00)
    net_rev_dbu = (
        service._usage_store["rec-orig-rev-01"].usage_quantity
        + service._usage_store["rec-retract-rev-01"].usage_quantity
        + service._usage_store["rec-revised-01"].usage_quantity
    )
    assert net_rev_dbu == 80.0


def test_duplicate_pagination_handling() -> None:
    """Verify that pagination overlaps (duplicate records across page boundaries) are cleanly deduplicated."""
    service = BillingIngestionService()
    initial_count = len(service._usage_store)

    page1_recs = [
        BillingUsageRecord(
            record_id=f"rec-page-rec-{i}",
            workspace_id="642006393507276",
            account_id="acc-dbx-az-01",
            sku_name="SERVERLESS_SQL_COMPUTE",
            cloud="azure",
            usage_start_time="2026-11-01T00:00:00Z",
            usage_end_time="2026-11-01T23:59:59Z",
            usage_date="2026-11-01",
            usage_unit="DBU",
            usage_quantity=10.0,
            record_type="original",
            ingestion_date="2026-11-02",
            billing_origin_product="SQL",
        )
        for i in range(1, 6)
    ]
    # Page 2 overlaps on rec-page-rec-5 and adds 6 and 7
    page2_recs = [
        BillingUsageRecord(
            record_id=f"rec-page-rec-{i}",
            workspace_id="642006393507276",
            account_id="acc-dbx-az-01",
            sku_name="SERVERLESS_SQL_COMPUTE",
            cloud="azure",
            usage_start_time="2026-11-01T00:00:00Z",
            usage_end_time="2026-11-01T23:59:59Z",
            usage_date="2026-11-01",
            usage_unit="DBU",
            usage_quantity=10.0,
            record_type="original",
            ingestion_date="2026-11-02",
            billing_origin_product="SQL",
        )
        for i in range(5, 8)
    ]

    res1 = service.ingest_records(page1_recs)
    assert res1["inserted_count"] == 5

    res2 = service.ingest_records(page2_recs)
    assert res2["inserted_count"] == 2  # rec-5 skipped as duplicate
    assert res2["duplicate_count"] == 1
    assert len(service._usage_store) == initial_count + 7


def test_overlapping_ingestion_windows() -> None:
    """Verify that query windows overlapping previously ingested dates insert only new delta records."""
    service = BillingIngestionService()
    initial_count = len(service._usage_store)

    # Window 1: Day 1 and Day 2
    w1 = [
        BillingUsageRecord(
            record_id="rec-win-day1",
            workspace_id="642006393507276",
            account_id="acc-dbx-az-01",
            sku_name="SERVERLESS_SQL_COMPUTE",
            cloud="azure",
            usage_start_time="2026-11-01T00:00:00Z",
            usage_end_time="2026-11-01T23:59:59Z",
            usage_date="2026-11-01",
            usage_unit="DBU",
            usage_quantity=10.0,
            record_type="original",
            ingestion_date="2026-11-02",
            billing_origin_product="SQL",
        ),
        BillingUsageRecord(
            record_id="rec-win-day2",
            workspace_id="642006393507276",
            account_id="acc-dbx-az-01",
            sku_name="SERVERLESS_SQL_COMPUTE",
            cloud="azure",
            usage_start_time="2026-11-02T00:00:00Z",
            usage_end_time="2026-11-02T23:59:59Z",
            usage_date="2026-11-02",
            usage_unit="DBU",
            usage_quantity=10.0,
            record_type="original",
            ingestion_date="2026-11-03",
            billing_origin_product="SQL",
        ),
    ]
    # Window 2: Day 2 (overlap) and Day 3 (new)
    w2 = [
        BillingUsageRecord(
            record_id="rec-win-day2",  # Already present
            workspace_id="642006393507276",
            account_id="acc-dbx-az-01",
            sku_name="SERVERLESS_SQL_COMPUTE",
            cloud="azure",
            usage_start_time="2026-11-02T00:00:00Z",
            usage_end_time="2026-11-02T23:59:59Z",
            usage_date="2026-11-02",
            usage_unit="DBU",
            usage_quantity=10.0,
            record_type="original",
            ingestion_date="2026-11-03",
            billing_origin_product="SQL",
        ),
        BillingUsageRecord(
            record_id="rec-win-day3",
            workspace_id="642006393507276",
            account_id="acc-dbx-az-01",
            sku_name="SERVERLESS_SQL_COMPUTE",
            cloud="azure",
            usage_start_time="2026-11-03T00:00:00Z",
            usage_end_time="2026-11-03T23:59:59Z",
            usage_date="2026-11-03",
            usage_unit="DBU",
            usage_quantity=10.0,
            record_type="original",
            ingestion_date="2026-11-04",
            billing_origin_product="SQL",
        ),
    ]

    service.ingest_records(w1)
    res = service.ingest_records(w2)
    assert res["inserted_count"] == 1  # Only day 3 inserted
    assert res["duplicate_count"] == 1  # Day 2 deduplicated
    assert len(service._usage_store) == initial_count + 3


def test_subscription_spend_aggregation_partial_accounting() -> None:
    """Verify that SubscriptionSpendAggregation strictly enforces partial total disclosures when components are unavailable."""
    comp_dbx = ComponentSpendCoverage(
        component_name="Databricks Platform Compute",
        reported_amount=Decimal("176840.00"),
        freshness_status=DataFreshnessStatus.INGESTED_HISTORICAL,
        is_eligible_for_actuals=True,
        lineage_source="system.billing.usage x system.billing.list_prices",
        record_count=24,
        notes="Verified DBU consumption and Lakehouse storage across 88,420 DBU",
    )
    comp_storage = ComponentSpendCoverage(
        component_name="Azure Storage (ADLS Gen2/Blob)",
        reported_amount=Decimal("79360.00"),
        freshness_status=DataFreshnessStatus.SOURCE_UNAVAILABLE,
        is_eligible_for_actuals=False,
        lineage_source="Unconfigured Azure Cost Management API",
        record_count=0,
        notes="Excluded from verified actuals; Cost Management Reader unconfigured",
    )
    comp_network = ComponentSpendCoverage(
        component_name="Azure Network (VNet/Egress)",
        reported_amount=Decimal("28420.00"),
        freshness_status=DataFreshnessStatus.SOURCE_UNAVAILABLE,
        is_eligible_for_actuals=False,
        lineage_source="Unconfigured Azure Cost Management API",
        record_count=0,
        notes="Excluded from verified actuals; Cost Management Reader unconfigured",
    )

    eligible_sum = sum(
        (
            c.reported_amount
            for c in [comp_dbx, comp_storage, comp_network]
            if c.is_eligible_for_actuals and c.reported_amount
        ),
        Decimal("0.00"),
    )
    total_est = sum(
        (c.reported_amount for c in [comp_dbx, comp_storage, comp_network] if c.reported_amount),
        Decimal("0.00"),
    )
    completeness = float((eligible_sum / total_est) * Decimal("100.0"))

    agg = SubscriptionSpendAggregation(
        period_start="2026-11-01",
        period_end="2026-11-30",
        verified_actual_spend=eligible_sum,
        is_partial_total=True,
        completeness_percentage=round(completeness, 1),
        components=[comp_dbx, comp_storage, comp_network],
        audit_notes=[
            "PARTIAL TOTAL: Verified actual spend represents only Databricks compute (62.1% coverage).",
            "Azure Storage ($79,360) and Azure Network ($28,420) are SOURCE_UNAVAILABLE and excluded.",
            "Never substitute baseline estimates or zero for missing cloud expenditure.",
        ],
    )

    assert agg.verified_actual_spend == Decimal("176840.00")
    assert agg.is_partial_total is True
    assert agg.completeness_percentage == 62.1
    assert len(agg.components) == 3
    assert agg.components[1].is_eligible_for_actuals is False
    assert agg.components[2].is_eligible_for_actuals is False
