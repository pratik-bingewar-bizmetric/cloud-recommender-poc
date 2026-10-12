"""Tests for RecommendationReport schema, trade-offs, and monetary precision."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from cloud_recommender.schemas.common import (
    CloudProvider,
    RecommendationStatus,
    ServiceCategory,
)
from cloud_recommender.schemas.recommendation import (
    ArchitectureComponent,
    CostBreakdown,
    PricingReference,
    RecommendationReport,
    TradeOffAssessment,
    TradeOffDimension,
)


def test_recommendation_report_monetary_precision_and_contract() -> None:
    """Verify RecommendationReport validates decimal-accurate financial figures."""
    workload_id = uuid4()

    comp1 = ArchitectureComponent(
        component_id="api-compute",
        category=ServiceCategory.COMPUTE,
        service_id="azure-container-apps",
        service_name="Azure Container Apps",
        sku_or_tier="0.5 vCPU, 1 GiB",
        quantity=3,
        rationale="Serverless container scaling based on HTTP request volume.",
        monthly_cost=Decimal("78.45"),
    )

    comp2 = ArchitectureComponent(
        component_id="db-primary",
        category=ServiceCategory.DATABASE,
        service_id="azure-postgresql-flexible",
        service_name="Azure Database for PostgreSQL Flexible Server",
        sku_or_tier="Standard_D2s_v5",
        quantity=1,
        rationale="Managed PostgreSQL with zone-redundant high availability.",
        monthly_cost=Decimal("142.80"),
    )

    subtotal = comp1.monthly_cost + comp2.monthly_cost  # 78.45 + 142.80 = 221.25
    buffer_amt = Decimal("33.19")  # 15% safety buffer
    total_monthly = subtotal + buffer_amt  # 254.44
    total_annual = total_monthly * Decimal("12")  # 3053.28

    costs = CostBreakdown(
        compute=comp1.monthly_cost,
        database=comp2.monthly_cost,
        subtotal=subtotal,
        safety_buffer_amount=buffer_amt,
        total_monthly=total_monthly,
        total_annual=total_annual,
    )

    trade_offs = TradeOffAssessment(
        cost_efficiency=TradeOffDimension(
            score=88, assessment="Serverless compute minimizes idle costs during off-peak hours."
        ),
        security_compliance=TradeOffDimension(
            score=95, assessment="Native Azure Key Vault integration and HIPAA certification."
        ),
        reliability_resilience=TradeOffDimension(
            score=92, assessment="Zone-redundant standby with automated health probes."
        ),
        scalability_performance=TradeOffDimension(
            score=90, assessment="Rapid horizontal replica scale-out via KEDA."
        ),
        operational_complexity=TradeOffDimension(
            score=85, assessment="PaaS managed platform eliminates container host patching."
        ),
        summary="Optimal cost-to-resilience balance for enterprise microservice workloads.",
    )

    pricing_ref = PricingReference(
        provider=CloudProvider.AZURE,
        service_id="azure-container-apps",
        meter_or_sku_id="D4v5-Standard",
        rate=Decimal("0.000024"),
        unit_description="1 vCPU-Second",
        retrieval_timestamp=datetime.now(UTC),
        source_url="https://prices.azure.com/api/retail/prices",
    )

    report = RecommendationReport(
        workload_profile_id=workload_id,
        provider=CloudProvider.AZURE,
        region="eastus",
        architecture_description="Container Apps microservices with managed PostgreSQL.",
        components=[comp1, comp2],
        cost_breakdown=costs,
        currency="USD",
        assumptions=["Continuous 730 hours/month compute utilization for database."],
        limitations=["Container Apps cold starts of up to 2 seconds if scaled to zero."],
        trade_offs=trade_offs,
        pricing_provenance=[pricing_ref],
        status=RecommendationStatus.PROPOSED,
        mermaid_diagram="graph LR; Client-->ACA; ACA-->Postgres;",
    )

    assert report.workload_profile_id == workload_id
    assert report.cost_breakdown.total_monthly == Decimal("254.44")
    assert report.cost_breakdown.total_annual == Decimal("3053.28")
    assert len(report.components) == 2
    assert report.trade_offs.security_compliance.score == 95
    assert report.pricing_provenance[0].rate == Decimal("0.000024")


def test_recommendation_report_serialization() -> None:
    """Verify recommendation report dumps and loads JSON without data degradation."""
    report = RecommendationReport(
        workload_profile_id=uuid4(),
        provider=CloudProvider.AWS,
        region="us-east-1",
        architecture_description="ECS Fargate stack",
        cost_breakdown=CostBreakdown(
            subtotal=Decimal("100.00"),
            total_monthly=Decimal("115.00"),
            total_annual=Decimal("1380.00"),
        ),
        trade_offs=TradeOffAssessment(
            cost_efficiency=TradeOffDimension(score=80, assessment="Good"),
            security_compliance=TradeOffDimension(score=85, assessment="Compliant"),
            reliability_resilience=TradeOffDimension(score=90, assessment="High"),
            scalability_performance=TradeOffDimension(score=85, assessment="Elastic"),
            operational_complexity=TradeOffDimension(score=80, assessment="Managed"),
            summary="Solid AWS architecture",
        ),
    )

    json_str = report.model_dump_json()
    reloaded = RecommendationReport.model_validate_json(json_str)
    assert reloaded.provider == CloudProvider.AWS
    assert reloaded.cost_breakdown.total_monthly == Decimal("115.00")
