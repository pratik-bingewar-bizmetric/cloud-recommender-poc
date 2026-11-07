"""Databricks workspace connection management and discovery orchestrator."""

from datetime import UTC, datetime
from typing import Any

import structlog

from cloud_recommender.schemas.databricks import (
    CategoryDiscoveryStatus,
    DatabricksCloud,
    DatabricksConnectionHealthResponse,
    DatabricksConnectionResponse,
    DatabricksConnectionStatus,
    DatabricksConnectionTestResponse,
    DatabricksWorkspaceDiscoveryResponse,
)
from cloud_recommender.services.databricks.auth import DatabricksAuthService
from cloud_recommender.services.databricks.discovery_service import (
    DatabricksDiscoveryService,
)

logger = structlog.get_logger(__name__)


class DatabricksWorkspaceService:
    """Service managing Databricks connections, validation, and discovery cache."""

    # Default registered workspaces
    _DEFAULT_WORKSPACES: dict[str, dict[str, Any]] = {
        "databricks-azure-dev": {
            "connection_id": "databricks-azure-dev",
            "workspace_id": "642006393507276",
            "workspace_name": "Azure Databricks Dev",
            "workspace_url": "https://adb-642006393507276.16.azuredatabricks.net",
            "cloud": DatabricksCloud.AZURE,
            "region": "northcentralus",
            "auth_method": "azure-cli / profile",
            "profile_name": "azure-dev",
            "status": DatabricksConnectionStatus.READY_TO_CONNECT,
            "last_connected_at": None,
            "last_error": None,
            "created_at": datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 11, 6, 12, 0, tzinfo=UTC),
        },
        "databricks-finops-dev": {
            "connection_id": "databricks-finops-dev",
            "workspace_id": "2250283018608626",
            "workspace_name": "AWS Databricks FinOps",
            "workspace_url": "https://dbc-8e061b63-c3bf.cloud.databricks.com",
            "cloud": DatabricksCloud.AWS,
            "region": "us-east-1",
            "auth_method": "cli-profile / oauth-sp",
            "profile_name": "finops-dev",
            "status": DatabricksConnectionStatus.READY_TO_CONNECT,
            "last_connected_at": None,
            "last_error": None,
            "created_at": datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 11, 6, 12, 0, tzinfo=UTC),
        },
    }

    # In-memory storage for discovery snapshots
    _discovery_cache: dict[str, DatabricksWorkspaceDiscoveryResponse] = {}

    def __init__(
        self,
        auth_service: DatabricksAuthService | None = None,
        discovery_service: DatabricksDiscoveryService | None = None,
    ) -> None:
        self.auth_service = auth_service or DatabricksAuthService()
        self.discovery_service = discovery_service or DatabricksDiscoveryService(
            auth_service=self.auth_service
        )

    def list_connections(self) -> list[DatabricksConnectionResponse]:
        """List all configured Databricks workspace connections."""
        return [DatabricksConnectionResponse(**data) for data in self._DEFAULT_WORKSPACES.values()]

    def get_connection(self, connection_id: str) -> DatabricksConnectionResponse | None:
        """Fetch connection metadata by connection_id."""
        data = self._DEFAULT_WORKSPACES.get(connection_id)
        return DatabricksConnectionResponse(**data) if data else None

    async def test_connection(self, connection_id: str) -> DatabricksConnectionTestResponse:
        """Validate live credentials and connectivity against the target Databricks workspace."""
        conn = self._DEFAULT_WORKSPACES.get(connection_id)
        now = datetime.now(UTC)
        if not conn:
            return DatabricksConnectionTestResponse(
                connection_id=connection_id,
                workspace_id="unknown",
                workspace_url="",
                success=False,
                status=DatabricksConnectionStatus.CONNECTION_ERROR,
                details=f"Databricks connection '{connection_id}' not found.",
                tested_at=now,
            )

        success, details, username = self.auth_service.test_connection(
            host=conn["workspace_url"],
            cloud=conn["cloud"].value,
            profile=conn["profile_name"],
        )

        # Update cached connection status
        conn["updated_at"] = now
        if success:
            conn["status"] = DatabricksConnectionStatus.CONNECTED
            conn["last_connected_at"] = now
            conn["last_error"] = None
        else:
            conn["status"] = (
                DatabricksConnectionStatus.PERMISSION_DENIED
                if "permission" in details.lower()
                else DatabricksConnectionStatus.AUTH_FAILED
            )
            conn["last_error"] = details

        return DatabricksConnectionTestResponse(
            connection_id=connection_id,
            workspace_id=conn["workspace_id"],
            workspace_url=conn["workspace_url"],
            success=success,
            status=conn["status"],
            current_user=username,
            details=details,
            tested_at=now,
        )

    async def get_or_discover_workspace(
        self, connection_id: str, force_refresh: bool = False
    ) -> DatabricksWorkspaceDiscoveryResponse:
        """Retrieve cached discovery or execute fresh live workspace discovery."""
        if not force_refresh and connection_id in self._discovery_cache:
            return self._discovery_cache[connection_id]

        conn = self._DEFAULT_WORKSPACES.get(connection_id)
        now = datetime.now(UTC)
        if not conn:
            return DatabricksWorkspaceDiscoveryResponse(
                connection_id=connection_id,
                workspace_id="unknown",
                workspace_name="Unknown Workspace",
                workspace_url="",
                cloud=DatabricksCloud.AZURE,
                overall_status="failed",
                categories={},
                resources=[],
                total_resources_count=0,
                discovered_at=now,
            )

        resp = await self.discovery_service.discover_workspace(
            connection_id=connection_id,
            host=conn["workspace_url"],
            cloud=conn["cloud"],
            workspace_id=conn["workspace_id"],
            workspace_name=conn["workspace_name"],
            profile=conn["profile_name"],
        )

        # Update connection state based on discovery outcome
        conn["updated_at"] = now
        if resp.overall_status in ("completed", "partial_failure"):
            conn["status"] = DatabricksConnectionStatus.CONNECTED
            conn["last_connected_at"] = now
            conn["last_error"] = None
        else:
            conn["status"] = DatabricksConnectionStatus.CONNECTION_ERROR

        self._discovery_cache[connection_id] = resp
        return resp

    async def get_health(self, connection_id: str) -> DatabricksConnectionHealthResponse:
        """Return comprehensive health, permissions, and discovery summary for a connection."""
        conn = self._DEFAULT_WORKSPACES.get(connection_id)
        if not conn:
            return DatabricksConnectionHealthResponse(
                connection_id=connection_id,
                workspace_id="unknown",
                cloud=DatabricksCloud.AZURE,
                status=DatabricksConnectionStatus.CONNECTION_ERROR,
                limitations=["Connection ID not recognized."],
            )

        discovery = await self.get_or_discover_workspace(connection_id, force_refresh=False)
        cats_summary = {k: v.status for k, v in discovery.categories.items()}
        counts: dict[str, int] = {}
        for r in discovery.resources:
            counts[r.resource_type] = counts.get(r.resource_type, 0) + 1

        capabilities = [
            f"category:{k}"
            for k, v in discovery.categories.items()
            if v.status
            in (CategoryDiscoveryStatus.AVAILABLE, CategoryDiscoveryStatus.NO_RESOURCES_FOUND)
        ]
        limitations = [
            f"{k}: {v.error_message}" for k, v in discovery.categories.items() if v.error_message
        ]

        # Extract current user from workspace metadata item
        auth_user = None
        for r in discovery.resources:
            if r.resource_type == "workspace" and r.creator:
                auth_user = r.creator
                break

        return DatabricksConnectionHealthResponse(
            connection_id=connection_id,
            workspace_id=conn["workspace_id"],
            cloud=conn["cloud"],
            status=conn["status"],
            authenticated_user=auth_user,
            last_verified_at=conn["last_connected_at"],
            categories_summary=cats_summary,
            resource_counts_by_type=counts,
            capabilities=capabilities,
            limitations=limitations,
        )
