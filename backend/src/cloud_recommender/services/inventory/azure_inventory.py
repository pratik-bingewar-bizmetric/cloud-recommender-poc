"""Azure read-only subscription, resource hierarchy, and cost intelligence service.

Strict adherence to architectural boundaries:
- 100% read-only operations (strictly HTTP GET against Azure Resource Manager).
- Zero resource creation, modification, or deletion against customer subscriptions.
- Supports Service Principal OAuth2 credentials and local Azure CLI access token session.
- Never prints, logs, or exposes credentials or bearer tokens.
- Models full Azure hierarchy: Tenant -> Management Groups -> Subscriptions -> Resource Groups -> Resources.
- Generates evidence-based Mermaid architecture graphs and deterministic cost rollups.
"""

import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
import structlog

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.analysis import WorkloadAssumptions
from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
from cloud_recommender.schemas.inventory import (
    CloudScopeSummary,
    DiscoveredResource,
    HierarchyNode,
    ProviderConnectionStatus,
    ResourceRelationship,
    ScopeCostGroup,
    SubscriptionOrProjectAnalysis,
    SubscriptionRecommendation,
)
from cloud_recommender.schemas.recommendation import (
    ArchitectureComponent,
    CostBreakdown,
    PricingReference,
)
from cloud_recommender.services.inventory.waste_debt_engine import WasteAndTechnicalDebtEngine
from cloud_recommender.services.pricing.engine import AzurePricingEngine

logger = structlog.get_logger(__name__)

ROUND_CENTS = Decimal("0.01")


def _quantize_money(val: Decimal) -> Decimal:
    return val.quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)


class AzureInventoryService:
    """Service discovering and analyzing Azure subscription hierarchy and resources."""

    def __init__(
        self,
        settings: Settings | None = None,
        pricing_engine: AzurePricingEngine | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.pricing_engine = pricing_engine or AzurePricingEngine(settings=self.settings)

    async def get_access_token(self) -> tuple[str | None, str]:
        """Obtain read-only Azure Resource Manager access token without exposing secrets.

        Returns (token, auth_method_description).
        """
        tenant_id = (self.settings.azure_tenant_id or "").strip()
        client_id = (self.settings.azure_client_id or "").strip()
        client_secret = (self.settings.azure_client_secret or "").strip()

        # 1. Service Principal OAuth2 Client Credentials
        if tenant_id and client_id and client_secret:
            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://management.azure.com/.default",
            }
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(token_url, data=data)
                    if resp.status_code == 200:
                        payload = resp.json()
                        token = payload.get("access_token")
                        if token:
                            return token, "service_principal_oauth2"
                    logger.warning(
                        "azure_sp_token_request_failed",
                        status_code=resp.status_code,
                    )
            except Exception as exc:
                logger.warning("azure_sp_token_exception", error=str(exc))

        # 2. Azure CLI session (if az is installed and logged in)
        az_path = shutil.which("az") or shutil.which("az.cmd")
        if az_path:
            try:
                proc = subprocess.run(
                    [
                        az_path,
                        "account",
                        "get-access-token",
                        "--resource",
                        "https://management.azure.com/",
                        "--output",
                        "json",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                if proc.returncode == 0:
                    data_obj = json.loads(proc.stdout)
                    token = data_obj.get("accessToken") or data_obj.get("token")
                    if token:
                        return token, "azure_cli_session"
            except Exception as exc:
                logger.debug("azure_cli_token_attempt_failed", error=str(exc))

        return None, "none"

    async def get_connection_status(self) -> ProviderConnectionStatus:
        """Check read-only ARM connection readiness and pricing API operational status."""
        token, auth_method = await self.get_access_token()
        scopes_count = 0
        limitations: list[str] = [
            "All Azure cloud operations are strictly read-only (Reader, Cost Management Reader).",
            "Zero automated infrastructure mutations or write operations permitted.",
        ]

        if not token:
            return ProviderConnectionStatus(
                provider=CloudProvider.AZURE,
                inventory_auth_ready=False,
                inventory_auth_method="unauthenticated",
                pricing_api_ready=True,
                pricing_api_source="Azure Retail Prices API (Public)",
                authorized_scopes_count=0,
                status_message=(
                    "Azure read-only inventory is unauthenticated. Configure AZURE_TENANT_ID, "
                    "AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET, or run 'az login' on the host."
                ),
                access_limitations=limitations,
            )

        # Count authorized subscriptions
        subs = await self.list_subscriptions(token=token)
        scopes_count = len(subs)

        return ProviderConnectionStatus(
            provider=CloudProvider.AZURE,
            inventory_auth_ready=True,
            inventory_auth_method=auth_method,
            pricing_api_ready=True,
            pricing_api_source="Azure Retail Prices API (Live / Benchmark Cached)",
            authorized_scopes_count=scopes_count,
            status_message=f"Connected to Azure ARM via {auth_method} with {scopes_count} authorized subscription(s).",
            access_limitations=limitations,
        )

    async def _arm_get_all(
        self, url: str, token: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Query read-only ARM endpoint handling nextLink pagination."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        all_items: list[dict[str, Any]] = []
        current_url: str | None = url
        current_params = params

        async with httpx.AsyncClient(timeout=30.0) as client:
            while current_url:
                resp = await client.get(current_url, headers=headers, params=current_params)
                current_params = None  # Params are encoded into nextLink URL
                if resp.status_code != 200:
                    logger.warning(
                        "arm_query_failed",
                        url=current_url,
                        status_code=resp.status_code,
                        detail=resp.text[:300],
                    )
                    break
                data = resp.json()
                items = data.get("value", [])
                if isinstance(items, list):
                    all_items.extend(items)
                current_url = data.get("nextLink")

        return all_items

    async def list_subscriptions(self, token: str | None = None) -> list[CloudScopeSummary]:
        """List authorized Azure subscriptions."""
        if not token:
            token, _ = await self.get_access_token()
        if not token:
            # Fallback to demo fixture subscription if unauthenticated
            return [
                CloudScopeSummary(
                    provider=CloudProvider.AZURE,
                    scope_id="f718c261-ab85-49fd-907e-99c022cc2aeb",
                    display_name="Azure subscription 1",
                    tenant_or_org_id="fe82a67c-faa7-4d9a-bbfa-7d25b7047b41",
                    parent_scope_id=None,
                    state="Enabled",
                    data_source="mock_fixture",
                )
            ]

        url = f"{self.settings.azure_arm_base_url.rstrip('/')}/subscriptions?api-version=2022-12-01"
        items = await self._arm_get_all(url, token)
        summaries: list[CloudScopeSummary] = []
        for item in items:
            sub_id = item.get("subscriptionId", "")
            name = item.get("displayName", sub_id)
            state = item.get("state", "Enabled")
            tenant_id = item.get("tenantId")
            summaries.append(
                CloudScopeSummary(
                    provider=CloudProvider.AZURE,
                    scope_id=sub_id,
                    display_name=name,
                    tenant_or_org_id=tenant_id,
                    parent_scope_id=None,
                    state=state,
                    data_source="live_authenticated",
                )
            )
        return summaries

    async def list_management_groups(self, token: str) -> list[HierarchyNode]:
        """Query Azure Management Groups if authorized."""
        url = f"{self.settings.azure_arm_base_url.rstrip('/')}/providers/Microsoft.Management/managementGroups?api-version=2020-05-01"
        try:
            items = await self._arm_get_all(url, token)
            nodes: list[HierarchyNode] = []
            for item in items:
                mg_id = item.get("id", item.get("name", ""))
                props = item.get("properties", {})
                dname = props.get("displayName", item.get("name", mg_id))
                parent = props.get("details", {}).get("parent", {}).get("id")
                nodes.append(
                    HierarchyNode(
                        node_id=mg_id,
                        name=dname,
                        node_type="azure_management_group",
                        parent_id=parent,
                        state_or_status="Active",
                    )
                )
            return nodes
        except Exception as exc:
            logger.info("management_groups_query_skipped_or_unauthorized", error=str(exc))
            return []

    async def list_resource_groups(self, subscription_id: str, token: str) -> list[dict[str, Any]]:
        """List Resource Groups for the subscription."""
        url = (
            f"{self.settings.azure_arm_base_url.rstrip('/')}/subscriptions/"
            f"{subscription_id}/resourcegroups?api-version=2021-04-01"
        )
        return await self._arm_get_all(url, token)

    async def list_resources(
        self, subscription_id: str, token: str, resource_group: str | None = None
    ) -> list[dict[str, Any]]:
        """List Resources within the subscription or specific resource group."""
        if resource_group:
            url = (
                f"{self.settings.azure_arm_base_url.rstrip('/')}/subscriptions/"
                f"{subscription_id}/resourceGroups/{resource_group}/resources?api-version=2021-04-01"
            )
        else:
            url = (
                f"{self.settings.azure_arm_base_url.rstrip('/')}/subscriptions/"
                f"{subscription_id}/resources?api-version=2021-04-01"
            )
        return await self._arm_get_all(url, token)

    def _normalize_resource_metadata(
        self, raw: dict[str, Any]
    ) -> tuple[str, str, ServiceCategory, str | None, str | None, str]:
        """Map raw ARM resource type and properties to canonical service ID and category.

        Returns (canonical_service_id, service_name, category, sku_str, kind, resource_group).
        """
        arm_id = raw.get("id", "")
        raw_type = raw.get("type", "")
        kind = raw.get("kind")
        sku_obj = raw.get("sku") or {}
        sku_name = sku_obj.get("name") if isinstance(sku_obj, dict) else str(sku_obj)
        sku_tier = sku_obj.get("tier") if isinstance(sku_obj, dict) else None

        sku_parts = []
        if sku_name:
            sku_parts.append(sku_name)
        if sku_tier:
            sku_parts.append(sku_tier)
        sku_str = " ".join(sku_parts) if sku_parts else None

        # Extract Resource Group name from ARM ID
        rg_match = re.search(r"/resourceGroups/([^/]+)/", arm_id, re.IGNORECASE)
        resource_group = rg_match.group(1) if rg_match else "UnknownResourceGroup"

        # 1. Cognitive Services / Azure AI Foundry
        if raw_type.lower() == "microsoft.cognitiveservices/accounts":
            service_id = "azure-openai-foundry"
            cat = ServiceCategory.AI_ML
            if kind and "openai" in kind.lower():
                name = "Azure OpenAI Service"
            elif kind and "formrecognizer" in kind.lower():
                name = "Azure Document Intelligence (Form Recognizer)"
            elif kind and "speech" in kind.lower():
                name = "Azure Speech Services"
            else:
                name = "Azure AI Services / Foundry"
            return service_id, name, cat, sku_str, kind, resource_group

        if raw_type.lower() == "microsoft.cognitiveservices/accounts/projects":
            return (
                "azure-openai-foundry-project",
                "Azure AI Foundry Project",
                ServiceCategory.AI_ML,
                sku_str,
                kind,
                resource_group,
            )

        # 2. Database for PostgreSQL
        if "microsoft.dbforpostgresql" in raw_type.lower():
            return (
                "azure-postgres-flexible",
                "Azure Database for PostgreSQL Flexible Server",
                ServiceCategory.DATABASE,
                sku_str or "Standard_B2s Burstable",
                kind,
                resource_group,
            )

        # 3. App Service Plan (Server Farms)
        if raw_type.lower() == "microsoft.web/serverfarms":
            return (
                "azure-app-service",
                "Azure App Service Plan",
                ServiceCategory.COMPUTE,
                sku_str or "B1 Basic",
                kind,
                resource_group,
            )

        # 4. App Service Web App (Sites)
        if raw_type.lower() == "microsoft.web/sites":
            return (
                "azure-app-service-site",
                "Azure Web App (App Service)",
                ServiceCategory.COMPUTE,
                sku_str or "Hosted on App Service Plan",
                kind,
                resource_group,
            )

        # 5. Key Vault
        if raw_type.lower() == "microsoft.keyvault/vaults":
            return (
                "azure-key-vault",
                "Azure Key Vault",
                ServiceCategory.SECURITY,
                sku_str or "Standard",
                kind,
                resource_group,
            )

        # 6. Managed Identity
        if raw_type.lower() == "microsoft.managedidentity/userassignedidentities":
            return (
                "azure-managed-identity",
                "Azure User-Assigned Managed Identity",
                ServiceCategory.SECURITY,
                sku_str or "Control Plane Identity",
                kind,
                resource_group,
            )

        # 7. Container Apps
        if "microsoft.app/containerapps" in raw_type.lower():
            return (
                "azure-container-apps",
                "Azure Container Apps",
                ServiceCategory.COMPUTE,
                sku_str or "Consumption 0.5 vCPU 1.0 GiB",
                kind,
                resource_group,
            )

        # 8. Front Door / CDN
        if "microsoft.cdn/profiles" in raw_type.lower():
            tier = "Premium" if sku_str and "premium" in sku_str.lower() else "Standard"
            return (
                "azure-front-door",
                "Azure Front Door",
                ServiceCategory.NETWORKING,
                sku_str or f"{tier} Tier",
                kind,
                resource_group,
            )

        # 9. WAF Policy
        if "microsoft.network/frontdoorwebapplicationfirewallpolicies" in raw_type.lower():
            return (
                "azure-web-application-firewall",
                "Azure Front Door WAF Policy",
                ServiceCategory.SECURITY,
                sku_str or "Standard Policy",
                kind,
                resource_group,
            )

        # 10. Application Gateway
        if raw_type.lower() == "microsoft.network/applicationgateways":
            return (
                "azure-web-application-firewall",
                "Azure Application Gateway WAF v2",
                ServiceCategory.NETWORKING,
                sku_str or "WAF_v2",
                kind,
                resource_group,
            )

        # 11. Storage Accounts
        if raw_type.lower() == "microsoft.storage/storageaccounts":
            return (
                "azure-blob-storage",
                "Azure Storage Account (Blob / Data Lake)",
                ServiceCategory.STORAGE,
                sku_str or "Standard_LRS Hot",
                kind,
                resource_group,
            )

        # 12. Azure Monitor / Log Analytics
        if "microsoft.operationalinsights/workspaces" in raw_type.lower():
            return (
                "azure-monitor",
                "Azure Monitor / Log Analytics Workspace",
                ServiceCategory.MONITORING,
                sku_str or "PerGB2018",
                kind,
                resource_group,
            )

        # Fallback
        base_name = raw_type.split("/")[-1] if "/" in raw_type else raw_type
        return (
            f"azure-{base_name.lower()}",
            f"Azure {base_name}",
            ServiceCategory.INTEGRATION,
            sku_str,
            kind,
            resource_group,
        )

    async def _price_discovered_resource(
        self,
        canonical_id: str,
        service_name: str,
        category: ServiceCategory,
        region: str,
        sku_str: str | None,
        kind: str | None,
        native_type: str,
        assumptions: WorkloadAssumptions,
        same_rg_server_farms: list[str],
    ) -> tuple[Decimal, str, str, str | None, PricingReference | None]:
        """Deterministically price a discovered Azure resource using official rates and rules.

        Returns (monthly_cost, pricing_status, explanation, warning, pricing_ref).
        """
        sku_lower = (sku_str or "").lower()

        # 1. Free tier SKUs (e.g. Cognitive Services F0, User-Assigned Managed Identity)
        _ = kind
        if sku_lower.startswith("f0") or "free" in sku_lower:
            return (
                Decimal("0.00"),
                "verified",
                f"{service_name} Free Tier ({sku_str or 'F0'}): $0.00/month included free quota.",
                None,
                None,
            )

        if native_type.lower() == "microsoft.managedidentity/userassignedidentities":
            return (
                Decimal("0.00"),
                "verified",
                "User-Assigned Managed Identity (Entra ID control-plane resource): $0.00/month (included with Azure).",
                None,
                None,
            )

        # 2. Child / Bundled control-plane resources
        if native_type.lower() == "microsoft.cognitiveservices/accounts/projects":
            return (
                Decimal("0.00"),
                "bundled",
                "Azure AI Foundry Project control-plane sub-resource: $0.00 incremental charge (token consumption billed on parent Cognitive Services account).",
                None,
                None,
            )

        # 3. Web App (Sites) hosted on an App Service Plan in the same RG
        if native_type.lower() == "microsoft.web/sites":
            hosting_plan_note = (
                f"hosted on {same_rg_server_farms[0]}"
                if same_rg_server_farms
                else "hosted on App Service Plan"
            )
            return (
                Decimal("0.00"),
                "bundled",
                f"Web App compute is bundled into its hosting App Service Plan ({hosting_plan_note}); $0.00 incremental fee to prevent duplicate billing.",
                None,
                None,
            )

        # 4. Standard priced resources via AzurePricingEngine
        comp = ArchitectureComponent(
            component_id=f"disc-{canonical_id}",
            category=category,
            service_id=canonical_id,
            service_name=service_name,
            sku_or_tier=sku_str,
            quantity=1,
            rationale="Discovered live resource",
            monthly_cost=Decimal("0.00"),
            region=region,
        )

        try:
            (
                rate,
                meter_id,
                unit_desc,
                source_url,
                prov_source,
            ) = await self.pricing_engine.get_price_for_service(
                canonical_id, region=region, sku_or_tier=sku_str
            )

            monthly, qty, u_measure, pricing_desc, warning = (
                self.pricing_engine.calculate_component_cost(
                    comp=comp,
                    assumptions=assumptions,
                    rate=rate,
                    provenance=prov_source,
                    region=region,
                )
            )

            if warning:
                pricing_status = "unpriced"
            elif canonical_id == "azure-openai-foundry":
                pricing_status = "provisional"  # Token pay-as-you-go consumption model
            else:
                pricing_status = "verified"

            pref = PricingReference(
                provider=CloudProvider.AZURE,
                service_id=canonical_id,
                meter_or_sku_id=meter_id,
                rate=rate,
                unit_description=unit_desc,
                retrieval_timestamp=datetime.now(UTC),
                source_url=source_url,
                provenance_source=prov_source,
                service_name=service_name,
                sku_name=sku_str,
                arm_region_name=region,
                pricing_tier_or_notes=f"Discovered {native_type}",
            )

            return monthly, pricing_status, pricing_desc, warning, pref

        except Exception as exc:
            logger.warning("resource_pricing_failed", canonical_id=canonical_id, error=str(exc))
            warning_msg = (
                f"Official pricing for {native_type} ({canonical_id}) could not be verified."
            )
            return (
                Decimal("0.00"),
                "unpriced",
                warning_msg,
                warning_msg,
                None,
            )

    def _get_category_node_class(self, category: ServiceCategory) -> str:
        """Map ServiceCategory enum to high-contrast Mermaid node class."""
        if category == ServiceCategory.COMPUTE:
            return "computeNode"
        if category == ServiceCategory.DATABASE:
            return "dbNode"
        if category == ServiceCategory.STORAGE:
            return "storageNode"
        if category == ServiceCategory.NETWORKING:
            return "netNode"
        if category == ServiceCategory.AI_ML:
            return "aiNode"
        if category == ServiceCategory.SECURITY:
            return "secNode"
        if category == ServiceCategory.MONITORING:
            return "monNode"
        return "computeNode"

    def _build_mermaid_diagram(
        self,
        sub_name: str,
        groups: list[ScopeCostGroup],
        resources: list[DiscoveredResource],
    ) -> str:
        """Construct renderable Mermaid flowchart illustrating discovered hierarchy and edges."""
        lines = ["flowchart TD"]
        lines.append(f'  subgraph Sub["Subscription: {sub_name}"]')

        # Resource Group subgraphs
        for g_idx, group in enumerate(groups):
            rg_node_id = f"RG_{g_idx}"
            lines.append(
                f'    subgraph {rg_node_id}["Resource Group: {group.group_name} ({group.location})"]'
            )
            if not group.resources:
                lines.append(
                    f'      empty_{g_idx}["(No active resources provisioned)"]:::emptyNode'
                )
            for r_idx, r in enumerate(group.resources):
                r_code = f"res_{g_idx}_{r_idx}"
                clean_name = r.resource_name.split("/")[-1].replace('"', "'")
                service_label = r.canonical_service_id.replace("azure-", "")
                cost_tag = (
                    f"${r.estimated_monthly_cost:.2f}/mo"
                    if r.estimated_monthly_cost > 0
                    else r.pricing_status.capitalize()
                )
                cls_name = self._get_category_node_class(r.service_category)
                lines.append(
                    f'      {r_code}["<b>{clean_name}</b><br/>{service_label}<br/><b>{cost_tag}</b>"]:::{cls_name}'
                )
            lines.append("    end")
        lines.append("  end")

        # Create quick map from resource_id to node_code
        id_to_code: dict[str, str] = {}
        for g_idx, group in enumerate(groups):
            for r_idx, r in enumerate(group.resources):
                id_to_code[r.resource_id] = f"res_{g_idx}_{r_idx}"

        # Relationships
        rendered_edges = set()
        for r in resources:
            src_code = id_to_code.get(r.resource_id)
            if not src_code:
                continue
            for rel in r.relationships:
                tgt_code = id_to_code.get(rel.target_resource_id)
                if not tgt_code or src_code == tgt_code:
                    continue
                edge_pair = (src_code, tgt_code, rel.is_verified)
                if edge_pair in rendered_edges:
                    continue
                rendered_edges.add(edge_pair)

                if rel.is_verified:
                    lines.append(f'  {src_code} -->|"{rel.direction}"| {tgt_code}')
                else:
                    lines.append(f'  {src_code} -.->|"{rel.direction}"| {tgt_code}')

        # Node class styling definitions
        lines.append(
            "  classDef computeNode fill:#eff6ff,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a;"
        )
        lines.append(
            "  classDef dbNode fill:#f0fdf4,stroke:#10b981,stroke-width:2px,color:#064e3b;"
        )
        lines.append(
            "  classDef storageNode fill:#fffbeb,stroke:#f59e0b,stroke-width:2px,color:#78350f;"
        )
        lines.append(
            "  classDef netNode fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0c4a6e;"
        )
        lines.append(
            "  classDef aiNode fill:#faf5ff,stroke:#a855f7,stroke-width:2px,color:#581c87;"
        )
        lines.append(
            "  classDef secNode fill:#fff7ed,stroke:#ea580c,stroke-width:2px,color:#7c2d12;"
        )
        lines.append(
            "  classDef monNode fill:#f8fafc,stroke:#64748b,stroke-width:2px,color:#1e293b;"
        )
        lines.append(
            "  classDef emptyNode fill:#f8fafc,stroke:#94a3b8,stroke-width:1.5px,stroke-dasharray: 4 4,color:#64748b;"
        )

        return "\n".join(lines)

    def _generate_subscription_recommendations(
        self,
        resources: list[DiscoveredResource],
        groups: list[ScopeCostGroup],
    ) -> list[SubscriptionRecommendation]:
        """Produce concrete, evidence-based architectural and cost recommendations."""
        recs: list[SubscriptionRecommendation] = []

        # 1. Multi-AI Account Consolidation
        ai_accounts = [
            r
            for r in resources
            if r.canonical_service_id == "azure-openai-foundry"
            and r.native_resource_type.lower() == "microsoft.cognitiveservices/accounts"
            and (r.sku_or_tier or "").startswith("S0")
        ]
        if len(ai_accounts) >= 2:
            recs.append(
                SubscriptionRecommendation(
                    id="rec-consolidate-ai-accounts",
                    category="redundancy_consolidation",
                    title="Consolidate Dispersed Cognitive Services / Azure AI Foundry Accounts",
                    target_resource_ids=[r.resource_id for r in ai_accounts],
                    target_resource_names=[r.resource_name for r in ai_accounts],
                    evidence=(
                        f"Detected {len(ai_accounts)} distinct S0 Azure AI / Cognitive Services accounts "
                        f"({', '.join(r.resource_name for r in ai_accounts)}) deployed across multiple Resource Groups."
                    ),
                    rationale=(
                        "Multiple independent S0 accounts fragment TPM (Tokens-Per-Minute) quota allocations, "
                        "increase administrative overhead, and duplicate model deployment management. "
                        "Consolidating behind a centralized Azure AI Foundry instance with Azure API Management "
                        "enables unified rate-limiting, chargeback tags, and optimized quota utilization."
                    ),
                    estimated_monthly_impact=Decimal("-25.00"),
                    impact_type="monthly_savings",
                    assumptions=[
                        "Assumes non-production workloads can share centralized model endpoints.",
                        "API Management Consumption or Basic tier used for gateway routing.",
                    ],
                    limitations=[
                        "Does not alter billing if separate accounts are mandated for compliance boundary isolation.",
                    ],
                )
            )

        # 2. Cross-Region Geographic Disparity Check
        for group in groups:
            locations = {r.region.lower() for r in group.resources if r.region}
            if len(locations) > 1:
                cross_resources = [r for r in group.resources if r.region]
                recs.append(
                    SubscriptionRecommendation(
                        id=f"rec-cross-region-{group.group_name}",
                        category="architecture_modernization",
                        title=f"Eliminate Inter-Region Latency in Resource Group '{group.group_name}'",
                        target_resource_ids=[r.resource_id for r in cross_resources],
                        target_resource_names=[r.resource_name for r in cross_resources],
                        evidence=(
                            f"Resource Group '{group.group_name}' contains resources in disparate geographic regions: "
                            f"{', '.join(sorted(locations))} (e.g. app compute vs. relational database in different countries)."
                        ),
                        rationale=(
                            "Distributing tightly coupled application compute and databases across different regions "
                            "incurs 50ms-150ms round-trip latency per query and generates billable cross-region "
                            "inter-data-center data transfer egress charges."
                        ),
                        estimated_monthly_impact=Decimal("-15.00"),
                        impact_type="monthly_savings",
                        assumptions=[
                            "Compute and database should reside in the same primary Azure region for sub-millisecond local network latency.",
                        ],
                        limitations=[
                            "Cross-region placement may have been selected intentionally if specific SKUs had regional capacity constraints.",
                        ],
                    )
                )

        # 3. Empty Resource Group Hygiene
        for group in groups:
            if group.resource_count == 0:
                recs.append(
                    SubscriptionRecommendation(
                        id=f"rec-empty-rg-{group.group_name}",
                        category="cost_optimization",
                        title=f"Clean Up Empty Resource Group '{group.group_name}'",
                        target_resource_ids=[group.group_id],
                        target_resource_names=[group.group_name],
                        evidence=f"Resource Group '{group.group_name}' contains 0 resources.",
                        rationale=(
                            "Empty resource groups create clutter in tenant inventory and governance dashboards. "
                            "Pruning empty resource groups enforces infrastructure hygiene."
                        ),
                        estimated_monthly_impact=Decimal("0.00"),
                        impact_type="cost_neutral",
                        assumptions=[
                            "Resource group has no active role assignments or policy locks."
                        ],
                    )
                )

        # 4. Observability & Edge Security Hygiene
        has_monitor = any(r.canonical_service_id == "azure-monitor" for r in resources)
        if not has_monitor:
            recs.append(
                SubscriptionRecommendation(
                    id="rec-missing-log-analytics",
                    category="resilience_security_observability",
                    title="Deploy Centralized Azure Monitor Log Analytics Workspace",
                    target_resource_ids=[r.resource_id for r in resources[:3]],
                    target_resource_names=[r.resource_name for r in resources[:3]],
                    evidence="No Log Analytics Workspace (Microsoft.OperationalInsights/workspaces) detected in the subscription.",
                    rationale=(
                        "Without centralized Log Analytics, diagnostic logs, container metrics, and security audit trails "
                        "are not centrally retained, limiting incident response and compliance audit capabilities."
                    ),
                    estimated_monthly_impact=Decimal("15.00"),
                    impact_type="resilience_investment",
                    assumptions=[
                        "Standard 5GB/month ingestion tier with 30-day default retention.",
                    ],
                )
            )

        return recs

    def _get_demo_fixture_analysis(
        self, scope_id: str, assumptions: WorkloadAssumptions
    ) -> SubscriptionOrProjectAnalysis:
        """Return an explicitly labeled mock fixture analysis when ARM auth is completely absent."""
        # Built to match real verified structure of Azure subscription f718c261-ab85-49fd-907e-99c022cc2aeb
        _ = assumptions
        sub_id = scope_id or "f718c261-ab85-49fd-907e-99c022cc2aeb"
        tenant_id = "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41"

        groups = [
            ScopeCostGroup(
                group_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense",
                group_name="rg-smart-expense",
                group_type="azure_resource_group",
                location="eastus",
                resource_count=6,
                verified_monthly_subtotal=Decimal("84.86"),
                total_monthly=Decimal("84.86"),
                total_five_month=Decimal("424.30"),
                total_annual=Decimal("1018.32"),
                resources=[
                    DiscoveredResource(
                        provider=CloudProvider.AZURE,
                        resource_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense/providers/Microsoft.CognitiveServices/accounts/smart-expense-ai-bizmetric",
                        resource_name="smart-expense-ai-bizmetric",
                        native_resource_type="Microsoft.CognitiveServices/accounts",
                        canonical_service_id="azure-openai-foundry",
                        service_category=ServiceCategory.AI_ML,
                        region="eastus",
                        sku_or_tier="S0",
                        kind="OpenAI",
                        parent_scope_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense",
                        subscription_id=sub_id,
                        resource_group="rg-smart-expense",
                        origin="mock_fixture",
                        pricing_status="provisional",
                        estimated_monthly_cost=Decimal("25.00"),
                        calculation_explanation="S0 Pay-as-you-go Azure OpenAI inference tokens.",
                        tags_or_labels={"Environment": "Production", "Owner": "AI-Team"},
                    ),
                    DiscoveredResource(
                        provider=CloudProvider.AZURE,
                        resource_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense/providers/Microsoft.CognitiveServices/accounts/smart-expense-docintel",
                        resource_name="smart-expense-docintel",
                        native_resource_type="Microsoft.CognitiveServices/accounts",
                        canonical_service_id="azure-openai-foundry",
                        service_category=ServiceCategory.AI_ML,
                        region="eastus",
                        sku_or_tier="F0",
                        kind="FormRecognizer",
                        parent_scope_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense",
                        subscription_id=sub_id,
                        resource_group="rg-smart-expense",
                        origin="mock_fixture",
                        pricing_status="verified",
                        estimated_monthly_cost=Decimal("0.00"),
                        calculation_explanation="Azure Document Intelligence Free Tier (F0): $0.00/mo.",
                        tags_or_labels={"Environment": "Production", "Owner": "AI-Team"},
                    ),
                    DiscoveredResource(
                        provider=CloudProvider.AZURE,
                        resource_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense/providers/Microsoft.CognitiveServices/accounts/smart-expense-speech",
                        resource_name="smart-expense-speech",
                        native_resource_type="Microsoft.CognitiveServices/accounts",
                        canonical_service_id="azure-openai-foundry",
                        service_category=ServiceCategory.AI_ML,
                        region="eastus",
                        sku_or_tier="F0",
                        kind="SpeechServices",
                        parent_scope_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense",
                        subscription_id=sub_id,
                        resource_group="rg-smart-expense",
                        origin="mock_fixture",
                        pricing_status="verified",
                        estimated_monthly_cost=Decimal("0.00"),
                        calculation_explanation="Azure Speech Services Free Tier (F0): $0.00/mo.",
                        tags_or_labels={"Environment": "Production", "Owner": "AI-Team"},
                    ),
                    DiscoveredResource(
                        provider=CloudProvider.AZURE,
                        resource_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense/providers/Microsoft.Compute/disks/disk-analytics-legacy-temp",
                        resource_name="disk-analytics-legacy-temp",
                        native_resource_type="Microsoft.Compute/disks",
                        canonical_service_id="azure-managed-disk",
                        service_category=ServiceCategory.STORAGE,
                        region="eastus",
                        sku_or_tier="Premium_LRS P10 (128 GiB)",
                        kind="Managed",
                        parent_scope_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense",
                        subscription_id=sub_id,
                        resource_group="rg-smart-expense",
                        origin="mock_fixture",
                        pricing_status="verified",
                        estimated_monthly_cost=Decimal("19.71"),
                        calculation_explanation="Standard retail price for Premium SSD P10 128 GiB: $19.71/mo.",
                        configuration={
                            "diskState": "Unattached",
                            "managedBy": None,
                            "diskSizeBytes": 137438953472,
                        },
                        tags_or_labels={},
                    ),
                    DiscoveredResource(
                        provider=CloudProvider.AZURE,
                        resource_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense/providers/Microsoft.Compute/virtualMachines/vm-staging-processor",
                        resource_name="vm-staging-processor",
                        native_resource_type="Microsoft.Compute/virtualMachines",
                        canonical_service_id="azure-virtual-machine",
                        service_category=ServiceCategory.COMPUTE,
                        region="eastus",
                        sku_or_tier="Standard_B2s (2 vCPU, 4 GiB RAM)",
                        kind="IaaS",
                        parent_scope_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense",
                        subscription_id=sub_id,
                        resource_group="rg-smart-expense",
                        origin="mock_fixture",
                        pricing_status="verified",
                        estimated_monthly_cost=Decimal("36.50"),
                        calculation_explanation="Pay-as-you-go Standard_B2s Linux VM: $36.50/mo.",
                        configuration={
                            "powerState": "PowerState/deallocated",
                            "avg_cpu_percent": 0.0,
                        },
                        tags_or_labels={"env": "staging"},
                    ),
                    DiscoveredResource(
                        provider=CloudProvider.AZURE,
                        resource_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense/providers/Microsoft.Network/publicIPAddresses/pip-smart-expense-legacy",
                        resource_name="pip-smart-expense-legacy",
                        native_resource_type="Microsoft.Network/publicIPAddresses",
                        canonical_service_id="azure-public-ip",
                        service_category=ServiceCategory.NETWORKING,
                        region="eastus",
                        sku_or_tier="Standard Static",
                        kind="Static",
                        parent_scope_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense",
                        subscription_id=sub_id,
                        resource_group="rg-smart-expense",
                        origin="mock_fixture",
                        pricing_status="verified",
                        estimated_monthly_cost=Decimal("3.65"),
                        calculation_explanation="Standard Static Public IP Address reservation: $3.65/mo.",
                        configuration={"ipConfiguration": None},
                        tags_or_labels={},
                    ),
                ],
            ),
            ScopeCostGroup(
                group_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-data",
                group_name="rg-smart-expense-data",
                group_type="azure_resource_group",
                location="eastus",
                resource_count=3,
                verified_monthly_subtotal=Decimal("140.25"),
                total_monthly=Decimal("140.25"),
                total_five_month=Decimal("701.25"),
                total_annual=Decimal("1683.00"),
                resources=[
                    DiscoveredResource(
                        provider=CloudProvider.AZURE,
                        resource_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-data/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-smart-expense-dev",
                        resource_name="psql-smart-expense-dev",
                        native_resource_type="Microsoft.DBforPostgreSQL/flexibleServers",
                        canonical_service_id="azure-postgres-flexible",
                        service_category=ServiceCategory.DATABASE,
                        region="eastus",
                        sku_or_tier="Standard_B2s Burstable (Zone-Redundant HA)",
                        kind="GeneralPurpose",
                        parent_scope_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-data",
                        subscription_id=sub_id,
                        resource_group="rg-smart-expense-data",
                        origin="mock_fixture",
                        pricing_status="verified",
                        estimated_monthly_cost=Decimal("73.00"),
                        calculation_explanation="PostgreSQL Flexible Server B2s with Zone-Redundant standby: $73.00/mo.",
                        configuration={
                            "highAvailability": {"mode": "ZoneRedundant"},
                            "backup": {"backupRetentionDays": 7},
                        },
                        tags_or_labels={"env": "dev"},
                    ),
                    DiscoveredResource(
                        provider=CloudProvider.AZURE,
                        resource_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-data/providers/Microsoft.Storage/storageAccounts/stgsmartbackup",
                        resource_name="stgsmartbackup",
                        native_resource_type="Microsoft.Storage/storageAccounts",
                        canonical_service_id="azure-blob-storage",
                        service_category=ServiceCategory.STORAGE,
                        region="eastus",
                        sku_or_tier="Standard_LRS Hot (500 GiB)",
                        kind="StorageV2",
                        parent_scope_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-data",
                        subscription_id=sub_id,
                        resource_group="rg-smart-expense-data",
                        origin="mock_fixture",
                        pricing_status="verified",
                        estimated_monthly_cost=Decimal("12.50"),
                        calculation_explanation="Standard LRS Hot Blob Storage 500 GiB: $12.50/mo.",
                        configuration={
                            "publicNetworkAccess": "Enabled",
                            "networkAcls": {"defaultAction": "Allow"},
                        },
                        tags_or_labels={"env": "dev"},
                    ),
                    DiscoveredResource(
                        provider=CloudProvider.AZURE,
                        resource_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-data/providers/Microsoft.Web/serverfarms/asp-smart-expense",
                        resource_name="asp-smart-expense",
                        native_resource_type="Microsoft.Web/serverfarms",
                        canonical_service_id="azure-app-service",
                        service_category=ServiceCategory.COMPUTE,
                        region="eastus",
                        sku_or_tier="B2 Basic (2 vCPU, 3.5 GiB RAM)",
                        kind="Linux",
                        parent_scope_id=f"/subscriptions/{sub_id}/resourceGroups/rg-smart-expense-data",
                        subscription_id=sub_id,
                        resource_group="rg-smart-expense-data",
                        origin="mock_fixture",
                        pricing_status="verified",
                        estimated_monthly_cost=Decimal("54.75"),
                        calculation_explanation="Azure App Service Plan Basic B2: $54.75/mo.",
                        configuration={"avg_cpu_percent": 3.8},
                        tags_or_labels={"env": "dev"},
                    ),
                ],
            ),
        ]

        all_resources = [r for g in groups for r in g.resources]

        waste_engine = WasteAndTechnicalDebtEngine(metric_window_days=30)
        (
            waste_findings,
            tech_debt_items,
            tot_monthly_savings,
            tot_annual_savings,
            coverage_summary,
        ) = waste_engine.evaluate_scope(CloudProvider.AZURE, sub_id, all_resources, groups)

        cost_breakdown = CostBreakdown(
            compute=Decimal("91.25"),
            database=Decimal("73.00"),
            storage=Decimal("32.21"),
            networking=Decimal("3.65"),
            ai=Decimal("25.00"),
            other=Decimal("0.00"),
            subtotal=Decimal("225.11"),
            verified_subtotal=Decimal("225.11"),
            safety_buffer_amount=Decimal("0.00"),
            total_monthly=Decimal("225.11"),
            total_five_month=Decimal("1125.55"),
            total_annual=Decimal("2701.32"),
            is_complete=True,
            estimate_status="complete",
        )

        mermaid = self._build_mermaid_diagram(
            "Azure subscription 1 (Fixture)", groups, all_resources
        )

        return SubscriptionOrProjectAnalysis(
            provider=CloudProvider.AZURE,
            scope_id=sub_id,
            scope_name="Azure subscription 1 (Mock Fixture)",
            scope_type="azure_subscription",
            tenant_or_org_id=tenant_id,
            hierarchy_nodes=[
                HierarchyNode(
                    node_id=sub_id,
                    name="Azure subscription 1",
                    node_type="azure_subscription",
                    state_or_status="Enabled",
                )
            ],
            data_source="mock_fixture",
            spend_label="estimated_public_list_pricing",
            resource_count=len(all_resources),
            group_count=len(groups),
            groups=groups,
            resources=all_resources,
            cost_breakdown=cost_breakdown,
            pricing_provenance=[],
            architecture_mermaid=mermaid,
            recommendations=[],
            total_potential_monthly_savings=tot_monthly_savings,
            total_potential_annual_savings=tot_annual_savings,
            waste_findings=waste_findings,
            technical_debt_items=tech_debt_items,
            telemetry_coverage=coverage_summary,
            access_limitations=[
                "Loaded from labeled mock fixture because ARM authentication was unavailable."
            ],
            assumptions=["Pricing based on public list rates."],
        )

    async def analyze_subscription(
        self,
        subscription_id: str | None = None,
        resource_group_filter: str | None = None,
        assumptions: WorkloadAssumptions | None = None,
        buffer_percentage: Decimal = Decimal("0.00"),
        metric_window_days: int = 30,
    ) -> SubscriptionOrProjectAnalysis:
        """Discover live Azure subscription resources, build graph, and aggregate costs."""
        assumptions = assumptions or WorkloadAssumptions()
        token, auth_method = await self.get_access_token()

        if not token:
            logger.info("azure_token_unavailable_using_mock_fixture")
            return self._get_demo_fixture_analysis(
                subscription_id or "f718c261-ab85-49fd-907e-99c022cc2aeb", assumptions
            )

        # 1. Resolve Subscription
        sub_id = subscription_id
        sub_name = "Azure Subscription"
        tenant_id = self.settings.azure_tenant_id

        if not sub_id:
            available_subs = await self.list_subscriptions(token=token)
            if available_subs:
                sub_id = available_subs[0].scope_id
                sub_name = available_subs[0].display_name
                tenant_id = available_subs[0].tenant_or_org_id or tenant_id
            else:
                sub_id = (
                    self.settings.azure_subscription_id or "f718c261-ab85-49fd-907e-99c022cc2aeb"
                )

        # 2. Hierarchy: Management Groups (if accessible)
        mg_nodes = await self.list_management_groups(token=token)
        hierarchy_nodes: list[HierarchyNode] = list(mg_nodes)
        hierarchy_nodes.append(
            HierarchyNode(
                node_id=sub_id,
                name=sub_name,
                node_type="azure_subscription",
                state_or_status="Enabled",
            )
        )

        # 3. Discover Resource Groups
        raw_rgs = await self.list_resource_groups(sub_id, token=token)
        if resource_group_filter:
            raw_rgs = [
                rg for rg in raw_rgs if rg.get("name", "").lower() == resource_group_filter.lower()
            ]

        # 4. Discover Resources
        raw_resources = await self.list_resources(
            sub_id, token=token, resource_group=resource_group_filter
        )

        # Index resources by RG and collect server farms for hosting resolution
        rgs_to_raw_resources: dict[str, list[dict[str, Any]]] = {
            rg.get("name", ""): [] for rg in raw_rgs
        }
        for item in raw_resources:
            arm_id = item.get("id", "")
            rg_match = re.search(r"/resourceGroups/([^/]+)/", arm_id, re.IGNORECASE)
            rg_name = rg_match.group(1) if rg_match else "DefaultResourceGroup"
            if rg_name not in rgs_to_raw_resources:
                rgs_to_raw_resources[rg_name] = []
            rgs_to_raw_resources[rg_name].append(item)

        # Process resources into DiscoveredResource
        discovered_resources: list[DiscoveredResource] = []
        cost_groups: list[ScopeCostGroup] = []

        total_compute = Decimal("0.00")
        total_database = Decimal("0.00")
        total_storage = Decimal("0.00")
        total_networking = Decimal("0.00")
        total_ai = Decimal("0.00")
        total_other = Decimal("0.00")

        all_provenance: list[PricingReference] = []

        # First pass: map and price resources
        for rg_dict in raw_rgs:
            rg_name = rg_dict.get("name", "")
            rg_location = rg_dict.get("location", "eastus")
            items = rgs_to_raw_resources.get(rg_name, [])

            hierarchy_nodes.append(
                HierarchyNode(
                    node_id=rg_dict.get("id", f"/subscriptions/{sub_id}/resourceGroups/{rg_name}"),
                    name=rg_name,
                    node_type="azure_resource_group",
                    parent_id=sub_id,
                    location=rg_location,
                )
            )

            # Identify App Service Plans in this RG
            server_farms_in_rg = [
                it.get("name", "")
                for it in items
                if it.get("type", "").lower() == "microsoft.web/serverfarms"
            ]

            rg_resources: list[DiscoveredResource] = []
            rg_subtotal = Decimal("0.00")
            rg_unpriced_count = 0

            for raw_res in items:
                arm_id = raw_res.get("id", "")
                res_name = raw_res.get("name", "")
                native_type = raw_res.get("type", "")
                location = raw_res.get("location", rg_location)
                tags = raw_res.get("tags") or {}

                (
                    canonical_id,
                    service_name,
                    category,
                    sku_str,
                    kind,
                    extracted_rg,
                ) = self._normalize_resource_metadata(raw_res)

                monthly, status, explanation, warning, pref = await self._price_discovered_resource(
                    canonical_id=canonical_id,
                    service_name=service_name,
                    category=category,
                    region=location,
                    sku_str=sku_str,
                    kind=kind,
                    native_type=native_type,
                    assumptions=assumptions,
                    same_rg_server_farms=server_farms_in_rg,
                )

                if warning:
                    rg_unpriced_count += 1

                if pref:
                    all_provenance.append(pref)

                # Add to category totals
                if category == ServiceCategory.COMPUTE:
                    total_compute += monthly
                elif category == ServiceCategory.DATABASE:
                    total_database += monthly
                elif category == ServiceCategory.STORAGE:
                    total_storage += monthly
                elif category == ServiceCategory.NETWORKING:
                    total_networking += monthly
                elif category == ServiceCategory.AI_ML:
                    total_ai += monthly
                else:
                    total_other += monthly

                rg_subtotal += monthly

                d_res = DiscoveredResource(
                    provider=CloudProvider.AZURE,
                    resource_id=arm_id,
                    resource_name=res_name,
                    native_resource_type=native_type,
                    canonical_service_id=canonical_id,
                    service_category=category,
                    region=location,
                    sku_or_tier=sku_str,
                    kind=kind,
                    parent_scope_id=rg_dict.get(
                        "id", f"/subscriptions/{sub_id}/resourceGroups/{rg_name}"
                    ),
                    subscription_id=sub_id,
                    resource_group=rg_name,
                    tags_or_labels=tags,
                    configuration=raw_res.get("properties") or {},
                    relationships=[],
                    origin="discovered",
                    pricing_status=status,  # type: ignore[arg-type]
                    estimated_monthly_cost=monthly,
                    actual_monthly_spend=None,
                    workload_quantity=None,
                    workload_unit=None,
                    calculation_explanation=explanation,
                    missing_price_warning=warning,
                    pricing_reference=pref,
                    discovery_timestamp=datetime.now(UTC),
                )
                rg_resources.append(d_res)
                discovered_resources.append(d_res)

            rg_total_monthly = _quantize_money(rg_subtotal)
            group_summary = ScopeCostGroup(
                group_id=rg_dict.get("id", f"/subscriptions/{sub_id}/resourceGroups/{rg_name}"),
                group_name=rg_name,
                group_type="azure_resource_group",
                location=rg_location,
                resource_count=len(rg_resources),
                verified_monthly_subtotal=rg_total_monthly,
                total_monthly=rg_total_monthly,
                total_five_month=_quantize_money(rg_total_monthly * Decimal("5.00")),
                total_annual=_quantize_money(rg_total_monthly * Decimal("12.00")),
                unpriced_resource_count=rg_unpriced_count,
                is_complete=rg_unpriced_count == 0,
                resources=rg_resources,
            )
            cost_groups.append(group_summary)

        # Second pass: establish evidence-based and co-located relationships
        for r in discovered_resources:
            # 1. Verified parent/child ARM relationship (e.g. CognitiveServices/accounts/projects)
            if "/" in r.resource_name and r.native_resource_type.endswith("/projects"):
                parent_name = r.resource_name.split("/")[0]
                parent_res = next(
                    (
                        p
                        for p in discovered_resources
                        if p.resource_name == parent_name and p.resource_group == r.resource_group
                    ),
                    None,
                )
                if parent_res:
                    r.relationships.append(
                        ResourceRelationship(
                            source_resource_id=parent_res.resource_id,
                            target_resource_id=r.resource_id,
                            target_resource_name=r.resource_name,
                            relationship_type="verified_arm_hierarchy",
                            is_verified=True,
                            direction="parent_to_child",
                            evidence=f"ARM child resource path '{r.resource_name}' under parent account '{parent_name}'.",
                        )
                    )

            # 2. Verified App Service Web App -> Server Farm hosting
            if r.native_resource_type.lower() == "microsoft.web/sites":
                # Look for server farm in same RG
                farm = next(
                    (
                        f
                        for f in discovered_resources
                        if f.native_resource_type.lower() == "microsoft.web/serverfarms"
                        and f.resource_group == r.resource_group
                    ),
                    None,
                )
                if farm:
                    r.relationships.append(
                        ResourceRelationship(
                            source_resource_id=r.resource_id,
                            target_resource_id=farm.resource_id,
                            target_resource_name=farm.resource_name,
                            relationship_type="verified_hosting_plan",
                            is_verified=True,
                            direction="hosted_on",
                            evidence=f"App Service site '{r.resource_name}' hosted on App Service Plan '{farm.resource_name}'.",
                        )
                    )

            # 3. Explicitly labeled inferred relationship: Co-located database/key-vault in same RG
            if r.native_resource_type.lower() == "microsoft.web/sites":
                for peer in discovered_resources:
                    if (
                        peer.resource_group == r.resource_group
                        and peer.resource_id != r.resource_id
                    ):
                        if peer.canonical_service_id in (
                            "azure-postgres-flexible",
                            "azure-key-vault",
                            "azure-managed-identity",
                        ):
                            r.relationships.append(
                                ResourceRelationship(
                                    source_resource_id=r.resource_id,
                                    target_resource_id=peer.resource_id,
                                    target_resource_name=peer.resource_name,
                                    relationship_type="inferred_co_located",
                                    is_verified=False,
                                    direction="depends_on",
                                    evidence=(
                                        f"Co-located in Resource Group '{r.resource_group}' (inferred application tier dependency)."
                                    ),
                                )
                            )

        # Build Totals & CostBreakdown
        subtotal = _quantize_money(
            total_compute
            + total_database
            + total_storage
            + total_networking
            + total_ai
            + total_other
        )
        buffer_amount = _quantize_money(subtotal * (buffer_percentage / Decimal("100.0")))
        total_monthly = _quantize_money(subtotal + buffer_amount)
        total_five_month = _quantize_money(total_monthly * Decimal("5.00"))
        total_annual = _quantize_money(total_monthly * Decimal("12.00"))

        unpriced_count = sum(g.unpriced_resource_count for g in cost_groups)
        unpriced_ids = [
            r.canonical_service_id for r in discovered_resources if r.pricing_status == "unpriced"
        ]

        cost_breakdown = CostBreakdown(
            compute=_quantize_money(total_compute),
            database=_quantize_money(total_database),
            storage=_quantize_money(total_storage),
            networking=_quantize_money(total_networking),
            ai=_quantize_money(total_ai),
            other=_quantize_money(total_other),
            subtotal=subtotal,
            verified_subtotal=subtotal,
            safety_buffer_amount=buffer_amount,
            total_monthly=total_monthly,
            total_five_month=total_five_month,
            total_annual=total_annual,
            is_complete=unpriced_count == 0,
            estimate_status="complete" if unpriced_count == 0 else "incomplete",
            unpriced_component_count=unpriced_count,
            unpriced_service_ids=list(set(unpriced_ids)),
        )

        mermaid_diag = self._build_mermaid_diagram(sub_name, cost_groups, discovered_resources)
        recs = self._generate_subscription_recommendations(discovered_resources, cost_groups)

        waste_engine = WasteAndTechnicalDebtEngine(metric_window_days=metric_window_days)
        (
            waste_findings,
            tech_debt_items,
            tot_monthly_savings,
            tot_annual_savings,
            coverage_summary,
        ) = waste_engine.evaluate_scope(
            CloudProvider.AZURE, sub_id, discovered_resources, cost_groups
        )

        access_limits = [
            f"Authenticated via {auth_method} with read-only ARM permissions.",
            "All resource operations strictly read-only; no infrastructure changes performed.",
        ]
        if not mg_nodes:
            access_limits.append(
                "Management Groups endpoint returned unauthorized or empty; parent tenant hierarchy omitted."
            )

        return SubscriptionOrProjectAnalysis(
            provider=CloudProvider.AZURE,
            scope_id=sub_id,
            scope_name=sub_name,
            scope_type="azure_subscription",
            tenant_or_org_id=tenant_id,
            hierarchy_nodes=hierarchy_nodes,
            data_source="live_authenticated",
            spend_label="estimated_public_list_pricing",
            actual_billed_monthly_spend=None,
            resource_count=len(discovered_resources),
            group_count=len(cost_groups),
            groups=cost_groups,
            resources=discovered_resources,
            cost_breakdown=cost_breakdown,
            pricing_provenance=all_provenance,
            architecture_mermaid=mermaid_diag,
            recommendations=recs,
            total_potential_monthly_savings=tot_monthly_savings,
            total_potential_annual_savings=tot_annual_savings,
            waste_findings=waste_findings,
            technical_debt_items=tech_debt_items,
            telemetry_coverage=coverage_summary,
            access_limitations=access_limits,
            assumptions=[
                "Pricing calculated deterministically from official Azure Retail Prices API rates and verified benchmark cache.",
                "Pay-as-you-go consumption resources use standard baseline workload assumptions.",
                "Actual billed monthly spend is subject to tenant Enterprise Agreements, Reservations, or Savings Plans.",
            ],
            completeness_warning=(
                f"{unpriced_count} resource(s) could not be verified from Azure Retail Prices."
                if unpriced_count > 0
                else None
            ),
            analyzed_at=datetime.now(UTC),
        )
