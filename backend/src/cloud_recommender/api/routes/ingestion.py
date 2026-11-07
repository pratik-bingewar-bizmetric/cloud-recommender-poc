"""FastAPI routes for scope-aware ingestion, readiness validation, and execution monitoring."""

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.db.repositories.configuration_repo import (
    ResourceConfigurationRepository,
)
from cloud_recommender.db.repositories.ingestion_repo import IngestionRepository
from cloud_recommender.db.session import get_session_factory
from cloud_recommender.schemas.ingestion import (
    IngestionReadinessResponse,
    IngestionRunCreate,
    IngestionRunResponse,
    IngestionRunSummaryResponse,
)
from cloud_recommender.services.configuration.configuration_service import (
    ConfigurationService,
)
from cloud_recommender.services.ingestion.ingestion_orchestrator import (
    IngestionConflictError,
    IngestionNotReadyError,
    IngestionOrchestrator,
)
from cloud_recommender.services.ingestion.readiness_service import (
    IngestionReadinessService,
)
from cloud_recommender.services.ingestion.scope_service import ScopeEnforcementService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ingestion", tags=["Scope-Aware Ingestion & Configuration Enforcement"])


async def get_ingestion_orchestrator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncGenerator[IngestionOrchestrator, None]:
    """FastAPI dependency supplying IngestionOrchestrator with DB repository or memory fallback."""
    if settings.catalog_offline_mode:
        config_service = ConfigurationService(settings=settings)
        readiness_service = IngestionReadinessService(config_service=config_service)
        scope_service = ScopeEnforcementService(configuration_service=config_service)
        yield IngestionOrchestrator(
            repository=None,
            config_service=config_service,
            readiness_service=readiness_service,
            scope_service=scope_service,
            settings=settings,
        )
        return

    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                config_repo = ResourceConfigurationRepository(session=session)
                ingest_repo = IngestionRepository(session=session)
                config_service = ConfigurationService(repository=config_repo, settings=settings)
                readiness_service = IngestionReadinessService(config_service=config_service)
                scope_service = ScopeEnforcementService(configuration_service=config_service)
                yield IngestionOrchestrator(
                    repository=ingest_repo,
                    config_service=config_service,
                    readiness_service=readiness_service,
                    scope_service=scope_service,
                    settings=settings,
                )
            except BaseException:
                await session.rollback()
                raise
            finally:
                await session.close()
    except Exception as exc:
        logger.warning("db_session_failed_falling_back_to_memory_ingestion", error=str(exc))
        config_service = ConfigurationService(settings=settings)
        readiness_service = IngestionReadinessService(config_service=config_service)
        scope_service = ScopeEnforcementService(configuration_service=config_service)
        yield IngestionOrchestrator(
            repository=None,
            config_service=config_service,
            readiness_service=readiness_service,
            scope_service=scope_service,
            settings=settings,
        )


@router.get(
    "/{connection_id}/readiness",
    response_model=IngestionReadinessResponse,
    summary="Validate Ingestion Pre-Flight Readiness",
)
async def check_readiness(
    connection_id: str,
    orchestrator: Annotated[IngestionOrchestrator, Depends(get_ingestion_orchestrator)],
) -> IngestionReadinessResponse:
    """Pre-flight check verifying connection, saved scope, versioning, and cloud permissions."""
    return await orchestrator.readiness_service.validate_readiness(connection_id)


@router.post(
    "/{connection_id}/runs",
    response_model=IngestionRunResponse,
    summary="Trigger Scope-Aware Ingestion Run",
)
async def trigger_run(
    connection_id: str,
    orchestrator: Annotated[IngestionOrchestrator, Depends(get_ingestion_orchestrator)],
    payload: IngestionRunCreate | None = None,
) -> IngestionRunResponse:
    """Trigger a new ingestion execution run bounded strictly to the active saved scope."""
    try:
        return await orchestrator.trigger_ingestion(connection_id, run_create=payload)
    except IngestionNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Ingestion cannot start because pre-flight readiness checks failed.",
                "readiness_state": exc.readiness.readiness_state.value,
                "details": exc.readiness.details,
                "missing_requirements": exc.readiness.missing_requirements,
            },
        ) from exc
    except IngestionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("ingestion_trigger_unhandled_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion run failed unexpectedly: {str(exc)}",
        ) from exc


@router.get(
    "/{connection_id}/runs",
    response_model=list[IngestionRunSummaryResponse],
    summary="List Ingestion Execution History with Version Lineage",
)
async def list_runs(
    connection_id: str,
    orchestrator: Annotated[IngestionOrchestrator, Depends(get_ingestion_orchestrator)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[IngestionRunSummaryResponse]:
    """Retrieve historical ingestion runs for a connection, preserving configuration version lineage."""
    return await orchestrator.list_runs(connection_id, limit=limit)


@router.get(
    "/runs/{run_id}",
    response_model=IngestionRunResponse,
    summary="Get Ingestion Run Details and Per-Resource Outcomes",
)
async def get_run_details(
    run_id: UUID,
    orchestrator: Annotated[IngestionOrchestrator, Depends(get_ingestion_orchestrator)],
) -> IngestionRunResponse:
    """Fetch complete execution details and per-resource extraction statuses for an ingestion run."""
    run = await orchestrator.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion run '{run_id}' not found.",
        )
    return run


@router.post(
    "/runs/{run_id}/retry",
    response_model=IngestionRunResponse,
    summary="Retry a Failed or Partial Ingestion Run",
)
async def retry_run(
    run_id: UUID,
    orchestrator: Annotated[IngestionOrchestrator, Depends(get_ingestion_orchestrator)],
) -> IngestionRunResponse:
    """Re-execute a failed or partially failed ingestion run."""
    try:
        return await orchestrator.retry_run(run_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except IngestionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retry failed: {str(exc)}",
        ) from exc
