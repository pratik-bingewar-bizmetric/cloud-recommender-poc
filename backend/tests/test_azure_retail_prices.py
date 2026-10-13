"""Unit tests for Azure Retail Prices API client, normalization, and local caching."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from cloud_recommender.services.pricing.azure_retail_client import (
    AzurePriceItem,
    AzureRetailPricesClient,
    map_region_to_front_door_zone,
    select_matching_meter,
)
from cloud_recommender.services.pricing.price_cache import (
    AzurePriceCache,
    normalize_service_id,
)


@pytest.mark.asyncio
async def test_azure_retail_client_query_success_and_pagination() -> None:
    """Verify Azure Retail Prices client handles OData filtering and pagination."""
    client = AzureRetailPricesClient(base_url="https://prices.azure.com/api/retail/prices")

    page_1_data = {
        "Items": [
            {
                "currencyCode": "USD",
                "tierMinimumUnits": 0.0,
                "retailPrice": 0.0864,
                "unitPrice": 0.0864,
                "armRegionName": "eastus",
                "location": "US East",
                "meterId": "meter-aca-vcpu",
                "meterName": "vCPU Duration",
                "productId": "prod-aca",
                "skuId": "sku-aca-1",
                "productName": "Azure Container Apps",
                "skuName": "Consumption",
                "serviceName": "Azure Container Apps",
                "serviceId": "DZH318Z0B123",
                "serviceFamily": "Compute",
                "unitOfMeasure": "1 Hour",
                "type": "Consumption",
                "isPrimaryMeterRegion": True,
            }
        ],
        "NextPageLink": "https://prices.azure.com/api/retail/prices?$skip=100",
    }
    page_2_data = {
        "Items": [
            {
                "currencyCode": "USD",
                "tierMinimumUnits": 0.0,
                "retailPrice": 0.0108,
                "unitPrice": 0.0108,
                "armRegionName": "eastus",
                "location": "US East",
                "meterId": "meter-aca-memory",
                "meterName": "Memory Duration",
                "productId": "prod-aca",
                "skuId": "sku-aca-2",
                "productName": "Azure Container Apps",
                "skuName": "Consumption",
                "serviceName": "Azure Container Apps",
                "serviceId": "DZH318Z0B123",
                "serviceFamily": "Compute",
                "unitOfMeasure": "1 GB/Hour",
                "type": "Consumption",
                "isPrimaryMeterRegion": True,
            }
        ],
        "NextPageLink": None,
    }

    resp1 = httpx.Response(status_code=200, json=page_1_data)
    resp2 = httpx.Response(status_code=200, json=page_2_data)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=[resp1, resp2]):
        items = await client.query_prices(service_name="Azure Container Apps", region="eastus")

    assert len(items) == 2
    assert items[0].meter_id == "meter-aca-vcpu"
    assert items[0].unit_price == Decimal("0.0864")
    assert items[1].meter_id == "meter-aca-memory"
    assert items[1].unit_price == Decimal("0.0108")


@pytest.mark.asyncio
async def test_azure_retail_client_network_error_handled() -> None:
    """Verify network failures gracefully return empty list rather than unhandled exception."""
    client = AzureRetailPricesClient(timeout_seconds=2.0)

    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        items = await client.query_prices(service_name="Virtual Machines", region="eastus")

    assert items == []


def test_price_cache_storage_and_ttl(tmp_path: Path) -> None:
    """Verify local price cache saves items and respects TTL freshness."""
    cache_file = tmp_path / "test_prices_cache.json"
    cache = AzurePriceCache(cache_file=cache_file, ttl_hours=2)

    item = AzurePriceItem(
        currency_code="USD",
        tier_minimum_units=0.0,
        retail_price=Decimal("0.184"),
        unit_price=Decimal("0.184"),
        arm_region_name="eastus",
        location="US East",
        meter_id="postgres-d2ds",
        meter_name="Compute D2ds_v5",
        product_id="prod-pg",
        sku_id="sku-pg",
        product_name="PostgreSQL Flexible",
        sku_name="D2ds_v5",
        service_name="Azure Database for PostgreSQL",
        service_id="DZH318Z0B456",
        service_family="Databases",
        unit_of_measure="1 Hour",
    )

    cache.put_cached_item("azure-postgres-flexible:eastus", item)
    loaded = cache.get_cached_item("azure-postgres-flexible:eastus")
    assert loaded is not None
    assert loaded.unit_price == Decimal("0.184")
    assert loaded.meter_id == "postgres-d2ds"

    # Test expired item
    raw_cache = cache.load_cache()
    raw_cache["azure-postgres-flexible:eastus"]["cached_at"] = (
        datetime.now(UTC) - timedelta(hours=5)
    ).isoformat()
    cache.save_cache(raw_cache)

    expired = cache.get_cached_item("azure-postgres-flexible:eastus")
    assert expired is None


def test_benchmark_pricing_fallback_dataset() -> None:
    """Verify official benchmark pricing rates exist for all core Azure services."""
    cache = AzurePriceCache()
    core_services = [
        "azure-container-apps",
        "azure-app-service",
        "azure-postgres-flexible",
        "azure-blob-storage",
        "azure-key-vault",
        "azure-monitor",
        "azure-openai-foundry",
        "azure-bandwidth",
        "azure-front-door",
        "azure-web-application-firewall",
    ]

    for sid in core_services:
        rate_info = cache.get_benchmark_pricing(sid)
        assert rate_info is not None, f"Missing benchmark pricing for {sid}"
        assert Decimal(rate_info["unit_price"]) > Decimal("0.0")
        assert "meter_id" in rate_info
        assert "source_url" in rate_info


def test_front_door_region_to_billing_zone_mapping() -> None:
    """Verify Azure ARM regions map to official Azure Front Door billing zones."""
    assert map_region_to_front_door_zone("eastus") == "Zone 1"
    assert map_region_to_front_door_zone("westus2") == "Zone 1"
    assert map_region_to_front_door_zone("westeurope") == "Zone 1"
    assert map_region_to_front_door_zone("northeurope") == "Zone 1"
    assert map_region_to_front_door_zone("global") == "Zone 1"
    assert map_region_to_front_door_zone("southeastasia") == "Zone 2"
    assert map_region_to_front_door_zone("japaneast") == "Zone 2"
    assert map_region_to_front_door_zone("brazilsouth") == "Zone 3"
    assert map_region_to_front_door_zone("australiaeast") == "Zone 4"
    assert map_region_to_front_door_zone("centralindia") == "Zone 5"
    assert map_region_to_front_door_zone("zone 2") == "Zone 2"


def test_select_matching_meter_multiple_matches_and_no_match() -> None:
    """Verify deterministic meter selection across tiered overage, wrong meters, and base meters."""
    representative_items = [
        AzurePriceItem(
            meter_id="captcha-meter",
            meter_name="Standard Captcha Session",
            product_id="DZH318Z0BPVW",
            sku_id="DZH318Z0BPVW/000J",
            product_name="Azure Front Door",
            sku_name="Standard",
            service_name="Azure Front Door Service",
            service_id="DZH317F70804",
            service_family="Networking",
            unit_of_measure="10K",
            retail_price=Decimal("0.60"),
            unit_price=Decimal("0.60"),
            tier_minimum_units=0.0,
            arm_region_name="Zone 1",
        ),
        AzurePriceItem(
            meter_id="egress-tier-10tb",
            meter_name="Standard Data Transfer Out",
            product_id="DZH318Z0BPVW",
            sku_id="DZH318Z0BPVW/000J",
            product_name="Azure Front Door",
            sku_name="Standard",
            service_name="Azure Front Door Service",
            service_id="DZH317F70804",
            service_family="Networking",
            unit_of_measure="1 GB",
            retail_price=Decimal("0.08"),
            unit_price=Decimal("0.08"),
            tier_minimum_units=10240.0,
            arm_region_name="Zone 1",
        ),
        AzurePriceItem(
            meter_id="79b4d346-f8f7-55fe-8375-5943ea4e697c",
            meter_name="Standard Data Transfer Out",
            product_id="DZH318Z0BPVW",
            sku_id="DZH318Z0BPVW/000J",
            product_name="Azure Front Door",
            sku_name="Standard",
            service_name="Azure Front Door Service",
            service_id="DZH317F70804",
            service_family="Networking",
            unit_of_measure="1 GB",
            retail_price=Decimal("0.0825"),
            unit_price=Decimal("0.0825"),
            tier_minimum_units=0.0,
            arm_region_name="Zone 1",
        ),
        AzurePriceItem(
            meter_id="7e3eab72-0b95-5524-984a-d1697f73feee",
            meter_name="Standard Base Fees",
            product_id="DZH318Z0BPVW",
            sku_id="DZH318Z0BPVW/000J",
            product_name="Azure Front Door",
            sku_name="Standard",
            service_name="Azure Front Door Service",
            service_id="DZH317F70804",
            service_family="Networking",
            unit_of_measure="1/Month",
            retail_price=Decimal("35.0"),
            unit_price=Decimal("35.0"),
            tier_minimum_units=0.0,
            arm_region_name="Zone 1",
        ),
    ]

    base_match = select_matching_meter(
        representative_items,
        product_name="azure front door",  # case-insensitive check
        sku_name="standard",
        meter_name="standard base fees",
        unit_of_measure="1/month",
        tier_minimum_units=0.0,
    )
    assert base_match is not None
    assert base_match.meter_id == "7e3eab72-0b95-5524-984a-d1697f73feee"
    assert base_match.unit_price == Decimal("35.0")

    egress_match = select_matching_meter(
        representative_items,
        product_name="Azure Front Door",
        sku_name="Standard",
        meter_name="Standard Data Transfer Out",
        unit_of_measure="1 GB",
        tier_minimum_units=0.0,
    )
    assert egress_match is not None
    assert egress_match.meter_id == "79b4d346-f8f7-55fe-8375-5943ea4e697c"
    assert egress_match.unit_price == Decimal("0.0825")

    no_match = select_matching_meter(
        representative_items,
        product_name="Azure Front Door",
        sku_name="Premium",
        meter_name="Premium Base Fees",
    )
    assert no_match is None


def test_service_id_normalization_aliases() -> None:
    """Verify service ID aliases normalize to canonical catalog IDs."""
    assert normalize_service_id("azure-front-door") == "azure-front-door"
    assert normalize_service_id("Azure-FrontDoor") == "azure-front-door"
    assert normalize_service_id("front-door") == "azure-front-door"
    assert (
        normalize_service_id("azure-web-application-firewall") == "azure-web-application-firewall"
    )
    assert normalize_service_id("azure-waf") == "azure-web-application-firewall"
    assert normalize_service_id("web-application-firewall") == "azure-web-application-firewall"
    assert normalize_service_id("azure-postgresql-flexible") == "azure-postgres-flexible"
