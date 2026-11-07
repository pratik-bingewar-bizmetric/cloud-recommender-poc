"""FastAPI routes for multi-workspace Databricks connectivity, testing, and discovery."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from cloud_recommender.schemas.databricks import (
    DatabricksConnectionHealthResponse,
    DatabricksConnectionResponse,
    DatabricksConnectionTestResponse,
    DatabricksWorkspaceDiscoveryResponse,
)
from cloud_recommender.services.databricks.workspace_service import (
    DatabricksWorkspaceService,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/databricks", tags=["Databricks Multi-Workspace Connectivity & Discovery"]
)


def get_workspace_service() -> DatabricksWorkspaceService:
    """Dependency injecting DatabricksWorkspaceService."""
    return DatabricksWorkspaceService()


@router.get(
    "/connections",
    response_model=list[DatabricksConnectionResponse],
    summary="List Registered Databricks Workspace Connections",
    description="Returns all configured Azure and AWS Databricks workspace connections with health and connection state.",
)
async def list_databricks_connections(
    service: Annotated[DatabricksWorkspaceService, Depends(get_workspace_service)],
) -> list[DatabricksConnectionResponse]:
    """List all registered Databricks workspaces."""
    return service.list_connections()


@router.get(
    "/connections/{connection_id}",
    response_model=DatabricksConnectionResponse,
    summary="Get Databricks Workspace Connection Details",
    description="Fetch configuration and connection status for a specific workspace connection.",
)
async def get_databricks_connection(
    connection_id: str,
    service: Annotated[DatabricksWorkspaceService, Depends(get_workspace_service)],
) -> DatabricksConnectionResponse:
    """Retrieve connection metadata by connection_id."""
    conn = service.get_connection(connection_id)
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Databricks connection '{connection_id}' was not found.",
        )
    return conn


@router.post(
    "/connections/{connection_id}/test",
    response_model=DatabricksConnectionTestResponse,
    summary="Test Databricks Workspace Connection",
    description="Validates live credentials and caller identity against the Databricks workspace.",
)
async def test_databricks_connection(
    connection_id: str,
    service: Annotated[DatabricksWorkspaceService, Depends(get_workspace_service)],
) -> DatabricksConnectionTestResponse:
    """Validate live connectivity and authentication without exposing credentials."""
    return await service.test_connection(connection_id)


@router.get(
    "/connections/{connection_id}/discovery",
    response_model=DatabricksWorkspaceDiscoveryResponse,
    summary="Get Workspace Discovered Resources",
    description="Returns discovered compute, warehouses, workflows, pipelines, Unity Catalog, and apps for the workspace.",
)
async def get_workspace_discovery(
    connection_id: str,
    service: Annotated[DatabricksWorkspaceService, Depends(get_workspace_service)],
) -> DatabricksWorkspaceDiscoveryResponse:
    """Retrieve cached discovery snapshot for the workspace."""
    return await service.get_or_discover_workspace(connection_id, force_refresh=False)


@router.post(
    "/connections/{connection_id}/discovery/refresh",
    response_model=DatabricksWorkspaceDiscoveryResponse,
    summary="Refresh Live Workspace Discovery",
    description="Queries live Databricks APIs across all categories and updates discovered inventory with upsert semantics.",
)
async def refresh_workspace_discovery(
    connection_id: str,
    service: Annotated[DatabricksWorkspaceService, Depends(get_workspace_service)],
) -> DatabricksWorkspaceDiscoveryResponse:
    """Execute live authenticated discovery across all categories."""
    return await service.get_or_discover_workspace(connection_id, force_refresh=True)


@router.get(
    "/connections/{connection_id}/health",
    response_model=DatabricksConnectionHealthResponse,
    summary="Get Connection Health & Permission Status",
    description="Returns a consolidated health, permission limitation, and capability report for the workspace.",
)
async def get_workspace_health(
    connection_id: str,
    service: Annotated[DatabricksWorkspaceService, Depends(get_workspace_service)],
) -> DatabricksConnectionHealthResponse:
    """Fetch health and permission status breakdown."""
    return await service.get_health(connection_id)
