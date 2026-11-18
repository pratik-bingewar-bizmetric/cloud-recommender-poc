"""Persistent, owner-bound cloud connections: create / list / validate / rotate / delete / reuse.

Microsoft Entra ID, Azure Resource Manager, Azure Databricks and the Fabric API are replaced by an
in-process ``httpx.MockTransport``; the repository is the in-memory implementation shared by two
"server instances" to prove persistence across a restart. No network, no real credentials.
"""

import json
import logging
import subprocess
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
import structlog
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from security_fixtures import PRODUCTION_SECURITY, build_app, make_token, new_rsa_key
from sqlalchemy.exc import SQLAlchemyError
from test_azure_live_connection import (
    CLIENT,
    SECRET,
    SUB_OK,
    TENANT,
    USER_TOKEN,
    VM_ID,
    FakeAzure,
)

from cloud_recommender.api.connection_deps import (
    get_azure_http_transport,
    get_connection_repository,
    reset_cipher_cache,
)
from cloud_recommender.core.config import Settings
from cloud_recommender.db.repositories.connection_repo import InMemoryConnectionRepository
from cloud_recommender.services.azure_live.session_store import (
    azure_session_store,
    connect_attempt_limiter,
)

SECRET_2 = "Rotated-Secret-Value-For-Tests~xyz789"
DB_URL = "https://adb-1234567890123456.7.azuredatabricks.net"
FABRIC_WS = "cccccccc-0000-0000-0000-00000000000c"


class FakeCloud(FakeAzure):
    """FakeAzure + Authorization permissions, Databricks and Fabric."""

    def __init__(self) -> None:
        super().__init__()
        self.valid_secrets = {SECRET}
        self.perm_mode = "reader"  # reader | arm_only | contributor | forbidden
        self.sub_tenant = TENANT
        self.db_mode = "ok"  # ok | forbidden | notfound
        self.fabric_mode = "ok"
        self.scopes: list[str] = []

    def _entra(self, request: httpx.Request, path: str) -> httpx.Response:
        if self.entra_down:
            raise httpx.ConnectError("boom")
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.token_form.append(form)
        self.scopes.append(form.get("scope", ""))
        tenant = path.split("/")[1]
        if tenant == "00000000-0000-0000-0000-000000000000":
            return httpx.Response(400, json={"error_description": "AADSTS90002: Tenant not found"})
        if form.get("client_id") != CLIENT:
            return httpx.Response(
                401, json={"error_description": "AADSTS700016: Application not found"}
            )
        if form.get("client_secret") not in self.valid_secrets:
            return httpx.Response(
                401, json={"error_description": "AADSTS7000215: Invalid client secret"}
            )
        token = {
            "https://management.azure.com/.default": USER_TOKEN,
            "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default": "db-token",
            "https://api.fabric.microsoft.com/.default": "fabric-token",
        }[form["scope"]]
        return httpx.Response(200, json={"access_token": token, "expires_in": 3599})

    def handler(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host.endswith(".azuredatabricks.net"):
            self.requests.append(request)
            if self.db_mode != "ok":
                return httpx.Response(403 if self.db_mode == "forbidden" else 404, json={})
            if path.endswith("/scim/v2/Me"):
                return httpx.Response(200, json={"userName": "sp"})
            return httpx.Response(200, json={"warehouses": [{"id": "w1"}, {"id": "w2"}]})
        if host == "api.fabric.microsoft.com":
            self.requests.append(request)
            if self.fabric_mode != "ok":
                return httpx.Response(403 if self.fabric_mode == "forbidden" else 404, json={})
            if path.endswith("/lakehouses"):
                return httpx.Response(200, json={"value": [{"displayName": "finops_lakehouse"}]})
            return httpx.Response(200, json={"displayName": "FinOps WS", "capacityId": "cap-1"})
        if host == "management.azure.com":
            if request.headers.get("authorization") == f"Bearer {USER_TOKEN}":
                if path == f"/subscriptions/{SUB_OK}":
                    self.requests.append(request)
                    return httpx.Response(
                        200,
                        json={
                            "subscriptionId": SUB_OK,
                            "displayName": "Prod",
                            "tenantId": self.sub_tenant,
                        },
                    )
                if path.endswith("/providers/Microsoft.Authorization/permissions"):
                    self.requests.append(request)
                    if self.perm_mode == "forbidden":
                        return httpx.Response(
                            403, json={"error": {"code": "AuthorizationFailed", "message": "x"}}
                        )
                    blocks = {
                        "reader": [{"actions": ["*/read"], "notActions": []}],
                        "arm_only": [
                            {
                                "actions": [
                                    "Microsoft.Resources/subscriptions/resourceGroups/read"
                                ],
                                "notActions": [],
                            }
                        ],
                        "contributor": [
                            {"actions": ["*"], "notActions": ["Microsoft.Authorization/*/Delete"]}
                        ],
                    }[self.perm_mode]
                    return httpx.Response(200, json={"value": blocks})
        return super().handler(request)


@pytest.fixture
def cloud() -> FakeCloud:
    return FakeCloud()


@pytest.fixture(scope="module")
def keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    return new_rsa_key()


@pytest.fixture
def repo() -> InMemoryConnectionRepository:
    return InMemoryConnectionRepository()


@pytest.fixture(autouse=True)
def reset_state() -> Any:
    for _ in (0, 1):
        azure_session_store.clear()
        connect_attempt_limiter._events.clear()
        reset_cipher_cache()
    yield
    azure_session_store.clear()


def make_app(
    keys: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    cloud: FakeCloud,
    repo: Any,
    **settings_kw: Any,
) -> FastAPI:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="production",
        catalog_offline_mode=True,
        azure_tenant_id=TENANT,
        azure_client_id="99999999-9999-9999-9999-999999999999",  # the SERVER identity: never used
        azure_client_secret="server-identity-secret-must-never-be-used",
        azure_auth_method="azure_cli",
        **{**PRODUCTION_SECURITY, "azure_live_connect_attempts_per_minute": 100, **settings_kw},
    )
    app = build_app(settings, keys[1])
    transport = httpx.MockTransport(cloud.handler)
    app.dependency_overrides[get_azure_http_transport] = lambda: transport
    app.dependency_overrides[get_connection_repository] = lambda: repo
    return app


def user(keys: Any, name: str = "alice") -> dict[str, str]:
    return {"Authorization": "Bearer " + make_token(keys[0], sub=name, roles=[])}


def payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "provider": "azure",
        "auth_method": "service_principal",
        "name": "Production",
        "scope_id": SUB_OK,
        "azure_tenant_id": TENANT,
        "azure_client_id": CLIENT,
        "azure_client_secret": SECRET,
    }
    body.update(overrides)
    return body


async def call(
    app: FastAPI, method: str, path: str, headers: dict[str, str] | None = None, **kw: Any
) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.request(method, f"/api/v1{path}", headers=headers, **kw)


async def create(app: FastAPI, keys: Any, name: str = "alice", **overrides: Any) -> dict[str, Any]:
    response = await call(app, "POST", "/connections", user(keys, name), json=payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def states(connection: dict[str, Any]) -> dict[str, str]:
    return {i["integration"]: i["state"] for i in connection["integrations"]}


# --------------------------------------------------------------------------------------
# Azure: validation workflow
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_service_principal_is_validated_saved_and_reported_per_integration(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    connection = await create(make_app(keys, cloud, repo), keys)
    assert connection["ownership"] == "owned" and connection["status"] == "connected"
    assert connection["auth_method"] == "service_principal" and connection["scope_id"] == SUB_OK
    assert states(connection) == {
        "resource_manager": "connected",
        "cost_management": "connected",
        "monitor": "connected",
        "databricks": "not_configured",
        "fabric": "not_configured",
    }
    # Saved encrypted, never in plaintext, never returned.
    row = next(iter(repo._rows.values()))
    assert row.secret_ciphertext and SECRET.encode() not in row.secret_ciphertext
    assert SECRET not in json.dumps(connection) and "ciphertext" not in json.dumps(connection)
    # The subscription's tenant was verified and the principal's own permissions were read.
    paths = [r.url.path for r in cloud.arm_calls()]
    assert f"/subscriptions/{SUB_OK}" in paths and any(p.endswith("/permissions") for p in paths)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "category"),
    [
        ({"azure_client_secret": "wrong"}, "invalid_client_secret"),
        ({"azure_client_id": "33333333-3333-3333-3333-333333333333"}, "application_not_found"),
        ({"azure_tenant_id": "00000000-0000-0000-0000-000000000000"}, "tenant_not_found"),
    ],
)
async def test_invalid_credentials_are_rejected_and_nothing_is_saved(
    keys: Any,
    cloud: FakeCloud,
    repo: InMemoryConnectionRepository,
    overrides: dict[str, Any],
    category: str,
) -> None:
    response = await call(
        make_app(keys, cloud, repo), "POST", "/connections", user(keys), json=payload(**overrides)
    )
    assert response.status_code == 400
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "INVALID_AZURE_CREDENTIALS" and detail["category"] == category
    assert repo._rows == {} and "wrong" not in response.text
    assert cloud.arm_calls() == []


@pytest.mark.asyncio
async def test_subscription_errors_are_specific(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    missing = await call(
        app,
        "POST",
        "/connections",
        user(keys),
        json=payload(scope_id="cccccccc-0000-0000-0000-000000000009"),
    )
    assert missing.status_code == 400
    assert missing.json()["error"]["message"]["error_code"] == "SUBSCRIPTION_NOT_ACCESSIBLE"
    bad_format = await call(
        app, "POST", "/connections", user(keys), json=payload(scope_id="not-a-guid")
    )
    assert bad_format.status_code == 422

    cloud.sub_tenant = "44444444-4444-4444-4444-444444444444"
    mismatch = await call(app, "POST", "/connections", user(keys), json=payload())
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["message"]["error_code"] == "SUBSCRIPTION_TENANT_MISMATCH"
    assert repo._rows == {}


@pytest.mark.asyncio
async def test_missing_required_fields_report_which_fields(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    body = payload()
    del body["azure_client_secret"], body["azure_client_id"]
    response = await call(
        make_app(keys, cloud, repo), "POST", "/connections", user(keys), json=body
    )
    assert response.status_code == 422
    detail = response.json()["error"]["message"]
    assert detail["error_code"] == "MISSING_REQUIRED_FIELDS"
    assert set(detail["fields"]) == {"azure_client_id", "azure_client_secret"}
    assert cloud.requests == []


@pytest.mark.asyncio
async def test_cost_and_monitor_permission_denied_are_reported_separately_never_as_zero(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    cloud.perm_mode = "arm_only"
    connection = await create(make_app(keys, cloud, repo), keys)
    assert states(connection)["resource_manager"] == "connected"
    by = {i["integration"]: i for i in connection["integrations"]}
    assert by["cost_management"]["state"] == "permission_denied"
    assert by["cost_management"]["required_permission"] == "Cost Management Reader"
    assert by["monitor"]["state"] == "permission_denied"
    assert by["monitor"]["required_permission"] == "Monitoring Reader"
    assert "cost_management" not in connection["capabilities"]
    assert not any(k in json.dumps(connection) for k in ("total_cost", '"cost": 0'))


@pytest.mark.asyncio
async def test_unreadable_permissions_are_unavailable_not_assumed_granted(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    cloud.perm_mode = "forbidden"
    connection = await create(make_app(keys, cloud, repo), keys)
    assert states(connection)["cost_management"] == "permission_denied"
    assert connection["status"] == "permission_denied"


@pytest.mark.asyncio
async def test_write_capable_principals_are_rejected_by_default_or_flagged(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    cloud.perm_mode = "contributor"
    rejected = await call(
        make_app(keys, cloud, repo), "POST", "/connections", user(keys), json=payload()
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"]["message"]["error_code"] == "WRITE_PERMISSIONS_DETECTED"
    assert repo._rows == {}

    flagged_app = make_app(keys, cloud, repo, connection_reject_write_principals=False)
    flagged = await create(flagged_app, keys)
    assert flagged["warnings"] and "write-capable" in flagged["warnings"][0]


@pytest.mark.asyncio
async def test_duplicate_and_limit(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo, connections_max_per_user=1)
    await create(app, keys)
    duplicate = await call(app, "POST", "/connections", user(keys), json=payload())
    assert duplicate.status_code == 409  # limit reached (checked before the duplicate)
    app2 = make_app(keys, cloud, repo)
    again = await call(app2, "POST", "/connections", user(keys), json=payload())
    assert again.status_code == 409
    assert again.json()["error"]["message"]["error_code"] == "DUPLICATE_CONNECTION"
    other_user = await call(app2, "POST", "/connections", user(keys, "bob"), json=payload())
    assert other_user.status_code == 201


# --------------------------------------------------------------------------------------
# Optional integrations: Databricks and Fabric
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_databricks_and_fabric_connected_with_details(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    connection = await create(
        make_app(keys, cloud, repo),
        keys,
        databricks_workspace_url=DB_URL,
        fabric_workspace_id=FABRIC_WS,
    )
    by = {i["integration"]: i for i in connection["integrations"]}
    assert (
        by["databricks"]["state"] == "connected"
        and by["databricks"]["details"]["warehouses_visible"] == 2
    )
    assert "not verified" in by["databricks"]["details"]["system_tables"]
    assert by["fabric"]["state"] == "connected"
    assert by["fabric"]["details"]["capacity_id"] == "cap-1"
    assert by["fabric"]["details"]["lakehouses"] == ["finops_lakehouse"]
    # Each service got a token for ITS audience with the same user-supplied principal.
    assert set(cloud.scopes) >= {
        "https://management.azure.com/.default",
        "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default",
        "https://api.fabric.microsoft.com/.default",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "state"), [("forbidden", "permission_denied"), ("notfound", "unavailable")]
)
async def test_databricks_and_fabric_failures_do_not_fail_azure(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository, mode: str, state: str
) -> None:
    cloud.db_mode = cloud.fabric_mode = mode
    connection = await create(
        make_app(keys, cloud, repo),
        keys,
        databricks_workspace_url=DB_URL,
        fabric_workspace_id=FABRIC_WS,
    )
    assert states(connection)["resource_manager"] == "connected"
    assert states(connection)["databricks"] == state and states(connection)["fabric"] == state
    assert connection["status"] == "connected"


@pytest.mark.asyncio
async def test_invalid_workspace_inputs_are_reported_without_any_call(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    connection = await create(
        make_app(keys, cloud, repo),
        keys,
        databricks_workspace_url="https://evil.example.org",
        fabric_workspace_id="not-a-guid",
    )
    assert states(connection)["databricks"] == "error" and states(connection)["fabric"] == "error"
    assert not [
        r for r in cloud.requests if r.url.host in ("evil.example.org", "api.fabric.microsoft.com")
    ]


# --------------------------------------------------------------------------------------
# Persistence, ownership, rotation, deletion
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_survives_a_backend_restart_and_is_used_for_data(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    created = await create(make_app(keys, cloud, repo), keys)
    cid = created["id"]

    # "Restart": a new app instance, empty in-memory sessions, same database.
    azure_session_store.clear()
    reset_cipher_cache()
    restarted = make_app(keys, cloud, repo)

    listed = (await call(restarted, "GET", "/connections", user(keys))).json()
    assert [c["id"] for c in listed if c["ownership"] == "owned"] == [cid]
    assert (await call(restarted, "GET", f"/connections/{cid}", user(keys))).json()[
        "name"
    ] == "Production"

    # The stored (decrypted) credential mints a token that serves live data for this connection.
    cloud.token_form.clear()
    overview = await call(
        restarted, "GET", f"/azure/connections/{cid}/subscriptions/{SUB_OK}/overview", user(keys)
    )
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["resources"]["state"] == "accessible" and body["connection"]["connection_id"] == cid
    assert [f["client_id"] for f in cloud.token_form] == [CLIENT]
    assert cloud.token_form[0]["client_secret"] == SECRET  # the owner's own stored secret
    assert all(r.headers["authorization"] == f"Bearer {USER_TOKEN}" for r in cloud.arm_calls()[-5:])


@pytest.mark.asyncio
async def test_expired_azure_token_is_refreshed_transparently_from_the_stored_credential(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    cid = (await create(app, keys))["id"]
    url = f"/azure/connections/{cid}/subscriptions/{SUB_OK}/resource-groups"
    assert (await call(app, "GET", url, user(keys))).status_code == 200
    import time

    real = azure_session_store._clock
    azure_session_store._clock = lambda: time.time() + 7200  # the cached token has expired
    try:
        before = len(cloud.token_form)
        assert (await call(app, "GET", url, user(keys))).status_code == 200
        assert len(cloud.token_form) == before + 1  # re-minted, no user interaction
    finally:
        azure_session_store._clock = real


@pytest.mark.asyncio
async def test_ownership_is_isolated_on_every_connection_route(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    cid = (await create(app, keys, "alice"))["id"]
    bob = user(keys, "bob")
    unknown = await call(app, "GET", "/connections/11111111-1111-1111-1111-111111111111", bob)
    attempts = [
        ("GET", f"/connections/{cid}", {}),
        ("PATCH", f"/connections/{cid}", {"json": {"name": "hijack"}}),
        ("DELETE", f"/connections/{cid}", {}),
        ("POST", f"/connections/{cid}/validate", {}),
        (
            "POST",
            "/connections/validate",
            {"json": {"connection_id": cid, "provider": "azure", "scope_id": SUB_OK}},
        ),
        ("GET", f"/azure/connections/{cid}/subscriptions", {}),
        ("GET", f"/azure/connections/{cid}/subscriptions/{SUB_OK}/overview", {}),
    ]
    for method, path, kw in attempts:
        response = await call(app, method, path, bob, **kw)
        assert response.status_code == 404, (method, path, response.status_code)
        assert response.json()["error"]["message"]["error_code"] in (
            "CONNECTION_NOT_FOUND",
            "AZURE_CONNECTION_NOT_FOUND",
        )
    assert unknown.status_code == 404
    assert [
        c for c in (await call(app, "GET", "/connections", bob)).json() if c["ownership"] == "owned"
    ] == []
    assert len(repo._rows) == 1  # alice's connection untouched
    assert (await call(app, "GET", f"/connections/{cid}", user(keys, "alice"))).status_code == 200


@pytest.mark.asyncio
async def test_secrets_are_never_returned_by_any_api(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    cid = (await create(app, keys))["id"]
    texts = [
        (await call(app, "GET", "/connections", user(keys))).text,
        (await call(app, "GET", f"/connections/{cid}", user(keys))).text,
        (await call(app, "POST", f"/connections/{cid}/validate", user(keys))).text,
        (
            await call(app, "PATCH", f"/connections/{cid}", user(keys), json={"name": "Renamed"})
        ).text,
    ]
    row = next(iter(repo._rows.values()))
    blob_text = base64_of(row.secret_ciphertext)
    for text in texts:
        assert SECRET not in text and "client_secret" not in text and blob_text not in text


def base64_of(blob: bytes | None) -> str:
    import base64

    return base64.b64encode(blob or b"").decode()


@pytest.mark.asyncio
async def test_credential_rotation_is_validated_before_it_replaces_the_stored_secret(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    cid = (await create(app, keys))["id"]
    before = next(iter(repo._rows.values())).secret_ciphertext

    bad = await call(
        app,
        "PATCH",
        f"/connections/{cid}",
        user(keys),
        json={"azure_client_secret": "not-valid-yet"},
    )
    assert bad.status_code == 400
    assert next(iter(repo._rows.values())).secret_ciphertext == before  # old credential kept

    cloud.valid_secrets = {SECRET_2}  # the customer rotated the secret in Entra
    ok = await call(
        app, "PATCH", f"/connections/{cid}", user(keys), json={"azure_client_secret": SECRET_2}
    )
    assert ok.status_code == 200 and SECRET_2 not in ok.text
    assert next(iter(repo._rows.values())).secret_ciphertext != before

    # The new secret is what data calls now use.
    azure_session_store.clear()
    cloud.token_form.clear()
    data = await call(
        app, "GET", f"/azure/connections/{cid}/subscriptions/{SUB_OK}/resource-groups", user(keys)
    )
    assert data.status_code == 200 and cloud.token_form[0]["client_secret"] == SECRET_2


@pytest.mark.asyncio
async def test_stored_credential_that_is_no_longer_valid_asks_for_a_new_secret(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    cid = (await create(app, keys))["id"]
    cloud.valid_secrets = {SECRET_2}  # secret rotated/expired at the cloud provider
    azure_session_store.clear()
    response = await call(
        app, "GET", f"/azure/connections/{cid}/subscriptions/{SUB_OK}/overview", user(keys)
    )
    assert response.status_code == 400
    detail = response.json()["error"]["message"]
    assert (
        detail["error_code"] == "STORED_CREDENTIAL_REJECTED"
        and "new client secret" in detail["message"]
    )
    # reconnect = re-validation with a corrected secret
    fixed = await call(
        app, "PATCH", f"/connections/{cid}", user(keys), json={"azure_client_secret": SECRET_2}
    )
    assert fixed.status_code == 200


@pytest.mark.asyncio
async def test_revalidation_updates_integration_status(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    cid = (await create(app, keys))["id"]
    cloud.perm_mode = "arm_only"  # access reduced after the connection was saved
    validated = (await call(app, "POST", f"/connections/{cid}/validate", user(keys))).json()
    assert states(validated)["cost_management"] == "permission_denied"
    legacy = await call(
        app,
        "POST",
        "/connections/validate",
        user(keys),
        json={"connection_id": cid, "provider": "azure", "scope_id": SUB_OK},
    )
    assert (
        legacy.status_code == 200
        and "cost_management: permission_denied" in legacy.json()["details"]
    )


@pytest.mark.asyncio
async def test_delete_removes_the_credential_and_cached_token(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    cid = (await create(app, keys))["id"]
    await call(
        app, "GET", f"/azure/connections/{cid}/subscriptions/{SUB_OK}/resource-groups", user(keys)
    )
    assert cid in azure_session_store._sessions
    assert (await call(app, "DELETE", f"/connections/{cid}", user(keys))).status_code == 204
    assert repo._rows == {} and cid not in azure_session_store._sessions
    assert (await call(app, "GET", f"/connections/{cid}", user(keys))).status_code == 404
    assert (await call(app, "DELETE", f"/connections/{cid}", user(keys))).status_code == 404


@pytest.mark.asyncio
async def test_edit_name_without_changing_the_secret(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    cid = (await create(app, keys))["id"]
    before = next(iter(repo._rows.values())).secret_ciphertext
    renamed = await call(app, "PATCH", f"/connections/{cid}", user(keys), json={"name": "Renamed"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Renamed"
    assert next(iter(repo._rows.values())).secret_ciphertext == before


# --------------------------------------------------------------------------------------
# Secure storage failures, store outages, logging
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_without_an_encryption_key_nothing_is_saved_and_no_cloud_call_is_made(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo, connection_encryption_keys='{"bad": "###"}')
    response = await call(app, "POST", "/connections", user(keys), json=payload())
    assert response.status_code == 503
    assert response.json()["error"]["message"]["error_code"] == "CREDENTIAL_STORE_UNAVAILABLE"
    assert repo._rows == {} and cloud.requests == []


@pytest.mark.asyncio
async def test_unreadable_stored_credential_after_key_loss_is_explicit(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    cid = (await create(make_app(keys, cloud, repo), keys))["id"]
    reset_cipher_cache()
    other_key = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
    app = make_app(
        keys,
        cloud,
        repo,
        connection_encryption_keys=json.dumps({"other": other_key}),
        connection_active_key_id="other",
    )
    response = await call(app, "POST", f"/connections/{cid}/validate", user(keys))
    assert response.status_code == 409
    assert response.json()["error"]["message"]["error_code"] == "CREDENTIAL_UNREADABLE"


class BrokenRepo(InMemoryConnectionRepository):
    async def list(self, _owner: str) -> list[Any]:
        raise SQLAlchemyError("relation does not exist")

    async def count(self, _owner: str) -> int:
        raise SQLAlchemyError("relation does not exist")


@pytest.mark.asyncio
async def test_database_problems_are_an_explicit_503_and_do_not_hide_organization_connections(
    keys: Any, cloud: FakeCloud
) -> None:
    app = make_app(keys, cloud, BrokenRepo())
    created = await call(app, "POST", "/connections", user(keys), json=payload())
    assert created.status_code == 503
    assert created.json()["error"]["message"]["error_code"] == "DATABASE_UNAVAILABLE"
    assert cloud.requests == []  # nothing validated or saved

    listed = await call(app, "GET", "/connections", user(keys))
    assert listed.status_code == 200 and listed.headers["x-owned-connections"] == "unavailable"


@pytest.mark.asyncio
async def test_no_secret_in_logs_or_error_responses(
    keys: Any,
    cloud: FakeCloud,
    repo: InMemoryConnectionRepository,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    app = make_app(keys, cloud, repo)
    with structlog.testing.capture_logs() as captured:
        cid = (await create(app, keys))["id"]
        responses = [
            await call(
                app,
                "POST",
                "/connections",
                user(keys),
                json=payload(azure_client_secret="leak-me-please-1"),
            ),
            await call(
                app,
                "POST",
                "/connections",
                user(keys),
                json={"provider": "azure", "azure_client_secret": SECRET},
            ),
            await call(
                app,
                "PATCH",
                f"/connections/{cid}",
                user(keys),
                json={"azure_client_secret": "leak-me-please-2"},
            ),
            await call(
                app,
                "PATCH",
                f"/connections/{cid}",
                user(keys),
                json={"azure_client_secret": SECRET_2, "x": 1},
            ),
        ]
    everything = " ".join(
        [r.getMessage() for r in caplog.records]
        + [json.dumps(e, default=str) for e in captured]
        + [r.text for r in responses]
    )
    for secret in (SECRET, SECRET_2, "leak-me-please-1", "leak-me-please-2"):
        assert secret not in everything


# --------------------------------------------------------------------------------------
# Authentication methods are explicit and never switched silently
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cli_and_managed_identity_are_explicit_and_not_silent_fallbacks(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_subprocess(*_a: Any, **_k: Any) -> None:
        raise AssertionError("the Azure CLI must not be started")

    monkeypatch.setattr(subprocess, "run", no_subprocess)
    app = make_app(keys, cloud, repo)
    body = payload(auth_method="azure_cli")
    for k in ("azure_client_id", "azure_client_secret"):
        del body[k]
    cli = await call(app, "POST", "/connections", user(keys), json=body)
    assert cli.status_code == 400  # not enabled in production
    assert cli.json()["error"]["message"]["error_code"] == "AUTH_METHOD_NOT_AVAILABLE"

    body["auth_method"] = "managed_identity"
    mi = await call(app, "POST", "/connections", user(keys), json=body)
    assert mi.status_code == 400  # no managed identity on this host: explicit error, no fallback
    assert mi.json()["error"]["message"]["category"] == "managed_identity_unavailable"
    assert repo._rows == {} and cloud.requests == []


@pytest.mark.asyncio
async def test_failed_service_principal_never_falls_back_to_another_identity(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    response = await call(
        app, "POST", "/connections", user(keys), json=payload(azure_client_secret="wrong")
    )
    assert response.status_code == 400
    assert [f["client_id"] for f in cloud.token_form] == [
        CLIENT
    ]  # only the supplied identity was tried
    assert cloud.arm_calls() == []


# --------------------------------------------------------------------------------------
# Authentication / authorization of the application user (separate from cloud credentials)
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_apis_require_application_authentication(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    cid = "11111111-1111-1111-1111-111111111111"
    for method, path in (
        ("GET", "/connections"),
        ("POST", "/connections"),
        ("GET", f"/connections/{cid}"),
        ("PATCH", f"/connections/{cid}"),
        ("DELETE", f"/connections/{cid}"),
        ("POST", f"/connections/{cid}/validate"),
    ):
        assert (await call(app, method, path, None, json={})).status_code == 401, (method, path)
        forged = {"Authorization": "Bearer " + make_token(new_rsa_key()[0])}
        assert (await call(app, method, path, forged, json={})).status_code == 401
    no_scope = {"Authorization": "Bearer " + make_token(keys[0], scp="")}
    assert (await call(app, "GET", "/connections", no_scope)).status_code == 403
    assert cloud.requests == [] and repo._rows == {}


@pytest.mark.asyncio
async def test_application_login_token_is_never_used_as_a_cloud_credential(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    token = user(keys)["Authorization"].split()[1]
    await create(app, keys)
    assert all(token not in (r.headers.get("authorization") or "") for r in cloud.requests)
    assert all(token not in r.content.decode(errors="ignore") for r in cloud.requests)


@pytest.mark.asyncio
async def test_owner_comes_from_the_token_not_the_request(
    keys: Any, cloud: FakeCloud, repo: InMemoryConnectionRepository
) -> None:
    app = make_app(keys, cloud, repo)
    response = await call(
        app,
        "POST",
        "/connections",
        user(keys, "alice"),
        json=payload(owner="bob", owner_oid="bob", user_id="bob"),
    )
    assert response.status_code == 201  # unknown owner fields are ignored, never trusted
    assert next(iter(repo._rows.values())).owner_key.endswith(":alice")


def test_vm_constant_is_used() -> None:  # keeps the shared import meaningful
    assert VM_ID.startswith("/subscriptions/")
