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

# Official published Azure benchmark rates for East US (USD)
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
        return BENCHMARK_AZURE_PRICES.get(service_id)
