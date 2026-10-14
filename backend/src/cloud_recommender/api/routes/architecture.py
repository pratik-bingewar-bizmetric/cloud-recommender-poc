"""API endpoints for generating production Azure architectures and recommendations."""

from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.analysis import ArchitectureGenerationRequest
from cloud_recommender.schemas.common import CloudProvider, RecommendationStatus
from cloud_recommender.schemas.recommendation import RecommendationReport
from cloud_recommender.schemas.workload import WorkloadProfile
from cloud_recommender.services.ai.exceptions import (
    AzureAIFoundryAuthError,
    AzureAIFoundryNotConfiguredError,
    AzureAIFoundryRateLimitError,
    AzureAIFoundryResponseError,
    AzureAIFoundryTimeoutError,
)
from cloud_recommender.services.ai.foundry_provider import AzureAIFoundryProvider
from cloud_recommender.services.pricing.engine import AzurePricingEngine

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/architecture", tags=["Architecture Generation"])


def get_ai_provider(settings: Settings = Depends(get_settings)) -> AzureAIFoundryProvider:
    return AzureAIFoundryProvider(settings=settings)


def get_pricing_engine(settings: Settings = Depends(get_settings)) -> AzurePricingEngine:
    return AzurePricingEngine(settings=settings)


@router.post(
    "/generate",
    response_model=RecommendationReport,
    status_code=status.HTTP_200_OK,
    summary="Generate production Azure architecture and deterministic pricing",
    description=(
        "Uses Azure AI Foundry to reason over requirements and clarifications "
        "to synthesize a production Azure architecture. Components are then "
        "priced via the Azure Pricing Engine using official rates."
    ),
)
async def generate_architecture(
    request: ArchitectureGenerationRequest,
    ai_provider: AzureAIFoundryProvider = Depends(get_ai_provider),
    pricing_engine: AzurePricingEngine = Depends(get_pricing_engine),
) -> RecommendationReport:
    """Generate production Azure architecture recommendation report."""
    profile_id = uuid4()
    profile = WorkloadProfile.model_validate(
        {**request.workload_profile.model_dump(), "id": profile_id}
    )

    try:
        (
            raw_components,
            trade_offs,
            arch_description,
            mermaid_diagram,
            assumptions_list,
            limitations_list,
        ) = await ai_provider.generate_architecture(
            workload=profile,
            assumptions=request.workload_assumptions,
            clarifications=request.clarifications,
        )

    except AzureAIFoundryNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "AZURE_AI_FOUNDRY_NOT_CONFIGURED",
                "message": str(exc),
                "missing_variables": exc.missing_vars,
            },
        ) from exc
    except AzureAIFoundryAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "AZURE_AI_FOUNDRY_AUTH_ERROR", "message": str(exc)},
        ) from exc
    except AzureAIFoundryRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error_code": "AZURE_AI_FOUNDRY_RATE_LIMIT", "message": str(exc)},
        ) from exc
    except AzureAIFoundryTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error_code": "AZURE_AI_FOUNDRY_TIMEOUT", "message": str(exc)},
        ) from exc
    except AzureAIFoundryResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error_code": "AZURE_AI_FOUNDRY_INVALID_RESPONSE", "message": str(exc)},
        ) from exc

    # Deterministically price components
    (
        priced_components,
        cost_breakdown,
        provenance,
        missing_warnings,
        pricing_assumptions,
    ) = await pricing_engine.price_architecture(
        components=raw_components,
        assumptions=request.workload_assumptions,
        region=request.target_region,
        buffer_percentage=request.workload_profile.cost_buffer_percentage,
    )

    combined_assumptions = assumptions_list + [
        a for a in pricing_assumptions if a not in assumptions_list
    ]

    report = RecommendationReport(
        id=uuid4(),
        workload_profile_id=profile_id,
        provider=CloudProvider.AZURE,
        region=request.target_region,
        architecture_description=arch_description,
        components=priced_components,
        cost_breakdown=cost_breakdown,
        currency="USD",
        assumptions=combined_assumptions,
        limitations=limitations_list,
        trade_offs=trade_offs,
        pricing_provenance=provenance,
        status=RecommendationStatus.DRAFT,
        mermaid_diagram=mermaid_diagram,
    )

    return report
