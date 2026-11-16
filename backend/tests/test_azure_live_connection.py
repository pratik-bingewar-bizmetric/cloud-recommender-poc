"""Live Azure connection (user-supplied service principal): acceptance tests.

Entra ID and Azure Resource Manager are replaced by an in-process ``httpx.MockTransport`` that
behaves like the real services (token endpoint, paging, 401/403/429 responses), so nothing here
touches the network or any real credential. All secrets and tokens are throw-away test values.
"""

import json
import logging
import subprocess
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import structlog
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from security_fixtures import (
    APPROVED_CLIENT_ID,
    PRODUCTION_SECURITY,
    build_app,
    make_token,
    new_rsa_key,
)

from cloud_recommender.api.routes.azure_live import get_azure_http_transport
from cloud_recommender.core.config import Settings
from cloud_recommender.services.azure_live.arm_client import AzureArmClient
from cloud_recommender.services.azure_live.session_store import (
    azure_session_store,
    connect_attempt_limiter,
)

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT = "22222222-2222-2222-2222-222222222222"
SECRET = "Sup3r-Secret-Value-For-Tests~abc123"
USER_TOKEN = "azure-token-for-user-sp"
SUB_OK = "aaaaaaaa-0000-0000-0000-000000000001"
SUB_RG_DENIED = "aaaaaaaa-0000-0000-0000-000000000002"
SUB_COST_DENIED = SUB_OK  # same subscription, cost denied in one test via flag
SERVER_CLIENT = "99999999-9999-9999-9999-999999999999"
SERVER_SECRET = "server-identity-secret-must-never-be-used"
VM_ID = (
    f"/subscriptions/{SUB_OK}/resourceGroups/rg-app/providers/Microsoft.Compute/virtualMachines/vm1"
)


class FakeAzure:
    """Mock Microsoft Entra ID + ARM. Records every request for assertions."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token_form: list[dict[str, str]] = []
        self.cost_mode = "ok"  # ok | denied | rate_limited | empty | unsupported
        self.metric_points = True
        self.entra_down = False

    # ------------------------------------------------------------------ routing
    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = urlparse(str(request.url))
        if url.netloc == "login.microsoftonline.com":
            return self._entra(request, url.path)
        if url.netloc == "management.azure.com":
            return self._arm(request, url)
        return httpx.Response(599, json={"error": "unexpected host " + url.netloc})

    def _entra(self, request: httpx.Request, path: str) -> httpx.Response:
        if self.entra_down:
            raise httpx.ConnectError("boom")
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.token_form.append(form)
        tenant = path.split("/")[1]
        if tenant == "00000000-0000-0000-0000-000000000000":
            return httpx.Response(
                400,
                json={
                    "error": "invalid_request",
                    "error_description": "AADSTS90002: Tenant not found. Trace ID: x",
                },
            )
        if form.get("client_id") != CLIENT:
            return httpx.Response(
                401,
                json={
                    "error": "unauthorized_client",
                    "error_description": "AADSTS700016: Application not found",
                },
            )
        if form.get("client_secret") != SECRET:
            return httpx.Response(
                401,
                json={
                    "error": "invalid_client",
                    "error_description": f"AADSTS7000215: Invalid client secret provided. Trace {SECRET[:0]}",
                },
            )
        return httpx.Response(
            200, json={"access_token": USER_TOKEN, "expires_in": 3599, "token_type": "Bearer"}
        )

    def _arm(self, request: httpx.Request, url: Any) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {USER_TOKEN}":
            return httpx.Response(
                401, json={"error": {"code": "InvalidAuthenticationToken", "message": "bad token"}}
            )
        path = url.path
        query = parse_qs(url.query)
        if path == "/subscriptions":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "subscriptionId": SUB_OK,
                            "displayName": "Prod",
                            "state": "Enabled",
                            "tenantId": TENANT,
                        },
                        {
                            "subscriptionId": SUB_RG_DENIED,
                            "displayName": "Restricted",
                            "state": "Enabled",
                            "tenantId": TENANT,
                        },
                    ]
                },
            )
        if path == f"/subscriptions/{SUB_OK}":
            return httpx.Response(
                200, json={"subscriptionId": SUB_OK, "displayName": "Prod", "state": "Enabled"}
            )
        if path.startswith("/subscriptions/") and path.count("/") == 2:
            return httpx.Response(
                403, json={"error": {"code": "AuthorizationFailed", "message": "no access"}}
            )
        if path == f"/subscriptions/{SUB_OK}/resourcegroups":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "name": "rg-app",
                            "id": f"/subscriptions/{SUB_OK}/resourceGroups/rg-app",
                            "location": "eastus",
                            "properties": {"provisioningState": "Succeeded"},
                        },
                        {
                            "name": "rg-data",
                            "id": f"/subscriptions/{SUB_OK}/resourceGroups/rg-data",
                            "location": "westus",
                            "properties": {"provisioningState": "Succeeded"},
                        },
                    ]
                },
            )
        if path == f"/subscriptions/{SUB_RG_DENIED}/resourcegroups":
            return httpx.Response(
                403, json={"error": {"code": "AuthorizationFailed", "message": "no rg access"}}
            )
        if path in (
            f"/subscriptions/{SUB_OK}/resources",
            f"/subscriptions/{SUB_RG_DENIED}/resources",
        ):
            if "page" not in query:
                return httpx.Response(
                    200,
                    json={
                        "value": [
                            {
                                "id": VM_ID,
                                "name": "vm1",
                                "type": "Microsoft.Compute/virtualMachines",
                                "location": "eastus",
                                "sku": {"name": "Standard_D2s_v3"},
                            },
                            {
                                "id": f"/subscriptions/{SUB_OK}/resourceGroups/rg-app/providers/Microsoft.Storage/storageAccounts/sa1",
                                "name": "sa1",
                                "type": "Microsoft.Storage/storageAccounts",
                                "location": "eastus",
                            },
                        ],
                        "nextLink": f"https://management.azure.com{path}?api-version=2021-04-01&page=2",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": f"/subscriptions/{SUB_OK}/resourceGroups/rg-data/providers/Microsoft.Compute/virtualMachines/vm2",
                            "name": "vm2",
                            "type": "Microsoft.Compute/virtualMachines",
                            "location": "westus",
                        }
                    ]
                },
            )
        if path == "/providers/Microsoft.Compute":
            return httpx.Response(
                200,
                json={
                    "resourceTypes": [
                        {
                            "resourceType": "virtualMachines",
                            "apiVersions": ["2024-07-01-preview", "2024-03-01"],
                        }
                    ]
                },
            )
        if path == VM_ID:
            return httpx.Response(
                200, json={"id": VM_ID, "name": "vm1", "properties": {"vmSize": "Standard_D2s_v3"}}
            )
        if path == f"{VM_ID}/providers/Microsoft.Insights/metricDefinitions":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "name": {"value": "Percentage CPU", "localizedValue": "Percentage CPU"},
                            "unit": "Percent",
                            "primaryAggregationType": "Average",
                            "supportedAggregationTypes": ["Average", "Maximum"],
                            "metricAvailabilities": [{"timeGrain": "PT1M"}, {"timeGrain": "PT1H"}],
                        }
                    ]
                },
            )
        if path == f"{VM_ID}/providers/Microsoft.Insights/metrics":
            data = (
                [{"timeStamp": "2026-11-16T10:00:00Z", "average": 12.5}]
                if self.metric_points
                else [{"timeStamp": "2026-11-16T10:00:00Z"}]
            )
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "name": {"value": "Percentage CPU", "localizedValue": "Percentage CPU"},
                            "unit": "Percent",
                            "timeseries": [{"data": data}],
                        }
                    ]
                },
            )
        if path == f"/subscriptions/{SUB_OK}/providers/Microsoft.CostManagement/query":
            assert request.method == "POST"
            if self.cost_mode == "denied":
                return httpx.Response(
                    403,
                    json={"error": {"code": "AuthorizationFailed", "message": "no cost access"}},
                )
            if self.cost_mode == "rate_limited":
                return httpx.Response(
                    429,
                    headers={"x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "37"},
                    json={"error": {"code": "429", "message": "Too many requests"}},
                )
            if self.cost_mode == "unsupported":
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "code": "BadRequest",
                            "message": "Cost Management is not supported for this subscription type",
                        }
                    },
                )
            rows = (
                []
                if self.cost_mode == "empty"
                else [[120.5, "Virtual Machines", "USD"], [30.25, "Storage", "USD"]]
            )
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "columns": [
                            {"name": "totalCost"},
                            {"name": "ServiceName"},
                            {"name": "Currency"},
                        ],
                        "rows": rows,
                    }
                },
            )
        return httpx.Response(
            404, json={"error": {"code": "NotFound", "message": "not found: " + path}}
        )

    def arm_calls(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == "management.azure.com"]


@pytest.fixture
def azure() -> FakeAzure:
    return FakeAzure()


@pytest.fixture(scope="module")
def keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    return new_rsa_key()


@pytest.fixture(autouse=True)
def reset_state() -> Any:
    azure_session_store.clear()
    connect_attempt_limiter._events.clear()
    yield
    azure_session_store.clear()
    connect_attempt_limiter._events.clear()


def make_app(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], azure: FakeAzure, **settings_kw: Any
) -> FastAPI:
    settings = Settings(
        _env_file=None,
        app_env="production",
        catalog_offline_mode=True,
        azure_tenant_id=TENANT,
        azure_client_id=SERVER_CLIENT,  # the SERVER's identity: must never be used
        azure_client_secret=SERVER_SECRET,
        azure_auth_method="azure_cli",
        **{**PRODUCTION_SECURITY, "azure_live_connect_attempts_per_minute": 50, **settings_kw},
    )
    app = build_app(settings, keys[1])
    transport = httpx.MockTransport(azure.handler)
    app.dependency_overrides[get_azure_http_transport] = lambda: transport
    return app


def bearer(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], sub: str = "user-1", **claims: Any
) -> dict[str, str]:
    token = make_token(keys[0], sub=sub, roles=[], **claims)
    return {"Authorization": f"Bearer {token}"}


async def request(
    app: FastAPI, method: str, path: str, headers: dict[str, str] | None = None, **kw: Any
) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.request(
            method, f"/api/v1/azure/connections{path}", headers=headers, **kw
        )


def creds(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"tenant_id": TENANT, "client_id": CLIENT, "client_secret": SECRET}
    body.update(overrides)
    return body


async def connect(app: FastAPI, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    response = await request(app, "POST", "", headers, json=creds(**overrides))
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


# --------------------------------------------------------------------------------------
# 1 / 2: credential validation and subscription discovery
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "category"),
    [
        ({"client_secret": "wrong-secret-value"}, "invalid_client_secret"),
        ({"client_id": "33333333-3333-3333-3333-333333333333"}, "application_not_found"),
        ({"tenant_id": "00000000-0000-0000-0000-000000000000"}, "tenant_not_found"),
    ],
)
async def test_invalid_credentials_are_rejected_without_leaking_them(
    keys: Any, azure: FakeAzure, overrides: dict[str, Any], category: str
) -> None:
    app = make_app(keys, azure)
    response = await request(app, "POST", "", bearer(keys), json=creds(**overrides))
    assert response.status_code == 400
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "INVALID_AZURE_CREDENTIALS"
    assert detail["category"] == category
    for secret in (SECRET, overrides.get("client_secret", "")):
        assert not secret or secret not in response.text
    assert azure_session_store._sessions == {}  # nothing was stored for a failed connect
    assert azure.arm_calls() == []  # no Azure data call without a valid token


@pytest.mark.asyncio
async def test_entra_outage_is_reported_as_502_not_as_bad_credentials(
    keys: Any, azure: FakeAzure
) -> None:
    azure.entra_down = True
    response = await request(make_app(keys, azure), "POST", "", bearer(keys), json=creds())
    assert response.status_code == 502
    assert response.json()["error"]["message"]["error_code"] == "ENTRA_UNAVAILABLE"


@pytest.mark.asyncio
async def test_valid_credentials_return_the_accessible_subscriptions(
    keys: Any, azure: FakeAzure
) -> None:
    app = make_app(keys, azure)
    body = await connect(app, bearer(keys), subscription_id=SUB_OK)

    conn = body["connection"]
    assert conn["tenant_id"] == TENANT and conn["client_id"] == CLIENT
    assert conn["identity_source"] == "user_supplied_service_principal"
    assert '"client_secret"' not in json.dumps(body) and SECRET not in json.dumps(body)

    subs = body["subscriptions"]
    assert subs["state"] == "accessible" and subs["count"] == 2
    assert {s["subscription_id"] for s in subs["items"]} == {SUB_OK, SUB_RG_DENIED}
    assert subs["source"]["connection_id"] == conn["connection_id"]
    assert body["requested_subscription"]["state"] == "accessible"


@pytest.mark.asyncio
async def test_requested_subscription_without_access_is_reported_as_permission_denied(
    keys: Any, azure: FakeAzure
) -> None:
    body = await connect(
        make_app(keys, azure), bearer(keys), subscription_id="cccccccc-0000-0000-0000-000000000009"
    )
    assert body["requested_subscription"]["state"] == "permission_denied"
    assert body["requested_subscription"]["required_permission"] == "Reader"


@pytest.mark.asyncio
async def test_validate_and_disconnect_lifecycle(keys: Any, azure: FakeAzure) -> None:
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]

    valid = await request(app, "POST", f"/{cid}/validate", headers)
    assert valid.status_code == 200 and valid.json()["valid"] is True

    gone = await request(app, "DELETE", f"/{cid}", headers)
    assert gone.status_code == 204
    assert (await request(app, "GET", f"/{cid}/subscriptions", headers)).status_code == 404


# --------------------------------------------------------------------------------------
# 3 / 4: resource groups and inventory use the supplied identity
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resource_groups_and_inventory_come_from_the_supplied_identity(
    keys: Any, azure: FakeAzure
) -> None:
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    base = f"/{cid}/subscriptions/{SUB_OK}"

    groups = (await request(app, "GET", f"{base}/resource-groups", headers)).json()
    assert groups["state"] == "accessible"
    assert [g["name"] for g in groups["items"]] == ["rg-app", "rg-data"]
    assert groups["source"]["subscription_id"] == SUB_OK

    inventory = (await request(app, "GET", f"{base}/resources", headers)).json()
    resources = inventory["resources"]
    assert resources["state"] == "accessible" and resources["count"] == 3  # paged: 2 + 1
    assert resources["truncated"] is False
    counts = {t["resource_type"]: t["count"] for t in inventory["type_breakdown"]}
    assert counts == {
        "Microsoft.Compute/virtualMachines": 2,
        "Microsoft.Storage/storageAccounts": 1,
    }
    assert resources["items"][0]["resource_group"] == "rg-app"

    # Every ARM call carried the USER's token; the server identity was never used.
    assert azure.arm_calls()
    assert all(r.headers["authorization"] == f"Bearer {USER_TOKEN}" for r in azure.arm_calls())
    assert [f["client_id"] for f in azure.token_form] == [CLIENT]
    assert SERVER_CLIENT not in json.dumps(azure.token_form) and SERVER_SECRET not in json.dumps(
        azure.token_form
    )


@pytest.mark.asyncio
async def test_resource_detail_resolves_a_stable_api_version(keys: Any, azure: FakeAzure) -> None:
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    response = await request(
        app,
        "GET",
        f"/{cid}/subscriptions/{SUB_OK}/resource",
        headers,
        params={"resource_id": VM_ID},
    )
    assert response.json()["state"] == "accessible"
    detail_call = [r for r in azure.arm_calls() if r.url.path == VM_ID][0]
    assert parse_qs(detail_call.url.query.decode())["api-version"] == [
        "2024-03-01"
    ]  # not the preview


@pytest.mark.asyncio
async def test_resource_group_filter(keys: Any, azure: FakeAzure) -> None:
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    await request(
        app,
        "GET",
        f"/{cid}/subscriptions/{SUB_OK}/resources",
        headers,
        params={"resource_group": "rg-app"},
    )
    assert any(
        r.url.path == f"/subscriptions/{SUB_OK}/resourceGroups/rg-app/resources"
        for r in azure.arm_calls()
    )


# --------------------------------------------------------------------------------------
# 5 / data transparency: monitoring, cost, partial failures
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_cost_management_permission_is_reported_not_shown_as_zero(
    keys: Any, azure: FakeAzure
) -> None:
    azure.cost_mode = "denied"
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    response = await request(app, "GET", f"/{cid}/subscriptions/{SUB_OK}/cost", headers)
    cost = response.json()
    assert cost["state"] == "permission_denied"
    assert cost["required_permission"] == "Cost Management Reader"
    assert cost["items"] is None and cost["count"] is None  # no numbers at all
    assert "Cost Management Reader" in cost["message"]
    assert cost["source"]["subscription_id"] == SUB_OK


@pytest.mark.asyncio
async def test_cost_data_is_reported_with_currency_and_real_totals(
    keys: Any, azure: FakeAzure
) -> None:
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    cost = (await request(app, "GET", f"/{cid}/subscriptions/{SUB_OK}/cost", headers)).json()
    assert cost["state"] == "accessible"
    summary = cost["items"][0]
    assert summary["total"] == 150.75 and summary["currency"] == "USD"
    assert summary["by_service"][0] == {
        "service": "Virtual Machines",
        "cost": 120.5,
        "currency": "USD",
    }
    posted = [r for r in azure.arm_calls() if r.method == "POST"]
    assert len(posted) == 1 and posted[0].url.path.endswith(
        "/providers/Microsoft.CostManagement/query"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "state"),
    [("empty", "empty"), ("rate_limited", "error"), ("unsupported", "unavailable")],
)
async def test_cost_states_are_distinct(keys: Any, azure: FakeAzure, mode: str, state: str) -> None:
    azure.cost_mode = mode
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    cost = (await request(app, "GET", f"/{cid}/subscriptions/{SUB_OK}/cost", headers)).json()
    assert cost["state"] == state
    assert not cost["items"]  # never a fabricated zero total
    if mode == "rate_limited":
        assert cost["retry_after_seconds"] == 37
    if mode == "empty":
        assert "not a statement that spend is zero" in cost["message"]


@pytest.mark.asyncio
async def test_one_failing_domain_never_hides_accessible_data(keys: Any, azure: FakeAzure) -> None:
    azure.cost_mode = "denied"
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]

    restricted = (
        await request(app, "GET", f"/{cid}/subscriptions/{SUB_RG_DENIED}/overview", headers)
    ).json()
    assert restricted["resource_groups"]["state"] == "permission_denied"
    assert restricted["resources"]["state"] == "accessible"  # still shown
    assert restricted["resources"]["count"] == 3

    overview = (
        await request(app, "GET", f"/{cid}/subscriptions/{SUB_OK}/overview", headers)
    ).json()
    assert overview["subscriptions"]["count"] == 2
    assert overview["resource_groups"]["count"] == 2
    assert overview["resources"]["count"] == 3
    assert overview["cost"]["state"] == "permission_denied"
    assert overview["connection"]["connection_id"] == cid
    assert overview["resources"]["source"]["connection_id"] == cid


@pytest.mark.asyncio
async def test_monitor_metric_definitions_and_values(keys: Any, azure: FakeAzure) -> None:
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    base = f"/{cid}/subscriptions/{SUB_OK}/metrics"

    definitions = (
        await request(app, "GET", f"{base}/definitions", headers, params={"resource_id": VM_ID})
    ).json()
    assert definitions["state"] == "accessible"
    assert definitions["items"][0]["name"] == "Percentage CPU"
    assert definitions["items"][0]["time_grains"] == ["PT1M", "PT1H"]

    values = (
        await request(
            app,
            "GET",
            base,
            headers,
            params={"resource_id": VM_ID, "metric_names": "Percentage CPU"},
        )
    ).json()["metrics"]
    assert values["state"] == "accessible"
    assert values["items"][0]["points"] == [{"timestamp": "2026-11-16T10:00:00Z", "value": 12.5}]

    azure.metric_points = False
    empty = (
        await request(
            app,
            "GET",
            base,
            headers,
            params={"resource_id": VM_ID, "metric_names": "Percentage CPU"},
        )
    ).json()["metrics"]
    assert empty["state"] == "empty"  # Azure returned a series without values: not a made-up 0


# --------------------------------------------------------------------------------------
# 6: no Azure CLI / server identity
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_azure_cli_or_ambient_identity_is_used(
    keys: Any, azure: FakeAzure, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_a: Any, **_k: Any) -> None:
        raise AssertionError("a subprocess (e.g. the Azure CLI) must never be started")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setenv("AZURE_CLIENT_ID", SERVER_CLIENT)
    monkeypatch.setenv("AZURE_CLIENT_SECRET", SERVER_SECRET)
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    overview = await request(app, "GET", f"/{cid}/subscriptions/{SUB_OK}/overview", headers)
    assert overview.status_code == 200
    assert [f["client_id"] for f in azure.token_form] == [CLIENT]


@pytest.mark.asyncio
async def test_personal_connection_never_falls_back_to_the_server_identity(
    keys: Any, azure: FakeAzure
) -> None:
    """If the user's token is rejected by Azure the result is 'unavailable', not shared-identity data."""
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    azure_session_store._sessions[cid].token = type(azure_session_store._sessions[cid].token)(
        value="revoked", expires_at=9e12
    )
    response = await request(app, "GET", f"/{cid}/subscriptions/{SUB_OK}/resource-groups", headers)
    assert response.json()["state"] == "unavailable"
    assert response.json()["http_status"] == 401
    assert all(r.headers["authorization"] == "Bearer revoked" for r in azure.arm_calls()[-1:])
    assert len(azure.token_form) == 1  # no second token was minted with any other identity


# --------------------------------------------------------------------------------------
# 7: secrets are never logged, echoed or retained
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_secret_is_never_logged_echoed_or_stored(
    keys: Any, azure: FakeAzure, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    app = make_app(keys, azure)
    headers = bearer(keys)
    with structlog.testing.capture_logs() as captured:
        ok = await request(app, "POST", "", headers, json=creds())
        bad = await request(
            app, "POST", "", headers, json=creds(client_secret="another-wrong-secret-9")
        )
        malformed = await request(  # validation error: pydantic would echo the whole input
            app, "POST", "", headers, json={"tenant_id": TENANT, "client_secret": SECRET}
        )
        too_many = await request(app, "POST", "", headers, json={**creds(), "unexpected": 1})
    assert ok.status_code == 201 and bad.status_code == 400
    assert malformed.status_code == 422 and too_many.status_code == 422

    everything = " ".join(
        [r.getMessage() for r in caplog.records]
        + [json.dumps(e, default=str) for e in captured]
        + [ok.text, bad.text, malformed.text, too_many.text]
    )
    for secret in (SECRET, "another-wrong-secret-9"):
        assert secret not in everything
    # Only the token is retained in memory, never the secret.
    assert SECRET not in repr(azure_session_store._sessions)
    assert USER_TOKEN not in repr(azure_session_store._sessions)  # token hidden from repr as well


def test_arm_client_repr_hides_the_token() -> None:
    client = AzureArmClient(token=USER_TOKEN, base_url="https://management.azure.com")
    assert USER_TOKEN not in repr(client)


# --------------------------------------------------------------------------------------
# 8: backend authentication stays mandatory
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authentication_is_mandatory_for_every_azure_live_endpoint(
    keys: Any, azure: FakeAzure
) -> None:
    app = make_app(keys, azure)
    cid = "x"
    calls = [
        ("POST", "", {"json": creds()}),
        ("POST", f"/{cid}/validate", {}),
        ("DELETE", f"/{cid}", {}),
        ("GET", f"/{cid}/subscriptions", {}),
        ("GET", f"/{cid}/subscriptions/{SUB_OK}/overview", {}),
        ("GET", f"/{cid}/subscriptions/{SUB_OK}/cost", {}),
    ]
    for method, path, kw in calls:
        assert (await request(app, method, path, None, **kw)).status_code == 401, (method, path)
    assert azure.requests == []  # nothing reached Entra or Azure


@pytest.mark.asyncio
async def test_rayfin_style_and_foreign_tokens_are_rejected(keys: Any, azure: FakeAzure) -> None:
    app = make_app(keys, azure)
    wrong_audience = {
        "Authorization": "Bearer " + make_token(keys[0], aud="api://rayfin-or-fabric")
    }
    hs256 = {
        "Authorization": "Bearer "
        + __import__("jwt").encode({"sub": "rayfin-session"}, "k" * 40, "HS256")
    }
    opaque = {"Authorization": "Bearer rayfin-session-token-opaque"}
    for headers in (wrong_audience, hs256, opaque):
        assert (await request(app, "POST", "", headers, json=creds())).status_code == 401
    assert azure.requests == []


@pytest.mark.asyncio
async def test_scope_and_approved_client_are_required(keys: Any, azure: FakeAzure) -> None:
    app = make_app(keys, azure)
    no_scope = {"Authorization": "Bearer " + make_token(keys[0], scp="")}
    wrong_client = {
        "Authorization": "Bearer " + make_token(keys[0], azp="99999999-0000-0000-0000-000000000000")
    }
    assert (await request(app, "POST", "", no_scope, json=creds())).status_code == 403
    assert (await request(app, "POST", "", wrong_client, json=creds())).status_code == 403
    assert APPROVED_CLIENT_ID in PRODUCTION_SECURITY["entra_allowed_client_ids"]
    assert azure.requests == []


# --------------------------------------------------------------------------------------
# Ownership, limits, input validation, safety rails
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_other_users_get_404_on_every_connection_route(keys: Any, azure: FakeAzure) -> None:
    app = make_app(keys, azure)
    cid = (await connect(app, bearer(keys, sub="alice")))["connection"]["connection_id"]
    bob = bearer(keys, sub="bob")
    base = f"/{cid}/subscriptions/{SUB_OK}"
    attempts = [
        ("POST", f"/{cid}/validate", {}),
        ("DELETE", f"/{cid}", {}),
        ("GET", f"/{cid}/subscriptions", {}),
        ("GET", f"{base}/resource-groups", {}),
        ("GET", f"{base}/resources", {}),
        ("GET", f"{base}/overview", {}),
        ("GET", f"{base}/cost", {}),
        ("GET", f"{base}/resource", {"params": {"resource_id": VM_ID}}),
        ("GET", f"{base}/metrics/definitions", {"params": {"resource_id": VM_ID}}),
    ]
    unknown = await request(app, "GET", "/nonexistent/subscriptions", bob)
    for method, path, kw in attempts:
        response = await request(app, method, path, bob, **kw)
        assert response.status_code == 404, (method, path)
        assert response.json() == unknown.json()  # identical body: no enumeration oracle
    assert (
        await request(app, "GET", f"/{cid}/subscriptions", bearer(keys, sub="alice"))
    ).status_code == 200


@pytest.mark.asyncio
async def test_sessions_expire(keys: Any, azure: FakeAzure) -> None:
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    now = azure_session_store._clock()
    azure_session_store._clock = lambda: now + 7200  # type: ignore[assignment]
    try:
        assert (await request(app, "GET", f"/{cid}/subscriptions", headers)).status_code == 404
    finally:
        import time

        azure_session_store._clock = time.time  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_connect_attempts_are_rate_limited_per_user(keys: Any, azure: FakeAzure) -> None:
    app = make_app(keys, azure, azure_live_connect_attempts_per_minute=2)
    headers = bearer(keys)
    statuses = [
        (await request(app, "POST", "", headers, json=creds(client_secret="wrong"))).status_code
        for _ in range(3)
    ]
    assert statuses == [400, 400, 429]
    limited = await request(app, "POST", "", headers, json=creds())
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    # another user is unaffected
    assert (
        await request(app, "POST", "", bearer(keys, sub="carol"), json=creds())
    ).status_code == 201


@pytest.mark.asyncio
async def test_connection_limit_per_user(keys: Any, azure: FakeAzure) -> None:
    app = make_app(keys, azure, azure_live_max_connections_per_user=2)
    headers = bearer(keys)
    await connect(app, headers)
    await connect(app, headers)
    third = await request(app, "POST", "", headers, json=creds())
    assert third.status_code == 409
    assert third.json()["error"]["message"]["error_code"] == "CONNECTION_LIMIT_REACHED"


@pytest.mark.asyncio
async def test_identifiers_are_validated_before_use_in_azure_urls(
    keys: Any, azure: FakeAzure
) -> None:
    app = make_app(keys, azure)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    before = len(azure.arm_calls())

    assert (
        await request(app, "POST", "", headers, json=creds(tenant_id="../evil"))
    ).status_code == 422
    assert (
        await request(app, "POST", "", headers, json=creds(client_id="x" * 5))
    ).status_code == 422
    assert (
        await request(app, "GET", f"/{cid}/subscriptions/not-a-guid/resources", headers)
    ).status_code == 422
    bad_ids = [
        f"/subscriptions/{SUB_RG_DENIED}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",  # other sub
        f"{VM_ID}?api-version=1",
        f"{VM_ID}/../../../..",
        "/providers/Microsoft.Authorization/roleAssignments",
    ]
    for rid in bad_ids:
        response = await request(
            app,
            "GET",
            f"/{cid}/subscriptions/{SUB_OK}/resource",
            headers,
            params={"resource_id": rid},
        )
        assert response.status_code == 422, rid
    assert len(azure.arm_calls()) == before  # no Azure call was made for invalid input
    assert not [
        r
        for r in azure.requests
        if r.url.host == "login.microsoftonline.com" and "evil" in str(r.url)
    ]


@pytest.mark.asyncio
async def test_pagination_never_follows_a_foreign_host(keys: Any, azure: FakeAzure) -> None:
    original = azure.handler

    def evil_next_link(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/subscriptions/{SUB_OK}/resources":
            return httpx.Response(
                200,
                json={
                    "value": [{"id": VM_ID, "name": "vm1", "type": "t"}],
                    "nextLink": "https://evil.test/steal",
                },
            )
        return original(request)

    azure.handler = evil_next_link  # type: ignore[method-assign]
    app = make_app(keys, azure)
    app.dependency_overrides[get_azure_http_transport] = lambda: httpx.MockTransport(azure.handler)
    headers = bearer(keys)
    cid = (await connect(app, headers))["connection"]["connection_id"]
    result = (
        await request(app, "GET", f"/{cid}/subscriptions/{SUB_OK}/resources", headers)
    ).json()["resources"]
    assert result["truncated"] is True and result["count"] == 1
    assert not [r for r in azure.requests if r.url.host == "evil.test"]


@pytest.mark.asyncio
async def test_arm_client_is_read_only() -> None:
    client = AzureArmClient(token="t", base_url="https://management.azure.com")
    for method in ("DELETE", "PUT", "PATCH"):
        with pytest.raises(PermissionError):
            await client._send(method, "https://management.azure.com/subscriptions/x")
    with pytest.raises(PermissionError):
        await client._send("POST", "https://management.azure.com/subscriptions/x/resourcegroups")
    with pytest.raises(PermissionError):
        await client._send("GET", "https://evil.test/subscriptions")


@pytest.mark.asyncio
async def test_empty_subscription_list_is_reported_as_empty_with_guidance(
    keys: Any, azure: FakeAzure
) -> None:
    original = azure.handler

    def no_subscriptions(request: httpx.Request) -> httpx.Response:
        if request.url.host == "management.azure.com" and request.url.path == "/subscriptions":
            return httpx.Response(200, json={"value": []})
        return original(request)

    app = make_app(keys, azure)
    app.dependency_overrides[get_azure_http_transport] = lambda: httpx.MockTransport(
        no_subscriptions
    )
    body = await connect(app, bearer(keys))
    assert body["subscriptions"]["state"] == "empty"
    assert "Assign Reader" in body["subscriptions"]["message"]
