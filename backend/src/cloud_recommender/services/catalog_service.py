"""Business service for querying and filtering the cloud service catalog."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cloud_recommender.catalog.seeds import load_curated_catalog
from cloud_recommender.db.models import CloudServiceCatalogModel
from cloud_recommender.db.repositories.catalog_repo import CatalogRepository
from cloud_recommender.schemas.catalog import (
    CatalogService,
    CatalogServiceFilter,
    CatalogServiceListResponse,
)
from cloud_recommender.schemas.common import ComplianceStandard

logger = structlog.get_logger(__name__)


class CatalogServiceManager:
    """Service orchestrating catalog queries across database repository with fixture fallback."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def list_catalog_services(
        self, filters: CatalogServiceFilter
    ) -> CatalogServiceListResponse:
        """List catalog services applying filters with fixture fallback."""
        if self.session is not None:
            try:
                repo = CatalogRepository(self.session)
                models, total = await repo.list_services(filters)
                if total > 0:
                    items = [self._model_to_schema(m) for m in models]
                    return CatalogServiceListResponse(
                        items=items,
                        total=total,
                        limit=filters.limit,
                        offset=filters.offset,
                    )
            except Exception as exc:
                logger.warning(
                    "database_catalog_query_failed_falling_back_to_fixtures",
                    error=str(exc),
                )

        # Fallback to in-memory curated catalog fixtures
        return self._filter_fixtures(filters)

    async def get_catalog_service(self, service_id: str) -> CatalogService | None:
        """Retrieve a single catalog service by service_id."""
        if self.session is not None:
            try:
                repo = CatalogRepository(self.session)
                model = await repo.get_by_service_id(service_id)
                if model is not None:
                    return self._model_to_schema(model)
            except Exception as exc:
                logger.warning(
                    "database_catalog_lookup_failed_falling_back_to_fixtures",
                    error=str(exc),
                )

        # Fallback lookup in curated fixtures
        fixtures = load_curated_catalog()
        for f in fixtures:
            if f.service_id == service_id:
                return CatalogService.model_validate(f.model_dump())
        return None

    def _filter_fixtures(self, filters: CatalogServiceFilter) -> CatalogServiceListResponse:
        """Filter the in-memory curated catalog fixtures."""
        fixtures = load_curated_catalog()
        filtered = []

        for item in fixtures:
            if filters.provider and item.provider != filters.provider:
                continue
            if filters.category and item.category != filters.category:
                continue
            if filters.is_serverless is not None and item.is_serverless != filters.is_serverless:
                continue
            if (
                filters.region
                and filters.region not in item.supported_regions
                and "global" not in item.supported_regions
            ):
                continue
            if filters.compliance and filters.compliance not in item.supported_compliance:
                continue
            if filters.search:
                term = filters.search.lower()
                if (
                    term not in item.name.lower()
                    and term not in item.description.lower()
                    and term not in item.service_id.lower()
                ):
                    continue
            filtered.append(CatalogService.model_validate(item.model_dump()))

        total = len(filtered)
        paged = filtered[filters.offset : filters.offset + filters.limit]

        return CatalogServiceListResponse(
            items=paged,
            total=total,
            limit=filters.limit,
            offset=filters.offset,
        )

    @staticmethod
    def _model_to_schema(model: CloudServiceCatalogModel) -> CatalogService:
        """Convert a SQLAlchemy ORM model to a validated Pydantic schema."""
        compliance_enums = [
            ComplianceStandard(c)
            for c in model.supported_compliance
            if c in ComplianceStandard._value2member_map_
        ]
        return CatalogService(
            provider=model.provider,  # type: ignore[arg-type]
            service_id=model.service_id,
            name=model.name,
            category=model.category,  # type: ignore[arg-type]
            description=model.description,
            supported_regions=model.supported_regions,
            supported_compliance=compliance_enums,
            sla_percentage=model.sla_percentage,
            is_serverless=model.is_serverless,
            attributes=model.attributes,
            pricing_unit=model.pricing_unit,
            measurement_metric=model.measurement_metric,
            documentation_url=model.documentation_url,
            pricing_source_type=model.pricing_source_type,
            pricing_reference_url=model.pricing_reference_url,
            dataset_version=model.dataset_version,
            retrieval_timestamp=model.retrieval_timestamp,
            provenance=model.provenance,
            status=model.status,  # type: ignore[arg-type]
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
