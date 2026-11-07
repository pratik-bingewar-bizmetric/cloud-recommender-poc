"""Repository for persisting and querying scope-aware ingestion runs and lineage."""

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloud_recommender.db.models import IngestionResourceRecordModel, IngestionRunModel
from cloud_recommender.schemas.ingestion import IngestionRunStatus, ResourceIngestionStatus

logger = structlog.get_logger(__name__)


class IngestionRepository:
    """Async repository for managing IngestionRunModel and IngestionResourceRecordModel."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(
        self,
        connection_id: str,
        provider: str,
        configuration_id: UUID,
        configuration_version: int,
        triggered_by: str,
        total_resources_scoped: int,
        scope_snapshot: dict[str, Any],
    ) -> IngestionRunModel:
        """Create a new ingestion run record initialized in PENDING or RUNNING status."""
        run = IngestionRunModel(
            run_id=uuid.uuid4(),
            connection_id=connection_id,
            provider=provider.lower(),
            configuration_id=configuration_id,
            configuration_version=configuration_version,
            status=IngestionRunStatus.RUNNING.value,
            triggered_by=triggered_by,
            started_at=datetime.now(UTC),
            completed_at=None,
            total_resources_scoped=total_resources_scoped,
            successful_resources_count=0,
            failed_resources_count=0,
            error_message=None,
            scope_snapshot_json=scope_snapshot,
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        logger.info(
            "ingestion_run_created",
            run_id=str(run.run_id),
            connection_id=connection_id,
            configuration_version=configuration_version,
            total_scoped=total_resources_scoped,
        )
        return run

    async def get_run(self, run_id: UUID) -> IngestionRunModel | None:
        """Fetch a specific ingestion run by run_id."""
        stmt = select(IngestionRunModel).where(IngestionRunModel.run_id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_runs(self, connection_id: str, limit: int = 50) -> list[IngestionRunModel]:
        """List ingestion execution history for a connection, ordered descending by start time."""
        stmt = (
            select(IngestionRunModel)
            .where(IngestionRunModel.connection_id == connection_id)
            .order_by(desc(IngestionRunModel.started_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_run_for_connection(self, connection_id: str) -> IngestionRunModel | None:
        """Check for any concurrent active run for the same connection (duplicate protection)."""
        stmt = (
            select(IngestionRunModel)
            .where(
                IngestionRunModel.connection_id == connection_id,
                IngestionRunModel.status.in_(
                    [IngestionRunStatus.PENDING.value, IngestionRunStatus.RUNNING.value]
                ),
            )
            .order_by(desc(IngestionRunModel.started_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_run_status(
        self,
        run_id: UUID,
        status: IngestionRunStatus,
        successful_count: int,
        failed_count: int,
        error_message: str | None = None,
        completed_at: datetime | None = None,
    ) -> IngestionRunModel | None:
        """Update the final lifecycle status and metrics of a run."""
        run = await self.get_run(run_id)
        if not run:
            return None

        run.status = status.value
        run.successful_resources_count = successful_count
        run.failed_resources_count = failed_count
        run.error_message = error_message
        run.completed_at = completed_at or datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(run)
        logger.info(
            "ingestion_run_status_updated",
            run_id=str(run_id),
            status=status.value,
            successful=successful_count,
            failed=failed_count,
        )
        return run

    async def record_resource_status(
        self,
        run_id: UUID,
        resource_id: str,
        resource_type: str | None,
        region: str | None,
        status: ResourceIngestionStatus,
        inventory_extracted: bool = False,
        cost_extracted: bool = False,
        metrics_extracted: bool = False,
        extracted_records_count: int = 0,
        error_message: str | None = None,
    ) -> IngestionResourceRecordModel:
        """Record per-resource execution details within a run."""
        record = IngestionResourceRecordModel(
            id=uuid.uuid4(),
            run_id=run_id,
            resource_id=resource_id,
            resource_type=resource_type,
            region=region,
            status=status.value,
            inventory_extracted=inventory_extracted,
            cost_extracted=cost_extracted,
            metrics_extracted=metrics_extracted,
            extracted_records_count=extracted_records_count,
            error_message=error_message,
            created_at=datetime.now(UTC),
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record
