"""API routes for centralized infrastructure monitoring, historical telemetry, and log intelligence."""

from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.common import CloudProvider
from cloud_recommender.schemas.monitoring import (
    LogSearchResponse,
    LogSeverity,
    MonitoringOverviewResponse,
    MonitoringQueryRequest,
    ResourceDetailMonitoringResponse,
    TimeWindowPreset,
)
from cloud_recommender.schemas.token_economics import TokenEconomicsSummary
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
from cloud_recommender.services.monitoring.monitoring_service import CentralizedMonitoringService

router = APIRouter(prefix="/monitoring", tags=["Centralized Monitoring & Telemetry"])


def get_monitoring_service(
    settings: Settings = Depends(get_settings),
) -> CentralizedMonitoringService:
    azure_service = AzureInventoryService(settings=settings)
    gcp_service = GcpInventoryService(settings=settings)
    return CentralizedMonitoringService(
        settings=settings,
        azure_service=azure_service,
        gcp_service=gcp_service,
    )


class LogSearchRequest(BaseModel):
    """Payload for bounded and filtered log search."""

    provider: CloudProvider = Field(
        default=CloudProvider.AZURE, description="Target cloud provider."
    )
    scope_id: str = Field(..., description="Target subscription ID or GCP project ID.")
    query: str | None = Field(default=None, description="Search query string.")
    severity: LogSeverity | None = Field(default=None, description="Filter by log severity.")
    resource_id: str | None = Field(default=None, description="Filter by resource ID.")
    time_window: TimeWindowPreset = Field(
        default="7d", description="Selectable historical time window."
    )
    page: int = Field(default=1, ge=1, description="Page number.")
    page_size: int = Field(default=50, ge=1, le=200, description="Results per page.")


@router.post(
    "/overview",
    response_model=MonitoringOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Query centralized monitoring KPIs, timeseries metrics, alerts, and recurring errors",
)
async def get_monitoring_overview(
    request: MonitoringQueryRequest,
    service: CentralizedMonitoringService = Depends(get_monitoring_service),
) -> MonitoringOverviewResponse:
    """Return high-level infrastructure monitoring overview with KPI strip and timeseries."""
    return await service.get_monitoring_overview(request)


@router.post(
    "/resource",
    response_model=ResourceDetailMonitoringResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect individual service telemetry across 7 diagnostic tabs",
)
async def get_resource_monitoring_detail(
    request: MonitoringQueryRequest,
    service: CentralizedMonitoringService = Depends(get_monitoring_service),
) -> ResourceDetailMonitoringResponse:
    """Return comprehensive 7-tab operational and FinOps deep dive for an individual cloud service."""
    return await service.get_resource_monitoring_detail(request)


@router.post(
    "/logs",
    response_model=LogSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search historical log entries and audit events across the selected cloud scope",
)
async def search_monitoring_logs(
    request: LogSearchRequest,
    service: CentralizedMonitoringService = Depends(get_monitoring_service),
) -> LogSearchResponse:
    """Search and filter historical logs with credentials and secrets automatically sanitized."""
    return await service.search_logs(
        provider=request.provider,
        scope_id=request.scope_id,
        query=request.query,
        severity=request.severity,
        resource_id=request.resource_id,
        time_window=request.time_window,
        page=request.page,
        page_size=request.page_size,
    )


@router.get(
    "/sources",
    status_code=status.HTTP_200_OK,
    summary="Query active telemetry data sources and connection status",
)
async def get_monitoring_sources(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return active monitoring data sources and telemetry availability status."""
    has_az_creds = bool(
        settings.azure_subscription_id and settings.azure_tenant_id and settings.azure_client_id
    )
    has_gcp_creds = bool(settings.gcp_access_token or settings.google_application_credentials)

    return {
        "azure_monitor": {
            "status": "connected" if has_az_creds else "simulation_fixture",
            "is_live": has_az_creds,
            "capabilities": ["metrics", "activity_logs", "resource_health", "cost_management"],
            "retention_days": 90 if has_az_creds else 30,
        },
        "gcp_monitoring": {
            "status": "connected" if has_gcp_creds else "simulation_fixture",
            "is_live": has_gcp_creds,
            "capabilities": ["cloud_monitoring", "cloud_logging", "asset_inventory"],
            "retention_days": 30,
        },
        "policy": "Read-Only / Zero-Execution Enforced",
    }


@router.post(
    "/token-economics",
    response_model=TokenEconomicsSummary,
    status_code=status.HTTP_200_OK,
    summary="Query AI model token consumption, rate meters, and cost telemetry",
)
async def get_token_economics(
    request: MonitoringQueryRequest,
    service: CentralizedMonitoringService = Depends(get_monitoring_service),
) -> TokenEconomicsSummary:
    """Calculate token consumption, model breakdown, and estimated AI costs with official rate meters."""
    return await service.get_token_economics(request)
