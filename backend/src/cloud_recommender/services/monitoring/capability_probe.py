"""Read-only probes that establish which Azure monitoring capabilities really work.

Availability is never inferred from environment variables or configuration. Each capability is
verified with one bounded, read-only GET using the existing authenticated identity, and reported
with the exact HTTP status and the permission that would be required. Nothing is created,
modified or deleted, and no retention period is stated (these APIs do not report one).
"""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from cloud_recommender.core.config import Settings
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService

logger = structlog.get_logger(__name__)

_TIMEOUT_SECONDS = 20.0
# The probes issue several sequential ARM calls; a short cache keeps the UI responsive.
# It caches only a real probe result for the same identity-less call and expires quickly.
_CACHE_TTL_SECONDS = 120.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_probe_cache() -> None:
    """Forget cached probe results (used by tests and on explicit refresh)."""
    _cache.clear()


def classify_http_status(status_code: int | None, count: int | None = None) -> str:
    """Map an HTTP outcome to AVAILABLE / NO_DATA / ACCESS_DENIED / UNAVAILABLE / ERROR."""
    if status_code is None:
        return "ERROR"
    if status_code == 200:
        return "AVAILABLE" if count is None or count > 0 else "NO_DATA"
    if status_code in (401, 403):
        return "ACCESS_DENIED"
    if status_code in (404, 405, 501):
        return "UNAVAILABLE"
    return "ERROR"


async def _get(
    client: httpx.AsyncClient, url: str, token: str
) -> tuple[int | None, Any, str | None]:
    try:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    except (httpx.TimeoutException, httpx.RequestError) as err:
        return None, None, f"{type(err).__name__}: {err}"
    body: Any = None
    try:
        body = resp.json()
    except ValueError:
        body = None
    error = None if resp.status_code == 200 else resp.text[:300]
    return resp.status_code, body, error


def _probe(
    name: str,
    path: str,
    permission: str,
    status_code: int | None,
    count: int | None,
    error: str | None,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "endpoint": path,
        "status": classify_http_status(status_code, count),
        "http_status": status_code,
        "record_count": count,
        "required_permission": permission,
        "message": error or detail,
    }


async def probe_azure_monitoring(
    settings: Settings, service: AzureInventoryService | None = None
) -> dict[str, Any]:
    """Probe Azure ARM / Monitor read endpoints with the existing authenticated identity."""
    cached = _cache.get("azure")
    if service is None and cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    result = await _probe_azure_monitoring_uncached(settings, service)
    if service is None and result.get("status") != "not_authenticated":
        _cache["azure"] = (time.monotonic(), result)
    return result


async def _probe_azure_monitoring_uncached(
    settings: Settings, service: AzureInventoryService | None
) -> dict[str, Any]:
    svc = service or AzureInventoryService(settings=settings)
    token, auth_method = await svc.get_access_token()
    checked_at = datetime.now(UTC).isoformat()
    if not token:
        return {
            "status": "not_authenticated",
            "is_live": False,
            "auth_method": auth_method,
            "capabilities": [],
            "retention_days": None,
            "probes": [],
            "last_checked": checked_at,
            "message": "No valid Azure identity. Run 'az login' or configure a service principal.",
        }

    base = settings.azure_arm_base_url.rstrip("/")
    probes: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        code, body, err = await _get(client, f"{base}/subscriptions?api-version=2022-12-01", token)
        subs = (body or {}).get("value", []) if isinstance(body, dict) else []
        probes.append(_probe("subscriptions", "/subscriptions", "Reader", code, len(subs), err))
        enabled = [s for s in subs if str(s.get("state", "")).lower() == "enabled"] or subs
        if enabled:
            sub_id = enabled[0]["subscriptionId"]
            scope = f"/subscriptions/{sub_id}"
            code, body, err = await _get(
                client, f"{base}{scope}/providers/Microsoft.Insights?api-version=2021-04-01", token
            )
            state = (body or {}).get("registrationState") if isinstance(body, dict) else None
            probes.append(
                _probe(
                    "insights_provider",
                    f"{scope}/providers/Microsoft.Insights",
                    "Reader",
                    code,
                    None,
                    err,
                    f"registrationState={state}" if state else None,
                )
            )
            since = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            code, body, err = await _get(
                client,
                f"{base}{scope}/providers/Microsoft.Insights/eventtypes/management/values"
                f"?api-version=2015-04-01&$filter=eventTimestamp ge '{since}'&$top=1",
                token,
            )
            events = (body or {}).get("value", []) if isinstance(body, dict) else []
            probes.append(
                _probe(
                    "activity_log",
                    f"{scope}/providers/Microsoft.Insights/eventtypes/management/values",
                    "Monitoring Reader (Microsoft.Insights/eventtypes/values/read)",
                    code,
                    len(events),
                    err,
                    "queried the last 24 hours, top 1",
                )
            )
            # ARM may return short (even empty) pages with a nextLink, so use the paginated lister.
            res = await svc.list_resources(sub_id, token)
            log = svc.pagination_log[-1] if svc.pagination_log else {}
            probes.append(
                _probe(
                    "resources",
                    f"{scope}/resources",
                    "Reader",
                    log.get("http_status"),
                    len(res),
                    log.get("error"),
                    f"{log.get('pages', 0)} page(s), complete={log.get('complete')}",
                )
            )
            tried = 0
            for resource in res:
                if tried >= 5:
                    break
                tried += 1
                rid = resource["id"]
                code, body, err = await _get(
                    client,
                    f"{base}{rid}/providers/Microsoft.Insights/metricDefinitions?api-version=2018-01-01",
                    token,
                )
                defs = (body or {}).get("value", []) if isinstance(body, dict) else []
                probe = _probe(
                    "metric_definitions",
                    "<resource>/providers/Microsoft.Insights/metricDefinitions",
                    "Monitoring Reader (Microsoft.Insights/metricDefinitions/read)",
                    code,
                    len(defs),
                    err,
                    f"resource type {resource.get('type')}: {len(defs)} metric definition(s)",
                )
                probes.append(probe)
                if probe["status"] == "AVAILABLE":
                    break
    probes.append(
        {
            "name": "cost_management",
            "endpoint": "Microsoft.CostManagement/query",
            "status": "NOT_PROBED",
            "http_status": None,
            "record_count": None,
            "required_permission": "Cost Management Reader",
            "message": "A query is a POST; verified by the Cost Management module, not here.",
        }
    )
    working = [p for p in probes if p["status"] in ("AVAILABLE", "NO_DATA")]
    return {
        "status": "connected" if working else "degraded",
        "is_live": bool(working),
        "auth_method": auth_method,
        "capabilities": [p["name"] for p in probes if p["status"] == "AVAILABLE"],
        "retention_days": None,
        "probes": probes,
        "last_checked": checked_at,
        "message": None,
    }
