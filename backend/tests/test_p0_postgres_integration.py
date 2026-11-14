"""PostgreSQL integration tests for the approval-token ledger and migration 0004.

These run ONLY against a disposable PostgreSQL that the operator names explicitly:

    TEST_POSTGRES_URL=postgresql+asyncpg://user:pass@host:5432/<name>_test  pytest tests/test_p0_postgres_integration.py

They are skipped otherwise (no PostgreSQL/Docker is assumed to exist), so the default suite stays
100% offline. Safety rules enforced before anything is created:

* the URL must differ from the application's configured ``database_url`` (host, port, database);
* the database name must contain ``test`` (``..._test``, ``test_...``);
* ledger tests only create tables inside a private, uniquely named SCHEMA and drop it afterwards;
* the migration test additionally requires ``TEST_POSTGRES_MIGRATE=1`` and a database that holds
  no tables at all, and removes what it created.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cloud_recommender.core.config import Settings
from cloud_recommender.db.models import BillingApprovalTokenModel
from cloud_recommender.services.databricks.billing_sql import build_usage_query
from cloud_recommender.services.databricks.sql_client import (
    ApprovalLedgerError,
    DatabricksSqlService,
    LedgerHandle,
)

TEST_URL = os.environ.get("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not TEST_URL, reason="TEST_POSTGRES_URL not set (no disposable PostgreSQL provided)"
)

WS = "642006393507276"
WH = "05ed10a52697a344"
BACKEND = Path(__file__).resolve().parents[1]


def _assert_disposable(url: str) -> None:
    """Refuse to touch anything that could be the application's database."""
    target = make_url(url)
    app = make_url(Settings().database_url)
    same = (target.host, target.port or 5432, target.database) == (
        app.host,
        app.port or 5432,
        app.database,
    )
    assert not same, "TEST_POSTGRES_URL points at the application database; refusing to run."
    assert "test" in (target.database or "").lower(), (
        "TEST_POSTGRES_URL database name must contain 'test'."
    )


def _service() -> DatabricksSqlService:
    return DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id=WH,
        auth_type="mock",
    )


QUERY = build_usage_query(WS, "2026-11-01", "2026-11-10", 100)


def _issue(svc: DatabricksSqlService, handle: LedgerHandle) -> str:
    return svc.issue_approval_token(
        query=QUERY,
        warehouse_id=WH,
        approver_sub="op",
        approver_roles=["Admin"],
        max_rows=100,
        start_date="2026-11-01",
        end_date="2026-11-10",
        session=handle,
    )


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    _assert_disposable(TEST_URL)
    schema = f"p0it_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(TEST_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = admin.execution_options(schema_translate_map={None: schema})
    async with scoped.begin() as conn:
        await conn.run_sync(BillingApprovalTokenModel.__table__.create)  # type: ignore[attr-defined]
    try:
        yield scoped
    finally:
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def _handle(engine: AsyncEngine) -> tuple[AsyncSession, LedgerHandle]:
    session = async_sessionmaker(engine, expire_on_commit=False)()
    return session, LedgerHandle(session=session, loop=asyncio.get_running_loop())


async def test_pg_issue_verify_consume_replay_across_service_instances(engine: AsyncEngine) -> None:
    session, handle = _handle(engine)
    try:
        svc = _service()
        tok = await asyncio.to_thread(_issue, svc, handle)
        assert await asyncio.to_thread(svc.verify_approval_token, tok, QUERY, WH, handle) is True
        assert await asyncio.to_thread(svc.consume_approval_token, tok, handle) is True
        # a brand-new service (simulated restart: empty in-memory set) must still refuse the replay
        fresh = _service()
        assert await asyncio.to_thread(fresh.verify_approval_token, tok, QUERY, WH, handle) is False
        assert await asyncio.to_thread(fresh.consume_approval_token, tok, handle) is False
        row = (
            await session.execute(
                text("SELECT is_consumed, consumed_at FROM billing_approval_tokens")
            )
        ).one_or_none()
        assert row is not None and row[0] is True and row[1] is not None
    finally:
        await session.close()


async def test_pg_concurrent_consume_has_exactly_one_winner(engine: AsyncEngine) -> None:
    session, handle = _handle(engine)
    tok = await asyncio.to_thread(_issue, _service(), handle)
    await session.close()

    def attempt(h: LedgerHandle) -> bool:
        # separate service instance each time => the in-memory set cannot decide the outcome
        return _service().consume_approval_token(tok, session=h)

    contenders = [_handle(engine) for _ in range(12)]
    try:
        results = await asyncio.gather(*(asyncio.to_thread(attempt, h) for _, h in contenders))
    finally:
        for s, _ in contenders:
            await s.close()
    assert results.count(True) == 1 and results.count(False) == 11


async def test_pg_unreachable_database_fails_closed() -> None:
    _assert_disposable(TEST_URL)
    dead = make_url(TEST_URL).set(host="127.0.0.1", port=1)
    dead_engine = create_async_engine(dead, connect_args={"timeout": 2})
    session = async_sessionmaker(dead_engine)()
    handle = LedgerHandle(session=session, loop=asyncio.get_running_loop())
    svc = _service()
    try:
        with pytest.raises(ApprovalLedgerError):
            await asyncio.to_thread(_issue, svc, handle)
        assert (
            await asyncio.to_thread(svc.verify_approval_token, "v2:x:y:z", QUERY, WH, handle)
            is False
        )
        assert await asyncio.to_thread(svc.consume_approval_token, "v2:x:y:z", handle) is False
    finally:
        await session.close()
        await dead_engine.dispose()


async def test_pg_missing_ledger_table_fails_closed() -> None:
    _assert_disposable(TEST_URL)
    schema = f"p0it_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(TEST_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = admin.execution_options(schema_translate_map={None: schema})
    session, handle = _handle(scoped)
    try:
        with pytest.raises(ApprovalLedgerError):
            await asyncio.to_thread(_issue, _service(), handle)
    finally:
        await session.close()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


# ------------------------------------------------------------------ migration 0004


@pytest.mark.skipif(
    os.environ.get("TEST_POSTGRES_MIGRATE") != "1", reason="TEST_POSTGRES_MIGRATE=1 not set"
)
def test_pg_migration_0004_upgrade_constraints_and_guarded_downgrade() -> None:
    from alembic.config import Config

    from alembic import command

    _assert_disposable(TEST_URL)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL.replace("%", "%%"))

    async def _scalar(sql: str) -> Any:
        eng = create_async_engine(TEST_URL)
        try:
            async with eng.begin() as conn:
                return (await conn.execute(text(sql))).scalar_one()
        finally:
            await eng.dispose()

    async def _exec(sql: str) -> None:
        eng = create_async_engine(TEST_URL)
        try:
            async with eng.begin() as conn:
                await conn.execute(text(sql))
        finally:
            await eng.dispose()

    tables = asyncio.run(
        _scalar("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
    )
    assert tables == 0, "migration test needs an EMPTY disposable database"

    command.upgrade(cfg, "head")
    try:
        # NUMERIC(38,18) round-trips exactly
        asyncio.run(
            _exec(
                "INSERT INTO billing_usage_records (workspace_id, record_id, sku_name, cloud, "
                "usage_start_time, usage_end_time, usage_date, usage_unit, usage_quantity, "
                "source_row_hash) VALUES ('1','r1','S','azure', now(), now(), '2026-11-01', 'DBU', "
                "0.123456789012345678, 'h1')"
            )
        )
        assert (
            asyncio.run(_scalar("SELECT usage_quantity::text FROM billing_usage_records"))
            == "0.123456789012345678"
        )
        # correction rows may share a record_id
        asyncio.run(
            _exec(
                "INSERT INTO billing_usage_records (workspace_id, record_id, sku_name, cloud, "
                "usage_start_time, usage_end_time, usage_date, usage_unit, usage_quantity, "
                "source_row_hash) VALUES ('1','r1','S','azure', now(), now(), '2026-11-01', 'DBU', "
                "-0.123456789012345678, 'h2')"
            )
        )
        # NULL account_id cannot duplicate a price row
        price = (
            "INSERT INTO billing_price_records (sku_name, cloud, currency_code, usage_unit, "
            "price_start_time, price_default) VALUES ('S','azure','USD','DBU', "
            "'2026-01-01T00:00:00Z', 1)"
        )
        asyncio.run(_exec(price))
        with pytest.raises(Exception, match="uq_billing_price_identity"):
            asyncio.run(_exec(price))
        # downgrade refuses while data exists (never truncates / fabricates)
        with pytest.raises(RuntimeError, match="Refusing to downgrade"):
            command.downgrade(cfg, "-1")
    finally:
        asyncio.run(_exec("TRUNCATE billing_usage_records, billing_price_records"))
        command.downgrade(cfg, "base")
