"""API endpoints for interactive deterministic cost simulation and price refreshing."""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.analysis import (
    CostSimulationRequest,
    CostSimulationResponse,
)
from cloud_recommender.services.pricing.engine import AzurePricingEngine

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/pricing", tags=["Cost Simulation & Pricing"])


def get_pricing_engine(settings: Settings = Depends(get_settings)) -> AzurePricingEngine:
    return AzurePricingEngine(settings=settings)


class PriceRefreshRequest(BaseModel):
    service_ids: list[str] = Field(
        default_factory=lambda: [
            "azure-container-apps",
            "azure-app-service",
            "azure-postgres-flexible",
            "azure-blob-storage",
            "azure-monitor",
        ]
    )
    region: str = Field(default="eastus")


class PriceRefreshResponse(BaseModel):
    status: str
    refreshed_count: int
    region: str
    timestamp: datetime


@router.post(
    "/simulate",
    response_model=CostSimulationResponse,
    status_code=status.HTTP_200_OK,
    summary="Deterministically recalculate architecture costs",
    description=(
        "Immediately recalculates itemized and aggregated monthly, 5-month, and annual costs "
        "when architecture components or workload parameters are edited in the UI. "
        "Does not invoke the LLM, guaranteeing sub-second response times and 100% determinism."
    ),
)
async def simulate_costs(
    request: CostSimulationRequest,
    pricing_engine: AzurePricingEngine = Depends(get_pricing_engine),
) -> CostSimulationResponse:
    """Recalculate costs for modified architecture components and workload assumptions."""
    (
        priced_components,
        cost_breakdown,
        provenance,
        missing_warnings,
        assumptions_list,
    ) = await pricing_engine.price_architecture(
        components=request.components,
        assumptions=request.workload_assumptions,
        region=request.target_region,
        buffer_percentage=request.safety_buffer_percentage,
    )

    return CostSimulationResponse(
        cost_breakdown=cost_breakdown,
        components=priced_components,
        pricing_provenance=provenance,
        missing_price_warnings=missing_warnings,
        assumptions=assumptions_list,
        calculation_timestamp=datetime.now(UTC),
    )


@router.post(
    "/refresh",
    response_model=PriceRefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh cached prices from official Azure Retail Prices API",
    description="Queries the public Azure Retail Prices API to update local pricing cache.",
)
async def refresh_prices(
    request: PriceRefreshRequest,
    pricing_engine: AzurePricingEngine = Depends(get_pricing_engine),
) -> PriceRefreshResponse:
    """Force refresh of pricing cache for target services."""
    refreshed = 0
    for sid in request.service_ids:
        try:
            # Query and cache
            await pricing_engine.get_price_for_service(sid, region=request.region)
            refreshed += 1
        except Exception as exc:
            logger.warning("pricing_refresh_failed_for_service", service_id=sid, error=str(exc))

    return PriceRefreshResponse(
        status="completed",
        refreshed_count=refreshed,
        region=request.region,
        timestamp=datetime.now(UTC),
    )
