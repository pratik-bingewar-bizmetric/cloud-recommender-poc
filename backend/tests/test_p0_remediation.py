"""P0 remediation tests (M7.1 pre-commit review findings).

Covers D10 (preview defaults), D4 (canonical timestamps), D5 (analytics attribution),
mixed currencies, C1 (statement completeness), C2 (rate-card completeness) and the signed
approval-token scope (row limit, date window, exact SQL, single use).

Fully offline: no SQL is executed, no warehouse is started, no network is used.
"""

import re
import threading
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cloud_recommender.schemas.billing_ingestion import (
    BillingPriceRecord,
    IngestionRunCreateRequest,
)
from cloud_recommender.services.databricks import sql_client as sql_client_module
from cloud_recommender.services.databricks.billing_ingestion_service import (
    BillingIngestionService,
)
from cloud_recommender.services.databricks.billing_sql import (
    PRICE_ROW_LIMIT,
    MatchStatus,
    build_list_prices_query,
    build_usage_query,
    canonical_timestamp,
)
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService
from cloud_recommender.services.databricks.sql_client import (
    ApprovalRequiredError,
    DatabricksSqlService,
    StatementIncompleteError,
    statement_row_limit,
)
from tests.test_m7_1_billing_hardening import (
    WH,
    WS,
    _FakeClient,
    _priced_service,
    _rec,
    _sql,
    _statement_response,
    _token,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "cloud_recommender"
COLS = ["record_id", "workspace_id", "sku_name", "usage_unit", "usage_quantity"]


def _price(sku: str, rate: str, currency: str = "USD", start: str = "2026-01-01T00:00:00Z") -> Any:
    return BillingPriceRecord(
        sku_name=sku,
        currency_code=currency,
        price_default=Decimal(rate),
        price_start_time=start,
    )


# ============================================================ D10 preview defaults


def test_d10_preview_route_has_no_hardcoded_dates() -> None:
    text = (SRC / "api/routes/finops.py").read_text(encoding="utf-8")
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", text), "stale date literal in finops routes"


def test_d10_preview_defaults_are_derived_from_today() -> None:
    from datetime import UTC, datetime

    svc = BillingIngestionService(sql_service=_sql())
    res = svc.preview_ingestion(workspace_id=WS)
    today = datetime.now(UTC).date()
    assert res.period_end == today.isoformat()
    assert res.period_start == today.replace(day=1).isoformat()


# ============================================================ D4 canonical identity


@pytest.mark.parametrize(
    "variant",
    [
        "2026-11-01T00:00:00Z",
        "2026-11-01T00:00:00.000+00:00",
        "2026-11-01 00:00:00",
        "2026-11-01T05:30:00+05:30",
    ],
)
def test_d4_timestamp_formatting_does_not_change_identity(variant: str) -> None:
    assert canonical_timestamp(variant) == canonical_timestamp("2026-11-01T00:00:00Z")


def test_d4_reextract_with_different_timestamp_format_is_a_duplicate() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    first = svc.ingest_records([_rec("t1", usage_start_time="2026-11-01T00:00:00Z")])
    again = svc.ingest_records([_rec("t1", usage_start_time="2026-11-01T00:00:00.000+00:00")])
    assert first["inserted_count"] == 1
    assert again["inserted_count"] == 0 and again["duplicate_count"] == 1


def test_d4_correction_in_a_later_run_is_kept_and_counted_as_shared_id() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    svc.ingest_records([_rec("c1", 10)])
    stats = svc.ingest_records([_rec("c1", -10, record_type="retraction")])
    assert stats["inserted_count"] == 1
    assert stats["shared_record_id_count"] == 1  # visible although it landed in a later run


def test_d4_unparsable_timestamp_is_kept_verbatim_not_guessed() -> None:
    assert canonical_timestamp("not-a-time ") == "not-a-time"
    assert canonical_timestamp(None) == ""


# ============================================================ D5 analytics attribution


def test_d5_app_filter_uses_app_id_only() -> None:
    assert FinOpsAnalyticsService._FILTER_META_KEYS["app"] == ("app_id",)
    keys = [k for k, _ in FinOpsAnalyticsService._RESOURCE_META_KEYS]
    assert "app_name" not in keys
    # same priority order as the ingestion-time attribution rules
    from cloud_recommender.services.databricks.billing_sql import ATTRIBUTION_RULES

    shared = [k for k in (k for k, _ in ATTRIBUTION_RULES) if k in keys]
    assert [k for k in keys if k in shared] == shared


def _analytics(svc: BillingIngestionService) -> FinOpsAnalyticsService:
    analytics = FinOpsAnalyticsService.__new__(FinOpsAnalyticsService)
    analytics._billing_service = svc  # type: ignore[attr-defined]
    analytics.validate_scope = lambda _w: ["all"]  # type: ignore[method-assign,assignment]
    return analytics


def test_d5_app_rows_are_found_by_app_id_and_not_by_substring() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec("a1", 5, usage_metadata={"app_id": "app-uuid-1"})])
    analytics = _analytics(svc)
    assert len(analytics._billing_rows("all", "app", "app-uuid-1")) == 1
    assert analytics._billing_rows("all", "app", "app-uuid") == []
    assert analytics._billing_rows("all", None, "app-uuid") == []
    assert len(analytics._billing_rows("all", None, "app-uuid-1")) == 1


# ============================================================ mixed currencies


def test_currency_equal_rates_in_different_currencies_are_ambiguous_not_merged() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    svc.ingest_price_records(
        [
            _price("SERVERLESS_SQL_COMPUTE", "0.70", "USD"),
            _price("SERVERLESS_SQL_COMPUTE", "0.70", "EUR"),
        ]
    )
    svc.ingest_records([_rec("m1", 10)])
    rec = svc._usage_store["m1"]
    assert rec.match_status == MatchStatus.AMBIGUOUS
    assert rec.effective_cost is None and rec.currency is None


def _two_currency_service() -> BillingIngestionService:
    svc = BillingIngestionService(sql_service=_sql())
    svc.ingest_price_records([_price("SKU_USD", "1.00", "USD"), _price("SKU_EUR", "2.00", "EUR")])
    svc.ingest_records([_rec("u1", 10, sku_name="SKU_USD"), _rec("e1", 10, sku_name="SKU_EUR")])
    return svc


def test_currency_summary_never_sums_across_currencies() -> None:
    summary = _two_currency_service().get_billing_summary(workspace_id=WS)
    assert summary.total_spend_verified is None and summary.currency is None
    assert summary.spend_complete is False
    assert {(r["currency"], r["spend"]) for r in summary.spend_by_currency} == {
        ("USD", 10.0),
        ("EUR", 20.0),
    }
    assert summary.total_dbu == 20.0  # quantities are unaffected


def test_currency_reconciliation_reports_per_currency_and_flags() -> None:
    rec = _two_currency_service().get_billing_reconciliation(workspace_id=WS)
    assert rec.gross_cost is None and rec.net_cost is None and rec.currency is None
    assert {r["currency"] for r in rec.cost_by_currency} == {"USD", "EUR"}
    single = next(c for c in rec.checks if c["name"] == "single_currency")
    assert single["passed"] is False
    assert rec.reconciliation_status == "DISCREPANCY_DETECTED"


def test_currency_single_currency_totals_are_unchanged() -> None:
    summary = _priced_service()
    summary.ingest_records([_rec("s1", 10)])
    out = summary.get_billing_summary(workspace_id=WS)
    assert out.total_spend_verified is not None and out.currency == "USD"
    assert [r["currency"] for r in out.spend_by_currency] == ["USD"]


def test_currency_analytics_withholds_costs_when_currencies_mix() -> None:
    analytics = _analytics(_two_currency_service())
    rows = analytics._billing_rows("all")
    assert len(rows) == 2
    assert all(r.effective_cost is None and r.currency is None for r in rows)
    assert all(r.match_status == MatchStatus.MIXED_CURRENCY for r in rows)
    assert all(r.usage_quantity == 10 for r in rows)
    assert analytics._sum_cost(rows) == 0.0
    assert "withheld" in (analytics._billing_provenance(rows).message or "")


def test_currency_analytics_leaves_single_currency_rows_alone() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec("o1", 10)])
    rows = _analytics(svc)._billing_rows("all")
    assert rows[0].effective_cost is not None and rows[0].currency == "USD"


# ============================================================ C1 statement completeness


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sql_client_module.time, "sleep", lambda _s: None)


def _running_service(api: Any) -> DatabricksSqlService:
    client = _FakeClient("RUNNING")
    client.statement_execution = api
    return _sql(client)


def _run_sql(svc: DatabricksSqlService, sql: str | None = None) -> list[dict[str, Any]]:
    q = sql or build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    return svc.execute_read_only_statement(
        q,
        is_approved=True,
        approval_token=_token(svc, q),
        date_start="2026-11-01" if not sql else None,
        date_end="2026-11-10" if not sql else None,
    )


def _api(first: Any, **extra: Any) -> SimpleNamespace:
    return SimpleNamespace(execute_statement=lambda **_: first, **extra)


def test_c1_complete_single_chunk_returns_all_rows() -> None:
    rows = [["r1", WS, "S", "DBU", "1"], ["r2", WS, "S", "DBU", "2"]]
    got = _run_sql(_running_service(_api(_statement_response(COLS, rows))))
    assert [r["record_id"] for r in got] == ["r1", "r2"]


def test_c1_pending_statement_is_polled_until_success() -> None:
    polls: list[str] = []
    done = _statement_response(COLS, [["r1", WS, "S", "DBU", "1"]])

    def get_statement(statement_id: str) -> Any:
        polls.append(statement_id)
        return done if len(polls) >= 2 else _statement_response(COLS, [], state="RUNNING")

    api = _api(_statement_response(COLS, [], state="PENDING"), get_statement=get_statement)
    assert len(_run_sql(_running_service(api))) == 1
    assert len(polls) == 2


def test_c1_statement_that_never_finishes_times_out_cancels_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled: list[str] = []
    clock = iter(range(0, 10_000, 20))
    monkeypatch.setattr(sql_client_module.time, "monotonic", lambda: float(next(clock)))
    api = _api(
        _statement_response(COLS, [], state="RUNNING"),
        get_statement=lambda _id: _statement_response(COLS, [], state="RUNNING"),
        cancel_execution=cancelled.append,
    )
    with pytest.raises(StatementIncompleteError) as err:
        _run_sql(_running_service(api))
    assert err.value.code == "STATEMENT_TIMEOUT"
    assert cancelled == ["stmt-1"]


@pytest.mark.parametrize("state", ["FAILED", "CANCELED", "CLOSED"])
def test_c1_failed_statement_raises_and_never_returns_rows(state: str) -> None:
    with pytest.raises(StatementIncompleteError) as err:
        _run_sql(_running_service(_api(_statement_response(COLS, [], state=state))))
    assert err.value.code == "STATEMENT_FAILED" and state in str(err.value)


def test_c1_truncated_result_raises() -> None:
    rows = [["r1", WS, "S", "DBU", "1"]]
    with pytest.raises(StatementIncompleteError) as err:
        _run_sql(_running_service(_api(_statement_response(COLS, rows, truncated=True))))
    assert err.value.code == "RESULT_TRUNCATED"


def test_c1_additional_chunks_are_followed_in_order() -> None:
    chunk0 = _statement_response(
        COLS, [["r1", WS, "S", "DBU", "1"]], total_rows=3, next_chunk=1, total_chunks=3
    )
    chunks = {
        1: SimpleNamespace(
            data_array=[["r2", WS, "S", "DBU", "2"]], next_chunk_index=2, external_links=None
        ),
        2: SimpleNamespace(
            data_array=[["r3", WS, "S", "DBU", "3"]], next_chunk_index=None, external_links=None
        ),
    }
    seen: list[int] = []

    def get_chunk(_sid: str, idx: int) -> Any:
        seen.append(idx)
        return chunks[idx]

    got = _run_sql(_running_service(_api(chunk0, get_statement_result_chunk_n=get_chunk)))
    assert [r["record_id"] for r in got] == ["r1", "r2", "r3"] and seen == [1, 2]


def test_c1_row_count_mismatch_with_manifest_raises() -> None:
    rows = [["r1", WS, "S", "DBU", "1"]]
    with pytest.raises(StatementIncompleteError) as err:
        _run_sql(_running_service(_api(_statement_response(COLS, rows, total_rows=5))))
    assert err.value.code == "RESULT_INCOMPLETE"


def test_c1_missing_chunks_raise() -> None:
    first = _statement_response(COLS, [["r1", WS, "S", "DBU", "1"]], total_rows=1, total_chunks=2)
    with pytest.raises(StatementIncompleteError):
        _run_sql(_running_service(_api(first)))


def test_c1_missing_manifest_cannot_be_verified() -> None:
    resp = _statement_response(COLS, [["r1", WS, "S", "DBU", "1"]])
    resp.manifest = None
    with pytest.raises(StatementIncompleteError):
        _run_sql(_running_service(_api(resp)))


def test_c1_external_links_are_not_silently_dropped() -> None:
    resp = _statement_response(COLS, [])
    resp.result.external_links = [object()]
    with pytest.raises(StatementIncompleteError):
        _run_sql(_running_service(_api(resp)))


def test_c1_sync_wait_is_capped_to_the_api_maximum() -> None:
    captured: dict[str, Any] = {}

    def execute(**kw: Any) -> Any:
        captured.update(kw)
        return _statement_response(COLS, [])

    svc = _running_service(SimpleNamespace(execute_statement=execute))
    svc.settings = svc.settings.model_copy(update={"databricks_query_timeout_seconds": 300})
    _run_sql(svc)
    assert captured["wait_timeout"] == "50s"


def _run_request(approved_token: str, **kw: Any) -> IngestionRunCreateRequest:
    base: dict[str, Any] = {
        "workspace_id": WS,
        "start_date": "2026-11-01",
        "end_date": "2026-11-10",
        "limit": 100,
        "is_approved": True,
        "approval_token": approved_token,
    }
    base.update(kw)
    return IngestionRunCreateRequest(**base)


def test_c1_run_reports_failed_with_code_and_ingests_nothing() -> None:
    svc = _running_service(
        _api(_statement_response(COLS, [["r1", WS, "S", "DBU", "1"]], truncated=True))
    )
    billing = BillingIngestionService(sql_service=svc)
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    res = billing.run_ingestion(_run_request(_token(svc, q)))
    assert res.status == "failed" and res.error_code == "RESULT_TRUNCATED"
    assert res.result_complete is False and billing._usage_store == {}


def test_c1_run_reaching_its_row_bound_is_incomplete_not_completed() -> None:
    cols = [
        "record_id",
        "workspace_id",
        "sku_name",
        "usage_start_time",
        "usage_end_time",
        "usage_date",
        "usage_unit",
        "usage_quantity",
    ]
    rows = [
        [f"r{i}", WS, "S", "2026-11-01T00:00:00Z", "2026-11-01T01:00:00Z", "2026-11-01", "DBU", "1"]
        for i in range(3)
    ]
    svc = _running_service(_api(_statement_response(cols, rows)))
    billing = BillingIngestionService(sql_service=svc)
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 3)
    res = billing.run_ingestion(_run_request(_token(svc, q), limit=3))
    assert res.status == "incomplete" and res.error_code == "ROW_LIMIT_REACHED"
    assert res.result_complete is False and res.inserted_count == 3
    assert "partial" in (res.error_message or "")


def test_c1_run_below_its_row_bound_is_completed_and_complete() -> None:
    cols = [
        "record_id",
        "workspace_id",
        "sku_name",
        "usage_start_time",
        "usage_end_time",
        "usage_date",
        "usage_unit",
        "usage_quantity",
    ]
    rows = [
        ["r1", WS, "S", "2026-11-01T00:00:00Z", "2026-11-01T01:00:00Z", "2026-11-01", "DBU", "1"]
    ]
    svc = _running_service(_api(_statement_response(cols, rows)))
    billing = BillingIngestionService(sql_service=svc)
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    res = billing.run_ingestion(_run_request(_token(svc, q)))
    assert res.status == "completed" and res.result_complete is True and res.error_code is None


# ============================================================ C2 rate card completeness


def test_c2_price_query_uses_its_own_bound_not_the_usage_limit() -> None:
    billing = BillingIngestionService(sql_service=_sql())
    request = IngestionRunCreateRequest(
        workspace_id=WS,
        start_date="2026-11-01",
        end_date="2026-11-10",
        limit=10,
        source_table="system.billing.list_prices",
    )
    sql, table = billing._build_statement(request)
    assert table == "system.billing.list_prices"
    assert sql == build_list_prices_query(limit=PRICE_ROW_LIMIT)
    assert statement_row_limit(sql) == PRICE_ROW_LIMIT


PRICE_COLS = ["sku_name", "cloud", "currency_code", "usage_unit", "price_start_time", "pricing"]


def _price_row(i: int) -> list[Any]:
    return [f"SKU_{i}", "AZURE", "USD", "DBU", "2026-01-01T00:00:00Z", '{"default": "1.5"}']


def _price_run(rows: list[list[Any]], **resp: Any) -> tuple[BillingIngestionService, Any]:
    svc = _running_service(_api(_statement_response(PRICE_COLS, rows, **resp)))
    billing = BillingIngestionService(sql_service=svc)
    q = build_list_prices_query(limit=PRICE_ROW_LIMIT)
    tok = svc.issue_approval_token(
        query=q, warehouse_id=WH, approver_roles=["Admin"], max_rows=PRICE_ROW_LIMIT
    )
    request = _run_request(tok, source_table="system.billing.list_prices")
    return billing, billing.run_ingestion(request)


def test_c2_complete_rate_card_is_marked_complete() -> None:
    billing, res = _price_run([_price_row(i) for i in range(5)])
    assert res.status == "completed" and res.result_complete is True
    assert billing.get_billing_summary(workspace_id=WS).price_card_complete is True
    assert len(billing.list_price_records()) == 5


def test_c2_rate_card_at_its_bound_is_incomplete_and_flagged_on_the_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloud_recommender.services.databricks import billing_ingestion_service as bis

    monkeypatch.setattr(bis, "PRICE_ROW_LIMIT", 3)
    svc = _running_service(_api(_statement_response(PRICE_COLS, [_price_row(i) for i in range(3)])))
    billing = BillingIngestionService(sql_service=svc)
    q = bis.build_list_prices_query(limit=3)
    tok = svc.issue_approval_token(query=q, warehouse_id=WH, approver_roles=["Admin"], max_rows=3)
    res = billing.run_ingestion(_run_request(tok, source_table="system.billing.list_prices"))
    assert res.status == "incomplete" and res.error_code == "ROW_LIMIT_REACHED"
    billing.ingest_records([_rec("p1", 1, sku_name="SKU_0")])
    assert billing.get_billing_summary(workspace_id=WS).price_card_complete is False


def test_c2_truncated_rate_card_run_fails_and_marks_the_card_incomplete() -> None:
    billing, res = _price_run([_price_row(0)], truncated=True)
    assert res.status == "failed" and res.error_code == "RESULT_TRUNCATED"
    assert billing._price_card_complete is False and billing.list_price_records() == []


# ============================================================ signed token scope


def test_token_row_limit_above_signed_max_rows_is_refused() -> None:
    svc = _sql()
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 5000)
    tok = svc.issue_approval_token(
        query=q,
        warehouse_id=WH,
        approver_roles=["Admin"],
        max_rows=100,
        start_date="2026-11-01",
        end_date="2026-11-10",
    )
    assert not svc.verify_approval_token(
        tok,
        q,
        WH,
        max_rows=5000,
        date_start="2026-11-01",
        date_end="2026-11-10",
        enforce_scope=True,
    )
    assert svc.verify_approval_token(
        tok, q, WH, max_rows=100, date_start="2026-11-01", date_end="2026-11-10", enforce_scope=True
    )


def test_token_unbounded_statement_is_refused_at_execution() -> None:
    client = _FakeClient("RUNNING")
    svc = _sql(client)
    q = "SELECT record_id FROM system.billing.usage"
    tok = svc.issue_approval_token(query=q, warehouse_id=WH, approver_roles=["Admin"])
    with pytest.raises(ApprovalRequiredError):
        svc.execute_read_only_statement(q, is_approved=True, approval_token=tok)
    assert client.executed == []


@pytest.mark.parametrize(
    ("start", "end"),
    [("2026-11-02", "2026-11-10"), ("2026-11-01", "2026-11-11"), (None, None)],
)
def test_token_date_window_must_match_exactly(start: str | None, end: str | None) -> None:
    client = _FakeClient("RUNNING")
    svc = _sql(client)
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = _token(svc, q)
    with pytest.raises(ApprovalRequiredError):
        svc.execute_read_only_statement(
            q, is_approved=True, approval_token=tok, date_start=start, date_end=end
        )
    assert client.executed == [] and tok not in svc._consumed_tokens


def test_token_is_bound_to_the_exact_sql_text() -> None:
    client = _FakeClient("RUNNING")
    svc = _sql(client)
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = _token(svc, q)
    altered = q.replace("LIMIT 100", "LIMIT 99")
    with pytest.raises(ApprovalRequiredError):
        svc.execute_read_only_statement(
            altered,
            is_approved=True,
            approval_token=tok,
            date_start="2026-11-01",
            date_end="2026-11-10",
        )
    assert client.executed == []


def test_token_expired_is_refused() -> None:
    svc = _sql()
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = svc.issue_approval_token(
        query=q,
        warehouse_id=WH,
        approver_roles=["Admin"],
        ttl_seconds=-5,
        max_rows=100,
        start_date="2026-11-01",
        end_date="2026-11-10",
    )
    assert not svc.verify_approval_token(
        tok, q, WH, max_rows=100, date_start="2026-11-01", date_end="2026-11-10", enforce_scope=True
    )


def test_token_legacy_format_is_not_accepted_for_live_execution() -> None:
    svc = _sql()
    svc.auth_type = "azure-cli"
    svc.settings = svc.settings.model_copy(update={"app_env": "development"})
    import hashlib
    import hmac
    import time

    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    qhash = hashlib.sha256(q.strip().encode()).hexdigest()
    payload = f"{WH}:{qhash}:{int(time.time()) + 300}"
    secret = next(iter(svc._get_signing_keys().values()))
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
    legacy = f"{payload}:{sig}"
    assert svc.verify_approval_token(legacy, q, WH) is True  # still verifiable in general
    assert not svc.verify_approval_token(
        legacy,
        q,
        WH,
        max_rows=100,
        date_start="2026-11-01",
        date_end="2026-11-10",
        enforce_scope=True,
    )


def test_token_single_use_exactly_one_winner_under_thread_contention() -> None:
    svc = _sql()
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = _token(svc, q)
    barrier = threading.Barrier(16)
    results: list[bool] = []

    def worker() -> None:
        barrier.wait()
        results.append(svc.consume_approval_token(tok))

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1 and results.count(False) == 15


def test_token_not_burnt_in_memory_when_the_ledger_is_down() -> None:
    from cloud_recommender.services.databricks.sql_client import LedgerHandle

    svc = _sql()
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = _token(svc, q)

    class _Down:
        async def run_sync(self, _fn: Any) -> Any:
            raise RuntimeError("database unavailable")

    import asyncio

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        handle = LedgerHandle(session=_Down(), loop=loop)  # type: ignore[arg-type]
        assert svc.consume_approval_token(tok, session=handle) is False
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=3)
    assert tok not in svc._consumed_tokens  # a token that never ran is not spent
    assert svc.consume_approval_token(tok) is True  # still usable once the ledger is back


# ============================================================ P1: no unguarded Azure simulation


def _azure_cfg(token: str | None, *, demo: bool, **azure_attrs: Any) -> Any:
    from unittest.mock import AsyncMock

    from cloud_recommender.core.config import Settings
    from cloud_recommender.services.configuration.configuration_service import (
        ConfigurationService,
    )
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService

    azure = AsyncMock(spec=AzureInventoryService)
    azure.get_access_token.return_value = (token, "none" if token is None else "azure_cli_session")
    for name, value in azure_attrs.items():
        getattr(azure, name).side_effect = value
    return ConfigurationService(azure_service=azure, settings=Settings(allow_demo_fixtures=demo))


async def test_p1_no_token_without_demo_flag_returns_authentication_required() -> None:
    out = await _azure_cfg(None, demo=False).discover_scopes("c1", provider="azure")
    assert out.status == "authentication_required" and out.data_source == "none"
    assert out.tree == [] and out.total_discovered_resources == 0
    assert out.databricks_workspaces_count == 0 and out.tenant_or_org_id is None
    assert "az login" in out.status_message


async def test_p1_default_settings_disable_demo_fixtures() -> None:
    from cloud_recommender.core.config import Settings

    # the environment of this suite opts in; the declared default must still be off
    assert Settings.model_fields["allow_demo_fixtures"].default is False


async def test_p1_demo_fixture_is_opt_in_and_labelled() -> None:
    out = await _azure_cfg(None, demo=True).discover_scopes("c1", provider="azure")
    assert out.status == "ready" and out.data_source == "demo_fixture"
    assert "DEMO FIXTURE" in out.status_message and out.tree


def test_p1_fixture_identifiers_live_only_in_the_isolated_demo_module() -> None:
    cfg = SRC / "services/configuration"
    service_text = (cfg / "configuration_service.py").read_text(encoding="utf-8")
    for fabricated in ("f718c261", "fe82a67c", "rg-analytics-databricks", "adb-lakehouse-prod"):
        assert fabricated not in service_text
        assert fabricated in (cfg / "demo_fixtures.py").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PermissionError("Reader role missing"), "permission_denied"),
        (RuntimeError("boom"), "error"),
    ],
)
async def test_p1_live_failures_are_classified_not_all_called_permission_denied(
    error: Exception, expected: str
) -> None:
    out = await _azure_cfg("tok", demo=False, list_subscriptions=error).discover_scopes(
        "c1", provider="azure"
    )
    assert out.status == expected and out.tree == []


@pytest.mark.parametrize(
    ("code", "expected"), [(401, "authentication_required"), (403, "permission_denied")]
)
async def test_p1_http_401_is_authentication_and_403_is_authorisation(
    code: int, expected: str
) -> None:
    exc = RuntimeError("arm failure")
    exc.response = SimpleNamespace(status_code=code)  # type: ignore[attr-defined]
    out = await _azure_cfg("tok", demo=False, list_subscriptions=exc).discover_scopes(
        "c1", provider="azure"
    )
    assert out.status == expected


async def test_p1_authenticated_discovery_is_unchanged() -> None:
    from unittest.mock import AsyncMock

    from cloud_recommender.core.config import Settings
    from cloud_recommender.schemas.inventory import CloudProvider, CloudScopeSummary
    from cloud_recommender.services.configuration.configuration_service import (
        ConfigurationService,
    )
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService

    azure = AsyncMock(spec=AzureInventoryService)
    azure.get_access_token.return_value = ("tok", "azure_cli_session")
    azure.list_subscriptions.return_value = [
        CloudScopeSummary(
            provider=CloudProvider.AZURE,
            scope_id="sub-live",
            display_name="Live Sub",
            tenant_or_org_id="tenant-live",
            parent_scope_id=None,
            state="Enabled",
            data_source="live_authenticated",
        )
    ]
    azure.list_resource_groups.return_value = [
        {"name": "rg-a", "id": "/subscriptions/sub-live/resourceGroups/rg-a", "location": "eastus"}
    ]
    azure.list_databricks_workspaces.return_value = []
    azure.list_resources.return_value = []
    cfg = ConfigurationService(azure_service=azure, settings=Settings(allow_demo_fixtures=False))
    out = await cfg.discover_scopes("c1", provider="azure")
    assert out.status == "ready" and out.data_source == "live"
    assert out.tree[0].name == "Live Sub" and out.tree[0].children[0].name == "rg-a"
    assert out.tenant_or_org_id == "tenant-live"


# ============================================================ migration 0004 (static, offline)

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic/versions/2026_11_13_0004_billing_precision_and_row_identity.py"


def test_migration_0004_has_no_fabricated_values_or_placeholder_hashes() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "md5(record_id)" not in text
    assert "price_effective_list, price_default, 0" not in text
    assert "COALESCE(account_id" in text  # NULL-safe price identity
    assert '_require_empty("billing_usage_records", direction="upgrade")' in text
    assert text.count('direction="downgrade"') == 2


def test_migration_0004_renders_offline_without_a_connection() -> None:
    import io
    from contextlib import redirect_stdout

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", "postgresql+asyncpg://nobody@invalid.invalid/none_test")
    buf = io.StringIO()
    with redirect_stdout(buf):
        command.upgrade(cfg, "2026_11_07_0003:2026_11_13_0004", sql=True)
    sql = buf.getvalue()
    assert "CREATE UNIQUE INDEX uq_billing_price_identity" in sql
    assert "COALESCE(account_id, '')" in sql
    assert "billing_ingestion_runs ADD COLUMN error_count" in sql
    assert "md5(" not in sql


def test_migration_0004_matches_the_orm_for_run_and_price_identity() -> None:
    from sqlalchemy import inspect

    from cloud_recommender.db.models import BillingIngestionRunModel, BillingPriceRecordModel

    run_cols = {c.name for c in inspect(BillingIngestionRunModel).columns}
    assert {"error_count", "shared_record_id_count", "result_complete", "error_code"} <= run_cols
    index_names = {i.name for i in BillingPriceRecordModel.__table__.indexes}
    assert "uq_billing_price_identity" in index_names
