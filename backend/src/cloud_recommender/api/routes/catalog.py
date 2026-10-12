"""Read-only cloud service catalog API endpoints."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.db.session import get_session_factory
from cloud_recommender.schemas.catalog import (
    CatalogService,
    CatalogServiceFilter,
    CatalogServiceListResponse,
)
from cloud_recommender.schemas.common import (
    CloudProvider,
    ComplianceStandard,
    ServiceCategory,
)
from cloud_recommender.services.catalog_service import CatalogServiceManager

router = APIRouter(prefix="/catalog", tags=["Catalog"])


async def get_catalog_service_manager(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncGenerator[CatalogServiceManager, None]:
    """FastAPI dependency yielding a CatalogServiceManager with guaranteed session lifecycle."""
    if settings.catalog_offline_mode:
        yield CatalogServiceManager(session=None, offline_mode=True)
        return

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield CatalogServiceManager(session=session, offline_mode=False)
        except BaseException:
            await session.rollback()
            raise
        finally:
            await session.close()


@router.get(
    "/services",
    response_model=CatalogServiceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List and filter catalog services",
    description=(
        "Retrieve normalized cloud services across Azure, AWS, and GCP "
        "with filtering and pagination."
    ),
)
async def list_services(
    provider: Annotated[
        CloudProvider | None,
        Query(description="Filter by cloud provider: 'azure', 'aws', 'gcp'"),
    ] = None,
    category: Annotated[
        ServiceCategory | None,
        Query(description="Filter by architectural category: 'compute', 'database', etc."),
    ] = None,
    region: Annotated[
        str | None,
        Query(description="Filter by supported geographic region"),
    ] = None,
    compliance: Annotated[
        ComplianceStandard | None,
        Query(description="Filter by compliance certification (e.g. 'hipaa', 'pci_dss')"),
    ] = None,
    is_serverless: Annotated[
        bool | None,
        Query(description="Filter by serverless operational model"),
    ] = None,
    search: Annotated[
        str | None,
        Query(description="Fuzzy search across service name and description"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Maximum number of records to return"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of records to skip"),
    ] = 0,
    manager: Annotated[CatalogServiceManager, Depends(get_catalog_service_manager)] = None,  # type: ignore[assignment]
) -> CatalogServiceListResponse:
    """List normalized catalog services matching query filters."""
    filters = CatalogServiceFilter(
        provider=provider,
        category=category,
        region=region,
        compliance=compliance,
        is_serverless=is_serverless,
        search=search,
        limit=limit,
        offset=offset,
    )
    return await manager.list_catalog_services(filters)


@router.get(
    "/services/{provider}/{service_id}",
    response_model=CatalogService,
    status_code=status.HTTP_200_OK,
    summary="Get provider-qualified catalog service details",
    description="Retrieve details for a specific cloud service by its provider and service_id.",
)
async def get_provider_service(
    provider: CloudProvider,
    service_id: str,
    manager: Annotated[CatalogServiceManager, Depends(get_catalog_service_manager)],
) -> CatalogService:
    """Retrieve an individual catalog service by provider and ID."""
    service = await manager.get_catalog_service(service_id=service_id, provider=provider)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog service '{service_id}' for provider '{provider.value}' was not found.",
        )
    return service


@router.get(
    "/services/{service_id}",
    response_model=CatalogService,
    status_code=status.HTTP_200_OK,
    summary="Get catalog service details",
    description=(
        "Retrieve details for a specific cloud service by its service_id. "
        "Accepts optional provider parameter to disambiguate identical identifiers."
    ),
)
async def get_service(
    service_id: str,
    provider: Annotated[
        CloudProvider | None,
        Query(description="Optional cloud provider to disambiguate service ID"),
    ] = None,
    manager: Annotated[CatalogServiceManager, Depends(get_catalog_service_manager)] = None,  # type: ignore[assignment]
) -> CatalogService:
    """Retrieve an individual catalog service by ID with optional provider qualification."""
    service = await manager.get_catalog_service(service_id=service_id, provider=provider)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog service '{service_id}' was not found.",
        )
    return service
