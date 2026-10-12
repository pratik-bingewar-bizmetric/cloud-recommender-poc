"""Integration tests for Phase A API routes (analysis, architecture, pricing)."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cloud_recommender.core.config import Settings
from cloud_recommender.main import create_app
from cloud_recommender.schemas.analysis import ClarifyingQuestion, WorkloadAssumptions
from cloud_recommender.schemas.common import ServiceCategory, WorkloadCategory
from cloud_recommender.schemas.recommendation import (
    ArchitectureComponent,
    TradeOffAssessment,
    TradeOffDimension,
)
from cloud_recommender.schemas.workload import WorkloadProfile, WorkloadProfileCreate
from cloud_recommender.services.ai.foundry_provider import AzureAIFoundryProvider


@pytest.fixture
def app_with_unconfigured_foundry() -> FastAPI:
    s = Settings(
        azure_ai_foundry_endpoint=None,
        azure_ai_foundry_api_key=None,
        azure_ai_foundry_deployment_name=None,
        catalog_offline_mode=True,
    )
    return create_app(settings=s)


@pytest.fixture
def app_with_configured_foundry() -> FastAPI:
    s = Settings(
        azure_ai_foundry_endpoint="https://my-foundry.services.ai.azure.com/models",
        azure_ai_foundry_api_key="valid-key",
        azure_ai_foundry_deployment_name="gpt-4o",
        catalog_offline_mode=True,
    )
    return create_app(settings=s)


@pytest.mark.asyncio
async def test_api_requirements_analysis_unconfigured_foundry_503(
    app_with_unconfigured_foundry: FastAPI,
) -> None:
    """Verify endpoint returns 503 when Azure AI Foundry credentials are unconfigured."""
    transport = ASGITransport(app=app_with_unconfigured_foundry)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/analysis/requirements",
            json={
                "idea": "I want a customer management platform with AI support and PostgreSQL.",
                "target_region": "eastus",
            },
        )

    assert response.status_code == 503
    data = response.json()
    detail = data.get("error", {}).get("message", {})
    assert detail.get("error_code") == "AZURE_AI_FOUNDRY_NOT_CONFIGURED"
    assert "AZURE_AI_FOUNDRY_ENDPOINT" in detail.get("missing_variables", [])


@pytest.mark.asyncio
async def test_api_requirements_analysis_validation_error(
    app_with_configured_foundry: FastAPI,
) -> None:
    """Verify input validation rejects idea shorter than 10 characters with 422."""
    transport = ASGITransport(app=app_with_configured_foundry)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/analysis/requirements",
            json={"idea": "Too short"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_api_requirements_analysis_success(
    app_with_configured_foundry: FastAPI,
) -> None:
    """Verify successful requirements extraction and clarifying question return."""
    expected_profile = WorkloadProfile(
        id=uuid4(),
        name="API Service Hub",
        category=WorkloadCategory.WEB_APP,
        description="Multi-tenant cloud platform",
    )
    expected_questions = [
        ClarifyingQuestion(
            id="q-audit",
            category="compliance",
            question="Does this require HIPAA audit trails?",
            rationale="Enables dedicated audit logging.",
            options=["Yes", "No"],
            default_answer="No",
            impact_on_architecture="Enables log retention policies.",
        )
    ]
    expected_assumptions = WorkloadAssumptions(customer_count=10000)

    transport = ASGITransport(app=app_with_configured_foundry)
    with patch.object(
        AzureAIFoundryProvider,
        "analyze_requirements",
        new_callable=AsyncMock,
        return_value=(expected_profile, expected_questions, expected_assumptions, []),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analysis/requirements",
                json={
                    "idea": (
                        "I want a customer management platform for 10,000 "
                        "customers with user authentication."
                    ),
                    "target_region": "eastus",
                    "customer_preset": 10000,
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["workload_profile"]["name"] == "API Service Hub"
    assert len(data["clarifying_questions"]) == 1
    assert data["workload_assumptions"]["customer_count"] == 10000


@pytest.mark.asyncio
async def test_api_architecture_generate_success(
    app_with_configured_foundry: FastAPI,
) -> None:
    """Verify /api/v1/architecture/generate returns complete RecommendationReport."""
    raw_components = [
        ArchitectureComponent(
            component_id="comp-aca",
            category=ServiceCategory.COMPUTE,
            service_id="azure-container-apps",
            service_name="Azure Container Apps",
            sku_or_tier="Consumption 0.5 vCPU",
            quantity=2,
            rationale="Containerized APIs",
            monthly_cost=Decimal("0.00"),
        ),
        ArchitectureComponent(
            component_id="comp-pg",
            category=ServiceCategory.DATABASE,
            service_id="azure-postgres-flexible",
            service_name="Azure Database for PostgreSQL",
            sku_or_tier="General Purpose D2ds_v5",
            quantity=1,
            rationale="Primary transactional database",
            monthly_cost=Decimal("0.00"),
        ),
    ]
    trade_offs = TradeOffAssessment(
        cost_efficiency=TradeOffDimension(score=85, assessment="Good"),
        security_compliance=TradeOffDimension(score=90, assessment="Strong"),
        reliability_resilience=TradeOffDimension(score=92, assessment="HA"),
        scalability_performance=TradeOffDimension(score=88, assessment="Elastic"),
        operational_complexity=TradeOffDimension(score=80, assessment="Low ops"),
        summary="Balanced production Azure architecture",
    )

    transport = ASGITransport(app=app_with_configured_foundry)
    with patch.object(
        AzureAIFoundryProvider,
        "generate_architecture",
        new_callable=AsyncMock,
        return_value=(
            raw_components,
            trade_offs,
            "Azure Container Apps with PostgreSQL Flexible Server",
            "graph TD\n  Client --> ACA\n  ACA --> PG",
            ["Standard availability"],
            [],
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            dto = WorkloadProfileCreate(
                name="Test Web App",
                category=WorkloadCategory.WEB_APP,
            )
            assumptions = WorkloadAssumptions(customer_count=10000)

            response = await client.post(
                "/api/v1/architecture/generate",
                json={
                    "workload_profile": dto.model_dump(mode="json"),
                    "workload_assumptions": assumptions.model_dump(mode="json"),
                    "clarifications": [{"question_id": "q-audit", "selected_option": "No"}],
                    "target_region": "eastus",
                },
            )

    assert response.status_code == 200
    report = response.json()
    assert report["provider"] == "azure"
    assert len(report["components"]) == 2
    assert "cost_breakdown" in report
    assert float(report["cost_breakdown"]["total_monthly"]) > 0.0
    assert float(report["cost_breakdown"]["total_five_month"]) > 0.0
    assert float(report["cost_breakdown"]["total_annual"]) > 0.0
    assert "graph TD" in report["mermaid_diagram"]


@pytest.mark.asyncio
async def test_api_pricing_simulate_recalculates_instantly(
    app_with_configured_foundry: FastAPI,
) -> None:
    """Verify /api/v1/pricing/simulate recalculates costs without calling LLM."""
    transport = ASGITransport(app=app_with_configured_foundry)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        components = [
            ArchitectureComponent(
                component_id="comp-1",
                category=ServiceCategory.COMPUTE,
                service_id="azure-app-service",
                service_name="Azure App Service",
                sku_or_tier="B1 Basic",
                quantity=1,
                rationale="Web tier",
                monthly_cost=Decimal("0.00"),
            ).model_dump(mode="json")
        ]
        assumptions = WorkloadAssumptions(customer_count=21).model_dump(mode="json")

        response = await client.post(
            "/api/v1/pricing/simulate",
            json={
                "components": components,
                "workload_assumptions": assumptions,
                "target_region": "eastus",
                "safety_buffer_percentage": "15.00",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "cost_breakdown" in data
    assert float(data["cost_breakdown"]["total_monthly"]) > 0.0
    assert len(data["pricing_provenance"]) == 1


@pytest.mark.asyncio
async def test_api_pricing_refresh(app_with_configured_foundry: FastAPI) -> None:
    """Verify /api/v1/pricing/refresh endpoint executes."""
    transport = ASGITransport(app=app_with_configured_foundry)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/pricing/refresh",
            json={"service_ids": ["azure-container-apps"], "region": "eastus"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
