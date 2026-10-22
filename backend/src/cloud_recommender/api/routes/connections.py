"""API endpoints for managing, discovering, and validating cloud connections."""

from fastapi import APIRouter, Depends, status

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.connections import (
    CloudConnection,
    ConnectionValidationResponse,
    CreateConnectionRequest,
    ValidateConnectionRequest,
)
from cloud_recommender.services.connections.connection_service import ConnectionService
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService

router = APIRouter(prefix="/connections", tags=["Cloud Connections & Auth Lifecycle"])


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
    summary="List configured and saved cloud connections with safe metadata only",
)
async def list_connections(
    service: ConnectionService = Depends(get_connection_service),
) -> list[CloudConnection]:
    """Return all available cloud connections.

    Credentials, secrets, and private keys are NEVER returned.
    """
    return await service.list_connections()


@router.post(
    "/validate",
    response_model=ConnectionValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform a real server-side connection validation check against provider APIs",
)
async def validate_connection(
    request: ValidateConnectionRequest,
    service: ConnectionService = Depends(get_connection_service),
) -> ConnectionValidationResponse:
    """Validate access, permissions, and discover resource count for a selected scope."""
    return await service.validate_connection(
        provider=request.provider,
        scope_id=request.scope_id,
        connection_id=request.connection_id,
    )


@router.post(
    "",
    response_model=CloudConnection,
    status_code=status.HTTP_201_CREATED,
    summary="Register and validate a new cloud connection with safe server-side credentials",
)
async def create_connection(
    request: CreateConnectionRequest,
    service: ConnectionService = Depends(get_connection_service),
) -> CloudConnection:
    """Validate credentials against cloud provider and register connection.

    Never echoes secrets back.
    """
    return await service.create_connection(request)
