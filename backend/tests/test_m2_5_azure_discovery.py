"""M2.5: read-only ARM Resource Group / resource discovery (paging, empty vs forbidden, stale cache)."""

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.azure_discovery import AzureDiscoveryStatus
from cloud_recommender.services.azure import discovery_service as ds
from cloud_recommender.services.azure.discovery_service import AzureDiscoveryService

SUB = "11111111-1111-1111-1111-111111111111"


def _svc() -> AzureDiscoveryService:
    svc = AzureDiscoveryService(Settings(offline_pricing_mode=True))
    svc.azure.get_access_token = AsyncMock(return_value=("tok", "azure_cli_session"))  # type: ignore[method-assign]
    return svc


def _resp(status: int, body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("GET", "https://x"))


def _router(routes: dict[str, list[httpx.Response]]) -> Any:
    """Return an AsyncClient.get replacement answering by URL substring, in order."""

    async def fake_get(_self: Any, url: str, **_: Any) -> httpx.Response:
        for needle, queue in routes.items():
            if needle in url:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"unexpected url {url}")

    return fake_get


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    ds._LAST_GOOD.clear()
    ds._TOKEN = None


async def test_resource_groups_follow_next_link_and_report_disabled_state() -> None:
    page1 = {
        "value": [
            {"id": f"/subscriptions/{SUB}/resourceGroups/a", "name": "a", "location": "eastus"}
        ],
        "nextLink": "https://management.azure.com/next-page-2",
    }
    page2 = {
        "value": [
            {
                "id": f"/subscriptions/{SUB}/resourceGroups/b",
                "name": "b",
                "location": "centralindia",
                "properties": {"provisioningState": "Succeeded"},
                "tags": {"k": "v"},
            }
        ]
    }
    routes = {
        "next-page-2": [_resp(200, page2)],
        "resourcegroups": [_resp(200, page1)],
        f"/subscriptions/{SUB}?api-version": [_resp(200, {"state": "Disabled"})],
    }
    with patch("httpx.AsyncClient.get", _router(routes)):
        out = await _svc().list_resource_groups(SUB)
    assert out.status is AzureDiscoveryStatus.OK
    assert [g.name for g in out.items] == ["a", "b"]
    assert out.count == 2 and out.page_count == 2
    assert out.subscription_state == "Disabled" and "Disabled" in out.status_message
    assert out.items[1].tags == {"k": "v"} and out.items[1].provisioning_state == "Succeeded"


async def test_empty_is_not_a_failure() -> None:
    routes = {
        "resourcegroups": [_resp(200, {"value": []})],
        f"/subscriptions/{SUB}?api": [_resp(200, {"state": "Enabled"})],
    }
    with patch("httpx.AsyncClient.get", _router(routes)):
        out = await _svc().list_resource_groups(SUB)
    assert out.status is AzureDiscoveryStatus.EMPTY and out.count == 0 and out.stale is False


async def test_forbidden_is_classified_and_names_the_missing_role() -> None:
    err = {"error": {"code": "AuthorizationFailed", "message": "no access"}}
    routes = {"resourcegroups": [_resp(403, err)], f"/subscriptions/{SUB}?api": [_resp(403, err)]}
    with patch("httpx.AsyncClient.get", _router(routes)):
        out = await _svc().list_resource_groups(SUB)
    assert out.status is AzureDiscoveryStatus.FORBIDDEN
    assert out.count is None and out.items == []
    assert "Reader" in out.status_message and out.http_status == 403


async def test_failed_refresh_preserves_last_good_inventory_and_marks_stale() -> None:
    ok = {"value": [{"id": "/x/rg1", "name": "rg1", "location": "eastus"}]}
    routes_ok = {
        "resourcegroups": [_resp(200, ok)],
        f"/subscriptions/{SUB}?api": [_resp(200, {"state": "Enabled"})],
    }
    svc = _svc()
    with patch("httpx.AsyncClient.get", _router(routes_ok)):
        first = await svc.list_resource_groups(SUB)
    assert first.stale is False and first.last_success_at is not None

    routes_bad = {
        "resourcegroups": [_resp(500, {"error": {"code": "Internal", "message": "boom"}})],
        f"/subscriptions/{SUB}?api": [_resp(200, {"state": "Enabled"})],
    }
    with patch("httpx.AsyncClient.get", _router(routes_bad)):
        second = await svc.list_resource_groups(SUB)
    assert second.status is AzureDiscoveryStatus.ERROR
    assert second.stale is True and [g.name for g in second.items] == ["rg1"]
    assert second.last_success_at == first.last_success_at


async def test_no_identity_returns_unauthenticated_without_fabricating() -> None:
    svc = AzureDiscoveryService(Settings(offline_pricing_mode=True))
    svc.azure.get_access_token = AsyncMock(return_value=(None, "none"))  # type: ignore[method-assign]
    rgs = await svc.list_resource_groups(SUB)
    res = await svc.list_resources(SUB)
    assert (
        rgs.status is AzureDiscoveryStatus.UNAUTHENTICATED and rgs.items == [] and rgs.count is None
    )
    assert res.status is AzureDiscoveryStatus.UNAUTHENTICATED and res.items == []


async def test_resources_extract_resource_group_and_fields() -> None:
    body = {
        "value": [
            {
                "id": f"/subscriptions/{SUB}/resourceGroups/Rg-One/providers/Microsoft.Network/virtualNetworks/vn",
                "name": "vn",
                "type": "Microsoft.Network/virtualNetworks",
                "location": "centralindia",
                "provisioningState": "Succeeded",
                "createdTime": "2025-01-01T00:00:00Z",
                "tags": {"owner": "x"},
            }
        ]
    }
    routes = {
        "/resources": [_resp(200, body)],
        f"/subscriptions/{SUB}?api": [_resp(200, {"state": "Enabled"})],
    }
    with patch("httpx.AsyncClient.get", _router(routes)):
        out = await _svc().list_resources(SUB)
    item = out.items[0]
    assert out.status is AzureDiscoveryStatus.OK and out.count == 1
    assert item.resource_group == "Rg-One" and item.provisioning_state == "Succeeded"
    assert (
        item.subscription_id == SUB
        and item.tags == {"owner": "x"}
        and item.location == "centralindia"
    )


async def test_network_error_is_error_not_empty() -> None:
    async def boom(*_a: Any, **_: Any) -> httpx.Response:
        raise httpx.ConnectError("down")

    with patch("httpx.AsyncClient.get", boom):
        out = await _svc().list_resource_groups(SUB)
    assert out.status is AzureDiscoveryStatus.ERROR and out.count is None
