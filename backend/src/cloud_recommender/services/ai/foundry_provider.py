"""Azure AI Foundry model inference provider with structured schema validation.

Adheres strictly to the single-provider requirement for Phase A:
- Solely integrates with configured Azure AI Foundry model deployments.
- Never falls back silently to mock models in live runtime.
- Strictly raises clear, actionable setup errors when unconfigured.
- Validates model responses against Pydantic domain models.
"""

import json
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import structlog

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.analysis import (
    ClarifyingAnswer,
    ClarifyingQuestion,
    WorkloadAssumptions,
)
from cloud_recommender.schemas.common import (
    ComplianceStandard,
    ServiceCategory,
    WorkloadCategory,
)
from cloud_recommender.schemas.recommendation import (
    ArchitectureComponent,
    TradeOffAssessment,
    TradeOffDimension,
)
from cloud_recommender.schemas.workload import WorkloadProfile
from cloud_recommender.services.ai.exceptions import (
    AzureAIFoundryAuthError,
    AzureAIFoundryNotConfiguredError,
    AzureAIFoundryRateLimitError,
    AzureAIFoundryResponseError,
    AzureAIFoundryTimeoutError,
)

logger = structlog.get_logger(__name__)


PROMPT_VERSION = "2026-10-phase-a-v1"


class AzureAIFoundryProvider:
    """Production provider integrating Azure AI Foundry model deployments."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def is_configured(self) -> bool:
        """Check whether required Azure AI Foundry credentials are configured."""
        endpoint = self.settings.azure_ai_foundry_endpoint
        api_key = self.settings.azure_ai_foundry_api_key
        deployment = self.settings.azure_ai_foundry_deployment_name
        return bool(endpoint and api_key and deployment)

    def assert_configured(self) -> None:
        """Raise AzureAIFoundryNotConfiguredError if configuration is missing."""
        missing = []
        if not self.settings.azure_ai_foundry_endpoint:
            missing.append("AZURE_AI_FOUNDRY_ENDPOINT")
        if not self.settings.azure_ai_foundry_api_key:
            missing.append("AZURE_AI_FOUNDRY_API_KEY")
        if not self.settings.azure_ai_foundry_deployment_name:
            missing.append("AZURE_AI_FOUNDRY_DEPLOYMENT_NAME")

        if missing:
            raise AzureAIFoundryNotConfiguredError(
                message=(
                    f"Azure AI Foundry is not configured. Missing required environment "
                    f"variables: {', '.join(missing)}. Please set these variables in your "
                    f"environment or .env file."
                ),
                missing_vars=missing,
            )

    def _build_url(self) -> str:
        """Construct the official inference completion URL for the deployment."""
        endpoint = (self.settings.azure_ai_foundry_endpoint or "").rstrip("/")
        api_version = self.settings.azure_ai_foundry_api_version
        deployment = self.settings.azure_ai_foundry_deployment_name or ""

        # Azure OpenAI style deployment path
        if "openai.azure.com" in endpoint:
            return (
                f"{endpoint}/openai/deployments/{deployment}"
                f"/chat/completions?api-version={api_version}"
            )

        # Azure AI Foundry / Azure AI Studio Model Inference API
        if "services.ai.azure.com" in endpoint:
            if endpoint.endswith("/models"):
                return f"{endpoint}/chat/completions?api-version={api_version}"
            return f"{endpoint}/models/chat/completions?api-version={api_version}"

        # Standard path fallback
        return f"{endpoint}/chat/completions?api-version={api_version}"

    async def _call_inference(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Execute async HTTP request to Azure AI Foundry model deployment."""
        self.assert_configured()

        url = self._build_url()
        api_key = self.settings.azure_ai_foundry_api_key or ""
        deployment = self.settings.azure_ai_foundry_deployment_name or ""

        headers = {
            "Content-Type": "application/json",
            "api-key": api_key,
        }
        if self.settings.azure_ai_foundry_auth_type == "bearer_token":
            headers["Authorization"] = f"Bearer {api_key}"

        payload: dict[str, Any] = {
            "messages": messages,
            "model": deployment,
            "temperature": temperature
            if temperature is not None
            else self.settings.llm_temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.settings.llm_max_tokens,
            "response_format": {"type": "json_object"},
        }

        timeout = float(self.settings.llm_request_timeout_seconds)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=payload)

            if response.status_code in (401, 403):
                raise AzureAIFoundryAuthError(
                    f"Azure AI Foundry auth failed ({response.status_code}): {response.text}"
                )
            if response.status_code == 429:
                raise AzureAIFoundryRateLimitError(
                    f"Azure AI Foundry rate limit exceeded (429): {response.text}"
                )
            if response.status_code >= 400:
                raise AzureAIFoundryResponseError(
                    f"Azure AI Foundry returned error ({response.status_code}): {response.text}"
                )

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise AzureAIFoundryResponseError(
                    f"Expected JSON object response, received {type(parsed).__name__}"
                )
            return parsed

        except httpx.TimeoutException as exc:
            raise AzureAIFoundryTimeoutError(
                f"Azure AI Foundry request timed out after {timeout} seconds: {exc}"
            ) from exc
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise AzureAIFoundryResponseError(
                f"Failed to parse structured JSON from Azure AI Foundry response: {exc}"
            ) from exc

    async def analyze_requirements(
        self,
        idea: str,
        target_region: str = "eastus",
        customer_preset: int | None = None,
    ) -> tuple[WorkloadProfile, list[ClarifyingQuestion], WorkloadAssumptions, list[str]]:
        """Parse natural language application idea into structured requirements."""
        system_prompt = (
            "You are a Senior Azure Cloud Solutions Architect.\n"
            f"Prompt Version: {PROMPT_VERSION}\n"
            "Analyze the user's natural language application concept.\n"
            "Produce a structured JSON output with the following exact keys:\n"
            "{\n"
            '  "application_name": "Concise name",\n'
            '  "category": "web_app" | "microservices" | "data_pipeline",\n'
            '  "description": "Clear technical description of the application",\n'
            '  "assumptions": {\n'
            '    "customer_count": int,\n'
            '    "monthly_active_users": int,\n'
            '    "requests_per_user_per_day": int,\n'
            '    "peak_rps": float,\n'
            '    "db_storage_gb": float,\n'
            '    "blob_storage_gb": float,\n'
            '    "monthly_egress_gb": float,\n'
            '    "ai_support_monthly_tokens": int,\n'
            '    "target_sla_percentage": float,\n'
            '    "ha_required": bool,\n'
            '    "backup_retention_days": int,\n'
            '    "target_region": "eastus"\n'
            "  },\n"
            '  "clarifying_questions": [\n'
            "    {\n"
            '      "id": "q-1",\n'
            '      "category": "availability | compliance | ai_support | data",\n'
            '      "question": "Question text",\n'
            '      "rationale": "Why this materially changes architecture or cost",\n'
            '      "options": ["Option A", "Option B", "Option C"],\n'
            '      "default_answer": "Option A",\n'
            '      "impact_on_architecture": "How the answer alters Azure services/SKUs"\n'
            "    }\n"
            "  ],\n"
            '  "missing_critical_requirements": ["list", "of", "missing", "aspects"]\n'
            "}\n"
            "Never invent pricing values or arithmetic. Focus on requirement extraction."
        )

        user_content = f"Application Concept: {idea}\nTarget Region: {target_region}"
        if customer_preset is not None:
            user_content += f"\nCustomer Scale Preset: {customer_preset} customers"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        data = await self._call_inference(messages)

        # Build WorkloadAssumptions
        raw_assump = data.get("assumptions", {})
        cust_count = (
            customer_preset
            if customer_preset is not None
            else int(raw_assump.get("customer_count", 10000))
        )
        assumptions = WorkloadAssumptions(
            customer_count=cust_count,
            monthly_active_users=int(
                raw_assump.get("monthly_active_users", max(1, cust_count // 4))
            ),
            requests_per_user_per_day=int(raw_assump.get("requests_per_user_per_day", 20)),
            peak_rps=float(raw_assump.get("peak_rps", max(1.0, cust_count / 200.0))),
            db_storage_gb=float(raw_assump.get("db_storage_gb", 100.0)),
            blob_storage_gb=float(raw_assump.get("blob_storage_gb", 250.0)),
            monthly_egress_gb=float(raw_assump.get("monthly_egress_gb", 150.0)),
            ai_support_monthly_tokens=int(
                raw_assump.get("ai_support_monthly_tokens", cust_count * 500)
            ),
            target_sla_percentage=float(raw_assump.get("target_sla_percentage", 99.95)),
            ha_required=bool(raw_assump.get("ha_required", True)),
            backup_retention_days=int(raw_assump.get("backup_retention_days", 30)),
            target_region=target_region,
        )

        # Build WorkloadProfile
        category_str = data.get("category", "web_app")
        try:
            category = WorkloadCategory(category_str)
        except ValueError:
            category = WorkloadCategory.WEB_APP

        profile = WorkloadProfile(
            id=uuid4(),
            name=data.get("application_name", "Analyzed Workload"),
            description=data.get("description", idea[:200]),
            category=category,
            target_traffic_rps=int(assumptions.peak_rps),
            monthly_active_users=assumptions.monthly_active_users,
            peak_multiplier=Decimal("2.50"),
            target_sla_percentage=Decimal(str(assumptions.target_sla_percentage)),
            high_availability=assumptions.ha_required,
            primary_region=target_region,
            target_regions=[target_region],
            compliance_frameworks=[ComplianceStandard.SOC2],
            storage_volume_gb=Decimal(str(assumptions.db_storage_gb + assumptions.blob_storage_gb)),
            monthly_data_egress_gb=Decimal(str(assumptions.monthly_egress_gb)),
            estimation_assumptions={
                "customer_count": str(assumptions.customer_count),
                "ai_support_monthly_tokens": str(assumptions.ai_support_monthly_tokens),
                "ha_required": str(assumptions.ha_required),
                "analysis_engine": "azure_ai_foundry",
            },
        )

        # Build Clarifying Questions
        questions: list[ClarifyingQuestion] = []
        for q in data.get("clarifying_questions", []):
            try:
                questions.append(ClarifyingQuestion.model_validate(q))
            except Exception as exc:
                logger.warning("invalid_clarifying_question_skipped", error=str(exc))

        missing_critical = data.get("missing_critical_requirements", [])

        return profile, questions, assumptions, missing_critical

    async def generate_architecture(
        self,
        workload: WorkloadProfile,
        assumptions: WorkloadAssumptions,
        clarifications: list[ClarifyingAnswer],
    ) -> tuple[list[ArchitectureComponent], TradeOffAssessment, str, str, list[str], list[str]]:
        """Generate structured production Azure architecture proposal."""
        system_prompt = (
            "You are a Staff Azure Solutions Architect designing a production Azure architecture.\n"
            f"Prompt Version: {PROMPT_VERSION}\n"
            "Requirements:\n"
            "- Architecture must be tailored strictly to requirements and assumptions.\n"
            "- Select real, supported Azure services (e.g. azure-container-apps, "
            "azure-app-service, azure-postgres-flexible, azure-blob-storage, "
            "azure-key-vault, azure-monitor, azure-openai-foundry).\n"
            "- For each component, specify component_id, category, service_id, "
            "service_name, sku_or_tier, quantity, rationale, dependencies, "
            "security_considerations, reliability_considerations, "
            "scaling_considerations, and known_risks.\n"
            "- DO NOT invent price values. Set monthly_cost to 0.00 "
            "(the deterministic pricing engine will price it).\n"
            "- Generate a valid Mermaid.js flowchart (graph TD) illustrating topology.\n"
            "- Provide a 5-pillar trade-off evaluation with scores (1-100) and commentary.\n"
            "Output JSON with exact structure:\n"
            "{\n"
            '  "architecture_description": "Comprehensive topology narrative",\n'
            '  "components": [\n'
            "    {\n"
            '      "component_id": "comp-frontend",\n'
            '      "category": "compute | database | storage | networking | ai_ml | monitoring",\n'
            '      "service_id": "azure-container-apps",\n'
            '      "service_name": "Azure Container Apps",\n'
            '      "sku_or_tier": "Consumption 0.5 vCPU 1.0 GiB",\n'
            '      "quantity": 2,\n'
            '      "rationale": "Technical rationale",\n'
            '      "dependencies": ["comp-api"],\n'
            '      "security_considerations": "Private ingress, mTLS",\n'
            '      "reliability_considerations": "Zone-redundant",\n'
            '      "scaling_considerations": "Autoscale 1 to 10 replicas",\n'
            '      "known_risks": ["Cold start latency on scale-from-zero"]\n'
            "    }\n"
            "  ],\n"
            '  "trade_offs": {\n'
            '    "cost_efficiency": {"score": 85, "assessment": "..."},\n'
            '    "security_compliance": {"score": 90, "assessment": "..."},\n'
            '    "reliability_resilience": {"score": 92, "assessment": "..."},\n'
            '    "scalability_performance": {"score": 88, "assessment": "..."},\n'
            '    "operational_complexity": {"score": 80, "assessment": "..."},\n'
            '    "summary": "Executive trade-off summary"\n'
            "  },\n"
            '  "mermaid_diagram": "graph TD\\n...",\n'
            '  "assumptions": ["..."],\n'
            '  "limitations": ["..."]\n'
            "}"
        )

        clarifications_str = "\n".join(
            f"- {c.question_id}: {c.selected_option}" for c in clarifications
        )
        user_content = (
            f"Workload Profile: {workload.name}\n"
            f"Category: {workload.category.value}\n"
            f"Target Region: {assumptions.target_region}\n"
            f"Customer Count: {assumptions.customer_count}\n"
            f"MAU: {assumptions.monthly_active_users}\n"
            f"Peak RPS: {assumptions.peak_rps}\n"
            f"Database Storage: {assumptions.db_storage_gb} GB\n"
            f"Blob Storage: {assumptions.blob_storage_gb} GB\n"
            f"Monthly Egress: {assumptions.monthly_egress_gb} GB\n"
            f"Monthly AI Tokens: {assumptions.ai_support_monthly_tokens}\n"
            f"Target SLA: {assumptions.target_sla_percentage}%\n"
            f"High Availability: {assumptions.ha_required}\n"
            f"User Clarifications:\n{clarifications_str if clarifications_str else 'None provided'}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        data = await self._call_inference(messages, max_tokens=4096)

        # Parse components
        components: list[ArchitectureComponent] = []
        for raw_c in data.get("components", []):
            try:
                cat_str = raw_c.get("category", "compute")
                try:
                    cat = ServiceCategory(cat_str)
                except ValueError:
                    cat = ServiceCategory.COMPUTE

                comp = ArchitectureComponent(
                    component_id=raw_c.get("component_id", f"comp-{uuid4().hex[:6]}"),
                    category=cat,
                    service_id=raw_c.get("service_id", "azure-container-apps"),
                    service_name=raw_c.get("service_name", "Azure Container Apps"),
                    sku_or_tier=raw_c.get("sku_or_tier"),
                    quantity=int(raw_c.get("quantity", 1)),
                    rationale=raw_c.get("rationale", "Selected for workload requirements"),
                    monthly_cost=Decimal("0.00"),  # Will be priced deterministically
                    region=assumptions.target_region,
                    dependencies=raw_c.get("dependencies", []),
                    security_considerations=raw_c.get("security_considerations"),
                    reliability_considerations=raw_c.get("reliability_considerations"),
                    scaling_considerations=raw_c.get("scaling_considerations"),
                    known_risks=raw_c.get("known_risks", []),
                )
                components.append(comp)
            except Exception as exc:
                logger.warning("invalid_component_skipped", error=str(exc))

        # Parse TradeOffAssessment
        raw_to = data.get("trade_offs", {})
        trade_offs = TradeOffAssessment(
            cost_efficiency=TradeOffDimension(
                score=int(raw_to.get("cost_efficiency", {}).get("score", 85)),
                assessment=str(raw_to.get("cost_efficiency", {}).get("assessment", "Balanced")),
            ),
            security_compliance=TradeOffDimension(
                score=int(raw_to.get("security_compliance", {}).get("score", 90)),
                assessment=str(raw_to.get("security_compliance", {}).get("assessment", "Strong")),
            ),
            reliability_resilience=TradeOffDimension(
                score=int(raw_to.get("reliability_resilience", {}).get("score", 92)),
                assessment=str(
                    raw_to.get("reliability_resilience", {}).get("assessment", "Zone-redundant")
                ),
            ),
            scalability_performance=TradeOffDimension(
                score=int(raw_to.get("scalability_performance", {}).get("score", 88)),
                assessment=str(
                    raw_to.get("scalability_performance", {}).get("assessment", "Scalable")
                ),
            ),
            operational_complexity=TradeOffDimension(
                score=int(raw_to.get("operational_complexity", {}).get("score", 80)),
                assessment=str(
                    raw_to.get("operational_complexity", {}).get("assessment", "Moderate")
                ),
            ),
            summary=str(raw_to.get("summary", "Production-grade Azure cloud blueprint")),
        )

        arch_desc = data.get("architecture_description", "Production Azure multi-tier architecture")
        mermaid = data.get(
            "mermaid_diagram",
            "graph TD\n  Client[Web Client] --> Gateway[Container Apps]\n"
            "  Gateway --> DB[(PostgreSQL Flexible)]",
        )
        assumptions_list = data.get("assumptions", [])
        limitations_list = data.get("limitations", [])

        return (
            components,
            trade_offs,
            arch_desc,
            mermaid,
            assumptions_list,
            limitations_list,
        )
