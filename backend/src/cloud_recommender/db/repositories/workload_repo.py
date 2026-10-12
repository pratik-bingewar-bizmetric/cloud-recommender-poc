"""Repository for WorkloadProfile database persistence."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloud_recommender.db.models import WorkloadProfileModel
from cloud_recommender.schemas.workload import WorkloadProfileCreate


class WorkloadRepository:
    """Async repository isolating WorkloadProfile database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: WorkloadProfileCreate) -> WorkloadProfileModel:
        """Create and persist a new WorkloadProfile record."""
        model = WorkloadProfileModel(
            name=data.name,
            description=data.description,
            category=data.category.value,
            target_traffic_rps=data.target_traffic_rps,
            monthly_active_users=data.monthly_active_users,
            peak_multiplier=data.peak_multiplier,
            target_sla_percentage=data.target_sla_percentage,
            high_availability=data.high_availability,
            multi_region=data.multi_region,
            rpo_minutes=data.rpo_minutes,
            rto_minutes=data.rto_minutes,
            compliance_frameworks=[c.value for c in data.compliance_frameworks],
            data_classification=data.data_classification,
            storage_volume_gb=data.storage_volume_gb,
            monthly_data_egress_gb=data.monthly_data_egress_gb,
            database_type=data.database_type,
            primary_region=data.primary_region,
            target_regions=data.target_regions,
            currency=data.currency,
            max_monthly_budget=data.max_monthly_budget,
            cost_buffer_percentage=data.cost_buffer_percentage,
            estimation_assumptions=data.estimation_assumptions,
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def get_by_id(self, workload_id: UUID) -> WorkloadProfileModel | None:
        """Retrieve a workload profile by its stable UUID."""
        stmt = select(WorkloadProfileModel).where(WorkloadProfileModel.id == workload_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 50, offset: int = 0) -> Sequence[WorkloadProfileModel]:
        """List workload profiles with pagination."""
        stmt = (
            select(WorkloadProfileModel)
            .order_by(WorkloadProfileModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Return total count of persisted workload profiles."""
        stmt = select(func.count(WorkloadProfileModel.id))
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)
