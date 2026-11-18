"""M2.4 regression tests: one connection state, honest refresh, zero vs unavailable (offline)."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from cloud_recommender.schemas.billing_ingestion import BillingUsageRecord
from cloud_recommender.schemas.databricks import (
    CategoryDiscoveryStatus,
    DatabricksCloud,
    DatabricksConnectionStatus,
    DatabricksWorkspaceDiscoveryResponse,
    WorkspaceConnectionState,
)
from cloud_recommender.schemas.finops import KpiStatus
from cloud_recommender.services.databricks.billing_ingestion_service import BillingIngestionService
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService
from cloud_recommender.services.databricks.refresher import MetadataRefresher
from cloud_recommender.services.databricks.workspace_service import (
    DatabricksWorkspaceService,
    connection_state_for,
)
from tests.fixtures.billing_baseline import add_synthetic_history
from tests.fixtures.live_inventory import (
    CONNECTION_ID,
    WORKSPACE_ID,
    fixture_resources,
    make_analytics_service,
)


@pytest.fixture
def svc() -> Iterator[FinOpsAnalyticsService]:
    """Analytics service with isolated caches/refresh state; registry status restored after."""
    service = make_analytics_service(with_billing=False)
    ws = service.workspace_service
    ws._refresh_state = {}
    conn = ws._resolve_raw_connection(CONNECTION_ID)
    assert conn is not None
    saved = (conn["status"], conn.get("last_error"), conn.get("last_connected_at"))
    conn["status"] = DatabricksConnectionStatus.CONNECTED
    conn["last_connected_at"] = datetime.now(UTC)
    conn["last_error"] = None
    try:
        yield service
    finally:
        conn["status"], conn["last_error"], conn["last_connected_at"] = saved


def _health(service: FinOpsAnalyticsService):  # type: ignore[no-untyped-def]
    return asyncio.run(service.workspace_service.get_health(CONNECTION_ID))


# ---------------------------------------------------------------------------
# One connection state; SQL warehouse is separate
# ---------------------------------------------------------------------------


def test_stopped_warehouse_does_not_make_workspace_unavailable(svc: FinOpsAnalyticsService) -> None:
    health = _health(svc)
    assert health.connection_state == WorkspaceConnectionState.CONNECTED
    assert health.sql_warehouse is not None
    assert health.sql_warehouse.state == "STOPPED"
    assert health.sql_warehouse.sql_available is False
    assert "approval" in health.sql_warehouse.message
    # REST inventory still resolves while the warehouse is stopped
    assert health.resource_counts_by_type["cluster"] == 1
    assert health.resource_counts_by_type["warehouse"] == 1


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (DatabricksConnectionStatus.CONNECTED, WorkspaceConnectionState.CONNECTED),
        (DatabricksConnectionStatus.AUTH_FAILED, WorkspaceConnectionState.AUTHENTICATION_REQUIRED),
        (DatabricksConnectionStatus.PERMISSION_DENIED, WorkspaceConnectionState.ACCESS_DENIED),
        (DatabricksConnectionStatus.CONNECTION_ERROR, WorkspaceConnectionState.ERROR),
        (DatabricksConnectionStatus.READY_TO_CONNECT, WorkspaceConnectionState.DISCONNECTED),
    ],
)
def test_registry_status_maps_to_single_normalized_state(
    status: DatabricksConnectionStatus, expected: WorkspaceConnectionState
) -> None:
    assert connection_state_for({"workspace_url": "https://x", "status": status}) == expected


def test_missing_host_is_not_configured() -> None:
    state = connection_state_for(
        {"workspace_url": "", "status": DatabricksConnectionStatus.CONNECTED}
    )
    assert state == WorkspaceConnectionState.NOT_CONFIGURED


def test_permission_failure_is_explicit_in_health(svc: FinOpsAnalyticsService) -> None:
    conn = svc.workspace_service._resolve_raw_connection(CONNECTION_ID)
    assert conn is not None
    conn["status"] = DatabricksConnectionStatus.PERMISSION_DENIED
    conn["last_error"] = "PERMISSION_DENIED: cannot list clusters"
    health = _health(svc)
    assert health.connection_state == WorkspaceConnectionState.ACCESS_DENIED
    assert "PERMISSION_DENIED" in (health.last_error or "")


def test_health_exposes_identity_environment_and_timestamps(svc: FinOpsAnalyticsService) -> None:
    health = _health(svc)
    assert health.workspace_id == WORKSPACE_ID
    assert health.environment == "development"  # not "Production"
    assert health.workspace_url and health.workspace_name
    assert health.last_connected_at is not None
    assert health.last_discovery_at is not None
    assert health.refresh_interval_seconds >= 1


# ---------------------------------------------------------------------------
# Failed refresh keeps last good inventory and is reported stale
# ---------------------------------------------------------------------------


def _failed_discovery() -> DatabricksWorkspaceDiscoveryResponse:
    return DatabricksWorkspaceDiscoveryResponse(
        connection_id=CONNECTION_ID,
        workspace_id=WORKSPACE_ID,
        workspace_name="x",
        workspace_url="https://example.invalid",
        cloud=DatabricksCloud.AZURE,
        overall_status="failed",
        categories={},
        resources=[],
        total_resources_count=0,
        discovered_at=datetime.now(UTC),
    )


def test_failed_refresh_does_not_replace_good_inventory_and_marks_stale(
    svc: FinOpsAnalyticsService,
) -> None:
    ws = svc.workspace_service

    async def failing(**_: object) -> DatabricksWorkspaceDiscoveryResponse:
        return _failed_discovery()

    ws.discovery_service.discover_workspace = failing  # type: ignore[method-assign,assignment]
    result = asyncio.run(ws.get_or_discover_workspace(CONNECTION_ID, force_refresh=True))
    assert result.total_resources_count == len(fixture_resources())  # last good inventory kept
    assert ws._discovery_cache[CONNECTION_ID].overall_status == "completed"

    health = _health(svc)
    assert health.discovery_stale is True
    assert health.last_discovery_attempt_at is not None
    # inventory is still served (as stale), never silently zeroed
    assert health.resource_counts_by_type["app"] == 1
    # and compute inventory still lists the cluster
    assert len(svc.get_compute_warehouses().clusters) == 1


def test_old_successful_discovery_is_flagged_stale(svc: FinOpsAnalyticsService) -> None:
    ws = svc.workspace_service
    ws._refresh_state[CONNECTION_ID] = {
        "last_success_at": datetime.now(UTC) - timedelta(hours=1),
        "last_error": None,
    }
    assert _health(svc).discovery_stale is True
    ws._refresh_state[CONNECTION_ID] = {"last_success_at": datetime.now(UTC), "last_error": None}
    assert _health(svc).discovery_stale is False


# ---------------------------------------------------------------------------
# Refresher: no overlap, intervals, keeps metadata caches
# ---------------------------------------------------------------------------


class _FakeWs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.release = asyncio.Event()
        self.settings = DatabricksWorkspaceService().settings

    async def get_or_discover_workspace(self, _cid: str, **kwargs: bool) -> None:
        self.calls.append(("inventory", bool(kwargs.get("keep_metadata"))))
        await self.release.wait()

    async def get_unity_catalog_metadata(self, _cid: str, **_: object) -> None:
        self.calls.append(("uc", True))

    async def get_system_tables_metadata(self, _cid: str, **_: object) -> None:
        self.calls.append(("system", True))


def test_refresher_prevents_overlapping_refreshes_and_keeps_metadata() -> None:
    async def run() -> _FakeWs:
        fake = _FakeWs()
        r = MetadataRefresher(fake, inventory_interval=60, metadata_interval=600)  # type: ignore[arg-type]
        first = asyncio.create_task(r.refresh_once("c1", force=True))
        await asyncio.sleep(0)
        await r.refresh_once("c1", force=True)  # overlapping request is skipped
        fake.release.set()
        await first
        return fake

    fake = asyncio.run(run())
    assert [c for c in fake.calls if c[0] == "inventory"] == [("inventory", True)]
    assert ("uc", True) in fake.calls and ("system", True) in fake.calls


def test_refresher_respects_intervals_and_activity_window() -> None:
    async def run() -> int:
        fake = _FakeWs()
        fake.release.set()
        r = MetadataRefresher(fake, inventory_interval=3600, metadata_interval=3600)  # type: ignore[arg-type]
        await r.refresh_once("c1")  # due (never refreshed)
        await r.refresh_once("c1")  # not due yet
        return len([c for c in fake.calls if c[0] == "inventory"])

    assert asyncio.run(run()) == 1
    r = MetadataRefresher(_FakeWs(), 60, 600)  # type: ignore[arg-type]
    assert r.active_connections() == []
    r.touch("c1")
    assert r.active_connections() == ["c1"]


# ---------------------------------------------------------------------------
# Zero vs unavailable
# ---------------------------------------------------------------------------


def test_unavailable_is_dash_with_reason_and_zero_is_a_real_value() -> None:
    blocked = make_analytics_service(with_billing=False).get_executive_overview()
    spend = blocked.kpis["total_spend"]
    assert spend.value is None and spend.formatted_value == "-"
    assert spend.status == KpiStatus.BLOCKED_PENDING_APPROVAL
    assert spend.reason and "approved read-only SQL" in spend.reason

    with_rows = make_analytics_service(with_billing=True)
    wh = with_rows.get_executive_overview(resource_id="05ed10a52697a344", resource_type="warehouse")
    ai = wh.kpis["ai_spend"]
    assert ai.value == 0.0 and ai.formatted_value == "$0.00" and ai.reason is None  # measured zero


def test_empty_billing_summary_and_reconciliation_are_unknown_not_zero() -> None:
    svc = BillingIngestionService()
    summary = svc.get_billing_summary()
    assert summary.total_dbu is None and summary.net_dbu is None
    assert summary.total_spend_verified is None and summary.data_status == "NO_BILLING_ROWS"
    rec = svc.get_billing_reconciliation()
    assert rec.reconciliation_status == "NO_DATA" and rec.gross_dbu is None and rec.net_cost is None


def test_unmatched_billing_never_shows_as_verified_spend() -> None:
    svc = BillingIngestionService()
    svc.ingest_records(
        [
            BillingUsageRecord(
                record_id="u1",
                workspace_id=WORKSPACE_ID,
                sku_name="UNKNOWN_SKU",
                usage_start_time="2026-11-01T00:00:00Z",
                usage_end_time="2026-11-01T01:00:00Z",
                usage_date="2026-11-01",
                usage_unit="DBU",
                usage_quantity=10.0,
            )
        ]
    )
    summary = svc.get_billing_summary(workspace_id=WORKSPACE_ID)
    assert summary.total_dbu == 10.0 and summary.total_spend_verified is None
    assert summary.unmatched_pricing_count == 1


def test_actual_figures_appear_only_when_billing_rows_exist() -> None:
    none = make_analytics_service(with_billing=False)
    assert none.get_cost_explorer().kpis["gross_consumption"].value is None
    assert none.get_forecast_budgets().kpis["actual_mtd"].value is None
    some = make_analytics_service(with_billing=False)
    add_synthetic_history(some.billing_service, days=3)
    assert some.get_cost_explorer().kpis["gross_consumption"].value == pytest.approx(330.0)
    assert some.get_forecast_budgets().kpis["forecast_month_end"].value is None  # < 14 days


def test_budget_utilization_needs_both_budget_and_actuals() -> None:
    svc = make_analytics_service(with_billing=False)
    add_synthetic_history(svc.billing_service, days=20)
    assert svc.get_forecast_budgets().kpis["budget_utilization"].value is None  # no budget set
    svc._budget = lambda: 5000.0  # type: ignore[method-assign]
    util = svc.get_forecast_budgets().kpis["budget_utilization"]
    assert util.value == pytest.approx(44.0)


def test_inventory_provenance_carries_retrieval_time(svc: FinOpsAnalyticsService) -> None:
    comp = svc.get_compute_warehouses()
    inv = comp.provenance["inventory"]
    assert inv.classification == KpiStatus.LIVE
    assert inv.retrieved_at is not None and inv.record_count == 2


def test_category_status_enum_still_distinguishes_no_resources() -> None:
    assert CategoryDiscoveryStatus.NO_RESOURCES_FOUND.value == "no_resources_found"


# ---------------------------------------------------------------------------
# Root cause of "Connected in one place, Unavailable in another"
# ---------------------------------------------------------------------------


def test_registry_status_is_shared_across_service_instances() -> None:
    """A status written by one service instance must be visible to every later instance.

    The API builds a new DatabricksWorkspaceService per request; previously each instance
    replaced the shared registry entry with a copy, so a CONNECTED status set by a long-running
    discovery was lost and health reported DISCONNECTED right after a successful discovery.
    """
    first = DatabricksWorkspaceService()
    conn = first._resolve_raw_connection(CONNECTION_ID)
    assert conn is not None
    saved = (conn["status"], conn.get("last_connected_at"))
    try:
        later = DatabricksWorkspaceService()  # a new request builds a new instance
        conn["status"] = DatabricksConnectionStatus.CONNECTED
        conn["last_connected_at"] = datetime.now(UTC)
        newest = DatabricksWorkspaceService()
        for service in (first, later, newest):
            resolved = service._resolve_raw_connection(CONNECTION_ID)
            assert resolved is not None
            assert connection_state_for(resolved) == WorkspaceConnectionState.CONNECTED
        assert later._resolve_raw_connection(CONNECTION_ID) is first._resolve_raw_connection(
            CONNECTION_ID
        )
    finally:
        conn["status"], conn["last_connected_at"] = saved


# ---------------------------------------------------------------------------
# Request-time warm-up never blocks a dashboard request
# ---------------------------------------------------------------------------


def test_warm_up_is_bounded_and_schedules_background_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from cloud_recommender.api.routes import finops as route

    scheduled: list[str] = []

    class _Ws:
        _discovery_cache: dict[str, object] = {}
        _uc_cache: dict[str, object] = {}
        _system_tables_cache: dict[str, object] = {}

        async def get_or_discover_workspace(self, _cid: str) -> None:
            await asyncio.sleep(30)  # a slow first discovery

    class _Refresher:
        workspace_service = _Ws()

        def touch(self, cid: str) -> None:
            scheduled.append(f"touch:{cid}")

        async def refresh_once(self, cid: str, force: bool = False) -> None:
            scheduled.append(f"refresh:{cid}:{force}")

    monkeypatch.setattr(route, "get_refresher", lambda _ws=None: _Refresher())
    monkeypatch.setattr(
        route, "get_finops_service", lambda: SimpleNamespace(workspace_service=None)
    )
    monkeypatch.setattr(route, "_FIRST_LOAD_TIMEOUT_SECONDS", 0.05)

    async def run() -> float:
        loop = asyncio.get_running_loop()
        start = loop.time()
        await route.warm_live_metadata(
            connection_id="c1",
            settings=SimpleNamespace(app_env="development"),  # type: ignore[arg-type]
        )
        elapsed = loop.time() - start
        await asyncio.sleep(0.05)  # let the scheduled background task run
        return elapsed

    elapsed = asyncio.run(run())
    assert elapsed < 1.0  # bounded wait, not the 30s discovery
    assert "touch:c1" in scheduled
    assert "refresh:c1:True" in scheduled  # slow metadata continues in the background


def test_warm_up_is_skipped_in_testing_environment() -> None:
    from types import SimpleNamespace

    from cloud_recommender.api.routes import finops as route

    asyncio.run(
        route.warm_live_metadata(
            connection_id="c1",
            settings=SimpleNamespace(app_env="testing"),  # type: ignore[arg-type]
        )
    )


# ---------------------------------------------------------------------------
# Blocking SDK work must not freeze the event loop (periodic refresh would stall the API)
# ---------------------------------------------------------------------------


def test_discovery_runs_off_the_event_loop() -> None:
    import time

    from cloud_recommender.services.databricks.discovery_service import DatabricksDiscoveryService

    service = DatabricksDiscoveryService()

    def slow_blocking(**_: object) -> DatabricksWorkspaceDiscoveryResponse:
        time.sleep(0.4)  # stands in for synchronous SDK calls
        return _failed_discovery()

    service._discover_workspace_sync = slow_blocking  # type: ignore[method-assign,assignment]

    async def run() -> int:
        ticks = 0

        async def heartbeat() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        beat = asyncio.create_task(heartbeat())
        await service.discover_workspace(
            connection_id=CONNECTION_ID,
            host="https://x",
            cloud=DatabricksCloud.AZURE,
            workspace_id=WORKSPACE_ID,
            workspace_name="x",
        )
        beat.cancel()
        return ticks

    # A blocked loop would record ~0 ticks during the 0.4 s call; a free loop records many.
    assert asyncio.run(run()) >= 8
