"""Health and readiness probe API routes."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from cloud_recommender import __version__
from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.db.session import check_db_health

router = APIRouter(tags=["Health"])


class LivenessResponse(BaseModel):
    """Liveness probe response model."""

    status: str = Field(default="ok", description="Liveness status indicator")
    service: str = Field(description="Service identifier")
    environment: str = Field(description="Configured deployment environment")
    version: str = Field(description="Application release version")
    timestamp: str = Field(description="ISO 8601 UTC timestamp of check")


class ReadinessResponse(BaseModel):
    """Readiness probe response model detailing dependency states."""

    status: str = Field(description="Overall readiness: 'ready' or 'not_ready'")
    service: str = Field(description="Service identifier")
    environment: str = Field(description="Configured deployment environment")
    timestamp: str = Field(description="ISO 8601 UTC timestamp of check")
    dependencies: dict[str, Any] = Field(description="Status of individual external dependencies")


@router.get(
    "/health",
    response_model=LivenessResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Liveness Probe",
    description="Returns HTTP 200 if the FastAPI application process is alive and responsive.",
)
async def liveness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LivenessResponse:
    """Return basic application process liveness."""
    return LivenessResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.app_env,
        version=__version__,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Application Readiness Probe",
    description=(
        "Evaluates external dependencies (PostgreSQL database connectivity) "
        "and returns status. Returns HTTP 503 if critical dependencies are unreachable."
    ),
)
async def readiness(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessResponse:
    """Check readiness of critical dependencies without claiming health for unchecked components."""
    db_status = await check_db_health()

    is_db_ready = db_status.get("status") == "connected"

    # Compile dependency audit
    dependencies: dict[str, Any] = {
        "database": db_status,
        "azure_integration": {
            "status": "unconfigured" if not settings.azure_tenant_id else "configured_read_only",
            "checked": False,
            "mode": "read_only",
        },
        "microsoft_fabric": {
            "status": "enabled" if settings.fabric_enabled else "disabled",
            "checked": False,
        },
        "llm_orchestration": {
            "provider": settings.llm_provider,
            "status": "mock" if settings.llm_provider == "mock" else "configured",
            "checked": False,
        },
        "pricing_engine": {
            "mode": "offline_cache" if settings.offline_pricing_mode else "live_apis",
            "checked": False,
        },
    }

    if is_db_ready:
        response.status_code = status.HTTP_200_OK
        overall_status = "ready"
    else:
        # In non-production or when database is unreachable, signal not_ready via 503
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "not_ready"

    return ReadinessResponse(
        status=overall_status,
        service=settings.app_name,
        environment=settings.app_env,
        timestamp=datetime.now(UTC).isoformat(),
        dependencies=dependencies,
    )
