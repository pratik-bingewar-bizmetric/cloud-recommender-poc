"""Client for querying the official public Azure Retail Prices API."""

from decimal import Decimal
from urllib.parse import quote

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

DEFAULT_AZURE_RETAIL_API_URL = "https://prices.azure.com/api/retail/prices"


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
        region: str = "eastus",
        price_type: str = "Consumption",
        arm_sku_name: str | None = None,
        max_pages: int = 3,
    ) -> list[AzurePriceItem]:
        """Query official Azure Retail Prices API with OData filters and pagination."""
        filters: list[str] = [f"armRegionName eq '{region}'", f"priceType eq '{price_type}'"]
        if service_name:
            filters.append(f"serviceName eq '{service_name}'")
        if arm_sku_name:
            filters.append(f"armSkuName eq '{arm_sku_name}'")

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
                                arm_region_name=raw.get("armRegionName", region),
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
