"""Pre-P2 corrections: D5 attribution completeness and currency honesty in analytics.

Fully offline: no SQL, no warehouse, no network, no cloud call.
"""

from decimal import Decimal
from typing import Any

import pytest

from cloud_recommender.schemas.billing_ingestion import BillingPriceRecord
from cloud_recommender.schemas.finops import KpiStatus
from cloud_recommender.services.databricks.billing_ingestion_service import (
    BillingIngestionService,
)
from cloud_recommender.services.databricks.billing_sql import (
    ATTRIBUTION_RULES,
    resolve_resource,
)
from cloud_recommender.services.databricks.finops_analytics_service import (
    FinOpsAnalyticsService,
    format_money,
)
from tests.fixtures.live_inventory import make_analytics_service
from tests.test_m7_1_billing_hardening import WS, _priced_service, _rec, _sql

EXPECTED_LABELS = {
    "warehouse_id": "warehouse",
    "endpoint_id": "serving",
    "endpoint_name": "serving",
    "app_id": "app",
    "job_id": "job",
    "dlt_pipeline_id": "pipeline",
    "cluster_id": "cluster",
    "instance_pool_id": "pool",
    "notebook_id": "notebook",
    "serverless_compute_id": "serverless",
}


def _analytics(billing: BillingIngestionService) -> FinOpsAnalyticsService:
    service = make_analytics_service(with_billing=False, with_inventory=False)
    service._billing_service = billing
    return service


def _price(sku: str, rate: str, currency: str) -> BillingPriceRecord:
    return BillingPriceRecord(
        sku_name=sku,
        currency_code=currency,
        price_default=Decimal(rate),
        price_start_time="2026-01-01T00:00:00Z",
    )


def _service_in(currency: str, rate: str = "2.00") -> BillingIngestionService:
    svc = BillingIngestionService(sql_service=_sql())
    svc.ingest_price_records([_price("SERVERLESS_SQL_COMPUTE", rate, currency)])
    svc.ingest_records(
        [
            _rec("r1", 10),
            _rec(
                "r2",
                5,
                usage_start_time="2026-11-02T00:00:00Z",
                usage_end_time="2026-11-02T01:00:00Z",
                usage_date="2026-11-02",
            ),
        ]
    )
    return svc


def _mixed_service() -> BillingIngestionService:
    svc = BillingIngestionService(sql_service=_sql())
    svc.ingest_price_records([_price("SKU_USD", "1.00", "USD"), _price("SKU_EUR", "2.00", "EUR")])
    svc.ingest_records([_rec("u1", 10, sku_name="SKU_USD"), _rec("e1", 10, sku_name="SKU_EUR")])
    return svc


# ===================================================================== D5 attribution


def test_d5_every_billing_attribution_key_is_supported_by_analytics() -> None:
    assert {k for k, _ in ATTRIBUTION_RULES} == set(EXPECTED_LABELS)
    assert dict(FinOpsAnalyticsService._RESOURCE_META_KEYS) == EXPECTED_LABELS
    # same priority order as the ingestion-time rules
    assert [k for k, _ in FinOpsAnalyticsService._RESOURCE_META_KEYS] == [
        k for k, _ in ATTRIBUTION_RULES
    ]


@pytest.mark.parametrize(("key", "label"), sorted(EXPECTED_LABELS.items()))
def test_d5_row_is_attributed_to_the_right_resource_in_billing_and_analytics(
    key: str, label: str
) -> None:
    svc = _priced_service()
    svc.ingest_records(
        [
            _rec("target", 7, usage_metadata={key: "res-A"}),
            _rec("other", 3, usage_metadata={key: "res-B"}),
            _rec("bystander", 11, usage_metadata={"warehouse_id": "wh-unrelated"}),
        ]
    )
    analytics = _analytics(svc)
    target = svc._usage_store["target"]

    assert analytics._resource_of(target) == (label, "res-A")
    billing_type, billing_id = resolve_resource(target.usage_metadata) or ("", "")
    assert billing_id == "res-A" and _LABEL_OF_TYPE[billing_type] == label

    # billing summary scopes by exact id
    summary = svc.get_billing_summary(workspace_id=WS, resource_id="res-A")
    assert summary.data_status == "INGESTED" and summary.net_dbu == 7.0
    # analytics filters by type + exact id, and by id alone
    typed = analytics._billing_rows("all", label, "res-A")
    assert [r.record_id for r in typed] == ["target"]
    assert [r.record_id for r in analytics._billing_rows("all", None, "res-A")] == ["target"]
    # a partial id never matches
    assert analytics._billing_rows("all", label, "res-") == []
    # all rows of the type, when no id is given
    assert {r.record_id for r in analytics._billing_rows("all", label, None)} >= {"target", "other"}


_LABEL_OF_TYPE = {
    "SQL_WAREHOUSE": "warehouse",
    "SERVING_ENDPOINT": "serving",
    "APP": "app",
    "JOB": "job",
    "PIPELINE": "pipeline",
    "CLUSTER": "cluster",
    "POOL": "pool",
    "NOTEBOOK": "notebook",
    "SERVERLESS": "serverless",
}


def test_d5_priority_is_identical_when_a_row_carries_several_keys() -> None:
    svc = _priced_service()
    svc.ingest_records(
        [
            _rec(
                "multi",
                4,
                usage_metadata={"job_id": "job-1", "warehouse_id": "wh-1", "cluster_id": "c-1"},
            )
        ]
    )
    rec = svc._usage_store["multi"]
    assert _analytics(svc)._resource_of(rec) == ("warehouse", "wh-1")
    assert resolve_resource(rec.usage_metadata) == ("SQL_WAREHOUSE", "wh-1")


def test_d5_existing_warehouse_cluster_serving_app_filters_still_work() -> None:
    svc = _priced_service()
    svc.ingest_records(
        [
            _rec("w", 1, usage_metadata={"warehouse_id": "w1"}),
            _rec("c", 1, usage_metadata={"cluster_id": "c1"}),
            _rec("s", 1, usage_metadata={"endpoint_name": "ep1"}),
            _rec("a", 1, usage_metadata={"app_id": "app1"}),
        ]
    )
    analytics = _analytics(svc)
    for label, rid, rec_id in (
        ("warehouse", "w1", "w"),
        ("cluster", "c1", "c"),
        ("serving", "ep1", "s"),
        ("app", "app1", "a"),
    ):
        assert [r.record_id for r in analytics._billing_rows("all", label, rid)] == [rec_id]


def test_d5_rows_with_only_newly_supported_keys_get_a_resource_driver() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec("p", 9, usage_metadata={"instance_pool_id": "pool-1"})])
    overview = _analytics(svc).get_executive_overview()
    assert any(d.driver == "pool: pool-1" for d in overview.top_cost_drivers)


# ===================================================================== currency: helper


def test_format_money_keeps_the_real_currency() -> None:
    assert format_money(1234.5, "USD") == "$1,234.50"
    assert format_money(1234.5, "EUR") == "1,234.50 EUR"
    assert format_money(0.5, "inr", 4) == "0.5000 INR"


# ===================================================================== currency: USD


def test_usd_scope_keeps_dollar_formatting_and_usd_currency() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec("u", 10)])
    ov = _analytics(svc).get_executive_overview()
    spend = ov.kpis["total_spend"]
    assert spend.currency == "USD" and spend.unit == "USD"
    assert spend.formatted_value.startswith("$") and spend.status == KpiStatus.CALCULATED
    rate = _analytics(svc).get_cost_explorer().kpis["effective_rate"]
    assert rate.currency == "USD" and rate.formatted_value.startswith("$")
    assert rate.formatted_value.endswith("/ DBU")


# ===================================================================== currency: non-USD


def test_eur_scope_is_labelled_eur_everywhere_and_never_as_dollars() -> None:
    analytics = _analytics(_service_in("EUR"))
    ov = analytics.get_executive_overview()
    spend = ov.kpis["total_spend"]
    assert spend.currency == "EUR" and spend.unit == "EUR"
    assert spend.value == pytest.approx(30.0) and spend.formatted_value == "30.00 EUR"

    ce = analytics.get_cost_explorer()
    assert ce.kpis["effective_rate"].unit == "EUR/DBU"
    assert ce.kpis["effective_rate"].formatted_value == "2.0000 EUR / DBU"
    assert ce.kpis["gross_consumption"].currency == "EUR"
    for kpi in (*ov.kpis.values(), *ce.kpis.values()):
        assert "$" not in kpi.formatted_value and "USD" not in (kpi.unit or "")
        assert kpi.currency in (None, "EUR")


def test_eur_csv_export_is_headed_with_the_real_currency_and_has_no_dollar_signs() -> None:
    csv_text = _analytics(_service_in("EUR")).export_cost_ledger_csv()
    header, *body = csv_text.strip().splitlines()
    assert "List Cost (EUR)" in header and "Effective Cost (EUR)" in header and "USD" not in header
    assert body and all("$" not in line for line in body)


def test_eur_drivers_and_anomaly_text_use_eur() -> None:
    drivers = _analytics(_service_in("EUR")).get_executive_overview().top_cost_drivers
    assert drivers and all(d.formatted_spend.endswith(" EUR") for d in drivers)


def test_rate_card_rows_show_their_own_currency() -> None:
    svc = _service_in("EUR", rate="0.12345")
    cards = _analytics(svc).get_settings_integrations().rate_cards
    assert cards and all("EUR" in c.list_rate and "$" not in c.list_rate for c in cards)


def test_non_money_kpis_carry_no_currency() -> None:
    ov = _analytics(_service_in("EUR")).get_executive_overview()
    assert ov.kpis["dbu_consumption"].currency is None


# ===================================================================== currency: mixed


def test_mixed_currency_kpis_are_unavailable_and_explained_never_summed() -> None:
    ov = _analytics(_mixed_service()).get_executive_overview()
    for key in ("total_spend", "databricks_spend", "ai_spend"):
        kpi = ov.kpis[key]
        assert kpi.value is None and kpi.status == KpiStatus.UNAVAILABLE
        assert kpi.formatted_value == "-" and kpi.currency is None
        assert "more than one currency" in (kpi.reason or "")
        assert "USD" in (kpi.reason or "") and "EUR" in (kpi.reason or "")
    assert ov.kpis["dbu_consumption"].value == pytest.approx(20.0)  # quantities stay visible


def test_mixed_currency_csv_has_no_amounts_and_says_why() -> None:
    csv_text = _analytics(_mixed_service()).export_cost_ledger_csv()
    header, *body = csv_text.strip().splitlines()
    assert "mixed currencies" in header and "$" not in csv_text
    assert body
    for line in body:
        cells = line.split(",")
        assert cells[6] == "" and cells[7] == ""  # list/effective cost columns are empty


def test_mixed_currency_cost_drivers_never_render_a_misleading_total() -> None:
    drivers = _analytics(_mixed_service()).get_executive_overview().top_cost_drivers
    assert drivers
    assert all("$" not in d.formatted_spend for d in drivers)


def test_mixed_currency_provenance_says_costs_are_withheld() -> None:
    analytics = _analytics(_mixed_service())
    rows = analytics._billing_rows("all")
    assert "withheld" in (analytics._billing_provenance(rows).message or "")


# ===================================================================== currency: unknown / budget


def test_no_billing_rows_means_no_currency_claim() -> None:
    ov = make_analytics_service(with_billing=False, with_inventory=False).get_executive_overview()
    for kpi in ov.kpis.values():
        assert kpi.currency is None and "USD" not in (kpi.unit or "")
        assert "$" not in kpi.formatted_value


def _forecast_with_budget(billing: BillingIngestionService) -> Any:
    analytics = _analytics(billing)
    analytics._budget = lambda: 1000.0  # type: ignore[method-assign]
    return analytics.get_forecast_budgets()


def test_budget_is_confirmed_usd_and_only_compared_with_usd_actuals() -> None:
    usd = _forecast_with_budget(_service_in("USD"))
    assert usd.kpis["approved_budget"].currency == "USD"
    assert usd.kpis["budget_utilization"].value is not None
    assert usd.budget_controls

    eur = _forecast_with_budget(_service_in("EUR"))
    assert eur.kpis["approved_budget"].currency == "USD"  # the setting itself is USD
    assert eur.kpis["actual_mtd"].currency == "EUR"
    assert eur.kpis["budget_utilization"].value is None
    assert eur.kpis["projected_overrun"].value is None
    assert eur.budget_controls == []  # a USD budget is never compared with EUR actuals


def test_budget_with_mixed_currencies_is_not_compared() -> None:
    out = _forecast_with_budget(_mixed_service())
    assert out.kpis["budget_utilization"].value is None
    assert out.kpis["actual_mtd"].value is None
    assert out.kpis["actual_mtd"].status == KpiStatus.UNAVAILABLE


def test_currency_state_does_not_leak_between_requests() -> None:
    eur = _analytics(_service_in("EUR"))
    usd_svc = _priced_service()
    usd_svc.ingest_records([_rec("u", 10)])
    usd = _analytics(usd_svc)
    assert eur.get_executive_overview().kpis["total_spend"].currency == "EUR"
    assert usd.get_executive_overview().kpis["total_spend"].currency == "USD"
    assert eur.get_executive_overview().kpis["total_spend"].currency == "EUR"
    empty = make_analytics_service(with_billing=False, with_inventory=False)
    assert empty.get_executive_overview().kpis["total_spend"].currency is None
