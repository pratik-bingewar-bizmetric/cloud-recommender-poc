"""Read-only cloud service catalog API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from cloud_recommender.db.session import get_db_session
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


async def get_optional_db_session() -> AsyncSession | None:
    """Dependency attempting to provide an async DB session without crashing if unconfigured."""
    try:
        async for session in get_db_session():
            return session
    except Exception:
        return None
    return None


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
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)] = None,
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
    manager = CatalogServiceManager(session=session)
    return await manager.list_catalog_services(filters)


@router.get(
    "/services/{service_id}",
    response_model=CatalogService,
    status_code=status.HTTP_200_OK,
    summary="Get catalog service details",
    description="Retrieve details for a specific cloud service by its normalized service_id.",
)
async def get_service(
    service_id: str,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)] = None,
) -> CatalogService:
    """Retrieve an individual catalog service by ID."""
    manager = CatalogServiceManager(session=session)
    service = await manager.get_catalog_service(service_id)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog service '{service_id}' was not found.",
        )
    return service
