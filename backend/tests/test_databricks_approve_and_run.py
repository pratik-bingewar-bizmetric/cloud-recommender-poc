"""Tests for application-managed Databricks billing ingestion approval (Phase 2.1A).

Verifies:
1. Endpoint authentication and RBAC: FinOpsAdmin role enforcement.
2. Zero-mutation guardrail: Warehouse STOPPED state does not resume compute,
   persists auditable approval, and returns operational blocker.
3. Secret redaction: Raw HMAC approval token is NEVER returned in the API response.
4. End-to-end execution: Authorized caller executes ingestion, generates single-use
   approval token internally, and persists records to PostgreSQL ledger.
5. Input validation: Strict workspace ID and date range checks.
"""

import asyncio
import threading
from collections.abc import Generator
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
    BillingApprovalTokenModel,
    BillingIngestionRunModel,
    BillingUsageRecordModel,
)
from cloud_recommender.services.databricks.billing_ingestion_service import (
    BillingIngestionService,
)
from cloud_recommender.services.databricks.sql_client import (
    DatabricksSqlService,
    LedgerHandle,
)
from tests.fixtures.billing_baseline import load_baseline_prices

WS = "642006393507276"
WH = "05ed10a52697a344"


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
        sub="admin-user-001",
        name="Admin Operator",
        preferred_username="admin@bizmetric.com",
        roles=["FinOpsAdmin"],
        scopes=["access_as_user"],
        is_authenticated=True,
    )


def _mock_viewer_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        sub="viewer-user-002",
        name="Viewer User",
        preferred_username="viewer@bizmetric.com",
        roles=["FinOpsViewer"],
        scopes=["access_as_user"],
        is_authenticated=True,
    )


def _statement_response(
    columns: list[str],
    rows: list[list[Any]],
    *,
    state: str = "SUCCEEDED",
) -> Any:
    return SimpleNamespace(
        statement_id="stmt-001",
        status=SimpleNamespace(state=state, error=None),
        manifest=SimpleNamespace(
            schema=SimpleNamespace(columns=[SimpleNamespace(name=c) for c in columns]),
            truncated=False,
            total_row_count=len(rows),
            total_chunk_count=1,
        ),
        result=SimpleNamespace(data_array=rows, next_chunk_index=None, external_links=None),
    )


class _FakeDatabricksClient:
    def __init__(self, state: str = "RUNNING", auto_stop: int | None = 5) -> None:
        self.state = state
        self.auto_stop = auto_stop
        self.executed: list[str] = []
        self.current_user = SimpleNamespace(
            me=lambda: SimpleNamespace(
                user_name="admin@bizmetric.com", display_name="Admin Operator"
            )
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
        cols = [
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
        rows = [
            [
                "rec-001",
                WS,
                "SERVERLESS_SQL_COMPUTE",
                "2026-11-01T00:00:00Z",
                "2026-11-01T01:00:00Z",
                "2026-11-01",
                "DBU",
                "10.5000",
                WH,
            ]
        ]
        return _statement_response(cols, rows)


def _create_test_app(
    svc: BillingIngestionService,
    ledger_handle: LedgerHandle,
    current_user_override: AuthenticatedUser | None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(finops_routes.router, prefix="/api/v1")
    app.dependency_overrides[finops_routes.get_billing_service] = lambda: svc
    app.dependency_overrides[finops_routes.get_billing_ledger] = lambda: ledger_handle
    app.dependency_overrides[finops_routes.warm_live_metadata] = lambda: None
    if current_user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user_override
    return app


def test_approve_and_run_unauthorized_user_forbidden(
    db_ledger: tuple[LedgerHandle, Session],
) -> None:
    """Non-FinOpsAdmin users must be rejected with 403 Forbidden."""
    handle, _ = db_ledger
    svc = BillingIngestionService(sql_service=DatabricksSqlService(auth_type="mock"))
    app = _create_test_app(svc, handle, current_user_override=_mock_viewer_user())
    client = TestClient(app)

    response = client.post(
        "/api/v1/finops/ingestion/approve-and-run",
        json={
            "workspace_id": WS,
            "source_table": "system.billing.usage",
            "start_date": "2026-11-01",
            "end_date": "2026-11-10",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "INSUFFICIENT_PERMISSIONS"


def test_approve_and_run_unauthenticated_rejected(
    db_ledger: tuple[LedgerHandle, Session],
) -> None:
    """Unauthenticated requests must be rejected with 401 Unauthorized."""
    handle, _ = db_ledger
    svc = BillingIngestionService(sql_service=DatabricksSqlService(auth_type="mock"))
    unauth_user = AuthenticatedUser(
        sub="anon",
        roles=[],
        is_authenticated=False,
    )
    app = _create_test_app(svc, handle, current_user_override=unauth_user)
    client = TestClient(app)

    response = client.post(
        "/api/v1/finops/ingestion/approve-and-run",
        json={"workspace_id": WS},
    )
    assert response.status_code == 401


def test_approve_and_run_warehouse_stopped_zero_mutation_guardrail(
    db_ledger: tuple[LedgerHandle, Session],
) -> None:
    """When warehouse is STOPPED, zero-execution policy prevents auto-start."""
    handle, sync = db_ledger
    fake_client = _FakeDatabricksClient(state="STOPPED")
    sql_svc = DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id=WH,
        auth_type="mock",
        workspace_client=fake_client,
    )
    svc = BillingIngestionService(sql_service=sql_svc)
    app = _create_test_app(svc, handle, current_user_override=_mock_admin_user())
    client = TestClient(app)

    response = client.post(
        "/api/v1/finops/ingestion/approve-and-run",
        json={
            "workspace_id": WS,
            "source_table": "system.billing.usage",
            "start_date": "2026-11-01",
            "end_date": "2026-11-10",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["error_code"] == "WAREHOUSE_STOPPED"
    assert "STOPPED" in data["warehouse_status"]
    assert data["approval_token_id"].startswith("tok-")
    # Secret token must NEVER be returned in response
    assert "approval_token" not in data or data.get("approval_token") is None
    assert (
        "Zero-execution policy" in data["error_message"]
        or "zero-execution" in data["error_message"]
    )

    # Verify that an auditable approval token record was persisted in the ledger
    sync.expire_all()
    tokens = sync.execute(select(BillingApprovalTokenModel)).scalars().all()
    assert len(tokens) == 1
    assert tokens[0].approver_sub in ("admin-user-001", "admin@bizmetric.com")
    assert tokens[0].warehouse_id == WH

    # Verify that no SQL execution was attempted against the stopped warehouse
    assert len(fake_client.executed) == 0


def test_approve_and_run_running_warehouse_executes_and_persists_to_db(
    db_ledger: tuple[LedgerHandle, Session],
) -> None:
    """When warehouse is RUNNING, token is generated and consumed internally, persisting to DB."""
    handle, sync = db_ledger
    fake_client = _FakeDatabricksClient(state="RUNNING")
    sql_svc = DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id=WH,
        auth_type="mock",
        workspace_client=fake_client,
    )
    svc = BillingIngestionService(sql_service=sql_svc)
    load_baseline_prices(svc)

    app = _create_test_app(svc, handle, current_user_override=_mock_admin_user())
    client = TestClient(app)

    response = client.post(
        "/api/v1/finops/ingestion/approve-and-run",
        json={
            "workspace_id": WS,
            "source_table": "system.billing.usage",
            "start_date": "2026-11-01",
            "end_date": "2026-11-10",
            "limit": 50,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["workspace_id"] == WS
    assert "RUNNING" in data["warehouse_status"]
    assert data["extracted_count"] == 1
    assert data["inserted_count"] == 1
    assert data["persisted_to_db_count"] == 1
    assert data["approval_token_id"].startswith("tok-")
    assert "approval_token" not in data or data.get("approval_token") is None

    # Check SQL was executed
    assert len(fake_client.executed) == 1

    # Verify records in SQLite / PostgreSQL tables
    sync.expire_all()
    usage_records = sync.execute(select(BillingUsageRecordModel)).scalars().all()
    assert len(usage_records) == 1
    assert usage_records[0].record_id == "rec-001"
    assert usage_records[0].workspace_id == WS
    assert usage_records[0].sku_name == "SERVERLESS_SQL_COMPUTE"

    ingestion_runs = sync.execute(select(BillingIngestionRunModel)).scalars().all()
    assert len(ingestion_runs) == 1
    assert ingestion_runs[0].status == "completed"
    assert ingestion_runs[0].extracted_count == 1


@pytest.mark.parametrize("bad_ws", ["1' OR '1'='1", "123; DROP TABLE x", "", "12a", "-1", " "])
def test_approve_and_run_bad_workspace_id_rejected(
    db_ledger: tuple[LedgerHandle, Session],
    bad_ws: str,
) -> None:
    handle, _ = db_ledger
    svc = BillingIngestionService(sql_service=DatabricksSqlService(auth_type="mock"))
    app = _create_test_app(svc, handle, current_user_override=_mock_admin_user())
    client = TestClient(app)

    response = client.post(
        "/api/v1/finops/ingestion/approve-and-run",
        json={"workspace_id": bad_ws},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "bad_start,bad_end",
    [
        ("2026-11-10", "2026-11-01"),  # inverted
        ("not-a-date", "2026-11-10"),
        ("2026-11-01", "2026-99-99"),
    ],
)
def test_approve_and_run_bad_dates_rejected(
    db_ledger: tuple[LedgerHandle, Session],
    bad_start: str,
    bad_end: str,
) -> None:
    handle, _ = db_ledger
    svc = BillingIngestionService(sql_service=DatabricksSqlService(auth_type="mock"))
    app = _create_test_app(svc, handle, current_user_override=_mock_admin_user())
    client = TestClient(app)

    response = client.post(
        "/api/v1/finops/ingestion/approve-and-run",
        json={
            "workspace_id": WS,
            "start_date": bad_start,
            "end_date": bad_end,
        },
    )
    assert response.status_code == 422
