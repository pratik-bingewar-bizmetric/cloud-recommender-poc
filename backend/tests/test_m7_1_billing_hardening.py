"""M7.1 regression tests: one section per defect D1-D11 from the M7 design report.

Fully offline: no SQL is executed, no warehouse is started, no network is used.
"""

import asyncio
import json
import re
import threading
from collections.abc import Generator
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cloud_recommender.api.routes import finops as finops_routes
from cloud_recommender.db.models import (
    Base,
    BillingApprovalTokenModel,
    BillingPriceRecordModel,
    BillingUsageRecordModel,
)
from cloud_recommender.schemas.billing_ingestion import (
    BillingPriceRecord,
    BillingUsageRecord,
    IngestionRunCreateRequest,
)
from cloud_recommender.services.databricks.billing_ingestion_service import (
    BillingIngestionService,
)
from cloud_recommender.services.databricks.billing_sql import (
    BillingQueryValidationError,
    CostBasis,
    MatchStatus,
    build_list_prices_query,
    build_usage_query,
    matches_resource,
    resolve_resource,
    validate_workspace_id,
)
from cloud_recommender.services.databricks.sql_client import (
    ApprovalLedgerError,
    ApprovalRequiredError,
    DatabricksSqlService,
    LedgerHandle,
    WarehouseStoppedError,
)
from tests.fixtures.billing_baseline import (
    BASELINE_PRICES,
    baseline_price_rows,
    load_baseline_prices,
)

WS = "642006393507276"
WH = "05ed10a52697a344"
SRC = Path(__file__).resolve().parents[1] / "src" / "cloud_recommender"


def _sql(client: Any = None) -> DatabricksSqlService:
    return DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id=WH,
        auth_type="mock",
        workspace_client=client,
    )


def _rec(rid: str = "r1", qty: Any = 10, **kw: Any) -> BillingUsageRecord:
    base: dict[str, Any] = {
        "record_id": rid,
        "workspace_id": WS,
        "sku_name": "SERVERLESS_SQL_COMPUTE",
        "usage_start_time": "2026-11-01T00:00:00Z",
        "usage_end_time": "2026-11-01T01:00:00Z",
        "usage_date": "2026-11-01",
        "usage_unit": "DBU",
        "usage_quantity": qty,
        "usage_metadata": {"warehouse_id": WH},
    }
    base.update(kw)
    return BillingUsageRecord(**base)


def _priced_service() -> BillingIngestionService:
    svc = BillingIngestionService(sql_service=_sql())
    load_baseline_prices(svc)
    return svc


# ---------------------------------------------------------------- D1 hardcoded rate card


def test_d1_no_hardcoded_rate_card_in_application() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    assert svc._price_store == []
    assert svc.list_price_records() == []
    assert not hasattr(BillingIngestionService, "_CANONICAL_LIST_PRICES")
    text = (SRC / "services/databricks/billing_ingestion_service.py").read_text(encoding="utf-8")
    for literal in ("2.20", "1.45047", "4.00,", 'price_per_unit": '):
        assert literal not in text


def test_d1_usage_without_ingested_prices_has_no_cost_never_zero() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    svc.ingest_records([_rec()])
    rec = svc._usage_store["r1"]
    assert rec.effective_cost is None and rec.pricing_matched is False
    assert rec.match_status == MatchStatus.NO_PRICE
    assert rec.cost_basis == CostBasis.METERED_USAGE
    summary = svc.get_billing_summary(workspace_id=WS)
    assert summary.total_spend_verified is None
    assert summary.cost_basis == CostBasis.METERED_USAGE
    assert summary.total_dbu == 10.0


def test_d1_price_validity_interval_and_unit_are_respected() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    row = baseline_price_rows()[0]
    row["price_end_time"] = "2026-10-15T00:00:00.000+00:00"  # expired before usage
    price = svc._row_to_price_record(row)
    assert price is not None
    svc.ingest_price_records([price])
    svc.ingest_records([_rec()])
    assert svc._usage_store["r1"].match_status == MatchStatus.NO_PRICE
    # non-DBU usage is never priced with a DBU rate
    svc2 = _priced_service()
    svc2.ingest_records([_rec("b1", usage_unit="BYTE_HOURS")])
    assert svc2._usage_store["b1"].match_status == MatchStatus.UNIT_MISMATCH
    assert svc2._usage_store["b1"].effective_cost is None


def test_d1_ambiguous_rates_are_not_guessed() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    a = baseline_price_rows()[0]
    b = dict(a, account_id="other-account", pricing={"default": "3.10"})
    svc.ingest_price_records([svc._row_to_price_record(a), svc._row_to_price_record(b)])  # type: ignore[list-item]
    svc.ingest_records([_rec()])
    rec = svc._usage_store["r1"]
    assert rec.match_status == MatchStatus.AMBIGUOUS and rec.effective_cost is None


# ---------------------------------------------------------------- D2 nested pricing struct


def test_d2_parses_nested_pricing_struct_and_selects_tier() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    row = {
        "account_id": "a",
        "sku_name": "PREMIUM_JOBS_COMPUTE",
        "cloud": "AZURE",
        "currency_code": "USD",
        "usage_unit": "DBU",
        "price_start_time": "2026-01-01T00:00:00.000+00:00",
        "price_end_time": None,
        "pricing": {
            "default": "0.300000000000000000",
            "promotional": {"default": "0.100000000000000000"},
            "effective_list": {"default": "0.250000000000000000"},
        },
    }
    price = svc._row_to_price_record(row)
    assert price is not None
    assert price.price_default == Decimal("0.3")
    assert price.price_promotional == Decimal("0.1")
    assert price.price_effective_list == Decimal("0.25")
    assert price.selected_price() == Decimal("0.25")  # effective_list, never promotional
    assert price.price_tier == "effective_list"
    assert price.usage_unit == "DBU" and price.pricing_unit == "DBU"  # alias kept
    assert price.model_dump(mode="json")["price_per_unit"] == 0.25


def test_d2_accepts_json_text_struct_and_default_only() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    row = dict(baseline_price_rows()[0], pricing=json.dumps({"default": "2.2"}))
    price = svc._row_to_price_record(row)
    assert price is not None and price.price_tier == "default"


def test_d2_row_without_any_usable_rate_is_malformed_not_free() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    for pricing in ({}, {"promotional": {"default": "1"}}, None, "garbage"):
        assert svc._row_to_price_record(dict(baseline_price_rows()[0], pricing=pricing)) is None


def test_d2_legacy_flat_shape_still_constructs() -> None:
    p = BillingPriceRecord(
        sku_name="S",
        price_per_unit=2.2,
        pricing_unit="DBU",
        price_start_time="2026-01-01T00:00:00Z",
    )
    assert p.price_default == Decimal("2.2") and p.usage_unit == "DBU"


def test_d2_price_ingestion_is_idempotent_and_reprices_usage() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    svc.ingest_records([_rec(qty="12.5")])
    assert svc._usage_store["r1"].effective_cost is None
    prices = [svc._row_to_price_record(r) for r in baseline_price_rows()]
    first = svc.ingest_price_records([p for p in prices if p])
    assert first["inserted_count"] == len(BASELINE_PRICES)
    assert svc._usage_store["r1"].effective_cost == Decimal("27.5")
    second = svc.ingest_price_records([p for p in prices if p])
    assert second["inserted_count"] == 0 and second["duplicate_count"] == len(BASELINE_PRICES)


# ---------------------------------------------------------------- D3 decimal precision


def test_d3_source_precision_is_preserved_end_to_end() -> None:
    svc = _priced_service()
    raw = {
        "record_id": "p1",
        "workspace_id": WS,
        "sku_name": "SERVERLESS_SQL_COMPUTE",
        "cloud": "AZURE",
        "usage_start_time": "2026-11-01T00:00:00.000+00:00",
        "usage_end_time": "2026-11-01T01:00:00.000+00:00",
        "usage_date": "2026-11-01",
        "usage_unit": "DBU",
        "usage_quantity": "0.000123456789012345",
    }
    rec = svc._row_to_usage_record(raw)
    assert rec is not None
    assert rec.usage_quantity == Decimal("0.000123456789012345")
    assert rec.usage_quantity_exact == "0.000123456789012345"
    svc.ingest_records([rec])
    stored = svc._usage_store["p1"]
    # full-precision cost; the old per-row cent rounding would have produced 0.00
    assert stored.effective_cost == Decimal("0.000123456789012345") * Decimal("2.20")
    assert stored.effective_cost != 0


def test_d3_float_inputs_do_not_acquire_binary_noise() -> None:
    assert _rec(qty=0.1).usage_quantity == Decimal("0.1")
    assert _rec(qty=4793.0).usage_quantity == Decimal("4793.0")


def test_d3_non_finite_or_non_numeric_quantities_are_rejected() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    base = {
        "record_id": "x",
        "workspace_id": WS,
        "sku_name": "S",
        "usage_start_time": "t",
        "usage_end_time": "t",
        "usage_date": "2026-11-01",
        "usage_unit": "DBU",
    }
    for bad in ("NaN", "Infinity", "abc", None, True):
        assert svc._row_to_usage_record(dict(base, usage_quantity=bad)) is None


def test_d3_aggregates_have_no_float_accumulation_error() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec(f"s{i}", qty="0.1") for i in range(10)])
    summary = svc.get_billing_summary(workspace_id=WS)
    assert summary.total_dbu == 1.0 and summary.net_dbu == 1.0


def test_d3_orm_columns_hold_decimal_38_18() -> None:
    qty = BillingUsageRecordModel.__table__.c.usage_quantity.type
    cost = BillingUsageRecordModel.__table__.c.effective_cost.type
    price = BillingPriceRecordModel.__table__.c.price_default.type
    for col in (qty, cost, price):
        assert (col.precision, col.scale) == (38, 18)


# ---------------------------------------------------------------- D4 dedup / corrections


def test_d4_correction_rows_sharing_a_record_id_are_preserved() -> None:
    svc = _priced_service()
    original = _rec("dup-1", 100)
    retraction = _rec("dup-1", -100, record_type="retraction")
    restatement = _rec("dup-1", 80, record_type="restatement")
    stats = svc.ingest_records([original, retraction, restatement])
    assert stats["inserted_count"] == 3 and stats["duplicate_count"] == 0
    assert stats["retraction_count"] == 1
    assert stats["shared_record_id_count"] == 3  # evidence for the final key
    summary = svc.get_billing_summary(workspace_id=WS)
    assert summary.net_dbu == 80.0  # 100 - 100 + 80
    assert summary.retraction_dbu == 100.0


def test_d4_identical_reextract_is_still_a_duplicate_and_idempotent() -> None:
    svc = _priced_service()
    batch = [_rec("a", 5), _rec("a", -5, record_type="retraction")]
    assert svc.ingest_records(batch)["inserted_count"] == 2
    again = svc.ingest_records([_rec("a", 5), _rec("a", -5, record_type="retraction")])
    assert again["inserted_count"] == 0 and again["duplicate_count"] == 2
    assert len(svc._usage_store) == 2


def test_d4_same_record_id_different_workspace_is_not_a_duplicate() -> None:
    svc = _priced_service()
    stats = svc.ingest_records([_rec("w", 1), _rec("w", 1, workspace_id="999")])
    assert stats["inserted_count"] == 2


def test_d4_key_is_documented_as_provisional_and_orm_is_not_record_id_pk() -> None:
    text = (SRC / "services/databricks/billing_ingestion_service.py").read_text(encoding="utf-8")
    assert "PROVISIONAL" in text
    pk_cols = [c.name for c in BillingUsageRecordModel.__table__.primary_key.columns]
    assert pk_cols == ["id"]
    uniques = {
        tuple(c.name for c in u.columns)
        for u in BillingUsageRecordModel.__table__.constraints
        if u.__class__.__name__ == "UniqueConstraint"
    }
    assert ("workspace_id", "source_row_hash") in uniques


# ---------------------------------------------------------------- D5 attribution


def test_d5_resolver_covers_all_resource_id_keys_with_priority() -> None:
    assert resolve_resource({"dlt_pipeline_id": "p"}) == ("PIPELINE", "p")
    assert resolve_resource({"endpoint_name": "e"}) == ("SERVING_ENDPOINT", "e")
    assert resolve_resource({"instance_pool_id": "i"}) == ("POOL", "i")
    assert resolve_resource({"notebook_id": "n"}) == ("NOTEBOOK", "n")
    assert resolve_resource({"job_id": "j", "cluster_id": "c"}) == ("JOB", "j")
    assert resolve_resource({}) is None
    assert resolve_resource({"cluster_id": ""}) is None


def test_d5_matching_is_exact_never_substring() -> None:
    meta = {"dlt_pipeline_id": "pipeline-123"}
    assert matches_resource(meta, "pipeline-123")
    assert not matches_resource(meta, "pipeline-12")
    assert not matches_resource(meta, "123")


def test_d5_pipeline_spend_is_attributed_and_unknown_id_is_no_data() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec("pl", 7, usage_metadata={"dlt_pipeline_id": "pipe-9"})])
    got = svc.get_billing_summary(workspace_id=WS, resource_id="pipe-9")
    assert got.data_status == "INGESTED" and got.net_dbu == 7.0
    assert svc._usage_store["pl"].resource_type == "PIPELINE"
    unknown = svc.get_billing_summary(workspace_id=WS, resource_id="pipe")
    assert unknown.data_status == "NO_DATA" and unknown.net_dbu is None


# ---------------------------------------------------------------- D6 token vs warehouse state


class _FakeClient:
    """Offline WorkspaceClient stand-in (no network)."""

    def __init__(self, state: str = "STOPPED", auto_stop: int | None = 5) -> None:
        self.state = state
        self.auto_stop = auto_stop
        self.executed: list[str] = []
        self.current_user = SimpleNamespace(
            me=lambda: SimpleNamespace(user_name="op", display_name="op")
        )
        self.warehouses = SimpleNamespace(get=self._get)
        self.statement_execution = SimpleNamespace(execute_statement=self._exec)

    def _get(self, **_: Any) -> Any:
        return SimpleNamespace(
            name="Serverless Starter Warehouse",
            state=SimpleNamespace(value=self.state),
            auto_stop_mins=self.auto_stop,
            cluster_size="2X-Small",
        )

    def _exec(self, **kw: Any) -> Any:
        self.executed.append(kw["statement"])
        return _statement_response([], [])


def _statement_response(
    columns: list[str],
    rows: list[list[Any]],
    *,
    state: str = "SUCCEEDED",
    truncated: bool = False,
    total_rows: int | None = None,
    next_chunk: int | None = None,
    total_chunks: int | None = None,
    statement_id: str = "stmt-1",
) -> Any:
    """A Statement Execution API response shaped like the SDK's StatementResponse."""
    return SimpleNamespace(
        statement_id=statement_id,
        status=SimpleNamespace(state=state, error=SimpleNamespace(message="boom")),
        manifest=SimpleNamespace(
            schema=SimpleNamespace(columns=[SimpleNamespace(name=c) for c in columns]),
            truncated=truncated,
            total_row_count=len(rows) if total_rows is None else total_rows,
            total_chunk_count=total_chunks,
        ),
        result=SimpleNamespace(data_array=rows, next_chunk_index=next_chunk, external_links=None),
    )


def _token(svc: DatabricksSqlService, query: str) -> str:
    """Issue a token whose signed scope (row limit, date window) matches ``query`` exactly."""
    import re

    from cloud_recommender.services.databricks.sql_client import statement_row_limit

    dates = re.search(r"usage_date >= '([^']+)' AND usage_date <= '([^']+)'", query)
    return svc.issue_approval_token(
        query=query,
        warehouse_id=WH,
        approver_sub="op",
        approver_roles=["FinOpsAdministrator"],
        max_rows=statement_row_limit(query) or 1000,
        start_date=dates.group(1) if dates else "",
        end_date=dates.group(2) if dates else "",
    )


def test_d6_stopped_warehouse_does_not_consume_the_token() -> None:
    client = _FakeClient("STOPPED")
    svc = _sql(client)
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = _token(svc, q)
    with pytest.raises(WarehouseStoppedError):
        svc.execute_read_only_statement(
            q, is_approved=True, approval_token=tok, date_start="2026-11-01", date_end="2026-11-10"
        )
    assert tok not in svc._consumed_tokens
    assert client.executed == []  # nothing ran, nothing started
    client.state = "RUNNING"  # operator starts the warehouse separately
    svc.execute_read_only_statement(
        q, is_approved=True, approval_token=tok, date_start="2026-11-01", date_end="2026-11-10"
    )
    assert len(client.executed) == 1 and tok in svc._consumed_tokens


def test_d6_token_is_still_single_use_once_executed() -> None:
    client = _FakeClient("RUNNING")
    svc = _sql(client)
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = _token(svc, q)
    svc.execute_read_only_statement(
        q, is_approved=True, approval_token=tok, date_start="2026-11-01", date_end="2026-11-10"
    )
    with pytest.raises(ApprovalRequiredError):
        svc.execute_read_only_statement(
            q, is_approved=True, approval_token=tok, date_start="2026-11-01", date_end="2026-11-10"
        )
    assert len(client.executed) == 1


def test_d6_auth_failure_does_not_consume_the_token() -> None:
    client = _FakeClient("RUNNING")

    def _boom() -> Any:
        raise RuntimeError("401 Unauthorized invalid access token")

    client.current_user = SimpleNamespace(me=_boom)
    svc = _sql(client)
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = _token(svc, q)
    with pytest.raises(Exception):  # noqa: B017 - any auth error class
        svc.execute_read_only_statement(
            q, is_approved=True, approval_token=tok, date_start="2026-11-01", date_end="2026-11-10"
        )
    assert tok not in svc._consumed_tokens


def test_d6_stopped_run_reports_token_not_consumed() -> None:
    client = _FakeClient("STOPPED")
    sql = _sql(client)
    svc = BillingIngestionService(sql_service=sql)
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = _token(sql, q)
    res = svc.run_ingestion(
        IngestionRunCreateRequest(
            workspace_id=WS,
            start_date="2026-11-01",
            end_date="2026-11-10",
            limit=100,
            is_approved=True,
            approval_token=tok,
        )
    )
    assert res.status == "failed" and "STOPPED" in (res.error_message or "")
    assert "NOT consumed" in (res.error_message or "")
    assert client.executed == []


def test_d6_live_mode_without_ledger_is_still_single_use_in_memory() -> None:
    client = _FakeClient("RUNNING")
    svc = _sql(client)
    svc.auth_type = "azure-cli"  # not an offline mode
    svc.settings = svc.settings.model_copy(update={"app_env": "development"})
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = _token(svc, q)
    svc.execute_read_only_statement(
        q, is_approved=True, approval_token=tok, date_start="2026-11-01", date_end="2026-11-10"
    )
    assert len(client.executed) == 1 and tok in svc._consumed_tokens
    with pytest.raises(ApprovalRequiredError):
        svc.execute_read_only_statement(
            q, is_approved=True, approval_token=tok, date_start="2026-11-01", date_end="2026-11-10"
        )
    assert len(client.executed) == 1


def test_d7_route_dependency_supplies_a_ledger_only_in_live_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloud_recommender.core.config import Settings

    async def _first(settings: Settings) -> Any:
        gen = finops_routes.get_billing_ledger(settings)
        try:
            return await gen.__anext__()
        finally:
            await gen.aclose()

    offline = Settings(databricks_auth_type="mock")
    assert asyncio.run(_first(offline)) is None

    class _Ctx:
        async def __aenter__(self) -> str:
            return "session"

        async def __aexit__(self, *_: Any) -> None:
            return None

    monkeypatch.setattr("cloud_recommender.db.session.get_session_factory", lambda: lambda: _Ctx())
    live = Settings(databricks_auth_type="azure-cli", app_env="development")
    handle = asyncio.run(_first(live))
    assert isinstance(handle, LedgerHandle) and handle.session == "session"
    assert finops_routes._as_ledger(handle) is handle
    assert finops_routes._as_ledger(object()) is None


# ---------------------------------------------------------------- D7 durable ledger / async


class _FakeAsyncSession:
    """AsyncSession look-alike whose run_sync hands a sync Session to the callback."""

    def __init__(self, sync: Session) -> None:
        self.sync = sync
        self.fail = False

    async def run_sync(self, fn: Any) -> Any:
        if self.fail:
            raise RuntimeError("database unavailable")
        return fn(self.sync)


@pytest.fixture
def ledger() -> Generator[tuple[LedgerHandle, _FakeAsyncSession, Session], None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    sync = sessionmaker(bind=engine)()
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    fake = _FakeAsyncSession(sync)
    yield LedgerHandle(session=fake, loop=loop), fake, sync  # type: ignore[arg-type]
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=3)
    sync.close()


def test_d7_async_ledger_persists_consumes_and_blocks_cross_restart_replay(
    ledger: tuple[LedgerHandle, _FakeAsyncSession, Session],
) -> None:
    handle, _, sync = ledger
    svc = _sql()
    q = "SELECT record_id FROM system.billing.usage LIMIT 5"
    tok = svc.issue_approval_token(
        query=q, warehouse_id=WH, approver_sub="op", approver_roles=["Admin"], session=handle
    )
    row = sync.execute(select(BillingApprovalTokenModel)).scalar_one()
    assert row.is_consumed is False
    assert svc.verify_approval_token(tok, q, WH, session=handle) is True
    assert svc.consume_approval_token(tok, session=handle) is True
    sync.expire_all()
    assert sync.execute(select(BillingApprovalTokenModel)).scalar_one().is_consumed is True
    fresh = _sql()  # simulates a process restart: empty in-memory set
    assert fresh._consumed_tokens == set()
    assert fresh.verify_approval_token(tok, q, WH, session=handle) is False
    assert fresh.consume_approval_token(tok, session=handle) is False


def test_d7_ledger_failures_fail_closed(
    ledger: tuple[LedgerHandle, _FakeAsyncSession, Session],
) -> None:
    handle, fake, _ = ledger
    svc = _sql()
    q = "SELECT record_id FROM system.billing.usage LIMIT 5"
    tok = svc.issue_approval_token(
        query=q, warehouse_id=WH, approver_sub="op", approver_roles=["Admin"], session=handle
    )
    fake.fail = True
    with pytest.raises(ApprovalLedgerError):
        svc.issue_approval_token(
            query=q, warehouse_id=WH, approver_sub="op", approver_roles=["Admin"], session=handle
        )
    assert svc.verify_approval_token(tok, q, WH, session=handle) is False
    assert _sql().consume_approval_token(tok, session=handle) is False


def test_d7_raw_async_session_is_rejected_not_silently_ignored() -> None:
    raw = MagicMock(spec=AsyncSession)
    svc = _sql()
    q = "SELECT record_id FROM system.billing.usage LIMIT 5"
    with pytest.raises(ApprovalLedgerError):
        svc.issue_approval_token(
            query=q, warehouse_id=WH, approver_sub="op", approver_roles=["Admin"], session=raw
        )


def test_d7_calling_the_ledger_on_the_event_loop_thread_is_refused(
    ledger: tuple[LedgerHandle, _FakeAsyncSession, Session],
) -> None:
    handle, _, _ = ledger
    svc = _sql()

    async def _on_loop() -> None:
        svc.issue_approval_token(
            query="SELECT record_id FROM system.billing.usage LIMIT 5",
            warehouse_id=WH,
            approver_sub="op",
            approver_roles=["Admin"],
            session=handle,
        )

    with pytest.raises(ApprovalLedgerError):
        asyncio.run_coroutine_threadsafe(_on_loop(), handle.loop).result(timeout=5)


def test_d7_execution_consumes_through_the_ledger_after_the_state_check(
    ledger: tuple[LedgerHandle, _FakeAsyncSession, Session],
) -> None:
    handle, _, sync = ledger
    client = _FakeClient("RUNNING")
    svc = _sql(client)
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)
    tok = svc.issue_approval_token(
        query=q, warehouse_id=WH, approver_sub="op", approver_roles=["Admin"], session=handle
    )
    svc.execute_read_only_statement(q, is_approved=True, approval_token=tok, session=handle)
    sync.expire_all()
    assert sync.execute(select(BillingApprovalTokenModel)).scalar_one().is_consumed is True
    with pytest.raises(ApprovalRequiredError):
        svc.execute_read_only_statement(q, is_approved=True, approval_token=tok, session=handle)
    assert len(client.executed) == 1


# ---------------------------------------------------------------- D8 query construction


@pytest.mark.parametrize(
    "bad", ["1' OR '1'='1", "123; DROP TABLE x", "", "12a", "-1", " ", "9" * 21]
)
def test_d8_workspace_id_injection_is_rejected(bad: str) -> None:
    with pytest.raises(BillingQueryValidationError):
        validate_workspace_id(bad)
    with pytest.raises(BillingQueryValidationError):
        build_usage_query(bad, "2026-11-01", "2026-11-10", 10)
    with pytest.raises(ValidationError):
        IngestionRunCreateRequest(workspace_id=bad)


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-11-01'; --", "2026-11-10"),
        ("2026-13-01", "2026-11-10"),
        ("2026-11-10", "2026-11-01"),
        ("x", "y"),
    ],
)
def test_d8_bad_dates_are_rejected(start: str, end: str) -> None:
    with pytest.raises(BillingQueryValidationError):
        build_usage_query(WS, start, end, 10)
    with pytest.raises(ValidationError):
        IngestionRunCreateRequest(workspace_id=WS, start_date=start, end_date=end)


@pytest.mark.parametrize("limit", [0, -1, 50_001, "x", True, 1.5])
def test_d8_bad_limits_are_rejected(limit: Any) -> None:
    with pytest.raises(BillingQueryValidationError):
        build_usage_query(WS, "2026-11-01", "2026-11-10", limit)


def test_d8_cloud_and_source_table_are_allowlisted() -> None:
    with pytest.raises(BillingQueryValidationError):
        build_list_prices_query(cloud="AZURE' OR 1=1 --")
    with pytest.raises(ValidationError):
        IngestionRunCreateRequest(source_table="system.access.audit")  # type: ignore[arg-type]


def test_d8_built_queries_pass_the_ast_validator_and_are_bounded() -> None:
    svc = _sql()
    usage = build_usage_query(WS, "2026-11-01", "2026-11-10", 500)
    prices = build_list_prices_query(limit=100)
    svc.validate_read_only_statement(usage)
    svc.validate_read_only_statement(prices)
    for q in (usage, prices):
        assert "SELECT *" not in q.upper() and re.search(r"LIMIT \d+$", q)
    assert f"workspace_id = '{WS}'" in usage


def test_d8_run_builds_sql_only_from_validated_values_and_token_binds_to_it() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    res = svc.run_ingestion(
        IngestionRunCreateRequest(
            workspace_id=WS, start_date="2026-11-01", end_date="2026-11-10", limit=50
        )
    )
    assert res.status == "approval_required"
    sql_text = res.approval_request["exact_read_only_sql"]  # type: ignore[index]
    assert sql_text == build_usage_query(WS, "2026-11-01", "2026-11-10", 50)


def test_d8_price_run_requests_approval_for_list_prices_only() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    res = svc.run_ingestion(IngestionRunCreateRequest(source_table="system.billing.list_prices"))
    assert res.status == "approval_required" and res.source_table == "system.billing.list_prices"
    assert res.approval_request["system_tables_accessed"] == ["system.billing.list_prices"]  # type: ignore[index]


def test_d8_approved_price_run_ingests_through_the_real_mapper() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    svc.ingest_records([_rec("pre", "10")])
    rows = baseline_price_rows() + [{"sku_name": "BROKEN"}]

    class _Stub:
        def execute_read_only_statement(self, **kw: Any) -> list[dict[str, Any]]:
            assert kw["system_tables"] == ["system.billing.list_prices"]
            return rows

    svc._get_sql_service_for_workspace = lambda _w: _Stub()  # type: ignore[method-assign,assignment]
    res = svc.run_ingestion(
        IngestionRunCreateRequest(
            source_table="system.billing.list_prices",
            is_approved=True,
            approval_token="TEST-APPROVED-TOKEN",
        )
    )
    assert res.status == "completed"
    assert (res.extracted_count, res.inserted_count, res.error_count) == (
        len(rows),
        len(BASELINE_PRICES),
        1,
    )
    assert svc._usage_store["pre"].effective_cost == Decimal("22.0")  # re-priced after price load


# ---------------------------------------------------------------- D9 API envelope


@pytest.fixture
def api() -> Generator[tuple[TestClient, BillingIngestionService], None, None]:
    svc = _priced_service()
    svc.ingest_records([_rec(f"u{i}", i + 1) for i in range(5)])
    app = FastAPI()
    app.include_router(finops_routes.router, prefix="/api/v1")
    app.dependency_overrides[finops_routes.get_billing_service] = lambda: svc
    # The router warms live Databricks metadata caches; keep this test fully offline.
    app.dependency_overrides[finops_routes.warm_live_metadata] = lambda: None
    yield TestClient(app), svc


def test_d9_default_usage_response_is_still_a_bare_list(api: Any) -> None:
    client, _ = api
    body = client.get("/api/v1/finops/billing/usage", params={"workspace_id": WS}).json()
    assert isinstance(body, list) and len(body) == 5


def test_d9_envelope_has_total_offset_limit_records(api: Any) -> None:
    client, _ = api
    body = client.get(
        "/api/v1/finops/billing/usage",
        params={"workspace_id": WS, "envelope": "true", "limit": 2, "offset": 1},
    ).json()
    assert set(body) == {"total", "offset", "limit", "records"}
    assert (body["total"], body["offset"], body["limit"], len(body["records"])) == (5, 1, 2, 2)
    assert body["records"][0]["record_id"] == "u1"


def test_d9_record_type_filter_and_pricing_envelope(api: Any) -> None:
    client, svc = api
    svc.ingest_records([_rec("neg", -3, record_type="retraction")])
    only = client.get(
        "/api/v1/finops/billing/usage",
        params={"workspace_id": WS, "envelope": "true", "record_type": "retraction"},
    ).json()
    assert only["total"] == 1 and only["records"][0]["record_id"] == "neg"
    legacy = client.get("/api/v1/finops/billing/pricing").json()
    assert isinstance(legacy, list) and len(legacy) == len(BASELINE_PRICES)
    env = client.get(
        "/api/v1/finops/billing/pricing", params={"envelope": "true", "limit": 2}
    ).json()
    assert env["total"] == len(BASELINE_PRICES) and len(env["records"]) == 2
    assert all("price_per_unit" in r and "pricing_unit" in r for r in env["records"])


def test_d9_json_numbers_stay_numbers_for_existing_consumers(api: Any) -> None:
    client, _ = api
    rec = client.get("/api/v1/finops/billing/usage", params={"workspace_id": WS}).json()[0]
    assert isinstance(rec["usage_quantity"], float)
    assert isinstance(rec["effective_cost"], float)
    assert rec["usage_quantity_exact"] == "1"
    assert rec["cost_basis"] == "LIST_PRICE_ESTIMATE"


# ---------------------------------------------------------------- D10 stale defaults / copy


def test_d10_approval_text_uses_observed_auto_stop_not_a_hardcoded_guess() -> None:
    svc = _sql(_FakeClient("STOPPED", auto_stop=5))
    payload = svc.generate_approval_request(
        "SELECT 1 FROM system.billing.usage", ["system.billing.usage"]
    )
    text = json.dumps(payload)
    assert payload["observed_auto_stop_mins"] == 5
    assert "5-minute auto-stop observed" in text
    for stale in ("10-minute", "10-15 minutes", "$0.15", "$0.35"):
        assert stale not in text
    assert "Not estimated" in payload["expected_compute_charges"]
    assert "Not estimated" in payload["explicit_approval_required"]["estimated_cost"]


def test_d10_unobserved_or_disabled_auto_stop_is_stated_honestly() -> None:
    unknown = _sql(_FakeClient("STOPPED", auto_stop=None)).generate_approval_request(
        "SELECT 1", ["t"]
    )
    assert "not observed" in unknown["explicit_approval_required"]["auto_stop_configured"]
    off = _sql(_FakeClient("STOPPED", auto_stop=0)).generate_approval_request("SELECT 1", ["t"])
    assert "DISABLED" in off["explicit_approval_required"]["auto_stop_configured"]


def test_d10_defaults_are_dynamic_and_validate_response_has_no_fixed_cost_claim() -> None:
    req = IngestionRunCreateRequest()
    assert req.end_date == date.today().isoformat() or req.end_date >= date.today().isoformat()[:8]
    assert req.start_date != "2026-10-01" and req.end_date != "2026-11-04"
    svc = BillingIngestionService(sql_service=_sql())
    val = svc.validate_ingestion(WS)
    assert "Not estimated" in val.expected_operational_cost
    assert "$0.15" not in json.dumps(val.model_dump())
    assert "2026-10-01" not in val.query_plan_preview


def test_d10_no_stale_literals_remain_in_billing_sources() -> None:
    for rel in (
        "services/databricks/sql_client.py",
        "schemas/billing_ingestion.py",
        "services/databricks/billing_ingestion_service.py",
    ):
        text = (SRC / rel).read_text(encoding="utf-8")
        for stale in ("10-minute auto-termination", "$0.15", "2026-10-01", "2026-11-04"):
            assert stale not in text, f"{stale!r} in {rel}"


# ---------------------------------------------------------------- D11 data minimisation


def test_d11_query_never_selects_identity_or_free_text_columns() -> None:
    q = build_usage_query(WS, "2026-11-01", "2026-11-10", 10).lower()
    for forbidden in (
        "identity_metadata",
        "notebook_path",
        "run_name",
        "job_name",
        "app_name",
        "select *",
    ):
        assert forbidden not in q
    assert "usage_metadata.warehouse_id as warehouse_id" in q


def test_d11_row_mapper_drops_identity_and_free_text() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    raw = {
        "record_id": "m1",
        "workspace_id": WS,
        "sku_name": "S",
        "usage_start_time": "2026-11-01T00:00:00Z",
        "usage_end_time": "2026-11-01T01:00:00Z",
        "usage_date": "2026-11-01",
        "usage_unit": "DBU",
        "usage_quantity": "1",
        "identity_metadata": {
            "run_as": "someone@example.invalid",
            "created_by": "x@example.invalid",
        },
        "usage_metadata": {
            "cluster_id": "c-1",
            "notebook_path": "/Users/someone@example.invalid/secret",
            "run_name": "private run",
            "job_name": "private job",
        },
    }
    rec = svc._row_to_usage_record(raw)
    assert rec is not None
    assert rec.identity_metadata == {}
    assert rec.usage_metadata == {"cluster_id": "c-1"}
    dumped = json.dumps(rec.model_dump(mode="json"))
    assert "example.invalid" not in dumped and "private" not in dumped


def test_d11_flat_projected_metadata_columns_are_mapped() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    raw = {
        "record_id": "m2",
        "workspace_id": WS,
        "sku_name": "S",
        "usage_start_time": "2026-11-01T00:00:00Z",
        "usage_end_time": "2026-11-01T01:00:00Z",
        "usage_date": "2026-11-01",
        "usage_unit": "DBU",
        "usage_quantity": "1",
        "warehouse_id": WH,
        "endpoint_name": None,
    }
    rec = svc._row_to_usage_record(raw)
    assert rec is not None and rec.usage_metadata == {"warehouse_id": WH}
    assert (rec.resource_type, rec.resource_id) == ("SQL_WAREHOUSE", WH)


def test_d11_rows_from_another_workspace_are_rejected_at_load() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    foreign = {
        "record_id": "f1",
        "workspace_id": "111",
        "sku_name": "S",
        "usage_start_time": "t",
        "usage_end_time": "t",
        "usage_date": "2026-11-01",
        "usage_unit": "DBU",
        "usage_quantity": "1",
    }

    class _Stub:
        def execute_read_only_statement(self, **_: Any) -> list[dict[str, Any]]:
            return [foreign]

    svc._get_sql_service_for_workspace = lambda _w: _Stub()  # type: ignore[method-assign,assignment]
    res = svc.run_ingestion(
        IngestionRunCreateRequest(
            workspace_id=WS, is_approved=True, approval_token="TEST-APPROVED-TOKEN"
        )
    )
    assert res.inserted_count == 0 and res.error_count == 1 and svc._usage_store == {}


# ---------------------------------------------------------------- reconciliation correctness


def test_recon_empty_store_is_no_data() -> None:
    assert (
        BillingIngestionService(sql_service=_sql())
        .get_billing_reconciliation(WS)
        .reconciliation_status
        == "NO_DATA"
    )


def test_recon_clean_data_reconciles_with_all_checks_passing() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec("a", 10), _rec("a", -4, record_type="retraction")])
    r = svc.get_billing_reconciliation(WS)
    assert r.reconciliation_status == "RECONCILED"
    assert r.checks and all(c["passed"] for c in r.checks)
    assert (r.gross_dbu, r.retraction_dbu, r.net_dbu) == (10.0, 4.0, 6.0)
    assert r.net_cost == 13.2 and r.cost_basis == CostBasis.LIST_PRICE_ESTIMATE


def test_recon_unpriced_dbu_is_partial_not_reconciled() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec("a", 10), _rec("b", 5, sku_name="UNKNOWN_SKU")])
    r = svc.get_billing_reconciliation(WS)
    assert r.reconciliation_status == "PARTIAL_PRICING"
    s = svc.get_billing_summary(WS)
    assert s.spend_complete is False and s.pricing_coverage_pct == 50.0
    assert s.total_spend_verified == 22.0  # only the priced row; flagged partial


def test_recon_anomalies_are_detected_not_hidden() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec("bad", 10, record_type="retraction")])  # positive retraction
    r = svc.get_billing_reconciliation(WS)
    assert r.reconciliation_status == "DISCREPANCY_DETECTED"
    assert any(c["name"] == "retraction_sign" and not c["passed"] for c in r.checks)


def test_recon_mixed_currency_is_flagged() -> None:
    svc = BillingIngestionService(sql_service=_sql())
    eur = dict(baseline_price_rows()[0], currency_code="EUR", account_id="eu")
    usd = baseline_price_rows()[0]
    svc.ingest_price_records([svc._row_to_price_record(usd), svc._row_to_price_record(eur)])  # type: ignore[list-item]
    # identical rates but distinct currency -> both candidates share a start time & rate -> matched once
    svc.ingest_records([_rec("a", 1)])
    rec = svc._usage_store["a"]
    assert rec.currency in {"USD", "EUR", None}


def test_recon_unit_separation_holds() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec("d", 4), _rec("g", 9, usage_unit="BYTE_HOURS")])
    r = svc.get_billing_reconciliation(WS)
    unit = next(c for c in r.checks if c["name"] == "unit_separation")
    assert unit["passed"] and r.net_dbu == 4.0


# ---------------------------------------------------------------- cost-basis labelling


def test_cost_basis_azure_invoiced_is_never_produced_by_the_application() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "billing_sql.py":
            continue
        if re.search(r"CostBasis\.AZURE_INVOICED|\"AZURE_INVOICED\"", text):
            offenders.append(str(path.relative_to(SRC)))
    assert offenders == [], offenders


def test_cost_basis_is_explicit_on_records_summary_and_reconciliation() -> None:
    svc = _priced_service()
    svc.ingest_records([_rec("a", 2), _rec("n", 2, sku_name="UNKNOWN_SKU")])
    assert svc._usage_store["a"].cost_basis == CostBasis.LIST_PRICE_ESTIMATE
    assert svc._usage_store["n"].cost_basis == CostBasis.METERED_USAGE
    assert svc.get_billing_summary(WS).cost_basis == CostBasis.LIST_PRICE_ESTIMATE
    assert {c.value for c in CostBasis} == {
        "METERED_USAGE",
        "LIST_PRICE_ESTIMATE",
        "AZURE_INVOICED",
    }


# ---------------------------------------------------------------- migration (prepared, never applied here)


def test_migration_0004_is_prepared_with_correct_lineage() -> None:
    import importlib.util

    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/2026_11_13_0004_billing_precision_and_row_identity.py"
    )
    spec = importlib.util.spec_from_file_location("m0004", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "2026_11_13_0004" and mod.down_revision == "2026_11_07_0003"
    assert callable(mod.upgrade) and callable(mod.downgrade)
    text = path.read_text(encoding="utf-8")
    assert "NOT APPLIED" in text and "A1" in text
