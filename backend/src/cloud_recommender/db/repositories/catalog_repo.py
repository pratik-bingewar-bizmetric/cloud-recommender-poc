"""Repository for CloudServiceCatalog database persistence and querying."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloud_recommender.db.models import CloudServiceCatalogModel
from cloud_recommender.schemas.catalog import CatalogServiceBase, CatalogServiceFilter
from cloud_recommender.schemas.common import CloudProvider


class CatalogRepository:
    """Async repository isolating CloudServiceCatalog database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, data: CatalogServiceBase) -> CloudServiceCatalogModel:
        """Idempotently insert or update a cloud service catalog entry."""
        stmt = select(CloudServiceCatalogModel).where(
            CloudServiceCatalogModel.provider == data.provider.value,
            CloudServiceCatalogModel.service_id == data.service_id,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.name = data.name
            existing.category = data.category.value
            existing.description = data.description
            existing.supported_regions = data.supported_regions
            existing.supported_compliance = [c.value for c in data.supported_compliance]
            existing.sla_percentage = data.sla_percentage
            existing.is_serverless = data.is_serverless
            existing.attributes = data.attributes
            existing.pricing_unit = data.pricing_unit
            existing.measurement_metric = data.measurement_metric
            existing.documentation_url = (
                str(data.documentation_url) if data.documentation_url else None
            )
            existing.pricing_source_type = data.pricing_source_type
            existing.pricing_reference_url = (
                str(data.pricing_reference_url) if data.pricing_reference_url else None
            )
            existing.dataset_version = data.dataset_version
            existing.retrieval_timestamp = data.retrieval_timestamp
            existing.provenance = data.provenance
            existing.status = data.status.value
            model = existing
        else:
            model = CloudServiceCatalogModel(
                provider=data.provider.value,
                service_id=data.service_id,
                name=data.name,
                category=data.category.value,
                description=data.description,
                supported_regions=data.supported_regions,
                supported_compliance=[c.value for c in data.supported_compliance],
                sla_percentage=data.sla_percentage,
                is_serverless=data.is_serverless,
                attributes=data.attributes,
                pricing_unit=data.pricing_unit,
                measurement_metric=data.measurement_metric,
                documentation_url=(str(data.documentation_url) if data.documentation_url else None),
                pricing_source_type=data.pricing_source_type,
                pricing_reference_url=(
                    str(data.pricing_reference_url) if data.pricing_reference_url else None
                ),
                dataset_version=data.dataset_version,
                retrieval_timestamp=data.retrieval_timestamp,
                provenance=data.provenance,
                status=data.status.value,
            )
            self.session.add(model)

        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def get_by_provider_and_id(
        self, provider: CloudProvider, service_id: str
    ) -> CloudServiceCatalogModel | None:
        """Retrieve a specific cloud service by provider and service ID."""
        stmt = select(CloudServiceCatalogModel).where(
            CloudServiceCatalogModel.provider == provider.value,
            CloudServiceCatalogModel.service_id == service_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_service_id(self, service_id: str) -> CloudServiceCatalogModel | None:
        """Retrieve a catalog service by service ID alone."""
        stmt = select(CloudServiceCatalogModel).where(
            CloudServiceCatalogModel.service_id == service_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_services(
        self, filter_params: CatalogServiceFilter
    ) -> tuple[Sequence[CloudServiceCatalogModel], int]:
        """Query catalog services with filtering and pagination."""
        query = select(CloudServiceCatalogModel)
        count_query = select(func.count(CloudServiceCatalogModel.id))

        conditions = []

        if filter_params.provider is not None:
            conditions.append(CloudServiceCatalogModel.provider == filter_params.provider.value)
        if filter_params.category is not None:
            conditions.append(CloudServiceCatalogModel.category == filter_params.category.value)
        if filter_params.is_serverless is not None:
            conditions.append(CloudServiceCatalogModel.is_serverless == filter_params.is_serverless)
        if filter_params.search:
            search_term = f"%{filter_params.search}%"
            conditions.append(
                or_(
                    CloudServiceCatalogModel.name.ilike(search_term),
                    CloudServiceCatalogModel.description.ilike(search_term),
                    CloudServiceCatalogModel.service_id.ilike(search_term),
                )
            )

        if conditions:
            query = query.where(*conditions)
            count_query = count_query.where(*conditions)

        # Count total matching
        total_res = await self.session.execute(count_query)
        total = int(total_res.scalar_one() or 0)

        # Apply pagination
        query = (
            query.order_by(
                CloudServiceCatalogModel.provider.asc(),
                CloudServiceCatalogModel.category.asc(),
                CloudServiceCatalogModel.name.asc(),
            )
            .limit(filter_params.limit)
            .offset(filter_params.offset)
        )

        result = await self.session.execute(query)
        items = result.scalars().all()
        return items, total

    async def seed_services(self, services: list[CatalogServiceBase]) -> int:
        """Idempotently seed a batch of catalog services."""
        count = 0
        for s in services:
            await self.upsert(s)
            count += 1
        return count
