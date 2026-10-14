"""Local caching and benchmark dataset for Azure Retail Prices."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from cloud_recommender.services.pricing.azure_retail_client import AzurePriceItem

logger = structlog.get_logger(__name__)

CACHE_DIR = Path(__file__).parent.parent.parent / "catalog" / "cache"
CACHE_FILE = CACHE_DIR / "azure_retail_prices_cache.json"

SERVICE_ID_ALIASES: dict[str, str] = {
    "azure-front-door": "azure-front-door",
    "azure-frontdoor": "azure-front-door",
    "front-door": "azure-front-door",
    "azure-front-door-cdn": "azure-front-door",
    "azure-front-door-service": "azure-front-door",
    "azure-web-application-firewall": "azure-web-application-firewall",
    "azure-waf": "azure-web-application-firewall",
    "web-application-firewall": "azure-web-application-firewall",
    "azure-waf-policy": "azure-web-application-firewall",
    "azure-application-gateway-waf": "azure-web-application-firewall",
    "azure-postgresql-flexible": "azure-postgres-flexible",
}


def normalize_service_id(service_id: str) -> str:
    """Normalize service identifier aliases to canonical catalog service IDs."""
    cleaned = (service_id or "").strip().lower()
    return SERVICE_ID_ALIASES.get(cleaned, cleaned)


# Official published Azure benchmark rates for East US / Zone 1 (USD)
BENCHMARK_AZURE_PRICES: dict[str, dict[str, Any]] = {
    "azure-container-apps": {
        "service_name": "Azure Container Apps",
        "meter_id": "aca-vcpu-active-eastus",
        "sku_name": "Consumption",
        "unit_of_measure": "vCPU Hour",
        "unit_price": "0.08640000",
        "memory_unit_price": "0.01080000",
        "request_unit_price": "0.00000040",
        "source_url": "https://azure.microsoft.com/en-us/pricing/details/container-apps/",
    },
    "azure-app-service": {
        "service_name": "Azure App Service",
        "meter_id": "app-service-b1-linux-eastus",
        "sku_name": "B1 Basic Linux",
        "unit_of_measure": "1 Hour",
        "unit_price": "0.01800000",  # ~$13.14 / month
        "p1v3_unit_price": "0.10900000",  # ~$79.57 / month
        "source_url": "https://azure.microsoft.com/en-us/pricing/details/app-service/linux/",
    },
    "azure-postgres-flexible": {
        "service_name": "Azure Database for PostgreSQL",
        "meter_id": "postgres-flex-d2ds-v5-eastus",
        "sku_name": "General Purpose D2ds_v5",
        "unit_of_measure": "1 Hour",
        "unit_price": "0.18400000",  # ~$134.32 / month
        "burstable_b1ms_price": "0.02000000",  # ~$14.60 / month
        "storage_per_gb_month": "0.11500000",
        "source_url": "https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/",
    },
    "azure-blob-storage": {
        "service_name": "Azure Blob Storage",
        "meter_id": "blob-hot-lrs-capacity-eastus",
        "sku_name": "Hot LRS",
        "unit_of_measure": "1 GB/Month",
        "unit_price": "0.01800000",
        "write_per_10k": "0.05000000",
        "read_per_10k": "0.00400000",
        "source_url": "https://azure.microsoft.com/en-us/pricing/details/storage/blobs/",
    },
    "azure-key-vault": {
        "service_name": "Azure Key Vault",
        "meter_id": "key-vault-standard-ops-eastus",
        "sku_name": "Standard",
        "unit_of_measure": "10000 Operations",
        "unit_price": "0.03000000",
        "monthly_base_estimate": "5.00",
        "source_url": "https://azure.microsoft.com/en-us/pricing/details/key-vault/",
    },
    "azure-monitor": {
        "service_name": "Azure Monitor",
        "meter_id": "log-analytics-data-ingestion-eastus",
        "sku_name": "Pay-As-You-Go",
        "unit_of_measure": "1 GB",
        "unit_price": "2.30000000",
        "free_tier_gb": "5.0",
        "source_url": "https://azure.microsoft.com/en-us/pricing/details/monitor/",
    },
    "azure-openai-foundry": {
        "service_name": "Azure AI Foundry / OpenAI",
        "meter_id": "openai-gpt-4o-eastus",
        "sku_name": "GPT-4o Standard",
        "unit_of_measure": "1000 Tokens",
        "unit_price": "0.00500000",
        "input_price_per_1k": "0.00250000",  # $2.50 / 1M tokens
        "output_price_per_1k": "0.01000000",  # $10.00 / 1M tokens
        "blended_price_per_1k": "0.00500000",  # 70% input, 30% output blend
        "source_url": "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    },
    "azure-bandwidth": {
        "service_name": "Bandwidth",
        "meter_id": "bandwidth-egress-zone1-eastus",
        "sku_name": "Internet Egress Zone 1",
        "unit_of_measure": "1 GB",
        "unit_price": "0.08700000",
        "free_tier_gb": "100.0",
        "source_url": "https://azure.microsoft.com/en-us/pricing/details/bandwidth/",
    },
    "azure-front-door": {
        "service_name": "Azure Front Door Service",
        "product_name": "Azure Front Door",
        "sku_name": "Standard",
        "meter_name": "Standard Base Fees",
        "meter_id": "7e3eab72-0b95-5524-984a-d1697f73feee",
        "unit_of_measure": "1/Month",
        "unit_price": "35.00000000",
        "egress_meter_id": "79b4d346-f8f7-55fe-8375-5943ea4e697c",
        "egress_meter_name": "Standard Data Transfer Out",
        "egress_unit_of_measure": "1 GB",
        "egress_price_per_gb": "0.08250000",
        "egress_price_per_gb_zone2": "0.11500000",
        "requests_meter_id": "10455c17-0774-5e4c-be93-0f3c32b1beda",
        "requests_meter_name": "Standard Requests",
        "requests_unit_of_measure": "10K",
        "requests_price_per_10k": "0.00900000",
        "requests_price_per_10k_zone2": "0.01080000",
        "premium_sku_name": "Premium",
        "premium_meter_name": "Premium Base Fees",
        "premium_meter_id": "7c765472-0673-5e48-bcb0-5a7b34c6330d",
        "premium_unit_price": "330.00000000",
        "premium_egress_meter_id": "fa528978-3833-589c-9a79-be1cc1b13907",
        "premium_egress_meter_name": "Premium Data Transfer Out",
        "premium_egress_price_per_gb": "0.08250000",
        "premium_egress_price_per_gb_zone2": "0.11500000",
        "premium_requests_meter_id": "c79b85fd-1cb9-58f1-96b5-65dff38474bf",
        "premium_requests_meter_name": "Premium Requests",
        "premium_requests_price_per_10k": "0.01500000",
        "premium_requests_price_per_10k_zone2": "0.01800000",
        "source_url": "https://azure.microsoft.com/en-us/pricing/details/frontdoor/",
    },
    "azure-web-application-firewall": {
        "service_name": "Azure Front Door Service",
        "product_name": "Azure Front Door Service",
        "sku_name": "Standard",
        "meter_name": "Standard Policy",
        "meter_id": "87a2540c-01e9-4df7-bcd6-b3054e7696f9",
        "unit_of_measure": "1/Month",
        "unit_price": "5.00000000",
        "custom_rule_meter_id": "e0ad2fc6-efc1-46d0-b1c2-a6d77259cedc",
        "custom_rule_meter_name": "Standard Rule",
        "custom_rule_unit_price": "1.00000000",
        "default_ruleset_meter_id": "e8de7b2c-c207-4b65-a23d-42bf91bc3fa8",
        "default_ruleset_meter_name": "Standard Default Ruleset",
        "default_ruleset_unit_price": "20.00000000",
        "request_meter_id": "1f84aa29-76be-4035-9473-e9d7a7c4f16b",
        "request_meter_name": "Standard Default Request",
        "request_unit_of_measure": "1M/Month",
        "request_price_per_1m": "1.00000000",
        "appgw_service_name": "Application Gateway",
        "appgw_product_name": "Application Gateway WAF v2",
        "appgw_sku_name": "Standard",
        "appgw_fixed_meter_id": "928d2f33-0737-413d-bcd6-d340f6c67250",
        "appgw_fixed_meter_name": "Standard Fixed Cost",
        "appgw_fixed_unit_of_measure": "1/Hour",
        "appgw_fixed_unit_price": "0.36000000",
        "appgw_capacity_meter_id": "c53957cb-e558-4d3f-bd96-c2d0d83b0b19",
        "appgw_capacity_meter_name": "Standard Capacity Units",
        "appgw_capacity_unit_of_measure": "1/Hour",
        "appgw_capacity_unit_price": "0.01440000",
        "source_url": "https://azure.microsoft.com/en-us/pricing/details/web-application-firewall/",
    },
}


class AzurePriceCache:
    """Manages file-based cache and benchmark pricing fallbacks."""

    def __init__(self, cache_file: Path = CACHE_FILE, ttl_hours: int = 24) -> None:
        self.cache_file = cache_file
        self.ttl = timedelta(hours=ttl_hours)
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

    def load_cache(self) -> dict[str, Any]:
        """Read cache from disk."""
        if not self.cache_file.exists():
            return {}
        try:
            with open(self.cache_file, encoding="utf-8") as f:
                loaded = json.load(f)
                return dict(loaded) if isinstance(loaded, dict) else {}
        except Exception as exc:
            logger.warning("failed_to_read_price_cache", error=str(exc))
            return {}

    def save_cache(self, data: dict[str, Any]) -> None:
        """Write cache to disk."""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            logger.warning("failed_to_save_price_cache", error=str(exc))

    def get_cached_item(self, cache_key: str) -> AzurePriceItem | None:
        """Retrieve a price item from cache if within TTL."""
        data = self.load_cache()
        entry = data.get(cache_key)
        if not entry:
            return None

        cached_at_str = entry.get("cached_at")
        if not cached_at_str:
            return None

        try:
            cached_at = datetime.fromisoformat(cached_at_str)
            if datetime.now(UTC) - cached_at > self.ttl:
                return None  # Expired
            return AzurePriceItem.model_validate(entry.get("item"))
        except Exception:
            return None

    def put_cached_item(self, cache_key: str, item: AzurePriceItem) -> None:
        """Store a price item in cache with current timestamp."""
        data = self.load_cache()
        data[cache_key] = {
            "cached_at": datetime.now(UTC).isoformat(),
            "item": item.model_dump(mode="json"),
        }
        self.save_cache(data)

    def get_benchmark_pricing(self, service_id: str) -> dict[str, Any] | None:
        """Return benchmark rate specification for a supported Azure service."""
        canonical_id = normalize_service_id(service_id)
        return BENCHMARK_AZURE_PRICES.get(canonical_id)
