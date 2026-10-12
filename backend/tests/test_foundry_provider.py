"""Unit tests for Azure AI Foundry provider configuration, inference, and error handling."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.analysis import ClarifyingAnswer, WorkloadAssumptions
from cloud_recommender.schemas.common import WorkloadCategory
from cloud_recommender.schemas.workload import WorkloadProfile
from cloud_recommender.services.ai.exceptions import (
    AzureAIFoundryAuthError,
    AzureAIFoundryNotConfiguredError,
    AzureAIFoundryRateLimitError,
    AzureAIFoundryResponseError,
    AzureAIFoundryTimeoutError,
)
from cloud_recommender.services.ai.foundry_provider import AzureAIFoundryProvider


def test_foundry_unconfigured_raises_error() -> None:
    """Verify that unconfigured Azure AI Foundry raises actionable error listing missing vars."""
    settings = Settings(
        azure_ai_foundry_endpoint=None,
        azure_ai_foundry_api_key=None,
        azure_ai_foundry_deployment_name=None,
    )
    provider = AzureAIFoundryProvider(settings=settings)

    assert not provider.is_configured()
    with pytest.raises(AzureAIFoundryNotConfiguredError) as exc_info:
        provider.assert_configured()

    assert "AZURE_AI_FOUNDRY_ENDPOINT" in exc_info.value.missing_vars
    assert "AZURE_AI_FOUNDRY_API_KEY" in exc_info.value.missing_vars
    assert "AZURE_AI_FOUNDRY_DEPLOYMENT_NAME" in exc_info.value.missing_vars


def test_foundry_url_builder_formats() -> None:
    """Verify inference URL formatting across Foundry and Azure OpenAI endpoint styles."""
    # Azure OpenAI style
    s1 = Settings(
        azure_ai_foundry_endpoint="https://my-resource.openai.azure.com",
        azure_ai_foundry_api_key="key123",
        azure_ai_foundry_deployment_name="gpt-4o",
        azure_ai_foundry_api_version="2024-05-01-preview",
    )
    p1 = AzureAIFoundryProvider(settings=s1)
    assert (
        p1._build_url()
        == "https://my-resource.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-05-01-preview"
    )

    # Azure AI Foundry / Studio style
    s2 = Settings(
        azure_ai_foundry_endpoint="https://my-project.services.ai.azure.com/models",
        azure_ai_foundry_api_key="key123",
        azure_ai_foundry_deployment_name="gpt-4o",
        azure_ai_foundry_api_version="2024-05-01-preview",
    )
    p2 = AzureAIFoundryProvider(settings=s2)
    assert (
        p2._build_url()
        == "https://my-project.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview"
    )


@pytest.mark.asyncio
async def test_foundry_analyze_requirements_mock_success() -> None:
    """Verify requirements analysis extracts valid WorkloadProfile and ClarifyingQuestions."""
    settings = Settings(
        azure_ai_foundry_endpoint="https://my-foundry.services.ai.azure.com/models",
        azure_ai_foundry_api_key="test-key",
        azure_ai_foundry_deployment_name="gpt-4o",
    )
    provider = AzureAIFoundryProvider(settings=settings)

    mock_response_data = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "application_name": "Customer Support Hub",
                            "category": "web_app",
                            "description": "Multi-tenant CRM and support desk platform",
                            "assumptions": {
                                "customer_count": 10000,
                                "monthly_active_users": 2500,
                                "requests_per_user_per_day": 25,
                                "peak_rps": 60.0,
                                "db_storage_gb": 120.0,
                                "blob_storage_gb": 300.0,
                                "monthly_egress_gb": 200.0,
                                "ai_support_monthly_tokens": 6000000,
                                "target_sla_percentage": 99.95,
                                "ha_required": True,
                                "backup_retention_days": 35,
                                "target_region": "eastus",
                            },
                            "clarifying_questions": [
                                {
                                    "id": "q-1",
                                    "category": "availability",
                                    "question": "What is the acceptable RPO/RTO for failover?",
                                    "rationale": "Directly impacts standby database configuration.",
                                    "options": ["RPO < 5 min, RTO < 15 min", "RPO < 1 hr"],
                                    "default_answer": "RPO < 5 min, RTO < 15 min",
                                    "impact_on_architecture": "Enables Zone-Redundant HA.",
                                }
                            ],
                            "missing_critical_requirements": ["compliance_certifications"],
                        }
                    )
                }
            }
        ]
    }

    mock_resp = httpx.Response(status_code=200, json=mock_response_data)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        profile, questions, assumptions, missing = await provider.analyze_requirements(
            idea="I want a customer management platform with AI support and PostgreSQL.",
            target_region="eastus",
            customer_preset=10000,
        )

    assert profile.name == "Customer Support Hub"
    assert profile.category == WorkloadCategory.WEB_APP
    assert assumptions.customer_count == 10000
    assert assumptions.monthly_active_users == 2500
    assert len(questions) == 1
    assert questions[0].id == "q-1"
    assert "compliance_certifications" in missing


@pytest.mark.asyncio
async def test_foundry_generate_architecture_mock_success() -> None:
    """Verify architecture generation produces components, trade-offs, and Mermaid diagram."""
    settings = Settings(
        azure_ai_foundry_endpoint="https://my-foundry.services.ai.azure.com/models",
        azure_ai_foundry_api_key="test-key",
        azure_ai_foundry_deployment_name="gpt-4o",
    )
    provider = AzureAIFoundryProvider(settings=settings)

    mock_response_data = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "architecture_description": (
                                "Azure Container Apps with PostgreSQL Flexible Server"
                            ),
                            "components": [
                                {
                                    "component_id": "comp-frontend",
                                    "category": "compute",
                                    "service_id": "azure-container-apps",
                                    "service_name": "Azure Container Apps",
                                    "sku_or_tier": "Consumption 0.5 vCPU 1.0 GiB",
                                    "quantity": 2,
                                    "rationale": "Serverless compute for frontend and API.",
                                    "dependencies": ["comp-db"],
                                    "security_considerations": "Private vnet integration",
                                    "reliability_considerations": "Multi-zone replicas",
                                    "scaling_considerations": "Autoscaling 2 to 10 instances",
                                    "known_risks": [],
                                },
                                {
                                    "component_id": "comp-db",
                                    "category": "database",
                                    "service_id": "azure-postgres-flexible",
                                    "service_name": "Azure Database for PostgreSQL",
                                    "sku_or_tier": "General Purpose D2ds_v5",
                                    "quantity": 1,
                                    "rationale": "Managed PostgreSQL with automated backups.",
                                    "dependencies": [],
                                    "security_considerations": "TLS 1.3 enforced",
                                    "reliability_considerations": "Zone-redundant HA",
                                    "scaling_considerations": "Online storage expansion",
                                    "known_risks": [],
                                },
                            ],
                            "trade_offs": {
                                "cost_efficiency": {"score": 88, "assessment": "Optimized"},
                                "security_compliance": {"score": 92, "assessment": "High"},
                                "reliability_resilience": {"score": 95, "assessment": "Resilient"},
                                "scalability_performance": {"score": 90, "assessment": "Elastic"},
                                "operational_complexity": {
                                    "score": 82,
                                    "assessment": "PaaS managed",
                                },
                                "summary": "Balanced production cloud blueprint",
                            },
                            "mermaid_diagram": (
                                "graph TD\n"
                                "  Web --> ACA[Container Apps]\n"
                                "  ACA --> PG[(PostgreSQL)]"
                            ),
                            "assumptions": ["Standard business hour traffic patterns"],
                            "limitations": ["No multi-region active-active"],
                        }
                    )
                }
            }
        ]
    }

    mock_resp = httpx.Response(status_code=200, json=mock_response_data)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        from uuid import uuid4

        profile = WorkloadProfile(
            id=uuid4(),
            name="Test App",
            category=WorkloadCategory.WEB_APP,
            target_regions=["eastus"],
        )
        assumptions = WorkloadAssumptions(customer_count=10000)
        clarifications = [ClarifyingAnswer(question_id="q-1", selected_option="Option A")]

        (
            components,
            trade_offs,
            desc,
            mermaid,
            assump_list,
            limit_list,
        ) = await provider.generate_architecture(profile, assumptions, clarifications)

    assert len(components) == 2
    assert components[0].component_id == "comp-frontend"
    assert components[1].service_id == "azure-postgres-flexible"
    assert trade_offs.reliability_resilience.score == 95
    assert "graph TD" in mermaid
    assert len(assump_list) == 1
    assert len(limit_list) == 1


@pytest.mark.asyncio
async def test_foundry_auth_failure_401() -> None:
    """Verify HTTP 401 raises AzureAIFoundryAuthError."""
    settings = Settings(
        azure_ai_foundry_endpoint="https://my-foundry.services.ai.azure.com/models",
        azure_ai_foundry_api_key="bad-key",
        azure_ai_foundry_deployment_name="gpt-4o",
    )
    provider = AzureAIFoundryProvider(settings=settings)
    mock_resp = httpx.Response(status_code=401, text="Unauthorized: Invalid API key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(AzureAIFoundryAuthError):
            await provider.analyze_requirements(idea="Test app concept")


@pytest.mark.asyncio
async def test_foundry_rate_limit_429() -> None:
    """Verify HTTP 429 raises AzureAIFoundryRateLimitError."""
    settings = Settings(
        azure_ai_foundry_endpoint="https://my-foundry.services.ai.azure.com/models",
        azure_ai_foundry_api_key="test-key",
        azure_ai_foundry_deployment_name="gpt-4o",
    )
    provider = AzureAIFoundryProvider(settings=settings)
    mock_resp = httpx.Response(status_code=429, text="Rate limit exceeded")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(AzureAIFoundryRateLimitError):
            await provider.analyze_requirements(idea="Test app concept")


@pytest.mark.asyncio
async def test_foundry_timeout_exception() -> None:
    """Verify network timeout raises AzureAIFoundryTimeoutError."""
    settings = Settings(
        azure_ai_foundry_endpoint="https://my-foundry.services.ai.azure.com/models",
        azure_ai_foundry_api_key="test-key",
        azure_ai_foundry_deployment_name="gpt-4o",
        llm_request_timeout_seconds=5,
    )
    provider = AzureAIFoundryProvider(settings=settings)

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Timed out"),
    ):
        with pytest.raises(AzureAIFoundryTimeoutError):
            await provider.analyze_requirements(idea="Test app concept")


@pytest.mark.asyncio
async def test_foundry_invalid_json_response() -> None:
    """Verify invalid JSON response raises AzureAIFoundryResponseError."""
    settings = Settings(
        azure_ai_foundry_endpoint="https://my-foundry.services.ai.azure.com/models",
        azure_ai_foundry_api_key="test-key",
        azure_ai_foundry_deployment_name="gpt-4o",
    )
    provider = AzureAIFoundryProvider(settings=settings)
    mock_resp = httpx.Response(
        status_code=200, json={"choices": [{"message": {"content": "Not JSON!"}}]}
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(AzureAIFoundryResponseError):
            await provider.analyze_requirements(idea="Test app concept")
