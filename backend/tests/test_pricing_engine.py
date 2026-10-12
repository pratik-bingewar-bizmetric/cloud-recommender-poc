"""Unit tests for the deterministic Azure pricing engine and cost simulator."""

from decimal import Decimal

import pytest

from cloud_recommender.schemas.analysis import WorkloadAssumptions
from cloud_recommender.schemas.common import ServiceCategory
from cloud_recommender.schemas.recommendation import ArchitectureComponent
from cloud_recommender.services.pricing.engine import AzurePricingEngine


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
    """Verify explicit warning is produced when a service rate is unknown."""
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
