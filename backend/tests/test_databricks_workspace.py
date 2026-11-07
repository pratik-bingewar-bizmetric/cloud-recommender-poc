"""Comprehensive automated tests for multi-workspace Databricks connectivity and discovery.

Tests:
- Azure workspace connection resolution and live client creation
- AWS workspace connection resolution
- Authentication failure handling and credential scrubbing
- Permission-denied per-category responses
- Partial discovery failure resilience (one category failure does not block others)
- Empty resource list handling
- Workspace isolation
- Connection health and capability reporting
- FastAPI endpoints for /api/v1/databricks
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.main import create_app
from cloud_recommender.schemas.databricks import (
    CategoryDiscoveryStatus,
    DatabricksCloud,
)
from cloud_recommender.services.databricks.auth import DatabricksAuthService
from cloud_recommender.services.databricks.discovery_service import (
    DatabricksDiscoveryService,
)
from cloud_recommender.services.databricks.workspace_service import (
    DatabricksWorkspaceService,
)


@pytest.fixture
def test_app() -> FastAPI:
    """Fixture providing FastAPI test instance."""
    s = Settings(
        catalog_offline_mode=True,
        entra_auth_enabled=False,
    )
    app = create_app(settings=s)
    app.dependency_overrides[get_settings] = lambda: s
    return app


def test_auth_service_scrubs_sensitive_secrets() -> None:
    """Verify secrets are redacted from error output and exception strings."""
    with patch.dict("os.environ", {"DATABRICKS_CLIENT_SECRET": "super-secret-key-12345"}):
        auth_service = DatabricksAuthService()
        raw_error = "Error connecting with secret super-secret-key-12345 to host."
        scrubbed = auth_service.scrub_sensitive(raw_error)
        assert "super-secret-key-12345" not in scrubbed
        assert "[REDACTED_SECRET]" in scrubbed


def test_auth_service_azure_cli_strategy() -> None:
    """Verify Azure Databricks host triggers azure-cli auth strategy."""
    auth_service = DatabricksAuthService()
    with patch("cloud_recommender.services.databricks.auth.WorkspaceClient") as mock_wc:
        auth_service.create_workspace_client(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            cloud="azure",
        )
        mock_wc.assert_called_with(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            auth_type="azure-cli",
        )


def test_auth_service_oauth_sp_strategy() -> None:
    """Verify explicit client_id and client_secret triggers OAuth SP strategy."""
    auth_service = DatabricksAuthService()
    with patch("cloud_recommender.services.databricks.auth.WorkspaceClient") as mock_wc:
        auth_service.create_workspace_client(
            host="https://dbc-8e061b63-c3bf.cloud.databricks.com",
            cloud="aws",
            client_id="sp-client-123",
            client_secret="sp-secret-456",
        )
        mock_wc.assert_called_with(
            host="https://dbc-8e061b63-c3bf.cloud.databricks.com",
            client_id="sp-client-123",
            client_secret="sp-secret-456",
        )


def test_auth_service_test_connection_success() -> None:
    """Verify successful connection returns authenticated user identity."""
    auth_service = DatabricksAuthService()
    mock_client = MagicMock()
    mock_me = MagicMock()
    mock_me.user_name = "test.user@company.com"
    mock_client.current_user.me.return_value = mock_me

    with patch.object(auth_service, "create_workspace_client", return_value=mock_client):
        success, details, user = auth_service.test_connection(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            cloud="azure",
        )
        assert success is True
        assert user == "test.user@company.com"
        assert "Successfully authenticated" in details


def test_auth_service_test_connection_auth_failure() -> None:
    """Verify auth failure returns graceful error details without unhandled exceptions."""
    auth_service = DatabricksAuthService()
    with patch.object(
        auth_service,
        "create_workspace_client",
        side_effect=ValueError("default auth: cannot configure default credentials"),
    ):
        success, details, user = auth_service.test_connection(
            host="https://dbc-8e061b63-c3bf.cloud.databricks.com",
            cloud="aws",
        )
        assert success is False
        assert user is None
        assert "No valid credentials found" in details


@pytest.mark.asyncio
async def test_discovery_service_all_categories_success() -> None:
    """Verify discovery queries all 8 categories and classifies them properly."""
    mock_client = MagicMock()

    # Workspace user
    mock_me = MagicMock()
    mock_me.user_name = "architect@cloud.local"
    mock_client.current_user.me.return_value = mock_me

    # Clusters
    cl = MagicMock()
    cl.cluster_id = "cl-1"
    cl.cluster_name = "Analytics Cluster"
    cl.state.value = "RUNNING"
    cl.spark_version = "14.3.x-scala2.12"
    cl.node_type_id = "Standard_D4s_v5"
    cl.num_workers = 4
    cl.autoscale = None
    cl.creator_user_name = "architect@cloud.local"
    mock_client.clusters.list.return_value = [cl]

    # Warehouses
    wh = MagicMock()
    wh.id = "wh-1"
    wh.name = "Prod SQL Warehouse"
    wh.state.value = "RUNNING"
    wh.cluster_size = "Medium"
    wh.auto_stop_mins = 15
    wh.num_clusters = 1
    wh.creator_name = "architect@cloud.local"
    mock_client.warehouses.list.return_value = [wh]

    # Jobs
    j = MagicMock()
    j.job_id = 101
    j.settings.name = "Daily ETL"
    j.settings.tasks = [MagicMock(), MagicMock()]
    j.settings.schedule.quartz_cron_expression = "0 0 * * * ?"
    j.creator_user_name = "etl-service@cloud.local"
    mock_client.jobs.list.return_value = [j]

    # Empty pipelines, model serving, apps, catalogs
    mock_client.pipelines.list_pipelines.return_value = []
    mock_client.serving_endpoints.list.return_value = []
    mock_client.catalogs.list.return_value = []
    mock_client.apps.list.return_value = []

    auth_service = MagicMock()
    auth_service.create_workspace_client.return_value = (mock_client, None)
    auth_service.scrub_sensitive = lambda t: t

    discovery_service = DatabricksDiscoveryService(auth_service=auth_service)
    resp = await discovery_service.discover_workspace(
        connection_id="databricks-azure-dev",
        host="https://adb-642006393507276.16.azuredatabricks.net",
        cloud=DatabricksCloud.AZURE,
        workspace_id="642006393507276",
        workspace_name="Azure Dev",
    )

    assert resp.overall_status == "completed"
    assert resp.categories["clusters"].status == CategoryDiscoveryStatus.AVAILABLE
    assert resp.categories["clusters"].resource_count == 1
    assert resp.categories["warehouses"].status == CategoryDiscoveryStatus.AVAILABLE
    assert resp.categories["jobs"].status == CategoryDiscoveryStatus.AVAILABLE
    assert resp.categories["pipelines"].status == CategoryDiscoveryStatus.NO_RESOURCES_FOUND
    assert resp.total_resources_count == 4  # 1 workspace + 1 cluster + 1 warehouse + 1 job


@pytest.mark.asyncio
async def test_discovery_service_permission_denied_isolation() -> None:
    """Verify that permission failure in one category (e.g. Unity Catalog) does NOT fail clusters."""
    mock_client = MagicMock()

    mock_me = MagicMock()
    mock_me.user_name = "data-engineer@cloud.local"
    mock_client.current_user.me.return_value = mock_me

    # Clusters work
    cl = MagicMock()
    cl.cluster_id = "cl-dev"
    cl.cluster_name = "Dev Cluster"
    cl.state.value = "TERMINATED"
    cl.autoscale = None
    cl.creator_user_name = "dev"
    mock_client.clusters.list.return_value = [cl]

    # Unity Catalog raises 403 Permission Denied
    mock_client.catalogs.list.side_effect = Exception("HTTP 403: User lacks USE_CATALOG permission")

    # Others empty
    mock_client.warehouses.list.return_value = []
    mock_client.jobs.list.return_value = []
    mock_client.pipelines.list_pipelines.return_value = []
    mock_client.serving_endpoints.list.return_value = []
    mock_client.apps.list.return_value = []

    auth_service = MagicMock()
    auth_service.create_workspace_client.return_value = (mock_client, None)
    auth_service.scrub_sensitive = lambda t: t

    discovery_service = DatabricksDiscoveryService(auth_service=auth_service)
    resp = await discovery_service.discover_workspace(
        connection_id="databricks-azure-dev",
        host="https://adb-642006393507276.16.azuredatabricks.net",
        cloud=DatabricksCloud.AZURE,
        workspace_id="642006393507276",
        workspace_name="Azure Dev",
    )

    # Overall is partial_failure because Unity Catalog failed
    assert resp.overall_status == "partial_failure"
    assert resp.categories["clusters"].status == CategoryDiscoveryStatus.AVAILABLE
    assert resp.categories["unity_catalog"].status == CategoryDiscoveryStatus.PERMISSION_DENIED
    assert "Permission denied" in (resp.categories["unity_catalog"].error_message or "")


@pytest.mark.asyncio
async def test_workspace_service_list_and_health() -> None:
    """Verify listing connections and computing health summary."""
    service = DatabricksWorkspaceService()
    conns = service.list_connections()
    assert len(conns) >= 2
    ws_ids = {c.workspace_id for c in conns}
    assert "642006393507276" in ws_ids
    assert "2250283018608626" in ws_ids

    # Health check
    health = await service.get_health("databricks-azure-dev")
    assert health.workspace_id == "642006393507276"
    assert health.cloud == DatabricksCloud.AZURE


@pytest.mark.asyncio
async def test_fastapi_databricks_endpoints(test_app: FastAPI) -> None:
    """Verify HTTP endpoints under /api/v1/databricks."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List connections
        resp = await client.get("/api/v1/databricks/connections")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        conn_ids = [c["connection_id"] for c in data]
        assert "databricks-azure-dev" in conn_ids
        assert "databricks-finops-dev" in conn_ids

        # 2. Get connection details
        resp_detail = await client.get("/api/v1/databricks/connections/databricks-azure-dev")
        assert resp_detail.status_code == 200
        assert resp_detail.json()["workspace_id"] == "642006393507276"

        # 3. Nonexistent connection 404
        resp_404 = await client.get("/api/v1/databricks/connections/non-existent")
        assert resp_404.status_code == 404

        # 4. Health endpoint
        resp_health = await client.get("/api/v1/databricks/connections/databricks-azure-dev/health")
        assert resp_health.status_code == 200
        assert resp_health.json()["connection_id"] == "databricks-azure-dev"
