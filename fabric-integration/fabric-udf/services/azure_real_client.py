"""Azure Real Read-Only API Client.

Directly queries official Azure management endpoints:
1. Azure Resource Graph REST API (Resource discovery, inventory, state)
2. Azure Monitor Metrics REST API (CPU, Memory, Network, Disk IOPS)
3. Azure Retail Prices API (Public consumption rates for SKUs)

Security Guardrails:
- 100% read-only operations (strictly HTTP GET or Resource Graph POST queries).
- Zero resource creation, modification, or deletion against customer subscriptions.
- Never prints, logs, or returns bearer tokens or client secrets.
- Surfaces honest error states if credentials fail or are revoked.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import logging
import shutil
import ssl
import subprocess
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from schemas.models import (
    DiscoveredResource,
    MetricPoint,
    MetricSeries,
    ResourceMetricsResponse,
)

logger = logging.getLogger(__name__)


def _sync_http_request(
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> tuple[int, Any]:
    """Execute synchronous HTTP request using standard library urllib."""
    target_url = url
    if params:
        query_string = urllib.parse.urlencode(params)
        sep = "&" if "?" in target_url else "?"
        target_url = f"{target_url}{sep}{query_string}"

    req_headers = headers.copy() if headers else {}
    req_headers.setdefault("User-Agent", "FinOps-UDF-Client/1.0")

    body_bytes: bytes | None = None
    if json_body is not None:
        body_bytes = json.dumps(json_body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    elif data is not None:
        body_bytes = urllib.parse.urlencode(data).encode("utf-8")
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = urllib.request.Request(
        target_url,
        data=body_bytes,
        headers=req_headers,
        method=method,
    )

    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            resp_bytes = resp.read()
            raw_text = resp_bytes.decode("utf-8", errors="replace")
            status_code = resp.status
            try:
                return status_code, json.loads(raw_text)
            except Exception:
                return status_code, raw_text
    except urllib.error.HTTPError as http_err:
        raw_text = http_err.read().decode("utf-8", errors="replace")
        try:
            return http_err.code, json.loads(raw_text)
        except Exception:
            return http_err.code, raw_text
    except Exception as exc:
        logger.warning(f"HTTP request to {target_url} failed: {exc}")
        return 0, str(exc)


class AzureRealClient:
    """Client for authentic read-only interactions with Azure cloud services."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def get_access_token(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> tuple[str | None, str]:
        """Acquire an ARM bearer token via OAuth2 Client Credentials or host Azure CLI session.

        Returns (token, auth_method_description).
        """
        # 1. Service Principal OAuth2 Client Credentials
        if tenant_id and client_id and client_secret:
            token_url = (
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            )
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://management.azure.com/.default",
            }
            status, payload = await asyncio.to_thread(
                _sync_http_request,
                "POST",
                token_url,
                data=data,
                timeout=self.timeout,
            )
            if status == 200 and isinstance(payload, dict):
                token = payload.get("access_token")
                if token:
                    return token, "service_principal_oauth2"
            logger.warning(f"azure_real_sp_token_failed status_code={status}")
            # Explicit credentials were provided and rejected - do not mask with CLI fallback
            return None, "unauthenticated"

        # 2. Host Azure CLI session fallback (used only when no explicit SP secrets were provided)
        az_path = shutil.which("az") or shutil.which("az.cmd")
        if az_path:
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
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
                    timeout=10,
                    check=False,
                )
                if proc.returncode == 0:
                    data_obj = json.loads(proc.stdout)
                    token = data_obj.get("accessToken") or data_obj.get("token")
                    if token:
                        return token, "azure_cli_session"
            except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
                logger.debug(f"azure_real_cli_token_attempt_failed error={exc}")

        return None, "unauthenticated"

    async def query_resource_graph(
        self, token: str, subscription_id: str, query: str | None = None
    ) -> list[DiscoveredResource]:
        """Execute a read-only KQL query against Azure Resource Graph for a subscription."""
        url = "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2021-03-01"
        kql = query or (
            f"Resources | where subscriptionId =~ '{subscription_id}' "
            "| project id, name, type, resourceGroup, location, sku, tags, properties"
        )
        payload = {
            "subscriptions": [subscription_id],
            "query": kql,
            "options": {"resultFormat": "objectArray"},
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        status, data = await asyncio.to_thread(
            _sync_http_request,
            "POST",
            url,
            json_body=payload,
            headers=headers,
            timeout=self.timeout,
        )

        if status != 200:
            err_msg = data if isinstance(data, str) else json.dumps(data)
            raise RuntimeError(
                f"Azure Resource Graph query failed (status {status}): {err_msg}"
            )

        rows: list[dict[str, Any]] = data.get("data", []) if isinstance(data, dict) else []
        resources: list[DiscoveredResource] = []

        for row in rows:
            sku_obj = row.get("sku")
            sku_name = (
                sku_obj.get("name")
                if isinstance(sku_obj, dict)
                else (sku_obj or None)
            )
            props = row.get("properties") or {}
            power_state = None
            if isinstance(props, dict):
                power_state = (
                    props.get("extended", {})
                    .get("instanceView", {})
                    .get("powerState", {})
                    .get("code")
                    or props.get("diskState")
                    or props.get("provisioningState")
                )

            raw_tags = row.get("tags") or {}
            tags = (
                {str(k): str(v) for k, v in raw_tags.items()}
                if isinstance(raw_tags, dict)
                else {}
            )

            resources.append(
                DiscoveredResource(
                    resource_id=row["id"],
                    name=row.get("name", row["id"].split("/")[-1]),
                    resource_type=row.get("type", "Unknown"),
                    resource_group=row.get("resourceGroup"),
                    location=row.get("location", "unknown"),
                    sku_name=sku_name,
                    tags=tags,
                    power_state=power_state,
                )
            )

        return resources

    async def query_monitor_metrics(
        self,
        token: str,
        resource_id: str,
        metric_names: list[str],
        time_grain: str = "PT1H",
        days: int = 7,
    ) -> ResourceMetricsResponse:
        """Query Azure Monitor metrics for a specific ARM resource."""
        clean_id = resource_id.lstrip("/")
        url = f"https://management.azure.com/{clean_id}/providers/Microsoft.Insights/metrics"

        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=days)
        timespan = f"{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"

        params = {
            "api-version": "2018-01-01",
            "metricnames": ",".join(metric_names),
            "interval": time_grain,
            "aggregation": "Average,Maximum,Minimum",
            "timespan": timespan,
        }
        headers = {"Authorization": f"Bearer {token}"}

        status, data = await asyncio.to_thread(
            _sync_http_request,
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=self.timeout,
        )

        if status != 200 or not isinstance(data, dict):
            err_msg = data if isinstance(data, str) else json.dumps(data)
            raise RuntimeError(
                f"Azure Monitor metrics query failed (status {status}): {err_msg}"
            )

        series_list: list[MetricSeries] = []
        start_str = data.get("timespan", "").split("/")[0]
        end_str = (
            data.get("timespan", "").split("/")[-1]
            if "/" in data.get("timespan", "")
            else ""
        )

        for value_obj in data.get("value", []):
            metric_name = value_obj.get("name", {}).get("value", "UnknownMetric")
            unit = value_obj.get("unit", "Count")
            points: list[MetricPoint] = []

            for ts in value_obj.get("timeseries", []):
                for d in ts.get("data", []):
                    if "timeStamp" in d:
                        points.append(
                            MetricPoint(
                                timestamp=d["timeStamp"],
                                average=d.get("average"),
                                maximum=d.get("maximum"),
                                minimum=d.get("minimum"),
                            )
                        )

            series_list.append(
                MetricSeries(metric_name=metric_name, unit=unit, points=points)
            )

        return ResourceMetricsResponse(
            resource_id=resource_id,
            time_grain=time_grain,
            start_time=start_str or "2026-01-01T00:00:00Z",
            end_time=end_str or "2026-01-01T00:00:00Z",
            series=series_list,
        )

    async def fetch_retail_price(
        self, arm_sku_name: str, region: str = "northcentralus"
    ) -> Decimal | None:
        """Fetch consumption hourly rate from public Azure Retail Prices API."""
        url = "https://prices.azure.com/api/retail/prices"
        filter_expr = f"armSkuName eq '{arm_sku_name}' and armRegionName eq '{region}' and priceType eq 'Consumption'"
        params = {"$filter": filter_expr}

        status, data = await asyncio.to_thread(
            _sync_http_request,
            "GET",
            url,
            params=params,
            timeout=10.0,
        )

        if status == 200 and isinstance(data, dict):
            items = data.get("Items", [])
            if items:
                for item in items:
                    if not item.get("isPrimaryMeterRegion") and len(items) > 1:
                        continue
                    unit_price = item.get("unitPrice")
                    if unit_price is not None:
                        return Decimal(str(unit_price))

        return None

    async def validate_arm_connection(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        subscription_id: str | None = None,
    ) -> dict[str, Any]:
        """Validate live credentials and RBAC roles against Azure Resource Manager and Cost Management."""
        token, auth_method = await self.get_access_token(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

        if not token:
            return {
                "valid": False,
                "error_code": "AUTHENTICATION_FAILED",
                "error_message": (
                    "Could not acquire Azure Resource Manager token. "
                    "Verify Tenant ID, Client ID, and Client Secret."
                ),
                "auth_method": auth_method,
            }

        result: dict[str, Any] = {
            "valid": True,
            "auth_method": auth_method,
            "provider": "azure",
            "scope_id": subscription_id,
            "roles": {
                "reader": False,
                "cost_management_reader": False,
                "resource_graph": False,
            },
            "subscription_name": None,
            "subscription_state": None,
            "resource_groups_count": 0,
            "discovered_resources_count": 0,
            "message": "Connection authenticated successfully.",
        }

        if not subscription_id:
            return result

        # 1. Probe Subscription Metadata (Reader Role)
        sub_url = f"https://management.azure.com/subscriptions/{subscription_id}?api-version=2022-12-01"
        sub_status, sub_data = await asyncio.to_thread(
            _sync_http_request,
            "GET",
            sub_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )

        if sub_status == 200 and isinstance(sub_data, dict):
            result["roles"]["reader"] = True
            result["subscription_name"] = sub_data.get("displayName")
            result["subscription_state"] = sub_data.get("state")
            result["message"] = (
                f"Verified Reader access on subscription '{result['subscription_name']}' "
                f"({result['subscription_state']})."
            )
        elif sub_status in (401, 403):
            result["valid"] = False
            result["error_code"] = "AUTHORIZATION_FAILED"
            result["error_message"] = (
                f"Authorization failed on subscription '{subscription_id}'. "
                "Ensure the Service Principal has the 'Reader' role assigned."
            )
            return result
        elif sub_status == 404:
            result["valid"] = False
            result["error_code"] = "SUBSCRIPTION_NOT_FOUND"
            result["error_message"] = (
                f"Subscription '{subscription_id}' was not found in tenant."
            )
            return result
        else:
            err_str = sub_data if isinstance(sub_data, str) else json.dumps(sub_data)
            logger.warning(f"Subscription probe returned HTTP {sub_status}: {err_str}")
            result["valid"] = False
            result["error_code"] = "INVALID_SUBSCRIPTION"
            result["error_message"] = (
                f"Subscription '{subscription_id}' probe failed (HTTP {sub_status}): {err_str}"
            )
            return result

        # 2. Probe Resource Groups
        rg_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups?api-version=2021-04-01"
        rg_status, rg_data = await asyncio.to_thread(
            _sync_http_request,
            "GET",
            rg_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if rg_status == 200 and isinstance(rg_data, dict):
            rgs = rg_data.get("value", [])
            result["resource_groups_count"] = len(rgs)

        # 3. Probe Azure Resource Graph
        try:
            resources = await self.query_resource_graph(token, subscription_id)
            result["roles"]["resource_graph"] = True
            result["discovered_resources_count"] = len(resources)
        except Exception as exc:
            logger.debug(f"Resource graph probe failed: {exc}")

        # 4. Probe Azure Cost Management
        cm_url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            "/providers/Microsoft.CostManagement/query?api-version=2021-10-01"
        )
        cm_payload = {
            "type": "ActualCost",
            "timeframe": "MonthToDate",
            "dataset": {
                "granularity": "None",
                "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            },
        }
        cm_status, _ = await asyncio.to_thread(
            _sync_http_request,
            "POST",
            cm_url,
            json_body=cm_payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if cm_status == 200:
            result["roles"]["cost_management_reader"] = True
        else:
            logger.debug(f"Cost Management probe returned HTTP {cm_status}")

        return result

    async def query_cost_management(
        self,
        token: str,
        subscription_id: str,
        timeframe: str = "MonthToDate",
    ) -> dict[str, Any]:
        """Query Azure Cost Management for aggregated actual expenditure by service and resource group."""
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            "/providers/Microsoft.CostManagement/query?api-version=2021-10-01"
        )
        payload = {
            "type": "ActualCost",
            "timeframe": timeframe,
            "dataset": {
                "granularity": "None",
                "aggregation": {
                    "totalCost": {"name": "Cost", "function": "Sum"},
                },
                "grouping": [
                    {"type": "Dimension", "name": "ServiceName"},
                    {"type": "Dimension", "name": "ResourceGroupName"},
                ],
            },
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        status, data = await asyncio.to_thread(
            _sync_http_request,
            "POST",
            url,
            json_body=payload,
            headers=headers,
            timeout=self.timeout,
        )

        if status != 200 or not isinstance(data, dict):
            err_msg = data if isinstance(data, str) else json.dumps(data)
            raise RuntimeError(
                f"Azure Cost Management query failed (status {status}): {err_msg}"
            )

        rows = data.get("properties", {}).get("rows", [])
        columns = [
            c.get("name") for c in data.get("properties", {}).get("columns", [])
        ]

        service_breakdown: dict[str, float] = {}
        rg_breakdown: dict[str, float] = {}
        total_usd = Decimal("0.00")
        currency = "USD"

        for row in rows:
            row_dict = dict(zip(columns, row))
            cost_val = Decimal(str(row_dict.get("Cost", 0)))
            total_usd += cost_val
            srv = str(row_dict.get("ServiceName", "Other"))
            rg = str(row_dict.get("ResourceGroupName", "Unassigned"))
            if "Currency" in row_dict:
                currency = str(row_dict["Currency"])

            service_breakdown[srv] = round(
                service_breakdown.get(srv, 0.0) + float(cost_val), 2
            )
            rg_breakdown[rg] = round(
                rg_breakdown.get(rg, 0.0) + float(cost_val), 2
            )

        return {
            "timeframe": timeframe,
            "total_cost": float(total_usd),
            "currency": currency,
            "service_breakdown": service_breakdown,
            "resource_group_breakdown": rg_breakdown,
            "row_count": len(rows),
        }

    async def query_arm_resources_direct(
        self, token: str, subscription_id: str
    ) -> list[DiscoveredResource]:
        """Direct ARM resource enumeration fallback if Resource Graph is unavailable."""
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            "/resources?api-version=2021-04-01"
        )
        headers = {"Authorization": f"Bearer {token}"}

        status, data = await asyncio.to_thread(
            _sync_http_request,
            "GET",
            url,
            headers=headers,
            timeout=self.timeout,
        )

        if status != 200 or not isinstance(data, dict):
            err_msg = data if isinstance(data, str) else json.dumps(data)
            raise RuntimeError(
                f"ARM direct resources query failed (status {status}): {err_msg}"
            )

        items = data.get("value", [])
        resources: list[DiscoveredResource] = []
        for item in items:
            raw_tags = item.get("tags") or {}
            tags = (
                {str(k): str(v) for k, v in raw_tags.items()}
                if isinstance(raw_tags, dict)
                else {}
            )
            sku_obj = item.get("sku")
            sku_name = (
                sku_obj.get("name")
                if isinstance(sku_obj, dict)
                else (sku_obj or None)
            )

            res_id = item.get("id", "")
            rg_name = None
            if "/resourcegroups/" in res_id.lower():
                parts = res_id.split("/")
                for i, p in enumerate(parts):
                    if p.lower() == "resourcegroups" and i + 1 < len(parts):
                        rg_name = parts[i + 1]
                        break

            resources.append(
                DiscoveredResource(
                    resource_id=res_id,
                    name=item.get("name", res_id.split("/")[-1]),
                    resource_type=item.get("type", "Unknown"),
                    resource_group=rg_name,
                    location=item.get("location", "unknown"),
                    sku_name=sku_name,
                    tags=tags,
                )
            )
        return resources
