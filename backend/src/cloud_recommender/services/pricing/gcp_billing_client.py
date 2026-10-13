"""Official Google Cloud Billing Catalog API v1 client.

Connects to the public Google Cloud Billing Catalog API
(https://cloudbilling.googleapis.com/v1/services/{serviceId}/skus)
using GCP_CLOUD_API_KEY strictly for SKU and pricing retrieval.

Security & Design Rules:
- Never logs, prints, or exposes GCP_CLOUD_API_KEY.
- Converts Google Money (units + nanos) using exact Decimal arithmetic:
  Decimal(str(units)) + (Decimal(str(nanos)) / Decimal("1000000000")).
- Supports nextPageToken pagination and deterministic regional SKU matching.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

NANO_DIVISOR = Decimal("1000000000")


class GcpSkuItem(BaseModel):
    """Normalized pricing record from the Google Cloud Billing Catalog API."""

    sku_id: str = Field(..., description="Official GCP SKU identifier (e.g. '011E-3072-CBDB').")
    service_id: str = Field(..., description="Official GCP Service ID (e.g. '152E-C115-5142').")
    service_display_name: str = Field(
        ..., description="GCP service display name (e.g. 'Cloud Run')."
    )
    description: str = Field(..., description="Human-readable SKU description.")
    resource_family: str = Field(default="Compute", description="Category resourceFamily.")
    resource_group: str = Field(default="CPU", description="Category resourceGroup.")
    usage_type: str = Field(default="OnDemand", description="Category usageType.")
    service_regions: list[str] = Field(default_factory=list, description="Supported GCP regions.")
    usage_unit: str = Field(..., description="Short unit code (e.g. 's', 'h', 'GiBy.mo', 'count').")
    usage_unit_description: str = Field(default="", description="Full unit description.")
    base_unit_conversion_factor: float = Field(default=1.0)
    unit_price: Decimal = Field(..., description="Unit price in USD converted from units + nanos.")
    currency_code: str = Field(default="USD")
    start_usage_amount: float = Field(default=0.0)
    effective_time: str | None = Field(default=None)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def convert_gcp_money_to_decimal(units: str | int | None, nanos: int | None) -> Decimal:
    """Convert Google Money {units, nanos} to exact Decimal."""
    u = Decimal(str(units if units is not None else "0"))
    n = Decimal(str(nanos if nanos is not None else 0)) / NANO_DIVISOR
    return u + n


def select_matching_gcp_sku(
    skus: list[GcpSkuItem],
    *,
    region: str = "us-central1",
    description_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    usage_unit: str | None = None,
    usage_type: str = "OnDemand",
) -> GcpSkuItem | None:
    """Deterministically select a matching GCP SKU from a candidate list.

    Never selects an arbitrary skus[0] without matching criteria.
    """
    if not skus:
        return None

    req_keywords = [k.lower() for k in (description_keywords or [])]
    excl_keywords = [k.lower() for k in (exclude_keywords or [])]
    region_lower = region.lower()

    candidates: list[GcpSkuItem] = []
    for item in skus:
        if usage_type and item.usage_type.lower() != usage_type.lower():
            continue
        if item.unit_price <= Decimal("0"):
            continue

        # Check region match (exact region, 'global', or multi-region 'us')
        regions_lower = [r.lower() for r in item.service_regions]
        if (
            region_lower not in regions_lower
            and "global" not in regions_lower
            and not (region_lower.startswith("us-") and "us" in regions_lower)
        ):
            continue

        desc_lower = item.description.lower()
        if req_keywords and not all(k in desc_lower for k in req_keywords):
            continue
        if excl_keywords and any(k in desc_lower for k in excl_keywords):
            continue
        if usage_unit and item.usage_unit.lower() != usage_unit.lower():
            continue

        candidates.append(item)

    if not candidates:
        return None

    # Sort deterministically: prefer exact region match over 'global', then by sku_id
    candidates.sort(
        key=lambda x: (
            0 if region_lower in [r.lower() for r in x.service_regions] else 1,
            x.sku_id,
        )
    )
    return candidates[0]


class GcpBillingCatalogClient:
    """Async client for the public Google Cloud Billing Catalog API v1."""

    # Official GCP Service IDs verified against https://cloudbilling.googleapis.com/v1/services
    OFFICIAL_SERVICE_IDS: dict[str, tuple[str, str]] = {
        "gcp-cloud-run": ("152E-C115-5142", "Cloud Run"),
        "gcp-cloud-functions": ("152E-C115-5142", "Cloud Run"),
        "gcp-cloud-sql-postgres": ("9662-B51E-5089", "Cloud SQL"),
        "gcp-cloud-storage": ("95FF-2EF5-5EA1", "Cloud Storage"),
        "gcp-secret-manager": ("EE82-7A5E-871C", "Secret Manager"),
        "gcp-cloud-cdn": ("E505-1604-58F8", "Networking"),
        "gcp-cloud-armor": ("E505-1604-58F8", "Networking"),
        "gcp-vertex-ai": ("C7E2-9256-1C43", "Vertex AI"),
        "gcp-cloud-monitoring": ("58CD-E7C3-72CA", "Cloud Monitoring"),
        "gcp-compute-engine": ("6F81-5844-456A", "Compute Engine"),
    }

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://cloudbilling.googleapis.com/v1",
        timeout_seconds: float = 15.0,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        """Return True if GCP_CLOUD_API_KEY is present."""
        return bool(self._api_key)

    async def list_services(self, max_pages: int = 3) -> list[dict[str, Any]]:
        """List public GCP billing services using pagination."""
        if not self._api_key:
            return []

        url = f"{self.base_url}/services"
        results: list[dict[str, Any]] = []
        page_token: str | None = None
        pages = 0

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            while pages < max_pages:
                params: dict[str, Any] = {"key": self._api_key, "pageSize": 200}
                if page_token:
                    params["pageToken"] = page_token
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning(
                        "gcp_billing_services_error",
                        status_code=resp.status_code,
                    )
                    break
                data = resp.json()
                services = data.get("services", [])
                results.extend(services)
                page_token = data.get("nextPageToken")
                pages += 1
                if not page_token:
                    break

        return results

    async def query_service_skus(
        self,
        gcp_service_id: str,
        service_display_name: str = "GCP Service",
        currency_code: str = "USD",
        max_pages: int = 2,
    ) -> list[GcpSkuItem]:
        """Fetch and normalize SKUs for a specific GCP service ID."""
        if not self._api_key:
            return []

        url = f"{self.base_url}/services/{gcp_service_id}/skus"
        normalized: list[GcpSkuItem] = []
        page_token: str | None = None
        pages = 0

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            while pages < max_pages:
                params: dict[str, Any] = {
                    "key": self._api_key,
                    "currencyCode": currency_code,
                    "pageSize": 200,
                }
                if page_token:
                    params["pageToken"] = page_token

                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning(
                        "gcp_billing_skus_query_failed",
                        service_id=gcp_service_id,
                        status_code=resp.status_code,
                    )
                    break

                data = resp.json()
                raw_skus = data.get("skus", [])
                for raw in raw_skus:
                    parsed = self._parse_raw_sku(raw, gcp_service_id, service_display_name)
                    if parsed is not None:
                        normalized.append(parsed)

                page_token = data.get("nextPageToken")
                pages += 1
                if not page_token:
                    break

        return normalized

    @staticmethod
    def _parse_raw_sku(
        raw: dict[str, Any], gcp_service_id: str, service_display_name: str
    ) -> GcpSkuItem | None:
        """Parse a single raw SKU object from Cloud Billing Catalog API."""
        sku_id = raw.get("skuId")
        description = raw.get("description", "")
        if not sku_id:
            return None

        cat = raw.get("category", {})
        pricing_info_list = raw.get("pricingInfo", [])
        if not pricing_info_list:
            return None

        pi = pricing_info_list[0]
        pe = pi.get("pricingExpression", {})
        tiered_rates = pe.get("tieredRates", [])
        if not tiered_rates:
            return None

        # Select the first non-zero rate tier, or tier 0 if all are 0
        chosen_tier = tiered_rates[0]
        for tr in tiered_rates:
            up = tr.get("unitPrice", {})
            dec = convert_gcp_money_to_decimal(up.get("units", "0"), up.get("nanos", 0))
            if dec > Decimal("0"):
                chosen_tier = tr
                break

        unit_price_obj = chosen_tier.get("unitPrice", {})
        price_dec = convert_gcp_money_to_decimal(
            unit_price_obj.get("units", "0"),
            unit_price_obj.get("nanos", 0),
        )

        return GcpSkuItem(
            sku_id=sku_id,
            service_id=gcp_service_id,
            service_display_name=service_display_name,
            description=description,
            resource_family=cat.get("resourceFamily", ""),
            resource_group=cat.get("resourceGroup", ""),
            usage_type=cat.get("usageType", "OnDemand"),
            service_regions=raw.get("serviceRegions", []),
            usage_unit=pe.get("usageUnit", "unit"),
            usage_unit_description=pe.get("usageUnitDescription", ""),
            base_unit_conversion_factor=float(pe.get("baseUnitConversionFactor", 1.0) or 1.0),
            unit_price=price_dec,
            currency_code=unit_price_obj.get("currencyCode", "USD"),
            start_usage_amount=float(chosen_tier.get("startUsageAmount", 0.0) or 0.0),
            effective_time=pi.get("effectiveTime"),
        )
