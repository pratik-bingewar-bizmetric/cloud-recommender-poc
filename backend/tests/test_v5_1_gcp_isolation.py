"""V5.1 financial integrity: missing/expired GCP credentials never silently return fixture inventory."""

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.common import CloudProvider
from cloud_recommender.schemas.inventory import CloudScopeSummary
from cloud_recommender.services.configuration.configuration_service import ConfigurationService
from cloud_recommender.services.connections.connection_service import ConnectionService
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService

REF = "smart-expense-gcp-prod"


def _settings(**kw: object) -> Settings:
    base: dict[str, object] = {"offline_pricing_mode": True, "allow_demo_fixtures": False}
    base.update(kw)
    return Settings(**base)  # type: ignore[arg-type]


def _no_token(svc: GcpInventoryService) -> Any:
    return patch.object(
        svc, "get_inventory_access_token", AsyncMock(return_value=(None, "unauthenticated"))
    )


def _resp(status: int, body: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.Response(
        status, json=body or {}, request=httpx.Request("GET", "https://cloudresourcemanager.test")
    )


def _http(*responses: httpx.Response) -> Any:
    queue = list(responses)

    async def fake_get(*_a: Any, **_k: Any) -> httpx.Response:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return patch("httpx.AsyncClient.get", fake_get)


# --------------------------------------------------------------------------- missing credentials
async def test_missing_credentials_list_projects_fails_closed() -> None:
    svc = GcpInventoryService(settings=_settings())
    with _no_token(svc), pytest.raises(HTTPException) as exc:
        await svc.list_projects()
    assert exc.value.status_code == 401
    assert "GCP authentication required" in str(exc.value.detail)


@pytest.mark.parametrize("project", [REF, "my-custom-project"])
async def test_missing_credentials_analyze_project_fails_closed(project: str) -> None:
    svc = GcpInventoryService(settings=_settings())
    with _no_token(svc), pytest.raises(HTTPException) as exc:
        await svc.analyze_project(project_id=project)
    assert exc.value.status_code == 401
    assert "mock_fixture" not in str(exc.value.detail)


async def test_connection_status_does_not_promise_fixture_data() -> None:
    svc = GcpInventoryService(settings=_settings())
    with _no_token(svc):
        status = await svc.get_connection_status()
    assert status.inventory_auth_ready is False
    assert "No fixture data is substituted" in status.status_message


# ---------------------------------------------------------------------- explicit demo opt-in only
async def test_explicit_opt_in_still_returns_labelled_fixture() -> None:
    svc = GcpInventoryService(settings=_settings(allow_demo_fixtures=True))
    with _no_token(svc):
        projects = await svc.list_projects()
        analysis = await svc.analyze_project(project_id=REF)
    assert [p.data_source for p in projects] == ["mock_fixture"]
    assert analysis.data_source == "mock_fixture"


# -------------------------------------------------------------- expired / invalid / failing credentials
@pytest.mark.parametrize("opt_in", [False, True])
async def test_expired_token_returns_explicit_401_even_with_opt_in(opt_in: bool) -> None:
    svc = GcpInventoryService(settings=_settings(allow_demo_fixtures=opt_in))
    with _http(_resp(401)), pytest.raises(HTTPException) as exc:
        await svc.list_projects(token="expired-token")
    assert exc.value.status_code == 401
    assert "expired" in str(exc.value.detail).lower()


async def test_forbidden_returns_explicit_403() -> None:
    svc = GcpInventoryService(settings=_settings())
    with _http(_resp(403)), pytest.raises(HTTPException) as exc:
        await svc.list_projects(token="t")
    assert exc.value.status_code == 403


async def test_upstream_failure_is_an_error_not_a_fixture() -> None:
    svc = GcpInventoryService(settings=_settings())
    with _http(_resp(500)), pytest.raises(HTTPException) as exc:
        await svc.list_projects(token="t")
    assert exc.value.status_code == 502
    assert "no fixture data is substituted" in str(exc.value.detail)


async def test_authorized_but_empty_project_list_is_not_replaced_by_fixture() -> None:
    for opt_in in (False, True):
        svc = GcpInventoryService(settings=_settings(allow_demo_fixtures=opt_in))
        with _http(_resp(200, {"projects": []})):
            assert await svc.list_projects(token="t") == []


# ------------------------------------------------------------------ legitimate live retrieval intact
async def test_live_project_listing_still_works() -> None:
    svc = GcpInventoryService(settings=_settings())
    body = {"projects": [{"projectId": "live-proj", "displayName": "Live", "state": "ACTIVE"}]}
    with _http(_resp(200, body)):
        projects = await svc.list_projects(token="valid-token")
    assert [(p.scope_id, p.data_source) for p in projects] == [("live-proj", "live_authenticated")]


async def test_reference_project_id_with_token_goes_live_not_fixture() -> None:
    svc = GcpInventoryService(settings=_settings())
    live = AsyncMock(return_value="LIVE-RESULT")
    with (
        patch.object(
            svc, "get_inventory_access_token", AsyncMock(return_value=("tok", "gcloud_adc_session"))
        ),
        patch.object(svc, "_analyze_live_project", live),
        patch.object(svc, "_get_reference_fixture_analysis", AsyncMock()) as fixture,
    ):
        result = await svc.analyze_project(project_id=REF)
    assert result == "LIVE-RESULT"
    live.assert_awaited_once()
    fixture.assert_not_awaited()


# ----------------------------------------------------------------------------- dependent services
async def test_connection_list_has_no_gcp_reference_connection_without_credentials() -> None:
    settings = _settings()
    gcp = GcpInventoryService(settings=settings)
    az = AzureInventoryService(settings=settings)
    svc = ConnectionService(settings=settings, azure_service=az, gcp_service=gcp)
    with (
        patch.object(az, "get_access_token", AsyncMock(return_value=(None, "none"))),
        _no_token(gcp),
    ):
        connections = await svc.list_connections()
    assert not any(c.provider == "gcp" and c.auth_method == "mock_fixture" for c in connections)
    assert not any(c.id == "gcp-smart-expense-prod" for c in connections)


async def test_live_gcp_discovery_tree_has_no_invented_assets() -> None:
    settings = _settings()
    gcp = GcpInventoryService(settings=settings)
    cfg = ConfigurationService(settings=settings, gcp_service=gcp)
    live = CloudScopeSummary(
        provider=CloudProvider.GCP,
        scope_id="live-proj",
        display_name="Live",
        state="ACTIVE",
        data_source="live_authenticated",
    )
    with (
        patch.object(
            gcp, "get_inventory_access_token", AsyncMock(return_value=("t", "gcloud_adc_session"))
        ),
        patch.object(gcp, "list_projects", AsyncMock(return_value=[live])),
    ):
        out = await cfg.discover_scopes("gcp-live", provider="gcp")
    assert out.total_discovered_resources == 0
    assert out.tree[0].children == []


async def test_gcp_discovery_without_credentials_reports_failure_not_fixture_tree() -> None:
    settings = _settings()
    gcp = GcpInventoryService(settings=settings)
    cfg = ConfigurationService(settings=settings, gcp_service=gcp)
    with _no_token(gcp):
        out = await cfg.discover_scopes("gcp-x", provider="gcp")
    assert out.status != "ready"
    assert out.tree == []
