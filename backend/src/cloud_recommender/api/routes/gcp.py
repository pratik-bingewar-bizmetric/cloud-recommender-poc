"""FastAPI routes for GCP Service Account authentication, connectivity checks, and resource discovery.

Endpoints:
- POST /api/v1/gcp/connections/test: Validate Service Account and probe 8 services WITHOUT persisting.
- POST /api/v1/gcp/connections: Validate, encrypt at rest, and save persistent GCP connection.
- GET /api/v1/gcp/connections: List the authenticated user's GCP connections (zero secrets).
- GET /api/v1/gcp/connections/{id}: Retrieve connection metadata (zero secrets).
- DELETE /api/v1/gcp/connections/{id}: Delete connection and securely remove encrypted key.
- GET /api/v1/gcp/projects: List accessible GCP projects via Cloud Resource Manager.
- GET /api/v1/gcp/resources: Discover resources across all connected services with deduplication.
- GET /api/v1/gcp/services/status: Return latest granular connectivity matrix for 8 GCP services.

Strict Security Invariants:
1. All endpoints enforce authenticated sessions and tenant/owner isolation.
2. Service Account private keys and bearer tokens are NEVER returned in API responses.
3. Zero-Execution policy: all operations are strictly read-only.
4. Billing is explicitly DEFERRED.
"""

from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from cloud_recommender.api.connection_deps import get_connection_manager
from cloud_recommender.core.auth import AuthenticatedUser, get_current_user, owner_key_for
from cloud_recommender.schemas.gcp import (
    GcpConnectionResponse,
    GcpCreateConnectionRequest,
    GcpDiscoveryResponse,
    GcpProjectMetadata,
    GcpServiceStatus,
    GcpTestConnectionRequest,
    GcpTestConnectionResponse,
)
from cloud_recommender.services.connections.connection_manager import ConnectionManager
from cloud_recommender.services.gcp.auth_service import (
    GcpAuthenticationError,
    _sanitize_auth_error,
)
from cloud_recommender.services.gcp.connectivity_service import (
    GcpConnectivityService,
    get_gcp_connectivity_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/gcp", tags=["Google Cloud Platform (GCP) Integration"])

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Manager = Annotated[ConnectionManager, Depends(get_connection_manager)]


def get_connectivity_service() -> GcpConnectivityService:
    return get_gcp_connectivity_service()


@router.post(
    "/connections/test",
    response_model=GcpTestConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Test GCP Service Account credentials and probe all services without persisting",
)
async def test_gcp_connection(
    request: GcpTestConnectionRequest,
    _user: CurrentUser,
    service: Annotated[GcpConnectivityService, Depends(get_connectivity_service)],
) -> GcpTestConnectionResponse:
    """Validate Service Account JSON and check connectivity for 8 GCP services.

    Credentials provided are evaluated in-memory and NEVER saved to the database.
    """
    try:
        return await service.test_connection(
            service_account_json=request.service_account_json,
            project_id=request.project_id,
            connection_name=request.connection_name,
        )
    except GcpAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": exc.error_code, "message": _sanitize_auth_error(exc.message)},
        ) from exc
    except Exception as exc:
        logger.warning("gcp_test_connection_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "CONNECTION_TEST_FAILED",
                "message": f"Connection test failed: {_sanitize_auth_error(str(exc))}",
            },
        ) from exc


@router.post(
    "/connections",
    response_model=GcpConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Validate, encrypt, and save a persistent GCP connection",
)
async def create_gcp_connection(
    request: GcpCreateConnectionRequest,
    user: CurrentUser,
    manager: Manager,
) -> GcpConnectionResponse:
    """Test credentials, encrypt Service Account JSON with AES-256-GCM, and persist."""
    try:
        return await manager.create_gcp(
            owner_key=owner_key_for(user),
            name=request.name,
            project_id=request.project_id,
            service_account_json=request.service_account_json,
        )
    except HTTPException:
        raise
    except GcpAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": exc.error_code, "message": _sanitize_auth_error(exc.message)},
        ) from exc
    except Exception as exc:
        logger.error("gcp_create_connection_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "CREATE_CONNECTION_FAILED",
                "message": f"Failed to save connection: {_sanitize_auth_error(str(exc))}",
            },
        ) from exc


@router.get(
    "/connections",
    response_model=list[GcpConnectionResponse],
    status_code=status.HTTP_200_OK,
    summary="List all GCP connections owned by the caller (zero secrets)",
)
async def list_gcp_connections(
    user: CurrentUser,
    manager: Manager,
) -> list[GcpConnectionResponse]:
    """Retrieve all persisted GCP connections belonging to the authenticated tenant/owner."""
    return await manager.list_gcp(owner_key_for(user))


@router.get(
    "/connections/{connection_id}",
    response_model=GcpConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get details of a specific GCP connection (zero secrets)",
)
async def get_gcp_connection(
    connection_id: str,
    user: CurrentUser,
    manager: Manager,
) -> GcpConnectionResponse:
    """Retrieve connection metadata. Enforces owner isolation (returns 404 for other owners)."""
    return await manager.get_gcp(owner_key_for(user), connection_id)


@router.delete(
    "/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a GCP connection and destroy its encrypted credential",
)
async def delete_gcp_connection(
    connection_id: str,
    user: CurrentUser,
    manager: Manager,
) -> Response:
    """Permanently delete connection metadata and encrypted key from the database."""
    # Ensure it's a GCP connection owned by caller
    await manager.get_gcp(owner_key_for(user), connection_id)
    await manager.delete(owner_key_for(user), connection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/projects",
    response_model=list[GcpProjectMetadata],
    status_code=status.HTTP_200_OK,
    summary="List accessible GCP projects for a saved connection or active session",
)
async def list_gcp_projects(
    user: CurrentUser,
    manager: Manager,
    service: Annotated[GcpConnectivityService, Depends(get_connectivity_service)],
    connection_id: str = Query(..., description="Connection ID of the saved GCP connection."),
) -> list[GcpProjectMetadata]:
    """List accessible projects discovered via Cloud Resource Manager using stored credentials."""
    record, secret_json = await manager.decrypt_gcp_secret(owner_key_for(user), connection_id)
    try:
        creds_data, info = service.auth_service.parse_and_validate_json(
            secret_json, expected_project_id=record.scope_id
        )
        token = service.auth_service.acquire_token(creds_data)
        async with httpx.AsyncClient(
            transport=service.transport, timeout=service.timeout_seconds
        ) as client:
            _, meta = await service.check_resource_manager(client, token, info.project_id)
        if meta:
            return [meta]
    except Exception as exc:
        logger.warning("gcp_list_projects_fallback", connection_id=connection_id, error=str(exc))

    return [
        GcpProjectMetadata(
            project_id=record.scope_id,
            project_name=record.name,
            project_state=record.status,
        )
    ]


@router.get(
    "/resources",
    response_model=GcpDiscoveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover GCP resources across Asset Inventory, Storage, SQL, Compute, and Monitoring",
)
async def get_gcp_resources(
    user: CurrentUser,
    manager: Manager,
    service: Annotated[GcpConnectivityService, Depends(get_connectivity_service)],
    connection_id: str = Query(..., description="ID of configured GCP connection."),
) -> GcpDiscoveryResponse:
    """Execute live read-only resource discovery using the connection's encrypted credentials."""
    record, secret_json = await manager.decrypt_gcp_secret(owner_key_for(user), connection_id)
    return await service.discover_resources(secret_json, record.scope_id)


@router.get(
    "/services/status",
    response_model=list[GcpServiceStatus],
    status_code=status.HTTP_200_OK,
    summary="Get current connectivity status for 8 GCP services",
)
async def get_gcp_services_status(
    user: CurrentUser,
    manager: Manager,
    service: Annotated[GcpConnectivityService, Depends(get_connectivity_service)],
    connection_id: str = Query(..., description="ID of configured GCP connection."),
) -> list[GcpServiceStatus]:
    """Probe all 8 GCP services and return independent status results."""
    record, secret_json = await manager.decrypt_gcp_secret(owner_key_for(user), connection_id)
    test_res = await service.test_connection(
        service_account_json=secret_json,
        project_id=record.scope_id,
        connection_name=record.name,
    )
    return test_res.services
