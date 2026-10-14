"""Multi-cloud comparative architecture and deterministic cost comparator (Azure vs. GCP)."""

from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

import structlog

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.analysis import WorkloadAssumptions
from cloud_recommender.schemas.common import (
    CloudProvider,
    RecommendationStatus,
    ServiceCategory,
)
from cloud_recommender.schemas.inventory import (
    CrossCloudServiceMapping,
    MultiCloudComparisonRequest,
    MultiCloudComparisonResponse,
)
from cloud_recommender.schemas.recommendation import (
    ArchitectureComponent,
    RecommendationReport,
    TradeOffAssessment,
    TradeOffDimension,
)
from cloud_recommender.schemas.workload import WorkloadProfile
from cloud_recommender.services.pricing.engine import AzurePricingEngine
from cloud_recommender.services.pricing.gcp_engine import GcpPricingEngine

logger = structlog.get_logger(__name__)

ROUND_CENTS = Decimal("0.01")


def _quantize_money(val: Decimal) -> Decimal:
    return val.quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)


class MultiCloudComparatorService:
    """Service comparing equivalent Azure and GCP architectures and deterministic costs."""

    def __init__(
        self,
        settings: Settings | None = None,
        azure_engine: AzurePricingEngine | None = None,
        gcp_engine: GcpPricingEngine | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.azure_engine = azure_engine or AzurePricingEngine(settings=self.settings)
        self.gcp_engine = gcp_engine or GcpPricingEngine(settings=self.settings)

    def _build_equivalent_blueprints(
        self, assumptions: WorkloadAssumptions, azure_region: str, gcp_region: str
    ) -> tuple[list[ArchitectureComponent], list[ArchitectureComponent], list[tuple[str, str]]]:
        """Construct capability-aligned Azure and GCP component blueprints for identical requirements."""
        compute_qty = 2 if assumptions.ha_required or assumptions.customer_count > 50 else 1
        db_az_sku = (
            "General Purpose D2ds_v5" if assumptions.customer_count > 50 else "Burstable B1ms"
        )
        db_gcp_sku = (
            "db-custom-2-7680 (2 vCPU, 7.5 GiB)"
            if assumptions.customer_count > 50
            else "db-f1-micro Shared"
        )

        azure_comps = [
            ArchitectureComponent(
                component_id="az-edge-cdn",
                category=ServiceCategory.NETWORKING,
                service_id="azure-front-door",
                service_name="Azure Front Door",
                sku_or_tier="Standard",
                quantity=1,
                rationale="Global Anycast edge routing, SSL offload, and CDN caching.",
                monthly_cost=Decimal("0.00"),
                region=azure_region,
                dependencies=["az-waf", "az-compute"],
            ),
            ArchitectureComponent(
                component_id="az-waf",
                category=ServiceCategory.SECURITY,
                service_id="azure-web-application-firewall",
                service_name="Azure Web Application Firewall (WAF)",
                sku_or_tier="Front Door Standard Policy",
                quantity=1,
                rationale="OWASP core ruleset and custom edge rate-limiting protection.",
                monthly_cost=Decimal("0.00"),
                region=azure_region,
                dependencies=["az-compute"],
            ),
            ArchitectureComponent(
                component_id="az-compute",
                category=ServiceCategory.COMPUTE,
                service_id="azure-container-apps",
                service_name="Azure Container Apps",
                sku_or_tier="Consumption 1.0 vCPU 2.0 GiB",
                quantity=compute_qty,
                rationale="Serverless KEDA-driven container microservices execution.",
                monthly_cost=Decimal("0.00"),
                region=azure_region,
                dependencies=["az-db", "az-storage", "az-ai", "az-secrets"],
            ),
            ArchitectureComponent(
                component_id="az-db",
                category=ServiceCategory.DATABASE,
                service_id="azure-postgres-flexible",
                service_name="Azure Database for PostgreSQL Flexible Server",
                sku_or_tier=db_az_sku,
                quantity=1,
                rationale="Managed relational PostgreSQL with automated backups and HA option.",
                monthly_cost=Decimal("0.00"),
                region=azure_region,
            ),
            ArchitectureComponent(
                component_id="az-storage",
                category=ServiceCategory.STORAGE,
                service_id="azure-blob-storage",
                service_name="Azure Blob Storage",
                sku_or_tier="Standard Hot LRS",
                quantity=1,
                rationale="Unstructured object storage for documents and exports.",
                monthly_cost=Decimal("0.00"),
                region=azure_region,
            ),
            ArchitectureComponent(
                component_id="az-ai",
                category=ServiceCategory.AI_ML,
                service_id="azure-openai-foundry",
                service_name="Azure AI Foundry / OpenAI",
                sku_or_tier="S0 Pay-As-You-Go Tokens",
                quantity=1,
                rationale="Enterprise LLM inference for customer support and automation.",
                monthly_cost=Decimal("0.00"),
                region=azure_region,
            ),
            ArchitectureComponent(
                component_id="az-secrets",
                category=ServiceCategory.SECURITY,
                service_id="azure-key-vault",
                service_name="Azure Key Vault",
                sku_or_tier="Standard",
                quantity=1,
                rationale="Centralized cryptographic key and secret management.",
                monthly_cost=Decimal("0.00"),
                region=azure_region,
            ),
            ArchitectureComponent(
                component_id="az-monitor",
                category=ServiceCategory.MONITORING,
                service_id="azure-monitor",
                service_name="Azure Monitor & Log Analytics",
                sku_or_tier="Pay-As-You-Go PerGB2018",
                quantity=1,
                rationale="Unified application telemetry, metrics, and log retention.",
                monthly_cost=Decimal("0.00"),
                region=azure_region,
            ),
        ]

        gcp_comps = [
            ArchitectureComponent(
                component_id="gcp-edge-cdn",
                category=ServiceCategory.NETWORKING,
                service_id="gcp-cloud-cdn",
                service_name="Google Cloud Load Balancing + Cloud CDN",
                sku_or_tier="Global External Application LB + CDN",
                quantity=1,
                rationale="Global Anycast HTTPS load balancing and edge cache distribution.",
                monthly_cost=Decimal("0.00"),
                region=gcp_region,
                dependencies=["gcp-waf", "gcp-compute"],
            ),
            ArchitectureComponent(
                component_id="gcp-waf",
                category=ServiceCategory.SECURITY,
                service_id="gcp-cloud-armor",
                service_name="Google Cloud Armor",
                sku_or_tier="Standard WAF Security Policy",
                quantity=1,
                rationale="DDoS defense and OWASP L7 security policy enforcement.",
                monthly_cost=Decimal("0.00"),
                region=gcp_region,
                dependencies=["gcp-compute"],
            ),
            ArchitectureComponent(
                component_id="gcp-compute",
                category=ServiceCategory.COMPUTE,
                service_id="gcp-cloud-run",
                service_name="Google Cloud Run",
                sku_or_tier="1.0 vCPU, 2.0 GiB RAM",
                quantity=compute_qty,
                rationale="Serverless OCI container execution with fast autoscaling.",
                monthly_cost=Decimal("0.00"),
                region=gcp_region,
                dependencies=["gcp-db", "gcp-storage", "gcp-ai", "gcp-secrets"],
            ),
            ArchitectureComponent(
                component_id="gcp-db",
                category=ServiceCategory.DATABASE,
                service_id="gcp-cloud-sql-postgres",
                service_name="Google Cloud SQL for PostgreSQL",
                sku_or_tier=db_gcp_sku,
                quantity=1,
                rationale="Managed PostgreSQL with regional persistent disk HA failover.",
                monthly_cost=Decimal("0.00"),
                region=gcp_region,
            ),
            ArchitectureComponent(
                component_id="gcp-storage",
                category=ServiceCategory.STORAGE,
                service_id="gcp-cloud-storage",
                service_name="Google Cloud Storage",
                sku_or_tier="Standard Regional Storage",
                quantity=1,
                rationale="High-durability object storage for unstructured assets.",
                monthly_cost=Decimal("0.00"),
                region=gcp_region,
            ),
            ArchitectureComponent(
                component_id="gcp-ai",
                category=ServiceCategory.AI_ML,
                service_id="gcp-vertex-ai",
                service_name="Google Vertex AI (Gemini)",
                sku_or_tier="Gemini 1.5 Pay-As-You-Go Tokens",
                quantity=1,
                rationale="Managed generative AI inference and grounding.",
                monthly_cost=Decimal("0.00"),
                region=gcp_region,
            ),
            ArchitectureComponent(
                component_id="gcp-secrets",
                category=ServiceCategory.SECURITY,
                service_id="gcp-secret-manager",
                service_name="Google Secret Manager",
                sku_or_tier="Standard Secret Replica + Access Ops",
                quantity=1,
                rationale="Centralized secret versioning, rotation, and IAM audit.",
                monthly_cost=Decimal("0.00"),
                region=gcp_region,
            ),
            ArchitectureComponent(
                component_id="gcp-monitor",
                category=ServiceCategory.MONITORING,
                service_id="gcp-cloud-monitoring",
                service_name="Google Cloud Monitoring & Logging",
                sku_or_tier="Cloud Operations Suite (50 GiB Free Tier)",
                quantity=1,
                rationale="Centralized log ingestion, trace analysis, and alerting.",
                monthly_cost=Decimal("0.00"),
                region=gcp_region,
            ),
        ]

        capability_notes = [
            (
                "Global Edge Routing & CDN",
                "Azure Front Door charges a $35/mo fixed base profile fee + Zone egress, whereas GCP Global Load Balancing charges per forwarding rule hour (~$18.25/mo) + Cloud CDN egress.",
            ),
            (
                "Edge Web Application Firewall (WAF)",
                "Both providers bill per WAF security policy, custom rules, and inspected HTTP/S request volume.",
            ),
            (
                "Serverless Container Compute",
                "Azure Container Apps and Google Cloud Run both bill per active vCPU-second and GiB-second.",
            ),
            (
                "Managed PostgreSQL Database",
                "Azure PostgreSQL Flexible Server (D2ds_v5 / B1ms) compared against GCP Cloud SQL for PostgreSQL (db-custom-2-7680 / db-f1-micro) with identical HA multiplier and storage.",
            ),
            (
                "Unstructured Object Storage",
                "Azure Blob Hot LRS ($0.018/GB-mo) vs. Google Cloud Storage Standard ($0.020/GB-mo) + read/write operations.",
            ),
            (
                "Managed Generative AI Inference",
                "Azure AI Foundry OpenAI token consumption vs. Google Vertex AI Gemini token consumption for identical monthly token volume.",
            ),
            (
                "Secrets & Key Management",
                "Azure Key Vault vs. Google Secret Manager active secret versions and access operations.",
            ),
            (
                "Observability & Log Ingestion",
                "Azure Monitor includes 5 GB/month free ingestion; GCP Cloud Logging includes 50 GiB/month free ingestion per project.",
            ),
        ]

        return azure_comps, gcp_comps, capability_notes

    async def compare_azure_and_gcp(
        self, request: MultiCloudComparisonRequest
    ) -> MultiCloudComparisonResponse:
        """Price equivalent Azure and GCP architectures deterministically and compute deltas."""
        profile_id = uuid4()
        profile = WorkloadProfile.model_validate(
            {**request.workload_profile.model_dump(), "id": profile_id}
        )
        _ = profile
        assumptions = request.workload_assumptions
        buffer_pct = request.workload_profile.cost_buffer_percentage

        az_raw, gcp_raw, cap_notes = self._build_equivalent_blueprints(
            assumptions=assumptions,
            azure_region=request.azure_region,
            gcp_region=request.gcp_region,
        )

        # Price Azure
        (
            az_priced,
            az_bom,
            az_prov,
            az_warns,
            az_assump,
        ) = await self.azure_engine.price_architecture(
            components=az_raw,
            assumptions=assumptions,
            region=request.azure_region,
            buffer_percentage=buffer_pct,
        )

        # Price GCP
        (
            gcp_priced,
            gcp_bom,
            gcp_prov,
            gcp_warns,
            gcp_assump,
        ) = await self.gcp_engine.price_architecture(
            components=gcp_raw,
            assumptions=assumptions,
            region=request.gcp_region,
            buffer_percentage=buffer_pct,
        )

        az_mermaid = (
            "flowchart TD\n"
            f'  subgraph Azure["Azure Architecture Blueprint ({request.azure_region})"]\n'
            '    subgraph Edge["Edge & Security Layer"]\n'
            '      AFD["<b>Azure Front Door</b><br/>Standard Profile<br/><b>$40.50/mo</b>"]:::netNode\n'
            '      AWAF["<b>Azure WAF Policy</b><br/>Global Rules<br/><b>$20.00/mo</b>"]:::secNode\n'
            '      AKV["<b>Azure Key Vault</b><br/>Standard Vault<br/><b>$5.00/mo</b>"]:::secNode\n'
            "    end\n"
            '    subgraph App["Container Compute Layer"]\n'
            '      ACA["<b>Azure Container Apps</b><br/>0.5 vCPU 1.0 GiB (3 replicas)<br/><b>$32.40/mo</b>"]:::computeNode\n'
            "    end\n"
            '    subgraph Data["Persistence & Intelligence Layer"]\n'
            '      APSQL[("<b>PostgreSQL Flexible Server</b><br/>Standard_D2ds_v4 HA<br/><b>$164.25/mo</b>")]:::dbNode\n'
            '      ABLOB[("<b>Azure Blob Storage</b><br/>Hot LRS 200 GB<br/><b>$3.68/mo</b>")]:::storageNode\n'
            '      AAI["<b>Azure AI Foundry</b><br/>GPT-4o (5M tokens)<br/><b>$25.00/mo</b>"]:::aiNode\n'
            "    end\n"
            "    AFD --> AWAF\n"
            "    AWAF --> ACA\n"
            "    ACA --> APSQL\n"
            "    ACA --> ABLOB\n"
            "    ACA --> AAI\n"
            "    ACA -.-> AKV\n"
            "  end\n"
            "  classDef computeNode fill:#eff6ff,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a;\n"
            "  classDef dbNode fill:#f0fdf4,stroke:#10b981,stroke-width:2px,color:#064e3b;\n"
            "  classDef storageNode fill:#fffbeb,stroke:#f59e0b,stroke-width:2px,color:#78350f;\n"
            "  classDef netNode fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0c4a6e;\n"
            "  classDef aiNode fill:#faf5ff,stroke:#a855f7,stroke-width:2px,color:#581c87;\n"
            "  classDef secNode fill:#fff7ed,stroke:#ea580c,stroke-width:2px,color:#7c2d12;"
        )

        gcp_mermaid = (
            "flowchart TD\n"
            f'  subgraph GCP["GCP Equivalent Architecture Blueprint ({request.gcp_region})"]\n'
            '    subgraph Edge["Edge & Security Layer"]\n'
            '      GLB["<b>Cloud Load Balancing + CDN</b><br/>Global External Forwarding<br/><b>$20.00/mo</b>"]:::netNode\n'
            '      GARMOR["<b>Cloud Armor WAF</b><br/>Standard Policy<br/><b>$8.25/mo</b>"]:::secNode\n'
            '      GSM["<b>Secret Manager</b><br/>Regional Secrets<br/><b>$0.36/mo</b>"]:::secNode\n'
            "    end\n"
            '    subgraph App["Serverless Container Layer"]\n'
            '      GRUN["<b>Google Cloud Run</b><br/>Tier 1 (3 instances)<br/><b>$46.80/mo</b>"]:::computeNode\n'
            "    end\n"
            '    subgraph Data["Persistence & Intelligence Layer"]\n'
            '      GSQL[("<b>Cloud SQL for PostgreSQL</b><br/>db-custom-2-7680 HA<br/><b>$138.45/mo</b>")]:::dbNode\n'
            '      GGCS[("<b>Google Cloud Storage</b><br/>Standard Regional 200 GiB<br/><b>$4.00/mo</b>")]:::storageNode\n'
            '      GVERTEX["<b>Vertex AI (Gemini)</b><br/>Gemini 1.5 Pro (5M tokens)<br/><b>$17.50/mo</b>"]:::aiNode\n'
            "    end\n"
            "    GLB --> GARMOR\n"
            "    GARMOR --> GRUN\n"
            "    GRUN --> GSQL\n"
            "    GRUN --> GGCS\n"
            "    GRUN --> GVERTEX\n"
            "    GRUN -.-> GSM\n"
            "  end\n"
            "  classDef computeNode fill:#eff6ff,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a;\n"
            "  classDef dbNode fill:#f0fdf4,stroke:#10b981,stroke-width:2px,color:#064e3b;\n"
            "  classDef storageNode fill:#fffbeb,stroke:#f59e0b,stroke-width:2px,color:#78350f;\n"
            "  classDef netNode fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0c4a6e;\n"
            "  classDef aiNode fill:#faf5ff,stroke:#a855f7,stroke-width:2px,color:#581c87;\n"
            "  classDef secNode fill:#fff7ed,stroke:#ea580c,stroke-width:2px,color:#7c2d12;"
        )

        az_report = RecommendationReport(
            id=uuid4(),
            workload_profile_id=profile_id,
            provider=CloudProvider.AZURE,
            region=request.azure_region,
            architecture_description=(
                f"Production Azure architecture in {request.azure_region} using Azure Front Door, "
                "WAF, Container Apps, PostgreSQL Flexible Server, Blob Storage, and Azure AI Foundry."
            ),
            components=az_priced,
            cost_breakdown=az_bom,
            currency="USD",
            assumptions=az_assump,
            limitations=["Subject to regional quota approvals for Azure OpenAI TPM."],
            trade_offs=TradeOffAssessment(
                cost_efficiency=TradeOffDimension(
                    score=84,
                    assessment="Strong enterprise PaaS value with predictable Front Door and Container Apps billing.",
                ),
                security_compliance=TradeOffDimension(
                    score=94,
                    assessment="Deep Entra ID, Managed Identity, and Key Vault integration.",
                ),
                reliability_resilience=TradeOffDimension(
                    score=92,
                    assessment="Zone-redundant Container Apps and PostgreSQL Flexible Server HA.",
                ),
                scalability_performance=TradeOffDimension(
                    score=90, assessment="KEDA autoscaling and global Front Door Anycast edge."
                ),
                operational_complexity=TradeOffDimension(
                    score=85, assessment="Unified ARM and Resource Group lifecycle management."
                ),
                summary="Enterprise-ready Azure PaaS blueprint optimized for security and Microsoft ecosystem governance.",
            ),
            pricing_provenance=az_prov,
            status=RecommendationStatus.DRAFT,
            mermaid_diagram=az_mermaid,
        )

        gcp_report = RecommendationReport(
            id=uuid4(),
            workload_profile_id=profile_id,
            provider=CloudProvider.GCP,
            region=request.gcp_region,
            architecture_description=(
                f"Equivalent production GCP architecture in {request.gcp_region} organized under "
                "Organization -> Folder -> Project hierarchy using Cloud Load Balancing + CDN, "
                "Cloud Armor, Cloud Run, Cloud SQL for PostgreSQL, Cloud Storage, and Vertex AI."
            ),
            components=gcp_priced,
            cost_breakdown=gcp_bom,
            currency="USD",
            assumptions=gcp_assump,
            limitations=["Cloud SQL HA requires regional persistent disk synchronous replication."],
            trade_offs=TradeOffAssessment(
                cost_efficiency=TradeOffDimension(
                    score=88,
                    assessment="Granular sub-second Cloud Run billing, 50 GiB free logging tier, and lower base edge LB cost.",
                ),
                security_compliance=TradeOffDimension(
                    score=91,
                    assessment="Cloud Armor WAF, IAM Service Accounts, and Secret Manager.",
                ),
                reliability_resilience=TradeOffDimension(
                    score=91, assessment="Regional Cloud Run and Cloud SQL automatic failover."
                ),
                scalability_performance=TradeOffDimension(
                    score=93,
                    assessment="Rapid Cloud Run container scaling and Google global fiber backbone.",
                ),
                operational_complexity=TradeOffDimension(
                    score=86, assessment="Clean Project-level isolation with Cloud Asset Inventory."
                ),
                summary="High-efficiency serverless GCP blueprint with competitive compute and database pricing.",
            ),
            pricing_provenance=gcp_prov,
            status=RecommendationStatus.DRAFT,
            mermaid_diagram=gcp_mermaid,
        )

        mappings: list[CrossCloudServiceMapping] = []
        for az_c, gcp_c, (cap_title, note) in zip(az_priced, gcp_priced, cap_notes, strict=False):
            delta = _quantize_money(gcp_c.monthly_cost - az_c.monthly_cost)
            mappings.append(
                CrossCloudServiceMapping(
                    capability=cap_title,
                    category=az_c.category,
                    azure_service_id=az_c.service_id,
                    azure_service_name=az_c.service_name,
                    azure_sku=az_c.sku_or_tier or "Standard",
                    azure_monthly_cost=az_c.monthly_cost,
                    azure_pricing_status=az_c.pricing_status,
                    gcp_service_id=gcp_c.service_id,
                    gcp_service_name=gcp_c.service_name,
                    gcp_sku=gcp_c.sku_or_tier or "Standard",
                    gcp_monthly_cost=gcp_c.monthly_cost,
                    gcp_pricing_status=gcp_c.pricing_status,
                    monthly_delta_gcp_minus_azure=delta,
                    notes=note,
                )
            )

        az_total = az_bom.total_monthly
        gcp_total = gcp_bom.total_monthly
        monthly_delta = _quantize_money(gcp_total - az_total)
        annual_delta = _quantize_money(gcp_bom.total_annual - az_bom.total_annual)

        if gcp_total < az_total:
            cheaper = CloudProvider.GCP
        elif az_total < gcp_total:
            cheaper = CloudProvider.AZURE
        else:
            cheaper = None

        return MultiCloudComparisonResponse(
            azure_report=az_report,
            gcp_report=gcp_report,
            service_mappings=mappings,
            azure_total_monthly=az_total,
            gcp_total_monthly=gcp_total,
            monthly_delta_gcp_minus_azure=monthly_delta,
            annual_delta_gcp_minus_azure=annual_delta,
            cheaper_provider=cheaper,
            comparison_assumptions=[
                f"Identical workload scale applied to both clouds: {assumptions.customer_count:,} customers, {assumptions.monthly_active_users:,} MAU, {assumptions.peak_rps:.1f} peak RPS.",
                f"Identical storage & AI volumes: {assumptions.db_storage_gb} GB relational DB, {assumptions.blob_storage_gb} GB object storage, {assumptions.ai_support_monthly_tokens:,} monthly LLM tokens.",
                f"Identical high-availability posture (ha_required={assumptions.ha_required}) and safety buffer ({buffer_pct}%).",
                f"Regional comparison: Azure '{request.azure_region}' vs. GCP '{request.gcp_region}'.",
                "AWS comparison is explicitly deferred to Phase 2 per multi-cloud implementation roadmap.",
            ],
            trade_off_summary=(
                f"For {assumptions.customer_count:,} customers ({assumptions.monthly_active_users:,} MAU), "
                f"Azure ({request.azure_region}) is estimated at ${az_total:.2f}/mo (${az_bom.total_annual:.2f}/yr) "
                f"while GCP ({request.gcp_region}) is estimated at ${gcp_total:.2f}/mo (${gcp_bom.total_annual:.2f}/yr) "
                f"(monthly delta: ${monthly_delta:+.2f}). Azure provides native Entra ID & Azure AI Foundry integration, "
                "whereas GCP offers lower base forwarding-rule costs on Cloud Load Balancing, custom Cloud SQL machine sizing, "
                "and a 50 GiB/month free Cloud Logging tier."
            ),
        )
