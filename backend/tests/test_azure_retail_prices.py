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


@pytest.mark.asyncio
async def test_live_azure_retail_prices_api_verification_front_door_and_waf(
    tmp_path: Path,
) -> None:
    """Verify live Azure Retail Prices API meter matching and retained fields for Front Door & WAF."""
    from cloud_recommender.core.config import Settings
    from cloud_recommender.schemas.analysis import WorkloadAssumptions
    from cloud_recommender.schemas.common import ServiceCategory
    from cloud_recommender.schemas.recommendation import ArchitectureComponent
    from cloud_recommender.services.pricing.engine import AzurePricingEngine

    settings = Settings(offline_pricing_mode=False)
    cache = AzurePriceCache(cache_file=tmp_path / "live_retail_verification.json", ttl_hours=24)
    client = AzureRetailPricesClient(timeout_seconds=20.0)
    engine = AzurePricingEngine(settings=settings, client=client, cache=cache)

    assumptions = WorkloadAssumptions(
        customer_count=10000,
        monthly_active_users=2500,
        requests_per_user_per_day=20,  # 1,500,000 requests/mo
        monthly_egress_gb=150.0,
        peak_rps=15.0,
    )

    # 1. Front Door Standard (eastus -> Zone 1) + Front Door WAF Policy (global -> "")
    comps_std = [
        ArchitectureComponent(
            component_id="fd-std",
            category=ServiceCategory.NETWORKING,
            service_id="azure-front-door",
            service_name="Azure Front Door",
            sku_or_tier="Standard",
            quantity=1,
            rationale="Global edge ingress",
            monthly_cost=Decimal("0.00"),
        ),
        ArchitectureComponent(
            component_id="waf-std",
            category=ServiceCategory.SECURITY,
            service_id="azure-web-application-firewall",
            service_name="Azure Web Application Firewall",
            sku_or_tier="Standard Policy",
            quantity=1,
            rationale="Edge WAF policy",
            monthly_cost=Decimal("0.00"),
        ),
    ]
    priced_std, bom_std, prov_std, warns_std, _ = await engine.price_architecture(
        comps_std, assumptions, region="eastus"
    )
    assert len(warns_std) == 0
    assert bom_std.is_complete is True
    assert bom_std.estimate_status == "complete"
    assert priced_std[0].pricing_status == "verified"
    assert priced_std[0].monthly_cost == Decimal("48.73")
    assert priced_std[1].pricing_status == "verified"
    assert priced_std[1].monthly_cost == Decimal("8.50")

    fd_std_prov = prov_std[0]
    assert fd_std_prov.provenance_source == "azure_retail_prices_api_live"
    assert fd_std_prov.service_name == "Azure Front Door Service"
    assert fd_std_prov.product_name == "Azure Front Door"
    assert fd_std_prov.sku_name == "Standard"
    assert fd_std_prov.meter_name == "Standard Base Fees"
    assert fd_std_prov.arm_region_name == "Zone 1"
    assert fd_std_prov.unit_description == "1/Month"
    assert fd_std_prov.rate == Decimal("35.0")
    assert fd_std_prov.tier_minimum_units == 0.0
    assert fd_std_prov.meter_or_sku_id == "7e3eab72-0b95-5524-984a-d1697f73feee"

    waf_std_prov = prov_std[1]
    assert waf_std_prov.provenance_source == "azure_retail_prices_api_live"
    assert waf_std_prov.service_name == "Azure Front Door Service"
    assert waf_std_prov.product_name == "Azure Front Door Service"
    assert waf_std_prov.sku_name == "Standard"
    assert waf_std_prov.meter_name == "Standard Policy"
    assert waf_std_prov.arm_region_name == ""
    assert waf_std_prov.unit_description == "1/Month"
    assert waf_std_prov.rate == Decimal("5.0")
    assert waf_std_prov.tier_minimum_units == 0.0
    assert waf_std_prov.meter_or_sku_id == "87a2540c-01e9-4df7-bcd6-b3054e7696f9"

    # 2. Front Door Standard in Zone 2 (southeastasia -> Zone 2 egress & request rates)
    priced_z2, _, prov_z2, warns_z2, _ = await engine.price_architecture(
        [comps_std[0]], assumptions, region="southeastasia"
    )
    assert len(warns_z2) == 0
    # $35.00 base + (150 GB * $0.115) + (150 * 10K * $0.0108) = 35.00 + 17.25 + 1.62 = $53.87
    assert priced_z2[0].monthly_cost == Decimal("53.87")
    cached_z2_egress = cache.get_cached_item("azure-front-door:Zone 2:standard:egress")
    cached_z2_req = cache.get_cached_item("azure-front-door:Zone 2:standard:requests")
    assert cached_z2_egress is not None
    assert cached_z2_egress.arm_region_name == "Zone 2"
    assert cached_z2_egress.unit_price == Decimal("0.115")
    assert cached_z2_req is not None
    assert cached_z2_req.arm_region_name == "Zone 2"
    assert cached_z2_req.unit_price == Decimal("0.0108")
    assert cached_z2_req.unit_of_measure == "10K"

    # 3. Front Door Premium + Bundled WAF Policy
    comps_prem = [
        comps_std[0].model_copy(update={"sku_or_tier": "Premium"}),
        comps_std[1].model_copy(update={"sku_or_tier": "Premium Policy"}),
    ]
    priced_prem, bom_prem, prov_prem, warns_prem, _ = await engine.price_architecture(
        comps_prem, assumptions, region="eastus"
    )
    assert len(warns_prem) == 0
    assert bom_prem.is_complete is True
    assert priced_prem[0].pricing_status == "verified"
    assert priced_prem[0].monthly_cost == Decimal("344.63")
    assert priced_prem[1].pricing_status == "bundled"
    assert priced_prem[1].monthly_cost == Decimal("0.00")
    assert prov_prem[0].meter_or_sku_id == "7c765472-0673-5e48-bcb0-5a7b34c6330d"
    assert prov_prem[0].sku_name == "Premium"
    assert prov_prem[0].meter_name == "Premium Base Fees"
    assert prov_prem[1].provenance_source == "bundled_in_front_door_premium"
    assert prov_prem[1].meter_or_sku_id == "7c765472-0673-5e48-bcb0-5a7b34c6330d"

    # 4. Application Gateway WAF v2 (eastus)
    comps_appgw = [
        ArchitectureComponent(
            component_id="appgw-waf",
            category=ServiceCategory.SECURITY,
            service_id="azure-web-application-firewall",
            service_name="Application Gateway WAF v2",
            sku_or_tier="Application Gateway WAF v2",
            quantity=1,
            rationale="Regional WAF v2",
            monthly_cost=Decimal("0.00"),
        )
    ]
    priced_appgw, bom_appgw, prov_appgw, warns_appgw, _ = await engine.price_architecture(
        comps_appgw, assumptions, region="eastus"
    )
    assert len(warns_appgw) == 0
    assert bom_appgw.is_complete is True
    assert priced_appgw[0].pricing_status == "verified"
    assert priced_appgw[0].monthly_cost == Decimal("283.82")
    assert prov_appgw[0].provenance_source == "azure_retail_prices_api_live"
    assert prov_appgw[0].service_name == "Application Gateway"
    assert prov_appgw[0].product_name == "Application Gateway WAF v2"
    assert prov_appgw[0].sku_name == "Standard"
    assert prov_appgw[0].meter_name == "Standard Fixed Cost"
    assert prov_appgw[0].arm_region_name == "eastus"
    assert prov_appgw[0].unit_description == "1/Hour"
    assert prov_appgw[0].rate == Decimal("0.36")
    assert prov_appgw[0].meter_or_sku_id == "928d2f33-0737-413d-bcd6-d340f6c67250"
