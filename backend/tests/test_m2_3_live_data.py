"""M2.3 live-data integration tests (offline).

Verifies that no modelled value is presented as real data, that real inputs (ingested billing
rows, live inventory, Query History API results) are transformed correctly, and that every
unavailable source is labelled honestly. All inputs are offline test fixtures; nothing here
claims live Databricks verification.
"""

import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from cloud_recommender.api.routes.finops import get_finops_service
from cloud_recommender.schemas.billing_ingestion import BillingUsageRecord
from cloud_recommender.schemas.databricks import (
    DatabricksResourceState,
    DiscoveredResourceItem,
    LiveQueryHistoryItem,
)
from cloud_recommender.schemas.finops import KpiStatus
from cloud_recommender.services.databricks.billing_ingestion_service import BillingIngestionService
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService
from tests.fixtures.billing_baseline import add_synthetic_history
from tests.fixtures.live_inventory import (
    fixture_resources,
    make_analytics_service,
    stub_query_history,
)

MODULE_GETTERS = [
    "get_executive_overview",
    "get_cost_explorer",
    "get_cost_allocation",
    "get_compute_warehouses",
    "get_ai_economics",
    "get_data_storage",
    "get_network_cloud",
    "get_optimization_advisor",
    "get_forecast_budgets",
    "get_anomaly_detection",
    "get_governance_policies",
    "get_showback_chargeback",
    "get_workload_economics",
]

# Values/identifiers that only ever existed in the retired mock model
MOCK_SENTINELS = [
    "$42,180",
    "42180",
    "176,840",
    "284,620",
    "319,500",
    "$108,155",
    "k0qfl59u",
    "finops.bot",
    "CHG-2408",
    "anom-01",
    "dec-01",
    "unindexed_large_event_log",
    "AI COE budget",
    "10.28B",
]


# ---------------------------------------------------------------------------
# No mock leakage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("with_inventory", [True, False])
def test_no_billing_means_no_money_values_anywhere(with_inventory: bool) -> None:
    """Without ingested billing rows no module may present a money/DBU/token value."""
    svc = make_analytics_service(with_billing=False, with_inventory=with_inventory)
    money_units = {"USD", "DBU", "tokens", "USD/DBU", "USD/1K", "TB", "GB"}
    for name in MODULE_GETTERS:
        resp = getattr(svc, name)(connection_id="databricks-azure-dev")
        for key, kpi in resp.kpis.items():
            if kpi.unit in money_units:
                assert kpi.value is None, f"{name}.{key} fabricated a value"
                assert kpi.status not in (KpiStatus.LIVE, KpiStatus.CALCULATED, KpiStatus.BASELINE)
                assert kpi.formatted_value not in ("$0", "$0.00", "0")


def test_no_mock_sentinels_in_any_module_response() -> None:
    """Serialized responses (with and without billing) contain no retired mock figures."""
    for with_billing in (False, True):
        svc = make_analytics_service(with_billing=with_billing)
        blobs = [
            getattr(svc, name)(connection_id="databricks-azure-dev").model_dump_json()
            for name in MODULE_GETTERS
        ]
        blobs.append(svc.get_reports_audit().model_dump_json())
        blobs.append(svc.get_settings_integrations().model_dump_json())
        blobs.append(svc.get_system_tables().model_dump_json())
        for mod in ("overview", "cost_explorer", "ai_economics", "optimization_advisor"):
            blobs.append(svc.get_module_ai_analysis(mod).model_dump_json())
        text = "\n".join(blobs)
        for sentinel in MOCK_SENTINELS:
            assert sentinel not in text, (
                f"mock sentinel {sentinel!r} leaked (billing={with_billing})"
            )


def test_runtime_billing_store_is_empty_until_ingestion() -> None:
    svc = BillingIngestionService()
    assert svc._usage_store == {}
    assert svc._runs_store == []
    assert len(svc._price_store) > 0  # rate card is configuration, kept separate from usage


# ---------------------------------------------------------------------------
# Billing row ingestion (system.billing.usage -> BillingUsageRecord)
# ---------------------------------------------------------------------------


def _raw_row(**over: object) -> dict[str, object]:
    row: dict[str, object] = {
        "record_id": "r-1",
        "workspace_id": "642006393507276",
        "account_id": "acct",
        "sku_name": "STANDARD_ALL_PURPOSE_COMPUTE",
        "cloud": "AZURE",
        "usage_start_time": "2026-11-02 00:00:00",
        "usage_end_time": "2026-11-02 01:00:00",
        "usage_date": "2026-11-02",
        "usage_unit": "DBU",
        "usage_quantity": "12.5",
        "record_type": "ORIGINAL",
        "billing_origin_product": "ALL_PURPOSE",
        "custom_tags": '{"Owner": "Finance"}',
        "usage_metadata": {"cluster_id": "1102-081455-7t3bqp3v"},
    }
    row.update(over)
    return row


def test_row_mapping_parses_json_maps_and_numeric_strings() -> None:
    rec = BillingIngestionService._row_to_usage_record(_raw_row())
    assert rec is not None
    assert rec.usage_quantity == 12.5 and rec.cloud == "azure" and rec.record_type == "original"
    assert rec.custom_tags == {"Owner": "Finance"}
    assert rec.usage_metadata == {"cluster_id": "1102-081455-7t3bqp3v"}


def test_row_mapping_rejects_malformed_rows() -> None:
    bad_qty = _raw_row(usage_quantity="not-a-number")
    missing_id = _raw_row()
    del missing_id["record_id"]
    missing_sku = _raw_row()
    del missing_sku["sku_name"]
    for row in (bad_qty, missing_id, missing_sku):
        assert BillingIngestionService._row_to_usage_record(row) is None


def test_approved_ingestion_run_populates_store_and_is_idempotent() -> None:
    """An approved run (SQL stubbed offline) maps rows, prices them and never double counts."""
    svc = BillingIngestionService()
    rows = [
        _raw_row(),
        _raw_row(record_id="r-2", usage_quantity="-2.5", record_type="RETRACTION"),
        {"record_id": "broken"},
    ]

    class _Sql:
        def __init__(self) -> None:
            self.calls = 0

        def execute_read_only_statement(self, **_: object) -> list[dict[str, object]]:
            self.calls += 1
            return rows

    stub = _Sql()
    svc._get_sql_service_for_workspace = lambda _w: stub  # type: ignore[method-assign,assignment]
    from cloud_recommender.schemas.billing_ingestion import IngestionRunCreateRequest

    req = IngestionRunCreateRequest(is_approved=True, approval_token="TEST-APPROVED-TOKEN")
    first = svc.run_ingestion(req)
    assert first.status == "completed"
    assert (first.extracted_count, first.inserted_count, first.error_count) == (3, 2, 1)
    assert first.retraction_count == 1
    assert sum(r.usage_quantity for r in svc._usage_store.values()) == 10.0  # 12.5 - 2.5
    priced = svc._usage_store["r-1"]
    assert priced.pricing_matched and priced.effective_cost == pytest.approx(27.5)  # 12.5 x 2.20

    second = svc.run_ingestion(req)
    assert second.inserted_count == 0 and second.duplicate_count == 2
    assert len(svc._usage_store) == 2


# ---------------------------------------------------------------------------
# Allocation / showback: real tags only, unallocated stays unallocated
# ---------------------------------------------------------------------------


def test_allocation_keeps_untagged_spend_unallocated_and_never_distributes_it() -> None:
    svc = make_analytics_service(with_billing=False)
    svc.billing_service.ingest_records(
        [
            BillingUsageRecord(
                record_id="t-1",
                workspace_id="642006393507276",
                sku_name="SERVERLESS_SQL_COMPUTE",
                usage_start_time="2026-11-01T00:00:00Z",
                usage_end_time="2026-11-01T01:00:00Z",
                usage_date="2026-11-01",
                usage_unit="DBU",
                usage_quantity=100.0,
                billing_origin_product="SQL",
                custom_tags={"team": "Growth"},
            ),
            BillingUsageRecord(
                record_id="t-2",
                workspace_id="642006393507276",
                sku_name="SERVERLESS_SQL_COMPUTE",
                usage_start_time="2026-11-01T00:00:00Z",
                usage_end_time="2026-11-01T01:00:00Z",
                usage_date="2026-11-01",
                usage_unit="DBU",
                usage_quantity=50.0,
                billing_origin_product="SQL",
                custom_tags={},
            ),
        ]
    )
    alloc = svc.get_cost_allocation()
    buckets = {b["business_unit"]: b["spend"] for b in alloc.spend_by_bu}
    assert buckets == {"Growth": 220.0, "Unallocated": 110.0}
    assert alloc.kpis["allocated_spend"].value == 220.0
    assert alloc.kpis["unallocated_spend"].value == 110.0
    assert alloc.allocation_completeness == {
        "tagged_records": 1,
        "untagged_records": 1,
        "allocated_pct": 50,
    }

    sb = svc.get_showback_chargeback()
    by_bu = {s.business_unit: s for s in sb.statements}
    assert by_bu["Unallocated"].total == 110.0 and by_bu["Growth"].total == 220.0
    assert all(s.shared_allocation is None for s in sb.statements)  # nothing spread artificially
    assert sb.kpis["statement_readiness"].value == pytest.approx(66.7, abs=0.05)

    assert svc.get_cost_explorer().kpis["unallocated_spend"].value == 110.0


def test_retractions_reduce_spend_and_are_not_dropped() -> None:
    svc = make_analytics_service(with_billing=False)
    svc.billing_service.ingest_records(
        [
            BillingUsageRecord(
                record_id=rid,
                workspace_id="642006393507276",
                sku_name="SERVERLESS_SQL_COMPUTE",
                usage_start_time="2026-11-01T00:00:00Z",
                usage_end_time="2026-11-01T01:00:00Z",
                usage_date="2026-11-01",
                usage_unit="DBU",
                usage_quantity=q,
                record_type=rt,
                billing_origin_product="SQL",
            )
            for rid, q, rt in (("o", 100.0, "original"), ("x", -40.0, "retraction"))
        ]
    )
    assert svc.get_executive_overview().kpis["dbu_consumption"].value == 60.0
    assert svc.get_executive_overview().kpis["total_spend"].value == pytest.approx(132.0)


# ---------------------------------------------------------------------------
# Forecast / anomaly: only with enough history
# ---------------------------------------------------------------------------


def test_flat_history_has_no_anomaly_and_spike_is_detected() -> None:
    flat = make_analytics_service(with_billing=False)
    add_synthetic_history(flat.billing_service, days=20)
    assert flat.get_anomaly_detection().anomalies == []
    assert flat.get_anomaly_detection().kpis["open_anomalies"].value == 0.0
    assert flat.get_anomaly_detection().kpis["open_anomalies"].status == KpiStatus.CALCULATED

    spiky = make_analytics_service(with_billing=False)
    add_synthetic_history(spiky.billing_service, days=20, spike_day=15, spike_dbu=500.0)
    found = spiky.get_anomaly_detection().anomalies
    assert [a.id for a in found] == ["anom-2026-11-15"]
    assert found[0].severity == "Critical" and found[0].resource_type == "workspace"
    assert spiky.get_executive_overview().kpis["anomalies"].value == 1.0


def test_forecast_never_runs_on_thin_history_and_is_labelled_estimated() -> None:
    thin = make_analytics_service(with_billing=False)
    add_synthetic_history(thin.billing_service, days=13)
    assert (
        thin.get_executive_overview().kpis["forecast_spend"].status
        == KpiStatus.INSUFFICIENT_HISTORY
    )
    assert thin.get_forecast_budgets().kpis["forecast_month_end"].value is None

    ok = make_analytics_service(with_billing=False)
    add_synthetic_history(ok.billing_service, days=14)
    fc = ok.get_forecast_budgets().kpis
    assert fc["forecast_month_end"].status == KpiStatus.ESTIMATED
    assert fc["forecast_month_end"].value == pytest.approx(110.0 * 14 + 110.0 * 16)
    assert fc["actual_mtd"].status == KpiStatus.CALCULATED  # actual stays distinct from forecast
    assert fc["approved_budget"].value is None  # no budget configured -> not invented


# ---------------------------------------------------------------------------
# Recommendations: rule negatives, evidence, workflow
# ---------------------------------------------------------------------------


def _with_resources(svc: FinOpsAnalyticsService, resources: list[DiscoveredResourceItem]) -> None:
    from cloud_recommender.schemas.databricks import DatabricksWorkspaceDiscoveryResponse

    cache = svc.workspace_service._discovery_cache["databricks-azure-dev"]
    svc.workspace_service._discovery_cache["databricks-azure-dev"] = (
        DatabricksWorkspaceDiscoveryResponse(
            **{
                **cache.model_dump(),
                "resources": resources,
                "total_resources_count": len(resources),
            }
        )
    )


def test_recommendation_rules_do_not_fire_on_healthy_configuration() -> None:
    svc = make_analytics_service(with_billing=False)
    healthy = []
    for r in fixture_resources():
        meta = dict(r.metadata)
        if r.resource_type == "cluster":
            meta["autotermination_minutes"] = 30
        if r.resource_type == "warehouse":
            meta["auto_stop_mins"] = 10
        if r.resource_type == "serving_endpoint":
            meta["served_entities"] = [{"workload_size": "Small", "scale_to_zero_enabled": True}]
        healthy.append(r.model_copy(update={"metadata": meta}))
    _with_resources(svc, healthy)
    assert svc.get_optimization_advisor().recommendations == []
    assert svc.get_optimization_advisor().kpis["quick_wins"].value == 0.0


def test_recommendation_thresholds_and_evidence() -> None:
    svc = make_analytics_service(with_billing=False)
    res = []
    for r in fixture_resources():
        meta = dict(r.metadata)
        if r.resource_type == "cluster":
            meta["autotermination_minutes"] = 120
        if r.resource_type == "warehouse":
            meta["auto_stop_mins"] = 0
        res.append(r.model_copy(update={"metadata": meta}))
    _with_resources(svc, res)
    recs = {r.id: r for r in svc.get_optimization_advisor().recommendations}
    cl = recs["rec-cl-longterm-1102-081455-7t3bqp3v"]
    assert "autotermination_minutes=120" in cl.evidence
    wh = recs["rec-wh-autostop-05ed10a52697a344"]
    assert "disabled" in wh.finding and "auto_stop_mins=0" in wh.evidence
    assert wh.current_cost == "-"


def test_recommendation_current_cost_uses_real_rows_when_available() -> None:
    svc = make_analytics_service(with_billing=True)
    wh = next(
        r
        for r in svc.get_optimization_advisor().recommendations
        if r.category == "Compute" and r.resource_id == "05ed10a52697a344"
    )
    assert wh.current_cost == "$42,178.40"
    assert wh.estimated_savings_monthly is None  # still not calculable


# ---------------------------------------------------------------------------
# Governance / data / AI from live inventory
# ---------------------------------------------------------------------------


def test_governance_checklist_is_computed_from_live_configuration() -> None:
    svc = make_analytics_service(with_billing=False)
    gov = svc.get_governance_policies()
    checks = {c["label"]: c["checked"] for c in gov.checklist}
    assert checks["Cluster policies are defined"] is True
    assert checks["All clusters have auto-termination configured"] is False
    assert checks["All SQL warehouses auto-stop within 10 minutes"] is False  # fixture: 15 min
    assert gov.kpis["resources_without_owner"].value == 0.0
    assert gov.kpis["policy_compliance"].status == KpiStatus.UNAVAILABLE  # no scanner source
    assert gov.kpis["expiring_exceptions"].status == KpiStatus.UNAVAILABLE


def test_data_storage_uses_unity_catalog_cache_for_tables() -> None:
    from cloud_recommender.schemas.databricks import (
        CategoryDiscoveryStatus,
        UnityCatalogCatalogItem,
        UnityCatalogMetadataResponse,
        UnityCatalogSchemaItem,
        UnityCatalogTableItem,
    )

    svc = make_analytics_service(with_billing=False)
    table = UnityCatalogTableItem(
        catalog_name="deaccelerator",
        schema_name="bronze",
        name="orders",
        full_name="deaccelerator.bronze.orders",
        table_type="MANAGED",
        data_source_format="DELTA",
    )
    svc.workspace_service._uc_cache["databricks-azure-dev"] = UnityCatalogMetadataResponse(
        connection_id="databricks-azure-dev",
        workspace_id="642006393507276",
        workspace_url="https://example.invalid",
        status=CategoryDiscoveryStatus.AVAILABLE,
        discovery_state=DatabricksResourceState.LIVE,
        retrieved_at=datetime.now(UTC),
        catalogs=[
            UnityCatalogCatalogItem(
                name="deaccelerator",
                schemas=[
                    UnityCatalogSchemaItem(
                        catalog_name="deaccelerator",
                        name="bronze",
                        full_name="deaccelerator.bronze",
                        tables=[table],
                    )
                ],
            )
        ],
        total_catalogs=1,
        total_schemas=1,
        total_tables=1,
    )
    data = svc.get_data_storage()
    assert [t.catalog_schema_table for t in data.tables] == ["deaccelerator.bronze.orders"]
    assert data.tables[0].storage_type == "MANAGED / DELTA"
    assert data.tables[0].size == "-"  # UC REST metadata has no size
    assert data.provenance["tables"].classification == KpiStatus.LIVE
    assert data.provenance["tables"].record_count == 1


def test_workload_economics_lists_unbilled_jobs_without_cost() -> None:
    svc = make_analytics_service(with_billing=False)
    job = DiscoveredResourceItem(
        id="42",
        name="nightly",
        resource_type="job",
        workspace_id="642006393507276",
        source_api="test",
        discovered_at=datetime.now(UTC),
    )
    _with_resources(svc, [*fixture_resources(), job])
    wl = svc.get_workload_economics().workloads
    assert [(w.workload, w.monthly_spend, w.unit_cost) for w in wl] == [("nightly", None, "-")]
    assert svc.get_workload_economics().kpis["avg_cost_workload"].value is None


def test_workload_economics_costs_workloads_from_billing_rows() -> None:
    svc = make_analytics_service(with_billing=True)
    wl = {w.workload: w for w in svc.get_workload_economics().workloads}
    assert wl["Serverless Starter Warehouse"].monthly_spend == pytest.approx(42178.4)
    assert wl["Serverless Starter Warehouse"].unit_cost == "-"
    assert wl["job-etl-pipeline-nightly"].workload_type == "job"
    assert wl["job-etl-pipeline-nightly"].owner == "DataPlatform"


# ---------------------------------------------------------------------------
# Query history: live API mapping, errors, route + pagination
# ---------------------------------------------------------------------------


def test_query_history_error_states_are_labelled_not_empty_success() -> None:
    import asyncio

    for state, expected in (
        (DatabricksResourceState.ACCESS_DENIED, KpiStatus.NOT_AUTHORIZED),
        (DatabricksResourceState.UNAVAILABLE, KpiStatus.UNAVAILABLE),
        (DatabricksResourceState.NO_DATA, KpiStatus.NO_DATA),
    ):
        svc = make_analytics_service(with_billing=False)
        stub_query_history(svc, state=state, error_message="why")
        hist = asyncio.run(svc.get_query_history())
        assert hist.records == []
        assert hist.provenance is not None and hist.provenance.classification == expected
        assert hist.provenance.message == "why"


@pytest.mark.asyncio
async def test_query_history_route_pagination_and_date_filters(app: FastAPI) -> None:
    svc = make_analytics_service(with_billing=False)
    items = [
        LiveQueryHistoryItem(
            query_id=f"q-{i}",
            status="FINISHED",
            warehouse_id="05ed10a52697a344",
            start_time="2026-11-05T00:00:00+00:00",
            duration_ms=10.0,
            sql_summary="SELECT 1",
        )
        for i in range(2)
    ]
    calls = stub_query_history(
        svc, items, state=DatabricksResourceState.LIVE, has_next_page=True, next_page_token="n2"
    )
    app.dependency_overrides[get_finops_service] = lambda: svc
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/api/v1/finops/query-history",
            params={
                "limit": 2,
                "page_token": "n1",
                "status": "FINISHED",
                "start_time_ms": 1000,
                "end_time_ms": 2000,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 2 and body["has_next_page"] is True
        assert body["next_page_token"] == "n2"
        assert body["provenance"]["classification"] == "LIVE"
        assert json.dumps(body).count("cost_correlation_dbu") == 2  # field present, value null
        assert all(r["cost_correlation_dbu"] is None for r in body["records"])
        assert calls[0]["page_token"] == "n1" and calls[0]["max_results"] == 2
        assert (calls[0]["start_time_ms"], calls[0]["end_time_ms"]) == (1000, 2000)

        bad = await client.get("/api/v1/finops/query-history", params={"limit": 1000})
        assert bad.status_code == 422  # page size is bounded
