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

import json
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.main import create_app
from cloud_recommender.schemas.databricks import (
    CategoryDiscoveryStatus,
    DatabricksCloud,
    DatabricksConnectionStatus,
    DatabricksResourceState,
)
from cloud_recommender.services.databricks.auth import (
    AzureCliCredentialProvider,
    DatabricksAuthError,
    DatabricksAuthService,
)
from cloud_recommender.services.databricks.billing_ingestion_service import (
    BillingIngestionService,
)
from cloud_recommender.services.databricks.discovery_service import (
    DatabricksDiscoveryService,
)
from cloud_recommender.services.databricks.sql_client import (
    DatabricksSqlService,
    WarehouseStoppedError,
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


def test_azure_cli_provider_detection() -> None:
    """Verify is_cli_installed returns True when az/az.cmd is found, False otherwise."""
    provider = AzureCliCredentialProvider()
    with patch(
        "cloud_recommender.services.databricks.auth.shutil.which", return_value="C:\\path\\az.cmd"
    ):
        assert provider.is_cli_installed() is True
    with patch("cloud_recommender.services.databricks.auth.shutil.which", return_value=None):
        assert provider.is_cli_installed() is False


def test_azure_cli_provider_session_validation_success() -> None:
    """Verify validate_cli_session returns user info on zero returncode."""
    provider = AzureCliCredentialProvider()
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = json.dumps(
        {"user": {"name": "pratik.bingewar@bizmetric.com", "type": "user"}}
    )
    with (
        patch.object(provider, "_find_az_executable", return_value="az.cmd"),
        patch("cloud_recommender.services.databricks.auth.subprocess.run", return_value=mock_res),
    ):
        is_logged_in, user, data = provider.validate_cli_session()
        assert is_logged_in is True
        assert user == "pratik.bingewar@bizmetric.com"
        assert data is not None


def test_azure_cli_provider_session_validation_unauthenticated() -> None:
    """Verify validate_cli_session returns failure and actionable login guidance when not logged in."""
    provider = AzureCliCredentialProvider()
    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stderr = "Please run 'az login' to setup account."
    with (
        patch.object(provider, "_find_az_executable", return_value="az.cmd"),
        patch("cloud_recommender.services.databricks.auth.subprocess.run", return_value=mock_res),
    ):
        is_logged_in, user_or_err, data = provider.validate_cli_session()
        assert is_logged_in is False
        assert "az login" in user_or_err
        assert data is None


def test_azure_cli_provider_token_acquisition_and_caching() -> None:
    """Verify token acquisition caches token in memory and dynamically refreshes."""
    provider = AzureCliCredentialProvider(ttl_buffer_seconds=300)
    now = int(time.time())
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = json.dumps(
        {
            "accessToken": "mock-token-xyz",
            "expires_on": now + 3600,
        }
    )

    with (
        patch.object(provider, "_find_az_executable", return_value="az.cmd"),
        patch(
            "cloud_recommender.services.databricks.auth.subprocess.run", return_value=mock_res
        ) as mock_run,
    ):
        token1 = provider.get_access_token()
        assert token1 == "mock-token-xyz"
        assert mock_run.call_count == 1

        token2 = provider.get_access_token()
        assert token2 == "mock-token-xyz"
        assert mock_run.call_count == 1

        token3 = provider.get_access_token(force_refresh=True)
        assert token3 == "mock-token-xyz"
        assert mock_run.call_count == 2

        headers = provider.get_auth_headers()
        assert headers == {"Authorization": "Bearer mock-token-xyz"}


def test_azure_cli_provider_missing_cli_raises() -> None:
    """Verify get_access_token raises DatabricksAuthError when az is missing."""
    provider = AzureCliCredentialProvider()
    with patch.object(provider, "_find_az_executable", return_value=None):
        with pytest.raises(DatabricksAuthError, match="not installed or not found"):
            provider.get_access_token()


def test_azure_cli_provider_token_error_scrubbing() -> None:
    """Verify secret strings are redacted from token acquisition error messages."""
    provider = AzureCliCredentialProvider()
    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stderr = "Failed with secret-token-12345 in response"
    with (
        patch.object(provider, "_find_az_executable", return_value="az.cmd"),
        patch("cloud_recommender.services.databricks.auth.subprocess.run", return_value=mock_res),
        patch.dict("os.environ", {"DATABRICKS_CLIENT_SECRET": "secret-token-12345"}),
    ):
        with pytest.raises(DatabricksAuthError) as exc_info:
            provider.get_access_token()
        assert "secret-token-12345" not in str(exc_info.value)
        assert "[REDACTED_SECRET]" in str(exc_info.value)


def test_environment_separation_dev_vs_prod() -> None:
    """Verify DEV_LOCAL uses Azure CLI while PROD requires OAuth M2M SP credentials."""
    mock_az_provider = MagicMock()
    mock_az_provider.is_cli_installed.return_value = True
    mock_az_provider.validate_cli_session.return_value = (True, "dev-user@company.com", {})

    auth_service = DatabricksAuthService(azure_cli_provider=mock_az_provider)

    with patch("cloud_recommender.services.databricks.auth.WorkspaceClient") as mock_wc:
        # DEV_LOCAL: environment="development" triggers azure-cli
        auth_service.create_workspace_client(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            cloud="azure",
            environment="development",
        )
        mock_wc.assert_called_with(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            auth_type="azure-cli",
        )

    # PROD: environment="production" requires SP credentials and fails closed if missing
    prod_settings_no_sp = Settings(
        app_env="production",
        databricks_client_id=None,
        databricks_client_secret=None,
    )
    auth_service_prod = DatabricksAuthService(
        settings=prod_settings_no_sp,
        azure_cli_provider=mock_az_provider,
    )
    with (
        patch.dict("os.environ", {"DATABRICKS_CLIENT_ID": "", "DATABRICKS_CLIENT_SECRET": ""}),
        pytest.raises(DatabricksAuthError, match="refusing silent fallback"),
    ):
        auth_service_prod.create_workspace_client(
            host="https://adb-7405608085231210.10.azuredatabricks.net",
            cloud="azure",
            environment="production",
        )

    # PROD with SP credentials succeeds with oauth-m2m
    prod_settings_with_sp = Settings(
        app_env="production",
        databricks_client_id="prod-sp-id",
        databricks_client_secret="prod-sp-secret-val",
    )
    auth_service_prod_ok = DatabricksAuthService(settings=prod_settings_with_sp)
    with patch("cloud_recommender.services.databricks.auth.WorkspaceClient") as mock_wc:
        auth_service_prod_ok.create_workspace_client(
            host="https://adb-7405608085231210.10.azuredatabricks.net",
            cloud="azure",
            environment="production",
        )
        mock_wc.assert_called_with(
            host="https://adb-7405608085231210.10.azuredatabricks.net",
            client_id="prod-sp-id",
            client_secret="prod-sp-secret-val",
            auth_type="oauth-m2m",
        )


def test_auth_service_azure_cli_strategy() -> None:
    """Verify Azure Databricks host triggers azure-cli fallback when in dev environment."""
    isolated_settings = Settings(databricks_client_id=None, databricks_client_secret=None)
    mock_az_provider = MagicMock()
    mock_az_provider.is_cli_installed.return_value = True
    mock_az_provider.validate_cli_session.return_value = (True, "dev-user@company.com", {})
    auth_service = DatabricksAuthService(
        settings=isolated_settings, azure_cli_provider=mock_az_provider
    )
    with (
        patch.dict("os.environ", {"DATABRICKS_CLIENT_ID": "", "DATABRICKS_CLIENT_SECRET": ""}),
        patch("cloud_recommender.services.databricks.auth.WorkspaceClient") as mock_wc,
    ):
        auth_service.create_workspace_client(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            cloud="azure",
            environment="development",
        )
        mock_wc.assert_called_with(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            auth_type="azure-cli",
        )


def test_auth_service_settings_sp_precedence_over_azure_cli() -> None:
    """Verify valid Settings (.env) SP credentials lock auth_type='oauth-m2m' in production."""
    sp_settings = Settings(
        app_env="production",
        databricks_auth_type="oauth-m2m",
        databricks_client_id="test-sp-client-id-0001",
        databricks_client_secret="valid-runtime-secret-value",
    )
    auth_service = DatabricksAuthService(settings=sp_settings)
    with patch("cloud_recommender.services.databricks.auth.WorkspaceClient") as mock_wc:
        auth_service.create_workspace_client(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            cloud="azure",
            profile="azure-dev",
            environment="production",
        )
        mock_wc.assert_called_with(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            client_id="test-sp-client-id-0001",
            client_secret="valid-runtime-secret-value",
            auth_type="oauth-m2m",
        )


def test_auth_service_skips_placeholder_sp_falls_back_to_azure_cli() -> None:
    """Verify placeholder SP credentials in azure-cli mode fall back to azure-cli."""
    placeholder_settings = Settings(
        databricks_auth_type="azure-cli",
        databricks_client_id="your-client-id",
        databricks_client_secret="changeme",
    )
    mock_az_provider = MagicMock()
    mock_az_provider.is_cli_installed.return_value = True
    mock_az_provider.validate_cli_session.return_value = (True, "dev-user@company.com", {})
    auth_service = DatabricksAuthService(
        settings=placeholder_settings, azure_cli_provider=mock_az_provider
    )
    with (
        patch.dict("os.environ", {"DATABRICKS_CLIENT_ID": "", "DATABRICKS_CLIENT_SECRET": ""}),
        patch("cloud_recommender.services.databricks.auth.WorkspaceClient") as mock_wc,
    ):
        auth_service.create_workspace_client(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            cloud="azure",
            environment="development",
        )
        mock_wc.assert_called_with(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            auth_type="azure-cli",
        )


def test_auth_service_oauth_mode_never_falls_back_to_azure_cli() -> None:
    """Verify oauth-m2m mode fails closed and never falls back to azure-cli."""
    oauth_settings = Settings(
        databricks_auth_type="oauth-m2m",
        databricks_client_id=None,
        databricks_client_secret=None,
    )
    auth_service = DatabricksAuthService(settings=oauth_settings)
    with (
        patch.dict("os.environ", {"DATABRICKS_CLIENT_ID": "", "DATABRICKS_CLIENT_SECRET": ""}),
        pytest.raises(DatabricksAuthError),
    ):
        auth_service.create_workspace_client(
            host="https://adb-642006393507276.16.azuredatabricks.net",
            cloud="azure",
        )


def test_auth_service_oauth_sp_strategy() -> None:
    """Verify explicit client_id and client_secret triggers locked OAuth M2M SP strategy."""
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
            auth_type="oauth-m2m",
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

    # Empty pipelines, model serving, apps, catalogs, policies, pools, mlflow, job_runs
    mock_client.pipelines.list_pipelines.return_value = []
    mock_client.serving_endpoints.list.return_value = []
    mock_client.catalogs.list.return_value = []
    mock_client.apps.list.return_value = []
    mock_client.cluster_policies.list.return_value = []
    mock_client.instance_pools.list.return_value = []
    mock_client.jobs.list_runs.return_value = []
    mock_client.experiments.search_experiments.return_value = []
    mock_client.experiments.list_experiments.return_value = []

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
    mock_client.cluster_policies.list.return_value = []
    mock_client.instance_pools.list.return_value = []
    mock_client.jobs.list_runs.return_value = []
    mock_client.experiments.search_experiments.return_value = []
    mock_client.experiments.list_experiments.return_value = []

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
    mock_wc = MagicMock()
    mock_wc.current_user.me.return_value = MagicMock(user_name="dev@test.com")
    mock_wc.clusters.list.return_value = []
    mock_wc.warehouses.list.return_value = []
    mock_wc.jobs.list.return_value = []
    mock_wc.pipelines.list_pipelines.return_value = []
    mock_wc.serving_endpoints.list.return_value = []
    mock_wc.catalogs.list.return_value = []
    mock_wc.apps.list.return_value = []
    mock_wc.cluster_policies.list.return_value = []
    mock_wc.instance_pools.list.return_value = []
    mock_wc.jobs.list_runs.return_value = []
    mock_wc.experiments.search_experiments.return_value = []
    mock_wc.experiments.list_experiments.return_value = []
    with patch(
        "cloud_recommender.services.databricks.auth.DatabricksAuthService.create_workspace_client",
        return_value=mock_wc,
    ):
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
        mock_wc = MagicMock()
        mock_wc.current_user.me.return_value = MagicMock(user_name="dev@test.com")
        mock_wc.clusters.list.return_value = []
        mock_wc.warehouses.list.return_value = []
        mock_wc.jobs.list.return_value = []
        mock_wc.pipelines.list_pipelines.return_value = []
        mock_wc.serving_endpoints.list.return_value = []
        mock_wc.catalogs.list.return_value = []
        mock_wc.apps.list.return_value = []
        mock_wc.cluster_policies.list.return_value = []
        mock_wc.instance_pools.list.return_value = []
        mock_wc.jobs.list_runs.return_value = []
        mock_wc.experiments.search_experiments.return_value = []
        mock_wc.experiments.list_experiments.return_value = []
        with patch(
            "cloud_recommender.services.databricks.auth.DatabricksAuthService.create_workspace_client",
            return_value=mock_wc,
        ):
            resp_health = await client.get(
                "/api/v1/databricks/connections/databricks-azure-dev/health"
            )
            assert resp_health.status_code == 200
            assert resp_health.json()["connection_id"] == "databricks-azure-dev"


# =============================================================================
# M1 Tests: Auth Diagnostics, Multi-Workspace Registry & SQL Client Integrity
# =============================================================================


def test_m1_auth_production_never_falls_back_to_personal_cli() -> None:
    """Verify production app_env never silently falls back to personal Azure CLI credentials."""
    prod_settings = Settings(
        app_env="production",
        databricks_auth_type="azure-cli",
        databricks_client_id=None,
        databricks_client_secret=None,
    )
    auth_service = DatabricksAuthService(settings=prod_settings)
    with patch.dict("os.environ", {"DATABRICKS_CLIENT_ID": "", "DATABRICKS_CLIENT_SECRET": ""}):
        with pytest.raises(DatabricksAuthError) as exc:
            auth_service.create_workspace_client(
                host="https://adb-7405608085231210.10.azuredatabricks.net",
                cloud="azure",
            )
    assert "refusing silent fallback" in str(exc.value).lower()


def test_m1_auth_scrubs_bearer_and_pat_tokens() -> None:
    """Verify Bearer JWTs and dapi tokens are always redacted from logs/error text."""
    # Built at runtime so secret scanners do not flag the dummy PAT literal in source.
    raw = (
        "Auth failed with Bearer eyJhbGciOiJSUzI1NiJ9.payload12345.sig67890 and "
        + "dapi"
        + "0123456789abcdef0123456789abcdef"
    )
    scrubbed = DatabricksAuthService.scrub_sensitive(raw)
    assert "payload12345" not in scrubbed
    assert "dapi0123456789" not in scrubbed
    assert "[REDACTED_TOKEN]" in scrubbed


@pytest.mark.asyncio
async def test_m1_workspace_registry_registers_dev_and_prod_from_config() -> None:
    """Verify Dev (642006393507276) and Prod (7405608085231210) come from env/Settings and stay isolated."""
    DatabricksWorkspaceService._shared_workspaces.clear()
    DatabricksWorkspaceService._discovery_cache.clear()
    cfg = Settings(
        databricks_dev_workspace_id="642006393507276",
        databricks_dev_host="https://adb-642006393507276.16.azuredatabricks.net",
        databricks_dev_warehouse_id="05ed10a52697a344",
        databricks_prod_workspace_id="7405608085231210",
        databricks_prod_host="https://adb-7405608085231210.10.azuredatabricks.net",
        databricks_prod_warehouse_id="prod-wh-99887766",
    )
    service = DatabricksWorkspaceService(settings=cfg)
    conns = {c.connection_id: c for c in service.list_connections()}

    assert "databricks-azure-dev" in conns
    assert conns["databricks-azure-dev"].workspace_id == "642006393507276"
    assert conns["databricks-azure-dev"].warehouse_id == "05ed10a52697a344"

    assert "databricks-azure-prod" in conns
    assert conns["databricks-azure-prod"].workspace_id == "7405608085231210"
    assert (
        conns["databricks-azure-prod"].workspace_url
        == "https://adb-7405608085231210.10.azuredatabricks.net"
    )
    assert conns["databricks-azure-prod"].warehouse_id == "prod-wh-99887766"
    assert "7840192837148901" not in {c.workspace_id for c in conns.values()}


@pytest.mark.asyncio
async def test_m1_workspace_connection_status_classification_and_isolation() -> None:
    """Verify test_connection distinguishes CONNECTED, 403 PERMISSION_DENIED, AUTH_FAILED, and preserves isolation."""
    DatabricksWorkspaceService._shared_workspaces.clear()
    DatabricksWorkspaceService._discovery_cache.clear()
    cfg = Settings(
        databricks_auth_type="oauth",
        databricks_prod_warehouse_id="prod-wh-1122",
    )
    auth_service = DatabricksAuthService(settings=cfg)
    ws_service = DatabricksWorkspaceService(auth_service=auth_service, settings=cfg)

    with patch.object(
        auth_service,
        "test_connection",
        side_effect=[
            (
                False,
                "Permission denied: Databricks Service Principal OAuth token was rejected (403 access_denied: Workspace 642006393507276 is inaccessible).",
                None,
            ),
            (
                False,
                "Service Principal / credential authentication failed: HTTP 401 invalid_client",
                None,
            ),
            (
                True,
                "Successfully authenticated as 'sp-finops-prod'.",
                "sp-finops-prod",
            ),
        ],
    ):
        dev_res = await ws_service.test_connection("databricks-azure-dev")
        prod_fail = await ws_service.test_connection("databricks-azure-prod")
        prod_ok = await ws_service.test_connection("databricks-azure-prod")

    assert dev_res.success is False
    assert dev_res.status == DatabricksConnectionStatus.PERMISSION_DENIED

    assert prod_fail.success is False
    assert prod_fail.status == DatabricksConnectionStatus.AUTH_FAILED

    assert prod_ok.success is True
    assert prod_ok.status == DatabricksConnectionStatus.CONNECTED
    assert prod_ok.current_user == "sp-finops-prod"
    # Dev remains isolated in PERMISSION_DENIED even after Prod connects
    dev_conn = ws_service.get_connection("databricks-azure-dev")
    assert dev_conn is not None
    assert dev_conn.status == DatabricksConnectionStatus.PERMISSION_DENIED


def test_m1_sql_client_ignores_llm_mock_and_classifies_warehouse_errors() -> None:
    """Verify llm_provider='mock' does not suppress live warehouse checks and errors classify accurately."""
    oauth_with_mock_llm = Settings(
        llm_provider="mock",
        databricks_auth_type="oauth",
        databricks_warehouse_id="05ed10a52697a344",
        finops_signing_secret="finops-test-signing-secret-2026-min-32-chars-long",
        finops_signing_kid="k1-2026",
    )

    # 1. Invalid credentials (401) -> AUTH_ERROR (not STOPPED)
    auth_fail_client = MagicMock()
    auth_fail_client.current_user.me.side_effect = Exception("HTTP 401 invalid_client")
    svc_auth_err = DatabricksSqlService(
        settings=oauth_with_mock_llm,
        workspace_client=auth_fail_client,
        warehouse_id="wh-custom-prod-01",
    )
    res_auth = svc_auth_err.check_warehouse_status()
    assert res_auth.status == "AUTH_ERROR"
    assert res_auth.warehouse_state == "UNKNOWN"
    assert res_auth.warehouse_id == "wh-custom-prod-01"
    assert res_auth.can_execute is False

    # 2. Warehouse metadata 403 -> PERMISSION_DENIED (not STOPPED)
    perm_client = MagicMock()
    perm_client.current_user.me.return_value = MagicMock(user_name="sp-finops")
    perm_client.warehouses.get.side_effect = Exception("HTTP 403 PermissionDenied: lacks CAN USE")
    svc_perm = DatabricksSqlService(
        settings=oauth_with_mock_llm,
        workspace_client=perm_client,
        warehouse_id="wh-custom-prod-02",
    )
    res_perm = svc_perm.check_warehouse_status()
    assert res_perm.status == "PERMISSION_DENIED"
    assert res_perm.warehouse_state == "UNKNOWN"
    assert res_perm.authenticated_user == "sp-finops"

    # 3. Actual STOPPED warehouse -> WAREHOUSE_STOPPED and raises WarehouseStoppedError
    stopped_client = MagicMock()
    stopped_client.current_user.me.return_value = MagicMock(user_name="sp-finops")
    stopped_wh = MagicMock()
    stopped_wh.name = "Prod Warehouse"
    stopped_wh.state.value = "STOPPED"
    stopped_client.warehouses.get.return_value = stopped_wh
    svc_stopped = DatabricksSqlService(
        settings=oauth_with_mock_llm,
        workspace_client=stopped_client,
        warehouse_id="wh-custom-prod-03",
    )
    res_stopped = svc_stopped.check_warehouse_status()
    assert res_stopped.status == "WAREHOUSE_STOPPED"
    assert res_stopped.warehouse_state == "STOPPED"
    assert res_stopped.warehouse_id == "wh-custom-prod-03"
    stopped_client.warehouses.get.assert_called_with(id="wh-custom-prod-03")
    stopped_token = svc_stopped.issue_approval_token(
        query="SELECT * FROM system.billing.usage",
        warehouse_id="wh-custom-prod-03",
        approver_roles=["FinOpsAdministrator"],
    )
    with pytest.raises(WarehouseStoppedError):
        svc_stopped.execute_read_only_statement(
            "SELECT * FROM system.billing.usage",
            is_approved=True,
            approval_token=stopped_token,
        )

    # 4. RUNNING warehouse -> uses self.warehouse_id (not settings.databricks_warehouse_id) on execute
    running_client = MagicMock()
    running_client.current_user.me.return_value = MagicMock(user_name="sp-finops")
    running_wh = MagicMock()
    running_wh.name = "Prod Active WH"
    running_wh.state.value = "RUNNING"
    running_client.warehouses.get.return_value = running_wh
    running_client.statement_execution.execute_statement.return_value = MagicMock(result=None)

    svc_running = DatabricksSqlService(
        settings=oauth_with_mock_llm,
        workspace_client=running_client,
        warehouse_id="wh-prod-override-99",
    )
    res_running = svc_running.check_warehouse_status()
    assert res_running.status == "AVAILABLE"
    assert res_running.warehouse_state == "RUNNING"
    assert res_running.can_execute is True

    running_token = svc_running.issue_approval_token(
        query="SELECT * FROM system.billing.usage LIMIT 1",
        warehouse_id="wh-prod-override-99",
        approver_roles=["FinOpsAdministrator"],
    )
    svc_running.execute_read_only_statement(
        "SELECT * FROM system.billing.usage LIMIT 1",
        is_approved=True,
        approval_token=running_token,
    )
    _, exec_kwargs = running_client.statement_execution.execute_statement.call_args
    assert exec_kwargs["warehouse_id"] == "wh-prod-override-99"


def test_m1_billing_ingestion_uses_selected_workspace_warehouse_and_auth_status() -> None:
    """Verify BillingIngestionService selects workspace warehouse_id and surfaces auth errors."""
    DatabricksWorkspaceService._shared_workspaces.clear()
    cfg = Settings(
        databricks_auth_type="oauth",
        databricks_prod_workspace_id="7405608085231210",
        databricks_prod_warehouse_id="prod-wh-7744",
    )
    ws_service = DatabricksWorkspaceService(settings=cfg)
    svc = BillingIngestionService(settings=cfg, workspace_service=ws_service)

    mock_client = MagicMock()
    mock_client.current_user.me.side_effect = Exception(
        "HTTP 403 access_denied: Workspace inaccessible"
    )

    with patch(
        "cloud_recommender.services.databricks.auth.DatabricksAuthService.create_workspace_client",
        return_value=mock_client,
    ):
        status_resp = svc.get_ingestion_status(workspace_id="7405608085231210")
        val_resp = svc.validate_ingestion(workspace_id="7405608085231210")

    assert status_resp.warehouse_id == "prod-wh-7744"
    assert status_resp.warehouse_status == "PERMISSION_DENIED"
    assert status_resp.connection_status == "PERMISSION_DENIED"
    assert status_resp.system_tables_status == "PERMISSION_DENIED"
    assert val_resp.valid is False
    assert val_resp.warehouse_id == "prod-wh-7744"


def test_m2_unity_catalog_discovery_hierarchy_and_detail_enrichment() -> None:
    """Verify UC discovery traverses Catalogs -> Schemas -> Tables, enriches details, and parses grants."""
    mock_client = MagicMock()
    now = datetime.now(UTC)

    mock_cat = MagicMock()
    mock_cat.name = "main_catalog"
    mock_cat.owner = "admin@example.com"
    mock_cat.comment = "Production metastore catalog"
    mock_cat.catalog_type = "MANAGED_CATALOG"
    mock_cat.created_at = 1700000000000
    mock_cat.updated_at = 1700000001000
    mock_client.catalogs.list.return_value = [mock_cat]

    mock_sch = MagicMock()
    mock_sch.name = "telemetry_schema"
    mock_sch.owner = "data_eng"
    mock_sch.comment = "Telemetry tables"
    mock_sch.created_at = 1700000002000
    mock_sch.updated_at = 1700000003000
    mock_client.schemas.list.return_value = [mock_sch]

    mock_tbl = MagicMock()
    mock_tbl.name = "events_delta"
    mock_tbl.full_name = "main_catalog.telemetry_schema.events_delta"
    mock_tbl.table_type = "MANAGED"
    mock_tbl.data_source_format = "DELTA"
    mock_tbl.owner = "data_eng"
    mock_client.tables.list.return_value = [mock_tbl]

    mock_detail = MagicMock()
    mock_detail.name = "events_delta"
    mock_detail.full_name = "main_catalog.telemetry_schema.events_delta"
    mock_detail.properties = {"delta.appendOnly": "true", "pipelines.autoOptimize": "true"}
    mock_col1 = MagicMock(type_text="STRING", type_name="STRING", nullable=False, comment="UUID")
    mock_col1.name = "event_id"
    mock_col2 = MagicMock(
        type_text="TIMESTAMP", type_name="TIMESTAMP", nullable=True, comment="Event time"
    )
    mock_col2.name = "timestamp"
    mock_detail.columns = [mock_col1, mock_col2]
    mock_client.tables.get.return_value = mock_detail

    mock_priv = MagicMock()
    mock_priv.privilege = "SELECT"
    mock_pa = MagicMock()
    mock_pa.principal = "sp_finops_reader"
    mock_pa.privileges = [mock_priv]
    mock_eff = MagicMock()
    mock_eff.privilege_assignments = [mock_pa]
    mock_client.grants.get_effective.return_value = mock_eff

    discovery_service = DatabricksDiscoveryService()
    res = discovery_service.discover_unity_catalog_hierarchy(
        client=mock_client,
        connection_id="conn-uc-01",
        workspace_id="ws-dev-01",
        workspace_url="https://adb-test.azuredatabricks.net",
        now=now,
        workspace_name="Dev Workspace",
        environment="development",
    )

    assert res.status == CategoryDiscoveryStatus.AVAILABLE
    assert res.discovery_state == DatabricksResourceState.LIVE
    assert res.total_catalogs == 1
    assert res.total_schemas == 1
    assert res.total_tables == 1
    assert len(res.catalogs) == 1

    cat = res.catalogs[0]
    assert cat.name == "main_catalog"
    assert cat.schemas_status == DatabricksResourceState.LIVE
    assert len(cat.schemas) == 1

    sch = cat.schemas[0]
    assert sch.name == "telemetry_schema"
    assert sch.tables_status == DatabricksResourceState.LIVE
    assert len(sch.tables) == 1

    tbl = sch.tables[0]
    assert tbl.name == "events_delta"
    assert tbl.full_name == "main_catalog.telemetry_schema.events_delta"
    assert tbl.table_type == "MANAGED"
    assert tbl.data_source_format == "DELTA"
    assert mock_client.tables.get.call_count == 0
    assert tbl.permissions_status == DatabricksResourceState.LIVE
    assert len(tbl.permissions) == 1
    assert tbl.permissions[0].principal.startswith("sp_f")
    assert "SELECT" in tbl.permissions[0].privileges


def test_m2_unity_catalog_permissions_403_and_partial_discovery() -> None:
    """Verify child 403 on schemas or grants yields PARTIAL_DISCOVERY and never reports NO_DATA."""
    mock_client = MagicMock()
    now = datetime.now(UTC)

    mock_cat1 = MagicMock(owner="admin")
    mock_cat1.name = "cat_accessible"
    mock_cat2 = MagicMock(owner="secops")
    mock_cat2.name = "cat_restricted"
    mock_client.catalogs.list.return_value = [mock_cat1, mock_cat2]

    mock_sch = MagicMock()
    mock_sch.name = "sch_ok"

    def schemas_list_side_effect(catalog_name: str, **kwargs: Any) -> list[Any]:
        _ = kwargs
        if catalog_name == "cat_accessible":
            return [mock_sch]
        raise Exception("HTTP 403 PermissionDenied: User is not authorized to list schemas")

    mock_client.schemas.list.side_effect = schemas_list_side_effect

    mock_tbl = MagicMock(full_name="cat_accessible.sch_ok.tbl_ok", columns=[])
    mock_tbl.name = "tbl_ok"
    mock_tbl.full_name = "cat_accessible.sch_ok.tbl_ok"
    mock_client.tables.list.return_value = [mock_tbl]
    mock_client.tables.get.return_value = mock_tbl

    mock_client.grants.get_effective.side_effect = Exception(
        "HTTP 403 PermissionDenied: grants read denied"
    )
    mock_client.grants.get.side_effect = Exception(
        "HTTP 403 PermissionDenied: direct grants read denied"
    )

    discovery_service = DatabricksDiscoveryService()
    res = discovery_service.discover_unity_catalog_hierarchy(
        client=mock_client,
        connection_id="conn-uc-02",
        workspace_id="ws-dev-02",
        workspace_url="https://adb-test.azuredatabricks.net",
        now=now,
    )

    assert res.status == CategoryDiscoveryStatus.AVAILABLE
    assert res.discovery_state == DatabricksResourceState.PARTIAL
    assert res.error_code == "PARTIAL_DISCOVERY"
    assert "accessible metadata" in (res.error_message or "")

    cat2 = next(c for c in res.catalogs if c.name == "cat_restricted")
    assert cat2.schemas_status == DatabricksResourceState.ACCESS_DENIED
    assert "Permission denied" in (cat2.schemas_error or "")

    cat1 = next(c for c in res.catalogs if c.name == "cat_accessible")
    tbl = cat1.schemas[0].tables[0]
    assert tbl.permissions_status == DatabricksResourceState.ACCESS_DENIED
    assert "Permission denied" in (tbl.permissions_error or "")


def test_m2_unity_catalog_empty_and_pagination() -> None:
    """Verify empty iterable confirms NO_DATA and 50+ items marks has_more=True."""
    mock_client = MagicMock()
    now = datetime.now(UTC)
    discovery_service = DatabricksDiscoveryService()

    # Empty iterable
    mock_client.catalogs.list.return_value = []
    res_empty = discovery_service.discover_unity_catalog_hierarchy(
        client=mock_client,
        connection_id="conn-uc-03",
        workspace_id="ws-dev-03",
        workspace_url="https://adb-test.azuredatabricks.net",
        now=now,
    )
    assert res_empty.status == CategoryDiscoveryStatus.NO_RESOURCES_FOUND
    assert res_empty.discovery_state == DatabricksResourceState.NO_DATA
    assert res_empty.total_catalogs == 0
    assert res_empty.has_more is False

    # 51 items triggers has_more (> 50)
    cats_51 = [MagicMock() for _ in range(51)]
    for i, c in enumerate(cats_51):
        c.name = f"cat_{i}"
    mock_client.catalogs.list.return_value = cats_51
    mock_client.schemas.list.return_value = []
    res_paginated = discovery_service.discover_unity_catalog_hierarchy(
        client=mock_client,
        connection_id="conn-uc-04",
        workspace_id="ws-dev-04",
        workspace_url="https://adb-test.azuredatabricks.net",
        now=now,
    )
    assert res_paginated.has_more is True
    assert res_paginated.total_catalogs == 15


def test_m2_system_tables_metadata_discovery_and_missing_schemas() -> None:
    """Verify system tables discovery prioritizes schemas, detects missing ones, and enforces zero SQL."""
    mock_client = MagicMock()
    now = datetime.now(UTC)

    mock_s1 = MagicMock()
    mock_s1.name = "billing"
    mock_s2 = MagicMock()
    mock_s2.name = "compute"
    mock_client.schemas.list.return_value = [mock_s1, mock_s2]

    mock_t_usage = MagicMock()
    mock_t_usage.name = "usage"
    mock_t_usage.full_name = "system.billing.usage"
    mock_t_usage.table_type = "SYSTEM_TABLE"
    mock_t_usage.data_source_format = "DELTA"
    mock_t_usage.owner = "System"
    col_acc = MagicMock(type_text="STRING", type_name="STRING", nullable=False)
    col_acc.name = "account_id"
    col_ws = MagicMock(type_text="STRING", type_name="STRING", nullable=False)
    col_ws.name = "workspace_id"
    col_qty = MagicMock(type_text="DECIMAL(18,4)", type_name="DECIMAL", nullable=False)
    col_qty.name = "usage_quantity"
    col_date = MagicMock(type_text="DATE", type_name="DATE", nullable=False)
    col_date.name = "usage_date"
    mock_t_usage.columns = [col_acc, col_ws, col_qty, col_date]

    def tables_list_side_effect(catalog_name: str, schema_name: str, **kwargs: Any) -> list[Any]:
        _ = (catalog_name, kwargs)
        if schema_name == "billing":
            return [mock_t_usage]
        return []

    mock_client.tables.list.side_effect = tables_list_side_effect
    mock_client.tables.get.return_value = mock_t_usage

    mock_priv = MagicMock()
    mock_priv.privilege = "SELECT"
    mock_pa = MagicMock()
    mock_pa.principal = "sp_finops"
    mock_pa.privileges = [mock_priv]
    mock_eff = MagicMock()
    mock_eff.privilege_assignments = [mock_pa]
    mock_client.grants.get_effective.return_value = mock_eff

    discovery_service = DatabricksDiscoveryService()
    res = discovery_service.discover_system_tables_metadata(
        client=mock_client,
        connection_id="conn-sys-01",
        workspace_id="ws-dev-01",
        workspace_url="https://adb-test.azuredatabricks.net",
        now=now,
        workspace_name="Dev Workspace",
        environment="development",
        warehouse_id="wh-dev-starter-01",
    )

    assert res.status == CategoryDiscoveryStatus.AVAILABLE
    assert res.discovery_state == DatabricksResourceState.LIVE
    assert res.sql_executed is False
    assert res.compute_started is False
    assert res.discovered_schemas == ["billing", "compute"]
    assert "query" in res.missing_schemas
    assert "access" in res.missing_schemas
    assert "lakeflow" in res.missing_schemas
    assert "storage" in res.missing_schemas
    assert len(res.target_schemas) == 9

    assert len(res.billing_ingestion_ready_tables) == 1
    ready = res.billing_ingestion_ready_tables[0]
    assert ready.full_name == "system.billing.usage"
    assert ready.domain == "billing"
    assert ready.exists is True
    assert ready.select_grant_verified is True
    assert ready.warehouse_id == "wh-dev-starter-01"
    assert "account_id" in ready.column_types


def test_m2_system_tables_billing_readiness_strict_criteria() -> None:
    """Verify table is excluded from billing ingestion registry if permission is denied, warehouse is missing, or required columns are absent."""
    mock_client = MagicMock()
    now = datetime.now(UTC)
    discovery_service = DatabricksDiscoveryService()

    mock_s = MagicMock()
    mock_s.name = "billing"
    mock_client.schemas.list.return_value = [mock_s]

    # Usage table missing required 'usage_quantity'
    mock_t_bad_cols = MagicMock()
    mock_t_bad_cols.name = "usage"
    mock_t_bad_cols.full_name = "system.billing.usage"
    col_acc = MagicMock()
    col_acc.name = "account_id"
    mock_t_bad_cols.columns = [col_acc]
    mock_client.tables.list.return_value = [mock_t_bad_cols]
    mock_client.tables.get.return_value = mock_t_bad_cols

    mock_priv = MagicMock()
    mock_priv.privilege = "SELECT"
    mock_pa = MagicMock()
    mock_pa.privileges = [mock_priv]
    mock_eff = MagicMock(privilege_assignments=[mock_pa])
    mock_client.grants.get_effective.return_value = mock_eff

    # 1. Missing required columns -> excluded from ready_registry
    res_bad_cols = discovery_service.discover_system_tables_metadata(
        client=mock_client,
        connection_id="conn-01",
        workspace_id="ws-01",
        workspace_url="https://adb-test.azuredatabricks.net",
        now=now,
        warehouse_id="wh-configured-01",
    )
    assert len(res_bad_cols.billing_ingestion_ready_tables) == 0

    # Good columns but 403 on grants
    col_ws = MagicMock()
    col_ws.name = "workspace_id"
    col_qty = MagicMock()
    col_qty.name = "usage_quantity"
    col_date = MagicMock()
    col_date.name = "usage_date"
    mock_t_good = MagicMock()
    mock_t_good.name = "usage"
    mock_t_good.full_name = "system.billing.usage"
    mock_t_good.columns = [col_acc, col_ws, col_qty, col_date]
    mock_client.tables.list.return_value = [mock_t_good]
    mock_client.tables.get.return_value = mock_t_good

    # 2. SELECT permission denied -> select_grant_verified=False -> excluded
    mock_client.grants.get_effective.side_effect = Exception(
        "HTTP 403 PermissionDenied: Access Denied"
    )
    mock_client.grants.get.side_effect = Exception("HTTP 403 PermissionDenied: Access Denied")
    res_perm_denied = discovery_service.discover_system_tables_metadata(
        client=mock_client,
        connection_id="conn-02",
        workspace_id="ws-02",
        workspace_url="https://adb-test.azuredatabricks.net",
        now=now,
        warehouse_id="wh-configured-01",
    )
    assert len(res_perm_denied.billing_ingestion_ready_tables) == 0
    assert res_perm_denied.tables[0].select_grant_verified is False

    # 3. SELECT verified, but warehouse_id is None -> excluded
    mock_client.grants.get_effective.side_effect = None
    mock_client.grants.get_effective.return_value = mock_eff
    res_no_wh = discovery_service.discover_system_tables_metadata(
        client=mock_client,
        connection_id="conn-03",
        workspace_id="ws-03",
        workspace_url="https://adb-test.azuredatabricks.net",
        now=now,
        warehouse_id=None,
    )
    assert len(res_no_wh.billing_ingestion_ready_tables) == 0


@pytest.mark.asyncio
async def test_m2_dev_prod_workspace_isolation_and_routes(test_app: FastAPI) -> None:
    """Verify Dev (642006393507276) and Prod (7405608085231210) remain strictly isolated across UC and System Tables endpoints."""
    DatabricksWorkspaceService._shared_workspaces.clear()
    cfg = Settings(
        databricks_auth_type="oauth",
        databricks_dev_workspace_id="642006393507276",
        databricks_dev_warehouse_id="wh-dev-01",
        databricks_prod_workspace_id="7405608085231210",
        databricks_prod_warehouse_id="wh-prod-99",
    )
    svc = DatabricksWorkspaceService(settings=cfg)

    connections = svc.list_connections()
    dev_ws = next(w for w in connections if w.workspace_id == "642006393507276")
    prod_ws = next(w for w in connections if w.workspace_id == "7405608085231210")
    assert dev_ws.environment == "development"
    assert prod_ws.environment == "production"

    mock_dev_client = MagicMock()
    mock_dev_client.catalogs.list.return_value = []
    mock_prod_client = MagicMock()
    mock_prod_client.catalogs.list.return_value = []

    with patch(
        "cloud_recommender.services.databricks.auth.DatabricksAuthService.create_workspace_client",
        side_effect=[mock_dev_client, mock_prod_client],
    ):
        dev_res = await svc.get_unity_catalog_metadata(connection_id="databricks-azure-dev")
        prod_res = await svc.get_unity_catalog_metadata(connection_id="databricks-azure-prod")

    assert dev_res.workspace_id == "642006393507276"
    assert dev_res.environment == "development"
    assert prod_res.workspace_id == "7405608085231210"
    assert prod_res.environment == "production"

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp_sys = await ac.get("/api/v1/databricks/connections/databricks-azure-dev/system-tables")
        assert resp_sys.status_code == 200
        data = resp_sys.json()
        assert "target_schemas" in data
        assert "billing_ingestion_ready_tables" in data
        assert data["sql_executed"] is False
        assert data["compute_started"] is False

        resp_uc = await ac.get("/api/v1/databricks/connections/databricks-azure-dev/unity-catalog")
        assert resp_uc.status_code == 200
        uc_data = resp_uc.json()
        assert "catalogs" in uc_data
        assert "total_catalogs" in uc_data
