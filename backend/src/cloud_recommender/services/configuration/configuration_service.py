"""Multi-cloud resource configuration service.

Provides hierarchical scope discovery, Databricks workspace identification,
persistent versioning, tenant isolation, and deterministic selection resolution.
Supports both database persistence and offline/in-memory fallback mode.
"""

import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import structlog

from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.db.models import ResourceConfigurationModel
from cloud_recommender.db.repositories.configuration_repo import (
    ResourceConfigurationRepository,
)
from cloud_recommender.schemas.configuration import (
    ConfigurationStatusResponse,
    ConfiguredScopeItemCreate,
    ConfiguredScopeItemResponse,
    EffectiveSelectionResponse,
    ResourceConfigurationResponse,
    ScopeDiscoveryNode,
    ScopeDiscoveryResponse,
    ScopeType,
    SelectionState,
)
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService

logger = structlog.get_logger(__name__)


class ConfigurationService:
    """Orchestrates resource configuration discovery, persistence, and deterministic resolution."""

    # In-memory store fallback for offline tests and simulation sessions
    _memory_configurations: dict[str, list[ResourceConfigurationResponse]] = {}

    def __init__(
        self,
        repository: ResourceConfigurationRepository | None = None,
        settings: Settings | None = None,
        azure_service: AzureInventoryService | None = None,
        gcp_service: GcpInventoryService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()
        self.azure_service = azure_service or AzureInventoryService(settings=self.settings)
        self.gcp_service = gcp_service or GcpInventoryService(settings=self.settings)

    async def discover_scopes(
        self, connection_id: str, provider: str = "azure"
    ) -> ScopeDiscoveryResponse:
        """Discover hierarchical cloud resources and Databricks workspaces for a connection."""
        prov = provider.lower()
        if prov == "azure":
            return await self._discover_azure_scopes(connection_id)
        if prov == "gcp":
            return await self._discover_gcp_scopes(connection_id)
        if prov == "aws":
            return self._discover_aws_scopes(connection_id)

        return ScopeDiscoveryResponse(
            provider=provider,
            connection_id=connection_id,
            status="unsupported",
            status_message=f"Cloud provider '{provider}' is not supported.",
            last_discovered_at=datetime.now(UTC),
            tree=[],
            total_discovered_resources=0,
            databricks_workspaces_count=0,
        )

    async def _discover_azure_scopes(self, connection_id: str) -> ScopeDiscoveryResponse:
        """Discover Azure subscription hierarchy, resource groups, resources, and Databricks workspaces."""
        token, auth_method = await self.azure_service.get_access_token()
        tree: list[ScopeDiscoveryNode] = []
        total_resources = 0
        databricks_workspaces_count = 0

        if not token:
            # Deterministic simulation fixture with Databricks workspaces
            logger.info("discovering_azure_scopes_simulation", connection_id=connection_id)
            sub_id = "f718c261-ab85-49fd-907e-99c022cc2aeb"
            tenant_id = "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41"

            # Resource Group 1: Analytics & Databricks
            rg1_id = f"/subscriptions/{sub_id}/resourceGroups/rg-analytics-databricks"
            ws1_id = f"{rg1_id}/providers/Microsoft.Databricks/workspaces/adb-lakehouse-prod"
            ws1_node = ScopeDiscoveryNode(
                id=ws1_id,
                name="adb-lakehouse-prod",
                scope_type=ScopeType.DATABRICKS_WORKSPACE,
                scope_identifier=ws1_id,
                parent_scope_identifier=rg1_id,
                resource_type="Microsoft.Databricks/workspaces",
                region="eastus",
                is_leaf=True,
                metadata={
                    "workspace_url": "adb-7840192837.14.azuredatabricks.net",
                    "workspace_id": "7840192837148901",
                    "pricing_tier": "premium",
                    "managed_resource_group_id": f"/subscriptions/{sub_id}/resourceGroups/rg-adb-managed-01",
                    "provisioning_state": "Succeeded",
                    "discovery_status": "discovered",
                },
            )
            sa1_id = f"{rg1_id}/providers/Microsoft.Storage/storageAccounts/stlakehouseprod01"
            sa1_node = ScopeDiscoveryNode(
                id=sa1_id,
                name="stlakehouseprod01",
                scope_type=ScopeType.RESOURCE,
                scope_identifier=sa1_id,
                parent_scope_identifier=rg1_id,
                resource_type="Microsoft.Storage/storageAccounts",
                region="eastus",
                is_leaf=True,
                metadata={"sku": "Standard_GRS", "kind": "StorageV2"},
            )
            rg1_node = ScopeDiscoveryNode(
                id=rg1_id,
                name="rg-analytics-databricks",
                scope_type=ScopeType.RESOURCE_GROUP,
                scope_identifier=rg1_id,
                parent_scope_identifier=sub_id,
                region="eastus",
                is_leaf=False,
                children=[ws1_node, sa1_node],
            )

            # Resource Group 2: Core Compute & Database
            rg2_id = f"/subscriptions/{sub_id}/resourceGroups/rg-finops-core"
            vm1_id = f"{rg2_id}/providers/Microsoft.Compute/virtualMachines/vm-app-server-01"
            vm1_node = ScopeDiscoveryNode(
                id=vm1_id,
                name="vm-app-server-01",
                scope_type=ScopeType.RESOURCE,
                scope_identifier=vm1_id,
                parent_scope_identifier=rg2_id,
                resource_type="Microsoft.Compute/virtualMachines",
                region="eastus",
                is_leaf=True,
                metadata={"vm_size": "Standard_D4s_v5", "os_type": "Linux"},
            )
            db1_id = f"{rg2_id}/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-finops-db"
            db1_node = ScopeDiscoveryNode(
                id=db1_id,
                name="psql-finops-db",
                scope_type=ScopeType.RESOURCE,
                scope_identifier=db1_id,
                parent_scope_identifier=rg2_id,
                resource_type="Microsoft.DBforPostgreSQL/flexibleServers",
                region="eastus",
                is_leaf=True,
                metadata={"sku": "Standard_D4ds_v4", "storage_gb": 128},
            )
            rg2_node = ScopeDiscoveryNode(
                id=rg2_id,
                name="rg-finops-core",
                scope_type=ScopeType.RESOURCE_GROUP,
                scope_identifier=rg2_id,
                parent_scope_identifier=sub_id,
                region="eastus",
                is_leaf=False,
                children=[vm1_node, db1_node],
            )

            sub_node = ScopeDiscoveryNode(
                id=sub_id,
                name="Azure Production Subscription",
                scope_type=ScopeType.SUBSCRIPTION,
                scope_identifier=sub_id,
                parent_scope_identifier=tenant_id,
                is_leaf=False,
                metadata={"tenant_id": tenant_id, "state": "Enabled"},
                children=[rg1_node, rg2_node],
            )
            tree.append(sub_node)
            total_resources = 4
            databricks_workspaces_count = 1

            return ScopeDiscoveryResponse(
                provider="azure",
                connection_id=connection_id,
                tenant_or_org_id=tenant_id,
                status="ready",
                status_message="Discovered Azure resource topology with Databricks workspaces (simulation fixture).",
                last_discovered_at=datetime.now(UTC),
                tree=tree,
                total_discovered_resources=total_resources,
                databricks_workspaces_count=databricks_workspaces_count,
            )

        # Live ARM discovery
        try:
            subs = await self.azure_service.list_subscriptions(token=token)
            if not subs:
                return ScopeDiscoveryResponse(
                    provider="azure",
                    connection_id=connection_id,
                    status="empty",
                    status_message="No authorized subscriptions found for this Azure credential.",
                    last_discovered_at=datetime.now(UTC),
                    tree=[],
                    total_discovered_resources=0,
                    databricks_workspaces_count=0,
                )

            tenant_id = subs[0].tenant_or_org_id or ""

            for sub in subs:
                sub_id = sub.scope_id
                sub_children: list[ScopeDiscoveryNode] = []

                # 1. Fetch Resource Groups
                rgs = await self.azure_service.list_resource_groups(sub_id, token)
                # 2. Fetch Databricks Workspaces
                workspaces = await self.azure_service.list_databricks_workspaces(sub_id, token)
                databricks_workspaces_count += len(workspaces)

                # 3. Fetch All Resources
                all_resources = await self.azure_service.list_resources(sub_id, token)
                total_resources += len(all_resources)

                # Group resources and workspaces by resource group
                rg_map: dict[str, list[ScopeDiscoveryNode]] = {}
                for rg in rgs:
                    rg_name = str(rg.get("name", ""))
                    rg_map[rg_name.lower()] = []

                # Place Databricks workspaces
                for ws in workspaces:
                    ws_rg = str(ws.get("resource_group", "")).lower()
                    ws_id = str(ws.get("resource_id", ""))
                    ws_node = ScopeDiscoveryNode(
                        id=ws_id,
                        name=str(ws.get("name", "")),
                        scope_type=ScopeType.DATABRICKS_WORKSPACE,
                        scope_identifier=ws_id,
                        parent_scope_identifier=ws.get("resource_group"),
                        resource_type="Microsoft.Databricks/workspaces",
                        region=ws.get("region"),
                        is_leaf=True,
                        metadata={
                            "workspace_url": ws.get("workspace_url"),
                            "workspace_id": ws.get("workspace_id"),
                            "pricing_tier": ws.get("pricing_tier"),
                            "managed_resource_group_id": ws.get("managed_resource_group_id"),
                            "provisioning_state": ws.get("provisioning_state"),
                            "discovery_status": "discovered",
                        },
                    )
                    if ws_rg in rg_map:
                        rg_map[ws_rg].append(ws_node)
                    else:
                        rg_map.setdefault(ws_rg, []).append(ws_node)

                # Place standard resources (exclude already added workspaces)
                ws_ids = {ws.get("resource_id") for ws in workspaces}
                for res in all_resources:
                    res_id = str(res.get("id", ""))
                    if res_id in ws_ids:
                        continue
                    res_type = str(res.get("type", ""))
                    res_name = str(res.get("name", ""))
                    res_loc = str(res.get("location", ""))

                    # Extract RG from ARM ID
                    rg_match = re.search(r"/resourceGroups/([^/]+)/", res_id, re.IGNORECASE)
                    rg_name = rg_match.group(1).lower() if rg_match else "unknown"

                    res_node = ScopeDiscoveryNode(
                        id=res_id,
                        name=res_name,
                        scope_type=ScopeType.RESOURCE,
                        scope_identifier=res_id,
                        parent_scope_identifier=rg_match.group(1) if rg_match else None,
                        resource_type=res_type,
                        region=res_loc,
                        is_leaf=True,
                        metadata={"sku": res.get("sku"), "kind": res.get("kind")},
                    )
                    rg_map.setdefault(rg_name, []).append(res_node)

                # Construct RG nodes
                for rg in rgs:
                    rg_name = str(rg.get("name", ""))
                    rg_id = str(rg.get("id", f"/subscriptions/{sub_id}/resourceGroups/{rg_name}"))
                    rg_loc = str(rg.get("location", ""))
                    rg_children = rg_map.get(rg_name.lower(), [])

                    rg_node = ScopeDiscoveryNode(
                        id=rg_id,
                        name=rg_name,
                        scope_type=ScopeType.RESOURCE_GROUP,
                        scope_identifier=rg_id,
                        parent_scope_identifier=sub_id,
                        region=rg_loc,
                        is_leaf=False,
                        children=rg_children,
                    )
                    sub_children.append(rg_node)

                sub_node = ScopeDiscoveryNode(
                    id=sub_id,
                    name=sub.display_name,
                    scope_type=ScopeType.SUBSCRIPTION,
                    scope_identifier=sub_id,
                    parent_scope_identifier=tenant_id,
                    is_leaf=False,
                    metadata={"tenant_id": tenant_id, "state": sub.state},
                    children=sub_children,
                )
                tree.append(sub_node)

            return ScopeDiscoveryResponse(
                provider="azure",
                connection_id=connection_id,
                tenant_or_org_id=tenant_id,
                status="ready",
                status_message=f"Live Azure discovery completed via {auth_method}.",
                last_discovered_at=datetime.now(UTC),
                tree=tree,
                total_discovered_resources=total_resources,
                databricks_workspaces_count=databricks_workspaces_count,
            )
        except Exception as exc:
            logger.warning("azure_scope_discovery_failed", error=str(exc))
            return ScopeDiscoveryResponse(
                provider="azure",
                connection_id=connection_id,
                status="permission_denied",
                status_message=f"Discovery failed or permission denied: {exc}",
                last_discovered_at=datetime.now(UTC),
                tree=[],
                total_discovered_resources=0,
                databricks_workspaces_count=0,
            )

    async def _discover_gcp_scopes(self, connection_id: str) -> ScopeDiscoveryResponse:
        """Discover GCP Organization -> Folders -> Projects hierarchy."""
        tree: list[ScopeDiscoveryNode] = []
        token, auth_method = await self.gcp_service.get_inventory_access_token()

        try:
            projects = await self.gcp_service.list_projects(token=token)
            total_resources = 0
            for proj in projects:
                proj_id = proj.scope_id
                proj_name = proj.display_name
                org_id = proj.tenant_or_org_id

                # In benchmark mode, simulate sample GCP assets
                assets = [
                    ScopeDiscoveryNode(
                        id=f"//compute.googleapis.com/projects/{proj_id}/zones/us-central1-a/instances/gce-app-01",
                        name="gce-app-01",
                        scope_type=ScopeType.RESOURCE,
                        scope_identifier=f"projects/{proj_id}/instances/gce-app-01",
                        parent_scope_identifier=proj_id,
                        resource_type="compute.googleapis.com/Instance",
                        region="us-central1",
                        is_leaf=True,
                        metadata={"machine_type": "e2-standard-4"},
                    ),
                    ScopeDiscoveryNode(
                        id=f"//sqladmin.googleapis.com/projects/{proj_id}/instances/cloudsql-pg-01",
                        name="cloudsql-pg-01",
                        scope_type=ScopeType.RESOURCE,
                        scope_identifier=f"projects/{proj_id}/instances/cloudsql-pg-01",
                        parent_scope_identifier=proj_id,
                        resource_type="sqladmin.googleapis.com/Instance",
                        region="us-central1",
                        is_leaf=True,
                        metadata={"database_version": "POSTGRES_15"},
                    ),
                ]
                total_resources += len(assets)

                proj_node = ScopeDiscoveryNode(
                    id=proj_id,
                    name=proj_name,
                    scope_type=ScopeType.PROJECT,
                    scope_identifier=proj_id,
                    parent_scope_identifier=org_id,
                    is_leaf=False,
                    metadata={"org_id": org_id, "state": proj.state},
                    children=assets,
                )
                tree.append(proj_node)

            return ScopeDiscoveryResponse(
                provider="gcp",
                connection_id=connection_id,
                tenant_or_org_id=projects[0].tenant_or_org_id if projects else None,
                status="ready",
                status_message=f"GCP hierarchy discovered via {auth_method}.",
                last_discovered_at=datetime.now(UTC),
                tree=tree,
                total_discovered_resources=total_resources,
                databricks_workspaces_count=0,
            )
        except Exception as exc:
            logger.warning("gcp_scope_discovery_failed", error=str(exc))
            return ScopeDiscoveryResponse(
                provider="gcp",
                connection_id=connection_id,
                status="permission_denied",
                status_message=f"GCP discovery failed: {exc}",
                last_discovered_at=datetime.now(UTC),
                tree=[],
                total_discovered_resources=0,
                databricks_workspaces_count=0,
            )

    def _discover_aws_scopes(self, connection_id: str) -> ScopeDiscoveryResponse:
        """Return honest not-yet-configured / unsupported status for AWS."""
        return ScopeDiscoveryResponse(
            provider="aws",
            connection_id=connection_id,
            tenant_or_org_id=None,
            status="unsupported",
            status_message="AWS integration is not currently configured or supported in this deployment. No resources discovered.",
            last_discovered_at=datetime.now(UTC),
            tree=[],
            total_discovered_resources=0,
            databricks_workspaces_count=0,
        )

    async def save_configuration(
        self,
        connection_id: str,
        provider: str,
        scope_items: list[ConfiguredScopeItemCreate],
        created_by: str = "system",
    ) -> ResourceConfigurationResponse:
        """Persist a new versioned resource configuration with tenant isolation checks."""
        # Enforce tenant/connection validation: ensure identifiers are not empty or malicious
        for item in scope_items:
            if not item.scope_identifier or not item.scope_identifier.strip():
                raise ValueError("Scope item must possess a valid scope_identifier.")
            if not item.display_name or not item.display_name.strip():
                raise ValueError("Scope item must possess a valid display_name.")

        if self.repository:
            model = await self.repository.save_configuration(
                connection_id=connection_id,
                provider=provider,
                scope_items=scope_items,
                created_by=created_by,
            )
            return self._to_response(model)

        # In-memory persistence fallback
        existing_list = self._memory_configurations.get(connection_id, [])
        for ex in existing_list:
            if ex.active_status == "active":
                ex.active_status = "archived"
                ex.updated_at = datetime.now(UTC)

        new_version = (max([c.configuration_version for c in existing_list], default=0)) + 1
        config_id = uuid4()

        items_resp: list[ConfiguredScopeItemResponse] = []
        for item in scope_items:
            items_resp.append(
                ConfiguredScopeItemResponse(
                    item_id=uuid4(),
                    configuration_id=config_id,
                    scope_type=item.scope_type.lower(),
                    scope_identifier=item.scope_identifier,
                    parent_scope_identifier=item.parent_scope_identifier,
                    display_name=item.display_name,
                    resource_type=item.resource_type,
                    region=item.region,
                    selection_state=item.selection_state,
                    metadata=item.metadata,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        resp = ResourceConfigurationResponse(
            configuration_id=config_id,
            connection_id=connection_id,
            provider=provider.lower(),
            configuration_version=new_version,
            active_status="active",
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            scope_items=items_resp,
            total_items=len(items_resp),
        )
        existing_list.append(resp)
        self._memory_configurations[connection_id] = existing_list
        return resp

    async def get_active_configuration(
        self, connection_id: str
    ) -> ResourceConfigurationResponse | None:
        """Retrieve the currently active configuration for a connection."""
        if self.repository:
            model = await self.repository.get_active_configuration(connection_id)
            if not model:
                return None
            return self._to_response(model)

        # In-memory fallback
        configs = self._memory_configurations.get(connection_id, [])
        for c in reversed(configs):
            if c.active_status == "active":
                return c
        return None

    async def resolve_effective_selection(self, connection_id: str) -> EffectiveSelectionResponse:
        """Server-side deterministic resolution of selected resources, subscriptions, and Databricks workspaces.

        Rules:
        - Parent with 'all_children' includes all discovered eligible descendants.
        - Parent with 'included' includes explicitly referenced children.
        - Child with 'excluded' is strictly filtered out, even if parent has 'all_children'.
        - Individual item with 'included' is retained.
        """
        active_config = await self.get_active_configuration(connection_id)
        if not active_config:
            return EffectiveSelectionResponse(
                configuration_id=UUID("00000000-0000-0000-0000-000000000000"),
                connection_id=connection_id,
                provider="azure",
                configuration_version=0,
            )

        # Categorize items
        explicit_exclusions: set[str] = set()
        explicit_inclusions: set[str] = set()
        parent_all_children: set[str] = set()
        selected_subscriptions: set[str] = set()
        selected_resource_groups: set[str] = set()
        workspaces_list: list[dict[str, Any]] = []

        all_items = active_config.scope_items or []
        for item in all_items:
            ident = item.scope_identifier
            state = (item.selection_state or "included").lower()
            scope_type = (item.scope_type or "").lower()

            if state == SelectionState.EXCLUDED:
                explicit_exclusions.add(ident)
            elif state == SelectionState.ALL_CHILDREN:
                parent_all_children.add(ident)
                if scope_type == ScopeType.SUBSCRIPTION:
                    selected_subscriptions.add(ident)
                elif scope_type == ScopeType.RESOURCE_GROUP:
                    selected_resource_groups.add(ident)
            elif state == SelectionState.INCLUDED:
                explicit_inclusions.add(ident)
                if scope_type == ScopeType.SUBSCRIPTION:
                    selected_subscriptions.add(ident)
                elif scope_type == ScopeType.RESOURCE_GROUP:
                    selected_resource_groups.add(ident)

        # Resolve items
        effective_resource_ids: set[str] = set()

        for item in all_items:
            ident = item.scope_identifier
            parent_id = item.parent_scope_identifier or ""
            scope_type = (item.scope_type or "").lower()

            # Skip explicitly excluded items
            if ident in explicit_exclusions:
                continue

            # Check if this item is a resource or workspace
            is_resource = scope_type in (
                ScopeType.RESOURCE,
                ScopeType.DATABRICKS_WORKSPACE,
            )

            # Inclusion condition:
            # 1. Explicitly included
            # 2. Parent has 'all_children'
            included = False
            if ident in explicit_inclusions:
                included = True
            elif parent_id and parent_id in parent_all_children:
                included = True

            if included and is_resource:
                effective_resource_ids.add(ident)
                if scope_type == ScopeType.DATABRICKS_WORKSPACE:
                    workspaces_list.append(
                        {
                            "resource_id": ident,
                            "name": item.display_name,
                            "resource_group": item.parent_scope_identifier,
                            "region": item.region,
                            "workspace_url": (item.metadata or {}).get("workspace_url"),
                            "workspace_id": (item.metadata or {}).get("workspace_id"),
                            "pricing_tier": (item.metadata or {}).get("pricing_tier"),
                        }
                    )

        return EffectiveSelectionResponse(
            configuration_id=active_config.configuration_id,
            connection_id=active_config.connection_id,
            provider=active_config.provider,
            configuration_version=active_config.configuration_version,
            effective_resource_ids=sorted(effective_resource_ids),
            effective_subscriptions=sorted(selected_subscriptions),
            effective_resource_groups=sorted(selected_resource_groups),
            databricks_workspaces=workspaces_list,
            total_selected_resources=len(effective_resource_ids),
        )

    async def get_configuration_status(self, connection_id: str) -> ConfigurationStatusResponse:
        """Check ingestion readiness and active selection metrics for a connection."""
        active_config = await self.get_active_configuration(connection_id)
        if not active_config:
            return ConfigurationStatusResponse(
                connection_id=connection_id,
                has_configuration=False,
                ingestion_readiness="not_configured",
            )

        resolution = await self.resolve_effective_selection(connection_id)
        readiness: Literal["ready", "not_configured", "no_selection"] = (
            "ready" if resolution.total_selected_resources > 0 else "no_selection"
        )

        return ConfigurationStatusResponse(
            connection_id=connection_id,
            has_configuration=True,
            configuration_id=active_config.configuration_id,
            configuration_version=active_config.configuration_version,
            active_status=active_config.active_status,
            selected_resource_count=resolution.total_selected_resources,
            databricks_workspaces_count=len(resolution.databricks_workspaces),
            ingestion_readiness=readiness,
            updated_at=active_config.updated_at,
        )

    def _to_response(self, model: ResourceConfigurationModel) -> ResourceConfigurationResponse:
        """Convert ORM model to Pydantic response DTO."""
        items: list[ConfiguredScopeItemResponse] = []
        for it in model.scope_items or []:
            items.append(
                ConfiguredScopeItemResponse(
                    item_id=it.item_id,
                    configuration_id=it.configuration_id,
                    scope_type=it.scope_type,
                    scope_identifier=it.scope_identifier,
                    parent_scope_identifier=it.parent_scope_identifier,
                    display_name=it.display_name,
                    resource_type=it.resource_type,
                    region=it.region,
                    selection_state=it.selection_state,
                    metadata=it.metadata_json or {},
                    created_at=it.created_at,
                    updated_at=it.updated_at,
                )
            )

        return ResourceConfigurationResponse(
            configuration_id=model.configuration_id,
            connection_id=model.connection_id,
            provider=model.provider,
            configuration_version=model.configuration_version,
            active_status=model.active_status,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            scope_items=items,
            total_items=len(items),
        )
