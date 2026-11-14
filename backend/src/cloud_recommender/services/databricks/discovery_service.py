"""Permission-aware live Databricks workspace discovery service.

Discovers compute, cluster policies, instance pools, warehouses, jobs, job runs,
pipelines, model serving, MLflow experiments/runs, Unity Catalog (catalogs,
schemas, tables, grants), System Tables metadata, Databricks Apps, and Query History.
Each discovery category evaluates independently and reports explicit M2 states:
- LIVE (AVAILABLE)
- NO_DATA (NO_RESOURCES_FOUND, only when confirmed by API contract)
- ACCESS_DENIED (PERMISSION_DENIED)
- AUTH_FAILED (AUTH_FAILED)
- UNAVAILABLE (CONNECTION_ERROR / 429 / 5xx / unconfirmed empty payload)
- NOT_SUPPORTED (UNSUPPORTED / 404)
Zero SQL execution, zero warehouse startup, and zero synthetic fallback data.
"""

import asyncio
import re
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from functools import partial
from typing import Any, TypeVar

import structlog
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import QueryFilter, QueryStatus, TimeRange

from cloud_recommender.schemas.databricks import (
    CategoryDiscoveryResult,
    CategoryDiscoveryStatus,
    DatabricksCloud,
    DatabricksResourceState,
    DatabricksWorkspaceDiscoveryResponse,
    DiscoveredResourceItem,
    LiveQueryHistoryItem,
    LiveQueryHistoryResponse,
    LiveSystemTableItem,
    SystemTablesMetadataResponse,
    TypedSystemTableRegistryEntry,
    UnityCatalogCatalogItem,
    UnityCatalogColumnItem,
    UnityCatalogMetadataResponse,
    UnityCatalogPermissionItem,
    UnityCatalogSchemaItem,
    UnityCatalogTableItem,
)
from cloud_recommender.services.databricks.auth import (
    DatabricksAuthService,
    classify_http_and_sdk_error,
)

logger = structlog.get_logger(__name__)

_T = TypeVar("_T")

_SYSTEM_TARGET_SCHEMAS: list[str] = [
    "billing",
    "compute",
    "query",
    "access",
    "lakeflow",
    "ai_gateway",
    "serving",
    "storage",
    "mlflow",
]

_SYSTEM_SCHEMA_DOMAIN_MAP: dict[str, str] = {
    "billing": "billing",
    "compute": "compute",
    "query": "query",
    "access": "access",
    "lakeflow": "lakeflow",
    "ai_gateway": "ai_serving",
    "serving": "ai_serving",
    "storage": "storage",
    "mlflow": "mlflow",
}

_M3_REGISTRY_SCHEMAS: frozenset[str] = frozenset(
    {"billing", "compute", "query", "lakeflow", "serving"}
)

_REQUIRED_COLUMNS_BY_TABLE: dict[str, set[str]] = {
    "system.billing.usage": {"account_id", "workspace_id", "usage_quantity", "usage_date"},
    "system.billing.list_prices": {"sku_name"},
    "system.compute.clusters": {"cluster_id"},
    "system.compute.warehouses": {"warehouse_id"},
    "system.lakeflow.jobs": {"job_id"},
    "system.lakeflow.pipelines": {"pipeline_id"},
    "system.ai_gateway.usage": {"endpoint_name"},
    "system.serving.endpoint_usage": {"endpoint_name"},
}

_RE_SQL_STRING_LITERAL = re.compile(r"'(?:''|[^'])*'")


class UnconfirmedEmptyResponseError(ValueError):
    """Raised when an HTTP 200 payload is empty/malformed without confirming zero records."""


def _normalize_timestamp(val: Any) -> str | None:
    """Normalize epoch ms/s, datetime, or ISO string to UTC ISO-8601 string."""
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        dt = val if val.tzinfo is not None else val.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if val <= 0:
            return None
        seconds = val / 1000.0 if val > 1e11 else float(val)
        return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        if s.isdigit():
            return _normalize_timestamp(int(s))
        return s
    return None


def _enum_str(val: Any, default: str = "UNKNOWN") -> str:
    """Extract string value safely from SDK enum or plain attribute."""
    if val is None:
        return default
    inner = getattr(val, "value", None)
    if isinstance(inner, str):
        return inner
    if isinstance(val, str):
        return val
    return default


def _opt_str(val: Any) -> str | None:
    """Safely convert scalar or enum values to str | None without leaking mock objects."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return str(val)
    inner = getattr(val, "value", None)
    if isinstance(inner, str):
        return inner
    return None


def _opt_int(val: Any) -> int | None:
    """Safely convert int/numeric attributes without leaking mock objects."""
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        return int(val)
    return None


def _opt_bool(val: Any) -> bool | None:
    """Safely extract bool without leaking mock objects."""
    if isinstance(val, bool):
        return val
    return None


def _mask_principal(principal: str | None) -> str | None:
    """Mask user email/principal PII while keeping service identity distinguishable."""
    if not principal:
        return None
    text = principal.strip()
    if "@" in text:
        local, domain = text.split("@", 1)
        prefix = local[:2] if len(local) > 2 else local[:1]
        return f"{prefix}***@{domain}"
    if len(text) > 8:
        return f"{text[:4]}***{text[-2:]}"
    return text


def _sanitize_sql_summary(sql_text: str | None, auth_service: DatabricksAuthService) -> str:
    """Produce a safe, secret-scrubbed, literal-masked SQL summary preview."""
    if not sql_text:
        return "[SQL summary unavailable]"
    scrubbed = auth_service.scrub_sensitive(sql_text)
    masked = _RE_SQL_STRING_LITERAL.sub("'[REDACTED]'", scrubbed)
    compact = " ".join(masked.split())
    if len(compact) > 160:
        return f"{compact[:157]}..."
    return compact


_ALL_WORKSPACE_CATEGORIES: tuple[str, ...] = (
    "workspace",
    "clusters",
    "cluster_policies",
    "instance_pools",
    "warehouses",
    "jobs",
    "job_runs",
    "pipelines",
    "model_serving",
    "mlflow",
    "unity_catalog",
    "apps",
)


class DatabricksDiscoveryService:
    """Service discovering multi-category assets across Azure and AWS Databricks workspaces."""

    def __init__(
        self,
        auth_service: DatabricksAuthService | None = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.05,
    ) -> None:
        self.auth_service = auth_service or DatabricksAuthService()
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)

    def _call_with_retry(self, fn: Callable[[], _T], source_api: str) -> _T:
        """Execute an SDK call with bounded exponential backoff on HTTP 429 and transient 5xx."""
        attempt = 0
        while True:
            try:
                return fn()
            except Exception as exc:
                kind, http_status, _ = classify_http_and_sdk_error(exc)
                is_transient = kind == "rate_limited" or (
                    http_status is not None and 500 <= http_status < 600
                )
                if is_transient and attempt < self.max_retries:
                    attempt += 1
                    sleep_time = self.retry_backoff_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "databricks_transient_error_retry",
                        source_api=source_api,
                        attempt=attempt,
                        http_status=http_status,
                        sleep_time=sleep_time,
                    )
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    continue
                raise

    def _safe_get_detail(self, fn: Callable[[], _T], source_api: str) -> _T | None:
        """Fetch optional detail record via .get() without failing the parent category."""
        try:
            return self._call_with_retry(fn, source_api)
        except Exception as exc:
            logger.debug("databricks_detail_get_skipped", source_api=source_api, error=str(exc))
            return None

    def init_client(
        self,
        host: str,
        cloud: DatabricksCloud,
        profile: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        auth_type: str | None = None,
        environment: str | None = None,
    ) -> tuple[WorkspaceClient | None, str | None, Exception | None]:
        """Initialize an authenticated WorkspaceClient, returning (client, scrubbed_error, raw_exc)."""
        try:
            client_res = self.auth_service.create_workspace_client(
                host=host,
                cloud=cloud.value,
                profile=profile,
                client_id=client_id,
                client_secret=client_secret,
                auth_type=auth_type,
                environment=environment,
            )
            client = client_res[0] if isinstance(client_res, tuple) else client_res
            return client, None, None
        except Exception as exc:
            connect_error = self.auth_service.scrub_sensitive(str(exc))
            logger.warning("databricks_client_init_failed", host=host, error=connect_error)
            return None, connect_error, exc

    def _classify_error_detailed(
        self, exc: Exception
    ) -> tuple[CategoryDiscoveryStatus, DatabricksResourceState, int | None, str, str]:
        """Classify SDK/REST errors cleanly across 401, 403, 404, 429, 5xx, and transport failures."""
        raw_msg = self.auth_service.scrub_sensitive(str(exc))
        kind, http_status, error_code = classify_http_and_sdk_error(exc)
        if isinstance(exc, UnconfirmedEmptyResponseError):
            return (
                CategoryDiscoveryStatus.CONNECTION_ERROR,
                DatabricksResourceState.UNAVAILABLE,
                200,
                "EMPTY_UNCONFIRMED",
                raw_msg,
            )
        if kind == "auth_failed":
            return (
                CategoryDiscoveryStatus.AUTH_FAILED,
                DatabricksResourceState.AUTH_FAILED,
                http_status,
                error_code,
                f"Authentication failed: {raw_msg}",
            )
        if kind == "permission_denied":
            return (
                CategoryDiscoveryStatus.PERMISSION_DENIED,
                DatabricksResourceState.ACCESS_DENIED,
                http_status,
                error_code,
                f"Permission denied: {raw_msg}",
            )
        if kind == "not_supported":
            return (
                CategoryDiscoveryStatus.UNSUPPORTED,
                DatabricksResourceState.NOT_SUPPORTED,
                http_status,
                error_code,
                f"Feature not enabled or unsupported: {raw_msg}",
            )
        if kind == "rate_limited":
            return (
                CategoryDiscoveryStatus.CONNECTION_ERROR,
                DatabricksResourceState.UNAVAILABLE,
                http_status,
                error_code,
                f"Rate limited by Databricks API (HTTP 429): {raw_msg}",
            )
        return (
            CategoryDiscoveryStatus.CONNECTION_ERROR,
            DatabricksResourceState.UNAVAILABLE,
            http_status,
            error_code,
            f"API unavailable: {raw_msg}",
        )

    def _classify_error(self, exc: Exception) -> tuple[CategoryDiscoveryStatus, str]:
        """Backward-compatible wrapper returning (CategoryDiscoveryStatus, message)."""
        status, _, _, _, msg = self._classify_error_detailed(exc)
        return status, msg

    def _collect_sdk_iterable(
        self, raw_result: Any, source_api: str, max_items: int = 10_000
    ) -> tuple[list[Any], bool]:
        """Safely consume an SDK iterable, refusing to call unconfirmed None/dict responses NO_DATA.

        SDK iterators follow the service's page tokens themselves, so every page is read until the
        source ends. ``max_items`` is only a safety bound (never an intended sample size): hitting
        it returns ``has_more=True`` and the category is reported as INCOMPLETE, not complete.
        """
        if raw_result is None or isinstance(raw_result, (dict, str, bytes)):
            raise UnconfirmedEmptyResponseError(
                f"{source_api} returned an empty or malformed response that did not confirm zero records."
            )
        if not isinstance(raw_result, Iterable):
            raise UnconfirmedEmptyResponseError(
                f"{source_api} returned non-iterable payload ({type(raw_result).__name__})."
            )
        collected: list[Any] = []
        has_more = False
        for item in raw_result:
            if len(collected) >= max_items:
                has_more = True
                break
            collected.append(item)
        return collected, has_more

    def _collect_run_artifacts(
        self, client: WorkspaceClient, run_id: str
    ) -> tuple[list[Any], bool]:
        """Collect MLflow run artifact file paths/metadata without downloading contents."""
        return self._collect_sdk_iterable(
            client.experiments.list_artifacts(run_id=run_id),
            "databricks-sdk/experiments.list_artifacts",
            max_items=25,
        )

    def _build_category_result(
        self,
        category: str,
        workspace_id: str,
        source_api: str,
        items: list[DiscoveredResourceItem],
        now: datetime,
        has_more: bool = False,
        next_page_token: str | None = None,
    ) -> CategoryDiscoveryResult:
        """Build a standardized LIVE / NO_DATA CategoryDiscoveryResult."""
        if items:
            return CategoryDiscoveryResult(
                category=category,
                status=CategoryDiscoveryStatus.AVAILABLE,
                discovery_state=DatabricksResourceState.LIVE,
                resource_count=len(items),
                workspace_id=workspace_id,
                source_api=source_api,
                empty_confirmed=False,
                has_more=has_more,
                next_page_token=next_page_token,
                discovered_at=now,
            )
        return CategoryDiscoveryResult(
            category=category,
            status=CategoryDiscoveryStatus.NO_RESOURCES_FOUND,
            discovery_state=DatabricksResourceState.NO_DATA,
            resource_count=0,
            workspace_id=workspace_id,
            source_api=source_api,
            empty_confirmed=not has_more,
            has_more=has_more,
            next_page_token=next_page_token,
            discovered_at=now,
        )

    def _build_error_category_result(
        self,
        category: str,
        workspace_id: str,
        source_api: str,
        exc: Exception,
        now: datetime,
    ) -> CategoryDiscoveryResult:
        """Build a standardized failed CategoryDiscoveryResult from an exception."""
        status, state, http_status, error_code, msg = self._classify_error_detailed(exc)
        return CategoryDiscoveryResult(
            category=category,
            status=status,
            discovery_state=state,
            resource_count=0,
            workspace_id=workspace_id,
            source_api=source_api,
            http_status=http_status,
            error_code=error_code,
            error_message=msg,
            discovered_at=now,
        )

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
        environment: str | None = None,
    ) -> DatabricksWorkspaceDiscoveryResponse:
        """Run the (blocking) SDK discovery in a worker thread so the event loop stays responsive."""
        return await asyncio.to_thread(
            self._discover_workspace_sync,
            connection_id=connection_id,
            host=host,
            cloud=cloud,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            profile=profile,
            client_id=client_id,
            client_secret=client_secret,
            environment=environment,
        )

    def _discover_workspace_sync(
        self,
        connection_id: str,
        host: str,
        cloud: DatabricksCloud,
        workspace_id: str,
        workspace_name: str,
        profile: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        environment: str | None = None,
    ) -> DatabricksWorkspaceDiscoveryResponse:
        """Execute independent category discovery against a Databricks workspace."""
        now = datetime.now(UTC)
        client, connect_error, raw_exc = self.init_client(
            host=host,
            cloud=cloud,
            profile=profile,
            client_id=client_id,
            client_secret=client_secret,
            environment=environment,
        )

        categories: dict[str, CategoryDiscoveryResult] = {}
        all_resources: list[DiscoveredResourceItem] = []

        # If client initialization completely failed, classify accurately without leaking secrets
        if not client or connect_error:
            err_msg = connect_error or "Failed to initialize Databricks workspace client."
            if raw_exc is not None:
                init_status, init_state, http_status, error_code, classified_msg = (
                    self._classify_error_detailed(raw_exc)
                )
            else:
                init_status = CategoryDiscoveryStatus.CONNECTION_ERROR
                init_state = DatabricksResourceState.UNAVAILABLE
                http_status = None
                error_code = "CONNECTION_ERROR"
                classified_msg = err_msg

            for cat_name in _ALL_WORKSPACE_CATEGORIES:
                categories[cat_name] = CategoryDiscoveryResult(
                    category=cat_name,
                    status=init_status,
                    discovery_state=init_state,
                    resource_count=0,
                    workspace_id=workspace_id,
                    source_api="databricks-sdk/auth",
                    http_status=http_status,
                    error_code=error_code,
                    error_message=classified_msg,
                    discovered_at=now,
                )
            return DatabricksWorkspaceDiscoveryResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=host,
                environment=environment,
                cloud=cloud,
                overall_status="failed",
                data_status=init_state,
                categories=categories,
                resources=[],
                total_resources_count=0,
                discovered_at=now,
            )
        r_ws = self._discover_workspace_metadata(
            client, workspace_id, workspace_name, host, cloud, now
        )
        r_cl = self.discover_clusters(client, workspace_id, now)
        r_cp = self.discover_cluster_policies(client, workspace_id, now)
        r_ip = self.discover_instance_pools(client, workspace_id, now)
        r_wh = self.discover_warehouses(client, workspace_id, now)
        r_jb = self.discover_jobs(client, workspace_id, now)
        r_jr = self.discover_job_runs(client, workspace_id, now)
        r_pl = self.discover_pipelines(client, workspace_id, now)
        r_ms = self.discover_model_serving(client, workspace_id, now)
        r_mf = self.discover_mlflow(client, workspace_id, now)
        r_uc = self.discover_unity_catalog(client, workspace_id, now)
        r_ap = self.discover_apps(client, workspace_id, now)

        category_runners: list[
            tuple[str, tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]]
        ] = [
            ("workspace", r_ws),
            ("clusters", r_cl),
            ("cluster_policies", r_cp),
            ("instance_pools", r_ip),
            ("warehouses", r_wh),
            ("jobs", r_jb),
            ("job_runs", r_jr),
            ("pipelines", r_pl),
            ("model_serving", r_ms),
            ("mlflow", r_mf),
            ("unity_catalog", r_uc),
            ("apps", r_ap),
        ]

        for cat_name, (cat_res, res_items) in category_runners:
            categories[cat_name] = cat_res
            all_resources.extend(res_items)

        # Determine overall discovery status
        failed_cats = sum(
            1
            for c in categories.values()
            if c.status
            in (
                CategoryDiscoveryStatus.CONNECTION_ERROR,
                CategoryDiscoveryStatus.PERMISSION_DENIED,
                CategoryDiscoveryStatus.AUTH_FAILED,
            )
        )
        success_cats = sum(
            1
            for c in categories.values()
            if c.status
            in (CategoryDiscoveryStatus.AVAILABLE, CategoryDiscoveryStatus.NO_RESOURCES_FOUND)
        )

        if failed_cats == 0:
            overall = "completed"
            data_status = (
                DatabricksResourceState.LIVE if all_resources else DatabricksResourceState.NO_DATA
            )
        elif success_cats > 0:
            overall = "partial_failure"
            data_status = DatabricksResourceState.PARTIAL
        else:
            overall = "failed"
            states = {
                c.discovery_state for c in categories.values() if c.discovery_state is not None
            }
            if DatabricksResourceState.AUTH_FAILED in states:
                data_status = DatabricksResourceState.AUTH_FAILED
            elif DatabricksResourceState.ACCESS_DENIED in states:
                data_status = DatabricksResourceState.ACCESS_DENIED
            else:
                data_status = DatabricksResourceState.UNAVAILABLE

        return DatabricksWorkspaceDiscoveryResponse(
            connection_id=connection_id,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            workspace_url=host,
            environment=environment,
            cloud=cloud,
            overall_status=overall,
            data_status=data_status,
            categories=categories,
            resources=all_resources,
            total_resources_count=len(all_resources),
            discovered_at=now,
        )

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
        source_api = "databricks-sdk/current_user.me"
        try:
            me = self._call_with_retry(client.current_user.me, source_api)
            user_principal = (
                _opt_str(getattr(me, "user_name", None))
                or _opt_str(getattr(me, "display_name", None))
                or "authenticated_user"
            )
            res = DiscoveredResourceItem(
                id=workspace_id,
                name=workspace_name,
                resource_type="workspace",
                workspace_id=workspace_id,
                status="ONLINE",
                creator=user_principal,
                source_api=source_api,
                metadata={"host": host, "cloud": cloud.value, "user": user_principal},
                discovered_at=now,
            )
            return self._build_category_result("workspace", workspace_id, source_api, [res], now), [
                res
            ]
        except Exception as exc:
            return self._build_error_category_result(
                "workspace", workspace_id, source_api, exc, now
            ), []

    def discover_clusters(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract compute clusters via clusters.list and optional clusters.get detail enrichment."""
        source_api = "databricks-sdk/clusters.list"
        try:
            items: list[DiscoveredResourceItem] = []
            clusters, has_more = self._call_with_retry(
                lambda: self._collect_sdk_iterable(client.clusters.list(page_size=100), source_api),
                source_api,
            )
            for idx, cl in enumerate(clusters):
                c_id = _opt_str(getattr(cl, "cluster_id", None)) or "unknown-cluster"
                detail = (
                    self._safe_get_detail(
                        partial(client.clusters.get, cluster_id=c_id),
                        "databricks-sdk/clusters.get",
                    )
                    if idx < 15 and c_id != "unknown-cluster"
                    else None
                )
                src = detail or cl
                c_name = (
                    _opt_str(getattr(src, "cluster_name", None))
                    or _opt_str(getattr(cl, "cluster_name", None))
                    or c_id
                )
                c_state = _enum_str(getattr(src, "state", getattr(cl, "state", None))).upper()
                autoscale_obj = getattr(src, "autoscale", None) or getattr(cl, "autoscale", None)
                autoscale = (
                    {
                        "min_workers": _opt_int(getattr(autoscale_obj, "min_workers", None)),
                        "max_workers": _opt_int(getattr(autoscale_obj, "max_workers", None)),
                    }
                    if autoscale_obj is not None
                    and (
                        _opt_int(getattr(autoscale_obj, "min_workers", None)) is not None
                        or _opt_int(getattr(autoscale_obj, "max_workers", None)) is not None
                    )
                    else None
                )
                raw_custom_tags = getattr(src, "custom_tags", None)
                custom_tags = (
                    {
                        str(k): _opt_str(v)
                        for k, v in raw_custom_tags.items()
                        if _opt_str(v) is not None
                    }
                    if isinstance(raw_custom_tags, dict)
                    else None
                )
                items.append(
                    DiscoveredResourceItem(
                        id=c_id,
                        name=c_name,
                        resource_type="cluster",
                        workspace_id=workspace_id,
                        status=c_state,
                        creator=_opt_str(getattr(src, "creator_user_name", None))
                        or _opt_str(getattr(cl, "creator_user_name", None)),
                        source_api=source_api,
                        metadata={
                            "spark_version": _opt_str(getattr(src, "spark_version", None))
                            or _opt_str(getattr(cl, "spark_version", None)),
                            "node_type_id": _opt_str(getattr(src, "node_type_id", None))
                            or _opt_str(getattr(cl, "node_type_id", None)),
                            "driver_node_type_id": _opt_str(
                                getattr(src, "driver_node_type_id", None)
                            )
                            or _opt_str(getattr(cl, "driver_node_type_id", None)),
                            "num_workers": _opt_int(getattr(src, "num_workers", None))
                            if _opt_int(getattr(src, "num_workers", None)) is not None
                            else _opt_int(getattr(cl, "num_workers", None)),
                            "autoscale": autoscale,
                            "autotermination_minutes": _opt_int(
                                getattr(src, "autotermination_minutes", None)
                            )
                            if _opt_int(getattr(src, "autotermination_minutes", None)) is not None
                            else _opt_int(getattr(cl, "autotermination_minutes", None)),
                            "start_time": _normalize_timestamp(getattr(src, "start_time", None))
                            or _normalize_timestamp(getattr(cl, "start_time", None)),
                            "terminated_time": _normalize_timestamp(
                                getattr(src, "terminated_time", None)
                            )
                            or _normalize_timestamp(getattr(cl, "terminated_time", None)),
                            "last_activity_time": _normalize_timestamp(
                                getattr(src, "last_activity_time", None)
                            ),
                            "cluster_source": _opt_str(getattr(src, "cluster_source", None)),
                            "custom_tags": custom_tags or None,
                        },
                        discovered_at=now,
                    )
                )
            return self._build_category_result(
                "clusters", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result(
                "clusters", workspace_id, source_api, exc, now
            ), []

    def discover_cluster_policies(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract compute cluster policies via cluster_policies.list."""
        source_api = "databricks-sdk/cluster_policies.list"
        try:
            items: list[DiscoveredResourceItem] = []
            policies, has_more = self._call_with_retry(
                lambda: self._collect_sdk_iterable(client.cluster_policies.list(), source_api),
                source_api,
            )
            for pol in policies:
                p_id = _opt_str(getattr(pol, "policy_id", None)) or "unknown-policy"
                p_name = _opt_str(getattr(pol, "name", None)) or p_id
                items.append(
                    DiscoveredResourceItem(
                        id=p_id,
                        name=p_name,
                        resource_type="cluster_policy",
                        workspace_id=workspace_id,
                        status="ACTIVE",
                        creator=_opt_str(getattr(pol, "creator_user_name", None)),
                        source_api=source_api,
                        metadata={
                            "policy_family_id": _opt_str(getattr(pol, "policy_family_id", None)),
                            "max_clusters_per_user": _opt_int(
                                getattr(pol, "max_clusters_per_user", None)
                            ),
                            "created_at": _normalize_timestamp(
                                getattr(pol, "created_at_timestamp", None)
                            ),
                        },
                        discovered_at=now,
                    )
                )
            return self._build_category_result(
                "cluster_policies", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result(
                "cluster_policies", workspace_id, source_api, exc, now
            ), []

    def discover_instance_pools(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract compute instance pools via instance_pools.list."""
        source_api = "databricks-sdk/instance_pools.list"
        try:
            items: list[DiscoveredResourceItem] = []
            pools, has_more = self._call_with_retry(
                lambda: self._collect_sdk_iterable(client.instance_pools.list(), source_api),
                source_api,
            )
            for pool in pools:
                pool_id = _opt_str(getattr(pool, "instance_pool_id", None)) or "unknown-pool"
                pool_name = _opt_str(getattr(pool, "instance_pool_name", None)) or pool_id
                p_state = _enum_str(getattr(pool, "state", None), default="ACTIVE").upper()
                items.append(
                    DiscoveredResourceItem(
                        id=pool_id,
                        name=pool_name,
                        resource_type="instance_pool",
                        workspace_id=workspace_id,
                        status=p_state,
                        creator=None,
                        source_api=source_api,
                        metadata={
                            "node_type_id": _opt_str(getattr(pool, "node_type_id", None)),
                            "min_idle_instances": _opt_int(
                                getattr(pool, "min_idle_instances", None)
                            ),
                            "max_capacity": _opt_int(getattr(pool, "max_capacity", None)),
                            "idle_instance_autotermination_minutes": _opt_int(
                                getattr(pool, "idle_instance_autotermination_minutes", None)
                            ),
                        },
                        discovered_at=now,
                    )
                )
            return self._build_category_result(
                "instance_pools", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result(
                "instance_pools", workspace_id, source_api, exc, now
            ), []

    def discover_warehouses(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract SQL Warehouses via warehouses.list and optional warehouses.get enrichment."""
        source_api = "databricks-sdk/warehouses.list"
        try:
            items: list[DiscoveredResourceItem] = []
            warehouses, has_more = self._call_with_retry(
                lambda: self._collect_sdk_iterable(
                    client.warehouses.list(page_size=100), source_api
                ),
                source_api,
            )
            for idx, wh in enumerate(warehouses):
                wh_id = _opt_str(getattr(wh, "id", None)) or "unknown-warehouse"
                detail = (
                    self._safe_get_detail(
                        partial(client.warehouses.get, id=wh_id),
                        "databricks-sdk/warehouses.get",
                    )
                    if idx < 15 and wh_id != "unknown-warehouse"
                    else None
                )
                src = detail or wh
                wh_name = (
                    _opt_str(getattr(src, "name", None))
                    or _opt_str(getattr(wh, "name", None))
                    or wh_id
                )
                wh_state = _enum_str(getattr(src, "state", getattr(wh, "state", None))).upper()
                health_obj = getattr(src, "health", None)
                channel_obj = getattr(src, "channel", None)
                items.append(
                    DiscoveredResourceItem(
                        id=wh_id,
                        name=wh_name,
                        resource_type="warehouse",
                        workspace_id=workspace_id,
                        status=wh_state,
                        creator=_opt_str(getattr(src, "creator_name", None))
                        or _opt_str(getattr(wh, "creator_name", None)),
                        source_api=source_api,
                        metadata={
                            "cluster_size": _opt_str(getattr(src, "cluster_size", None))
                            or _opt_str(getattr(wh, "cluster_size", None)),
                            "auto_stop_mins": _opt_int(getattr(src, "auto_stop_mins", None))
                            if _opt_int(getattr(src, "auto_stop_mins", None)) is not None
                            else _opt_int(getattr(wh, "auto_stop_mins", None)),
                            "num_clusters": _opt_int(getattr(src, "num_clusters", None))
                            if _opt_int(getattr(src, "num_clusters", None)) is not None
                            else _opt_int(getattr(wh, "num_clusters", None)),
                            "min_num_clusters": _opt_int(getattr(src, "min_num_clusters", None)),
                            "max_num_clusters": _opt_int(getattr(src, "max_num_clusters", None)),
                            "warehouse_type": _opt_str(getattr(src, "warehouse_type", None))
                            or _opt_str(getattr(wh, "warehouse_type", None)),
                            "enable_serverless_compute": _opt_bool(
                                getattr(src, "enable_serverless_compute", None)
                            )
                            if _opt_bool(getattr(src, "enable_serverless_compute", None))
                            is not None
                            else _opt_bool(getattr(wh, "enable_serverless_compute", None)),
                            "spot_instance_policy": _opt_str(
                                getattr(src, "spot_instance_policy", None)
                            ),
                            "health_status": _opt_str(getattr(health_obj, "status", None))
                            if health_obj is not None
                            else None,
                            "channel": _opt_str(getattr(channel_obj, "name", None))
                            if channel_obj is not None
                            else None,
                        },
                        discovered_at=now,
                    )
                )
            return self._build_category_result(
                "warehouses", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result(
                "warehouses", workspace_id, source_api, exc, now
            ), []

    def discover_jobs(
        self,
        client: WorkspaceClient,
        workspace_id: str,
        now: datetime,
        page_token: str | None = None,
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract Jobs and Workflows via jobs.list and optional jobs.get detail enrichment."""
        source_api = "databricks-sdk/jobs.list"
        try:
            items: list[DiscoveredResourceItem] = []
            list_kwargs: dict[str, Any] = {"limit": 100}
            if page_token:
                list_kwargs["page_token"] = page_token
            jobs, has_more = self._call_with_retry(
                lambda: self._collect_sdk_iterable(client.jobs.list(**list_kwargs), source_api),
                source_api,
            )
            for idx, j in enumerate(jobs):
                j_id = str(getattr(j, "job_id", "unknown-job"))
                j_settings = getattr(j, "settings", None)
                raw_tasks = getattr(j_settings, "tasks", None) if j_settings else None
                task_count = len(raw_tasks) if isinstance(raw_tasks, list) else 0
                if idx < 15 and j_id.isdigit():
                    detail = self._safe_get_detail(
                        partial(client.jobs.get, job_id=int(j_id)),
                        "databricks-sdk/jobs.get",
                    )
                    if detail is not None:
                        d_settings = getattr(detail, "settings", None)
                        if d_settings is not None:
                            j_settings = d_settings
                            d_tasks = getattr(d_settings, "tasks", None)
                            if isinstance(d_tasks, list):
                                task_count = len(d_tasks)
                j_name = _opt_str(getattr(j_settings, "name", None)) or f"job-{j_id}"
                sched = getattr(j_settings, "schedule", None) if j_settings else None
                cron = _opt_str(getattr(sched, "quartz_cron_expression", None)) if sched else None
                tz_id = _opt_str(getattr(sched, "timezone_id", None)) if sched else None
                pause_state = _opt_str(getattr(sched, "pause_status", None)) if sched else None
                items.append(
                    DiscoveredResourceItem(
                        id=j_id,
                        name=j_name,
                        resource_type="job",
                        workspace_id=workspace_id,
                        status="PAUSED"
                        if pause_state == "PAUSED"
                        else ("SCHEDULED" if cron else "MANUAL"),
                        creator=_opt_str(getattr(j, "creator_user_name", None)),
                        source_api=source_api,
                        metadata={
                            "tasks_count": task_count,
                            "cron_schedule": cron,
                            "timezone_id": tz_id,
                            "max_concurrent_runs": _opt_int(
                                getattr(j_settings, "max_concurrent_runs", None)
                            )
                            if j_settings
                            else None,
                            "created_time": _normalize_timestamp(getattr(j, "created_time", None)),
                        },
                        discovered_at=now,
                    )
                )
            return self._build_category_result(
                "jobs", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result("jobs", workspace_id, source_api, exc, now), []

    def discover_job_runs(
        self,
        client: WorkspaceClient,
        workspace_id: str,
        now: datetime,
        max_items: int = 100,
        job_id: int | None = None,
        page_token: str | None = None,
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract recent Job Runs via jobs.list_runs."""
        source_api = "databricks-sdk/jobs.list_runs"
        try:
            items: list[DiscoveredResourceItem] = []
            run_kwargs: dict[str, Any] = {"limit": 25, "expand_tasks": False}
            if job_id is not None:
                run_kwargs["job_id"] = job_id
            if page_token:
                run_kwargs["page_token"] = page_token
            runs, has_more = self._call_with_retry(
                lambda: self._collect_sdk_iterable(
                    client.jobs.list_runs(**run_kwargs),
                    source_api,
                    max_items=max_items,
                ),
                source_api,
            )
            for run in runs:
                run_id = _opt_str(getattr(run, "run_id", None)) or "unknown-run"
                run_name = _opt_str(getattr(run, "run_name", None)) or f"run-{run_id}"
                r_state_obj = getattr(run, "state", None)
                life_cycle = _enum_str(getattr(r_state_obj, "life_cycle_state", None))
                result_state = _opt_str(getattr(r_state_obj, "result_state", None))
                combined_state = result_state or life_cycle
                items.append(
                    DiscoveredResourceItem(
                        id=run_id,
                        name=run_name,
                        resource_type="job_run",
                        workspace_id=workspace_id,
                        status=combined_state.upper(),
                        creator=_opt_str(getattr(run, "creator_user_name", None)),
                        source_api=source_api,
                        metadata={
                            "job_id": _opt_str(getattr(run, "job_id", None)),
                            "life_cycle_state": life_cycle,
                            "result_state": result_state,
                            "trigger": _opt_str(getattr(run, "trigger", None)),
                            "attempt_number": _opt_int(getattr(run, "attempt_number", None)),
                            "start_time": _normalize_timestamp(getattr(run, "start_time", None)),
                            "end_time": _normalize_timestamp(getattr(run, "end_time", None)),
                            "execution_duration_ms": _opt_int(
                                getattr(run, "execution_duration", None)
                            ),
                            "setup_duration_ms": _opt_int(getattr(run, "setup_duration", None)),
                            "cleanup_duration_ms": _opt_int(getattr(run, "cleanup_duration", None)),
                        },
                        discovered_at=now,
                    )
                )
            return self._build_category_result(
                "job_runs", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result(
                "job_runs", workspace_id, source_api, exc, now
            ), []

    def discover_pipelines(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract Lakeflow / DLT Pipelines via pipelines.list_pipelines and optional .get."""
        source_api = "databricks-sdk/pipelines.list_pipelines"
        try:
            items: list[DiscoveredResourceItem] = []
            pipelines, has_more = self._call_with_retry(
                lambda: self._collect_sdk_iterable(
                    client.pipelines.list_pipelines(max_results=100), source_api
                ),
                source_api,
            )
            for idx, p in enumerate(pipelines):
                p_id = _opt_str(getattr(p, "pipeline_id", None)) or "unknown-pipeline"
                detail = (
                    self._safe_get_detail(
                        partial(client.pipelines.get, pipeline_id=p_id),
                        "databricks-sdk/pipelines.get",
                    )
                    if idx < 15 and p_id != "unknown-pipeline"
                    else None
                )
                spec = getattr(detail, "spec", None) if detail is not None else None
                p_name = (
                    _opt_str(getattr(detail, "name", None))
                    or _opt_str(getattr(p, "name", None))
                    or p_id
                )
                p_state = _enum_str(getattr(detail, "state", getattr(p, "state", None))).upper()
                raw_updates = getattr(detail, "latest_updates", None) if detail else None
                latest_update_state: str | None = None
                if isinstance(raw_updates, list) and raw_updates:
                    latest_update_state = _opt_str(getattr(raw_updates[0], "state", None))
                items.append(
                    DiscoveredResourceItem(
                        id=p_id,
                        name=p_name,
                        resource_type="pipeline",
                        workspace_id=workspace_id,
                        status=p_state,
                        creator=_opt_str(getattr(detail, "creator_user_name", None))
                        or _opt_str(getattr(p, "creator_user_name", None)),
                        source_api=source_api,
                        metadata={
                            "health": _opt_str(getattr(detail, "health", None))
                            or _opt_str(getattr(p, "health", None)),
                            "cluster_id": _opt_str(getattr(detail, "cluster_id", None))
                            or _opt_str(getattr(p, "cluster_id", None)),
                            "target": _opt_str(getattr(spec, "target", None)) if spec else None,
                            "catalog": _opt_str(getattr(spec, "catalog", None)) if spec else None,
                            "serverless": _opt_bool(getattr(spec, "serverless", None))
                            if spec
                            else None,
                            "continuous": _opt_bool(getattr(spec, "continuous", None))
                            if spec
                            else None,
                            "channel": _opt_str(getattr(spec, "channel", None)) if spec else None,
                            "edition": _opt_str(getattr(spec, "edition", None)) if spec else None,
                            "latest_updates_count": len(raw_updates)
                            if isinstance(raw_updates, list)
                            else None,
                            "latest_update_state": latest_update_state,
                        },
                        discovered_at=now,
                    )
                )
            return self._build_category_result(
                "pipelines", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result(
                "pipelines", workspace_id, source_api, exc, now
            ), []

    def discover_model_serving(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract Model Serving endpoints via serving_endpoints.list and optional .get."""
        source_api = "databricks-sdk/serving_endpoints.list"
        try:
            items: list[DiscoveredResourceItem] = []
            endpoints, has_more = self._call_with_retry(
                lambda: self._collect_sdk_iterable(client.serving_endpoints.list(), source_api),
                source_api,
            )
            for idx, ep in enumerate(endpoints):
                ep_name = _opt_str(getattr(ep, "name", None)) or "unknown-endpoint"
                detail = (
                    self._safe_get_detail(
                        partial(client.serving_endpoints.get, name=ep_name),
                        "databricks-sdk/serving_endpoints.get",
                    )
                    if idx < 15 and ep_name != "unknown-endpoint"
                    else None
                )
                src = detail or ep
                ep_state_obj = getattr(src, "state", None) or getattr(ep, "state", None)
                ep_ready = _opt_str(getattr(ep_state_obj, "ready", None)) if ep_state_obj else None
                ep_cfg_update = (
                    _opt_str(getattr(ep_state_obj, "config_update", None)) if ep_state_obj else None
                )
                ep_state = (ep_ready or ep_cfg_update or "UNKNOWN").upper()
                cfg = getattr(detail, "config", None) if detail is not None else None
                raw_entities = (
                    getattr(cfg, "served_entities", None) or getattr(cfg, "served_models", None)
                    if cfg is not None
                    else None
                )
                served_entities: list[dict[str, Any]] = []
                if isinstance(raw_entities, list):
                    for ent in raw_entities:
                        served_entities.append(
                            {
                                "name": _opt_str(getattr(ent, "name", None)),
                                "entity_name": _opt_str(
                                    getattr(ent, "entity_name", None)
                                    or getattr(ent, "model_name", None)
                                ),
                                "entity_version": _opt_str(
                                    getattr(ent, "entity_version", None)
                                    or getattr(ent, "model_version", None)
                                ),
                                "workload_size": _opt_str(getattr(ent, "workload_size", None)),
                                "workload_type": _opt_str(getattr(ent, "workload_type", None)),
                                "scale_to_zero_enabled": _opt_bool(
                                    getattr(ent, "scale_to_zero_enabled", None)
                                ),
                            }
                        )
                traffic_cfg = getattr(cfg, "traffic_config", None) if cfg is not None else None
                routes = getattr(traffic_cfg, "routes", None) if traffic_cfg is not None else None
                items.append(
                    DiscoveredResourceItem(
                        id=ep_name,
                        name=ep_name,
                        resource_type="serving_endpoint",
                        workspace_id=workspace_id,
                        status=ep_state,
                        creator=_opt_str(getattr(src, "creator", None))
                        or _opt_str(getattr(ep, "creator", None)),
                        source_api=source_api,
                        metadata={
                            "creation_timestamp": _normalize_timestamp(
                                getattr(src, "creation_timestamp", None)
                            )
                            or _normalize_timestamp(getattr(ep, "creation_timestamp", None)),
                            "last_updated_timestamp": _normalize_timestamp(
                                getattr(src, "last_updated_timestamp", None)
                            )
                            or _normalize_timestamp(getattr(ep, "last_updated_timestamp", None)),
                            "task": _opt_str(getattr(src, "task", None))
                            or _opt_str(getattr(ep, "task", None)),
                            "served_entities": served_entities or None,
                            "traffic_routes_count": len(routes)
                            if isinstance(routes, list)
                            else None,
                        },
                        discovered_at=now,
                    )
                )
            return self._build_category_result(
                "model_serving", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result(
                "model_serving", workspace_id, source_api, exc, now
            ), []

    def discover_mlflow(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract MLflow Experiments, Runs, Run details, and Artifact metadata (zero downloads)."""
        source_api = "databricks-sdk/experiments.search_experiments+search_runs"
        try:
            items: list[DiscoveredResourceItem] = []
            try:
                experiments, has_more = self._call_with_retry(
                    lambda: self._collect_sdk_iterable(
                        client.experiments.search_experiments(max_results=100), source_api
                    ),
                    source_api,
                )
            except Exception as search_exc:
                kind, _, _ = classify_http_and_sdk_error(search_exc)
                if (isinstance(search_exc, AttributeError) or kind == "not_supported") and hasattr(
                    client.experiments, "list_experiments"
                ):
                    experiments, has_more = self._call_with_retry(
                        lambda: self._collect_sdk_iterable(
                            client.experiments.list_experiments(max_results=100),
                            "databricks-sdk/experiments.list_experiments",
                        ),
                        "databricks-sdk/experiments.list_experiments",
                    )
                else:
                    raise

            exp_ids: list[str] = []
            for exp in experiments:
                exp_id = _opt_str(getattr(exp, "experiment_id", None))
                if not exp_id:
                    continue
                exp_ids.append(exp_id)
                exp_name = _opt_str(getattr(exp, "name", None)) or exp_id
                exp_stage = _opt_str(getattr(exp, "lifecycle_stage", None)) or "ACTIVE"
                items.append(
                    DiscoveredResourceItem(
                        id=exp_id,
                        name=exp_name,
                        resource_type="mlflow_experiment",
                        workspace_id=workspace_id,
                        status=exp_stage.upper(),
                        creator=None,
                        source_api="databricks-sdk/experiments.search_experiments",
                        metadata={
                            "artifact_location": _opt_str(getattr(exp, "artifact_location", None)),
                            "creation_time": _normalize_timestamp(
                                getattr(exp, "creation_time", None)
                            ),
                            "last_update_time": _normalize_timestamp(
                                getattr(exp, "last_update_time", None)
                            ),
                        },
                        discovered_at=now,
                    )
                )

            if exp_ids:
                try:
                    runs, runs_more = self._call_with_retry(
                        lambda: self._collect_sdk_iterable(
                            client.experiments.search_runs(
                                experiment_ids=exp_ids[:100], max_results=50
                            ),
                            "databricks-sdk/experiments.search_runs",
                            max_items=50,
                        ),
                        "databricks-sdk/experiments.search_runs",
                    )
                    # Runs are a most-recent window; more experiments than the API accepts per
                    # search_runs call (100) also means the run list is not exhaustive.
                    has_more = has_more or runs_more or len(exp_ids) > 100
                    for idx, run in enumerate(runs):
                        info = getattr(run, "info", None)
                        run_id = _opt_str(getattr(info, "run_id", None)) if info else None
                        if not run_id:
                            continue
                        run_name = (
                            _opt_str(getattr(info, "run_name", None)) if info else None
                        ) or run_id
                        run_status = (
                            _opt_str(getattr(info, "status", None)) if info else None
                        ) or "UNKNOWN"

                        run_data = getattr(run, "data", None)
                        artifacts_count: int | None = None
                        artifact_paths: list[str] | None = None

                        if idx < 10:
                            run_detail = self._safe_get_detail(
                                partial(client.experiments.get_run, run_id=run_id),
                                "databricks-sdk/experiments.get_run",
                            )
                            if run_detail is not None:
                                r_obj = getattr(run_detail, "run", None) or run_detail
                                d_info = getattr(r_obj, "info", None)
                                if d_info is not None:
                                    info = d_info
                                d_data = getattr(r_obj, "data", None)
                                if d_data is not None:
                                    run_data = d_data
                            raw_artifacts = self._safe_get_detail(
                                partial(self._collect_run_artifacts, client, run_id),
                                "databricks-sdk/experiments.list_artifacts",
                            )
                            if isinstance(raw_artifacts, tuple) and isinstance(
                                raw_artifacts[0], list
                            ):
                                file_infos = raw_artifacts[0]
                                paths = [
                                    p
                                    for fi in file_infos
                                    if (p := _opt_str(getattr(fi, "path", None))) is not None
                                ]
                                artifacts_count = len(paths)
                                artifact_paths = paths[:10]

                        metrics_list = getattr(run_data, "metrics", None) if run_data else None
                        params_list = getattr(run_data, "params", None) if run_data else None
                        tags_list = getattr(run_data, "tags", None) if run_data else None
                        sample_metrics: dict[str, float] = {}
                        if isinstance(metrics_list, list):
                            for m in metrics_list[:5]:
                                m_key = _opt_str(getattr(m, "key", None))
                                m_val = getattr(m, "value", None)
                                if (
                                    m_key
                                    and isinstance(m_val, (int, float))
                                    and not isinstance(m_val, bool)
                                ):
                                    sample_metrics[m_key] = float(m_val)

                        items.append(
                            DiscoveredResourceItem(
                                id=run_id,
                                name=run_name,
                                resource_type="mlflow_run",
                                workspace_id=workspace_id,
                                status=run_status.upper(),
                                creator=_mask_principal(
                                    _opt_str(getattr(info, "user_id", None)) if info else None
                                ),
                                source_api="databricks-sdk/experiments.search_runs",
                                metadata={
                                    "experiment_id": _opt_str(getattr(info, "experiment_id", None))
                                    if info
                                    else None,
                                    "start_time": _normalize_timestamp(
                                        getattr(info, "start_time", None)
                                    )
                                    if info
                                    else None,
                                    "end_time": _normalize_timestamp(
                                        getattr(info, "end_time", None)
                                    )
                                    if info
                                    else None,
                                    "metrics_count": len(metrics_list)
                                    if isinstance(metrics_list, list)
                                    else None,
                                    "params_count": len(params_list)
                                    if isinstance(params_list, list)
                                    else None,
                                    "tags_count": len(tags_list)
                                    if isinstance(tags_list, list)
                                    else None,
                                    "sample_metrics": sample_metrics or None,
                                    "artifacts_count": artifacts_count,
                                    "artifact_paths": artifact_paths,
                                },
                                discovered_at=now,
                            )
                        )
                except Exception as run_exc:
                    logger.debug("mlflow_search_runs_skipped", error=str(run_exc))

            return self._build_category_result(
                "mlflow", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result(
                "mlflow", workspace_id, source_api, exc, now
            ), []

    def discover_unity_catalog(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract Unity Catalog catalogs via catalogs.list."""
        source_api = "databricks-sdk/catalogs.list"
        try:
            items: list[DiscoveredResourceItem] = []
            catalogs, has_more = self._call_with_retry(
                lambda: self._collect_sdk_iterable(
                    client.catalogs.list(include_browse=True, max_results=100), source_api
                ),
                source_api,
            )
            for cat in catalogs:
                c_name = _opt_str(getattr(cat, "name", None)) or "unknown-catalog"
                items.append(
                    DiscoveredResourceItem(
                        id=c_name,
                        name=c_name,
                        resource_type="catalog",
                        workspace_id=workspace_id,
                        status="ACTIVE",
                        creator=_opt_str(getattr(cat, "owner", None)),
                        source_api=source_api,
                        metadata={
                            "comment": _opt_str(getattr(cat, "comment", None)),
                            "owner": _opt_str(getattr(cat, "owner", None)),
                            "catalog_type": _opt_str(getattr(cat, "catalog_type", None)),
                            "created_at": _normalize_timestamp(getattr(cat, "created_at", None)),
                            "updated_at": _normalize_timestamp(getattr(cat, "updated_at", None)),
                        },
                        discovered_at=now,
                    )
                )
            return self._build_category_result(
                "unity_catalog", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result(
                "unity_catalog", workspace_id, source_api, exc, now
            ), []

    def discover_apps(
        self, client: WorkspaceClient, workspace_id: str, now: datetime
    ) -> tuple[CategoryDiscoveryResult, list[DiscoveredResourceItem]]:
        """Extract Databricks Apps via apps.list and optional apps.get enrichment."""
        source_api = "databricks-sdk/apps.list"
        try:
            items: list[DiscoveredResourceItem] = []
            apps, has_more = self._call_with_retry(
                lambda: self._collect_sdk_iterable(client.apps.list(page_size=50), source_api),
                source_api,
            )
            for idx, app in enumerate(apps):
                a_name = _opt_str(getattr(app, "name", None)) or "unknown-app"
                detail = (
                    self._safe_get_detail(
                        partial(client.apps.get, name=a_name),
                        "databricks-sdk/apps.get",
                    )
                    if idx < 15 and a_name != "unknown-app"
                    else None
                )
                src = detail or app
                comp_status = getattr(src, "compute_status", None) or getattr(
                    app, "compute_status", None
                )
                a_state = _enum_str(
                    getattr(comp_status, "state", None) if comp_status else None,
                    default="ACTIVE",
                ).upper()
                active_dep = getattr(src, "active_deployment", None)
                dep_status = getattr(active_dep, "status", None) if active_dep else None
                raw_resources = getattr(src, "resources", None)
                res_summary: list[dict[str, str | None]] = []
                if isinstance(raw_resources, list):
                    for rr in raw_resources[:10]:
                        res_summary.append(
                            {
                                "name": _opt_str(getattr(rr, "name", None)),
                                "description": _opt_str(getattr(rr, "description", None)),
                            }
                        )
                items.append(
                    DiscoveredResourceItem(
                        id=_opt_str(getattr(src, "id", None)) or a_name,
                        name=a_name,
                        resource_type="app",
                        workspace_id=workspace_id,
                        status=a_state,
                        creator=_opt_str(getattr(src, "creator", None))
                        or _opt_str(getattr(app, "creator", None)),
                        source_api=source_api,
                        metadata={
                            "url": _opt_str(getattr(src, "url", None))
                            or _opt_str(getattr(app, "url", None)),
                            "create_time": _normalize_timestamp(getattr(src, "create_time", None))
                            or _normalize_timestamp(getattr(app, "create_time", None)),
                            "update_time": _normalize_timestamp(getattr(src, "update_time", None))
                            or _normalize_timestamp(getattr(app, "update_time", None)),
                            "compute_size": _opt_str(getattr(src, "compute_size", None)),
                            "compute_min_instances": _opt_int(
                                getattr(src, "compute_min_instances", None)
                            ),
                            "compute_max_instances": _opt_int(
                                getattr(src, "compute_max_instances", None)
                            ),
                            "active_deployment_id": _opt_str(
                                getattr(active_dep, "deployment_id", None)
                            )
                            if active_dep
                            else None,
                            "active_deployment_status": _opt_str(getattr(dep_status, "state", None))
                            if dep_status
                            else None,
                            "resources_count": len(raw_resources)
                            if isinstance(raw_resources, list)
                            else None,
                            "resources_summary": res_summary or None,
                        },
                        discovered_at=now,
                    )
                )
            return self._build_category_result(
                "apps", workspace_id, source_api, items, now, has_more=has_more
            ), items
        except Exception as exc:
            return self._build_error_category_result("apps", workspace_id, source_api, exc, now), []

    def discover_unity_catalog_hierarchy(
        self,
        client: WorkspaceClient | None,
        connection_id: str,
        workspace_id: str,
        workspace_url: str,
        now: datetime,
        catalog_name: str | None = None,
        include_permissions: bool = True,
        init_error: Exception | None = None,
        init_error_text: str | None = None,
        workspace_name: str | None = None,
        environment: str | None = None,
    ) -> UnityCatalogMetadataResponse:
        """Discover live Unity Catalog catalogs, schemas, tables, columns, properties, and grants."""
        if client is None:
            if init_error is not None:
                status, state, http_status, err_code, err_msg = self._classify_error_detailed(
                    init_error
                )
            else:
                status = CategoryDiscoveryStatus.CONNECTION_ERROR
                state = DatabricksResourceState.UNAVAILABLE
                http_status = None
                err_code = "CONNECTION_ERROR"
                err_msg = init_error_text or "Databricks client unavailable."
            return UnityCatalogMetadataResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=status,
                discovery_state=state,
                retrieved_at=now,
                http_status=http_status,
                error_code=err_code,
                error_message=err_msg,
            )

        try:
            raw_catalogs, has_more_catalogs = self._call_with_retry(
                partial(
                    self._collect_sdk_iterable,
                    client.catalogs.list(include_browse=True, max_results=100),
                    "databricks-sdk/catalogs.list",
                    max_items=50,
                ),
                "databricks-sdk/catalogs.list",
            )
        except Exception as exc:
            status, state, http_status, err_code, err_msg = self._classify_error_detailed(exc)
            return UnityCatalogMetadataResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=status,
                discovery_state=state,
                retrieved_at=now,
                http_status=http_status,
                error_code=err_code,
                error_message=err_msg,
            )

        catalog_items: list[UnityCatalogCatalogItem] = []
        total_schemas = 0
        total_tables = 0
        has_partial_failure = False
        failure_states: set[DatabricksResourceState] = set()

        for cat in raw_catalogs[:15]:
            c_name = _opt_str(getattr(cat, "name", None))
            if not c_name:
                continue
            if catalog_name and c_name != catalog_name:
                continue

            schemas_list: list[UnityCatalogSchemaItem] = []
            schemas_state = DatabricksResourceState.NO_DATA
            schemas_err: str | None = None
            try:
                raw_schemas, _ = self._call_with_retry(
                    partial(
                        self._collect_sdk_iterable,
                        client.schemas.list(
                            catalog_name=c_name, include_browse=True, max_results=100
                        ),
                        "databricks-sdk/schemas.list",
                        max_items=50,
                    ),
                    "databricks-sdk/schemas.list",
                )
                for sch in raw_schemas[:25]:
                    s_name = _opt_str(getattr(sch, "name", None))
                    if not s_name:
                        continue
                    tables_list: list[UnityCatalogTableItem] = []
                    tables_state = DatabricksResourceState.NO_DATA
                    tables_err: str | None = None
                    try:
                        raw_tables, _ = self._call_with_retry(
                            partial(
                                self._collect_sdk_iterable,
                                client.tables.list(
                                    catalog_name=c_name,
                                    schema_name=s_name,
                                    include_browse=True,
                                    omit_columns=False,
                                    omit_properties=False,
                                    max_results=100,
                                ),
                                "databricks-sdk/tables.list",
                                max_items=50,
                            ),
                            "databricks-sdk/tables.list",
                        )
                        for tbl in raw_tables[:30]:
                            t_name = _opt_str(getattr(tbl, "name", None))
                            if not t_name:
                                continue
                            full_name = (
                                _opt_str(getattr(tbl, "full_name", None))
                                or f"{c_name}.{s_name}.{t_name}"
                            )
                            src_tbl = tbl

                            raw_props = getattr(src_tbl, "properties", None)
                            props: dict[str, str] = {}
                            if isinstance(raw_props, dict):
                                for pk, pv in raw_props.items():
                                    k_str = _opt_str(pk)
                                    v_str = _opt_str(pv)
                                    if k_str is not None and v_str is not None:
                                        props[k_str] = v_str

                            cols: list[UnityCatalogColumnItem] = []
                            raw_cols = getattr(src_tbl, "columns", None)
                            if not isinstance(raw_cols, list):
                                raw_cols = getattr(tbl, "columns", None)
                            if isinstance(raw_cols, list):
                                for col in raw_cols:
                                    col_name = _opt_str(getattr(col, "name", None))
                                    if col_name:
                                        cols.append(
                                            UnityCatalogColumnItem(
                                                name=col_name,
                                                type_text=_opt_str(getattr(col, "type_text", None))
                                                or _opt_str(getattr(col, "type_name", None))
                                                or "STRING",
                                                type_name=_opt_str(getattr(col, "type_name", None)),
                                                nullable=bool(getattr(col, "nullable", True)),
                                                comment=_opt_str(getattr(col, "comment", None)),
                                            )
                                        )

                            perms: list[UnityCatalogPermissionItem] = []
                            perms_state = DatabricksResourceState.NO_DATA
                            perms_err: str | None = None
                            if include_permissions:
                                try:
                                    eff = self._call_with_retry(
                                        partial(
                                            client.grants.get_effective,
                                            securable_type="TABLE",
                                            full_name=full_name,
                                        ),
                                        "databricks-sdk/grants.get_effective",
                                    )
                                    priv_assignments = getattr(eff, "privilege_assignments", None)
                                    if (
                                        not isinstance(priv_assignments, list)
                                        or len(priv_assignments) == 0
                                    ) and hasattr(client.grants, "get"):
                                        direct_res = self._safe_get_detail(
                                            partial(
                                                client.grants.get,
                                                securable_type="TABLE",
                                                full_name=full_name,
                                            ),
                                            "databricks-sdk/grants.get",
                                        )
                                        direct_pa = (
                                            getattr(direct_res, "privilege_assignments", None)
                                            if direct_res is not None
                                            else None
                                        )
                                        if isinstance(direct_pa, list) and direct_pa:
                                            priv_assignments = direct_pa

                                    if isinstance(priv_assignments, list):
                                        for pa in priv_assignments:
                                            principal = (
                                                _opt_str(getattr(pa, "principal", None))
                                                or "unknown"
                                            )
                                            privs = getattr(pa, "privileges", None)
                                            priv_names = [
                                                _enum_str(getattr(p, "privilege", p))
                                                for p in (privs if isinstance(privs, list) else [])
                                            ]
                                            perms.append(
                                                UnityCatalogPermissionItem(
                                                    principal=_mask_principal(principal)
                                                    or principal,
                                                    privileges=priv_names,
                                                )
                                            )
                                        perms_state = (
                                            DatabricksResourceState.LIVE
                                            if perms
                                            else DatabricksResourceState.NO_DATA
                                        )
                                    else:
                                        perms_state = DatabricksResourceState.UNAVAILABLE
                                except Exception as perm_exc:
                                    _, p_state, _, _, p_msg = self._classify_error_detailed(
                                        perm_exc
                                    )
                                    perms_state = p_state
                                    perms_err = p_msg
                                    has_partial_failure = True
                                    failure_states.add(p_state)

                            tables_list.append(
                                UnityCatalogTableItem(
                                    catalog_name=c_name,
                                    schema_name=s_name,
                                    name=t_name,
                                    full_name=full_name,
                                    table_type=_opt_str(getattr(src_tbl, "table_type", None))
                                    or _opt_str(getattr(tbl, "table_type", None)),
                                    data_source_format=_opt_str(
                                        getattr(src_tbl, "data_source_format", None)
                                    )
                                    or _opt_str(getattr(tbl, "data_source_format", None)),
                                    owner=_opt_str(getattr(src_tbl, "owner", None))
                                    or _opt_str(getattr(tbl, "owner", None)),
                                    storage_location=_opt_str(
                                        getattr(src_tbl, "storage_location", None)
                                    )
                                    or _opt_str(getattr(tbl, "storage_location", None)),
                                    comment=_opt_str(getattr(src_tbl, "comment", None))
                                    or _opt_str(getattr(tbl, "comment", None)),
                                    created_at=_normalize_timestamp(
                                        getattr(src_tbl, "created_at", None)
                                    )
                                    or _normalize_timestamp(getattr(tbl, "created_at", None)),
                                    updated_at=_normalize_timestamp(
                                        getattr(src_tbl, "updated_at", None)
                                    )
                                    or _normalize_timestamp(getattr(tbl, "updated_at", None)),
                                    properties=props,
                                    columns=cols,
                                    permissions=perms,
                                    permissions_status=perms_state,
                                    permissions_error=perms_err,
                                )
                            )
                        tables_state = (
                            DatabricksResourceState.PARTIAL
                            if tables_list
                            and any(
                                t.permissions_status
                                in (
                                    DatabricksResourceState.ACCESS_DENIED,
                                    DatabricksResourceState.UNAVAILABLE,
                                    DatabricksResourceState.AUTH_FAILED,
                                )
                                for t in tables_list
                            )
                            else (
                                DatabricksResourceState.LIVE
                                if tables_list
                                else DatabricksResourceState.NO_DATA
                            )
                        )
                        total_tables += len(tables_list)
                    except Exception as tbl_exc:
                        _, tables_state, _, _, tables_err = self._classify_error_detailed(tbl_exc)
                        has_partial_failure = True
                        failure_states.add(tables_state)

                    schemas_list.append(
                        UnityCatalogSchemaItem(
                            catalog_name=c_name,
                            name=s_name,
                            full_name=f"{c_name}.{s_name}",
                            owner=_opt_str(getattr(sch, "owner", None)),
                            comment=_opt_str(getattr(sch, "comment", None)),
                            created_at=_normalize_timestamp(getattr(sch, "created_at", None)),
                            updated_at=_normalize_timestamp(getattr(sch, "updated_at", None)),
                            tables=tables_list,
                            tables_status=tables_state,
                            tables_error=tables_err,
                        )
                    )
                schemas_state = (
                    DatabricksResourceState.PARTIAL
                    if schemas_list
                    and any(
                        s.tables_status
                        in (
                            DatabricksResourceState.ACCESS_DENIED,
                            DatabricksResourceState.UNAVAILABLE,
                            DatabricksResourceState.AUTH_FAILED,
                            DatabricksResourceState.PARTIAL,
                        )
                        for s in schemas_list
                    )
                    else (
                        DatabricksResourceState.LIVE
                        if schemas_list
                        else DatabricksResourceState.NO_DATA
                    )
                )
                total_schemas += len(schemas_list)
            except Exception as sch_exc:
                _, schemas_state, _, _, schemas_err = self._classify_error_detailed(sch_exc)
                has_partial_failure = True
                failure_states.add(schemas_state)

            catalog_items.append(
                UnityCatalogCatalogItem(
                    name=c_name,
                    owner=_opt_str(getattr(cat, "owner", None)),
                    comment=_opt_str(getattr(cat, "comment", None)),
                    catalog_type=_opt_str(getattr(cat, "catalog_type", None)),
                    created_at=_normalize_timestamp(getattr(cat, "created_at", None)),
                    updated_at=_normalize_timestamp(getattr(cat, "updated_at", None)),
                    schemas=schemas_list,
                    schemas_status=schemas_state,
                    schemas_error=schemas_err,
                )
            )

        http_status_out: int | None = None
        err_code_out: str | None = None
        err_msg_out: str | None = None
        if catalog_items:
            status = CategoryDiscoveryStatus.AVAILABLE
            state = (
                DatabricksResourceState.PARTIAL
                if has_partial_failure
                else DatabricksResourceState.LIVE
            )
            if has_partial_failure:
                err_code_out = "PARTIAL_DISCOVERY"
                err_msg_out = "One or more Unity Catalog child schemas, table details, or permission lookups failed; preserving accessible metadata."
        elif has_partial_failure:
            if DatabricksResourceState.AUTH_FAILED in failure_states:
                status = CategoryDiscoveryStatus.AUTH_FAILED
                state = DatabricksResourceState.AUTH_FAILED
                http_status_out = 401
                err_code_out = "HTTP_401"
            elif DatabricksResourceState.ACCESS_DENIED in failure_states:
                status = CategoryDiscoveryStatus.PERMISSION_DENIED
                state = DatabricksResourceState.ACCESS_DENIED
                http_status_out = 403
                err_code_out = "HTTP_403"
            else:
                status = CategoryDiscoveryStatus.CONNECTION_ERROR
                state = DatabricksResourceState.UNAVAILABLE
                err_code_out = "UNAVAILABLE"
            err_msg_out = "Unity Catalog metadata retrieval failed."
        else:
            status = CategoryDiscoveryStatus.NO_RESOURCES_FOUND
            state = DatabricksResourceState.NO_DATA

        return UnityCatalogMetadataResponse(
            connection_id=connection_id,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            workspace_url=workspace_url,
            environment=environment,
            status=status,
            discovery_state=state,
            retrieved_at=now,
            catalogs=catalog_items,
            total_catalogs=len(catalog_items),
            total_schemas=total_schemas,
            total_tables=total_tables,
            has_more=has_more_catalogs,
            next_page_token=None,
            http_status=http_status_out,
            error_code=err_code_out,
            error_message=err_msg_out,
        )

    def discover_system_tables_metadata(
        self,
        client: WorkspaceClient | None,
        connection_id: str,
        workspace_id: str,
        workspace_url: str,
        now: datetime,
        init_error: Exception | None = None,
        init_error_text: str | None = None,
        workspace_name: str | None = None,
        environment: str | None = None,
        warehouse_id: str | None = None,
    ) -> SystemTablesMetadataResponse:
        """Discover available System Table schemas, tables, columns, and SELECT grants without SQL execution."""
        if client is None:
            if init_error is not None:
                status, state, http_status, err_code, err_msg = self._classify_error_detailed(
                    init_error
                )
            else:
                status = CategoryDiscoveryStatus.CONNECTION_ERROR
                state = DatabricksResourceState.UNAVAILABLE
                http_status = None
                err_code = "CONNECTION_ERROR"
                err_msg = init_error_text or "Databricks client unavailable."
            return SystemTablesMetadataResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=status,
                discovery_state=state,
                retrieved_at=now,
                target_schemas=list(_SYSTEM_TARGET_SCHEMAS),
                missing_schemas=list(_SYSTEM_TARGET_SCHEMAS),
                http_status=http_status,
                error_code=err_code,
                error_message=err_msg,
            )

        try:
            raw_schemas, has_more_schemas = self._call_with_retry(
                partial(
                    self._collect_sdk_iterable,
                    client.schemas.list(
                        catalog_name="system", include_browse=True, max_results=100
                    ),
                    "databricks-sdk/schemas.list(catalog=system)",
                    max_items=100,
                ),
                "databricks-sdk/schemas.list(catalog=system)",
            )
        except Exception as exc:
            status, state, http_status, err_code, err_msg = self._classify_error_detailed(exc)
            return SystemTablesMetadataResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=status,
                discovery_state=state,
                retrieved_at=now,
                target_schemas=list(_SYSTEM_TARGET_SCHEMAS),
                missing_schemas=list(_SYSTEM_TARGET_SCHEMAS),
                http_status=http_status,
                error_code=err_code,
                error_message=err_msg,
            )

        discovered_schema_names: list[str] = []
        for sch in raw_schemas:
            s_name = _opt_str(getattr(sch, "name", None))
            if s_name and s_name != "information_schema":
                discovered_schema_names.append(s_name)

        discovered_set = set(discovered_schema_names)
        missing_schemas = [s for s in _SYSTEM_TARGET_SCHEMAS if s not in discovered_set]

        # Inspect target schemas present (plus any additional discovered system schemas)
        ordered_schemas = [s for s in _SYSTEM_TARGET_SCHEMAS if s in discovered_set] + [
            s for s in discovered_schema_names if s not in _SYSTEM_TARGET_SCHEMAS
        ]

        tables: list[LiveSystemTableItem] = []
        ready_registry: list[TypedSystemTableRegistryEntry] = []
        detail_fetch_count = 0

        for sch_name in ordered_schemas:
            domain = _SYSTEM_SCHEMA_DOMAIN_MAP.get(sch_name, sch_name)
            try:
                raw_tables, _ = self._call_with_retry(
                    partial(
                        self._collect_sdk_iterable,
                        client.tables.list(
                            catalog_name="system",
                            schema_name=sch_name,
                            include_browse=True,
                            omit_columns=False,
                            omit_properties=False,
                            max_results=100,
                        ),
                        f"databricks-sdk/tables.list(system.{sch_name})",
                        max_items=50,
                    ),
                    f"databricks-sdk/tables.list(system.{sch_name})",
                )
                if not raw_tables:
                    tables.append(
                        LiveSystemTableItem(
                            schema_name=sch_name,
                            table_name="*",
                            full_name=f"system.{sch_name}",
                            domain=domain,
                            schema_discovered=True,
                            table_discovered=False,
                            metadata_status=DatabricksResourceState.NO_DATA,
                            note=f"Schema system.{sch_name} exists, but no tables are visible to caller.",
                        )
                    )
                    continue
                for tbl in raw_tables:
                    t_name = _opt_str(getattr(tbl, "name", None)) or "unknown"
                    full_name = (
                        _opt_str(getattr(tbl, "full_name", None)) or f"system.{sch_name}.{t_name}"
                    )
                    src_tbl = tbl
                    raw_cols = getattr(tbl, "columns", None)
                    if (
                        not isinstance(raw_cols, list) or len(raw_cols) == 0
                    ) and detail_fetch_count < 25:
                        detail_fetch_count += 1
                        tbl_detail = self._safe_get_detail(
                            partial(
                                client.tables.get,
                                full_name=full_name,
                                include_delta_metadata=True,
                                include_browse=True,
                            ),
                            f"databricks-sdk/tables.get({full_name})",
                        )
                        if tbl_detail is not None:
                            src_tbl = tbl_detail

                    cols: list[UnityCatalogColumnItem] = []
                    detail_cols = getattr(src_tbl, "columns", None)
                    if not isinstance(detail_cols, list):
                        detail_cols = raw_cols
                    if isinstance(detail_cols, list):
                        for col in detail_cols:
                            col_name = _opt_str(getattr(col, "name", None))
                            if col_name:
                                cols.append(
                                    UnityCatalogColumnItem(
                                        name=col_name,
                                        type_text=_opt_str(getattr(col, "type_text", None))
                                        or _opt_str(getattr(col, "type_name", None))
                                        or "STRING",
                                        type_name=_opt_str(getattr(col, "type_name", None)),
                                        nullable=bool(getattr(col, "nullable", True)),
                                        comment=_opt_str(getattr(col, "comment", None)),
                                    )
                                )

                    eff_privs: list[str] = []
                    select_verified: bool | None = None
                    grant_note = "Metadata visible via Unity Catalog REST API (no SQL executed)."
                    try:
                        eff = self._call_with_retry(
                            partial(
                                client.grants.get_effective,
                                securable_type="TABLE",
                                full_name=full_name,
                            ),
                            f"databricks-sdk/grants.get_effective({full_name})",
                        )
                        priv_assignments = getattr(eff, "privilege_assignments", None)
                        if (
                            not isinstance(priv_assignments, list) or len(priv_assignments) == 0
                        ) and hasattr(client.grants, "get"):
                            direct_eff = self._safe_get_detail(
                                partial(
                                    client.grants.get,
                                    securable_type="TABLE",
                                    full_name=full_name,
                                ),
                                f"databricks-sdk/grants.get({full_name})",
                            )
                            direct_pa = (
                                getattr(direct_eff, "privilege_assignments", None)
                                if direct_eff is not None
                                else None
                            )
                            if isinstance(direct_pa, list) and direct_pa:
                                priv_assignments = direct_pa

                        if isinstance(priv_assignments, list):
                            for pa in priv_assignments:
                                raw_p = getattr(pa, "privileges", None)
                                if isinstance(raw_p, list):
                                    for p in raw_p:
                                        p_str = _enum_str(getattr(p, "privilege", p))
                                        if p_str not in eff_privs:
                                            eff_privs.append(p_str)
                            select_verified = any(
                                p.upper() in ("SELECT", "ALL_PRIVILEGES") for p in eff_privs
                            )
                            grant_note = (
                                "Metadata visible and SELECT privilege verified."
                                if select_verified
                                else "Metadata visible; row-level SELECT grant not verified for caller."
                            )
                    except Exception as grant_exc:
                        _, g_state, _, _, g_msg = self._classify_error_detailed(grant_exc)
                        select_verified = (
                            False if g_state == DatabricksResourceState.ACCESS_DENIED else None
                        )
                        grant_note = f"Metadata visible; effective grants check returned {g_state.value} ({g_msg})."

                    tables.append(
                        LiveSystemTableItem(
                            schema_name=sch_name,
                            table_name=t_name,
                            full_name=full_name,
                            domain=domain,
                            table_type=_opt_str(getattr(src_tbl, "table_type", None))
                            or _opt_str(getattr(tbl, "table_type", None)),
                            data_source_format=_opt_str(
                                getattr(src_tbl, "data_source_format", None)
                            )
                            or _opt_str(getattr(tbl, "data_source_format", None)),
                            owner=_opt_str(getattr(src_tbl, "owner", None))
                            or _opt_str(getattr(tbl, "owner", None)),
                            comment=_opt_str(getattr(src_tbl, "comment", None))
                            or _opt_str(getattr(tbl, "comment", None)),
                            columns_count=len(cols),
                            columns=cols,
                            effective_privileges=eff_privs,
                            schema_discovered=True,
                            table_discovered=True,
                            metadata_status=DatabricksResourceState.LIVE,
                            select_grant_verified=select_verified,
                            note=grant_note,
                        )
                    )

                    # Check required columns
                    discovered_col_names = {c.name.lower() for c in cols}
                    required_cols = _REQUIRED_COLUMNS_BY_TABLE.get(full_name.lower())
                    columns_verified = bool(cols) and (
                        required_cols is None or required_cols.issubset(discovered_col_names)
                    )

                    clean_wh = warehouse_id.strip() if warehouse_id else None

                    # Only mark ready when:
                    # 1. Target system schema is in M3 registry schemas
                    # 2. Columns are verified
                    # 3. SELECT permission is explicitly confirmed (never assumed from metadata alone)
                    # 4. Warehouse configuration is identified (non-empty warehouse_id)
                    if (
                        sch_name in _M3_REGISTRY_SCHEMAS
                        and columns_verified
                        and select_verified is True
                        and clean_wh is not None
                    ):
                        ready_registry.append(
                            TypedSystemTableRegistryEntry(
                                full_name=full_name,
                                domain=domain,
                                exists=True,
                                metadata_status=DatabricksResourceState.LIVE,
                                select_grant_verified=True,
                                column_types={c.name: c.type_text for c in cols},
                                warehouse_id=clean_wh,
                            )
                        )
            except Exception as tbl_exc:
                _, t_state, _, _, t_msg = self._classify_error_detailed(tbl_exc)
                tables.append(
                    LiveSystemTableItem(
                        schema_name=sch_name,
                        table_name="*",
                        full_name=f"system.{sch_name}",
                        domain=domain,
                        schema_discovered=True,
                        table_discovered=False,
                        metadata_status=t_state,
                        note=t_msg,
                    )
                )

        has_live_tables = any(t.metadata_status == DatabricksResourceState.LIVE for t in tables)
        failed_tables = [
            t
            for t in tables
            if t.metadata_status
            in (
                DatabricksResourceState.ACCESS_DENIED,
                DatabricksResourceState.AUTH_FAILED,
                DatabricksResourceState.UNAVAILABLE,
            )
        ]

        http_status_out: int | None = None
        err_code_out: str | None = None
        err_msg_out: str | None = None
        if has_live_tables and failed_tables:
            overall_status = CategoryDiscoveryStatus.AVAILABLE
            overall_state = DatabricksResourceState.PARTIAL
            err_code_out = "PARTIAL_SYSTEM_TABLES"
            err_msg_out = "Some system.* schemas succeeded while others were denied or unavailable."
        elif has_live_tables:
            overall_status = CategoryDiscoveryStatus.AVAILABLE
            overall_state = DatabricksResourceState.LIVE
        elif failed_tables:
            states = {t.metadata_status for t in failed_tables}
            if DatabricksResourceState.AUTH_FAILED in states:
                overall_status = CategoryDiscoveryStatus.AUTH_FAILED
                overall_state = DatabricksResourceState.AUTH_FAILED
                http_status_out = 401
                err_code_out = "HTTP_401"
            elif DatabricksResourceState.ACCESS_DENIED in states:
                overall_status = CategoryDiscoveryStatus.PERMISSION_DENIED
                overall_state = DatabricksResourceState.ACCESS_DENIED
                http_status_out = 403
                err_code_out = "HTTP_403"
            else:
                overall_status = CategoryDiscoveryStatus.CONNECTION_ERROR
                overall_state = DatabricksResourceState.UNAVAILABLE
                err_code_out = "UNAVAILABLE"
            err_msg_out = failed_tables[0].note
        elif discovered_schema_names:
            overall_status = CategoryDiscoveryStatus.NO_RESOURCES_FOUND
            overall_state = DatabricksResourceState.NO_DATA
        else:
            overall_status = CategoryDiscoveryStatus.NO_RESOURCES_FOUND
            overall_state = DatabricksResourceState.NO_DATA

        return SystemTablesMetadataResponse(
            connection_id=connection_id,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            workspace_url=workspace_url,
            environment=environment,
            status=overall_status,
            discovery_state=overall_state,
            retrieved_at=now,
            target_schemas=list(_SYSTEM_TARGET_SCHEMAS),
            discovered_schemas=discovered_schema_names,
            missing_schemas=missing_schemas,
            tables=tables,
            billing_ingestion_ready_tables=ready_registry,
            total_tables=len(tables),
            has_more=has_more_schemas,
            next_page_token=None,
            http_status=http_status_out,
            error_code=err_code_out,
            error_message=err_msg_out,
        )

    def discover_query_history(
        self,
        client: WorkspaceClient | None,
        connection_id: str,
        workspace_id: str,
        workspace_url: str,
        now: datetime,
        warehouse_id: str | None = None,
        status_filter: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        query_source: str | None = None,
        max_results: int = 50,
        page_token: str | None = None,
        init_error: Exception | None = None,
        init_error_text: str | None = None,
        workspace_name: str | None = None,
        environment: str | None = None,
    ) -> LiveQueryHistoryResponse:
        """Fetch paginated SQL Query History via REST API without executing SQL or starting warehouses."""
        if client is None:
            if init_error is not None:
                cat_status, state, http_status, err_code, err_msg = self._classify_error_detailed(
                    init_error
                )
            else:
                cat_status = CategoryDiscoveryStatus.CONNECTION_ERROR
                state = DatabricksResourceState.UNAVAILABLE
                http_status = None
                err_code = "CONNECTION_ERROR"
                err_msg = init_error_text or "Databricks client unavailable."
            return LiveQueryHistoryResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=cat_status,
                discovery_state=state,
                retrieved_at=now,
                http_status=http_status,
                error_code=err_code,
                error_message=err_msg,
            )

        query_filter: QueryFilter | None = None
        filter_kwargs: dict[str, Any] = {}
        if warehouse_id and warehouse_id.strip():
            filter_kwargs["warehouse_ids"] = [warehouse_id.strip()]
        if status_filter and status_filter.strip() and status_filter.lower() != "all":
            normalized_st = status_filter.strip().upper()
            if normalized_st in ("QUEUED", "RUNNING", "FINISHED", "FAILED", "CANCELED"):
                filter_kwargs["statuses"] = [QueryStatus(normalized_st)]
        if start_time_ms is not None or end_time_ms is not None:
            filter_kwargs["query_start_time_range"] = TimeRange(
                start_time_ms=start_time_ms, end_time_ms=end_time_ms
            )
        if filter_kwargs:
            query_filter = QueryFilter(**filter_kwargs)

        try:
            resp = self._call_with_retry(
                partial(
                    client.query_history.list,
                    filter_by=query_filter,
                    include_metrics=True,
                    max_results=max_results,
                    page_token=page_token,
                ),
                "databricks-sdk/query_history.list",
            )
        except Exception as exc:
            cat_status, state, http_status, err_code, err_msg = self._classify_error_detailed(exc)
            return LiveQueryHistoryResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=cat_status,
                discovery_state=state,
                retrieved_at=now,
                http_status=http_status,
                error_code=err_code,
                error_message=err_msg,
            )

        if resp is None:
            return LiveQueryHistoryResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=CategoryDiscoveryStatus.CONNECTION_ERROR,
                discovery_state=DatabricksResourceState.UNAVAILABLE,
                retrieved_at=now,
                empty_confirmed=False,
                http_status=200,
                error_code="EMPTY_UNCONFIRMED",
                error_message="Query History API returned empty null response without API contract confirmation.",
            )

        raw_res = getattr(resp, "res", None)
        has_next = _opt_bool(getattr(resp, "has_next_page", None))
        next_token = _opt_str(getattr(resp, "next_page_token", None))

        if raw_res is None:
            # Confirm emptiness strictly when API explicitly sets has_next_page=False
            if has_next is False:
                return LiveQueryHistoryResponse(
                    connection_id=connection_id,
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                    workspace_url=workspace_url,
                    environment=environment,
                    status=CategoryDiscoveryStatus.NO_RESOURCES_FOUND,
                    discovery_state=DatabricksResourceState.NO_DATA,
                    retrieved_at=now,
                    records=[],
                    total_returned=0,
                    has_next_page=False,
                    next_page_token=None,
                    empty_confirmed=True,
                )
            return LiveQueryHistoryResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=CategoryDiscoveryStatus.CONNECTION_ERROR,
                discovery_state=DatabricksResourceState.UNAVAILABLE,
                retrieved_at=now,
                empty_confirmed=False,
                http_status=200,
                error_code="EMPTY_UNCONFIRMED",
                error_message="HTTP 200 query history payload omitted both 'res' and 'has_next_page' confirmation.",
            )

        if not isinstance(raw_res, list):
            return LiveQueryHistoryResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=CategoryDiscoveryStatus.CONNECTION_ERROR,
                discovery_state=DatabricksResourceState.UNAVAILABLE,
                retrieved_at=now,
                empty_confirmed=False,
                http_status=200,
                error_code="EMPTY_UNCONFIRMED",
                error_message="Query History API returned unexpected 'res' payload format.",
            )

        if len(raw_res) == 0 and has_next is True:
            return LiveQueryHistoryResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=CategoryDiscoveryStatus.CONNECTION_ERROR,
                discovery_state=DatabricksResourceState.UNAVAILABLE,
                retrieved_at=now,
                has_next_page=True,
                next_page_token=next_token,
                empty_confirmed=False,
                http_status=200,
                error_code="EMPTY_UNCONFIRMED",
                error_message="Query History returned 0 items with has_next_page=true.",
            )

        records: list[LiveQueryHistoryItem] = []
        for q in raw_res:
            raw_src = getattr(q, "query_source", None)
            q_src_str = _opt_str(getattr(raw_src, "name", raw_src))
            if query_source and query_source.strip() and query_source.lower() != "all":
                if not q_src_str or query_source.strip().lower() not in q_src_str.lower():
                    continue

            qid = _opt_str(getattr(q, "query_id", None)) or "unknown-query"
            q_status = _enum_str(getattr(q, "status", None)).upper()
            dur = getattr(q, "duration", None)
            dur_ms = (
                float(dur) if isinstance(dur, (int, float)) and not isinstance(dur, bool) else None
            )
            metrics = getattr(q, "metrics", None)
            read_bytes = (
                _opt_int(getattr(metrics, "read_bytes", None)) if metrics is not None else None
            )
            rows_produced = _opt_int(getattr(q, "rows_produced", None)) or (
                _opt_int(getattr(metrics, "rows_produced_count", None))
                if metrics is not None
                else None
            )
            q_err = _opt_str(getattr(q, "error_message", None))
            records.append(
                LiveQueryHistoryItem(
                    query_id=qid,
                    status=q_status,
                    warehouse_id=_opt_str(getattr(q, "warehouse_id", None)),
                    statement_type=_opt_str(getattr(q, "statement_type", None)),
                    query_source=q_src_str,
                    start_time=_normalize_timestamp(getattr(q, "query_start_time_ms", None)),
                    end_time=_normalize_timestamp(getattr(q, "query_end_time_ms", None)),
                    duration_ms=dur_ms,
                    rows_produced=rows_produced,
                    read_bytes=read_bytes,
                    executed_by_masked=_mask_principal(_opt_str(getattr(q, "user_name", None))),
                    sql_summary=_sanitize_sql_summary(
                        _opt_str(getattr(q, "query_text", None)), self.auth_service
                    ),
                    error_message=self.auth_service.scrub_sensitive(q_err) if q_err else None,
                )
            )

        if records:
            return LiveQueryHistoryResponse(
                connection_id=connection_id,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                workspace_url=workspace_url,
                environment=environment,
                status=CategoryDiscoveryStatus.AVAILABLE,
                discovery_state=DatabricksResourceState.LIVE,
                retrieved_at=now,
                records=records,
                total_returned=len(records),
                has_next_page=bool(has_next),
                next_page_token=next_token,
                empty_confirmed=False,
            )

        return LiveQueryHistoryResponse(
            connection_id=connection_id,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            workspace_url=workspace_url,
            environment=environment,
            status=CategoryDiscoveryStatus.NO_RESOURCES_FOUND,
            discovery_state=DatabricksResourceState.NO_DATA,
            retrieved_at=now,
            records=[],
            total_returned=0,
            has_next_page=False,
            next_page_token=None,
            empty_confirmed=True,
        )
