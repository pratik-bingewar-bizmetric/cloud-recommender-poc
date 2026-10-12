"""Unit tests for ORM models, constraints, and repository methods."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from cloud_recommender.catalog.seeds import load_curated_catalog
from cloud_recommender.db.models import (
    Base,
    CloudServiceCatalogModel,
    WorkloadProfileModel,
)
from cloud_recommender.db.repositories.catalog_repo import CatalogRepository
from cloud_recommender.db.repositories.workload_repo import WorkloadRepository
from cloud_recommender.schemas.catalog import CatalogServiceFilter
from cloud_recommender.schemas.common import CloudProvider, WorkloadCategory
from cloud_recommender.schemas.workload import WorkloadProfileCreate


def test_orm_models_metadata_and_constraints() -> None:
    """Verify ORM models are registered in Base metadata with constraints."""
    tables = Base.metadata.tables
    assert "workload_profiles" in tables
    assert "cloud_service_catalog" in tables

    catalog_table = tables["cloud_service_catalog"]
    # Check unique constraint
    constraint_names = [c.name for c in catalog_table.constraints]
    assert "uq_provider_service_id" in constraint_names

    workload_table = tables["workload_profiles"]
    assert "id" in workload_table.c
    assert "name" in workload_table.c
    assert "category" in workload_table.c


@pytest.mark.asyncio
async def test_workload_repository_create_and_queries() -> None:
    """Verify WorkloadRepository constructs model and invokes session methods."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    created_id = uuid4()

    async def mock_refresh(instance: WorkloadProfileModel) -> None:
        instance.id = created_id

    mock_session.refresh = AsyncMock(side_effect=mock_refresh)

    repo = WorkloadRepository(session=mock_session)
    dto = WorkloadProfileCreate(
        name="Test Service",
        category=WorkloadCategory.WEB_APP,
        max_monthly_budget=Decimal("1500.00"),
    )

    result = await repo.create(dto)
    assert mock_session.add.called
    assert mock_session.commit.called
    assert result.name == "Test Service"
    assert result.category == "web_app"


@pytest.mark.asyncio
async def test_catalog_repository_upsert_idempotency() -> None:
    """Verify CatalogRepository upsert updates existing record rather than duplicating."""
    mock_session = AsyncMock()

    existing_model = CloudServiceCatalogModel(
        id=uuid4(),
        provider="azure",
        service_id="azure-container-apps",
        name="Old Name",
        category="compute",
        description="Old description",
        supported_regions=["eastus"],
        supported_compliance=["hipaa"],
        sla_percentage=99.9,
        is_serverless=True,
        attributes={},
        pricing_source_type="curated_fixture",
        dataset_version="1.0.0",
        provenance="Test",
        status="fixture",
    )

    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = existing_model
    mock_session.execute.return_value = mock_exec_result

    repo = CatalogRepository(session=mock_session)
    curated = load_curated_catalog()
    aca_data = next(s for s in curated if s.service_id == "azure-container-apps")

    updated_model = await repo.upsert(aca_data)
    assert updated_model is existing_model
    assert updated_model.name == "Azure Container Apps"
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_catalog_repository_list_query_filters() -> None:
    """Verify list_services executes filtered query with pagination."""
    mock_session = AsyncMock()

    mock_exec_count = MagicMock()
    mock_exec_count.scalar_one.return_value = 5

    mock_exec_items = MagicMock()
    mock_exec_items.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_exec_count, mock_exec_items]

    repo = CatalogRepository(session=mock_session)
    filters = CatalogServiceFilter(provider=CloudProvider.AZURE, limit=10, offset=0)

    items, total = await repo.list_services(filters)
    assert total == 5
    assert items == []
    assert mock_session.execute.call_count == 2
