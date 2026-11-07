"""Permission-aware live Databricks workspace discovery service.

Discovers compute, warehouses, workflows, pipelines, model serving, Unity Catalog, and apps.
Each discovery category evaluates independently:
- AVAILABLE
- PERMISSION_DENIED
- UNSUPPORTED
- NO_RESOURCES_FOUND
- CONNECTION_ERROR
- NOT_YET_DISCOVERED
Failure in one category does NOT prevent discovery in other categories.
Zero synthetic production data; operates strictly with real Databricks SDK responses.
"""

from datetime import UTC, datetime

import structlog
from databricks.sdk import WorkspaceClient

from cloud_recommender.schemas.databricks import (
    CategoryDiscoveryResult,
    CategoryDiscoveryStatus,
    DatabricksCloud,
    DatabricksWorkspaceDiscoveryResponse,
    DiscoveredResourceItem,
)
from cloud_recommender.services.databricks.auth import DatabricksAuthService

logger = structlog.get_logger(__name__)


class DatabricksDiscoveryService:
    """Service discovering multi-category assets across Azure and AWS Databricks workspaces."""

    def __init__(self, auth_service: DatabricksAuthService | None = None) -> None:
        self.auth_service = auth_service or DatabricksAuthService()

    async def discover_workspace(
        self,
        connection_id: str,
        host: str,
        cloud: DatabricksCloud,
        workspace_id: str,
        workspace_name: str,
        profile: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> DatabricksWorkspaceDiscoveryResponse:
        """Execute independent category discovery against a Databricks workspace."""
        now = datetime.now(UTC)
        client: WorkspaceClient | None = None
        connect_error: str | None = None

        try:
            client_res = self.auth_service.create_workspace_client(
                host=host,
                cloud=cloud.value,
                profile=profile,
                client_id=client_id,
                client_secret=client_secret,
            )
            if isinstance(client_res, tuple):
                client = client_res[0]
            else:
                client = client_res
        except Exception as exc:
            connect_error = self.auth_service.scrub_sensitive(str(exc))
            logger.warning("databricks_client_init_failed", host=host, error=connect_error)

        categories: dict[str, CategoryDiscoveryResult] = {}
        all_resources: list[DiscoveredResourceItem] = []

        # If client initialization completely failed, mark all categories with CONNECTION_ERROR
        if not client or connect_error:
            for cat_name in (
                "workspace",
                "clusters",
                "warehouses",
                "jobs",
                "pipelines",
                "model_serving",
                "unity_catalog",
                "apps",
            ):
                categories[cat_name] = CategoryDiscoveryResult(
                    category=cat_name,
                    status=CategoryDiscoveryStatus.CONNECTION_ERROR,
                    resource_count=0,
                    error_message=connect_error
                    or "Failed to initialize Databricks workspace client.",
                    discovered_at=now,
                )
            return DatabricksWorkspaceDiscoveryResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=host,
                cloud=cloud,
                overall_status="failed",
                categories=categories,
                resources=[],
                total_resources_count=0,
                discovered_at=now,
            )

        # Category 1: Workspace Metadata
        cat_ws, res_ws = self._discover_workspace_metadata(
            client, workspace_id, workspace_name, host, cloud, now
        )
        categories["workspace"] = cat_ws
        all_resources.extend(res_ws)

        # Category 2: Compute Clusters
        cat_cl, res_cl = self._discover_clusters(client, workspace_id, now)
        categories["clusters"] = cat_cl
        all_resources.extend(res_cl)

        # Category 3: SQL Warehouses
        cat_wh, res_wh = self._discover_warehouses(client, workspace_id, now)
        categories["warehouses"] = cat_wh
        all_resources.extend(res_wh)

        # Category 4: Jobs and Workflows
        cat_jb, res_jb = self._discover_jobs(client, workspace_id, now)
        categories["jobs"] = cat_jb
        all_resources.extend(res_jb)

        # Category 5: Lakeflow / DLT Pipelines
        cat_pl, res_pl = self._discover_pipelines(client, workspace_id, now)
        categories["pipelines"] = cat_pl
        all_resources.extend(res_pl)

        # Category 6: Model Serving
        cat_ms, res_ms = self._discover_model_serving(client, workspace_id, now)
        categories["model_serving"] = cat_ms
        all_resources.extend(res_ms)

        # Category 7: Unity Catalog
        cat_uc, res_uc = self._discover_unity_catalog(client, workspace_id, now)
        categories["unity_catalog"] = cat_uc
        all_resources.extend(res_uc)

        # Category 8: Databricks Apps
        cat_ap, res_ap = self._discover_apps(client, workspace_id, now)
        categories["apps"] = cat_ap
        all_resources.extend(res_ap)

        # Determine overall discovery status
        failed_cats = sum(
            1
            for c in categories.values()
            if c.status
            in (CategoryDiscoveryStatus.CONNECTION_ERROR, CategoryDiscoveryStatus.PERMISSION_DENIED)
        )
        success_cats = sum(
            1
            for c in categories.values()
            if c.status
            in (CategoryDiscoveryStatus.AVAILABLE, CategoryDiscoveryStatus.NO_RESOURCES_FOUND)
        )

        if failed_cats == 0:
            overall = "completed"
        elif success_cats > 0:
            overall = "partial_failure"
        else:
            overall = "failed"

        return DatabricksWorkspaceDiscoveryResponse(
            connection_id=connection_id,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            workspace_url=host,
            cloud=cloud,
            overall_status=overall,
            categories=categories,
            resources=all_resources,
            total_resources_count=len(all_resources),
            discovered_at=now,
        )

    def _classify_error(self, exc: Exception) -> tuple[CategoryDiscoveryStatus, str]:
        """Map exception to CategoryDiscoveryStatus and scrubbed error string."""
        raw_msg = self.auth_service.scrub_sensitive(str(exc))
        lowered = raw_msg.lower()

        if (
            "403" in lowered
            or "permission" in lowered
            or "unauthorized" in lowered
            or "denied" in lowered
        ):
            return CategoryDiscoveryStatus.PERMISSION_DENIED, f"Permission denied: {raw_msg}"
        if (
            "404" in lowered
            or "not found" in lowered
            or "not enabled" in lowered
            or "unsupported" in lowered
        ):
            return (
                CategoryDiscoveryStatus.UNSUPPORTED,
                f"Feature not enabled or unsupported: {raw_msg}",
            )
        return CategoryDiscoveryStatus.CONNECTION_ERROR, f"API query error: {raw_msg}"

    def _discover_workspace_metadata(
        self,
        client: WorkspaceClient,
        workspace_id: str,
        workspace_name: str,
        host: str,
        cloud: DatabricksCloud,
        now: datetime,
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Verify basic workspace identity and current user."""
        try:
            me = client.current_user.me()
            user_principal = me.user_name or me.display_name or "authenticated_user"
            res = DiscoveredResourceItem(
                id=workspace_id,
                name=workspace_name,
                resource_type="workspace",
                workspace_id=workspace_id,
                status="ONLINE",
                creator=user_principal,
                source_api="databricks-sdk/current_user",
                metadata={"host": host, "cloud": cloud.value, "user": user_principal},
                discovered_at=now,
            )
            return (
                CategoryDiscoveryResult(
                    category="workspace",
                    status=CategoryDiscoveryStatus.AVAILABLE,
                    resource_count=1,
                    discovered_at=now,
                ),
                [res],
            )
        except Exception as exc:
            status, err = self._classify_error(exc)
            return CategoryDiscoveryResult(
                category="workspace", status=status, error_message=err, discovered_at=now
            ), []

    def _discover_clusters(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract compute clusters."""
        try:
            items: list[DiscoveredResourceItem] = []
            clusters = list(client.clusters.list())
            for cl in clusters:
                c_id = cl.cluster_id or "unknown-cluster"
                c_name = cl.cluster_name or c_id
                c_state = cl.state.value if cl.state else "UNKNOWN"
                autoscale = (
                    {
                        "min_workers": cl.autoscale.min_workers,
                        "max_workers": cl.autoscale.max_workers,
                    }
                    if cl.autoscale
                    else None
                )
                items.append(
                    DiscoveredResourceItem(
                        id=c_id,
                        name=c_name,
                        resource_type="cluster",
                        workspace_id=workspace_id,
                        status=c_state,
                        creator=cl.creator_user_name,
                        source_api="databricks-sdk/clusters.list",
                        metadata={
                            "spark_version": cl.spark_version,
                            "node_type_id": cl.node_type_id,
                            "driver_node_type_id": cl.driver_node_type_id,
                            "num_workers": cl.num_workers,
                            "autoscale": autoscale,
                        },
                        discovered_at=now,
                    )
                )
            status = (
                CategoryDiscoveryStatus.AVAILABLE
                if items
                else CategoryDiscoveryStatus.NO_RESOURCES_FOUND
            )
            return CategoryDiscoveryResult(
                category="clusters", status=status, resource_count=len(items), discovered_at=now
            ), items
        except Exception as exc:
            status, err = self._classify_error(exc)
            return CategoryDiscoveryResult(
                category="clusters", status=status, error_message=err, discovered_at=now
            ), []

    def _discover_warehouses(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract SQL Warehouses."""
        try:
            items: list[DiscoveredResourceItem] = []
            warehouses = list(client.warehouses.list())
            for wh in warehouses:
                wh_id = wh.id or "unknown-warehouse"
                wh_name = wh.name or wh_id
                wh_state = wh.state.value if wh.state else "UNKNOWN"
                items.append(
                    DiscoveredResourceItem(
                        id=wh_id,
                        name=wh_name,
                        resource_type="warehouse",
                        workspace_id=workspace_id,
                        status=wh_state,
                        creator=wh.creator_name,
                        source_api="databricks-sdk/warehouses.list",
                        metadata={
                            "cluster_size": wh.cluster_size,
                            "auto_stop_mins": wh.auto_stop_mins,
                            "num_clusters": wh.num_clusters,
                            "warehouse_type": getattr(wh, "warehouse_type", None),
                        },
                        discovered_at=now,
                    )
                )
            status = (
                CategoryDiscoveryStatus.AVAILABLE
                if items
                else CategoryDiscoveryStatus.NO_RESOURCES_FOUND
            )
            return CategoryDiscoveryResult(
                category="warehouses", status=status, resource_count=len(items), discovered_at=now
            ), items
        except Exception as exc:
            status, err = self._classify_error(exc)
            return CategoryDiscoveryResult(
                category="warehouses", status=status, error_message=err, discovered_at=now
            ), []

    def _discover_jobs(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract Jobs and Workflows."""
        try:
            items: list[DiscoveredResourceItem] = []
            jobs = list(client.jobs.list(limit=50))
            for j in jobs:
                j_id = str(j.job_id)
                j_name = j.settings.name if j.settings and j.settings.name else f"job-{j_id}"
                task_count = len(j.settings.tasks) if j.settings and j.settings.tasks else 0
                cron = (
                    j.settings.schedule.quartz_cron_expression
                    if j.settings and j.settings.schedule
                    else None
                )
                items.append(
                    DiscoveredResourceItem(
                        id=j_id,
                        name=j_name,
                        resource_type="job",
                        workspace_id=workspace_id,
                        status="SCHEDULED" if cron else "MANUAL",
                        creator=j.creator_user_name,
                        source_api="databricks-sdk/jobs.list",
                        metadata={"tasks_count": task_count, "cron_schedule": cron},
                        discovered_at=now,
                    )
                )
            status = (
                CategoryDiscoveryStatus.AVAILABLE
                if items
                else CategoryDiscoveryStatus.NO_RESOURCES_FOUND
            )
            return CategoryDiscoveryResult(
                category="jobs", status=status, resource_count=len(items), discovered_at=now
            ), items
        except Exception as exc:
            status, err = self._classify_error(exc)
            return CategoryDiscoveryResult(
                category="jobs", status=status, error_message=err, discovered_at=now
            ), []

    def _discover_pipelines(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract Lakeflow / DLT Pipelines."""
        try:
            items: list[DiscoveredResourceItem] = []
            pipelines = list(client.pipelines.list_pipelines(max_results=50))
            for p in pipelines:
                p_id = p.pipeline_id or "unknown-pipeline"
                p_name = p.name or p_id
                p_state = p.state.value if p.state else "UNKNOWN"
                items.append(
                    DiscoveredResourceItem(
                        id=p_id,
                        name=p_name,
                        resource_type="pipeline",
                        workspace_id=workspace_id,
                        status=p_state,
                        creator=None,
                        source_api="databricks-sdk/pipelines.list_pipelines",
                        metadata={},
                        discovered_at=now,
                    )
                )
            status = (
                CategoryDiscoveryStatus.AVAILABLE
                if items
                else CategoryDiscoveryStatus.NO_RESOURCES_FOUND
            )
            return CategoryDiscoveryResult(
                category="pipelines", status=status, resource_count=len(items), discovered_at=now
            ), items
        except Exception as exc:
            status, err = self._classify_error(exc)
            return CategoryDiscoveryResult(
                category="pipelines", status=status, error_message=err, discovered_at=now
            ), []

    def _discover_model_serving(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract Model Serving endpoints."""
        try:
            items: list[DiscoveredResourceItem] = []
            endpoints = list(client.serving_endpoints.list())
            for ep in endpoints:
                ep_name = ep.name or "unknown-endpoint"
                ep_state = (
                    ep.state.config_update.value
                    if ep.state and ep.state.config_update
                    else "UNKNOWN"
                )
                items.append(
                    DiscoveredResourceItem(
                        id=ep_name,
                        name=ep_name,
                        resource_type="serving_endpoint",
                        workspace_id=workspace_id,
                        status=ep_state,
                        creator=ep.creator,
                        source_api="databricks-sdk/serving_endpoints.list",
                        metadata={},
                        discovered_at=now,
                    )
                )
            status = (
                CategoryDiscoveryStatus.AVAILABLE
                if items
                else CategoryDiscoveryStatus.NO_RESOURCES_FOUND
            )
            return CategoryDiscoveryResult(
                category="model_serving",
                status=status,
                resource_count=len(items),
                discovered_at=now,
            ), items
        except Exception as exc:
            status, err = self._classify_error(exc)
            return CategoryDiscoveryResult(
                category="model_serving", status=status, error_message=err, discovered_at=now
            ), []

    def _discover_unity_catalog(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract Unity Catalog catalogs."""
        try:
            items: list[DiscoveredResourceItem] = []
            catalogs = list(client.catalogs.list())
            for cat in catalogs:
                c_name = cat.name or "unknown-catalog"
                items.append(
                    DiscoveredResourceItem(
                        id=c_name,
                        name=c_name,
                        resource_type="catalog",
                        workspace_id=workspace_id,
                        status="ACTIVE",
                        creator=cat.owner,
                        source_api="databricks-sdk/catalogs.list",
                        metadata={"comment": cat.comment, "owner": cat.owner},
                        discovered_at=now,
                    )
                )
            status = (
                CategoryDiscoveryStatus.AVAILABLE
                if items
                else CategoryDiscoveryStatus.NO_RESOURCES_FOUND
            )
            return CategoryDiscoveryResult(
                category="unity_catalog",
                status=status,
                resource_count=len(items),
                discovered_at=now,
            ), items
        except Exception as exc:
            status, err = self._classify_error(exc)
            return CategoryDiscoveryResult(
                category="unity_catalog", status=status, error_message=err, discovered_at=now
            ), []

    def _discover_apps(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract Databricks Apps."""
        try:
            items: list[DiscoveredResourceItem] = []
            apps = list(client.apps.list())
            for app in apps:
                a_name = app.name or "unknown-app"
                a_state = (
                    app.compute_status.state.value
                    if app.compute_status and app.compute_status.state
                    else "ACTIVE"
                )
                items.append(
                    DiscoveredResourceItem(
                        id=a_name,
                        name=a_name,
                        resource_type="app",
                        workspace_id=workspace_id,
                        status=a_state,
                        creator=app.creator,
                        source_api="databricks-sdk/apps.list",
                        metadata={"url": app.url if hasattr(app, "url") else None},
                        discovered_at=now,
                    )
                )
            status = (
                CategoryDiscoveryStatus.AVAILABLE
                if items
                else CategoryDiscoveryStatus.NO_RESOURCES_FOUND
            )
            return CategoryDiscoveryResult(
                category="apps", status=status, resource_count=len(items), discovered_at=now
            ), items
        except Exception as exc:
            status, err = self._classify_error(exc)
            return CategoryDiscoveryResult(
                category="apps", status=status, error_message=err, discovered_at=now
            ), []
