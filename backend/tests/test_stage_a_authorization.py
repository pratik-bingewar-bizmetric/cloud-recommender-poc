"""Stage A: simplified authorization - attribution, pricing refresh cooldown, headers, approvals.

All tokens use throw-away RSA keys; no cloud, Databricks or database access is performed (the
services behind the routes are stubbed).
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from security_fixtures import PRODUCTION_SECURITY, build_app, make_token, new_rsa_key

from cloud_recommender.api.routes.finops import get_finops_service
from cloud_recommender.api.routes.pricing import get_pricing_engine
from cloud_recommender.core.auth import AuthenticatedUser, actor_for
from cloud_recommender.core.config import Settings
from cloud_recommender.core.refresh_guard import RefreshGuard, get_pricing_refresh_guard
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService


@pytest.fixture(scope="module")
def keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    return new_rsa_key()


def make_app(keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], **settings_kw: Any) -> FastAPI:
    settings = Settings(
        _env_file=None,
        app_env="production",
        catalog_offline_mode=True,
        **{**PRODUCTION_SECURITY, **settings_kw},
    )
    return build_app(settings, keys[1])


async def post(app: FastAPI, path: str, token: str, **kwargs: Any) -> Any:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post(path, headers={"Authorization": f"Bearer {token}"}, **kwargs)


# --------------------------------------------------------------------------------------
# D4: attribution
# --------------------------------------------------------------------------------------


def test_actor_is_derived_from_token_identity() -> None:
    user = AuthenticatedUser(sub="s", oid="o", name="N", preferred_username="a@contoso.net")
    assert actor_for(user) == "a@contoso.net"
    assert actor_for(AuthenticatedUser(sub="s", oid="o", name="N")) == "N"
    assert actor_for(AuthenticatedUser(sub="s", oid="o")) == "o"
    assert actor_for(AuthenticatedUser(sub="s")) == "s"


def test_anomaly_status_audit_event_records_the_actor() -> None:
    service = FinOpsAnalyticsService()
    service.update_anomaly_status("anom-1", "Acknowledged", actor="analyst@contoso.net")
    assert service._audit_events[0].actor == "analyst@contoso.net"


@pytest.mark.asyncio
async def test_routes_attribute_actions_to_the_authenticated_user(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    app = make_app(keys)
    service = MagicMock()
    app.dependency_overrides[get_finops_service] = lambda: service
    token = make_token(keys[0], roles=[], preferred_username="analyst@contoso.net")

    await post(
        app,
        "/api/v1/finops/optimization-advisor/d1/action",
        token,
        json={"action": "Approved", "notes": "n", "actor": "spoofed@evil.test"},
    )
    await post(
        app,
        "/api/v1/finops/anomalies/a1/status",
        token,
        json={"status": "Acknowledged", "actor": "spoofed@evil.test"},
    )

    assert service.record_decision_action.call_args.kwargs["actor"] == "analyst@contoso.net"
    assert service.update_anomaly_status.call_args.kwargs["actor"] == "analyst@contoso.net"


# --------------------------------------------------------------------------------------
# Restricted: approval token and billing run
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/api/v1/finops/ingestion/approval-token", "/api/v1/finops/ingestion/run"]
)
async def test_billing_execution_path_needs_finops_admin_on_a_user_token(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], path: str
) -> None:
    app = make_app(keys)
    no_role = make_token(keys[0], roles=[])
    admin = make_token(keys[0], roles=["FinOpsAdmin"])
    daemon = make_token(keys[0], scp="", roles=["FinOpsDaemon", "FinOpsAdmin"])
    assert (await post(app, path, no_role, json=[])).status_code == 403
    assert (await post(app, path, daemon, json=[])).status_code == 403  # humans only
    assert (await post(app, path, admin, json=[])).status_code == 422  # gate passed


# --------------------------------------------------------------------------------------
# D5: pricing refresh cooldown + concurrency protection
# --------------------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_guard_enforces_cooldown_per_scope() -> None:
    clock = FakeClock()
    guard = RefreshGuard(clock=clock)
    with guard.guard("sub-a|eastus", 900):
        pass
    with pytest.raises(HTTPException) as excinfo:
        guard.acquire("sub-a|eastus", 900)
    assert excinfo.value.status_code == 429
    assert excinfo.value.headers == {"Retry-After": "900"}
    guard.acquire("sub-b|eastus", 900)  # other scope unaffected
    guard.release("sub-b|eastus")
    clock.now += 899
    with pytest.raises(HTTPException):
        guard.acquire("sub-a|eastus", 900)
    clock.now += 2
    guard.acquire("sub-a|eastus", 900)  # window elapsed
    guard.release("sub-a|eastus")


def test_guard_rejects_concurrent_refresh_for_same_scope() -> None:
    guard = RefreshGuard(clock=FakeClock())
    guard.acquire("sub-a|eastus", 0)  # cooldown disabled, still single-flight
    with pytest.raises(HTTPException) as excinfo:
        guard.acquire("sub-a|eastus", 0)
    assert excinfo.value.status_code == 409
    guard.release("sub-a|eastus")
    guard.acquire("sub-a|eastus", 0)


def test_guard_releases_in_flight_marker_when_refresh_fails() -> None:
    guard = RefreshGuard(clock=FakeClock())
    with pytest.raises(RuntimeError), guard.guard("k", 0):
        raise RuntimeError("upstream failed")
    guard.acquire("k", 0)  # not stuck "in progress"


def pricing_app(keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], **kw: Any) -> tuple[FastAPI, Any]:
    app = make_app(keys, **kw)
    engine = MagicMock()
    engine.get_price_for_service = AsyncMock(return_value=object())
    app.dependency_overrides[get_pricing_engine] = lambda: engine
    app.dependency_overrides[get_pricing_refresh_guard] = lambda: RefreshGuard()
    guard = RefreshGuard()
    app.dependency_overrides[get_pricing_refresh_guard] = lambda: guard
    return app, engine


@pytest.mark.asyncio
async def test_pricing_refresh_cooldown_is_15_minutes_by_default_and_per_scope(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    assert Settings(_env_file=None, app_env="testing").pricing_refresh_cooldown_seconds == 900
    app, engine = pricing_app(keys)
    token = make_token(keys[0], roles=[])  # ordinary user, no role

    first = await post(app, "/api/v1/pricing/refresh", token, json={"subscription_id": "sub-a"})
    again = await post(app, "/api/v1/pricing/refresh", token, json={"subscription_id": "sub-a"})
    other = await post(app, "/api/v1/pricing/refresh", token, json={"subscription_id": "sub-b"})

    assert first.status_code == 200
    assert again.status_code == 429
    assert again.json()["error"]["message"]["error_code"] == "REFRESH_COOLDOWN"
    assert int(again.headers["retry-after"]) > 0
    assert other.status_code == 200
    assert (
        engine.get_price_for_service.await_count == 14
    )  # 7 default services x 2 allowed refreshes


@pytest.mark.asyncio
async def test_pricing_refresh_cooldown_is_configurable(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    app, _ = pricing_app(keys, pricing_refresh_cooldown_seconds=0)
    token = make_token(keys[0], roles=[])
    for _ in range(2):
        assert (await post(app, "/api/v1/pricing/refresh", token, json={})).status_code == 200


@pytest.mark.asyncio
async def test_concurrent_pricing_refresh_is_rejected_with_409(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    app, engine = pricing_app(keys, pricing_refresh_cooldown_seconds=0)
    gate = asyncio.Event()
    entered = asyncio.Event()

    async def slow_refresh(*_a: Any, **_k: Any) -> object:
        entered.set()
        await gate.wait()
        return object()

    engine.get_price_for_service = AsyncMock(side_effect=slow_refresh)
    token = make_token(keys[0], roles=[])

    first = asyncio.create_task(post(app, "/api/v1/pricing/refresh", token, json={}))
    try:
        # Wait until the first request is PROVABLY inside the guarded section. A fixed sleep let
        # the second request win on a loaded machine; it then blocked on ``gate`` forever (the
        # gate is only released after the second request returns) and hung the whole suite.
        await asyncio.wait_for(entered.wait(), timeout=30)
        second = await asyncio.wait_for(
            post(app, "/api/v1/pricing/refresh", token, json={}), timeout=30
        )
    finally:
        gate.set()  # always release the first request, even if an assertion above fails
    first_response = await asyncio.wait_for(first, timeout=30)

    assert second.status_code == 409
    assert second.json()["error"]["message"]["error_code"] == "REFRESH_IN_PROGRESS"
    assert first_response.status_code == 200


# --------------------------------------------------------------------------------------
# Error headers are preserved (Retry-After, WWW-Authenticate)
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_carries_www_authenticate_header(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    app = make_app(keys)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/api/v1/connections")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
