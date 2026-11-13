"""V5.1 financial integrity: expired/missing Azure authentication never activates fixtures."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.main import create_app
from cloud_recommender.services.connections.connection_service import ConnectionService
from cloud_recommender.services.inventory.azure_inventory import (
    AzureAuthenticationRequired,
    AzureInventoryService,
)

SUB = "11111111-1111-1111-1111-111111111111"


def _settings(**kw: object) -> Settings:
    base: dict[str, object] = {"offline_pricing_mode": True, "allow_demo_fixtures": False}
    base.update(kw)
    return Settings(**base)  # type: ignore[arg-type]


def _unauthenticated(svc: AzureInventoryService) -> object:
    return patch.object(svc, "get_access_token", AsyncMock(return_value=(None, "none")))


def test_fixtures_are_off_unless_explicitly_enabled() -> None:
    assert Settings.model_fields["allow_demo_fixtures"].default is False


async def test_list_subscriptions_fails_closed_without_identity() -> None:
    svc = AzureInventoryService(settings=_settings())
    with _unauthenticated(svc), pytest.raises(AzureAuthenticationRequired):
        await svc.list_subscriptions()


async def test_analyze_subscription_fails_closed_without_identity() -> None:
    svc = AzureInventoryService(settings=_settings())
    with _unauthenticated(svc), pytest.raises(AzureAuthenticationRequired):
        await svc.analyze_subscription(subscription_id=SUB)


async def test_opt_in_still_returns_labelled_fixture() -> None:
    svc = AzureInventoryService(settings=_settings(allow_demo_fixtures=True))
    with _unauthenticated(svc):
        subs = await svc.list_subscriptions()
        analysis = await svc.analyze_subscription(subscription_id=SUB)
    assert subs[0].data_source == "mock_fixture"
    assert analysis.data_source == "mock_fixture"


async def test_authorized_but_empty_subscription_is_not_replaced_by_fixture() -> None:
    """Empty (or forbidden) ARM listings must stay empty/live, never swap in fixture resources."""
    svc = AzureInventoryService(settings=_settings())
    with (
        patch.object(svc, "get_access_token", AsyncMock(return_value=("tok", "azure_cli_session"))),
        patch.object(svc, "list_management_groups", AsyncMock(return_value=[])),
        patch.object(svc, "list_resource_groups", AsyncMock(return_value=[])),
        patch.object(svc, "list_resources", AsyncMock(return_value=[])),
        patch.object(svc, "list_subscriptions", AsyncMock(return_value=[])),
    ):
        analysis = await svc.analyze_subscription(subscription_id=SUB)
    assert analysis.data_source != "mock_fixture"
    assert all(r.origin != "mock_fixture" for r in analysis.resources)
    assert "Benchmark Simulation" not in (analysis.scope_name or "")


async def test_connection_list_has_no_reference_connection_when_unauthenticated() -> None:
    settings = _settings()
    az = AzureInventoryService(settings=settings)
    svc = ConnectionService(settings=settings, azure_service=az)
    with (
        patch.object(az, "get_access_token", AsyncMock(return_value=(None, "none"))),
        patch.object(
            svc.gcp_service, "get_inventory_access_token", AsyncMock(return_value=(None, "none"))
        ),
    ):
        connections = await svc.list_connections()
    assert all(c.auth_method != "simulation_fixture" for c in connections if c.provider == "azure")
    assert not any(c.id == "azure-ref-sub-prod" for c in connections)


async def test_api_returns_401_not_fixture_when_azure_auth_expired() -> None:
    settings = _settings()
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    transport = httpx.ASGITransport(app=app)
    with patch.object(
        AzureInventoryService, "get_access_token", AsyncMock(return_value=(None, "none"))
    ):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            subs = await client.get("/api/v1/inventory/azure/subscriptions")
            analyze = await client.post("/api/v1/inventory/azure/analyze", json={"scope_id": SUB})
    for resp in (subs, analyze):
        assert resp.status_code == 401
        body = resp.json()["error"]
        assert body["type"] == "azure_authentication_required"
        assert "az login" in body["message"]
        assert "mock_fixture" not in resp.text
