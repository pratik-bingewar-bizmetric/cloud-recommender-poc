"""Unit tests for the deterministic GCP pricing engine and Cloud Billing Catalog client."""

from decimal import Decimal

import pytest

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.analysis import WorkloadAssumptions
from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
from cloud_recommender.schemas.recommendation import ArchitectureComponent
from cloud_recommender.services.pricing.gcp_billing_client import (
    GcpSkuItem,
    convert_gcp_money_to_decimal,
    select_matching_gcp_sku,
)
from cloud_recommender.services.pricing.gcp_engine import GcpPricingEngine


def test_gcp_money_conversion() -> None:
    """Verify exact Decimal arithmetic converting Google Money units + nanos."""
    # $0.000018 / sec (units=0, nanos=18000)
    d1 = convert_gcp_money_to_decimal("0", 18000)
    assert d1 == Decimal("0.000018")

    # $5.25 (units=5, nanos=250000000)
    d2 = convert_gcp_money_to_decimal("5", 250000000)
    assert d2 == Decimal("5.25")

    # None handling
    assert convert_gcp_money_to_decimal(None, None) == Decimal("0.00")


def test_select_matching_gcp_sku() -> None:
    """Verify regional SKU selection logic without arbitrary first-result selection."""
    skus = [
        GcpSkuItem(
            sku_id="SKU-ASIA",
            service_id="152E-C115-5142",
            service_display_name="Cloud Run",
            description="Services CPU in asia-east1",
            service_regions=["asia-east1"],
            usage_unit="s",
            unit_price=Decimal("0.000020"),
        ),
        GcpSkuItem(
            sku_id="SKU-US-CENTRAL",
            service_id="152E-C115-5142",
            service_display_name="Cloud Run",
            description="Services CPU in us-central1",
            service_regions=["us-central1"],
            usage_unit="s",
            unit_price=Decimal("0.000018"),
        ),
    ]

    matched = select_matching_gcp_sku(
        skus, region="us-central1", description_keywords=["services cpu"], usage_unit="s"
    )
    assert matched is not None
    assert matched.sku_id == "SKU-US-CENTRAL"
    assert matched.unit_price == Decimal("0.000018")

    # Missing region returns None rather than arbitrary mismatch
    assert select_matching_gcp_sku(skus, region="europe-west1") is None


@pytest.mark.asyncio
async def test_gcp_pricing_engine_deterministic_bom() -> None:
    """Verify deterministic Decimal BOM calculations across GCP components."""
    engine = GcpPricingEngine(settings=Settings(offline_pricing_mode=True))
    assumptions = WorkloadAssumptions(
        customer_count=10000,
        monthly_active_users=2500,
        peak_rps=50.0,
        db_storage_gb=100.0,
        blob_storage_gb=250.0,
        monthly_egress_gb=150.0,
        ai_support_monthly_tokens=5000000,
        ha_required=True,
    )

    components = [
        ArchitectureComponent(
            component_id="comp-run",
            category=ServiceCategory.COMPUTE,
            service_id="gcp-cloud-run",
            service_name="Google Cloud Run",
            quantity=2,
            rationale="API container",
            monthly_cost=Decimal("0.00"),
        ),
        ArchitectureComponent(
            component_id="comp-sql",
            category=ServiceCategory.DATABASE,
            service_id="gcp-cloud-sql-postgres",
            service_name="Cloud SQL for PostgreSQL",
            quantity=1,
            rationale="Transactional persistence",
            monthly_cost=Decimal("0.00"),
        ),
        ArchitectureComponent(
            component_id="comp-gcs",
            category=ServiceCategory.STORAGE,
            service_id="gcp-cloud-storage",
            service_name="Google Cloud Storage",
            quantity=1,
            rationale="Object store",
            monthly_cost=Decimal("0.00"),
        ),
        ArchitectureComponent(
            component_id="comp-vertex",
            category=ServiceCategory.AI_ML,
            service_id="gcp-vertex-ai",
            service_name="Vertex AI",
            quantity=1,
            rationale="Gemini customer support",
            monthly_cost=Decimal("0.00"),
        ),
        ArchitectureComponent(
            component_id="comp-iam",
            category=ServiceCategory.SECURITY,
            service_id="gcp-iam-service-account",
            service_name="IAM Service Account",
            quantity=1,
            rationale="Workload identity",
            monthly_cost=Decimal("0.00"),
        ),
    ]

    (
        priced,
        bom,
        prov,
        warns,
        assump_list,
    ) = await engine.price_architecture(
        components=components,
        assumptions=assumptions,
        region="us-central1",
        buffer_percentage=Decimal("15.00"),
    )

    assert len(warns) == 0
    assert bom.is_complete is True
    assert bom.compute > Decimal("0.00")
    assert bom.database > Decimal("0.00")
    assert bom.storage > Decimal("0.00")
    assert bom.ai > Decimal("0.00")
    assert bom.total_monthly == bom.subtotal + bom.safety_buffer_amount
    assert bom.total_five_month == bom.total_monthly * Decimal("5.00")
    assert bom.total_annual == bom.total_monthly * Decimal("12.00")

    # IAM service account must be $0.00 and bundled/verified
    iam_comp = next(c for c in priced if c.service_id == "gcp-iam-service-account")
    assert iam_comp.monthly_cost == Decimal("0.00")
    assert iam_comp.pricing_status == "bundled"

    # All provenance records must reference GCP
    assert all(p.provider == CloudProvider.GCP for p in prov)
