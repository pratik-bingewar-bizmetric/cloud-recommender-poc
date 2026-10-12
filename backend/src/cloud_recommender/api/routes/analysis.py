"""API endpoints for application requirements analysis and clarifying questions."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.analysis import (
    RequirementsAnalysisRequest,
    RequirementsAnalysisResponse,
)
from cloud_recommender.services.ai.exceptions import (
    AzureAIFoundryAuthError,
    AzureAIFoundryNotConfiguredError,
    AzureAIFoundryRateLimitError,
    AzureAIFoundryResponseError,
    AzureAIFoundryTimeoutError,
)
from cloud_recommender.services.ai.foundry_provider import AzureAIFoundryProvider

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analysis", tags=["Requirements Analysis"])


def get_ai_provider(settings: Settings = Depends(get_settings)) -> AzureAIFoundryProvider:
    """Dependency injecting AzureAIFoundryProvider."""
    return AzureAIFoundryProvider(settings=settings)


@router.post(
    "/requirements",
    response_model=RequirementsAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze application idea and extract requirements",
    description=(
        "Analyzes natural language application idea using Azure AI Foundry. "
        "Extracts structured workload requirements, derives initial workload assumptions, "
        "and generates targeted clarifying questions for missing or ambiguous details."
    ),
)
async def analyze_requirements(
    request: RequirementsAnalysisRequest,
    ai_provider: AzureAIFoundryProvider = Depends(get_ai_provider),
) -> RequirementsAnalysisResponse:
    """Analyze application idea into structured requirements and clarifying inquiries."""
    try:
        profile, questions, assumptions, missing = await ai_provider.analyze_requirements(
            idea=request.idea,
            target_region=request.target_region,
            customer_preset=request.customer_preset,
        )

        return RequirementsAnalysisResponse(
            workload_profile=profile,
            clarifying_questions=questions,
            workload_assumptions=assumptions,
            missing_critical_requirements=missing,
            ai_provider_used="azure_ai_foundry",
            status="ready_for_architecture",
        )

    except AzureAIFoundryNotConfiguredError as exc:
        logger.error("azure_ai_foundry_not_configured", missing=exc.missing_vars)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "AZURE_AI_FOUNDRY_NOT_CONFIGURED",
                "message": str(exc),
                "missing_variables": exc.missing_vars,
                "guidance": (
                    "Please configure AZURE_AI_FOUNDRY_ENDPOINT, AZURE_AI_FOUNDRY_API_KEY, "
                    "and AZURE_AI_FOUNDRY_DEPLOYMENT_NAME in your environment or .env file."
                ),
            },
        ) from exc

    except AzureAIFoundryAuthError as exc:
        logger.error("azure_ai_foundry_auth_failure", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "AZURE_AI_FOUNDRY_AUTH_ERROR",
                "message": str(exc),
            },
        ) from exc

    except AzureAIFoundryRateLimitError as exc:
        logger.warning("azure_ai_foundry_rate_limited", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error_code": "AZURE_AI_FOUNDRY_RATE_LIMIT",
                "message": str(exc),
            },
        ) from exc

    except AzureAIFoundryTimeoutError as exc:
        logger.error("azure_ai_foundry_timeout", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "error_code": "AZURE_AI_FOUNDRY_TIMEOUT",
                "message": str(exc),
            },
        ) from exc

    except AzureAIFoundryResponseError as exc:
        logger.error("azure_ai_foundry_invalid_response", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "AZURE_AI_FOUNDRY_INVALID_RESPONSE",
                "message": str(exc),
            },
        ) from exc
