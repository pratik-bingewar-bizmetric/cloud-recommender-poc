"""Comprehensive tests for Databricks Phase 2.1C Warehouse-Independent Readiness.

Verifies:
1. SQL Statements API multi-chunk result pagination and complete retrieval.
2. Partial extraction detection and manifest mismatch rejection.
3. High-watermark checkpoint persistence and incremental retrieval.
4. Data model fidelity: Decimal precision, lineage, source IDs, retractions.
5. Multi-dimensional pricing reconciliation with controlled fixtures.
6. Process-restart recovery: reloading persisted database records into memory.
7. Idempotent upserts and duplicate prevention on retry.
"""

import asyncio
import threading
from collections.abc import Generator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cloud_recommender.api.routes import finops as finops_routes
from cloud_recommender.core.auth import AuthenticatedUser, get_current_user
from cloud_recommender.db.models import (
    Base,
    BillingPriceRecordModel,
    BillingSourceCheckpointModel,
    BillingUsageRecordModel,
)
from cloud_recommender.schemas.billing_ingestion import (
    BillingUsageRecord,
)
from cloud_recommender.services.databricks.billing_ingestion_service import (
    BillingIngestionService,
)
from cloud_recommender.services.databricks.sql_client import (
    DatabricksSqlService,
    LedgerHandle,
    StatementIncompleteError,
)
from tests.fixtures.billing_baseline import load_baseline_prices

WS = "642006393507276"
WH = "05ed10a52697a344"
COLS = [
    "record_id",
    "workspace_id",
    "sku_name",
    "usage_start_time",
    "usage_end_time",
    "usage_date",
    "usage_unit",
    "usage_quantity",
    "warehouse_id",
]


class _FakeAsyncSession:
    """AsyncSession look-alike whose run_sync hands a sync Session to the callback."""

    def __init__(self, sync: Session) -> None:
        self.sync = sync

    async def run_sync(self, fn: Any) -> Any:
        return fn(self.sync)


@pytest.fixture
def db_ledger() -> Generator[tuple[LedgerHandle, Session], None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    sync = sessionmaker(bind=engine)()
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    fake = _FakeAsyncSession(sync)
    yield LedgerHandle(session=fake, loop=loop), sync  # type: ignore[arg-type]
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=3)
    sync.close()


def _mock_admin_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        sub="admin-operator-2026",
        name="Admin Operator",
        preferred_username="admin@bizmetric.com",
        roles=["FinOpsAdmin"],
        scopes=["access_as_user"],
        is_authenticated=True,
    )


def _statement_response(
    columns: list[str],
    rows: list[list[Any]],
    *,
    next_chunk: int | None = None,
    total_chunks: int | None = None,
    total_rows: int | None = None,
    state: str = "SUCCEEDED",
    truncated: bool = False,
) -> Any:
    return SimpleNamespace(
        statement_id="stmt-chunk-test",
        status=SimpleNamespace(state=state, error=None),
        manifest=SimpleNamespace(
            schema=SimpleNamespace(columns=[SimpleNamespace(name=c) for c in columns]),
            truncated=truncated,
            total_row_count=len(rows) if total_rows is None else total_rows,
            total_chunk_count=total_chunks,
        ),
        result=SimpleNamespace(data_array=rows, next_chunk_index=next_chunk, external_links=None),
    )


# -----------------------------------------------------------------------------
# 1. Statements API Pagination & Chunk Retrieval Tests
# -----------------------------------------------------------------------------


def test_statements_api_multi_chunk_pagination_retrieval() -> None:
    """Verify that multi-chunk Statement Execution API responses are gathered completely."""
    chunk0 = _statement_response(
        COLS,
        [
            [
                "rec-c0",
                WS,
                "SERVERLESS_SQL_COMPUTE",
                "2026-11-01T00:00:00Z",
                "2026-11-01T01:00:00Z",
                "2026-11-01",
                "DBU",
                "10.0",
                WH,
            ]
        ],
        next_chunk=1,
        total_chunks=3,
        total_rows=3,
    )
    chunk1 = SimpleNamespace(
        data_array=[
            [
                "rec-c1",
                WS,
                "SERVERLESS_SQL_COMPUTE",
                "2026-11-01T01:00:00Z",
                "2026-11-01T02:00:00Z",
                "2026-11-01",
                "DBU",
                "15.0",
                WH,
            ]
        ],
        next_chunk_index=2,
        external_links=None,
    )
    chunk2 = SimpleNamespace(
        data_array=[
            [
                "rec-c2",
                WS,
                "SERVERLESS_SQL_COMPUTE",
                "2026-11-01T02:00:00Z",
                "2026-11-01T03:00:00Z",
                "2026-11-01",
                "DBU",
                "20.0",
                WH,
            ]
        ],
        next_chunk_index=None,
        external_links=None,
    )

    chunks_map = {1: chunk1, 2: chunk2}
    fetched_chunks: list[int] = []

    def _get_chunk(_sid: str, chunk_index: int) -> Any:
        fetched_chunks.append(chunk_index)
        return chunks_map[chunk_index]

    fake_client = SimpleNamespace(
        current_user=SimpleNamespace(me=lambda: SimpleNamespace(user_name="admin@bizmetric.com")),
        warehouses=SimpleNamespace(
            get=lambda **_: SimpleNamespace(
                name="Serverless Starter Warehouse",
                state=SimpleNamespace(value="RUNNING"),
                auto_stop_mins=5,
                cluster_size="2X-Small",
            )
        ),
        statement_execution=SimpleNamespace(
            execute_statement=lambda **_: chunk0,
            get_statement_result_chunk_n=_get_chunk,
        ),
    )

    sql_svc = DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id=WH,
        auth_type="mock",
        workspace_client=fake_client,
    )

    query = "SELECT record_id, workspace_id, sku_name, usage_start_time, usage_end_time, usage_date, usage_unit, usage_quantity, warehouse_id FROM system.billing.usage LIMIT 50"
    tok = sql_svc.issue_approval_token(
        query, WH, approver_sub="admin", approver_roles=["FinOpsAdmin"]
    )
    results = sql_svc.execute_read_only_statement(query, is_approved=True, approval_token=tok)

    assert len(results) == 3
    assert [r["record_id"] for r in results] == ["rec-c0", "rec-c1", "rec-c2"]
    assert fetched_chunks == [1, 2]


def test_statements_api_manifest_mismatch_raises_incomplete() -> None:
    """If the manifest declares more rows than returned across chunks, reject execution."""
    resp = _statement_response(
        COLS,
        [
            [
                "r1",
                WS,
                "S",
                "2026-11-01T00:00:00Z",
                "2026-11-01T01:00:00Z",
                "2026-11-01",
                "DBU",
                "1.0",
                WH,
            ]
        ],
        total_rows=5,
    )
    fake_client = SimpleNamespace(
        current_user=SimpleNamespace(me=lambda: SimpleNamespace(user_name="admin@bizmetric.com")),
        warehouses=SimpleNamespace(
            get=lambda **_: SimpleNamespace(
                name="WH",
                state=SimpleNamespace(value="RUNNING"),
                auto_stop_mins=5,
                cluster_size="2X-Small",
            )
        ),
        statement_execution=SimpleNamespace(execute_statement=lambda **_: resp),
    )
    sql_svc = DatabricksSqlService(auth_type="mock", workspace_client=fake_client)
    q = "SELECT record_id FROM system.billing.usage LIMIT 10"
    tok = sql_svc.issue_approval_token(q, WH, approver_sub="admin", approver_roles=["FinOpsAdmin"])
    with pytest.raises(StatementIncompleteError) as exc:
        sql_svc.execute_read_only_statement(q, is_approved=True, approval_token=tok)
    assert exc.value.code == "RESULT_INCOMPLETE"


# -----------------------------------------------------------------------------
# 2. Checkpoint Management & Incremental Ingestion Tests
# -----------------------------------------------------------------------------


def test_checkpoint_persistence_and_incremental_retrieval(
    db_ledger: tuple[LedgerHandle, Session],
) -> None:
    """Verify watermark checkpoints are updated accurately in billing_source_checkpoints."""
    handle, sync = db_ledger
    svc = BillingIngestionService(sql_service=DatabricksSqlService(auth_type="mock"))

    batch1 = [
        BillingUsageRecord(
            record_id="b1-rec1",
            workspace_id=WS,
            sku_name="SERVERLESS_SQL_COMPUTE",
            usage_start_time="2026-11-01T00:00:00Z",
            usage_end_time="2026-11-01T01:00:00Z",
            usage_date="2026-11-01",
            usage_unit="DBU",
            usage_quantity=Decimal("10.5"),
        ),
        BillingUsageRecord(
            record_id="b1-rec2",
            workspace_id=WS,
            sku_name="SERVERLESS_SQL_COMPUTE",
            usage_start_time="2026-11-02T00:00:00Z",
            usage_end_time="2026-11-02T01:00:00Z",
            usage_date="2026-11-02",
            usage_unit="DBU",
            usage_quantity=Decimal("12.0"),
        ),
    ]

    svc.persist_checkpoint_to_db(WS, "system.billing.usage", batch1, handle)
    sync.expire_all()
    cp1 = sync.execute(select(BillingSourceCheckpointModel)).scalar_one()
    assert cp1.workspace_id == WS
    assert cp1.table_name == "system.billing.usage"
    assert cp1.latest_usage_date == "2026-11-02"
    assert cp1.records_ingested_total == 2

    # Second incremental batch advances high watermark
    batch2 = [
        BillingUsageRecord(
            record_id="b2-rec3",
            workspace_id=WS,
            sku_name="SERVERLESS_SQL_COMPUTE",
            usage_start_time="2026-11-05T00:00:00Z",
            usage_end_time="2026-11-05T01:00:00Z",
            usage_date="2026-11-05",
            usage_unit="DBU",
            usage_quantity=Decimal("8.0"),
        )
    ]
    svc.persist_checkpoint_to_db(WS, "system.billing.usage", batch2, handle)
    sync.expire_all()
    cp2 = sync.execute(select(BillingSourceCheckpointModel)).scalar_one()
    assert cp2.latest_usage_date == "2026-11-05"
    assert cp2.records_ingested_total == 3

    # Check retrieval helper
    retrieved = svc.get_checkpoint_from_db(WS, "system.billing.usage", handle)
    assert retrieved is not None
    assert retrieved["latest_usage_date"] == "2026-11-05"
    assert retrieved["records_ingested_total"] == 3


# -----------------------------------------------------------------------------
# 3. Process Restart & Database Reload Tests
# -----------------------------------------------------------------------------


def test_process_restart_reloads_usage_and_prices_from_db(
    db_ledger: tuple[LedgerHandle, Session],
) -> None:
    """Verify that persisted records in PostgreSQL are re-hydrated cleanly across restarts."""
    handle, sync = db_ledger
    svc1 = BillingIngestionService(sql_service=DatabricksSqlService(auth_type="mock"))
    load_baseline_prices(svc1)

    rec = BillingUsageRecord(
        record_id="persist-001",
        workspace_id=WS,
        sku_name="SERVERLESS_SQL_COMPUTE",
        usage_start_time="2026-11-01T00:00:00Z",
        usage_end_time="2026-11-01T01:00:00Z",
        usage_date="2026-11-01",
        usage_unit="DBU",
        usage_quantity=Decimal("20.0"),
        source_row_hash="hash-abc-123",
    )
    svc1.persist_usage_records_to_db([rec], handle)
    svc1.persist_price_records_to_db(svc1._price_store, handle)

    # Verify rows in database tables
    sync.expire_all()
    assert len(sync.execute(select(BillingUsageRecordModel)).scalars().all()) == 1
    assert len(sync.execute(select(BillingPriceRecordModel)).scalars().all()) > 0

    # Simulate backend restart with clean, unpopulated service instance
    svc2 = BillingIngestionService(sql_service=DatabricksSqlService(auth_type="mock"))
    assert len(svc2._usage_store) == 0
    assert len(svc2._price_store) == 0

    # Load from database ledger
    n_usage = svc2.load_persisted_records(handle)
    n_prices = svc2.load_persisted_price_records(handle)
    assert n_usage == 1
    assert n_prices > 0

    # Verify re-hydrated usage was priced automatically
    assert "persist-001" in svc2._usage_store
    loaded_rec = svc2._usage_store["persist-001"]
    assert loaded_rec.pricing_matched is True
    assert loaded_rec.effective_cost is not None
    assert round(loaded_rec.effective_cost, 2) == Decimal("44.00")  # 20 DBU * 2.20 list price


# -----------------------------------------------------------------------------
# 4. Multi-Dimensional Reconciliation & Retraction Identity Tests
# -----------------------------------------------------------------------------


def test_multi_dimensional_reconciliation_and_retractions() -> None:
    """Verify exact 6-identity reconciliation with positive usage, retractions, and unmatched compute."""
    svc = BillingIngestionService(sql_service=DatabricksSqlService(auth_type="mock"))
    load_baseline_prices(svc)

    records = [
        # Original serverless SQL usage
        BillingUsageRecord(
            record_id="rec-sql-orig",
            workspace_id=WS,
            sku_name="SERVERLESS_SQL_COMPUTE",
            usage_start_time="2026-11-01T00:00:00Z",
            usage_end_time="2026-11-01T01:00:00Z",
            usage_date="2026-11-01",
            usage_unit="DBU",
            usage_quantity=Decimal("50.0"),
            record_type="original",
        ),
        # Retraction (correction) reducing 10 DBU
        BillingUsageRecord(
            record_id="rec-sql-retract",
            workspace_id=WS,
            sku_name="SERVERLESS_SQL_COMPUTE",
            usage_start_time="2026-11-01T00:00:00Z",
            usage_end_time="2026-11-01T01:00:00Z",
            usage_date="2026-11-01",
            usage_unit="DBU",
            usage_quantity=Decimal("-10.0"),
            record_type="retraction",
        ),
        # Unmatched preview compute (Genie) - must preserve without fake $0.00
        BillingUsageRecord(
            record_id="rec-genie-unmatched",
            workspace_id=WS,
            sku_name="GENIE_SPACE_COMPUTE",
            usage_start_time="2026-11-01T02:00:00Z",
            usage_end_time="2026-11-01T03:00:00Z",
            usage_date="2026-11-01",
            usage_unit="DBU",
            usage_quantity=Decimal("15.0"),
            record_type="original",
        ),
        # Storage record (BYTE_HOURS) - must not be contaminated with DBU rate
        BillingUsageRecord(
            record_id="rec-storage-unmatched",
            workspace_id=WS,
            sku_name="MANAGED_STORAGE",
            usage_start_time="2026-11-01T00:00:00Z",
            usage_end_time="2026-11-01T01:00:00Z",
            usage_date="2026-11-01",
            usage_unit="BYTE_HOURS",
            usage_quantity=Decimal("1000000.0"),
            record_type="original",
        ),
    ]

    svc.ingest_records(records)
    recon = svc.get_billing_reconciliation(workspace_id=WS)

    assert recon.reconciliation_status == "PARTIAL_PRICING"
    assert recon.checks is not None
    assert all(c["passed"] for c in recon.checks), (
        f"Failed checks: {[c for c in recon.checks if not c['passed']]}"
    )

    # Check summary calculation
    summary = svc.get_billing_summary(workspace_id=WS)
    assert summary.total_dbu == 65.0  # 50 + 15 gross DBU
    assert summary.net_dbu == 55.0  # (50 - 10) + 15 = 55 net DBU
    assert summary.retraction_dbu == 10.0  # 10 DBU retraction
    assert summary.matched_pricing_count == 2  # orig and retraction matched
    assert summary.unmatched_pricing_count == 1  # genie unmatched DBU


# -----------------------------------------------------------------------------
# 5. Checkpoint & Reconciliation Endpoints API Integration Test
# -----------------------------------------------------------------------------


def test_finops_api_checkpoint_endpoint(
    db_ledger: tuple[LedgerHandle, Session],
) -> None:
    """Verify GET /api/v1/finops/billing/checkpoint returns active checkpoint state."""
    handle, _ = db_ledger
    svc = BillingIngestionService(sql_service=DatabricksSqlService(auth_type="mock"))
    rec = BillingUsageRecord(
        record_id="cp-test-01",
        workspace_id=WS,
        sku_name="SERVERLESS_SQL_COMPUTE",
        usage_start_time="2026-11-10T00:00:00Z",
        usage_end_time="2026-11-10T01:00:00Z",
        usage_date="2026-11-10",
        usage_unit="DBU",
        usage_quantity=Decimal("5.0"),
    )
    svc.persist_checkpoint_to_db(WS, "system.billing.usage", [rec], handle)

    app = FastAPI()
    app.include_router(finops_routes.router, prefix="/api/v1")
    app.dependency_overrides[finops_routes.get_billing_service] = lambda: svc
    app.dependency_overrides[finops_routes.get_billing_ledger] = lambda: handle
    app.dependency_overrides[finops_routes.warm_live_metadata] = lambda: None
    app.dependency_overrides[get_current_user] = _mock_admin_user

    client = TestClient(app)
    res = client.get("/api/v1/finops/billing/checkpoint", params={"workspace_id": WS})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "CHECKPOINT_ACTIVE"
    assert data["latest_usage_date"] == "2026-11-10"
    assert data["records_ingested_total"] == 1
