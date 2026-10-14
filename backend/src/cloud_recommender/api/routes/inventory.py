"""API endpoints for subscription/project-level cloud inventory, cost rollups, and multi-cloud comparison."""

import structlog
from fastapi import APIRouter, Depends, status

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.inventory import (
    CloudScopeSummary,
    MultiCloudComparisonRequest,
    MultiCloudComparisonResponse,
    ProviderConnectionStatus,
    ScopeAnalysisRequest,
    SubscriptionOrProjectAnalysis,
)
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
from cloud_recommender.services.inventory.multi_cloud_comparator import (
    MultiCloudComparatorService,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/inventory", tags=["Subscription & Project Inventory"])


def get_azure_inventory_service(
    settings: Settings = Depends(get_settings),
) -> AzureInventoryService:
    return AzureInventoryService(settings=settings)


def get_gcp_inventory_service(
    settings: Settings = Depends(get_settings),
) -> GcpInventoryService:
    return GcpInventoryService(settings=settings)


def get_comparator_service(
    settings: Settings = Depends(get_settings),
) -> MultiCloudComparatorService:
    return MultiCloudComparatorService(settings=settings)


@router.get(
    "/providers/status",
    response_model=list[ProviderConnectionStatus],
    status_code=status.HTTP_200_OK,
    summary="Check read-only inventory auth and pricing API status for Azure and GCP",
)
async def get_providers_status(
    azure_service: AzureInventoryService = Depends(get_azure_inventory_service),
    gcp_service: GcpInventoryService = Depends(get_gcp_inventory_service),
) -> list[ProviderConnectionStatus]:
    """Return connection and authentication readiness for Azure and GCP."""
    az_status = await azure_service.get_connection_status()
    gcp_status = await gcp_service.get_connection_status()
    return [az_status, gcp_status]


@router.get(
    "/azure/subscriptions",
    response_model=list[CloudScopeSummary],
    status_code=status.HTTP_200_OK,
    summary="List authorized Azure subscriptions",
)
async def list_azure_subscriptions(
    azure_service: AzureInventoryService = Depends(get_azure_inventory_service),
) -> list[CloudScopeSummary]:
    """Return authorized Azure subscriptions available for read-only discovery."""
    return await azure_service.list_subscriptions()


@router.post(
    "/azure/analyze",
    response_model=SubscriptionOrProjectAnalysis,
    status_code=status.HTTP_200_OK,
    summary="Discover and analyze an Azure subscription hierarchy, architecture graph, and costs",
)
async def analyze_azure_subscription(
    request: ScopeAnalysisRequest,
    azure_service: AzureInventoryService = Depends(get_azure_inventory_service),
) -> SubscriptionOrProjectAnalysis:
    """Perform read-only discovery of Azure Subscription -> Resource Groups -> Resources and aggregate costs."""
    return await azure_service.analyze_subscription(
        subscription_id=request.scope_id,
        resource_group_filter=request.resource_group_filter,
        assumptions=request.workload_assumptions,
        buffer_percentage=request.safety_buffer_percentage,
        metric_window_days=request.metric_window_days,
    )


@router.get(
    "/gcp/projects",
    response_model=list[CloudScopeSummary],
    status_code=status.HTTP_200_OK,
    summary="List accessible GCP projects",
)
async def list_gcp_projects(
    gcp_service: GcpInventoryService = Depends(get_gcp_inventory_service),
) -> list[CloudScopeSummary]:
    """Return accessible GCP projects or labeled reference project fixture."""
    return await gcp_service.list_projects()


@router.post(
    "/gcp/analyze",
    response_model=SubscriptionOrProjectAnalysis,
    status_code=status.HTTP_200_OK,
    summary="Analyze GCP Organization -> Folder -> Project hierarchy, graph, and SKU costs",
)
async def analyze_gcp_project(
    request: ScopeAnalysisRequest,
    gcp_service: GcpInventoryService = Depends(get_gcp_inventory_service),
) -> SubscriptionOrProjectAnalysis:
    """Analyze GCP project resources, relationships, and deterministic Cloud Billing Catalog costs."""
    return await gcp_service.analyze_project(
        project_id=request.scope_id,
        assumptions=request.workload_assumptions,
        buffer_percentage=request.safety_buffer_percentage,
        metric_window_days=request.metric_window_days,
    )


@router.post(
    "/compare",
    response_model=MultiCloudComparisonResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare equivalent Azure and GCP architectures and deterministic costs",
)
async def compare_multi_cloud(
    request: MultiCloudComparisonRequest,
    comparator: MultiCloudComparatorService = Depends(get_comparator_service),
) -> MultiCloudComparisonResponse:
    """Generate and deterministically price comparable Azure and GCP architectures for identical workload assumptions."""
    return await comparator.compare_azure_and_gcp(request)
