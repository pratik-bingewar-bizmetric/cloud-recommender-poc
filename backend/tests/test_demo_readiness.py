"""Demo-readiness tests: live-data registries, ARM pagination, monitoring probes, completeness.

Fully offline: HTTP is served by httpx.MockTransport; no cloud call is made.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from cloud_recommender.core.config import Settings
from cloud_recommender.services.configuration.configuration_service import ConfigurationService
from cloud_recommender.services.databricks.discovery_service import DatabricksDiscoveryService
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService
from cloud_recommender.services.inventory import azure_inventory as az_module
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
from cloud_recommender.services.monitoring import capability_probe as probe_module
from cloud_recommender.services.monitoring.capability_probe import (
    classify_http_status,
    clear_probe_cache,
    probe_azure_monitoring,
)
from tests.fixtures.live_inventory import CONNECTION_ID, _res, make_analytics_service


def _client_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    real = httpx.AsyncClient

    def factory(*_a: Any, **kw: Any) -> httpx.AsyncClient:
        kw.pop("timeout", None)
        return real(transport=httpx.MockTransport(handler), **kw)

    return factory


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(az_module.asyncio, "sleep", no_sleep)
    clear_probe_cache()


def _service() -> AzureInventoryService:
    return AzureInventoryService(settings=Settings(allow_demo_fixtures=False))


# ====================================================== ARM pagination (P4)


async def test_arm_pagination_follows_every_next_link_until_the_source_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        "https://m/a": {"value": [{"id": 1}], "nextLink": "https://m/b"},
        "https://m/b": {"value": [], "nextLink": "https://m/c"},  # ARM may return empty pages
        "https://m/c": {"value": [{"id": 2}, {"id": 3}]},
    }

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[str(req.url).split("?")[0]])

    monkeypatch.setattr(az_module.httpx, "AsyncClient", _client_factory(handler))
    svc = _service()
    items = await svc._arm_get_all("https://m/a", "tok")
    assert [i["id"] for i in items] == [1, 2, 3]
    assert svc.pagination_log[-1]["pages"] == 3
    assert svc.pagination_log[-1]["records"] == 3 and svc.pagination_log[-1]["complete"] is True


async def test_arm_failure_is_reported_incomplete_with_the_exact_status_and_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "page2" in str(req.url):
            return httpx.Response(403, text="AuthorizationFailed: missing Reader")
        return httpx.Response(200, json={"value": [{"id": 1}], "nextLink": "https://m/page2"})

    monkeypatch.setattr(az_module.httpx, "AsyncClient", _client_factory(handler))
    svc = _service()
    items = await svc._arm_get_all("https://m/a", "tok")
    entry = svc.pagination_log[-1]
    assert len(items) == 1  # what was retrieved is kept ...
    assert entry["complete"] is False  # ... but never presented as complete
    assert entry["http_status"] == 403 and "AuthorizationFailed" in entry["error"]
    assert entry["records"] == 1


async def test_arm_transient_errors_are_retried_with_a_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"value": [{"id": 1}]})

    monkeypatch.setattr(az_module.httpx, "AsyncClient", _client_factory(handler))
    svc = _service()
    assert len(await svc._arm_get_all("https://m/a", "tok")) == 1
    assert calls["n"] == 3 and svc.pagination_log[-1]["complete"] is True


async def test_arm_persistent_throttling_stops_after_bounded_retries_and_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, text="slow down", headers={"Retry-After": "1"})

    monkeypatch.setattr(az_module.httpx, "AsyncClient", _client_factory(handler))
    svc = _service()
    assert await svc._arm_get_all("https://m/a", "tok") == []
    assert calls["n"] == svc._ARM_MAX_RETRIES + 1
    assert svc.pagination_log[-1]["complete"] is False
    assert svc.pagination_log[-1]["http_status"] == 429


async def test_arm_repeating_next_link_cannot_loop_forever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [{"id": 1}], "nextLink": "https://m/a"})

    monkeypatch.setattr(az_module.httpx, "AsyncClient", _client_factory(handler))
    svc = _service()
    items = await svc._arm_get_all("https://m/a", "tok")
    assert len(items) == 1
    assert svc.pagination_log[-1]["complete"] is False
    assert "repeated nextLink" in svc.pagination_log[-1]["error"]


async def test_arm_network_failure_is_incomplete_not_empty_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(az_module.httpx, "AsyncClient", _client_factory(handler))
    svc = _service()
    assert await svc._arm_get_all("https://m/a", "tok") == []
    assert svc.pagination_log[-1]["complete"] is False
    assert svc.pagination_log[-1]["http_status"] is None
    assert "ConnectError" in svc.pagination_log[-1]["error"]


# ====================================================== scope discovery completeness (P5)


class _FakeAzure:
    """Stands in for AzureInventoryService; records one failed read."""

    def __init__(self, *, fail: bool) -> None:
        self.pagination_log: list[dict[str, Any]] = []
        self.fail = fail

    async def get_access_token(self) -> tuple[str, str]:
        return "tok", "azure_cli_session"

    async def list_subscriptions(self, token: str | None = None) -> list[Any]:  # noqa: ARG002
        from cloud_recommender.schemas.inventory import CloudProvider, CloudScopeSummary

        return [
            CloudScopeSummary(
                provider=CloudProvider.AZURE,
                scope_id="sub-1",
                display_name="Sub",
                tenant_or_org_id="t",
                parent_scope_id=None,
                state="Enabled",
                data_source="live_authenticated",
            )
        ]

    async def list_resource_groups(self, *_a: Any) -> list[dict[str, Any]]:
        return [{"name": "rg", "id": "/subscriptions/sub-1/resourceGroups/rg", "location": "x"}]

    async def list_databricks_workspaces(self, *_a: Any) -> list[dict[str, Any]]:
        return []

    async def list_resources(self, *_a: Any) -> list[dict[str, Any]]:
        self.pagination_log.append(
            {
                "url": "https://m/resources",
                "pages": 1,
                "records": 0,
                "complete": not self.fail,
                "http_status": 403 if self.fail else 200,
                "error": "AuthorizationFailed" if self.fail else None,
            }
        )
        return []


async def test_scope_discovery_reports_complete_only_when_every_read_finished() -> None:
    ok = ConfigurationService(
        azure_service=_FakeAzure(fail=False),  # type: ignore[arg-type]
        settings=Settings(allow_demo_fixtures=False),
    )
    out = await ok.discover_scopes("c", provider="azure")
    assert out.completeness == "COMPLETE" and out.source_errors == []


async def test_scope_discovery_surfaces_the_exact_failed_read_as_incomplete() -> None:
    bad = ConfigurationService(
        azure_service=_FakeAzure(fail=True),  # type: ignore[arg-type]
        settings=Settings(allow_demo_fixtures=False),
    )
    out = await bad.discover_scopes("c", provider="azure")
    assert out.completeness == "INCOMPLETE" and "INCOMPLETE" in out.status_message
    assert out.source_errors[0]["http_status"] == 403
    assert out.tree  # accessible data is still shown


async def test_unauthenticated_scope_discovery_reports_unknown_completeness() -> None:
    from unittest.mock import AsyncMock

    azure = AsyncMock(spec=AzureInventoryService)
    azure.get_access_token.return_value = (None, "none")
    cfg = ConfigurationService(azure_service=azure, settings=Settings(allow_demo_fixtures=False))
    out = await cfg.discover_scopes("c", provider="azure")
    assert out.status == "authentication_required" and out.completeness == "UNKNOWN"


# ====================================================== monitoring probes (P3)


def test_http_outcomes_are_classified_honestly() -> None:
    assert classify_http_status(200, 3) == "AVAILABLE"
    assert classify_http_status(200, 0) == "NO_DATA"
    assert classify_http_status(200, None) == "AVAILABLE"
    assert classify_http_status(401) == "ACCESS_DENIED"
    assert classify_http_status(403) == "ACCESS_DENIED"
    assert classify_http_status(404) == "UNAVAILABLE"
    assert classify_http_status(500) == "ERROR"
    assert classify_http_status(None) == "ERROR"


class _TokenService:
    def __init__(self, token: str | None, resources: list[dict[str, Any]] | None = None) -> None:
        self.token = token
        self.pagination_log: list[dict[str, Any]] = []
        self._resources = resources or []

    async def get_access_token(self) -> tuple[str | None, str]:
        return self.token, "azure_cli_session" if self.token else "none"

    async def list_resources(self, *_a: Any) -> list[dict[str, Any]]:
        self.pagination_log.append(
            {"pages": 1, "records": len(self._resources), "complete": True, "http_status": 200}
        )
        return self._resources


def _arm(handler_map: dict[str, tuple[int, Any]]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        for needle, (code, body) in handler_map.items():
            if needle in url:
                if isinstance(body, str):
                    return httpx.Response(code, text=body)
                return httpx.Response(code, json=body)
        return httpx.Response(404, text="not mapped")

    return handler


async def test_probe_without_identity_states_not_authenticated_and_invents_nothing() -> None:
    out = await probe_azure_monitoring(Settings(), _TokenService(None))  # type: ignore[arg-type]
    assert out["status"] == "not_authenticated" and out["is_live"] is False
    assert out["capabilities"] == [] and out["probes"] == [] and out["retention_days"] is None


async def test_probe_reports_each_capability_with_exact_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _arm(
        {
            "metricDefinitions": (200, {"value": [{"name": "m1"}, {"name": "m2"}]}),
            "eventtypes/management": (403, "AuthorizationFailed: needs Monitoring Reader"),
            "providers/Microsoft.Insights?": (200, {"registrationState": "Registered"}),
            "/subscriptions?": (
                200,
                {"value": [{"subscriptionId": "s1", "state": "Enabled"}]},
            ),
        }
    )
    monkeypatch.setattr(probe_module.httpx, "AsyncClient", _client_factory(handler))
    service = _TokenService("tok", [{"id": "/subscriptions/s1/resourceGroups/r/x", "type": "T/x"}])
    out = await probe_azure_monitoring(Settings(), service)  # type: ignore[arg-type]
    by_name = {p["name"]: p for p in out["probes"]}
    assert by_name["subscriptions"]["status"] == "AVAILABLE"
    assert by_name["activity_log"]["status"] == "ACCESS_DENIED"
    assert by_name["activity_log"]["http_status"] == 403
    assert "Monitoring Reader" in by_name["activity_log"]["required_permission"]
    assert "AuthorizationFailed" in by_name["activity_log"]["message"]
    assert by_name["metric_definitions"]["status"] == "AVAILABLE"
    assert by_name["metric_definitions"]["record_count"] == 2
    assert by_name["cost_management"]["status"] == "NOT_PROBED"
    assert out["retention_days"] is None  # never invented
    assert "activity_log" not in out["capabilities"]
    assert out["status"] == "connected" and out["is_live"] is True


async def test_probe_with_no_resources_reports_no_data_not_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _arm(
        {
            "providers/Microsoft.Insights?": (200, {"registrationState": "Registered"}),
            "eventtypes/management": (200, {"value": []}),
            "/subscriptions?": (200, {"value": [{"subscriptionId": "s1", "state": "Enabled"}]}),
        }
    )
    monkeypatch.setattr(probe_module.httpx, "AsyncClient", _client_factory(handler))
    out = await probe_azure_monitoring(Settings(), _TokenService("tok", []))  # type: ignore[arg-type]
    by_name = {p["name"]: p for p in out["probes"]}
    assert by_name["activity_log"]["status"] == "NO_DATA"
    assert by_name["resources"]["status"] == "NO_DATA"
    assert "metric_definitions" not in by_name  # nothing to probe: not invented


def test_monitoring_sources_route_never_reads_credentials_from_settings() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1] / "src/cloud_recommender/api/routes/monitoring.py"
    ).read_text(encoding="utf-8")
    assert "azure_subscription_id and settings.azure_tenant_id" not in src
    assert "simulation_fixture" not in src
    assert 'retention_days": 90' not in src


# ====================================================== P2: no hardcoded registries


def test_analytics_has_no_hardcoded_resource_or_workspace_registries() -> None:
    for name in (
        "KNOWN_WAREHOUSES",
        "KNOWN_CLUSTERS",
        "KNOWN_SERVING_ENDPOINTS",
        "KNOWN_APPS",
        "HISTORICAL_FIXTURE_ENDPOINTS",
        "AUTHORIZED_WORKSPACES",
    ):
        assert not hasattr(FinOpsAnalyticsService, name), name


def test_resource_existence_comes_from_live_discovery_not_a_fixed_list() -> None:
    service = make_analytics_service(with_billing=False, with_inventory=True)
    # present in (fake) live discovery -> resolves
    assert service._resolve_resource_filter("05ed10a52697a344", "warehouse") == ("warehouse", False)
    # a resource that was previously in the hardcoded list but is not discovered is unknown
    assert service._resolve_resource_filter("wonder-cement-app", "app") == (None, True)
    # newly discovered resources are recognised without any code change
    service.workspace_service._discovery_cache[CONNECTION_ID].resources.append(
        _res("brand-new-endpoint", "brand-new-endpoint", "serving_endpoint", "READY")
    )
    assert service._resolve_resource_filter("brand-new-endpoint", "serving") == ("serving", False)


def test_scope_validation_uses_the_workspace_registry_only() -> None:
    service = make_analytics_service(with_billing=False, with_inventory=False)
    allowed = service._get_authorized_workspaces()
    assert "all" in allowed
    assert {c.workspace_id for c in service.workspace_service.list_connections()} <= allowed
    with pytest.raises(ValueError):
        service.validate_scope("999999999999999")


# ====================================================== P4: Databricks discovery bound


def test_databricks_collection_reads_every_item_and_flags_only_the_safety_bound() -> None:
    svc = DatabricksDiscoveryService.__new__(DatabricksDiscoveryService)
    items, more = svc._collect_sdk_iterable(iter(range(5_000)), "api")
    assert len(items) == 5_000 and more is False  # no longer cut at 500
    items, more = svc._collect_sdk_iterable(iter(range(30)), "api", max_items=10)
    assert len(items) == 10 and more is True  # a hit bound is reported, never hidden


async def test_probe_cache_serves_repeat_calls_without_new_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    async def fake_uncached(_s: Settings, _svc: Any) -> dict[str, Any]:
        calls["n"] += 1
        return {"status": "connected", "probes": []}

    monkeypatch.setattr(probe_module, "_probe_azure_monitoring_uncached", fake_uncached)
    await probe_azure_monitoring(Settings())
    await probe_azure_monitoring(Settings())
    assert calls["n"] == 1
    clear_probe_cache()
    await probe_azure_monitoring(Settings())
    assert calls["n"] == 2


# ====================================================== ingestion providers never fabricate


def _scope(resource_ids: list[str]) -> Any:
    import uuid

    from cloud_recommender.schemas.ingestion import IngestionScope

    return IngestionScope(
        connection_id="c",
        provider="azure",
        configuration_id=uuid.uuid4(),
        configuration_version=1,
        effective_resource_ids=resource_ids,
    )


RID = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"


async def test_azure_ingestion_without_identity_fails_instead_of_fabricating() -> None:
    from unittest.mock import AsyncMock

    from cloud_recommender.schemas.ingestion import ResourceIngestionStatus
    from cloud_recommender.services.ingestion.providers.azure import AzureProviderIngestor

    azure = AsyncMock(spec=AzureInventoryService)
    azure.get_access_token.return_value = (None, "none")
    ingestor = AzureProviderIngestor(
        azure_service=azure, settings=Settings(allow_demo_fixtures=False)
    )
    (res,) = await ingestor.ingest_scope(_scope([RID]))
    assert res.status == ResourceIngestionStatus.FAILED
    assert "authentication required" in (res.error_message or "").lower()
    assert res.cost_records == [] and res.metric_records == [] and res.inventory_payload is None


async def test_azure_live_ingestion_reports_only_identifiers_never_invented_cost_or_metrics() -> (
    None
):
    from unittest.mock import AsyncMock

    from cloud_recommender.services.ingestion.providers.azure import AzureProviderIngestor

    azure = AsyncMock(spec=AzureInventoryService)
    azure.get_access_token.return_value = ("tok", "azure_cli_session")
    ingestor = AzureProviderIngestor(
        azure_service=azure, settings=Settings(allow_demo_fixtures=False)
    )
    (res,) = await ingestor.ingest_scope(_scope([RID]))
    assert res.inventory_extracted is True and res.inventory_payload["name"] == "vm1"
    assert res.cost_extracted is False and res.metrics_extracted is False
    assert res.cost_records == [] and res.metric_records == []


async def test_azure_demo_fixture_is_opt_in_and_labelled() -> None:
    from unittest.mock import AsyncMock

    from cloud_recommender.services.ingestion.providers.azure import AzureProviderIngestor

    azure = AsyncMock(spec=AzureInventoryService)
    azure.get_access_token.return_value = (None, "none")
    ingestor = AzureProviderIngestor(
        azure_service=azure, settings=Settings(allow_demo_fixtures=True)
    )
    (res,) = await ingestor.ingest_scope(_scope([RID]))
    assert res.inventory_payload["data_source"] == "demo_fixture"


async def test_gcp_ingestion_is_skipped_not_fabricated_by_default() -> None:
    from cloud_recommender.schemas.ingestion import ResourceIngestionStatus
    from cloud_recommender.services.ingestion.providers.gcp import GcpProviderIngestor

    ingestor = GcpProviderIngestor(settings=Settings(allow_demo_fixtures=False))
    (res,) = await ingestor.ingest_scope(_scope(["projects/p/instances/vm-1"]))
    assert res.status == ResourceIngestionStatus.SKIPPED
    assert res.cost_records == [] and res.metric_records == []
