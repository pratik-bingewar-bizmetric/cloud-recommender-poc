"""FastAPI routes for multi-workspace Databricks connectivity, testing, and discovery."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from cloud_recommender.schemas.databricks import (
    DatabricksCategoryPageResponse,
    DatabricksConnectionHealthResponse,
    DatabricksConnectionResponse,
    DatabricksConnectionTestResponse,
    DatabricksWorkspaceDiscoveryResponse,
    LiveQueryHistoryResponse,
    SystemTablesMetadataResponse,
    UnityCatalogMetadataResponse,
)
from cloud_recommender.services.databricks.refresher import get_refresher
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
    get_refresher().touch(connection_id)
    return await service.get_health(connection_id)


@router.get(
    "/connections/{connection_id}/categories/{category}",
    response_model=DatabricksCategoryPageResponse,
    summary="Get Paginated Resources for a Workspace Category",
    description="Returns paginated resources, retrieval timestamp, and explicit M2 state for a single discovery category.",
)
async def get_workspace_category_resources(
    connection_id: str,
    category: str,
    service: Annotated[DatabricksWorkspaceService, Depends(get_workspace_service)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    force_refresh: Annotated[bool, Query()] = False,
    job_id: Annotated[int | None, Query(ge=1)] = None,
    page_token: Annotated[str | None, Query()] = None,
) -> DatabricksCategoryPageResponse:
    """Return paginated resources and state for a workspace category."""
    return await service.get_category_resources(
        connection_id=connection_id,
        category=category,
        limit=limit,
        offset=offset,
        force_refresh=force_refresh,
        job_id=job_id,
        page_token=page_token,
    )


@router.get(
    "/connections/{connection_id}/unity-catalog",
    response_model=UnityCatalogMetadataResponse,
    summary="Get Live Unity Catalog Hierarchy & Effective Grants",
    description="Reads Unity Catalog catalogs, schemas, tables, columns, and effective permissions metadata via REST APIs.",
)
async def get_workspace_unity_catalog(
    connection_id: str,
    service: Annotated[DatabricksWorkspaceService, Depends(get_workspace_service)],
    catalog_name: Annotated[str | None, Query()] = None,
    include_permissions: Annotated[bool, Query()] = True,
    force_refresh: Annotated[bool, Query()] = False,
) -> UnityCatalogMetadataResponse:
    """Discover Unity Catalog catalogs, schemas, tables, and effective grants."""
    return await service.get_unity_catalog_metadata(
        connection_id=connection_id,
        catalog_name=catalog_name,
        include_permissions=include_permissions,
        force_refresh=force_refresh,
    )


@router.get(
    "/connections/{connection_id}/system-tables",
    response_model=SystemTablesMetadataResponse,
    summary="Get Live System Tables Metadata (Zero SQL)",
    description="Discovers available system.* schemas, tables, column metadata, and SELECT grant status without executing SQL or starting compute.",
)
async def get_workspace_system_tables(
    connection_id: str,
    service: Annotated[DatabricksWorkspaceService, Depends(get_workspace_service)],
    force_refresh: Annotated[bool, Query()] = False,
    warehouse_id: Annotated[str | None, Query()] = None,
) -> SystemTablesMetadataResponse:
    """Discover system.* schemas and tables cleanly via UC REST APIs."""
    return await service.get_system_tables_metadata(
        connection_id=connection_id,
        force_refresh=force_refresh,
        warehouse_id=warehouse_id,
    )


@router.get(
    "/connections/{connection_id}/query-history",
    response_model=LiveQueryHistoryResponse,
    summary="Get Paginated Read-Only SQL Query History",
    description="Retrieves paginated SQL query history metadata via Databricks Query History REST API without executing SQL or starting warehouses.",
)
async def get_workspace_query_history(
    connection_id: str,
    service: Annotated[DatabricksWorkspaceService, Depends(get_workspace_service)],
    warehouse_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    start_time_ms: Annotated[int | None, Query(ge=0)] = None,
    end_time_ms: Annotated[int | None, Query(ge=0)] = None,
    query_source: Annotated[str | None, Query()] = None,
    max_results: Annotated[int, Query(ge=1, le=100)] = 50,
    page_token: Annotated[str | None, Query()] = None,
) -> LiveQueryHistoryResponse:
    """Retrieve paginated SQL query history metadata safely."""
    return await service.get_query_history(
        connection_id=connection_id,
        warehouse_id=warehouse_id,
        status_filter=status,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
        query_source=query_source,
        max_results=max_results,
        page_token=page_token,
    )
