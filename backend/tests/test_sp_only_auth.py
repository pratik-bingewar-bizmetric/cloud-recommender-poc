"""Comprehensive test suite for Service Principal-Only authentication and application sessions."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from cloud_recommender.core.app_sessions import AppSessionStore, get_app_session_store
from cloud_recommender.main import create_app
from cloud_recommender.schemas.azure_live import DataAccessState, DataDomain, DataSource
from cloud_recommender.services.azure_live.credentials import AzureCredentialError, AzureToken
from cloud_recommender.services.azure_live.session_store import (
    azure_session_store,
)

TENANT_ID = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
SUBSCRIPTION_ID = "33333333-3333-3333-3333-333333333333"
CLIENT_SECRET = "super-secret-client-credential-never-leak"


def make_data_source(api: str = "GET /subscriptions/{id}") -> DataSource:
    return DataSource(
        connection_id="conn-mock",
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        subscription_id=SUBSCRIPTION_ID,
        api=api,
        fetched_at=datetime.now(UTC),
    )


def get_error_detail(response) -> dict[str, Any]:
    body = response.json()
    if "error" in body and isinstance(body["error"], dict) and "message" in body["error"]:
        msg = body["error"]["message"]
        if isinstance(msg, dict):
            return msg
    if "detail" in body and isinstance(body["detail"], dict):
        return body["detail"]
    return body


@pytest.fixture(autouse=True)
def reset_stores() -> None:
    store = get_app_session_store()
    store.clear()
    azure_session_store.clear()


@pytest.fixture
def mock_app():
    return create_app()


@pytest.fixture
def client(mock_app):
    return TestClient(mock_app)


def test_app_session_store_token_hashing_and_lifecycle():
    """Verify session token is stored only as SHA-256 hash, and lifecycle works."""
    store = AppSessionStore(default_ttl_seconds=3600)
    raw_token, session = store.create_session(
        account_name="Production FinOps",
        tenant_id=TENANT_ID,
        subscription_id=SUBSCRIPTION_ID,
        subscription_name="Prod Subscription",
        client_id=CLIENT_ID,
        connection_id="conn-123456",
    )

    assert raw_token.startswith("finops_sess_")
    token_hash = store.hash_token(raw_token)
    assert session.token_hash == token_hash
    # The raw token must NOT be stored inside the session object
    assert raw_token not in str(session.__dict__)

    # Lookup by token
    resolved = store.get_session_by_token(raw_token)
    assert resolved is not None
    assert resolved.account_name == "Production FinOps"
    assert resolved.session_id == session.session_id

    # Lookup by invalid token
    assert store.get_session_by_token("finops_sess_invalid_token") is None

    # Revoke session
    assert store.revoke_session(session.session_id) is True
    assert store.get_session_by_token(raw_token) is None
    assert store.get_session_by_hash(token_hash).revoked_at is not None


def test_app_session_store_expiration():
    """Verify expired sessions are rejected."""
    fixed_time = datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC)
    current_time = fixed_time

    def clock():
        return current_time

    store = AppSessionStore(default_ttl_seconds=60, clock=clock)
    raw_token, session = store.create_session(
        account_name="Expiring Account",
        tenant_id=TENANT_ID,
        subscription_id=SUBSCRIPTION_ID,
        subscription_name="Test Sub",
        client_id=CLIENT_ID,
        connection_id="conn-exp",
    )

    assert store.get_session_by_token(raw_token) is not None

    # Fast forward beyond TTL (61 seconds)
    current_time = fixed_time + timedelta(seconds=61)
    assert store.get_session_by_token(raw_token) is None


@pytest.mark.asyncio
async def test_auth_connect_success(client):
    """Test successful POST /api/v1/auth/connect."""
    fake_token = AzureToken(value="mock-arm-access-token", expires_at=time.time() + 3600)

    with (
        patch(
            "cloud_recommender.api.routes.auth.acquire_service_principal_token",
            new=AsyncMock(return_value=fake_token),
        ),
        patch(
            "cloud_recommender.api.routes.auth.AzureLiveDataService.verify_subscription",
            new=AsyncMock(
                return_value=DataDomain(
                    domain="requested_subscription",
                    state=DataAccessState.ACCESSIBLE,
                    items=[
                        {
                            "subscription_id": SUBSCRIPTION_ID,
                            "display_name": "Core Enterprise",
                            "state": "Enabled",
                        }
                    ],
                    source=make_data_source("GET /subscriptions/{id}"),
                    http_status=200,
                )
            ),
        ),
        patch(
            "cloud_recommender.api.routes.auth.AzureLiveDataService.cost",
            new=AsyncMock(
                return_value=DataDomain(
                    domain="cost",
                    state=DataAccessState.ACCESSIBLE,
                    items=[],
                    source=make_data_source("POST /providers/Microsoft.CostManagement/query"),
                    http_status=200,
                )
            ),
        ),
    ):
        response = client.post(
            "/api/v1/auth/connect",
            json={
                "account_name": "Azure Enterprise Production",
                "subscription_id": SUBSCRIPTION_ID,
                "tenant_id": TENANT_ID,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_token" in data
        assert data["session_token"].startswith("finops_sess_")
        assert data["account_name"] == "Azure Enterprise Production"
        assert data["subscription_name"] == "Core Enterprise"
        assert data["roles"] == ["FinOpsAdmin"]
        assert data["permissions"]["reader"] is True
        assert data["permissions"]["cost_management_reader"] is True

        session_token = data["session_token"]

        # Now test calling protected /api/v1/auth/session with bearer token
        session_resp = client.get(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        assert session_resp.status_code == 200
        sess_data = session_resp.json()
        assert sess_data["account_id"] == data["account_id"]
        assert sess_data["subscription_id"] == SUBSCRIPTION_ID

        # Test listing live connections via GET /api/v1/azure/connections
        conn_resp = client.get(
            "/api/v1/azure/connections",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        assert conn_resp.status_code == 200
        conns = conn_resp.json()
        assert len(conns) == 1
        assert conns[0]["connection_id"] == data["connection_id"]

        # Test single connection detail via GET /api/v1/azure/connections/{connection_id}
        detail_resp = client.get(
            f"/api/v1/azure/connections/{data['connection_id']}",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        assert detail_resp.status_code == 200
        assert detail_resp.json()["connection_id"] == data["connection_id"]

        # Test logout POST /api/v1/auth/logout
        logout_resp = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        assert logout_resp.status_code == 200
        assert logout_resp.json()["status"] == "logged_out"

        # Subsequent call with revoked token must fail with SESSION_REVOKED (401)
        subsequent_resp = client.get(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        assert subsequent_resp.status_code == 401
        err = get_error_detail(subsequent_resp)
        assert err["error_code"] == "SESSION_REVOKED"


@pytest.mark.asyncio
async def test_auth_connect_invalid_azure_credentials(client):
    """Test invalid client secret returns 400 with actionable error."""
    with patch(
        "cloud_recommender.api.routes.auth.acquire_service_principal_token",
        side_effect=AzureCredentialError(
            "invalid_client_secret", "The client secret is incorrect.", aadsts="7000215"
        ),
    ):
        response = client.post(
            "/api/v1/auth/connect",
            json={
                "account_name": "Azure Enterprise Production",
                "subscription_id": SUBSCRIPTION_ID,
                "tenant_id": TENANT_ID,
                "client_id": CLIENT_ID,
                "client_secret": "wrong-secret",
            },
        )

        assert response.status_code == 400
        detail = get_error_detail(response)
        assert detail["error_code"] == "INVALID_AZURE_CREDENTIALS"
        assert detail["category"] == "invalid_client_secret"
        assert detail["aadsts"] == "7000215"


@pytest.mark.asyncio
async def test_auth_connect_subscription_permission_denied(client):
    """Test service principal lacking Reader access on subscription returns 403."""
    fake_token = AzureToken(value="mock-arm-access-token", expires_at=time.time() + 3600)

    with (
        patch(
            "cloud_recommender.api.routes.auth.acquire_service_principal_token",
            new=AsyncMock(return_value=fake_token),
        ),
        patch(
            "cloud_recommender.api.routes.auth.AzureLiveDataService.verify_subscription",
            new=AsyncMock(
                return_value=DataDomain(
                    domain="requested_subscription",
                    state=DataAccessState.PERMISSION_DENIED,
                    message="The service principal has no access to this subscription.",
                    required_permission="Reader",
                    source=make_data_source("GET /subscriptions/{id}"),
                    http_status=403,
                )
            ),
        ),
    ):
        response = client.post(
            "/api/v1/auth/connect",
            json={
                "account_name": "Azure Enterprise Production",
                "subscription_id": SUBSCRIPTION_ID,
                "tenant_id": TENANT_ID,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
        )

        assert response.status_code == 403
        detail = get_error_detail(response)
        assert detail["error_code"] == "SUBSCRIPTION_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_auth_connect_subscription_disabled(client):
    """Test subscription in Disabled state returns 400."""
    fake_token = AzureToken(value="mock-arm-access-token", expires_at=time.time() + 3600)

    with (
        patch(
            "cloud_recommender.api.routes.auth.acquire_service_principal_token",
            new=AsyncMock(return_value=fake_token),
        ),
        patch(
            "cloud_recommender.api.routes.auth.AzureLiveDataService.verify_subscription",
            new=AsyncMock(
                return_value=DataDomain(
                    domain="requested_subscription",
                    state=DataAccessState.ACCESSIBLE,
                    items=[
                        {
                            "subscription_id": SUBSCRIPTION_ID,
                            "display_name": "Disabled Sub",
                            "state": "Disabled",
                        }
                    ],
                    source=make_data_source("GET /subscriptions/{id}"),
                    http_status=200,
                )
            ),
        ),
    ):
        response = client.post(
            "/api/v1/auth/connect",
            json={
                "account_name": "Azure Enterprise Production",
                "subscription_id": SUBSCRIPTION_ID,
                "tenant_id": TENANT_ID,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
        )

        assert response.status_code == 400
        detail = get_error_detail(response)
        assert detail["error_code"] == "SUBSCRIPTION_DISABLED"


def test_auth_invalid_bearer_token(client):
    """Test invalid session token returns 401 INVALID_SESSION_TOKEN."""
    response = client.get(
        "/api/v1/auth/session",
        headers={"Authorization": "Bearer finops_sess_nonexistent_token_123"},
    )
    assert response.status_code == 401
    detail = get_error_detail(response)
    assert detail["error_code"] == "INVALID_SESSION_TOKEN"


def test_multi_tenant_owner_isolation(client):
    """Test that Session A cannot access or see Session B's live connections."""
    store = get_app_session_store()
    raw_token_a, session_a = store.create_session(
        account_name="Tenant A Account",
        tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        subscription_id=SUBSCRIPTION_ID,
        subscription_name="Sub A",
        client_id="11111111-1111-1111-1111-111111111111",
        connection_id="conn-tenant-a",
    )
    raw_token_b, session_b = store.create_session(
        account_name="Tenant B Account",
        tenant_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        subscription_id=SUBSCRIPTION_ID,
        subscription_name="Sub B",
        client_id="22222222-2222-2222-2222-222222222222",
        connection_id="conn-tenant-b",
    )

    fake_token = AzureToken(value="mock-token", expires_at=time.time() + 3600)
    # Register conn-tenant-a under owner A
    owner_a = f"{session_a.tenant_id}:{session_a.account_id}"
    azure_session_store.create(
        owner_key=owner_a,
        tenant_id=session_a.tenant_id,
        client_id=session_a.client_id,
        token=fake_token,
        connection_id="conn-tenant-a",
    )

    # Register conn-tenant-b under owner B
    owner_b = f"{session_b.tenant_id}:{session_b.account_id}"
    azure_session_store.create(
        owner_key=owner_b,
        tenant_id=session_b.tenant_id,
        client_id=session_b.client_id,
        token=fake_token,
        connection_id="conn-tenant-b",
    )

    # Tenant A lists connections: sees only conn-tenant-a
    resp_a = client.get(
        "/api/v1/azure/connections",
        headers={"Authorization": f"Bearer {raw_token_a}"},
    )
    assert resp_a.status_code == 200
    ids_a = [c["connection_id"] for c in resp_a.json()]
    assert "conn-tenant-a" in ids_a
    assert "conn-tenant-b" not in ids_a

    # Tenant A attempts to fetch conn-tenant-b directly -> 404
    resp_b_from_a = client.get(
        "/api/v1/azure/connections/conn-tenant-b",
        headers={"Authorization": f"Bearer {raw_token_a}"},
    )
    assert resp_b_from_a.status_code == 404
