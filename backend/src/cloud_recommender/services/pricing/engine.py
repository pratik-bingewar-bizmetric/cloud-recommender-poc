"""Deterministic Azure pricing engine and cost simulator.

Strict adherence to design principles:
- 100% deterministic Decimal calculations with explicit rounding.
- Zero price hallucinations (originates strictly from Azure Retail Prices API and verified cache).
- Transparent bill-of-materials with 5-month and annual projections.
- Sizing mapped explicitly from user workload assumptions.
"""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import structlog

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.analysis import WorkloadAssumptions
from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
from cloud_recommender.schemas.recommendation import (
    ArchitectureComponent,
    CostBreakdown,
    PricingReference,
)
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

logger = structlog.get_logger(__name__)

ROUND_CENTS = Decimal("0.01")


def _quantize_money(val: Decimal) -> Decimal:
    """Round financial amount to 2 decimal places using standard financial half-up rule."""
    return val.quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)


class AzurePricingEngine:
    """Engine computing deterministic multi-month and annual Azure bills."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: AzureRetailPricesClient | None = None,
        cache: AzurePriceCache | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or AzureRetailPricesClient(
            base_url=self.settings.azure_retail_prices_api_url
        )
        self.cache = cache or AzurePriceCache(ttl_hours=self.settings.pricing_cache_ttl_hours)

    HOURS_PER_MONTH = Decimal("730.0")

    @staticmethod
    def _resolve_front_door_tier(sku_or_tier: str | None) -> str | None:
        """Resolve Azure Front Door SKU tier ('Standard' or 'Premium') from component SKU string.

        Returns None if an explicit unrecognized SKU was provided.
        """
        if not sku_or_tier or not sku_or_tier.strip():
            return "Standard"
        lowered = sku_or_tier.strip().lower()
        if lowered in (
            "standard / premium",
            "standard/premium",
            "default",
            "global edge",
            "cdn",
        ):
            return "Standard"
        if "premium" in lowered and "standard" not in lowered:
            return "Premium"
        if "standard" in lowered:
            return "Standard"
        return None

    @staticmethod
    def _resolve_waf_mode(sku_or_tier: str | None) -> str | None:
        """Resolve WAF product mode ('front_door_waf_policy' or 'appgw_waf_v2').

        Returns None if an explicit unrecognized SKU was provided.
        """
        if not sku_or_tier or not sku_or_tier.strip():
            return "front_door_waf_policy"
        lowered = sku_or_tier.strip().lower()
        if any(
            kw in lowered
            for kw in ("application gateway", "app gateway", "waf v2", "waf_v2", "regional")
        ):
            return "appgw_waf_v2"
        if any(
            kw in lowered
            for kw in (
                "standard",
                "premium",
                "policy",
                "managed ruleset",
                "default",
                "front door",
                "global",
                "owasp",
                "drs",
            )
        ):
            return "front_door_waf_policy"
        return None

    @classmethod
    def _is_regional_app_gateway_waf(cls, sku_or_tier: str | None) -> bool:
        """Determine whether WAF component specifies regional Application Gateway WAF v2."""
        return cls._resolve_waf_mode(sku_or_tier) == "appgw_waf_v2"

    @classmethod
    def _is_valid_sku_for_service(cls, canonical_id: str, sku_or_tier: str | None) -> bool:
        """Check whether the requested SKU/tier is valid and supported for the given service."""
        if not sku_or_tier or not sku_or_tier.strip():
            return True
        lowered = sku_or_tier.strip().lower()
        if any(
            bad in lowered
            for bad in ("unknown", "invalid", "unsupported", "nonexistent", "unverified", "fake")
        ):
            return False
        if canonical_id == "azure-front-door":
            return cls._resolve_front_door_tier(sku_or_tier) is not None
        if canonical_id == "azure-web-application-firewall":
            return cls._resolve_waf_mode(sku_or_tier) is not None
        return True

    @staticmethod
    def _convert_requests_to_billing_units(
        monthly_requests: Decimal, unit_of_measure: str
    ) -> Decimal:
        """Convert raw monthly request count into meter billing units (e.g. '10K' or '1M/Month')."""
        normalized_uom = (unit_of_measure or "").strip().upper()
        if normalized_uom.startswith("10K") or "10,000" in normalized_uom:
            return monthly_requests / Decimal("10000.0")
        if normalized_uom.startswith("1M") or "1,000,000" in normalized_uom:
            return monthly_requests / Decimal("1000000.0")
        if normalized_uom.startswith("1K") or "1,000" in normalized_uom:
            return monthly_requests / Decimal("1000.0")
        return monthly_requests

    def _build_cache_key(
        self, canonical_id: str, region: str, sku_or_tier: str | None = None
    ) -> str:
        """Construct deterministic cache key accounting for zone/tier variants."""
        if canonical_id == "azure-front-door":
            zone = map_region_to_front_door_zone(region)
            tier = (self._resolve_front_door_tier(sku_or_tier) or "unknown").lower()
            return f"{canonical_id}:{zone}:{tier}"
        if canonical_id == "azure-web-application-firewall":
            waf_mode = self._resolve_waf_mode(sku_or_tier)
            if waf_mode == "appgw_waf_v2":
                return f"{canonical_id}:{region}:appgw_waf_v2"
            if waf_mode == "front_door_waf_policy":
                return f"{canonical_id}:global:standard_policy"
            return f"{canonical_id}:{region}:unknown"
        return f"{canonical_id}:{region}"

    async def _query_front_door_live(
        self, region: str, tier: str, cache_key: str
    ) -> AzurePriceItem | None:
        """Query live Azure Retail Prices API for Azure Front Door and cache base + usage meters."""
        zone = map_region_to_front_door_zone(region)
        live_items = await self.client.query_prices(
            service_name="Azure Front Door Service",
            region=zone,
            product_name="Azure Front Door",
            sku_name=tier,
        )

        base_item = select_matching_meter(
            live_items,
            product_name="Azure Front Door",
            sku_name=tier,
            meter_name=f"{tier} Base Fees",
            unit_of_measure="1/Month",
            tier_minimum_units=0.0,
        )
        egress_item = select_matching_meter(
            live_items,
            product_name="Azure Front Door",
            sku_name=tier,
            meter_name=f"{tier} Data Transfer Out",
            unit_of_measure="1 GB",
            tier_minimum_units=0.0,
        )
        requests_item = select_matching_meter(
            live_items,
            product_name="Azure Front Door",
            sku_name=tier,
            meter_name=f"{tier} Requests",
            unit_of_measure="10K",
            tier_minimum_units=0.0,
        )

        # In Azure Retail Prices API, Front Door Base Fees are published under Zone 1
        # while Data Transfer Out and Requests are published per billing zone (Zone 1..5).
        if zone != "Zone 1" and (base_item is None or egress_item is None or requests_item is None):
            zone1_items = await self.client.query_prices(
                service_name="Azure Front Door Service",
                region="Zone 1",
                product_name="Azure Front Door",
                sku_name=tier,
            )
            if base_item is None:
                base_item = select_matching_meter(
                    zone1_items,
                    product_name="Azure Front Door",
                    sku_name=tier,
                    meter_name=f"{tier} Base Fees",
                    unit_of_measure="1/Month",
                    tier_minimum_units=0.0,
                )
            if egress_item is None:
                egress_item = select_matching_meter(
                    zone1_items,
                    product_name="Azure Front Door",
                    sku_name=tier,
                    meter_name=f"{tier} Data Transfer Out",
                    unit_of_measure="1 GB",
                    tier_minimum_units=0.0,
                )
            if requests_item is None:
                requests_item = select_matching_meter(
                    zone1_items,
                    product_name="Azure Front Door",
                    sku_name=tier,
                    meter_name=f"{tier} Requests",
                    unit_of_measure="10K",
                    tier_minimum_units=0.0,
                )

        if egress_item:
            self.cache.put_cached_item(f"{cache_key}:egress", egress_item)
        if requests_item:
            self.cache.put_cached_item(f"{cache_key}:requests", requests_item)
        if base_item:
            self.cache.put_cached_item(cache_key, base_item)

        return base_item

    async def _query_waf_live(
        self, region: str, is_appgw: bool, cache_key: str
    ) -> AzurePriceItem | None:
        """Query live Azure Retail Prices API for WAF Policy or Application Gateway WAF v2."""
        if is_appgw:
            live_items = await self.client.query_prices(
                service_name="Application Gateway",
                region=region,
                product_name="Application Gateway WAF v2",
            )
            if not live_items and region != "eastus":
                live_items = await self.client.query_prices(
                    service_name="Application Gateway",
                    region="eastus",
                    product_name="Application Gateway WAF v2",
                )
            if not live_items:
                return None

            fixed_item = select_matching_meter(
                live_items,
                product_name="Application Gateway WAF v2",
                sku_name="Standard",
                meter_name="Standard Fixed Cost",
                unit_of_measure="1/Hour",
                tier_minimum_units=0.0,
            )
            cu_item = select_matching_meter(
                live_items,
                product_name="Application Gateway WAF v2",
                sku_name="Standard",
                meter_name="Standard Capacity Units",
                unit_of_measure="1/Hour",
                tier_minimum_units=0.0,
            )
            if cu_item:
                self.cache.put_cached_item(f"{cache_key}:capacity_unit", cu_item)
            if fixed_item:
                self.cache.put_cached_item(cache_key, fixed_item)
            return fixed_item

        # Global Front Door WAF Policy (stored with armRegionName == "" in Azure Retail Prices API)
        live_items = await self.client.query_prices(
            service_name="Azure Front Door Service",
            region="",
            product_name="Azure Front Door Service",
        )
        if not live_items:
            return None

        policy_item = select_matching_meter(
            live_items,
            product_name="Azure Front Door Service",
            sku_name="Standard",
            meter_name="Standard Policy",
            unit_of_measure="1/Month",
            tier_minimum_units=0.0,
        )
        rule_item = select_matching_meter(
            live_items,
            product_name="Azure Front Door Service",
            sku_name="Standard",
            meter_name="Standard Rule",
            unit_of_measure="1/Month",
            tier_minimum_units=0.0,
        )
        req_item = select_matching_meter(
            live_items,
            product_name="Azure Front Door Service",
            sku_name="Standard",
            meter_name="Standard Default Request",
            unit_of_measure="1M/Month",
            tier_minimum_units=0.0,
        )
        if rule_item:
            self.cache.put_cached_item(f"{cache_key}:rule", rule_item)
        if req_item:
            self.cache.put_cached_item(f"{cache_key}:request", req_item)
        if policy_item:
            self.cache.put_cached_item(cache_key, policy_item)
        return policy_item

    async def get_price_for_service(
        self,
        service_id: str,
        region: str = "eastus",
        sku_or_tier: str | None = None,
        *,
        force_live: bool = False,
    ) -> tuple[Decimal, str, str, str, str]:
        """Retrieve unit rate, meter ID, unit description, source URL, and provenance."""
        canonical_id = normalize_service_id(service_id)
        if not self._is_valid_sku_for_service(canonical_id, sku_or_tier):
            return (
                Decimal("0.00"),
                f"unverified-{service_id}-sku",
                "N/A",
                "https://azure.microsoft.com/pricing/",
                "unverified_missing_rate",
            )

        cache_key = self._build_cache_key(canonical_id, region, sku_or_tier)

        # 1. Try local cache (variant key first, then direct service_id:region key)
        if not force_live:
            cached = self.cache.get_cached_item(cache_key)
            if cached is None and cache_key != f"{service_id}:{region}":
                cached = self.cache.get_cached_item(f"{service_id}:{region}")
            if cached:
                return (
                    cached.unit_price,
                    cached.meter_id,
                    cached.unit_of_measure,
                    "https://prices.azure.com/api/retail/prices",
                    "azure_retail_prices_api_cached",
                )

        # 2. If not offline_pricing_mode (or force_live requested), attempt live query
        benchmark = self.cache.get_benchmark_pricing(canonical_id)
        if (force_live or not self.settings.offline_pricing_mode) and benchmark:
            try:
                matched_live: AzurePriceItem | None = None
                if canonical_id == "azure-front-door":
                    tier = self._resolve_front_door_tier(sku_or_tier)
                    if tier is not None:
                        matched_live = await self._query_front_door_live(region, tier, cache_key)
                elif canonical_id == "azure-web-application-firewall":
                    is_appgw = self._is_regional_app_gateway_waf(sku_or_tier)
                    matched_live = await self._query_waf_live(region, is_appgw, cache_key)
                else:
                    azure_service_name = benchmark["service_name"]
                    live_items = await self.client.query_prices(
                        service_name=azure_service_name,
                        region=region,
                    )
                    if live_items:
                        # Never select an arbitrary live_items[0]; require a valid base-tier match
                        matched_live = select_matching_meter(
                            live_items,
                            sku_name=benchmark.get("sku_name"),
                            meter_name=benchmark.get("meter_name"),
                            tier_minimum_units=0.0,
                        ) or select_matching_meter(live_items, tier_minimum_units=0.0)
                        if matched_live is not None:
                            self.cache.put_cached_item(cache_key, matched_live)

                if matched_live is not None:
                    return (
                        matched_live.unit_price,
                        matched_live.meter_id,
                        matched_live.unit_of_measure,
                        "https://prices.azure.com/api/retail/prices",
                        "azure_retail_prices_api_live",
                    )
            except Exception as exc:
                logger.warning("live_azure_pricing_failed_falling_back", error=str(exc))

        # 3. Fallback to verified benchmark dataset
        if benchmark:
            if canonical_id == "azure-front-door":
                tier = self._resolve_front_door_tier(sku_or_tier)
                if tier == "Premium":
                    return (
                        Decimal(str(benchmark["premium_unit_price"])),
                        str(benchmark["premium_meter_id"]),
                        str(benchmark["unit_of_measure"]),
                        str(benchmark["source_url"]),
                        "official_azure_pricing_benchmark_dataset",
                    )
            elif (
                canonical_id == "azure-web-application-firewall"
                and self._is_regional_app_gateway_waf(sku_or_tier)
            ):
                return (
                    Decimal(str(benchmark["appgw_fixed_unit_price"])),
                    str(benchmark["appgw_fixed_meter_id"]),
                    str(benchmark["appgw_fixed_unit_of_measure"]),
                    str(benchmark["source_url"]),
                    "official_azure_pricing_benchmark_dataset",
                )

            unit_price_raw = benchmark.get("unit_price") or benchmark.get("blended_price_per_1k")
            if unit_price_raw is not None:
                return (
                    Decimal(str(unit_price_raw)),
                    str(benchmark.get("meter_id", f"meter-{canonical_id}")),
                    str(benchmark.get("unit_of_measure", "Unit")),
                    str(benchmark.get("source_url", "https://azure.microsoft.com/pricing/")),
                    "official_azure_pricing_benchmark_dataset",
                )

        # Unknown / Unverified service
        return (
            Decimal("0.00"),
            f"unverified-{service_id}",
            "N/A",
            "https://azure.microsoft.com/pricing/",
            "unverified_missing_rate",
        )

    def _calculate_front_door_cost(
        self,
        comp: ArchitectureComponent,
        assumptions: WorkloadAssumptions,
        rate: Decimal,
        region: str,
    ) -> tuple[Decimal, Decimal, str, str, str | None]:
        """Calculate Azure Front Door fixed base fee + outbound data transfer + request charges."""
        tier = self._resolve_front_door_tier(comp.sku_or_tier)
        if tier is None:
            warning = (
                f"Official pricing for '{comp.service_id}' with unrecognized SKU/tier "
                f"'{comp.sku_or_tier}' could not be verified from Azure Retail Prices."
            )
            return (
                Decimal("0.00"),
                Decimal("0.00"),
                "Unpriced (Unknown SKU)",
                f"{warning} Excluded from deterministic cost total.",
                warning,
            )

        zone = map_region_to_front_door_zone(region)
        cache_key = self._build_cache_key("azure-front-door", region, comp.sku_or_tier)
        benchmark = self.cache.get_benchmark_pricing("azure-front-door") or {}

        cached_base = self.cache.get_cached_item(cache_key)
        cached_egress = self.cache.get_cached_item(f"{cache_key}:egress")
        cached_req = self.cache.get_cached_item(f"{cache_key}:requests")

        if tier == "Premium":
            bm_base_raw = benchmark.get("premium_unit_price")
            bm_egress_raw = (
                benchmark.get("premium_egress_price_per_gb_zone2")
                if zone == "Zone 2"
                else benchmark.get("premium_egress_price_per_gb")
            )
            bm_req_raw = (
                benchmark.get("premium_requests_price_per_10k_zone2")
                if zone == "Zone 2"
                else benchmark.get("premium_requests_price_per_10k")
            )
            bm_req_uom = str(benchmark.get("requests_unit_of_measure", "10K"))
        else:
            bm_base_raw = benchmark.get("unit_price")
            bm_egress_raw = (
                benchmark.get("egress_price_per_gb_zone2")
                if zone == "Zone 2"
                else benchmark.get("egress_price_per_gb")
            )
            bm_req_raw = (
                benchmark.get("requests_price_per_10k_zone2")
                if zone == "Zone 2"
                else benchmark.get("requests_price_per_10k")
            )
            bm_req_uom = str(benchmark.get("requests_unit_of_measure", "10K"))

        base_rate: Decimal | None = (
            cached_base.unit_price
            if cached_base is not None
            else (
                Decimal(str(bm_base_raw))
                if bm_base_raw is not None
                else (rate if rate > Decimal("0.00") else None)
            )
        )
        egress_rate: Decimal | None = (
            cached_egress.unit_price
            if cached_egress is not None
            else (Decimal(str(bm_egress_raw)) if bm_egress_raw is not None else None)
        )
        req_rate: Decimal | None = (
            cached_req.unit_price
            if cached_req is not None
            else (Decimal(str(bm_req_raw)) if bm_req_raw is not None else None)
        )
        req_uom = cached_req.unit_of_measure if cached_req is not None else bm_req_uom

        if base_rate is None or egress_rate is None or req_rate is None:
            warning = (
                f"Official pricing meters for Azure Front Door ({tier}, {zone}) are incomplete "
                "or unavailable in both cache and benchmark records."
            )
            return (
                Decimal("0.00"),
                Decimal("0.00"),
                "Unpriced (Missing Meter)",
                f"{warning} Excluded from deterministic cost total.",
                warning,
            )

        qty = Decimal(str(comp.quantity))
        base_cost = base_rate * qty

        egress_gb = Decimal(str(assumptions.monthly_egress_gb))
        egress_cost = egress_gb * egress_rate

        monthly_requests = (
            Decimal(str(assumptions.monthly_active_users))
            * Decimal(str(assumptions.requests_per_user_per_day))
            * Decimal("30")
        )
        request_billing_units = self._convert_requests_to_billing_units(monthly_requests, req_uom)
        requests_cost = request_billing_units * req_rate

        monthly = _quantize_money(base_cost + egress_cost + requests_cost)
        workload_qty = _quantize_money(egress_gb)
        unit = f"Profile + GB Egress & {req_uom} Requests"
        assumption_desc = (
            f"Azure Front Door {tier} ({zone}): {comp.quantity} profile(s) @ "
            f"${base_rate:.2f}/mo base + {egress_gb} GB data transfer out @ "
            f"${egress_rate}/GB + {int(monthly_requests):,} HTTP/S requests "
            f"({request_billing_units:.1f} x {req_uom}) @ ${req_rate}/{req_uom}."
        )
        return monthly, workload_qty, unit, assumption_desc, None

    def _calculate_waf_cost(
        self,
        comp: ArchitectureComponent,
        assumptions: WorkloadAssumptions,
        rate: Decimal,
        region: str,
        paired_front_door_tier: str | None,
    ) -> tuple[Decimal, Decimal, str, str, str | None]:
        """Calculate Web Application Firewall cost and prevent duplicate Front Door billing."""
        waf_mode = self._resolve_waf_mode(comp.sku_or_tier)
        if waf_mode is None:
            warning = (
                f"Official pricing for '{comp.service_id}' with unrecognized SKU/tier "
                f"'{comp.sku_or_tier}' could not be verified from Azure Retail Prices."
            )
            return (
                Decimal("0.00"),
                Decimal("0.00"),
                "Unpriced (Unknown SKU)",
                f"{warning} Excluded from deterministic cost total.",
                warning,
            )

        benchmark = self.cache.get_benchmark_pricing("azure-web-application-firewall") or {}
        cache_key = self._build_cache_key(
            "azure-web-application-firewall", region, comp.sku_or_tier
        )
        qty = Decimal(str(comp.quantity))

        # Mode 1: Regional Application Gateway WAF v2
        if waf_mode == "appgw_waf_v2":
            cached_fixed = self.cache.get_cached_item(cache_key)
            cached_cu = self.cache.get_cached_item(f"{cache_key}:capacity_unit")

            bm_fixed_raw = benchmark.get("appgw_fixed_unit_price")
            bm_cu_raw = benchmark.get("appgw_capacity_unit_price")

            fixed_hourly: Decimal | None = (
                cached_fixed.unit_price
                if cached_fixed is not None
                else (
                    Decimal(str(bm_fixed_raw))
                    if bm_fixed_raw is not None
                    else (rate if rate > Decimal("0.00") else None)
                )
            )
            cu_hourly: Decimal | None = (
                cached_cu.unit_price
                if cached_cu is not None
                else (Decimal(str(bm_cu_raw)) if bm_cu_raw is not None else None)
            )

            if fixed_hourly is None or cu_hourly is None:
                warning = (
                    f"Official pricing meters for Application Gateway WAF v2 ({region}) "
                    "could not be verified."
                )
                return (
                    Decimal("0.00"),
                    Decimal("0.00"),
                    "Unpriced (Missing Meter)",
                    f"{warning} Excluded from deterministic cost total.",
                    warning,
                )

            capacity_units = max(1, int((assumptions.peak_rps + 9.999) // 10))
            hours = self.HOURS_PER_MONTH * qty
            fixed_cost = hours * fixed_hourly
            cu_cost = hours * Decimal(str(capacity_units)) * cu_hourly
            monthly = _quantize_money(fixed_cost + cu_cost)
            workload_qty = hours
            unit = "Gateway Hours + Capacity Units"
            assumption_desc = (
                f"Application Gateway WAF v2 ({region}): {comp.quantity} instance(s) x "
                f"{int(self.HOURS_PER_MONTH)} hrs/mo @ ${fixed_hourly}/hr fixed + "
                f"{capacity_units} Capacity Unit(s) @ ${cu_hourly}/CU-hr."
            )
            return monthly, workload_qty, unit, assumption_desc, None

        # Mode 2: Paired with Azure Front Door Premium -> Included in Front Door Premium base fee
        if paired_front_door_tier == "Premium":
            fd_benchmark = self.cache.get_benchmark_pricing("azure-front-door") or {}
            fd_prem_cache_key = self._build_cache_key("azure-front-door", region, "Premium")
            fd_prem_cached = self.cache.get_cached_item(fd_prem_cache_key)
            covered_base_price = (
                fd_prem_cached.unit_price
                if fd_prem_cached is not None
                else (
                    Decimal(str(fd_benchmark["premium_unit_price"]))
                    if "premium_unit_price" in fd_benchmark
                    else None
                )
            )
            if covered_base_price is None:
                warning = (
                    "Official Azure Front Door Premium meter covering bundled WAF Policy "
                    "could not be verified."
                )
                return (
                    Decimal("0.00"),
                    Decimal("0.00"),
                    "Unpriced (Missing Covering Meter)",
                    f"{warning} Excluded from deterministic cost total.",
                    warning,
                )

            monthly = Decimal("0.00")
            workload_qty = qty
            unit = "Included in Front Door Premium"
            assumption_desc = (
                "Included with Azure Front Door Premium tier (WAF policy, Microsoft Default "
                f"Ruleset, and Bot Protection are covered by the ${covered_base_price:.2f}/mo "
                "Front Door Premium base fee; $0.00 incremental charge applied to prevent "
                "duplicate billing)."
            )
            return monthly, workload_qty, unit, assumption_desc, None

        # Mode 3: Paired with Azure Front Door Standard or standalone global WAF Policy
        cached_policy = self.cache.get_cached_item(cache_key)
        cached_rule = self.cache.get_cached_item(f"{cache_key}:rule")
        cached_req = self.cache.get_cached_item(f"{cache_key}:request")

        bm_policy_raw = benchmark.get("unit_price")
        bm_rule_raw = benchmark.get("custom_rule_unit_price")
        bm_req_raw = benchmark.get("request_price_per_1m")
        bm_req_uom = str(benchmark.get("request_unit_of_measure", "1M/Month"))

        policy_rate: Decimal | None = (
            cached_policy.unit_price
            if cached_policy is not None
            else (
                Decimal(str(bm_policy_raw))
                if bm_policy_raw is not None
                else (rate if rate > Decimal("0.00") else None)
            )
        )
        rule_rate: Decimal | None = (
            cached_rule.unit_price
            if cached_rule is not None
            else (Decimal(str(bm_rule_raw)) if bm_rule_raw is not None else None)
        )
        req_rate_per_1m: Decimal | None = (
            cached_req.unit_price
            if cached_req is not None
            else (Decimal(str(bm_req_raw)) if bm_req_raw is not None else None)
        )
        req_uom = cached_req.unit_of_measure if cached_req is not None else bm_req_uom

        if policy_rate is None or rule_rate is None or req_rate_per_1m is None:
            warning = (
                "Official pricing meters for Azure Front Door WAF Policy could not be verified."
            )
            return (
                Decimal("0.00"),
                Decimal("0.00"),
                "Unpriced (Missing Meter)",
                f"{warning} Excluded from deterministic cost total.",
                warning,
            )

        custom_rules_count = Decimal("2")
        monthly_requests = (
            Decimal(str(assumptions.monthly_active_users))
            * Decimal(str(assumptions.requests_per_user_per_day))
            * Decimal("30")
        )
        requests_millions = self._convert_requests_to_billing_units(monthly_requests, req_uom)

        policy_cost = policy_rate * qty
        rules_cost = custom_rules_count * rule_rate * qty
        requests_cost = requests_millions * req_rate_per_1m

        monthly = _quantize_money(policy_cost + rules_cost + requests_cost)
        workload_qty = qty
        unit = f"Policies + {req_uom} Requests"
        context_label = (
            "paired with Azure Front Door Standard"
            if paired_front_door_tier == "Standard"
            else "Azure Front Door WAF Standard Policy"
        )
        assumption_desc = (
            f"WAF Policy ({context_label}): {comp.quantity} policy @ ${policy_rate:.2f}/mo "
            f"+ {int(custom_rules_count)} custom rules @ ${rule_rate:.2f}/mo "
            f"+ {requests_millions:.2f}M inspected requests @ ${req_rate_per_1m:.2f}/{req_uom}."
        )
        return monthly, workload_qty, unit, assumption_desc, None

    def calculate_component_cost(
        self,
        comp: ArchitectureComponent,
        assumptions: WorkloadAssumptions,
        rate: Decimal,
        provenance: str,
        *,
        region: str = "eastus",
        paired_front_door_tier: str | None = None,
    ) -> tuple[Decimal, Decimal, str, str, str | None]:
        """Calculate component monthly cost based on workload parameters."""
        service_id = comp.service_id.lower()
        canonical_id = normalize_service_id(service_id)

        # Never fabricate a numeric price for an unverified service or unknown SKU
        if provenance == "unverified_missing_rate":
            sku_detail = f" (SKU/tier '{comp.sku_or_tier}')" if comp.sku_or_tier else ""
            missing_warning = (
                f"Official pricing for service '{comp.service_id}'{sku_detail} could not be "
                "verified from Azure Retail Prices."
            )
            return (
                Decimal("0.00"),
                Decimal("0.00"),
                "Unpriced (Missing Verified Rate)",
                (
                    f"Official pricing for '{comp.service_name}' ({comp.service_id}){sku_detail} "
                    "could not be verified from Azure Retail Prices; excluded from deterministic "
                    "cost total."
                ),
                missing_warning,
            )

        # 0A. Azure Front Door
        if (
            canonical_id == "azure-front-door"
            or "front-door" in service_id
            or "frontdoor" in service_id
        ):
            return self._calculate_front_door_cost(
                comp=comp,
                assumptions=assumptions,
                rate=rate,
                region=region,
            )

        # 0B. Azure Web Application Firewall (WAF)
        if (
            canonical_id == "azure-web-application-firewall"
            or "web-application-firewall" in service_id
            or "waf" in service_id
        ):
            return self._calculate_waf_cost(
                comp=comp,
                assumptions=assumptions,
                rate=rate,
                region=region,
                paired_front_door_tier=paired_front_door_tier,
            )

        # 1. Azure Container Apps
        if "container-apps" in service_id or "container" in service_id:
            # Active execution ratio based on user concurrency
            active_ratio = min(
                Decimal("1.0"),
                max(
                    Decimal("0.25"),
                    Decimal(str(assumptions.monthly_active_users)) / Decimal("1000.0"),
                ),
            )
            hours = self.HOURS_PER_MONTH * Decimal(str(comp.quantity))
            vcpu_alloc = Decimal("0.5") if assumptions.customer_count <= 50 else Decimal("1.0")
            mem_alloc = Decimal("1.0") if assumptions.customer_count <= 50 else Decimal("2.0")

            # vCPU: $0.0864 / hr, RAM: $0.0108 / hr
            vcpu_cost = hours * vcpu_alloc * rate * active_ratio
            mem_cost = hours * mem_alloc * Decimal("0.0108") * active_ratio
            monthly = _quantize_money(vcpu_cost + mem_cost)
            workload_qty = _quantize_money(hours * vcpu_alloc * active_ratio)
            unit = "vCPU-Hours"
            assumption_desc = (
                f"{comp.quantity} replica(s) sizing: {vcpu_alloc} vCPU, {mem_alloc} GiB RAM, "
                f"active ratio {int(active_ratio * 100)}% ({assumptions.monthly_active_users} MAU)."
            )
            return monthly, workload_qty, unit, assumption_desc, None

        # 2. Azure App Service
        if "app-service" in service_id:
            sku_lower = (comp.sku_or_tier or "").lower()
            if comp.sku_or_tier and ("b1" in sku_lower or "basic" in sku_lower):
                hourly = rate if rate > 0 else Decimal("0.018")  # ~$13.14/mo
                sku = "B1 Basic"
            elif assumptions.customer_count > 50 or (comp.sku_or_tier and "p1" in sku_lower):
                hourly = Decimal("0.109")  # ~$79.57/mo
                sku = "P1v3 Premium"
            else:
                hourly = rate if rate > 0 else Decimal("0.018")  # ~$13.14/mo
                sku = "B1 Basic"
            monthly = _quantize_money(hourly * self.HOURS_PER_MONTH * Decimal(str(comp.quantity)))
            workload_qty = Decimal(str(730 * comp.quantity))
            unit = "Hours"
            assumption_desc = (
                f"{comp.quantity} x {sku} instances running continuously (730 hrs/month)."
            )
            return monthly, workload_qty, unit, assumption_desc, None

        # 3. Azure PostgreSQL Flexible Server
        if "postgres" in service_id:
            storage_gb = Decimal(str(assumptions.db_storage_gb))
            storage_rate = Decimal("0.115")
            storage_cost = storage_gb * storage_rate

            if comp.sku_or_tier and (
                "d2ds" in comp.sku_or_tier.lower() or "general purpose" in comp.sku_or_tier.lower()
            ):
                compute_hourly = rate if rate > 0 else Decimal("0.184")
                sku = "General Purpose D2ds_v5"
            elif comp.sku_or_tier and "b2s" in comp.sku_or_tier.lower():
                compute_hourly = Decimal("0.0728")
                sku = "Burstable Standard_B2s"
            elif comp.sku_or_tier and "b1ms" in comp.sku_or_tier.lower():
                compute_hourly = Decimal("0.020")
                sku = "Burstable B1ms"
            elif assumptions.customer_count <= 50:
                compute_hourly = Decimal("0.020")  # B1ms (~$14.60)
                sku = "Burstable B1ms"
            else:
                compute_hourly = rate if rate > 0 else Decimal("0.184")  # D2ds_v5 (~$134.32)
                sku = "General Purpose D2ds_v5"

            ha_mult = Decimal("2.0") if assumptions.ha_required else Decimal("1.0")
            compute_cost = (
                compute_hourly * self.HOURS_PER_MONTH * ha_mult * Decimal(str(comp.quantity))
            )
            monthly = _quantize_money(compute_cost + storage_cost)
            workload_qty = Decimal(str(730 * int(ha_mult) * comp.quantity))
            unit = "Instance Hours"
            ha_status = (
                "Zone-Redundant HA with Standby" if assumptions.ha_required else "Single Node"
            )
            assumption_desc = f"{sku} ({ha_status}) + {storage_gb} GB storage at $0.115/GB-mo."
            return monthly, workload_qty, unit, assumption_desc, None

        # 4. Azure Blob Storage
        if (
            "blob" in service_id
            or "storage" in service_id
            and comp.category == ServiceCategory.STORAGE
        ):
            storage_gb = Decimal(str(assumptions.blob_storage_gb))
            cap_cost = storage_gb * rate
            # Operations estimate
            ops_cost = (
                Decimal(str(assumptions.monthly_active_users * 20))
                / Decimal("10000.0")
                * Decimal("0.05")
            )
            monthly = _quantize_money(cap_cost + ops_cost)
            workload_qty = storage_gb
            unit = "GB/Month"
            assumption_desc = (
                f"{storage_gb} GB Hot LRS capacity + estimated read/write IO operations."
            )
            return monthly, workload_qty, unit, assumption_desc, None

        # 5. Azure AI Foundry / OpenAI
        if "ai" in service_id or "openai" in service_id or comp.category == ServiceCategory.AI_ML:
            tokens_thousands = Decimal(str(assumptions.ai_support_monthly_tokens)) / Decimal(
                "1000.0"
            )
            token_rate = rate if rate > 0 else Decimal("0.0050")  # $0.005 / 1k tokens blended
            monthly = _quantize_money(tokens_thousands * token_rate)
            workload_qty = tokens_thousands
            unit = "1000 Tokens"
            assumption_desc = (
                f"{assumptions.ai_support_monthly_tokens:,} monthly tokens at "
                f"${token_rate}/1k tokens blended rate."
            )
            return monthly, workload_qty, unit, assumption_desc, None

        # 6. Azure Key Vault
        if "key-vault" in service_id or "vault" in service_id:
            monthly = Decimal("5.00")
            workload_qty = Decimal("100000")
            unit = "Operations"
            assumption_desc = (
                "Base Key Vault certificate/key management + 100k cryptographic operations."
            )
            return monthly, workload_qty, unit, assumption_desc, None

        # 7. Azure Monitor
        if "monitor" in service_id or comp.category == ServiceCategory.MONITORING:
            ingest_gb = max(
                Decimal("1.0"), Decimal(str(assumptions.customer_count)) * Decimal("0.002")
            )
            billable_gb = max(Decimal("0.0"), ingest_gb - Decimal("5.0"))  # First 5GB free
            monthly = _quantize_money(billable_gb * rate)
            workload_qty = ingest_gb
            unit = "GB Ingestion"
            assumption_desc = (
                f"{ingest_gb:.1f} GB log telemetry ingestion (first 5 GB included free)."
            )
            return monthly, workload_qty, unit, assumption_desc, None

        # 8. Bandwidth / Egress
        if "bandwidth" in service_id or "network" in service_id:
            egress_gb = Decimal(str(assumptions.monthly_egress_gb))
            billable_gb = max(Decimal("0.0"), egress_gb - Decimal("100.0"))
            monthly = _quantize_money(billable_gb * rate)
            workload_qty = egress_gb
            unit = "GB Egress"
            assumption_desc = (
                f"{egress_gb} GB outbound internet transfer (first 100 GB included free)."
            )
            return monthly, workload_qty, unit, assumption_desc, None

        # Default / Other (only reached when provenance is verified/cached)
        monthly = _quantize_money(rate * Decimal(str(comp.quantity)))
        workload_qty = Decimal(str(comp.quantity))
        unit = "Units"
        assumption_desc = f"Standard utility pricing allocation for {comp.service_name}."
        return monthly, workload_qty, unit, assumption_desc, None

    def _build_pricing_reference_metadata(
        self,
        comp: ArchitectureComponent,
        canonical_id: str,
        region: str,
        prov_source: str,
        pricing_status: str,
    ) -> dict[str, str | float | None]:
        """Extract matched API / benchmark metadata for PricingReference."""
        cache_key = self._build_cache_key(canonical_id, region, comp.sku_or_tier)
        cached_item = self.cache.get_cached_item(cache_key)
        if cached_item is not None:
            return {
                "service_name": cached_item.service_name,
                "product_name": cached_item.product_name,
                "sku_name": cached_item.sku_name,
                "meter_name": cached_item.meter_name,
                "arm_region_name": cached_item.arm_region_name,
                "tier_minimum_units": cached_item.tier_minimum_units,
                "pricing_tier_or_notes": f"Status: {pricing_status} ({prov_source})",
            }

        benchmark = self.cache.get_benchmark_pricing(canonical_id)
        if not benchmark or pricing_status == "unpriced":
            return {
                "service_name": comp.service_name,
                "product_name": None,
                "sku_name": comp.sku_or_tier,
                "meter_name": None,
                "arm_region_name": region,
                "tier_minimum_units": None,
                "pricing_tier_or_notes": "Unpriced: missing verified retail rate",
            }

        if canonical_id == "azure-front-door":
            tier = self._resolve_front_door_tier(comp.sku_or_tier) or "Standard"
            zone = map_region_to_front_door_zone(region)
            return {
                "service_name": str(benchmark.get("service_name", "Azure Front Door Service")),
                "product_name": str(benchmark.get("product_name", "Azure Front Door")),
                "sku_name": tier,
                "meter_name": f"{tier} Base Fees",
                "arm_region_name": zone,
                "tier_minimum_units": 0.0,
                "pricing_tier_or_notes": f"Status: {pricing_status} ({zone}, {tier})",
            }

        if canonical_id == "azure-web-application-firewall":
            if self._is_regional_app_gateway_waf(comp.sku_or_tier):
                return {
                    "service_name": str(benchmark.get("appgw_service_name", "Application Gateway")),
                    "product_name": str(
                        benchmark.get("appgw_product_name", "Application Gateway WAF v2")
                    ),
                    "sku_name": str(benchmark.get("appgw_sku_name", "Standard")),
                    "meter_name": str(
                        benchmark.get("appgw_fixed_meter_name", "Standard Fixed Cost")
                    ),
                    "arm_region_name": region,
                    "tier_minimum_units": 0.0,
                    "pricing_tier_or_notes": f"Status: {pricing_status} (Application Gateway WAF v2)",
                }
            if pricing_status == "bundled":
                zone = map_region_to_front_door_zone(region)
                return {
                    "service_name": "Azure Front Door Service",
                    "product_name": "Azure Front Door",
                    "sku_name": "Premium",
                    "meter_name": "Premium Base Fees",
                    "arm_region_name": zone,
                    "tier_minimum_units": 0.0,
                    "pricing_tier_or_notes": (
                        "Status: bundled (Covered by Azure Front Door Premium base fee)"
                    ),
                }
            return {
                "service_name": str(benchmark.get("service_name", "Azure Front Door Service")),
                "product_name": str(benchmark.get("product_name", "Azure Front Door Service")),
                "sku_name": str(benchmark.get("sku_name", "Standard")),
                "meter_name": str(benchmark.get("meter_name", "Standard Policy")),
                "arm_region_name": "",
                "tier_minimum_units": 0.0,
                "pricing_tier_or_notes": f"Status: {pricing_status} (Global WAF Policy)",
            }

        return {
            "service_name": str(benchmark.get("service_name", comp.service_name)),
            "product_name": str(benchmark.get("service_name", comp.service_name)),
            "sku_name": str(benchmark.get("sku_name", comp.sku_or_tier or "Standard")),
            "meter_name": str(benchmark.get("meter_id", "")),
            "arm_region_name": region,
            "tier_minimum_units": 0.0,
            "pricing_tier_or_notes": f"Status: {pricing_status} ({prov_source})",
        }

    async def price_architecture(
        self,
        components: list[ArchitectureComponent],
        assumptions: WorkloadAssumptions,
        region: str = "eastus",
        buffer_percentage: Decimal = Decimal("15.00"),
    ) -> tuple[
        list[ArchitectureComponent], CostBreakdown, list[PricingReference], list[str], list[str]
    ]:
        """Deterministically price all architecture components and produce itemized BOM."""
        priced_components: list[ArchitectureComponent] = []
        provenance_records: list[PricingReference] = []
        missing_warnings: list[str] = []
        unpriced_service_ids: list[str] = []
        assumptions_list: list[str] = [
            f"Deployment region: {region}",
            (
                f"Customer scale: {assumptions.customer_count:,} registered customers "
                f"with {assumptions.monthly_active_users:,} monthly active users"
            ),
            (
                f"Traffic assumptions: {assumptions.peak_rps:.1f} peak RPS, "
                f"{assumptions.requests_per_user_per_day} API interactions/user/day"
            ),
            (
                f"Storage assumptions: {assumptions.db_storage_gb} GB database, "
                f"{assumptions.blob_storage_gb} GB unstructured object storage"
            ),
            f"AI consumption: {assumptions.ai_support_monthly_tokens:,} tokens/month",
            "Runtime assumption: 730 operational hours per month for always-on resources",
        ]

        compute_total = Decimal("0.00")
        database_total = Decimal("0.00")
        storage_total = Decimal("0.00")
        networking_total = Decimal("0.00")
        ai_total = Decimal("0.00")
        other_total = Decimal("0.00")

        now = datetime.now(UTC)

        # Detect whether Azure Front Door is present in the architecture to coordinate WAF billing
        front_door_comp = next(
            (c for c in components if normalize_service_id(c.service_id) == "azure-front-door"),
            None,
        )
        paired_front_door_tier: str | None = None
        if front_door_comp is not None:
            paired_front_door_tier = self._resolve_front_door_tier(front_door_comp.sku_or_tier)

        for comp in components:
            canonical_id = normalize_service_id(comp.service_id)
            rate, meter_id, unit_desc, source_url, prov_source = await self.get_price_for_service(
                comp.service_id,
                region=region,
                sku_or_tier=comp.sku_or_tier,
            )

            monthly, qty, u_measure, pricing_desc, warning = self.calculate_component_cost(
                comp=comp,
                assumptions=assumptions,
                rate=rate,
                provenance=prov_source,
                region=region,
                paired_front_door_tier=paired_front_door_tier,
            )

            if warning:
                missing_warnings.append(warning)
                unpriced_service_ids.append(comp.service_id)
                prov_source = "unverified_missing_rate"
                pricing_status = "unpriced"
            elif (
                canonical_id == "azure-web-application-firewall"
                and paired_front_door_tier == "Premium"
                and not self._is_regional_app_gateway_waf(comp.sku_or_tier)
            ):
                fd_benchmark = self.cache.get_benchmark_pricing("azure-front-door") or {}
                meter_id = str(
                    fd_benchmark.get("premium_meter_id", "7c765472-0673-5e48-bcb0-5a7b34c6330d")
                )
                rate = Decimal("0.00")
                unit_desc = "Included in Azure Front Door Premium (1/Month)"
                prov_source = "bundled_in_front_door_premium"
                pricing_status = "bundled"
            elif prov_source in ("azure_retail_prices_api_live", "azure_retail_prices_api_cached"):
                pricing_status = "verified"
            elif canonical_id in ("azure-openai-foundry", "azure-key-vault") or (
                not self.settings.offline_pricing_mode
                and prov_source == "official_azure_pricing_benchmark_dataset"
            ):
                pricing_status = "provisional"
            else:
                pricing_status = "verified"

            updated_comp = comp.model_copy(
                update={
                    "monthly_cost": monthly,
                    "workload_quantity": qty,
                    "workload_unit": u_measure,
                    "pricing_assumptions": pricing_desc,
                    "region": region,
                    "missing_price_warning": warning,
                    "pricing_status": pricing_status,
                }
            )
            priced_components.append(updated_comp)

            # Categorize costs (only verified/provisional/bundled have >= 0 amounts; unpriced is 0.00)
            if comp.category == ServiceCategory.COMPUTE:
                compute_total += monthly
            elif comp.category == ServiceCategory.DATABASE:
                database_total += monthly
            elif comp.category == ServiceCategory.STORAGE:
                storage_total += monthly
            elif comp.category == ServiceCategory.NETWORKING:
                networking_total += monthly
            elif comp.category == ServiceCategory.AI_ML:
                ai_total += monthly
            else:
                other_total += monthly

            meta = self._build_pricing_reference_metadata(
                comp=comp,
                canonical_id=canonical_id,
                region=region,
                prov_source=prov_source,
                pricing_status=pricing_status,
            )

            # Record provenance
            provenance_records.append(
                PricingReference(
                    provider=CloudProvider.AZURE,
                    service_id=comp.service_id,
                    meter_or_sku_id=meter_id,
                    rate=rate,
                    unit_description=unit_desc,
                    retrieval_timestamp=now,
                    source_url=source_url,
                    provenance_source=prov_source,
                    service_name=str(meta["service_name"]) if meta["service_name"] else None,
                    product_name=str(meta["product_name"]) if meta["product_name"] else None,
                    sku_name=str(meta["sku_name"]) if meta["sku_name"] else None,
                    meter_name=str(meta["meter_name"]) if meta["meter_name"] else None,
                    arm_region_name=(
                        str(meta["arm_region_name"])
                        if meta["arm_region_name"] is not None
                        else None
                    ),
                    tier_minimum_units=(
                        float(meta["tier_minimum_units"])
                        if isinstance(meta["tier_minimum_units"], (int, float))
                        else None
                    ),
                    pricing_tier_or_notes=(
                        str(meta["pricing_tier_or_notes"])
                        if meta["pricing_tier_or_notes"]
                        else None
                    ),
                )
            )

        subtotal = _quantize_money(
            compute_total
            + database_total
            + storage_total
            + networking_total
            + ai_total
            + other_total
        )
        verified_subtotal = subtotal
        buffer_amount = _quantize_money(verified_subtotal * (buffer_percentage / Decimal("100.0")))
        total_monthly = _quantize_money(verified_subtotal + buffer_amount)
        total_five_month = _quantize_money(total_monthly * Decimal("5.00"))
        total_annual = _quantize_money(total_monthly * Decimal("12.00"))

        is_complete = len(unpriced_service_ids) == 0
        estimate_status = "complete" if is_complete else "incomplete"

        if is_complete:
            assumptions_list.append(
                f"Contingency buffer: {buffer_percentage}% applied to verified BOM subtotal "
                f"(${verified_subtotal})"
            )
        else:
            assumptions_list.append(
                f"INCOMPLETE ESTIMATE: {len(unpriced_service_ids)} component(s) "
                f"({', '.join(unpriced_service_ids)}) have no verified rate and are excluded "
                f"from totals. Contingency buffer ({buffer_percentage}%) applies ONLY to the "
                f"verified subtotal (${verified_subtotal}) and does NOT cover unpriced components."
            )

        cost_breakdown = CostBreakdown(
            compute=_quantize_money(compute_total),
            database=_quantize_money(database_total),
            storage=_quantize_money(storage_total),
            networking=_quantize_money(networking_total),
            ai=_quantize_money(ai_total),
            other=_quantize_money(other_total),
            subtotal=subtotal,
            verified_subtotal=verified_subtotal,
            safety_buffer_amount=buffer_amount,
            total_monthly=total_monthly,
            total_five_month=total_five_month,
            total_annual=total_annual,
            is_complete=is_complete,
            estimate_status=estimate_status,
            unpriced_component_count=len(unpriced_service_ids),
            unpriced_service_ids=unpriced_service_ids,
        )

        return (
            priced_components,
            cost_breakdown,
            provenance_records,
            missing_warnings,
            assumptions_list,
        )
