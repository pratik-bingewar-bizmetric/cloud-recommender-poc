"""Ingestion orchestrator service.

Coordinates scope-aware ingestion runs across cloud providers with:
- Strict pre-flight readiness validation.
- Duplicate run protection.
- Server-side scope enforcement.
- Immutable configuration version lineage.
- Partial failure resilience and per-resource tracking.
- Safe retry execution.
- Dual persistence: SQLAlchemy database repository with in-memory fallback.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.db.models import IngestionRunModel
from cloud_recommender.db.repositories.ingestion_repo import IngestionRepository
from cloud_recommender.schemas.ingestion import (
    IngestionReadinessResponse,
    IngestionResourceStatusResponse,
    IngestionRunCreate,
    IngestionRunResponse,
    IngestionRunStatus,
    IngestionRunSummaryResponse,
    IngestionScope,
    ResourceIngestionStatus,
)
from cloud_recommender.services.configuration.configuration_service import (
    ConfigurationService,
)
from cloud_recommender.services.ingestion.providers.aws import AwsProviderIngestor
from cloud_recommender.services.ingestion.providers.azure import AzureProviderIngestor
from cloud_recommender.services.ingestion.providers.base import (
    ResourceExtractionResult,
)
from cloud_recommender.services.ingestion.providers.databricks import (
    DatabricksWorkspaceIngestor,
)
from cloud_recommender.services.ingestion.providers.gcp import GcpProviderIngestor
from cloud_recommender.services.ingestion.readiness_service import IngestionReadinessService
from cloud_recommender.services.ingestion.scope_service import ScopeEnforcementService

logger = structlog.get_logger(__name__)


class IngestionConflictError(Exception):
    """Raised when an ingestion run is already actively running for the given connection."""

    pass


class IngestionNotReadyError(Exception):
    """Raised when an ingestion run is requested but pre-flight readiness checks fail."""

    def __init__(self, readiness: IngestionReadinessResponse) -> None:
        self.readiness = readiness
        super().__init__(readiness.details)


class IngestionOrchestrator:
    """Service orchestrating scope-aware ingestion runs with version lineage."""

    # In-memory execution store for session-less runs and unit tests
    _memory_runs: dict[str, list[IngestionRunResponse]] = {}

    def __init__(
        self,
        repository: IngestionRepository | None = None,
        config_service: ConfigurationService | None = None,
        readiness_service: IngestionReadinessService | None = None,
        scope_service: ScopeEnforcementService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()
        self.config_service = config_service or ConfigurationService()
        self.readiness_service = readiness_service or IngestionReadinessService(
            config_service=self.config_service
        )
        self.scope_service = scope_service or ScopeEnforcementService(
            configuration_service=self.config_service
        )

    async def trigger_ingestion(
        self, connection_id: str, run_create: IngestionRunCreate | None = None
    ) -> IngestionRunResponse:
        """Execute a scope-aware ingestion run after strict pre-flight validation."""
        req = run_create or IngestionRunCreate()

        # Step 1: Pre-flight readiness check
        readiness = await self.readiness_service.validate_readiness(connection_id)
        if not readiness.can_start_ingestion:
            logger.warning(
                "ingestion_blocked_by_readiness",
                connection_id=connection_id,
                state=readiness.readiness_state.value,
                details=readiness.details,
            )
            raise IngestionNotReadyError(readiness)

        # Step 2: Duplicate run protection
        await self._check_duplicate_running(connection_id)

        # Step 3: Resolve effective scope
        scope = await self.scope_service.calculate_effective_scope(connection_id)
        scope_snapshot: dict[str, Any] = {
            "effective_resource_ids": scope.effective_resource_ids,
            "effective_workspace_ids": scope.effective_workspace_ids,
            "subscriptions": scope.subscriptions,
            "resource_groups": scope.resource_groups,
        }

        # Step 4: Initialize run record
        run_id = uuid4()
        started_at = datetime.now(UTC)

        if self.repository:
            run_model = await self.repository.create_run(
                connection_id=connection_id,
                provider=scope.provider,
                configuration_id=scope.configuration_id,
                configuration_version=scope.configuration_version,
                triggered_by=req.triggered_by,
                total_resources_scoped=len(scope.effective_resource_ids),
                scope_snapshot=scope_snapshot,
            )
            run_id = run_model.run_id

        # Step 5: Execute provider extraction bounded strictly to effective scope
        extraction_results = await self._execute_provider_ingestion(scope)

        # Step 6: Evaluate outcomes & per-resource tracking
        successful_count = 0
        failed_count = 0
        resource_statuses: list[IngestionResourceStatusResponse] = []

        for res in extraction_results:
            is_success = res.status == ResourceIngestionStatus.SUCCESS
            if is_success:
                successful_count += 1
            else:
                failed_count += 1

            status_dto = IngestionResourceStatusResponse(
                resource_id=res.resource_id,
                resource_type=res.resource_type,
                region=res.region,
                status=res.status,
                inventory_extracted=res.inventory_extracted,
                cost_extracted=res.cost_extracted,
                metrics_extracted=res.metrics_extracted,
                extracted_records_count=res.extracted_records_count,
                error_message=res.error_message,
            )
            resource_statuses.append(status_dto)

            if self.repository:
                await self.repository.record_resource_status(
                    run_id=run_id,
                    resource_id=res.resource_id,
                    resource_type=res.resource_type,
                    region=res.region,
                    status=res.status,
                    inventory_extracted=res.inventory_extracted,
                    cost_extracted=res.cost_extracted,
                    metrics_extracted=res.metrics_extracted,
                    extracted_records_count=res.extracted_records_count,
                    error_message=res.error_message,
                )

        # Determine overall run status
        total_scoped = len(scope.effective_resource_ids)
        if failed_count == 0:
            final_status = IngestionRunStatus.COMPLETED
            err_msg = None
        elif successful_count > 0:
            final_status = IngestionRunStatus.PARTIAL_FAILURE
            err_msg = f"{failed_count} of {total_scoped} resources failed extraction."
        else:
            final_status = IngestionRunStatus.FAILED
            err_msg = f"All {total_scoped} scoped resources failed extraction."

        completed_at = datetime.now(UTC)

        # Persist final run state
        if self.repository:
            await self.repository.update_run_status(
                run_id=run_id,
                status=final_status,
                successful_count=successful_count,
                failed_count=failed_count,
                error_message=err_msg,
                completed_at=completed_at,
            )

        run_resp = IngestionRunResponse(
            run_id=run_id,
            connection_id=connection_id,
            provider=scope.provider,
            configuration_id=scope.configuration_id,
            configuration_version=scope.configuration_version,
            status=final_status,
            triggered_by=req.triggered_by,
            started_at=started_at,
            completed_at=completed_at,
            total_resources_scoped=total_scoped,
            successful_resources_count=successful_count,
            failed_resources_count=failed_count,
            error_message=err_msg,
            scope_snapshot=scope_snapshot,
            resource_statuses=resource_statuses,
        )

        # In-memory history tracking
        conn_runs = self._memory_runs.setdefault(connection_id, [])
        conn_runs.insert(0, run_resp)

        logger.info(
            "ingestion_run_completed",
            run_id=str(run_id),
            status=final_status.value,
            successful=successful_count,
            failed=failed_count,
        )
        return run_resp

    async def retry_run(self, run_id: UUID) -> IngestionRunResponse:
        """Retry a previously failed or partial_failure ingestion run."""
        prior_run = await self.get_run(run_id)
        if not prior_run:
            raise ValueError(f"Ingestion run '{run_id}' not found.")

        if prior_run.status not in (
            IngestionRunStatus.FAILED,
            IngestionRunStatus.PARTIAL_FAILURE,
        ):
            raise ValueError(
                f"Run '{run_id}' has status '{prior_run.status.value}' and cannot be retried."
            )

        logger.info(
            "retrying_ingestion_run", run_id=str(run_id), connection_id=prior_run.connection_id
        )
        # Re-trigger with force_resync=True
        return await self.trigger_ingestion(
            prior_run.connection_id,
            run_create=IngestionRunCreate(force_resync=True, triggered_by="retry"),
        )

    async def get_run(self, run_id: UUID) -> IngestionRunResponse | None:
        """Fetch full details and per-resource status for a given run."""
        if self.repository:
            model = await self.repository.get_run(run_id)
            if model:
                return self._model_to_response(model)

        # In-memory search
        for runs in self._memory_runs.values():
            for r in runs:
                if r.run_id == run_id:
                    return r
        return None

    async def list_runs(
        self, connection_id: str, limit: int = 50
    ) -> list[IngestionRunSummaryResponse]:
        """List historical ingestion runs for a connection, retaining historical version lineage."""
        if self.repository:
            models = await self.repository.list_runs(connection_id, limit=limit)
            return [
                IngestionRunSummaryResponse(
                    run_id=m.run_id,
                    connection_id=m.connection_id,
                    provider=m.provider,
                    configuration_version=m.configuration_version,
                    status=IngestionRunStatus(m.status),
                    triggered_by=m.triggered_by,
                    started_at=m.started_at,
                    completed_at=m.completed_at,
                    total_resources_scoped=m.total_resources_scoped,
                    successful_resources_count=m.successful_resources_count,
                    failed_resources_count=m.failed_resources_count,
                    error_message=m.error_message,
                )
                for m in models
            ]

        # In-memory fallback
        runs = self._memory_runs.get(connection_id, [])
        return [
            IngestionRunSummaryResponse(
                run_id=r.run_id,
                connection_id=r.connection_id,
                provider=r.provider,
                configuration_version=r.configuration_version,
                status=r.status,
                triggered_by=r.triggered_by,
                started_at=r.started_at,
                completed_at=r.completed_at,
                total_resources_scoped=r.total_resources_scoped,
                successful_resources_count=r.successful_resources_count,
                failed_resources_count=r.failed_resources_count,
                error_message=r.error_message,
            )
            for r in runs[:limit]
        ]

    async def _check_duplicate_running(self, connection_id: str) -> None:
        """Ensure no concurrent run is already executing for this connection."""
        if self.repository:
            active = await self.repository.get_active_run_for_connection(connection_id)
            if active:
                raise IngestionConflictError(
                    f"An ingestion run ('{active.run_id}') is already in progress for connection '{connection_id}'."
                )
        else:
            runs = self._memory_runs.get(connection_id, [])
            for r in runs:
                if r.status in (IngestionRunStatus.RUNNING, IngestionRunStatus.PENDING):
                    raise IngestionConflictError(
                        f"An ingestion run ('{r.run_id}') is already in progress for connection '{connection_id}'."
                    )

    async def _execute_provider_ingestion(
        self, scope: IngestionScope
    ) -> list[ResourceExtractionResult]:
        """Dispatch extraction to the appropriate modular provider ingestors."""
        provider = scope.provider.lower()
        results: list[ResourceExtractionResult] = []

        if provider == "azure":
            azure_ingestor = AzureProviderIngestor(settings=self.settings)
            azure_results = await azure_ingestor.ingest_scope(scope)
            results.extend(azure_results)

            # If Databricks workspaces are in scope, extract workspace telemetry
            if scope.effective_workspace_ids:
                db_ingestor = DatabricksWorkspaceIngestor(settings=self.settings)
                db_results = await db_ingestor.ingest_scope(scope)
                # Avoid duplicate entries if workspace was already processed
                existing_ids = {r.resource_id for r in results}
                for dbr in db_results:
                    if dbr.resource_id not in existing_ids:
                        results.append(dbr)

        elif provider == "gcp":
            gcp_ingestor = GcpProviderIngestor(settings=self.settings)
            results = await gcp_ingestor.ingest_scope(scope)

        elif provider == "aws":
            aws_ingestor = AwsProviderIngestor()
            results = await aws_ingestor.ingest_scope(scope)

        else:
            logger.warning("unsupported_provider_in_orchestration", provider=provider)
            for res_id in scope.effective_resource_ids:
                results.append(
                    ResourceExtractionResult(
                        resource_id=res_id,
                        status=ResourceIngestionStatus.SKIPPED,
                        error_message=f"Provider '{provider}' is not supported.",
                    )
                )

        return results

    def _model_to_response(self, model: IngestionRunModel) -> IngestionRunResponse:
        """Convert SQLAlchemy IngestionRunModel to Pydantic IngestionRunResponse."""
        resource_statuses = [
            IngestionResourceStatusResponse(
                resource_id=r.resource_id,
                resource_type=r.resource_type,
                region=r.region,
                status=ResourceIngestionStatus(r.status),
                inventory_extracted=r.inventory_extracted,
                cost_extracted=r.cost_extracted,
                metrics_extracted=r.metrics_extracted,
                extracted_records_count=r.extracted_records_count,
                error_message=r.error_message,
            )
            for r in (model.resource_records or [])
        ]

        return IngestionRunResponse(
            run_id=model.run_id,
            connection_id=model.connection_id,
            provider=model.provider,
            configuration_id=model.configuration_id,
            configuration_version=model.configuration_version,
            status=IngestionRunStatus(model.status),
            triggered_by=model.triggered_by,
            started_at=model.started_at,
            completed_at=model.completed_at,
            total_resources_scoped=model.total_resources_scoped,
            successful_resources_count=model.successful_resources_count,
            failed_resources_count=model.failed_resources_count,
            error_message=model.error_message,
            scope_snapshot=model.scope_snapshot_json or {},
            resource_statuses=resource_statuses,
        )
