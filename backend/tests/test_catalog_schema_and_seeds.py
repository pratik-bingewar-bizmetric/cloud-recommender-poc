"""Tests for CatalogService schemas, curated fixtures, and in-memory filtering."""

import pytest

from cloud_recommender.catalog.seeds import load_curated_catalog
from cloud_recommender.schemas.catalog import CatalogServiceFilter
from cloud_recommender.schemas.common import (
    CatalogRecordStatus,
    CloudProvider,
    ComplianceStandard,
    ServiceCategory,
)
from cloud_recommender.services.catalog_service import CatalogServiceManager


def test_load_curated_catalog_fixtures() -> None:
    """Verify curated fixtures file loads and validates against CatalogServiceBase schema."""
    services = load_curated_catalog()
    assert len(services) == 18

    # Verify all 3 providers are represented equally (6 services each)
    providers = [s.provider for s in services]
    assert providers.count(CloudProvider.AZURE) == 6
    assert providers.count(CloudProvider.AWS) == 6
    assert providers.count(CloudProvider.GCP) == 6

    # Verify all services have valid documentation URLs and fixture status
    for s in services:
        assert s.status == CatalogRecordStatus.FIXTURE
        assert s.documentation_url is not None
        assert s.documentation_url.startswith("https://")
        assert s.pricing_source_type == "curated_fixture"
        assert s.provenance is not None
        assert len(s.supported_regions) > 0


@pytest.mark.asyncio
async def test_catalog_manager_filtering_by_provider() -> None:
    """Verify filtering by provider returns only services for that hyperscaler."""
    manager = CatalogServiceManager(session=None)

    azure_res = await manager.list_catalog_services(
        CatalogServiceFilter(provider=CloudProvider.AZURE)
    )
    assert azure_res.total == 6
    assert all(s.provider == CloudProvider.AZURE for s in azure_res.items)

    aws_res = await manager.list_catalog_services(CatalogServiceFilter(provider=CloudProvider.AWS))
    assert aws_res.total == 6
    assert all(s.provider == CloudProvider.AWS for s in aws_res.items)

    gcp_res = await manager.list_catalog_services(CatalogServiceFilter(provider=CloudProvider.GCP))
    assert gcp_res.total == 6
    assert all(s.provider == CloudProvider.GCP for s in gcp_res.items)


@pytest.mark.asyncio
async def test_catalog_manager_filtering_by_category() -> None:
    """Verify filtering by category (e.g. database, compute)."""
    manager = CatalogServiceManager(session=None)

    db_res = await manager.list_catalog_services(
        CatalogServiceFilter(category=ServiceCategory.DATABASE)
    )
    assert db_res.total == 6
    assert all(s.category == ServiceCategory.DATABASE for s in db_res.items)

    compute_res = await manager.list_catalog_services(
        CatalogServiceFilter(category=ServiceCategory.COMPUTE)
    )
    assert compute_res.total == 6
    assert all(s.category == ServiceCategory.COMPUTE for s in compute_res.items)


@pytest.mark.asyncio
async def test_catalog_manager_filtering_serverless() -> None:
    """Verify filtering by is_serverless flag."""
    manager = CatalogServiceManager(session=None)

    serverless_res = await manager.list_catalog_services(CatalogServiceFilter(is_serverless=True))
    assert serverless_res.total > 0
    assert all(s.is_serverless is True for s in serverless_res.items)


@pytest.mark.asyncio
async def test_catalog_manager_filtering_compliance() -> None:
    """Verify filtering by compliance framework (e.g. HIPAA)."""
    manager = CatalogServiceManager(session=None)

    hipaa_res = await manager.list_catalog_services(
        CatalogServiceFilter(compliance=ComplianceStandard.HIPAA)
    )
    assert hipaa_res.total > 0
    assert all(ComplianceStandard.HIPAA in s.supported_compliance for s in hipaa_res.items)


@pytest.mark.asyncio
async def test_catalog_manager_search() -> None:
    """Verify fuzzy search across name and description."""
    manager = CatalogServiceManager(session=None)

    search_res = await manager.list_catalog_services(CatalogServiceFilter(search="PostgreSQL"))
    assert search_res.total >= 3  # Azure Flexible, AWS Aurora, GCP Cloud SQL
    assert any(s.service_id == "azure-postgresql-flexible" for s in search_res.items)


@pytest.mark.asyncio
async def test_catalog_manager_pagination() -> None:
    """Verify limit and offset pagination."""
    manager = CatalogServiceManager(session=None)

    page1 = await manager.list_catalog_services(CatalogServiceFilter(limit=5, offset=0))
    assert len(page1.items) == 5
    assert page1.total == 18

    page2 = await manager.list_catalog_services(CatalogServiceFilter(limit=5, offset=5))
    assert len(page2.items) == 5

    # Distinct items between pages
    page1_ids = {s.service_id for s in page1.items}
    page2_ids = {s.service_id for s in page2.items}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_catalog_manager_get_by_id() -> None:
    """Verify lookup by service_id."""
    manager = CatalogServiceManager(session=None)

    aca = await manager.get_catalog_service("azure-container-apps")
    assert aca is not None
    assert aca.name == "Azure Container Apps"
    assert aca.provider == CloudProvider.AZURE

    not_found = await manager.get_catalog_service("non-existent-service")
    assert not_found is None
