"""Client for querying the official public Azure Retail Prices API."""

from decimal import Decimal
from urllib.parse import quote

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

DEFAULT_AZURE_RETAIL_API_URL = "https://prices.azure.com/api/retail/prices"

# Official Azure Front Door billing zone mapping.
# Azure Retail Prices API indexes Azure Front Door under billing zones ('Zone 1', 'Zone 2', etc.)
# rather than regional ARM names like 'eastus' or 'westeurope'.
FRONT_DOOR_REGION_TO_ZONE: dict[str, str] = {
    # Zone 1: North America, Europe, UK, Canada
    "eastus": "Zone 1",
    "eastus2": "Zone 1",
    "westus": "Zone 1",
    "westus2": "Zone 1",
    "westus3": "Zone 1",
    "centralus": "Zone 1",
    "northcentralus": "Zone 1",
    "southcentralus": "Zone 1",
    "canadacentral": "Zone 1",
    "canadaeast": "Zone 1",
    "westeurope": "Zone 1",
    "northeurope": "Zone 1",
    "uksouth": "Zone 1",
    "ukwest": "Zone 1",
    "francecentral": "Zone 1",
    "germanywestcentral": "Zone 1",
    "swedencentral": "Zone 1",
    "switzerlandnorth": "Zone 1",
    "global": "Zone 1",
    # Zone 2: Asia Pacific (including Japan & Korea)
    "southeastasia": "Zone 2",
    "eastasia": "Zone 2",
    "japaneast": "Zone 2",
    "japanwest": "Zone 2",
    "koreacentral": "Zone 2",
    "koreasouth": "Zone 2",
    # Zone 3: South America
    "brazilsouth": "Zone 3",
    "brazilsoutheast": "Zone 3",
    # Zone 4: Australia & New Zealand
    "australiaeast": "Zone 4",
    "australiasoutheast": "Zone 4",
    "australiacentral": "Zone 4",
    # Zone 5: India
    "centralindia": "Zone 5",
    "southindia": "Zone 5",
    "westindia": "Zone 5",
}


class AzurePriceItem(BaseModel):
    """Normalized record from official Azure Retail Prices API."""

    currency_code: str = Field(default="USD")
    tier_minimum_units: float = Field(default=0.0)
    retail_price: Decimal
    unit_price: Decimal
    arm_region_name: str = Field(default="eastus")
    location: str = Field(default="US East")
    meter_id: str
    meter_name: str
    product_id: str
    sku_id: str
    product_name: str
    sku_name: str
    service_name: str
    service_id: str
    service_family: str
    unit_of_measure: str
    type: str = Field(default="Consumption")
    is_primary_meter_region: bool = Field(default=True)
    arm_sku_name: str | None = None
    effective_start_date: str | None = None


def map_region_to_front_door_zone(region: str) -> str:
    """Map an Azure ARM region (e.g. 'eastus') to its Azure Front Door billing zone ('Zone 1')."""
    cleaned = (region or "eastus").strip()
    if cleaned.lower().startswith("zone "):
        parts = cleaned.split()
        return f"Zone {parts[-1]}"
    return FRONT_DOOR_REGION_TO_ZONE.get(cleaned.lower(), "Zone 1")


def select_matching_meter(
    items: list[AzurePriceItem],
    *,
    product_name: str | None = None,
    sku_name: str | None = None,
    meter_name: str | None = None,
    unit_of_measure: str | None = None,
    tier_minimum_units: float | None = 0.0,
    require_positive_price: bool = True,
) -> AzurePriceItem | None:
    """Deterministically select the matching AzurePriceItem from multi-item API responses."""
    candidates: list[AzurePriceItem] = []
    for item in items:
        if require_positive_price and item.unit_price <= Decimal("0.0"):
            continue
        if (
            product_name is not None
            and item.product_name.strip().lower() != product_name.strip().lower()
        ):
            continue
        if sku_name is not None and item.sku_name.strip().lower() != sku_name.strip().lower():
            continue
        if meter_name is not None and item.meter_name.strip().lower() != meter_name.strip().lower():
            continue
        if (
            unit_of_measure is not None
            and item.unit_of_measure.strip().lower() != unit_of_measure.strip().lower()
        ):
            continue
        if (
            tier_minimum_units is not None
            and abs(item.tier_minimum_units - tier_minimum_units) > 1e-6
        ):
            continue
        candidates.append(item)

    if not candidates:
        return None

    primary = [c for c in candidates if c.is_primary_meter_region]
    return primary[0] if primary else candidates[0]


class AzureRetailPricesClient:
    """Async HTTP client querying the official Azure Retail Prices public API."""

    def __init__(
        self,
        base_url: str = DEFAULT_AZURE_RETAIL_API_URL,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    async def query_prices(
        self,
        service_name: str | None = None,
        region: str | None = "eastus",
        price_type: str = "Consumption",
        arm_sku_name: str | None = None,
        product_name: str | None = None,
        sku_name: str | None = None,
        meter_name: str | None = None,
        max_pages: int = 3,
    ) -> list[AzurePriceItem]:
        """Query official Azure Retail Prices API with OData filters and pagination."""
        filters: list[str] = []
        if region is not None:
            filters.append(f"armRegionName eq '{region}'")
        if price_type:
            filters.append(f"priceType eq '{price_type}'")
        if service_name:
            filters.append(f"serviceName eq '{service_name}'")
        if arm_sku_name:
            filters.append(f"armSkuName eq '{arm_sku_name}'")
        if product_name:
            filters.append(f"productName eq '{product_name}'")
        if sku_name:
            filters.append(f"skuName eq '{sku_name}'")
        if meter_name:
            filters.append(f"meterName eq '{meter_name}'")

        filter_str = " and ".join(filters)
        url: str | None = f"{self.base_url}?$filter={quote(filter_str)}"

        items: list[AzurePriceItem] = []
        pages_fetched = 0

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            while url and pages_fetched < max_pages:
                try:
                    response = await client.get(url)
                    if response.status_code != 200:
                        logger.warning(
                            "azure_retail_prices_query_failed",
                            status_code=response.status_code,
                            filter=filter_str,
                        )
                        break

                    data = response.json()
                    raw_items = data.get("Items", [])
                    for raw in raw_items:
                        try:
                            item = AzurePriceItem(
                                currency_code=raw.get("currencyCode", "USD"),
                                tier_minimum_units=float(raw.get("tierMinimumUnits", 0.0)),
                                retail_price=Decimal(str(raw.get("retailPrice", 0.0))),
                                unit_price=Decimal(str(raw.get("unitPrice", 0.0))),
                                arm_region_name=raw.get("armRegionName", region or ""),
                                location=raw.get("location", ""),
                                meter_id=raw.get("meterId", ""),
                                meter_name=raw.get("meterName", ""),
                                product_id=raw.get("productId", ""),
                                sku_id=raw.get("skuId", ""),
                                product_name=raw.get("productName", ""),
                                sku_name=raw.get("skuName", ""),
                                service_name=raw.get("serviceName", ""),
                                service_id=raw.get("serviceId", ""),
                                service_family=raw.get("serviceFamily", ""),
                                unit_of_measure=raw.get("unitOfMeasure", ""),
                                type=raw.get("type", "Consumption"),
                                is_primary_meter_region=bool(raw.get("isPrimaryMeterRegion", True)),
                                arm_sku_name=raw.get("armSkuName"),
                                effective_start_date=raw.get("effectiveStartDate"),
                            )
                            items.append(item)
                        except Exception as parse_err:
                            logger.debug("skip_invalid_azure_price_item", error=str(parse_err))

                    url = data.get("NextPageLink")
                    pages_fetched += 1

                except (httpx.TimeoutException, httpx.RequestError) as net_err:
                    logger.warning("azure_retail_prices_network_error", error=str(net_err))
                    break

        return items
