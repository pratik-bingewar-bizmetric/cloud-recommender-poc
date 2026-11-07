"""API endpoints for multi-cloud resource configuration, discovery, and selection resolution."""

from collections.abc import AsyncGenerator
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.db.repositories.configuration_repo import (
    ResourceConfigurationRepository,
)
from cloud_recommender.db.session import get_session_factory
from cloud_recommender.schemas.configuration import (
    ConfigurationStatusResponse,
    EffectiveSelectionResponse,
    ResourceConfigurationCreate,
    ResourceConfigurationResponse,
    ScopeDiscoveryResponse,
)
from cloud_recommender.services.configuration.configuration_service import (
    ConfigurationService,
)
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/configuration", tags=["Resource Configuration & Scope Selection"])


async def get_configuration_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncGenerator[ConfigurationService, None]:
    """FastAPI dependency supplying ConfigurationService with DB repository or memory fallback."""
    azure_service = AzureInventoryService(settings=settings)
    gcp_service = GcpInventoryService(settings=settings)

    if settings.catalog_offline_mode:
        yield ConfigurationService(
            repository=None,
            settings=settings,
            azure_service=azure_service,
            gcp_service=gcp_service,
        )
        return

    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                repo = ResourceConfigurationRepository(session=session)
                yield ConfigurationService(
                    repository=repo,
                    settings=settings,
                    azure_service=azure_service,
                    gcp_service=gcp_service,
                )
            except BaseException:
                await session.rollback()
                raise
            finally:
                await session.close()
    except Exception as exc:
        logger.warning("db_session_failed_falling_back_to_memory", error=str(exc))
        yield ConfigurationService(
            repository=None,
            settings=settings,
            azure_service=azure_service,
            gcp_service=gcp_service,
        )


@router.get(
    "/scopes/discover",
    response_model=ScopeDiscoveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover cloud resources and Databricks workspaces in a hierarchical tree",
)
async def discover_scopes(
    connection_id: Annotated[str, Query(description="Cloud connection identifier to discover")],
    provider: Annotated[str, Query(description="Provider ('azure', 'gcp', 'aws')")] = "azure",
    service: ConfigurationService = Depends(get_configuration_service),
) -> ScopeDiscoveryResponse:
    """Discover subscriptions, resource groups, resources, and Azure Databricks workspaces."""
    return await service.discover_scopes(connection_id=connection_id, provider=provider)


@router.get(
    "/{connection_id}",
    response_model=ResourceConfigurationResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve active resource configuration for a connection",
)
async def get_configuration(
    connection_id: str,
    service: ConfigurationService = Depends(get_configuration_service),
) -> ResourceConfigurationResponse:
    """Fetch the active resource selection configuration including all scope items."""
    config = await service.get_active_configuration(connection_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active resource configuration found for connection '{connection_id}'.",
        )
    return config


@router.post(
    "",
    response_model=ResourceConfigurationResponse,
    status_code=status.HTTP_200_OK,
    summary="Save or update resource configuration (creates new revision)",
)
async def save_configuration(
    payload: ResourceConfigurationCreate,
    service: ConfigurationService = Depends(get_configuration_service),
) -> ResourceConfigurationResponse:
    """Persist a new versioned resource selection scope for a cloud connection."""
    try:
        return await service.save_configuration(
            connection_id=payload.connection_id,
            provider=payload.provider,
            scope_items=payload.scope_items,
            created_by=payload.created_by,
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err),
        ) from val_err
    except Exception as exc:
        logger.error("save_configuration_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save resource configuration: {exc}",
        ) from exc


@router.get(
    "/{connection_id}/selected",
    response_model=EffectiveSelectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get deterministically resolved effective selected resource IDs",
)
async def get_effective_selection(
    connection_id: str,
    service: ConfigurationService = Depends(get_configuration_service),
) -> EffectiveSelectionResponse:
    """Resolve hierarchical selections (handling all_children cascade and explicit exclusions)."""
    return await service.resolve_effective_selection(connection_id)


@router.get(
    "/{connection_id}/workspaces",
    response_model=list[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Get selected Databricks workspaces for future ingestion",
)
async def get_selected_workspaces(
    connection_id: str,
    service: ConfigurationService = Depends(get_configuration_service),
) -> list[dict[str, Any]]:
    """Return all Azure Databricks workspaces that fall within the active selected scope."""
    effective = await service.resolve_effective_selection(connection_id)
    return effective.databricks_workspaces


@router.get(
    "/{connection_id}/status",
    response_model=ConfigurationStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ingestion readiness and selection status",
)
async def get_configuration_status(
    connection_id: str,
    service: ConfigurationService = Depends(get_configuration_service),
) -> ConfigurationStatusResponse:
    """Return whether the connection has a valid configuration ready for Databricks Apps ingestion."""
    return await service.get_configuration_status(connection_id)
