"""Comprehensive automated test suite for GCP Phase 1: Service Account Authentication,
Multi-Service Connectivity, Resource Discovery, and Persistent Encrypted Connection Management.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from cloud_recommender.core.auth import AuthenticatedUser
from cloud_recommender.core.config import Settings
from cloud_recommender.core.secret_vault import CredentialCipher, KeyRing
from cloud_recommender.db.repositories.connection_repo import (
    InMemoryConnectionRepository,
)
from cloud_recommender.main import app
from cloud_recommender.schemas.gcp import (
    GcpServiceConnectivityState,
    GcpServiceStatus,
    GcpTestConnectionResponse,
)
from cloud_recommender.services.connections.connection_manager import ConnectionManager
from cloud_recommender.services.gcp.auth_service import (
    GcpAuthenticationError,
    GcpAuthService,
)
from cloud_recommender.services.gcp.connectivity_service import GcpConnectivityService

# Sample test RSA key format
MOCK_PRIVATE_KEY = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC3/v4rN3P3Fk8y\n"
    "-----END PRIVATE KEY-----\n"
)

VALID_SA_DICT = {
    "type": "service_account",
    "project_id": "cloud-recommender-pricing-dev",
    "private_key_id": "de7e66b1e92c1234567890abcdef",
    "private_key": MOCK_PRIVATE_KEY,
    "client_email": "finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com",
    "client_id": "112233445566778899001",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/finops-gcp-reader%40cloud-recommender-pricing-dev.iam.gserviceaccount.com",
}

VALID_SA_JSON = json.dumps(VALID_SA_DICT)


# ---------------------------------------------------------------------------
# 1. Authentication & Validation Tests
# ---------------------------------------------------------------------------


def test_parse_and_validate_json_success() -> None:
    svc = GcpAuthService()
    parsed, info = svc.parse_and_validate_json(VALID_SA_JSON)
    assert parsed["type"] == "service_account"
    assert info.project_id == "cloud-recommender-pricing-dev"
    assert (
        info.client_email
        == "finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com"
    )
    assert info.private_key_id == "de7e66b1e92c1234567890abcdef"
    # Ensure info model does NOT hold the private key
    assert not hasattr(info, "private_key")


def test_parse_and_validate_json_malformed() -> None:
    svc = GcpAuthService()
    with pytest.raises(GcpAuthenticationError) as exc:
        svc.parse_and_validate_json("{not valid json}")
    assert exc.value.error_code == "INVALID_JSON"


def test_parse_and_validate_json_wrong_type() -> None:
    svc = GcpAuthService()
    bad_type = dict(VALID_SA_DICT, type="authorized_user")
    with pytest.raises(GcpAuthenticationError) as exc:
        svc.parse_and_validate_json(bad_type)
    assert exc.value.error_code == "INVALID_CREDENTIAL_TYPE"


def test_parse_and_validate_json_missing_private_key() -> None:
    svc = GcpAuthService()
    no_key = dict(VALID_SA_DICT)
    del no_key["private_key"]
    with pytest.raises(GcpAuthenticationError) as exc:
        svc.parse_and_validate_json(no_key)
    assert exc.value.error_code == "MISSING_PRIVATE_KEY"


def test_parse_and_validate_json_malformed_private_key() -> None:
    svc = GcpAuthService()
    bad_pem = dict(VALID_SA_DICT, private_key="not a pem key")
    with pytest.raises(GcpAuthenticationError) as exc:
        svc.parse_and_validate_json(bad_pem)
    assert exc.value.error_code == "INVALID_PRIVATE_KEY_FORMAT"


def test_parse_and_validate_json_rejects_azure_uuid() -> None:
    svc = GcpAuthService()
    uuid_proj = dict(VALID_SA_DICT, project_id=str(uuid.uuid4()))
    with pytest.raises(GcpAuthenticationError) as exc:
        svc.parse_and_validate_json(uuid_proj)
    assert exc.value.error_code == "INVALID_PROJECT_ID"


def test_parse_and_validate_json_mismatched_project() -> None:
    svc = GcpAuthService()
    with pytest.raises(GcpAuthenticationError) as exc:
        svc.parse_and_validate_json(VALID_SA_DICT, expected_project_id="other-project-id")
    assert exc.value.error_code == "PROJECT_ID_MISMATCH"


def test_acquire_token_caching_and_mocked_refresh() -> None:
    svc = GcpAuthService()
    mock_creds = MagicMock()
    mock_creds.token = "mock-gcp-bearer-token-12345"
    mock_creds.expiry = None

    with patch(
        "google.oauth2.service_account.Credentials.from_service_account_info",
        return_value=mock_creds,
    ):
        tok1 = svc.acquire_token(VALID_SA_DICT)
        assert tok1 == "mock-gcp-bearer-token-12345"
        mock_creds.refresh.assert_called_once()

        # Second call should use cache
        tok2 = svc.acquire_token(VALID_SA_DICT)
        assert tok2 == "mock-gcp-bearer-token-12345"
        assert mock_creds.refresh.call_count == 1


# ---------------------------------------------------------------------------
# 2. Connectivity & Discovery Probes Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connectivity_service_probes_success() -> None:
    mock_auth = MagicMock()
    mock_auth.parse_and_validate_json.return_value = (
        VALID_SA_DICT,
        GcpAuthService().parse_and_validate_json(VALID_SA_DICT)[1],
    )
    mock_auth.acquire_token.return_value = "mock_token"

    # Mock responses for all endpoints
    async def fake_handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "cloudresourcemanager.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "projectId": "cloud-recommender-pricing-dev",
                    "displayName": "Dev Project",
                    "state": "ACTIVE",
                },
                request=request,
            )
        if host == "serviceusage.googleapis.com":
            return httpx.Response(
                200,
                json={"services": [{"name": "projects/123/services/cloudasset.googleapis.com"}]},
                request=request,
            )
        if host == "cloudasset.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "//compute.googleapis.com/projects/p/zones/z/instances/vm1",
                            "assetType": "compute.googleapis.com/Instance",
                        }
                    ]
                },
                request=request,
            )
        if host == "storage.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"name": "my-test-bucket", "location": "US", "storageClass": "STANDARD"}
                    ]
                },
                request=request,
            )
        if host == "sqladmin.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "name": "db-inst-1",
                            "region": "us-central1",
                            "databaseVersion": "POSTGRES_15",
                        }
                    ]
                },
                request=request,
            )
        if host == "compute.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "items": {
                        "zones/us-central1-a": {
                            "instances": [
                                {
                                    "name": "vm-app-1",
                                    "machineType": "e2-medium",
                                    "status": "RUNNING",
                                }
                            ]
                        }
                    }
                },
                request=request,
            )
        if host == "monitoring.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "metricDescriptors": [
                        {
                            "type": "compute.googleapis.com/instance/cpu/utilization",
                            "monitoredResourceTypes": ["gce_instance"],
                        }
                    ]
                },
                request=request,
            )
        if host == "recommender.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "recommendations": [
                        {
                            "name": "recs/r1",
                            "recommenderSubtype": "IDLE_RESOURCE",
                            "description": "Stop idle VM",
                        }
                    ]
                },
                request=request,
            )
        return httpx.Response(404, json={}, request=request)

    transport = httpx.MockTransport(fake_handler)
    conn_svc = GcpConnectivityService(auth_service=mock_auth, transport=transport)

    test_res = await conn_svc.test_connection(VALID_SA_JSON, "cloud-recommender-pricing-dev")
    assert test_res.success is True
    assert test_res.overall_status == "Connected"
    assert test_res.project_id == "cloud-recommender-pricing-dev"
    assert len(test_res.services) == 8
    for s in test_res.services:
        assert s.status == GcpServiceConnectivityState.SUCCESS

    # Test full resource discovery and deduplication
    discovery = await conn_svc.discover_resources(VALID_SA_JSON, "cloud-recommender-pricing-dev")
    assert discovery.project_id == "cloud-recommender-pricing-dev"
    assert discovery.total_resources >= 4
    types = [r.resource_type for r in discovery.resources]
    assert "compute.googleapis.com/Instance" in types
    assert "storage.googleapis.com/Bucket" in types
    assert "sqladmin.googleapis.com/Instance" in types
    assert len(discovery.recommendations) == 1
    assert discovery.monitoring is not None
    assert discovery.monitoring.metric_descriptors_count == 1


@pytest.mark.asyncio
async def test_connectivity_service_api_disabled_and_permission_denied() -> None:
    mock_auth = MagicMock()
    mock_auth.parse_and_validate_json.return_value = (
        VALID_SA_DICT,
        GcpAuthService().parse_and_validate_json(VALID_SA_DICT)[1],
    )
    mock_auth.acquire_token.return_value = "mock_token"

    async def fake_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "cloudresourcemanager" in url:
            return httpx.Response(
                200,
                json={"projectId": "cloud-recommender-pricing-dev", "state": "ACTIVE"},
                request=request,
            )
        if "cloudasset" in url:
            # 403 API disabled
            return httpx.Response(
                403,
                json={
                    "error": {
                        "code": 403,
                        "status": "PERMISSION_DENIED",
                        "message": "Cloud Asset API has not been used in project or is disabled.",
                    }
                },
                request=request,
            )
        if "compute" in url:
            # 403 Permission denied
            return httpx.Response(
                403,
                json={
                    "error": {
                        "code": 403,
                        "status": "PERMISSION_DENIED",
                        "message": "Required 'compute.instances.list' permission.",
                    }
                },
                request=request,
            )
        if "storage" in url:
            # 503 Service unavailable
            return httpx.Response(503, json={"error": "backend error"}, request=request)
        return httpx.Response(200, json={}, request=request)

    transport = httpx.MockTransport(fake_handler)
    conn_svc = GcpConnectivityService(auth_service=mock_auth, transport=transport)

    test_res = await conn_svc.test_connection(VALID_SA_JSON, "cloud-recommender-pricing-dev")
    # crm succeeded, so overall is Partially Connected
    assert test_res.overall_status == "Partially Connected"
    status_map = {s.service: s.status for s in test_res.services}
    assert status_map["cloud_asset_inventory"] == GcpServiceConnectivityState.API_DISABLED
    assert status_map["compute_engine"] == GcpServiceConnectivityState.PERMISSION_DENIED
    assert status_map["cloud_storage"] == GcpServiceConnectivityState.SERVICE_UNAVAILABLE


# ---------------------------------------------------------------------------
# 3. Persistent Connection & Encryption Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_gcp_connection_lifecycle() -> None:
    repo = InMemoryConnectionRepository()
    cipher = CredentialCipher(KeyRing({"test-key-v1": b"0" * 32}, "test-key-v1"))
    settings = Settings(connections_max_per_user=5)
    owner_key = "test-tenant-01:test-user-01"

    manager = ConnectionManager(
        repo=repo,
        cipher_factory=lambda: cipher,
        settings=settings,
    )

    # Mock connectivity service
    with patch(
        "cloud_recommender.services.gcp.connectivity_service.GcpConnectivityService.test_connection"
    ) as mock_test:
        from cloud_recommender.schemas.gcp import GcpTestConnectionResponse

        mock_test.return_value = GcpTestConnectionResponse(
            success=True,
            project_id="cloud-recommender-pricing-dev",
            client_email="finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com",
            private_key_id="de7e66b1e92c1234567890abcdef",
            overall_status="Connected",
            billing_status="DEFERRED",
            services=[],
        )

        # 1. Create GCP connection
        created = await manager.create_gcp(
            owner_key=owner_key,
            name="Dev GCP Account",
            project_id="cloud-recommender-pricing-dev",
            service_account_json=VALID_SA_JSON,
        )

        assert created.provider == "gcp"
        assert created.project_id == "cloud-recommender-pricing-dev"
        assert (
            created.client_email
            == "finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com"
        )
        assert created.private_key_id == "de7e66b1e92c1234567890abcdef"
        assert created.billing_status == "DEFERRED"

        # Verify ciphertext in repo is encrypted and does not contain plaintext JSON
        raw_record = await repo.get(owner_key, created.id)
        assert raw_record is not None
        assert raw_record.secret_ciphertext is not None
        assert b"private_key" not in raw_record.secret_ciphertext
        assert raw_record.secret_kid == "test-key-v1"

        # 2. List GCP connections
        conn_list = await manager.list_gcp(owner_key)
        assert len(conn_list) == 1
        assert conn_list[0].id == created.id

        # 3. Get GCP connection
        fetched = await manager.get_gcp(owner_key, created.id)
        assert fetched.id == created.id

        # 4. Decrypt secret for backend usage
        rec, decrypted_json = await manager.decrypt_gcp_secret(owner_key, created.id)
        assert rec.id == created.id
        decrypted_dict = json.loads(decrypted_json)
        assert decrypted_dict["client_email"] == VALID_SA_DICT["client_email"]

        # 5. Delete GCP connection
        await manager.delete(owner_key, created.id)
        deleted_rec = await repo.get(owner_key, created.id)
        assert deleted_rec is None


@pytest.mark.asyncio
async def test_tenant_owner_isolation_enforcement() -> None:
    repo = InMemoryConnectionRepository()
    cipher = CredentialCipher(KeyRing({"test-key-v1": b"0" * 32}, "test-key-v1"))
    settings = Settings(connections_max_per_user=5)
    owner1 = "tenant-a:user-1"
    owner2 = "tenant-b:user-2"

    manager = ConnectionManager(
        repo=repo,
        cipher_factory=lambda: cipher,
        settings=settings,
    )

    with patch(
        "cloud_recommender.services.gcp.connectivity_service.GcpConnectivityService.test_connection"
    ) as mock_test:
        from cloud_recommender.schemas.gcp import GcpTestConnectionResponse

        mock_test.return_value = GcpTestConnectionResponse(
            success=True,
            project_id="cloud-recommender-pricing-dev",
            client_email="finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com",
            private_key_id="de7e66b1e92c1234567890abcdef",
            overall_status="Connected",
            billing_status="DEFERRED",
            services=[],
        )

        created = await manager.create_gcp(
            owner_key=owner1,
            name="Tenant A GCP",
            project_id="cloud-recommender-pricing-dev",
            service_account_json=VALID_SA_JSON,
        )

        # Owner 2 cannot see or access Owner 1's connection
        owner2_list = await manager.list_gcp(owner2)
        assert len(owner2_list) == 0

        with pytest.raises(HTTPException) as exc:
            await manager.get_gcp(owner2, created.id)
        assert exc.value.status_code == 404

        with pytest.raises(HTTPException) as exc:
            await manager.decrypt_gcp_secret(owner2, created.id)
        assert exc.value.status_code == 404

        with pytest.raises(HTTPException) as exc:
            await manager.delete(owner2, created.id)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# 4. FastAPI Endpoints Integration Tests
# ---------------------------------------------------------------------------


def test_api_test_connection_endpoint() -> None:
    from cloud_recommender.api.routes.gcp import get_connectivity_service
    from cloud_recommender.core.auth import get_current_user
    from cloud_recommender.schemas.gcp import GcpTestConnectionResponse

    fake_user = AuthenticatedUser(
        sub="test-user-01",
        tenant_id="test-tenant",
        account_id="test-user",
        roles=["Reader"],
        scopes=["access_as_user"],
        is_authenticated=True,
        is_development_identity=True,
    )
    app.dependency_overrides[get_current_user] = lambda: fake_user

    from unittest.mock import AsyncMock, MagicMock

    mock_conn = MagicMock()
    mock_conn.test_connection = AsyncMock(
        return_value=GcpTestConnectionResponse(
            success=True,
            project_id="cloud-recommender-pricing-dev",
            client_email="finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com",
            private_key_id="de7e66b1e92c1234567890abcdef",
            overall_status="Connected",
            billing_status="DEFERRED",
            services=[],
        )
    )
    app.dependency_overrides[get_connectivity_service] = lambda: mock_conn

    client = TestClient(app)
    resp = client.post(
        "/api/v1/gcp/connections/test",
        json={
            "connection_name": "Test GCP",
            "project_id": "cloud-recommender-pricing-dev",
            "service_account_json": VALID_SA_JSON,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["project_id"] == "cloud-recommender-pricing-dev"
    assert data["billing_status"] == "DEFERRED"
    # Ensure zero secrets in response
    assert "private_key" not in data
    assert '"private_key":' not in json.dumps(data)
    assert '"token":' not in json.dumps(data)

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 5. Phase 1.1 Reliability, Security & Edge Case Tests
# ---------------------------------------------------------------------------


def test_sanitize_auth_error_removes_tokens_and_keys() -> None:
    from cloud_recommender.services.gcp.auth_service import _sanitize_auth_error

    err_with_token = "Error occurred with ya29.c.b0AY2e-test_token_string in response."
    clean = _sanitize_auth_error(err_with_token)
    assert "ya29." not in clean
    assert "[REDACTED_TOKEN]" in clean

    err_with_key = (
        "Failed loading key: -----BEGIN PRIVATE KEY-----\nMIIEvgIBADANB\n-----END PRIVATE KEY-----"
    )
    clean_key = _sanitize_auth_error(err_with_key)
    assert "BEGIN PRIVATE KEY" not in clean_key
    assert "[REDACTED_KEY]" in clean_key

    err_with_query = "https://example.com?key=AIzaSyA_secret_key&foo=bar"
    clean_query = _sanitize_auth_error(err_with_query)
    assert "AIzaSyA" not in clean_query
    assert "key=[REDACTED]" in clean_query


def test_token_cache_isolation_by_email_and_key_id() -> None:
    svc = GcpAuthService()
    creds1 = dict(VALID_SA_DICT, client_email="sa1@project.iam.gserviceaccount.com")
    creds2 = dict(VALID_SA_DICT, client_email="sa2@project.iam.gserviceaccount.com")

    mock_c1 = MagicMock()
    mock_c1.token = "token-for-sa1"
    mock_c1.expiry = None

    mock_c2 = MagicMock()
    mock_c2.token = "token-for-sa2"
    mock_c2.expiry = None

    with patch(
        "google.oauth2.service_account.Credentials.from_service_account_info",
        side_effect=[mock_c1, mock_c2],
    ):
        t1 = svc.acquire_token(creds1)
        t2 = svc.acquire_token(creds2)
        assert t1 == "token-for-sa1"
        assert t2 == "token-for-sa2"
        assert t1 != t2


def test_transport_error_classification_in_token_refresh() -> None:
    from google.auth.exceptions import TransportError

    svc = GcpAuthService()
    mock_c = MagicMock()
    mock_c.refresh.side_effect = TransportError(
        "Network timeout connecting to oauth2.googleapis.com"
    )

    with patch(
        "google.oauth2.service_account.Credentials.from_service_account_info",
        return_value=mock_c,
    ):
        with pytest.raises(GcpAuthenticationError) as exc:
            svc.acquire_token(VALID_SA_DICT)
        assert exc.value.error_code == "SERVICE_UNAVAILABLE"
        assert "transport error" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_compute_engine_deferred_when_billing_unconfigured() -> None:
    mock_auth = MagicMock()
    mock_auth.parse_and_validate_json.return_value = (
        VALID_SA_DICT,
        GcpAuthService().parse_and_validate_json(VALID_SA_DICT)[1],
    )
    mock_auth.acquire_token.return_value = "mock_token"

    async def fake_handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "cloudresourcemanager.googleapis.com":
            return httpx.Response(
                200,
                json={"projectId": "cloud-recommender-pricing-dev", "state": "ACTIVE"},
                request=request,
            )
        if host == "compute.googleapis.com":
            return httpx.Response(
                403,
                json={
                    "error": {
                        "code": 403,
                        "message": "Compute Engine API has not been used in project 963778958698 before or it is disabled. Enable it by visiting https://console.developers.google.com/apis/api/compute.googleapis.com/overview?project=963778958698 then retry. If you enabled this API recently, wait a few minutes for the action to propagate to our systems and retry.",
                        "status": "PERMISSION_DENIED",
                        "details": [{"@type": "type.googleapis.com/google.rpc.Help"}],
                    }
                },
                request=request,
            )
        if host == "monitoring.googleapis.com":
            return httpx.Response(200, json={"metricDescriptors": []}, request=request)
        if host == "recommender.googleapis.com":
            return httpx.Response(200, json={"recommendations": []}, request=request)
        return httpx.Response(200, json={}, request=request)

    transport = httpx.MockTransport(fake_handler)
    conn_svc = GcpConnectivityService(auth_service=mock_auth, transport=transport)

    test_res = await conn_svc.test_connection(VALID_SA_JSON, "cloud-recommender-pricing-dev")
    compute_status = next(s for s in test_res.services if s.service == "compute_engine")
    assert compute_status.status == GcpServiceConnectivityState.DEFERRED
    # Overall status should still be Connected because compute is DEFERRED (billing policy)
    assert test_res.overall_status == "Connected"
    assert test_res.success is True

    # In resource discovery, compute deferred status should NOT mark partial_discovery = True
    discovery = await conn_svc.discover_resources(VALID_SA_JSON, "cloud-recommender-pricing-dev")
    assert discovery.partial_discovery is False
    assert any("Compute Engine: DEFERRED" in n for n in discovery.discovery_notes)


@pytest.mark.asyncio
async def test_empty_monitoring_and_recommender_success() -> None:
    mock_auth = MagicMock()
    mock_auth.parse_and_validate_json.return_value = (
        VALID_SA_DICT,
        GcpAuthService().parse_and_validate_json(VALID_SA_DICT)[1],
    )
    mock_auth.acquire_token.return_value = "mock_token"

    async def fake_handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "monitoring.googleapis.com":
            return httpx.Response(200, json={"metricDescriptors": []}, request=request)
        if host == "recommender.googleapis.com":
            return httpx.Response(200, json={"recommendations": []}, request=request)
        return httpx.Response(200, json={}, request=request)

    transport = httpx.MockTransport(fake_handler)
    conn_svc = GcpConnectivityService(auth_service=mock_auth, transport=transport)

    async with httpx.AsyncClient(transport=transport) as client:
        mon_status, mon_sum = await conn_svc.check_monitoring(client, "tok", "proj")
        assert mon_status.status == GcpServiceConnectivityState.SUCCESS
        assert mon_sum.metric_descriptors_count == 0
        assert "0 metric descriptors found" in mon_status.message

        rec_status, recs = await conn_svc.check_recommender(client, "tok", "proj")
        assert rec_status.status == GcpServiceConnectivityState.SUCCESS
        assert len(recs) == 0
        assert "0 recommendations found" in rec_status.message


@pytest.mark.asyncio
async def test_pagination_and_deduplication() -> None:
    mock_auth = MagicMock()
    mock_auth.parse_and_validate_json.return_value = (
        VALID_SA_DICT,
        GcpAuthService().parse_and_validate_json(VALID_SA_DICT)[1],
    )
    mock_auth.acquire_token.return_value = "mock_token"

    req_counts: dict[str, int] = {"asset": 0, "storage": 0}

    async def fake_handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "cloudasset.googleapis.com":
            req_counts["asset"] += 1
            page_token = request.url.params.get("pageToken")
            if not page_token:
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {"name": "//compute.googleapis.com/r1", "assetType": "type1"},
                            {"name": "//compute.googleapis.com/r2", "assetType": "type2"},
                        ],
                        "nextPageToken": "page-2-token",
                    },
                    request=request,
                )
            else:
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "name": "//compute.googleapis.com/r2",
                                "assetType": "type2",
                            },  # duplicate
                            {"name": "//compute.googleapis.com/r3", "assetType": "type3"},
                        ],
                    },
                    request=request,
                )
        if host == "storage.googleapis.com":
            req_counts["storage"] += 1
            page_token = request.url.params.get("pageToken")
            if not page_token:
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {"name": "b1", "location": "US"},
                            {"name": "b2", "location": "US"},
                        ],
                        "nextPageToken": "tok2",
                    },
                    request=request,
                )
            return httpx.Response(
                200,
                json={"items": [{"name": "b3", "location": "EU"}]},
                request=request,
            )
        return httpx.Response(200, json={}, request=request)

    transport = httpx.MockTransport(fake_handler)
    conn_svc = GcpConnectivityService(auth_service=mock_auth, transport=transport)

    async with httpx.AsyncClient(transport=transport) as client:
        asset_st, assets = await conn_svc.check_asset_inventory(client, "tok", "proj")
        assert asset_st.status == GcpServiceConnectivityState.SUCCESS
        assert len(assets) == 3  # r1, r2, r3 (r2 deduped)
        assert req_counts["asset"] == 2

        storage_st, buckets = await conn_svc.check_storage(client, "tok", "proj")
        assert storage_st.status == GcpServiceConnectivityState.SUCCESS
        assert len(buckets) == 3  # b1, b2, b3
        assert req_counts["storage"] == 2


@pytest.mark.asyncio
async def test_connection_manager_validation_and_duplicate_handling() -> None:
    repo = InMemoryConnectionRepository()
    ring = KeyRing({"key-1": b"0123456789abcdef0123456789abcdef"}, active_kid="key-1")
    cipher = CredentialCipher(ring)
    settings = Settings(connections_max_per_user=5)

    mock_conn = MagicMock()
    mock_conn.test_connection = AsyncMock(
        return_value=GcpTestConnectionResponse(
            success=True,
            project_id="cloud-recommender-pricing-dev",
            client_email="finops-gcp-reader@cloud-recommender-pricing-dev.iam.gserviceaccount.com",
            private_key_id="de7e66b1e92c1234567890abcdef",
            overall_status="Connected",
            billing_status="DEFERRED",
            services=[
                GcpServiceStatus(
                    service="compute_engine",
                    service_name="Compute Engine",
                    status=GcpServiceConnectivityState.DEFERRED,
                    api_endpoint="https://compute.googleapis.com",
                    message="Compute API deferred.",
                ),
                GcpServiceStatus(
                    service="cloud_resource_manager",
                    service_name="Cloud Resource Manager",
                    status=GcpServiceConnectivityState.SUCCESS,
                    api_endpoint="https://cloudresourcemanager.googleapis.com",
                    message="Active",
                ),
            ],
        )
    )

    with patch(
        "cloud_recommender.services.gcp.connectivity_service.get_gcp_connectivity_service",
        return_value=mock_conn,
    ):
        manager = ConnectionManager(
            repo=repo,
            cipher_factory=lambda: cipher,
            settings=settings,
        )

        # Invalid name validation
        with pytest.raises(HTTPException) as exc:
            await manager.create_gcp("u1", " ", "cloud-recommender-pricing-dev", VALID_SA_JSON)
        assert exc.value.status_code == 422

        # Invalid project ID validation
        with pytest.raises(HTTPException) as exc:
            await manager.create_gcp("u1", "Valid Name", "abc", VALID_SA_JSON)
        assert exc.value.status_code == 422

        # Valid create
        created = await manager.create_gcp(
            "u1", "Valid GCP", "cloud-recommender-pricing-dev", VALID_SA_JSON
        )
        assert created.status == "connected"

        # Duplicate project connection rejected
        with pytest.raises(HTTPException) as exc:
            await manager.create_gcp(
                "u1", "Second GCP", "cloud-recommender-pricing-dev", VALID_SA_JSON
            )
        assert exc.value.status_code == 409

        # Validate method supports GCP and maps DEFERRED status
        revalidated = await manager.validate("u1", created.id)
        assert revalidated.id == created.id
        # Check that integrations list has deferred state for compute
        compute_integ = next(
            (i for i in revalidated.integrations if i.integration == "compute_engine"), None
        )
        assert compute_integ is not None
        from cloud_recommender.schemas.connections import IntegrationState

        assert compute_integ.state == IntegrationState.DEFERRED
