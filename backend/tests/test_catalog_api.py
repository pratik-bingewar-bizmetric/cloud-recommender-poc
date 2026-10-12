"""Integration tests for read-only catalog API endpoints."""

import httpx
import pytest


@pytest.mark.asyncio
async def test_list_catalog_services_default(client: httpx.AsyncClient) -> None:
    """Verify GET /api/v1/catalog/services returns 200 and paginated list."""
    response = await client.get("/api/v1/catalog/services")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 18
    assert len(data["items"]) == 18
    assert data["limit"] == 50
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_list_catalog_services_filtered_by_provider(client: httpx.AsyncClient) -> None:
    """Verify filtering by provider returns only that provider's items."""
    response = await client.get("/api/v1/catalog/services?provider=azure")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 6
    assert all(item["provider"] == "azure" for item in data["items"])


@pytest.mark.asyncio
async def test_list_catalog_services_filtered_by_category(client: httpx.AsyncClient) -> None:
    """Verify filtering by category returns matching category items."""
    response = await client.get("/api/v1/catalog/services?category=compute")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 6
    assert all(item["category"] == "compute" for item in data["items"])


@pytest.mark.asyncio
async def test_list_catalog_services_pagination(client: httpx.AsyncClient) -> None:
    """Verify limit and offset query parameters."""
    response = await client.get("/api/v1/catalog/services?limit=4&offset=2")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 4
    assert data["total"] == 18
    assert data["limit"] == 4
    assert data["offset"] == 2


@pytest.mark.asyncio
async def test_get_catalog_service_by_id_success(client: httpx.AsyncClient) -> None:
    """Verify GET /api/v1/catalog/services/{id} returns service details."""
    response = await client.get("/api/v1/catalog/services/azure-container-apps")
    assert response.status_code == 200

    data = response.json()
    assert data["service_id"] == "azure-container-apps"
    assert data["name"] == "Azure Container Apps"
    assert data["provider"] == "azure"
    assert data["category"] == "compute"
    assert data["is_serverless"] is True


@pytest.mark.asyncio
async def test_get_catalog_service_not_found(client: httpx.AsyncClient) -> None:
    """Verify GET /api/v1/catalog/services/{id} with unknown ID returns 404."""
    response = await client.get("/api/v1/catalog/services/non-existent-service-id")
    assert response.status_code == 404

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == 404
    assert "not found" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_list_catalog_services_invalid_query_parameter(client: httpx.AsyncClient) -> None:
    """Verify invalid query parameter returns 422 validation error."""
    # Invalid provider enum
    response = await client.get("/api/v1/catalog/services?provider=nonexistentcloud")
    assert response.status_code == 422

    # Invalid limit (less than 1)
    response_limit = await client.get("/api/v1/catalog/services?limit=0")
    assert response_limit.status_code == 422
