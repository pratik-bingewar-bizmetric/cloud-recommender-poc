"""Unit tests for the deterministic Azure pricing engine and cost simulator."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.analysis import WorkloadAssumptions
from cloud_recommender.schemas.common import ServiceCategory
from cloud_recommender.schemas.recommendation import ArchitectureComponent
from cloud_recommender.services.pricing.azure_retail_client import (
    AzurePriceItem,
    AzureRetailPricesClient,
)
from cloud_recommender.services.pricing.engine import AzurePricingEngine
from cloud_recommender.services.pricing.price_cache import AzurePriceCache


@pytest.fixture
def sample_components() -> list[ArchitectureComponent]:
    return [
        ArchitectureComponent(
            component_id="comp-compute",
            category=ServiceCategory.COMPUTE,
            service_id="azure-container-apps",
            service_name="Azure Container Apps",
            quantity=2,
            rationale="Microservices container hosting",
            monthly_cost=Decimal("0.00"),
        ),
        ArchitectureComponent(
            component_id="comp-db",
            category=ServiceCategory.DATABASE,
            service_id="azure-postgres-flexible",
            service_name="Azure Database for PostgreSQL",
            quantity=1,
            rationale="Transactional relational persistence",
            monthly_cost=Decimal("0.00"),
        ),
        ArchitectureComponent(
            component_id="comp-storage",
            category=ServiceCategory.STORAGE,
            service_id="azure-blob-storage",
            service_name="Azure Blob Storage",
            quantity=1,
            rationale="Unstructured documents and media",
            monthly_cost=Decimal("0.00"),
        ),
        ArchitectureComponent(
            component_id="comp-ai",
            category=ServiceCategory.AI_ML,
            service_id="azure-openai-foundry",
            service_name="Azure AI Foundry / OpenAI",
            quantity=1,
            rationale="Customer support intelligence",
            monthly_cost=Decimal("0.00"),
        ),
    ]


@pytest.mark.asyncio
async def test_pricing_engine_customer_presets_scaling(
    sample_components: list[ArchitectureComponent],
) -> None:
    """Verify costs scale deterministically between 21, 51, and 10,000 customer scale presets."""
    engine = AzurePricingEngine()

    # Preset 21
    assumptions_21 = WorkloadAssumptions(
        customer_count=21,
        monthly_active_users=10,
        peak_rps=1.0,
        db_storage_gb=5.0,
        blob_storage_gb=10.0,
        ai_support_monthly_tokens=200000,
        ha_required=False,
    )
    comps_21, bom_21, prov_21, warns_21, _ = await engine.price_architecture(
        sample_components, assumptions_21
    )

    # Preset 51
    assumptions_51 = WorkloadAssumptions(
        customer_count=51,
        monthly_active_users=30,
        peak_rps=3.0,
        db_storage_gb=15.0,
        blob_storage_gb=30.0,
        ai_support_monthly_tokens=500000,
        ha_required=False,
    )
    comps_51, bom_51, prov_51, warns_51, _ = await engine.price_architecture(
        sample_components, assumptions_51
    )

    # Preset 10,000
    assumptions_10k = WorkloadAssumptions(
        customer_count=10000,
        monthly_active_users=2500,
        peak_rps=50.0,
        db_storage_gb=100.0,
        blob_storage_gb=250.0,
        ai_support_monthly_tokens=5000000,
        ha_required=True,
    )
    comps_10k, bom_10k, prov_10k, warns_10k, _ = await engine.price_architecture(
        sample_components, assumptions_10k
    )

    # Verify scaling progression
    assert bom_21.total_monthly < bom_51.total_monthly < bom_10k.total_monthly
    assert bom_21.database < bom_10k.database  # D2ds_v5 + HA vs B1ms single node
    assert bom_21.ai < bom_10k.ai  # 200k vs 5M tokens
    assert len(warns_21) == 0


@pytest.mark.asyncio
async def test_pricing_engine_decimal_precision_and_projections(
    sample_components: list[ArchitectureComponent],
) -> None:
    """Verify strict Decimal math, safety buffers, 5-month projections, and annual totals."""
    engine = AzurePricingEngine()
    assumptions = WorkloadAssumptions(customer_count=10000)

    priced_comps, bom, prov, warns, assumps = await engine.price_architecture(
        sample_components, assumptions, buffer_percentage=Decimal("15.00")
    )

    # Validate Decimal types
    assert isinstance(bom.total_monthly, Decimal)
    assert isinstance(bom.total_five_month, Decimal)
    assert isinstance(bom.total_annual, Decimal)
    assert isinstance(bom.safety_buffer_amount, Decimal)

    # Validate relationships
    assert bom.total_monthly == bom.subtotal + bom.safety_buffer_amount
    assert bom.total_five_month == bom.total_monthly * Decimal("5.00")
    assert bom.total_annual == bom.total_monthly * Decimal("12.00")

    # Validate category breakdown equals subtotal
    category_sum = bom.compute + bom.database + bom.storage + bom.networking + bom.ai + bom.other
    assert bom.subtotal == category_sum


@pytest.mark.asyncio
async def test_pricing_engine_missing_price_warning() -> None:
    """Verify explicit warning and $0.00 cost when a service rate is unknown."""
    engine = AzurePricingEngine()
    custom_comp = [
        ArchitectureComponent(
            component_id="comp-custom",
            category=ServiceCategory.INTEGRATION,
            service_id="custom-unverified-app",
            service_name="Custom Unverified App",
            quantity=1,
            rationale="Custom appliance",
            monthly_cost=Decimal("0.00"),
        )
    ]
    assumptions = WorkloadAssumptions()

    priced, bom, prov, warnings, _ = await engine.price_architecture(custom_comp, assumptions)

    assert len(warnings) == 1
    assert "could not be verified" in warnings[0]
    assert priced[0].missing_price_warning is not None
    # Unverified component must never fabricate a $10.00 charge
    assert priced[0].monthly_cost == Decimal("0.00")
    assert bom.total_monthly == Decimal("0.00")


@pytest.mark.asyncio
async def test_pricing_engine_adding_removing_components(
    sample_components: list[ArchitectureComponent],
) -> None:
    """Verify adding/removing components recalculates totals immediately."""
    engine = AzurePricingEngine()
    assumptions = WorkloadAssumptions(customer_count=51)

    # Baseline with 4 components
    _, bom_base, _, _, _ = await engine.price_architecture(sample_components, assumptions)

    # Remove AI component
    without_ai = [c for c in sample_components if c.service_id != "azure-openai-foundry"]
    _, bom_no_ai, _, _, _ = await engine.price_architecture(without_ai, assumptions)

    assert bom_no_ai.ai == Decimal("0.00")
    assert bom_no_ai.total_monthly < bom_base.total_monthly

    # Add extra security component
    with_vault = sample_components + [
        ArchitectureComponent(
            component_id="comp-vault",
            category=ServiceCategory.SECURITY,
            service_id="azure-key-vault",
            service_name="Azure Key Vault",
            quantity=1,
            rationale="Hardware security and key management",
            monthly_cost=Decimal("0.00"),
        )
    ]
    _, bom_with_vault, _, _, _ = await engine.price_architecture(with_vault, assumptions)

    assert bom_with_vault.total_monthly > bom_base.total_monthly


@pytest.mark.asyncio
async def test_pricing_engine_high_availability_impact(
    sample_components: list[ArchitectureComponent],
) -> None:
    """Verify HA flag doubles database compute allocation for standby replica."""
    engine = AzurePricingEngine()
    assumptions_no_ha = WorkloadAssumptions(customer_count=10000, ha_required=False)
    assumptions_ha = WorkloadAssumptions(customer_count=10000, ha_required=True)

    _, bom_no_ha, _, _, _ = await engine.price_architecture(sample_components, assumptions_no_ha)
    _, bom_ha, _, _, _ = await engine.price_architecture(sample_components, assumptions_ha)

    assert bom_ha.database > bom_no_ha.database


@pytest.mark.asyncio
async def test_pricing_engine_front_door_standard_and_premium_dimensions() -> None:
    """Verify Azure Front Door accounts for base fee, data transfer out, and request dimensions."""
    engine = AzurePricingEngine()
    assumptions = WorkloadAssumptions(
        customer_count=10000,
        monthly_active_users=2500,
        requests_per_user_per_day=20,  # 2500 * 20 * 30 = 1,500,000 requests (150 x 10K)
        monthly_egress_gb=150.0,
    )

    fd_standard = [
        ArchitectureComponent(
            component_id="comp-fd-std",
            category=ServiceCategory.NETWORKING,
            service_id="azure-front-door",
            service_name="Azure Front Door",
            sku_or_tier="Standard",
            quantity=1,
            rationale="Global edge ingress",
            monthly_cost=Decimal("0.00"),
        )
    ]
    priced_std, bom_std, prov_std, warns_std, _ = await engine.price_architecture(
        fd_standard, assumptions, region="eastus"
    )
    # Standard Zone 1: $35.00 base + (150 GB * $0.0825) + (150 * 10K * $0.009)
    # = 35.00 + 12.375 + 1.35 = 48.725 -> $48.73
    assert len(warns_std) == 0
    assert priced_std[0].missing_price_warning is None
    assert priced_std[0].monthly_cost == Decimal("48.73")
    assert prov_std[0].meter_or_sku_id == "7e3eab72-0b95-5524-984a-d1697f73feee"

    # Premium Zone 1: $330.00 base + (150 GB * $0.0825) + (150 * 10K * $0.015)
    # = 330.00 + 12.375 + 2.25 = 344.625 -> $344.63
    fd_premium = [fd_standard[0].model_copy(update={"sku_or_tier": "Premium"})]
    priced_prem, bom_prem, prov_prem, warns_prem, _ = await engine.price_architecture(
        fd_premium, assumptions, region="eastus"
    )
    assert len(warns_prem) == 0
    assert priced_prem[0].missing_price_warning is None
    assert priced_prem[0].monthly_cost == Decimal("344.63")
    assert prov_prem[0].meter_or_sku_id == "7c765472-0673-5e48-bcb0-5a7b34c6330d"

    # Zone 2 (southeastasia): $35.00 base + (150 GB * $0.14) + (150 * 10K * $0.0095)
    # = 35.00 + 21.00 + 1.425 = 57.425 -> $57.43
    priced_z2, _, _, warns_z2, _ = await engine.price_architecture(
        fd_standard, assumptions, region="southeastasia"
    )
    assert len(warns_z2) == 0
    assert priced_z2[0].monthly_cost == Decimal("57.43")


@pytest.mark.asyncio
async def test_pricing_engine_waf_with_front_door_standard_vs_premium_duplicate_prevention() -> (
    None
):
    """Verify WAF pricing with Front Door Standard vs Premium prevents duplicate charges."""
    engine = AzurePricingEngine()
    assumptions = WorkloadAssumptions(
        customer_count=10000,
        monthly_active_users=2500,
        requests_per_user_per_day=20,  # 1.5M requests/month
        monthly_egress_gb=150.0,
    )

    # Case 1: Front Door Standard + WAF Policy -> Separate verified WAF Policy charge
    comps_std = [
        ArchitectureComponent(
            component_id="comp-fd",
            category=ServiceCategory.NETWORKING,
            service_id="azure-front-door",
            service_name="Azure Front Door",
            sku_or_tier="Standard",
            quantity=1,
            rationale="Global edge load balancer",
            monthly_cost=Decimal("0.00"),
        ),
        ArchitectureComponent(
            component_id="comp-waf",
            category=ServiceCategory.SECURITY,
            service_id="azure-web-application-firewall",
            service_name="Azure Web Application Firewall",
            sku_or_tier="Standard Policy",
            quantity=1,
            rationale="Edge WAF policy",
            monthly_cost=Decimal("0.00"),
        ),
    ]
    priced_std, _, prov_std, warns_std, _ = await engine.price_architecture(
        comps_std, assumptions, region="eastus"
    )
    assert len(warns_std) == 0
    waf_std = next(c for c in priced_std if c.service_id == "azure-web-application-firewall")
    # $5.00 policy + 2 * $1.00 custom rules + 1.5M * $1.00/1M requests = $8.50
    assert waf_std.monthly_cost == Decimal("8.50")
    assert waf_std.missing_price_warning is None
    waf_prov_std = next(p for p in prov_std if p.service_id == "azure-web-application-firewall")
    assert waf_prov_std.meter_or_sku_id == "87a2540c-01e9-4df7-bcd6-b3054e7696f9"

    # Case 2: Front Door Premium + WAF Policy -> WAF included in $330/mo Front Door Premium
    comps_prem = [
        comps_std[0].model_copy(update={"sku_or_tier": "Premium"}),
        comps_std[1].model_copy(update={"sku_or_tier": "Premium Policy"}),
    ]
    priced_prem, _, prov_prem, warns_prem, _ = await engine.price_architecture(
        comps_prem, assumptions, region="eastus"
    )
    assert len(warns_prem) == 0
    fd_prem = next(c for c in priced_prem if c.service_id == "azure-front-door")
    waf_prem = next(c for c in priced_prem if c.service_id == "azure-web-application-firewall")
    assert fd_prem.monthly_cost == Decimal("344.63")
    assert waf_prem.monthly_cost == Decimal("0.00")
    assert waf_prem.missing_price_warning is None
    assert "prevent duplicate billing" in (waf_prem.pricing_assumptions or "")
    waf_prov_prem = next(p for p in prov_prem if p.service_id == "azure-web-application-firewall")
    assert waf_prov_prem.rate == Decimal("0.00")
    assert waf_prov_prem.meter_or_sku_id == "7c765472-0673-5e48-bcb0-5a7b34c6330d"


@pytest.mark.asyncio
async def test_pricing_engine_waf_regional_application_gateway_v2() -> None:
    """Verify Application Gateway WAF v2 uses hourly fixed + capacity unit meters."""
    engine = AzurePricingEngine()
    assumptions = WorkloadAssumptions(
        customer_count=10000,
        peak_rps=15.0,  # 2 Capacity Units
    )
    comps = [
        ArchitectureComponent(
            component_id="comp-appgw-waf",
            category=ServiceCategory.SECURITY,
            service_id="azure-web-application-firewall",
            service_name="Application Gateway WAF v2",
            sku_or_tier="Application Gateway WAF v2",
            quantity=1,
            rationale="Regional Layer-7 WAF ingress",
            monthly_cost=Decimal("0.00"),
        )
    ]

    priced, _, prov, warns, _ = await engine.price_architecture(comps, assumptions, region="eastus")
    assert len(warns) == 0
    # Fixed: 730 * $0.36 = $262.80; Capacity Units: 730 * 2 * $0.0144 = $21.024 -> $283.82
    assert priced[0].monthly_cost == Decimal("283.82")
    assert priced[0].missing_price_warning is None
    assert prov[0].meter_or_sku_id == "928d2f33-0737-413d-bcd6-d340f6c67250"


@pytest.mark.asyncio
async def test_pricing_engine_live_api_matching_caching_and_zone_fallback(
    tmp_path: Path,
) -> None:
    """Verify live API querying, multi-meter selection, caching, and regional zone fallback."""
    settings = Settings(offline_pricing_mode=False)
    cache = AzurePriceCache(cache_file=tmp_path / "live_cache.json", ttl_hours=24)
    mock_client = AsyncMock(spec=AzureRetailPricesClient)

    fd_live_items = [
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
            retail_price=Decimal("35.00"),
            unit_price=Decimal("35.00"),
            tier_minimum_units=0.0,
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
            meter_id="10455c17-0774-5e4c-be93-0f3c32b1beda",
            meter_name="Standard Requests",
            product_id="DZH318Z0BPVW",
            sku_id="DZH318Z0BPVW/000J",
            product_name="Azure Front Door",
            sku_name="Standard",
            service_name="Azure Front Door Service",
            service_id="DZH317F70804",
            service_family="Networking",
            unit_of_measure="10K",
            retail_price=Decimal("0.009"),
            unit_price=Decimal("0.009"),
            tier_minimum_units=0.0,
            arm_region_name="Zone 1",
        ),
    ]

    # Simulate Zone 3 returning empty and falling back to Zone 1
    mock_client.query_prices.side_effect = [[], fd_live_items]

    engine = AzurePricingEngine(settings=settings, client=mock_client, cache=cache)

    rate, meter_id, uom, _, prov = await engine.get_price_for_service(
        "azure-front-door", region="brazilsouth", sku_or_tier="Standard"
    )
    assert prov == "azure_retail_prices_api_live"
    assert rate == Decimal("35.00")
    assert meter_id == "7e3eab72-0b95-5524-984a-d1697f73feee"
    assert uom == "1/Month"
    assert mock_client.query_prices.call_count == 2

    # Second call hits local cache without invoking HTTP client
    rate2, meter_id2, _, _, prov2 = await engine.get_price_for_service(
        "azure-front-door", region="brazilsouth", sku_or_tier="Standard"
    )
    assert prov2 == "azure_retail_prices_api_cached"
    assert rate2 == Decimal("35.00")
    assert meter_id2 == "7e3eab72-0b95-5524-984a-d1697f73feee"
    assert mock_client.query_prices.call_count == 2
