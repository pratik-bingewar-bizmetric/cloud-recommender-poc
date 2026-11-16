"""Live Azure data domains fetched with the connection's own token.

Each domain is fetched independently and reported with an explicit access state:
accessible / permission_denied / unavailable / empty / error. Nothing is defaulted to zero or
substituted with mock data; a failed domain never hides another one.
"""

import asyncio
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.azure_live import (
    CostSummary,
    DataAccessState,
    DataDomain,
    DataSource,
    OverviewResponse,
    ResourceTypeCount,
)
from cloud_recommender.services.azure_live.arm_client import ArmResponse, AzureArmClient
from cloud_recommender.services.azure_live.session_store import AzureSession

logger = structlog.get_logger(__name__)

API_SUBSCRIPTIONS = "2022-12-01"
API_RESOURCES = "2021-04-01"
API_MONITOR = "2018-01-01"
API_COST = "2023-11-01"

ROLE_READER = "Reader"
ROLE_MONITORING = "Monitoring Reader"
ROLE_COST = "Cost Management Reader"

COST_PERIODS = {"month_to_date": "MonthToDate", "last_month": "TheLastMonth"}


def parse_resource_id(resource_id: str) -> tuple[str | None, str | None, str]:
    """Return (namespace, type path, kind) of an ARM resource ID; kind is 'group' or 'resource'."""
    parts = [p for p in resource_id.split("/") if p]
    lowered = [p.lower() for p in parts]
    if "providers" not in lowered:
        return None, None, "group"
    index = lowered.index("providers")
    namespace = parts[index + 1]
    rest = parts[index + 2 :]
    type_path = "/".join(rest[0::2])
    return namespace, type_path, "resource"


class AzureLiveDataService:
    """Fetches Azure data on behalf of one connection session."""

    def __init__(
        self,
        session: AzureSession,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.client = AzureArmClient(
            token=session.token.value,
            base_url=settings.azure_arm_base_url,
            timeout=float(settings.azure_live_request_timeout_seconds),
            transport=transport,
        )

    # ----------------------------------------------------------------- helpers

    def _source(self, api: str, subscription_id: str | None = None) -> DataSource:
        return DataSource(
            connection_id=self.session.connection_id,
            tenant_id=self.session.tenant_id,
            client_id=self.session.client_id,
            subscription_id=subscription_id,
            api=api,
            fetched_at=datetime.now(UTC),
        )

    def _failure(
        self,
        domain: str,
        response: ArmResponse,
        api: str,
        subscription_id: str | None,
        required_role: str,
    ) -> DataDomain:
        """Translate a failed ARM response into an explicit, honest domain state."""
        status = response.status_code
        message: str
        state: DataAccessState
        required: str | None = None
        if response.network_error:
            state, message = DataAccessState.ERROR, "Azure could not be reached. Try again."
        elif status == 401:
            state = DataAccessState.UNAVAILABLE
            message = "Azure rejected the access token (expired or revoked). Reconnect to continue."
        elif status == 403:
            state = DataAccessState.PERMISSION_DENIED
            required = required_role
            message = (
                f"The connected service principal is not authorized for this data. "
                f"Assign the '{required_role}' role on the subscription."
            )
        elif status in (404, 400, 409):
            state = DataAccessState.UNAVAILABLE
            message = response.error_message or "This data is not available for the selected scope."
        elif status == 429:
            state = DataAccessState.ERROR
            message = "Azure is rate limiting this request."
            if response.retry_after:
                message += f" Retry in {response.retry_after} seconds."
        else:
            state = DataAccessState.ERROR
            message = response.error_message or "Azure returned an unexpected error."
        return DataDomain(
            domain=domain,
            state=state,
            items=None,
            count=None,
            message=message,
            required_permission=required,
            http_status=status,
            azure_error_code=response.error_code,
            retry_after_seconds=response.retry_after,
            source=self._source(api, subscription_id),
        )

    def _success(
        self,
        domain: str,
        items: list[Any],
        api: str,
        subscription_id: str | None,
        empty_message: str,
        truncated: bool = False,
    ) -> DataDomain:
        return DataDomain(
            domain=domain,
            state=DataAccessState.ACCESSIBLE if items else DataAccessState.EMPTY,
            items=items,
            count=len(items),
            message=None if items else empty_message,
            http_status=200,
            truncated=truncated,
            source=self._source(api, subscription_id),
        )

    # ----------------------------------------------------------- subscriptions

    async def list_subscriptions(self) -> DataDomain:
        api = "GET /subscriptions"
        response = await self.client.get("/subscriptions", API_SUBSCRIPTIONS)
        if not response.ok:
            return self._failure("subscriptions", response, api, None, ROLE_READER)
        items = [
            {
                "subscription_id": s.get("subscriptionId"),
                "display_name": s.get("displayName"),
                "state": s.get("state"),
                "tenant_id": s.get("tenantId"),
            }
            for s in (response.body or {}).get("value", [])
            if isinstance(s, dict)
        ]
        return self._success(
            "subscriptions",
            items,
            api,
            None,
            "The service principal has no role assignment on any subscription. "
            "Assign Reader on a subscription to see data.",
        )

    async def verify_subscription(self, subscription_id: str) -> DataDomain:
        api = "GET /subscriptions/{id}"
        response = await self.client.get(f"/subscriptions/{subscription_id}", API_SUBSCRIPTIONS)
        if not response.ok:
            if response.status_code in (403, 404):
                # ARM answers 403/404 when the principal has no role on the subscription.
                return DataDomain(
                    domain="requested_subscription",
                    state=DataAccessState.PERMISSION_DENIED,
                    message="The service principal has no access to this subscription.",
                    required_permission=ROLE_READER,
                    http_status=response.status_code,
                    azure_error_code=response.error_code,
                    source=self._source(api, subscription_id),
                )
            return self._failure(
                "requested_subscription", response, api, subscription_id, ROLE_READER
            )
        body = response.body or {}
        return self._success(
            "requested_subscription",
            [
                {
                    "subscription_id": body.get("subscriptionId"),
                    "display_name": body.get("displayName"),
                    "state": body.get("state"),
                }
            ],
            api,
            subscription_id,
            "",
        )

    # ---------------------------------------------------------- resource groups

    async def list_resource_groups(self, subscription_id: str) -> DataDomain:
        api = "GET /subscriptions/{id}/resourcegroups"
        items, truncated, error = await self.client.get_paged(
            f"/subscriptions/{subscription_id}/resourcegroups",
            API_RESOURCES,
            max_items=self.settings.azure_live_max_resources,
        )
        if error is not None:
            return self._failure("resource_groups", error, api, subscription_id, ROLE_READER)
        groups = [
            {
                "name": g.get("name"),
                "id": g.get("id"),
                "location": g.get("location"),
                "provisioning_state": (g.get("properties") or {}).get("provisioningState"),
                "tags": g.get("tags") or {},
            }
            for g in items
        ]
        return self._success(
            "resource_groups",
            groups,
            api,
            subscription_id,
            "The subscription has no resource groups.",
            truncated,
        )

    # ---------------------------------------------------------------- resources

    @staticmethod
    def _resource_group_of(resource_id: str) -> str | None:
        parts = resource_id.split("/")
        lowered = [p.lower() for p in parts]
        if "resourcegroups" in lowered:
            idx = lowered.index("resourcegroups")
            return parts[idx + 1] if idx + 1 < len(parts) else None
        return None

    async def list_resources(
        self, subscription_id: str, resource_group: str | None = None
    ) -> tuple[DataDomain, list[ResourceTypeCount]]:
        if resource_group:
            path = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/resources"
            api = "GET /subscriptions/{id}/resourceGroups/{rg}/resources"
        else:
            path = f"/subscriptions/{subscription_id}/resources"
            api = "GET /subscriptions/{id}/resources"
        items, truncated, error = await self.client.get_paged(
            path, API_RESOURCES, max_items=self.settings.azure_live_max_resources
        )
        if error is not None:
            return self._failure("resources", error, api, subscription_id, ROLE_READER), []
        resources = [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "type": r.get("type"),
                "location": r.get("location"),
                "kind": r.get("kind"),
                "sku": (r.get("sku") or {}).get("name") if isinstance(r.get("sku"), dict) else None,
                "resource_group": self._resource_group_of(str(r.get("id", ""))),
                "tags": r.get("tags") or {},
            }
            for r in items
        ]
        counts: Counter[str] = Counter()
        display: dict[str, str] = {}
        for res in resources:
            rtype = str(res["type"] or "unknown")
            counts[rtype.lower()] += 1
            display.setdefault(rtype.lower(), rtype)
        breakdown = [
            ResourceTypeCount(resource_type=display[key], count=count)
            for key, count in counts.most_common()
        ]
        domain = self._success(
            "resources",
            resources,
            api,
            subscription_id,
            "No resources exist in this scope (the principal can read it).",
            truncated,
        )
        return domain, breakdown

    async def _resolve_api_version(self, namespace: str, type_path: str) -> str | None:
        response = await self.client.get(f"/providers/{namespace}", API_RESOURCES)
        if not response.ok:
            return None
        for rtype in (response.body or {}).get("resourceTypes", []):
            if str(rtype.get("resourceType", "")).lower() == type_path.lower():
                versions = [str(v) for v in rtype.get("apiVersions", [])]
                stable = [v for v in versions if "preview" not in v.lower()]
                candidates = stable or versions
                return candidates[0] if candidates else None
        return None

    async def get_resource(self, subscription_id: str, resource_id: str) -> DataDomain:
        api = "GET {resourceId}"
        namespace, type_path, kind = parse_resource_id(resource_id)
        if kind == "group":
            version: str | None = API_RESOURCES
        else:
            version = await self._resolve_api_version(namespace or "", type_path or "")
        if version is None:
            return DataDomain(
                domain="resource_detail",
                state=DataAccessState.UNAVAILABLE,
                message="No supported API version could be determined for this resource type.",
                source=self._source(api, subscription_id),
            )
        response = await self.client.get(resource_id, version)
        if not response.ok:
            return self._failure("resource_detail", response, api, subscription_id, ROLE_READER)
        return self._success("resource_detail", [response.body], api, subscription_id, "")

    # ---------------------------------------------------------------- monitoring

    async def metric_definitions(self, subscription_id: str, resource_id: str) -> DataDomain:
        api = "GET {resourceId}/providers/Microsoft.Insights/metricDefinitions"
        response = await self.client.get(
            f"{resource_id}/providers/Microsoft.Insights/metricDefinitions", API_MONITOR
        )
        if not response.ok:
            return self._failure(
                "metric_definitions", response, api, subscription_id, ROLE_MONITORING
            )
        items = [
            {
                "name": (m.get("name") or {}).get("value"),
                "display_name": (m.get("name") or {}).get("localizedValue"),
                "unit": m.get("unit"),
                "primary_aggregation": m.get("primaryAggregationType"),
                "supported_aggregations": m.get("supportedAggregationTypes") or [],
                "dimensions": [
                    d.get("value") for d in (m.get("dimensions") or []) if isinstance(d, dict)
                ],
                "time_grains": [
                    a.get("timeGrain")
                    for a in (m.get("metricAvailabilities") or [])
                    if isinstance(a, dict)
                ],
            }
            for m in (response.body or {}).get("value", [])
            if isinstance(m, dict)
        ]
        return self._success(
            "metric_definitions",
            items,
            api,
            subscription_id,
            "This resource type does not emit Azure Monitor platform metrics.",
        )

    async def metric_values(
        self,
        subscription_id: str,
        resource_id: str,
        metric_names: list[str],
        hours: int,
        interval: str,
        aggregation: str,
    ) -> DataDomain:
        api = "GET {resourceId}/providers/Microsoft.Insights/metrics"
        end = datetime.now(UTC).replace(microsecond=0)
        start = end.timestamp() - hours * 3600
        timespan = (
            f"{datetime.fromtimestamp(start, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}/"
            f"{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        response = await self.client.get(
            f"{resource_id}/providers/Microsoft.Insights/metrics",
            API_MONITOR,
            {
                "metricnames": ",".join(metric_names),
                "timespan": timespan,
                "interval": interval,
                "aggregation": aggregation,
            },
        )
        if not response.ok:
            return self._failure("metric_values", response, api, subscription_id, ROLE_MONITORING)
        key = aggregation.lower()
        series: list[dict[str, Any]] = []
        has_points = False
        for metric in (response.body or {}).get("value", []):
            if not isinstance(metric, dict):
                continue
            points: list[dict[str, Any]] = []
            for ts in metric.get("timeseries") or []:
                for datum in ts.get("data") or []:
                    if key in datum:  # Azure reports a value only when it has one
                        points.append({"timestamp": datum.get("timeStamp"), "value": datum[key]})
            has_points = has_points or bool(points)
            series.append(
                {
                    "name": (metric.get("name") or {}).get("value"),
                    "display_name": (metric.get("name") or {}).get("localizedValue"),
                    "unit": metric.get("unit"),
                    "aggregation": aggregation,
                    "points": points,
                }
            )
        domain = self._success(
            "metric_values", series, api, subscription_id, "No metric series were returned."
        )
        if series and not has_points:
            domain.state = DataAccessState.EMPTY
            domain.message = (
                "Azure returned no datapoints for this resource in the selected window."
            )
        return domain

    # --------------------------------------------------------------------- cost

    async def cost(self, subscription_id: str, period: str = "month_to_date") -> DataDomain:
        api = "POST /subscriptions/{id}/providers/Microsoft.CostManagement/query"
        timeframe = COST_PERIODS.get(period, "MonthToDate")
        body = {
            "type": "ActualCost",
            "timeframe": timeframe,
            "dataset": {
                "granularity": "None",
                "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
                "grouping": [{"type": "Dimension", "name": "ServiceName"}],
            },
        }
        response = await self.client.post_cost_query(
            f"/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query",
            API_COST,
            body,
        )
        if not response.ok:
            return self._failure("cost", response, api, subscription_id, ROLE_COST)

        props = (response.body or {}).get("properties") or {}
        columns = [str(c.get("name", "")).lower() for c in props.get("columns") or []]
        rows = props.get("rows") or []

        def col(*names: str) -> int | None:
            for name in names:
                if name.lower() in columns:
                    return columns.index(name.lower())
            return None

        cost_idx = col("totalcost", "pretaxcost", "cost")
        svc_idx = col("servicename")
        cur_idx = col("currency")
        by_service: list[dict[str, Any]] = []
        for row in rows:
            if cost_idx is None or not isinstance(row, list):
                continue
            by_service.append(
                {
                    "service": row[svc_idx] if svc_idx is not None else None,
                    "cost": row[cost_idx],
                    "currency": row[cur_idx] if cur_idx is not None else None,
                }
            )

        domain = self._success(
            "cost",
            [],
            api,
            subscription_id,
            "Azure returned no cost rows for this period. This is not a statement that spend is "
            "zero; cost data may not be available yet for this subscription.",
        )
        if not by_service:
            return domain

        currencies = {r["currency"] for r in by_service if r["currency"]}
        total: float | None = None
        message: str | None = None
        if len(currencies) <= 1:
            total = round(sum(float(r["cost"]) for r in by_service), 2)
        else:
            message = "Costs are in multiple currencies, so no single total is shown."
        today = datetime.now(UTC).date()
        summary = CostSummary(
            period=period,
            period_start=today.replace(day=1).isoformat() if period == "month_to_date" else None,
            period_end=today.isoformat() if period == "month_to_date" else None,
            currency=next(iter(currencies)) if len(currencies) == 1 else None,
            total=total,
            by_service=sorted(by_service, key=lambda r: float(r["cost"]), reverse=True),
        )
        domain.state = DataAccessState.ACCESSIBLE
        domain.items = [summary.model_dump()]
        domain.count = len(by_service)
        domain.message = message
        return domain

    # ----------------------------------------------------------------- overview

    def _unexpected(self, domain: str, subscription_id: str | None) -> DataDomain:
        return DataDomain(
            domain=domain,
            state=DataAccessState.ERROR,
            message="An unexpected error occurred while fetching this data.",
            source=self._source("internal", subscription_id),
        )

    async def overview(
        self, connection_info_builder: Any, subscription_id: str
    ) -> OverviewResponse:
        """Fetch all domains concurrently; one failure never hides another."""
        results = await asyncio.gather(
            self.list_subscriptions(),
            self.list_resource_groups(subscription_id),
            self.list_resources(subscription_id),
            self.cost(subscription_id),
            return_exceptions=True,
        )
        subs, groups, resources, cost = results
        for value in results:
            if isinstance(value, BaseException):
                logger.error("azure_live_overview_domain_failed", error_type=type(value).__name__)
        breakdown: list[ResourceTypeCount] = []
        if isinstance(resources, BaseException):
            resources_domain = self._unexpected("resources", subscription_id)
        else:
            resources_domain, breakdown = resources
        return OverviewResponse(
            connection=connection_info_builder(self.session),
            subscription_id=subscription_id,
            subscriptions=subs
            if not isinstance(subs, BaseException)
            else self._unexpected("subscriptions", None),
            resource_groups=groups
            if not isinstance(groups, BaseException)
            else self._unexpected("resource_groups", subscription_id),
            resources=resources_domain,
            type_breakdown=breakdown,
            cost=cost
            if not isinstance(cost, BaseException)
            else self._unexpected("cost", subscription_id),
        )
