"""API endpoints for managing, discovering, and validating cloud connections.

Two kinds of connections are served by the same contract:

- **owned**: created by the caller with their own cloud credentials (Azure service principal);
  persisted, encrypted at rest, visible and editable only by the owner (404 for anyone else).
- **organization**: connections of the platform's own identity (read-only for ordinary users).

The application user (Entra token / explicit development identity) is separate from the cloud
account being connected: cloud credentials never come from the user's login token.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Response, status

from cloud_recommender.api.connection_deps import get_connection_manager
from cloud_recommender.core.auth import AuthenticatedUser, get_current_user, owner_key_for
from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.common import CloudProvider
from cloud_recommender.schemas.connections import (
    CloudConnection,
    ConnectionValidationResponse,
    CreateConnectionRequest,
    UpdateConnectionRequest,
    ValidateConnectionRequest,
)
from cloud_recommender.services.azure_live.validation import is_guid
from cloud_recommender.services.connections.connection_manager import ConnectionManager
from cloud_recommender.services.connections.connection_service import ConnectionService
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/connections", tags=["Cloud Connections & Auth Lifecycle"])

Manager = Annotated[ConnectionManager, Depends(get_connection_manager)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def get_connection_service(settings: Settings = Depends(get_settings)) -> ConnectionService:
    azure_service = AzureInventoryService(settings=settings)
    gcp_service = GcpInventoryService(settings=settings)
    return ConnectionService(
        settings=settings, azure_service=azure_service, gcp_service=gcp_service
    )


@router.get(
    "",
    response_model=list[CloudConnection],
    status_code=status.HTTP_200_OK,
    summary="List the caller's own connections and the organization's connections (no secrets)",
)
async def list_connections(
    user: CurrentUser,
    manager: Manager,
    response: Response,
    service: ConnectionService = Depends(get_connection_service),
) -> list[CloudConnection]:
    """Owned (persistent) connections first, then organization connections.

    Credentials, secrets and tokens are NEVER returned. If the connection store is unavailable the
    organization connections are still returned and the problem is reported in the
    ``X-Owned-Connections`` response header (create/update/delete fail loudly instead).
    """
    organization = await service.list_connections()
    try:
        owned = await manager.list(owner_key_for(user))
    except Exception as exc:  # store/database problem must not hide organization connections
        logger.warning("owned_connections_unavailable", error_type=type(exc).__name__)
        response.headers["X-Owned-Connections"] = "unavailable"
        owned = []
    return [*owned, *organization]


@router.post(
    "",
    response_model=CloudConnection,
    status_code=status.HTTP_201_CREATED,
    summary="Create (validate, encrypt and save) a cloud connection",
)
async def create_connection(
    request: CreateConnectionRequest,
    user: CurrentUser,
    manager: Manager,
    service: ConnectionService = Depends(get_connection_service),
) -> CloudConnection:
    """Azure, GCP and AWS connections are validated with supplied credentials and saved encrypted.

    The owner is taken from the validated token, never from the request.
    """
    if request.provider in (CloudProvider.AZURE, CloudProvider.GCP, CloudProvider.AWS):
        return await manager.create(owner_key_for(user), request)
    return await service.create_connection(request)


@router.post(
    "/validate",
    response_model=ConnectionValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate access for a connection or scope",
)
async def validate_connection(
    request: ValidateConnectionRequest,
    user: CurrentUser,
    manager: Manager,
    service: ConnectionService = Depends(get_connection_service),
) -> ConnectionValidationResponse:
    """Validate an owned connection with its stored credential, or an organization scope."""
    if request.connection_id and is_guid(request.connection_id):
        validated = await manager.validate(owner_key_for(user), request.connection_id)
        ok = validated.status == "connected"
        details = "; ".join(
            f"{i.integration}: {i.state.value}" + (f" ({i.message})" if i.message else "")
            for i in validated.integrations
        )
        return ConnectionValidationResponse(
            success=ok,
            connection_id=validated.id,
            provider=validated.provider,
            scope_id=validated.scope_id,
            scope_name=validated.name,
            status=validated.status,
            details=details,
            permissions_verified=list(validated.capabilities),
            is_live=True,
        )
    return await service.validate_connection(
        provider=request.provider,
        scope_id=request.scope_id,
        connection_id=request.connection_id,
    )


@router.get(
    "/{connection_id}", response_model=CloudConnection, summary="Get one of your connections"
)
async def get_connection(
    connection_id: str, user: CurrentUser, manager: Manager
) -> CloudConnection:
    return await manager.get(owner_key_for(user), connection_id)


@router.post(
    "/{connection_id}/validate",
    response_model=CloudConnection,
    summary="Re-validate your connection with its stored credential (reconnect)",
)
async def validate_owned_connection(
    connection_id: str, user: CurrentUser, manager: Manager
) -> CloudConnection:
    return await manager.validate(owner_key_for(user), connection_id)


@router.patch(
    "/{connection_id}",
    response_model=CloudConnection,
    summary="Edit, reconnect or rotate the credential of your connection",
)
async def update_connection(
    connection_id: str, request: UpdateConnectionRequest, user: CurrentUser, manager: Manager
) -> CloudConnection:
    """The change is validated against the cloud provider BEFORE it is saved."""
    return await manager.update(owner_key_for(user), connection_id, request)


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your connection and its stored credential",
)
async def delete_connection(connection_id: str, user: CurrentUser, manager: Manager) -> Response:
    await manager.delete(owner_key_for(user), connection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
