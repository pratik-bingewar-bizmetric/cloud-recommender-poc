"""Route authorization policy sweep (simplified model: public / user / restricted / daemon).

Guards against newly introduced routes that bypass authentication or the operation policy. The
sweep inspects the live OpenAPI schema of the real application and checks, for EVERY operation:

1. No token -> 401 (except a frozen public allow-list).
2. A scoped user without roles: non-GET operations outside the frozen user list -> 403
   (restricted by default); operations in the user list are authorized.
3. A daemon (application-only) token: 403 for everything except the frozen daemon list.

Probes use an invalid (non-object) JSON body so body-bearing operations stop at request
validation (422), and the few user operations without a body run against stubbed services, so no
real handler reaches a cloud, Databricks or database resource.
"""

import importlib
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from security_fixtures import (
    APPROVED_CLIENT_ID,
    AUDIENCE,
    TENANT_ID,
    build_app,
    make_token,
    new_rsa_key,
)

from cloud_recommender.api.routes.databricks import get_workspace_service
from cloud_recommender.api.routes.finops import get_billing_service, get_finops_service
from cloud_recommender.api.routes.pricing import get_pricing_engine
from cloud_recommender.core.auth import (
    DAEMON_ALLOWED_ENDPOINTS,
    ROLE_FINOPS_DAEMON,
    USER_NON_GET_ENDPOINTS,
    enforce_route_policy,
)
from cloud_recommender.core.config import Settings

# Deliberately public operations. Adding to this set requires a conscious security review.
PUBLIC_OPERATIONS = frozenset(
    {
        ("GET", "/"),
        ("GET", "/health"),
        ("GET", "/health/ready"),
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/health/ready"),
        ("GET", "/api/v1/catalog/services"),
        ("GET", "/api/v1/catalog/services/{provider}/{service_id}"),
        ("GET", "/api/v1/catalog/services/{service_id}"),
    }
)

# Non-GET operations open to any authenticated user (class U). Frozen: changing it needs review.
USER_NON_GET_OPERATIONS = frozenset(
    {
        ("POST", "/api/v1/analysis/requirements"),
        ("POST", "/api/v1/architecture/generate"),
        ("POST", "/api/v1/finops/forecast-budgets/simulate"),
        ("POST", "/api/v1/inventory/azure/analyze"),
        ("POST", "/api/v1/inventory/gcp/analyze"),
        ("POST", "/api/v1/inventory/compare"),
        ("POST", "/api/v1/monitoring/overview"),
        ("POST", "/api/v1/monitoring/resource"),
        ("POST", "/api/v1/monitoring/logs"),
        ("POST", "/api/v1/monitoring/token-economics"),
        ("POST", "/api/v1/pricing/simulate"),
        ("POST", "/api/v1/databricks/connections/{connection_id}/test"),
        ("POST", "/api/v1/databricks/connections/{connection_id}/discovery/refresh"),
        ("POST", "/api/v1/finops/ingestion/validate"),
        ("POST", "/api/v1/finops/ingestion/preview"),
        ("POST", "/api/v1/finops/optimization-advisor/{decision_id}/action"),
        ("POST", "/api/v1/finops/anomalies/{anomaly_id}/status"),
        ("POST", "/api/v1/pricing/refresh"),
        # live Azure connection (owner-bound sessions; ownership enforced by the session store)
        ("POST", "/api/v1/azure/connections"),
        ("POST", "/api/v1/azure/connections/{connection_id}/validate"),
        ("DELETE", "/api/v1/azure/connections/{connection_id}"),
    }
)

# Restricted (FinOpsAdmin) operations: everything else that is not GET.
RESTRICTED_OPERATIONS = frozenset(
    {
        ("POST", "/api/v1/configuration"),
        ("POST", "/api/v1/connections"),
        ("POST", "/api/v1/connections/validate"),
        ("POST", "/api/v1/finops/ingestion/run"),
        ("POST", "/api/v1/finops/ingestion/approval-token"),
        ("POST", "/api/v1/ingestion/{connection_id}/runs"),
        ("POST", "/api/v1/ingestion/runs/{run_id}/retry"),
    }
)

# Operations an application-only (daemon) token may call: read-only organization status.
DAEMON_OPERATIONS = frozenset(
    {
        ("GET", "/api/v1/databricks/connections"),
        ("GET", "/api/v1/databricks/connections/{connection_id}/health"),
        ("GET", "/api/v1/finops/ingestion/status"),
        ("GET", "/api/v1/finops/ingestion/runs"),
    }
)

ROUTE_MODULES = (
    "analysis architecture azure_live catalog configuration connections databricks finops health "
    "ingestion inventory monitoring pricing"
).split()


def policy_settings() -> Settings:
    # Non-production so that /openapi.json is served for enumeration; the authorization policy
    # itself is environment independent.
    return Settings(
        _env_file=None,
        app_env="testing",
        catalog_offline_mode=True,
        entra_auth_enabled=True,
        entra_tenant_id=TENANT_ID,
        entra_audience=AUDIENCE,
        entra_allowed_client_ids=[APPROVED_CLIENT_ID],
        dev_auth_enabled=False,
    )


@pytest.fixture(scope="module")
def key_pair() -> Any:
    return new_rsa_key()


@pytest.fixture
def app(key_pair: Any) -> FastAPI:
    return build_app(policy_settings(), key_pair[1])


def stub_services(app: FastAPI) -> None:
    """Stub the services behind user operations that have no request body."""
    stub = MagicMock()
    stub.test_connection = AsyncMock(return_value={})
    stub.get_or_discover_workspace = AsyncMock(return_value={})
    app.dependency_overrides[get_workspace_service] = lambda: stub
    app.dependency_overrides[get_billing_service] = lambda: MagicMock()
    app.dependency_overrides[get_finops_service] = lambda: MagicMock()
    app.dependency_overrides[get_pricing_engine] = lambda: MagicMock()


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


async def operations(client: AsyncClient) -> list[tuple[str, str]]:
    spec = (await client.get("/openapi.json")).json()
    return [
        (method.upper(), path)
        for path, item in spec["paths"].items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    ]


async def find_unauthenticated(app: FastAPI) -> list[tuple[str, str]]:
    """Operations answering a tokenless request with anything but 401 (excluding public ones)."""
    offenders: list[tuple[str, str]] = []
    transport = ASGITransport(app=app)
    with patch(
        "cloud_recommender.api.routes.health.check_db_health",
        new=AsyncMock(return_value={"status": "connected"}),
    ):
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            for method, path in await operations(client):
                if (method, path) in PUBLIC_OPERATIONS:
                    continue
                response = await client.request(method, concrete(path), content="[]")
                if response.status_code != 401:
                    offenders.append((method, path))
    return offenders


@pytest.mark.asyncio
async def test_every_operation_requires_authentication_except_public_allow_list(
    app: FastAPI,
) -> None:
    assert await find_unauthenticated(app) == []


@pytest.mark.asyncio
async def test_frozen_classification_covers_every_operation_exactly(app: FastAPI) -> None:
    """Every non-GET operation is classified user or restricted; no stale or duplicate entries."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        actual = set(await operations(client))
    non_get = {op for op in actual if op[0] != "GET"}
    assert USER_NON_GET_OPERATIONS.isdisjoint(RESTRICTED_OPERATIONS)
    assert non_get == USER_NON_GET_OPERATIONS | RESTRICTED_OPERATIONS
    assert PUBLIC_OPERATIONS <= actual
    assert DAEMON_OPERATIONS <= actual
    assert not any(method != "GET" for method, _ in PUBLIC_OPERATIONS)


@pytest.mark.asyncio
async def test_non_get_operations_follow_the_user_and_restricted_classification(
    app: FastAPI, key_pair: Any
) -> None:
    stub_services(app)
    token = make_token(key_pair[0], roles=[])  # authenticated, scoped, no roles at all
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    restricted_seen = 0
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as client:
        for method, path in await operations(client):
            if method == "GET":
                continue
            response = await client.request(method, concrete(path), headers=headers, content="[]")
            if (method, path) in USER_NON_GET_OPERATIONS:
                assert response.status_code not in (401, 403), (method, path)
            else:
                assert response.status_code == 403, (method, path, response.status_code)
                assert response.json()["error"]["message"]["error_code"] == (
                    "INSUFFICIENT_PERMISSIONS"
                )
                restricted_seen += 1
    assert restricted_seen == len(RESTRICTED_OPERATIONS)


@pytest.mark.asyncio
async def test_daemon_token_is_limited_to_the_designated_endpoints(
    app: FastAPI, key_pair: Any
) -> None:
    token = make_token(key_pair[0], scp="", roles=[ROLE_FINOPS_DAEMON])
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    stub_services(app)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as client:
        for method, path in await operations(client):
            if (method, path) in PUBLIC_OPERATIONS or (method, path) in DAEMON_OPERATIONS:
                continue
            response = await client.request(method, concrete(path), headers=headers, content="[]")
            assert response.status_code == 403, (method, path, response.status_code)
            assert (
                response.json()["error"]["message"]["error_code"]
                == "OPERATION_NOT_PERMITTED_FOR_APPLICATION"
            )


def test_classification_matches_application_lists() -> None:
    """The frozen test lists and the application's lists must be changed together."""
    expected_user = {
        f"cloud_recommender.api.routes.{module}.{func}"
        for module, func in [
            ("analysis", "analyze_requirements"),
            ("architecture", "generate_architecture"),
            ("finops", "simulate_scenario"),
            ("inventory", "analyze_azure_subscription"),
            ("inventory", "analyze_gcp_project"),
            ("inventory", "compare_multi_cloud"),
            ("monitoring", "get_monitoring_overview"),
            ("monitoring", "get_resource_monitoring_detail"),
            ("monitoring", "search_monitoring_logs"),
            ("monitoring", "get_token_economics"),
            ("pricing", "simulate_costs"),
            ("databricks", "test_databricks_connection"),
            ("databricks", "refresh_workspace_discovery"),
            ("finops", "validate_ingestion"),
            ("finops", "preview_ingestion"),
            ("finops", "record_decision_action"),
            ("finops", "update_finops_anomaly_status"),
            ("pricing", "refresh_prices"),
            ("azure_live", "connect_azure"),
            ("azure_live", "validate_azure_connection"),
            ("azure_live", "disconnect_azure"),
        ]
    }
    expected_daemon = {
        f"cloud_recommender.api.routes.{module}.{func}"
        for module, func in [
            ("databricks", "list_databricks_connections"),
            ("databricks", "get_workspace_health"),
            ("finops", "get_ingestion_status"),
            ("finops", "get_ingestion_runs"),
        ]
    }
    assert expected_user == set(USER_NON_GET_ENDPOINTS)
    assert expected_daemon == set(DAEMON_ALLOWED_ENDPOINTS)


def test_allow_list_entries_refer_to_real_endpoints_with_the_right_methods() -> None:
    """No stale entries (a renamed route must not silently gain or lose its classification)."""
    real: dict[str, set[str]] = {}
    for module_name in ROUTE_MODULES:
        module = importlib.import_module(f"cloud_recommender.api.routes.{module_name}")
        for route in module.router.routes:
            methods = getattr(route, "methods", None) or set()
            endpoint = getattr(route, "endpoint", None)
            if endpoint is not None:
                real[f"{endpoint.__module__}.{endpoint.__qualname__}"] = set(methods)
    for entry in USER_NON_GET_ENDPOINTS:
        assert entry in real, f"stale user-list entry: {entry}"
        assert real[entry] - {"GET", "HEAD", "OPTIONS"}, f"GET-only user-list entry: {entry}"
    for entry in DAEMON_ALLOWED_ENDPOINTS:
        assert entry in real, f"stale daemon-list entry: {entry}"
        assert real[entry] <= {"GET", "HEAD"}, f"daemon list must be read-only: {entry}"


@pytest.mark.asyncio
async def test_sweep_detects_a_newly_added_unprotected_route(key_pair: Any) -> None:
    """Meta-test: a route added without the router policy is reported by the sweep."""
    app = build_app(policy_settings(), key_pair[1])
    rogue = APIRouter()

    @rogue.post("/api/v1/zz-new-unprotected")
    async def rogue_endpoint() -> dict[str, str]:  # pragma: no cover - never reached by sweep
        return {"status": "executed"}

    app.include_router(rogue)
    app.openapi_schema = None  # recompute OpenAPI so the new route is visible
    assert ("POST", "/api/v1/zz-new-unprotected") in await find_unauthenticated(app)


@pytest.mark.asyncio
async def test_newly_added_protected_post_defaults_to_restricted(key_pair: Any) -> None:
    """A new non-GET route behind the standard router policy needs FinOpsAdmin by default."""
    app = build_app(policy_settings(), key_pair[1])
    new_router = APIRouter()

    @new_router.post("/zz-new-protected")
    async def new_endpoint() -> dict[str, str]:
        return {"status": "executed"}

    app.include_router(new_router, prefix="/api/v1", dependencies=[Depends(enforce_route_policy)])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        user = {"Authorization": f"Bearer {make_token(key_pair[0], roles=[])}"}
        admin = {"Authorization": f"Bearer {make_token(key_pair[0], roles=['FinOpsAdmin'])}"}
        daemon = {
            "Authorization": f"Bearer {make_token(key_pair[0], scp='', roles=[ROLE_FINOPS_DAEMON])}"
        }
        assert (await client.post("/api/v1/zz-new-protected")).status_code == 401
        assert (await client.post("/api/v1/zz-new-protected", headers=user)).status_code == 403
        assert (await client.post("/api/v1/zz-new-protected", headers=daemon)).status_code == 403
        assert (await client.post("/api/v1/zz-new-protected", headers=admin)).status_code == 200
