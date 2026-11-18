"""Databricks workspace connection management and discovery orchestrator."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import structlog

from cloud_recommender.core.config import Settings, reload_settings
from cloud_recommender.schemas.databricks import (
    CategoryDiscoveryStatus,
    DatabricksCategoryPageResponse,
    DatabricksCloud,
    DatabricksConnectionHealthResponse,
    DatabricksConnectionResponse,
    DatabricksConnectionStatus,
    DatabricksConnectionTestResponse,
    DatabricksResourceState,
    DatabricksWorkspaceDiscoveryResponse,
    LiveQueryHistoryResponse,
    SqlWarehouseStatus,
    SystemTablesMetadataResponse,
    UnityCatalogMetadataResponse,
    WorkspaceConnectionState,
)
from cloud_recommender.services.databricks.auth import (
    DatabricksAuthService,
    classify_databricks_error,
)
from cloud_recommender.services.databricks.discovery_service import (
    DatabricksDiscoveryService,
)

logger = structlog.get_logger(__name__)


def now_utc() -> datetime:
    return datetime.now(UTC)


def connection_state_for(conn: dict[str, Any]) -> WorkspaceConnectionState:
    """Map the registry status to the single normalized state shown everywhere."""
    if not conn.get("workspace_url"):
        return WorkspaceConnectionState.NOT_CONFIGURED
    status = conn.get("status")
    if status == DatabricksConnectionStatus.CONNECTED:
        return WorkspaceConnectionState.CONNECTED
    if status == DatabricksConnectionStatus.AUTH_FAILED:
        return WorkspaceConnectionState.AUTHENTICATION_REQUIRED
    if status == DatabricksConnectionStatus.PERMISSION_DENIED:
        return WorkspaceConnectionState.ACCESS_DENIED
    if status == DatabricksConnectionStatus.CONNECTION_ERROR:
        return WorkspaceConnectionState.ERROR
    return WorkspaceConnectionState.DISCONNECTED


class DatabricksWorkspaceService:
    """Service managing Databricks connections, validation, and discovery cache."""

    # Process-shared state keyed cleanly by connection_id for multi-workspace isolation
    _shared_workspaces: dict[str, dict[str, Any]] = {}
    _discovery_cache: dict[str, DatabricksWorkspaceDiscoveryResponse] = {}
    _uc_cache: dict[str, UnityCatalogMetadataResponse] = {}
    _system_tables_cache: dict[str, SystemTablesMetadataResponse] = {}
    # Per-connection refresh bookkeeping: last_attempt_at / last_success_at / last_error
    _refresh_state: dict[str, dict[str, Any]] = {}

    def __init__(
        self,
        auth_service: DatabricksAuthService | None = None,
        discovery_service: DatabricksDiscoveryService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._explicit_settings = settings is not None
        self.settings = settings or reload_settings()
        self.auth_service = auth_service or DatabricksAuthService(settings=self.settings)
        self.discovery_service = discovery_service or DatabricksDiscoveryService(
            auth_service=self.auth_service
        )
        self._workspaces = self._build_workspace_registry(self.settings)

    def _effective_auth_method_label(
        self,
        settings: Settings,
        profile_name: str | None,
        environment: str = "development",
    ) -> str:
        """Describe configured auth mode without exposing credentials."""
        if environment in ("production", "prod"):
            return "oauth-m2m (service principal)"
        auth_type = (settings.databricks_auth_type or "").strip().lower()
        if auth_type in ("oauth", "oauth-m2m"):
            return "oauth-m2m (service principal)"
        if profile_name:
            return f"azure-cli / profile:{profile_name}"
        return "azure-cli (delegated)"

    def _build_workspace_registry(self, settings: Settings) -> dict[str, dict[str, Any]]:
        """Build configuration-driven workspace registry supporting Dev, Prod, and custom entries."""
        dev_id = (
            settings.databricks_dev_workspace_id
            or settings.databricks_workspace_id
            or "642006393507276"
        ).strip()
        dev_host = (
            (
                settings.databricks_dev_host
                or settings.databricks_host
                or "https://adb-642006393507276.16.azuredatabricks.net"
            )
            .strip()
            .rstrip("/")
        )
        dev_warehouse = (
            settings.databricks_dev_warehouse_id
            or settings.databricks_warehouse_id
            or "05ed10a52697a344"
        ).strip()

        registry: dict[str, dict[str, Any]] = {
            "databricks-azure-dev": {
                "connection_id": "databricks-azure-dev",
                "workspace_id": dev_id,
                "workspace_name": "Azure Databricks Dev",
                "workspace_url": dev_host,
                "cloud": DatabricksCloud.AZURE,
                "region": "northcentralus",
                "auth_method": self._effective_auth_method_label(
                    settings, settings.databricks_profile, environment="development"
                ),
                "profile_name": settings.databricks_profile,
                "warehouse_id": dev_warehouse or None,
                "environment": "development",
                "status": DatabricksConnectionStatus.READY_TO_CONNECT,
                "last_connected_at": None,
                "last_error": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        }

        prod_id = (settings.databricks_prod_workspace_id or "").strip()
        prod_host = (settings.databricks_prod_host or "").strip().rstrip("/")
        if prod_id and prod_host:
            prod_wh = (settings.databricks_prod_warehouse_id or "").strip() or None
            registry["databricks-azure-prod"] = {
                "connection_id": "databricks-azure-prod",
                "workspace_id": prod_id,
                "workspace_name": "Azure Databricks Prod",
                "workspace_url": prod_host,
                "cloud": DatabricksCloud.AZURE,
                "region": "eastus",
                "auth_method": self._effective_auth_method_label(
                    settings, settings.databricks_prod_profile, environment="production"
                ),
                "profile_name": settings.databricks_prod_profile,
                "warehouse_id": prod_wh,
                "environment": "production",
                "status": DatabricksConnectionStatus.READY_TO_CONNECT,
                "last_connected_at": None,
                "last_error": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }

        registry["databricks-finops-dev"] = {
            "connection_id": "databricks-finops-dev",
            "workspace_id": "2250283018608626",
            "workspace_name": "AWS Databricks FinOps",
            "workspace_url": "https://dbc-8e061b63-c3bf.cloud.databricks.com",
            "cloud": DatabricksCloud.AWS,
            "region": "us-east-1",
            "auth_method": "cli-profile / oauth-sp",
            "profile_name": "finops-dev",
            "warehouse_id": None,
            "environment": "development",
            "status": DatabricksConnectionStatus.READY_TO_CONNECT,
            "last_connected_at": None,
            "last_error": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        raw_extra = (settings.databricks_workspaces_json or "").strip()
        if raw_extra:
            try:
                extra_entries = json.loads(raw_extra)
                if isinstance(extra_entries, list):
                    for item in extra_entries:
                        if not isinstance(item, dict):
                            continue
                        cid = str(item.get("connection_id") or "").strip()
                        wid = str(item.get("workspace_id") or "").strip()
                        wurl = str(item.get("workspace_url") or "").strip().rstrip("/")
                        if not (cid and wid and wurl):
                            continue
                        cloud_val = str(item.get("cloud") or "azure").lower()
                        registry[cid] = {
                            "connection_id": cid,
                            "workspace_id": wid,
                            "workspace_name": str(item.get("workspace_name") or cid),
                            "workspace_url": wurl,
                            "cloud": DatabricksCloud(cloud_val)
                            if cloud_val in ("azure", "aws", "gcp")
                            else DatabricksCloud.AZURE,
                            "region": item.get("region"),
                            "auth_method": str(
                                item.get("auth_method")
                                or self._effective_auth_method_label(
                                    settings, item.get("profile_name")
                                )
                            ),
                            "profile_name": item.get("profile_name"),
                            "warehouse_id": item.get("warehouse_id"),
                            "environment": item.get("environment"),
                            "status": DatabricksConnectionStatus.READY_TO_CONNECT,
                            "last_connected_at": None,
                            "last_error": None,
                            "created_at": datetime.now(UTC),
                            "updated_at": datetime.now(UTC),
                        }
            except Exception as exc:
                logger.warning("invalid_databricks_workspaces_json", error=str(exc))

        # One process-wide mutable entry per connection. Every service instance (the API creates
        # one per request) must mutate the SAME dict, otherwise a status written by a long-running
        # discovery is lost when the next instance replaces the shared entry with a copy.
        live_keys = {"status", "last_connected_at", "last_error", "updated_at", "created_at"}
        for cid, entry in list(registry.items()):
            prev = self._shared_workspaces.get(cid)
            if (
                prev
                and prev.get("workspace_id") == entry["workspace_id"]
                and prev.get("workspace_url") == entry["workspace_url"]
            ):
                for key, value in entry.items():
                    if key not in live_keys:
                        prev[key] = value  # refresh static configuration in place
                registry[cid] = prev
            else:
                self._shared_workspaces[cid] = entry

        return registry

    def list_connections(self) -> list[DatabricksConnectionResponse]:
        """List all configured Databricks workspace connections."""
        return [DatabricksConnectionResponse(**data) for data in self._workspaces.values()]

    def get_connection(self, connection_id: str) -> DatabricksConnectionResponse | None:
        """Fetch connection metadata by connection_id or workspace_id."""
        data = self._workspaces.get(connection_id)
        if not data:
            for candidate in self._workspaces.values():
                if candidate["workspace_id"] == connection_id:
                    data = candidate
                    break
        return DatabricksConnectionResponse(**data) if data else None

    def _resolve_raw_connection(self, identifier: str) -> dict[str, Any] | None:
        """Resolve mutable connection dict by connection_id or workspace_id."""
        if identifier in self._workspaces:
            return self._workspaces[identifier]
        for candidate in self._workspaces.values():
            if candidate["workspace_id"] == identifier:
                return candidate
        return None

    def _status_from_error_text(self, error_text: str) -> DatabricksConnectionStatus:
        """Map an error diagnostic string to exact DatabricksConnectionStatus."""
        kind = classify_databricks_error(error_text)
        if kind == "permission_denied":
            return DatabricksConnectionStatus.PERMISSION_DENIED
        if kind == "auth_failed":
            return DatabricksConnectionStatus.AUTH_FAILED
        return DatabricksConnectionStatus.CONNECTION_ERROR

    async def test_connection(self, connection_id: str) -> DatabricksConnectionTestResponse:
        """Validate live credentials and connectivity against the target Databricks workspace."""
        conn = self._resolve_raw_connection(connection_id)
        now = datetime.now(UTC)
        if not conn:
            return DatabricksConnectionTestResponse(
                connection_id=connection_id,
                workspace_id="unknown",
                workspace_url="",
                success=False,
                status=DatabricksConnectionStatus.CONNECTION_ERROR,
                details=f"Databricks connection '{connection_id}' not found.",
                tested_at=now,
            )

        success, details, username = await asyncio.to_thread(
            self.auth_service.test_connection,
            host=conn["workspace_url"],
            cloud=conn["cloud"].value,
            profile=conn["profile_name"],
            environment=conn.get("environment"),
        )

        conn["updated_at"] = now
        if success:
            conn["status"] = DatabricksConnectionStatus.CONNECTED
            conn["last_connected_at"] = now
            conn["last_error"] = None
        else:
            conn["status"] = self._status_from_error_text(details)
            conn["last_error"] = details

        return DatabricksConnectionTestResponse(
            connection_id=conn["connection_id"],
            workspace_id=conn["workspace_id"],
            workspace_url=conn["workspace_url"],
            success=success,
            status=conn["status"],
            current_user=username,
            details=details,
            tested_at=now,
        )

    async def get_or_discover_workspace(
        self, connection_id: str, force_refresh: bool = False, keep_metadata: bool = False
    ) -> DatabricksWorkspaceDiscoveryResponse:
        """Retrieve cached discovery or execute fresh live workspace discovery."""
        conn = self._resolve_raw_connection(connection_id)
        now = datetime.now(UTC)
        if not conn:
            return DatabricksWorkspaceDiscoveryResponse(
                connection_id=connection_id,
                workspace_id="unknown",
                workspace_name="Unknown Workspace",
                workspace_url="",
                cloud=DatabricksCloud.AZURE,
                overall_status="failed",
                categories={},
                resources=[],
                total_resources_count=0,
                discovered_at=now,
            )

        canonical_cid = str(conn["connection_id"])
        if force_refresh:
            if not keep_metadata:
                self._uc_cache.pop(canonical_cid, None)
                self._system_tables_cache.pop(canonical_cid, None)
        elif canonical_cid in self._discovery_cache:
            return self._discovery_cache[canonical_cid]

        resp = await self.discovery_service.discover_workspace(
            connection_id=canonical_cid,
            host=conn["workspace_url"],
            cloud=conn["cloud"],
            workspace_id=conn["workspace_id"],
            workspace_name=conn["workspace_name"],
            profile=conn["profile_name"],
            environment=conn.get("environment"),
        )

        # Update connection state based on discovery outcome without masking auth/permission failures
        conn["updated_at"] = now
        ws_cat = resp.categories.get("workspace")
        ws_err = ws_cat.error_message if ws_cat else None

        if resp.overall_status in ("completed", "partial_failure"):
            conn["status"] = DatabricksConnectionStatus.CONNECTED
            conn["last_connected_at"] = now
            conn["last_error"] = None
        else:
            first_err = ws_err or next(
                (c.error_message for c in resp.categories.values() if c.error_message),
                "Workspace discovery failed.",
            )
            if ws_cat and ws_cat.status == CategoryDiscoveryStatus.AUTH_FAILED:
                conn["status"] = DatabricksConnectionStatus.AUTH_FAILED
            elif ws_cat and ws_cat.status == CategoryDiscoveryStatus.PERMISSION_DENIED:
                conn["status"] = DatabricksConnectionStatus.PERMISSION_DENIED
            else:
                conn["status"] = self._status_from_error_text(first_err)
            conn["last_error"] = first_err

        state = self._refresh_state.setdefault(canonical_cid, {})
        state["last_attempt_at"] = now
        previous = self._discovery_cache.get(canonical_cid)
        if resp.overall_status == "failed":
            state["last_error"] = conn.get("last_error") or "Workspace discovery failed."
            if previous is not None and previous.overall_status != "failed":
                # Never replace a good inventory with an empty failed one: keep it, flag it stale.
                return previous
        else:
            state["last_success_at"] = resp.discovered_at
            state["last_error"] = None
        self._discovery_cache[canonical_cid] = resp
        return resp

    async def get_health(self, connection_id: str) -> DatabricksConnectionHealthResponse:
        """Return comprehensive health, permissions, and discovery summary for a connection."""
        conn = self._resolve_raw_connection(connection_id)
        if not conn:
            return DatabricksConnectionHealthResponse(
                connection_id=connection_id,
                workspace_id="unknown",
                cloud=DatabricksCloud.AZURE,
                status=DatabricksConnectionStatus.CONNECTION_ERROR,
                last_error=f"Connection ID '{connection_id}' not recognized.",
                limitations=["Connection ID not recognized."],
            )

        canonical_cid = str(conn["connection_id"])
        discovery = await self.get_or_discover_workspace(canonical_cid, force_refresh=False)
        cats_summary = {k: v.status for k, v in discovery.categories.items()}
        counts: dict[str, int] = {}
        for r in discovery.resources:
            counts[r.resource_type] = counts.get(r.resource_type, 0) + 1

        capabilities = [
            f"category:{k}"
            for k, v in discovery.categories.items()
            if v.status
            in (CategoryDiscoveryStatus.AVAILABLE, CategoryDiscoveryStatus.NO_RESOURCES_FOUND)
        ]
        limitations = [
            f"{k}: {v.error_message}" for k, v in discovery.categories.items() if v.error_message
        ]

        # Extract current user from workspace metadata item
        auth_user = None
        for r in discovery.resources:
            if r.resource_type == "workspace" and r.creator:
                auth_user = r.creator
                break

        refresh = self._refresh_state.get(canonical_cid, {})
        interval = max(int(self.settings.databricks_inventory_refresh_seconds), 1)
        last_ok = refresh.get("last_success_at") or (
            discovery.discovered_at if discovery.overall_status != "failed" else None
        )
        stale = bool(refresh.get("last_error")) or (
            last_ok is not None and (now_utc() - last_ok).total_seconds() > interval * 3
        )
        warehouses = [r for r in discovery.resources if r.resource_type == "warehouse"]
        target_wh = next(
            (w for w in warehouses if w.id == conn.get("warehouse_id")),
            warehouses[0] if warehouses else None,
        )
        sql_wh = SqlWarehouseStatus(
            warehouse_id=target_wh.id if target_wh else conn.get("warehouse_id"),
            warehouse_name=target_wh.name if target_wh else None,
            state=target_wh.status if target_wh else None,
            sql_available=bool(target_wh and target_wh.status == "RUNNING"),
            message=(
                "SQL warehouse is running."
                if target_wh and target_wh.status == "RUNNING"
                else f"SQL warehouse is {target_wh.status if target_wh else 'not discovered'}; "
                "it is never started automatically and requires explicit approval."
            ),
        )
        return DatabricksConnectionHealthResponse(
            connection_id=canonical_cid,
            workspace_id=conn["workspace_id"],
            cloud=conn["cloud"],
            status=conn["status"],
            connection_state=connection_state_for(conn),
            workspace_name=conn.get("workspace_name"),
            workspace_url=conn.get("workspace_url"),
            environment=conn.get("environment"),
            last_connected_at=conn.get("last_connected_at"),
            last_discovery_at=last_ok,
            last_discovery_attempt_at=refresh.get("last_attempt_at"),
            discovery_stale=stale,
            refresh_interval_seconds=interval,
            sql_warehouse=sql_wh,
            authenticated_user=auth_user,
            auth_method=conn["auth_method"],
            last_error=conn.get("last_error"),
            last_verified_at=conn["last_connected_at"],
            categories_summary=cats_summary,
            resource_counts_by_type=counts,
            capabilities=capabilities,
            limitations=limitations,
        )

    async def get_category_resources(
        self,
        connection_id: str,
        category: str,
        limit: int = 50,
        offset: int = 0,
        force_refresh: bool = False,
        job_id: int | None = None,
        page_token: str | None = None,
    ) -> DatabricksCategoryPageResponse:
        """Return paginated resources and state for a single workspace discovery category."""
        now = datetime.now(UTC)
        conn = self._resolve_raw_connection(connection_id)
        if not conn:
            return DatabricksCategoryPageResponse(
                connection_id=connection_id,
                workspace_id="unknown",
                workspace_name="Unknown Workspace",
                workspace_url="",
                category=category,
                status=CategoryDiscoveryStatus.CONNECTION_ERROR,
                discovery_state=DatabricksResourceState.UNAVAILABLE,
                source_api="databricks-sdk",
                retrieved_at=now,
                error_code="CONNECTION_NOT_FOUND",
                error_message=f"Databricks connection '{connection_id}' was not found.",
            )

        ws_env = conn.get("environment")
        if (job_id is not None and category == "job_runs") or (
            page_token and category in ("jobs", "job_runs")
        ):
            client, err_text, raw_exc = await asyncio.to_thread(
                self.discovery_service.init_client,
                host=conn["workspace_url"],
                cloud=conn["cloud"],
                profile=conn["profile_name"],
                environment=ws_env,
            )
            if not client:
                cat_err = self.discovery_service._build_error_category_result(
                    category,
                    conn["workspace_id"],
                    f"databricks-sdk/{category}",
                    raw_exc or Exception(err_text or "Client unavailable"),
                    now,
                )
                return DatabricksCategoryPageResponse(
                    connection_id=str(conn["connection_id"]),
                    workspace_id=conn["workspace_id"],
                    workspace_name=conn["workspace_name"],
                    workspace_url=conn["workspace_url"],
                    environment=ws_env,
                    category=category,
                    status=cat_err.status,
                    discovery_state=cat_err.discovery_state or DatabricksResourceState.UNAVAILABLE,
                    source_api=cat_err.source_api or f"databricks-sdk/{category}",
                    retrieved_at=now,
                    http_status=cat_err.http_status,
                    error_code=cat_err.error_code,
                    error_message=cat_err.error_message,
                )
            if category == "jobs":
                cat_info, matching = await asyncio.to_thread(
                    self.discovery_service.discover_jobs,
                    client,
                    conn["workspace_id"],
                    now,
                    page_token=page_token,
                )
            else:
                cat_info, matching = await asyncio.to_thread(
                    self.discovery_service.discover_job_runs,
                    client,
                    conn["workspace_id"],
                    now,
                    max_items=max(1, min(limit, 500)),
                    job_id=job_id,
                    page_token=page_token,
                )
            safe_offset = max(0, offset)
            safe_limit = max(1, min(limit, 500))
            page_items = matching[safe_offset : safe_offset + safe_limit]
            has_more = (safe_offset + safe_limit) < len(matching) or cat_info.has_more
            next_token = (
                str(safe_offset + safe_limit)
                if (safe_offset + safe_limit) < len(matching)
                else None
            )
            return DatabricksCategoryPageResponse(
                connection_id=str(conn["connection_id"]),
                workspace_id=conn["workspace_id"],
                workspace_name=conn["workspace_name"],
                workspace_url=conn["workspace_url"],
                environment=ws_env,
                category=category,
                status=cat_info.status,
                discovery_state=cat_info.discovery_state or DatabricksResourceState.UNAVAILABLE,
                source_api=cat_info.source_api or f"databricks-sdk/{category}",
                retrieved_at=cat_info.discovered_at or now,
                items=page_items,
                total_returned=len(page_items),
                has_more=has_more,
                next_page_token=next_token or cat_info.next_page_token,
                empty_confirmed=cat_info.empty_confirmed,
                http_status=cat_info.http_status,
                error_code=cat_info.error_code,
                error_message=cat_info.error_message,
            )

        discovery = await self.get_or_discover_workspace(
            str(conn["connection_id"]), force_refresh=force_refresh
        )
        cached_cat = discovery.categories.get(category)
        if not cached_cat:
            return DatabricksCategoryPageResponse(
                connection_id=str(conn["connection_id"]),
                workspace_id=conn["workspace_id"],
                workspace_name=conn["workspace_name"],
                workspace_url=conn["workspace_url"],
                environment=ws_env,
                category=category,
                status=CategoryDiscoveryStatus.UNSUPPORTED,
                discovery_state=DatabricksResourceState.NOT_SUPPORTED,
                source_api="databricks-sdk",
                retrieved_at=discovery.discovered_at,
                error_code="UNKNOWN_CATEGORY",
                error_message=f"Category '{category}' is not supported.",
            )

        type_map: dict[str, set[str]] = {
            "workspace": {"workspace"},
            "clusters": {"cluster"},
            "cluster_policies": {"cluster_policy"},
            "instance_pools": {"instance_pool"},
            "warehouses": {"warehouse"},
            "jobs": {"job"},
            "job_runs": {"job_run"},
            "pipelines": {"pipeline"},
            "model_serving": {"serving_endpoint"},
            "mlflow": {"mlflow_experiment", "mlflow_run"},
            "unity_catalog": {"catalog"},
            "apps": {"app"},
        }
        allowed_types = type_map.get(category, set())
        matching = [r for r in discovery.resources if r.resource_type in allowed_types]
        safe_offset = max(0, offset)
        safe_limit = max(1, min(limit, 500))
        page_items = matching[safe_offset : safe_offset + safe_limit]
        has_more = (safe_offset + safe_limit) < len(matching) or cached_cat.has_more
        next_token = (
            str(safe_offset + safe_limit) if (safe_offset + safe_limit) < len(matching) else None
        )

        return DatabricksCategoryPageResponse(
            connection_id=str(conn["connection_id"]),
            workspace_id=conn["workspace_id"],
            workspace_name=conn["workspace_name"],
            workspace_url=conn["workspace_url"],
            environment=ws_env,
            category=category,
            status=cached_cat.status,
            discovery_state=cached_cat.discovery_state or DatabricksResourceState.UNAVAILABLE,
            source_api=cached_cat.source_api or f"databricks-sdk/{category}",
            retrieved_at=cached_cat.discovered_at or discovery.discovered_at,
            items=page_items,
            total_returned=len(page_items),
            has_more=has_more,
            next_page_token=next_token,
            empty_confirmed=cached_cat.empty_confirmed,
            http_status=cached_cat.http_status,
            error_code=cached_cat.error_code,
            error_message=cached_cat.error_message,
        )

    async def get_unity_catalog_metadata(
        self,
        connection_id: str,
        catalog_name: str | None = None,
        include_permissions: bool = True,
        force_refresh: bool = False,
    ) -> UnityCatalogMetadataResponse:
        """Fetch live Unity Catalog catalogs, schemas, tables, and effective grants."""
        now = datetime.now(UTC)
        conn = self._resolve_raw_connection(connection_id)
        if not conn:
            return UnityCatalogMetadataResponse(
                connection_id=connection_id,
                workspace_id="unknown",
                workspace_url="",
                status=CategoryDiscoveryStatus.CONNECTION_ERROR,
                discovery_state=DatabricksResourceState.UNAVAILABLE,
                retrieved_at=now,
                error_code="CONNECTION_NOT_FOUND",
                error_message=f"Databricks connection '{connection_id}' was not found.",
            )

        canonical_cid = str(conn["connection_id"])
        if not force_refresh and not catalog_name and canonical_cid in self._uc_cache:
            return self._uc_cache[canonical_cid]

        client, err_text, raw_exc = await asyncio.to_thread(
            self.discovery_service.init_client,
            host=conn["workspace_url"],
            cloud=conn["cloud"],
            profile=conn["profile_name"],
            environment=conn.get("environment"),
        )
        res = await asyncio.to_thread(
            self.discovery_service.discover_unity_catalog_hierarchy,
            client=client,
            connection_id=canonical_cid,
            workspace_id=conn["workspace_id"],
            workspace_url=conn["workspace_url"],
            now=now,
            catalog_name=catalog_name,
            include_permissions=include_permissions,
            init_error=raw_exc,
            init_error_text=err_text,
            workspace_name=conn["workspace_name"],
            environment=conn.get("environment"),
        )
        if not catalog_name:
            self._uc_cache[canonical_cid] = res
        return res

    async def get_system_tables_metadata(
        self,
        connection_id: str,
        force_refresh: bool = False,
        warehouse_id: str | None = None,
    ) -> SystemTablesMetadataResponse:
        """Discover live System Tables schemas, table columns, and SELECT grants (zero SQL)."""
        now = datetime.now(UTC)
        conn = self._resolve_raw_connection(connection_id)
        if not conn:
            return SystemTablesMetadataResponse(
                connection_id=connection_id,
                workspace_id="unknown",
                workspace_url="",
                status=CategoryDiscoveryStatus.CONNECTION_ERROR,
                discovery_state=DatabricksResourceState.UNAVAILABLE,
                retrieved_at=now,
                error_code="CONNECTION_NOT_FOUND",
                error_message=f"Databricks connection '{connection_id}' was not found.",
            )

        canonical_cid = str(conn["connection_id"])
        if not force_refresh and not warehouse_id and canonical_cid in self._system_tables_cache:
            return self._system_tables_cache[canonical_cid]

        resolved_wh = (
            warehouse_id
            or conn.get("warehouse_id")
            or self.settings.databricks_warehouse_id
            or None
        )

        client, err_text, raw_exc = await asyncio.to_thread(
            self.discovery_service.init_client,
            host=conn["workspace_url"],
            cloud=conn["cloud"],
            profile=conn["profile_name"],
            environment=conn.get("environment"),
        )
        res = await asyncio.to_thread(
            self.discovery_service.discover_system_tables_metadata,
            client=client,
            connection_id=canonical_cid,
            workspace_id=conn["workspace_id"],
            workspace_url=conn["workspace_url"],
            now=now,
            init_error=raw_exc,
            init_error_text=err_text,
            workspace_name=conn["workspace_name"],
            environment=conn.get("environment"),
            warehouse_id=resolved_wh,
        )
        if not warehouse_id:
            self._system_tables_cache[canonical_cid] = res
        return res

    async def get_query_history(
        self,
        connection_id: str,
        warehouse_id: str | None = None,
        status_filter: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        query_source: str | None = None,
        max_results: int = 50,
        page_token: str | None = None,
    ) -> LiveQueryHistoryResponse:
        """Fetch paginated live SQL query history via Query History REST API (zero SQL executed)."""
        now = datetime.now(UTC)
        conn = self._resolve_raw_connection(connection_id)
        if not conn:
            return LiveQueryHistoryResponse(
                connection_id=connection_id,
                workspace_id="unknown",
                workspace_url="",
                status=CategoryDiscoveryStatus.CONNECTION_ERROR,
                discovery_state=DatabricksResourceState.UNAVAILABLE,
                retrieved_at=now,
                error_code="CONNECTION_NOT_FOUND",
                error_message=f"Databricks connection '{connection_id}' was not found.",
            )

        client, err_text, raw_exc = await asyncio.to_thread(
            self.discovery_service.init_client,
            host=conn["workspace_url"],
            cloud=conn["cloud"],
            profile=conn["profile_name"],
            environment=conn.get("environment"),
        )
        return await asyncio.to_thread(
            self.discovery_service.discover_query_history,
            client=client,
            connection_id=str(conn["connection_id"]),
            workspace_id=conn["workspace_id"],
            workspace_url=conn["workspace_url"],
            now=now,
            warehouse_id=warehouse_id,
            status_filter=status_filter,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            query_source=query_source,
            max_results=max(1, min(max_results, 100)),
            page_token=page_token,
            init_error=raw_exc,
            init_error_text=err_text,
            workspace_name=conn["workspace_name"],
            environment=conn.get("environment"),
        )
