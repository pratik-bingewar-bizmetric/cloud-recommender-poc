"""Read-only Azure Resource Group / resource discovery with last-good-inventory caching (M2.5).

Only ARM GET calls are issued. Errors are classified rather than swallowed so that an empty
subscription (authorized, nothing found) is never confused with an authorization failure. A failed
refresh returns the last successful inventory marked ``stale``; nothing is ever fabricated.
"""

import asyncio
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from cloud_recommender.core.config import Settings
from cloud_recommender.schemas.azure_discovery import (
    AzureDiscoveryStatus,
    AzureResourceGroupItem,
    AzureResourceGroupsResponse,
    AzureResourceItem,
    AzureResourcesResponse,
)
from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService

logger = structlog.get_logger(__name__)

_RG_API = "2021-04-01"
_SUB_API = "2022-12-01"
_RG_FROM_ID = re.compile(r"/resourcegroups/([^/]+)", re.IGNORECASE)

# Last successful result per cache key, shared across requests for the process lifetime.
_LAST_GOOD: dict[str, tuple[datetime, list[Any]]] = {}

# Short-lived ARM token cache so one page load does not shell out to the Azure CLI per call.
_TOKEN_TTL_SECONDS = 300.0
_TOKEN: tuple[str, str, float] | None = None
_TOKEN_LOCK = asyncio.Lock()

_STATUS_BY_HTTP = {
    401: AzureDiscoveryStatus.UNAUTHENTICATED,
    403: AzureDiscoveryStatus.FORBIDDEN,
    404: AzureDiscoveryStatus.NOT_FOUND,
}


class _Fetch:
    """Outcome of a strict, fully paged ARM listing."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.pages = 0
        self.http_status: int | None = None
        self.status = AzureDiscoveryStatus.OK
        self.error: str | None = None


class AzureDiscoveryService:
    """Discover Resource Groups and resources through read-only ARM listings."""

    def __init__(
        self, settings: Settings, azure_service: AzureInventoryService | None = None
    ) -> None:
        self.settings = settings
        self.azure = azure_service or AzureInventoryService(settings=settings)

    async def _token(self) -> tuple[str | None, str]:
        """ARM token and auth method; only successful acquisitions are cached (never logged)."""
        global _TOKEN
        async with _TOKEN_LOCK:
            if _TOKEN and time.monotonic() - _TOKEN[2] < _TOKEN_TTL_SECONDS:
                return _TOKEN[0], _TOKEN[1]
            token, method = await self.azure.get_access_token()
            _TOKEN = (token, method, time.monotonic()) if token else None
            return token, method

    def _base(self) -> str:
        return self.settings.azure_arm_base_url.rstrip("/")

    async def _get_paged(self, url: str, token: str) -> _Fetch:
        out = _Fetch()
        headers = {"Authorization": f"Bearer {token}"}
        current: str | None = url
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                while current:
                    resp = await client.get(current, headers=headers)
                    out.http_status = resp.status_code
                    if resp.status_code != 200:
                        out.status = _STATUS_BY_HTTP.get(
                            resp.status_code, AzureDiscoveryStatus.ERROR
                        )
                        try:
                            err = resp.json().get("error", {})
                            out.error = f"{err.get('code')}: {str(err.get('message'))[:200]}"
                        except ValueError:
                            out.error = f"HTTP {resp.status_code}"
                        return out
                    body = resp.json()
                    out.pages += 1
                    out.items.extend(body.get("value", []))
                    current = body.get("nextLink")
        except httpx.HTTPError as exc:
            out.status = AzureDiscoveryStatus.ERROR
            out.error = f"{type(exc).__name__}: network error contacting Azure Resource Manager"
        return out

    async def _subscription_state(self, subscription_id: str, token: str) -> str | None:
        """Authoritative state of the subscription (Enabled/Disabled/...); None if unreadable."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self._base()}/subscriptions/{subscription_id}?api-version={_SUB_API}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            if resp.status_code == 200:
                state = resp.json().get("state")
                return str(state) if state else None
        except httpx.HTTPError:
            return None
        return None

    @staticmethod
    def _failure_message(kind: str, scope: str, fetch: _Fetch) -> str:
        if fetch.status is AzureDiscoveryStatus.FORBIDDEN:
            return (
                f"Not authorized to list {kind} in {scope}. The signed-in identity needs the "
                f"read-only 'Reader' role at that scope. ({fetch.error})"
            )
        if fetch.status is AzureDiscoveryStatus.UNAUTHENTICATED:
            return f"Azure rejected the access token while listing {kind}. ({fetch.error})"
        if fetch.status is AzureDiscoveryStatus.NOT_FOUND:
            return f"{scope} was not found for this identity. ({fetch.error})"
        return f"Azure Resource Manager {kind} listing failed. ({fetch.error})"

    @staticmethod
    def _disabled_note(state: str | None) -> str:
        if state and state.lower() != "enabled":
            return (
                f" Subscription state is '{state}': inventory is read-only and may be incomplete."
            )
        return ""

    async def list_resource_groups(self, subscription_id: str) -> AzureResourceGroupsResponse:
        now = datetime.now(UTC)
        token, method = await self._token()
        if not token:
            return AzureResourceGroupsResponse(
                subscription_id=subscription_id,
                status=AzureDiscoveryStatus.UNAUTHENTICATED,
                status_message=(
                    "No Azure identity is available. Configure a service principal or run 'az login'; "
                    "no resource groups are shown without a live ARM call."
                ),
                retrieved_at=now,
            )
        state = await self._subscription_state(subscription_id, token)
        fetch = await self._get_paged(
            f"{self._base()}/subscriptions/{subscription_id}/resourcegroups?api-version={_RG_API}",
            token,
        )
        key = f"rg:{subscription_id}"
        if fetch.status is not AzureDiscoveryStatus.OK:
            msg = self._failure_message("resource groups", f"subscription {subscription_id}", fetch)
            cached = _LAST_GOOD.get(key)
            if cached:
                return AzureResourceGroupsResponse(
                    subscription_id=subscription_id,
                    subscription_state=state,
                    status=fetch.status,
                    status_message=f"{msg} Showing last successful inventory.",
                    http_status=fetch.http_status,
                    page_count=fetch.pages,
                    auth_method=method,
                    retrieved_at=now,
                    last_success_at=cached[0],
                    stale=True,
                    count=len(cached[1]),
                    items=list(cached[1]),
                )
            return AzureResourceGroupsResponse(
                subscription_id=subscription_id,
                subscription_state=state,
                status=fetch.status,
                status_message=msg,
                http_status=fetch.http_status,
                page_count=fetch.pages,
                auth_method=method,
                retrieved_at=now,
                count=None,
            )
        groups = [
            AzureResourceGroupItem(
                id=str(g.get("id", "")),
                name=str(g.get("name", "")),
                subscription_id=subscription_id,
                location=g.get("location"),
                provisioning_state=(g.get("properties") or {}).get("provisioningState"),
                managed_by=g.get("managedBy"),
                tags=g.get("tags") or {},
            )
            for g in fetch.items
        ]
        _LAST_GOOD[key] = (now, groups)
        empty = not groups
        return AzureResourceGroupsResponse(
            subscription_id=subscription_id,
            subscription_state=state,
            status=AzureDiscoveryStatus.EMPTY if empty else AzureDiscoveryStatus.OK,
            status_message=(
                (
                    "Authorized: the subscription has no resource groups."
                    if empty
                    else f"Discovered {len(groups)} resource group(s) across {fetch.pages} page(s)."
                )
                + self._disabled_note(state)
            ),
            http_status=200,
            page_count=fetch.pages,
            auth_method=method,
            retrieved_at=now,
            last_success_at=now,
            count=len(groups),
            items=groups,
        )

    async def list_resources(
        self, subscription_id: str, resource_group: str | None = None
    ) -> AzureResourcesResponse:
        now = datetime.now(UTC)
        token, method = await self._token()
        if not token:
            return AzureResourcesResponse(
                subscription_id=subscription_id,
                resource_group=resource_group,
                status=AzureDiscoveryStatus.UNAUTHENTICATED,
                status_message="No Azure identity is available; no resource inventory is shown.",
                retrieved_at=now,
            )
        state = await self._subscription_state(subscription_id, token)
        scope = f"/subscriptions/{subscription_id}"
        if resource_group:
            scope += f"/resourceGroups/{resource_group}"
        fetch = await self._get_paged(
            f"{self._base()}{scope}/resources?api-version={_RG_API}"
            "&$expand=createdTime,changedTime,provisioningState",
            token,
        )
        key = f"res:{subscription_id}:{(resource_group or '').lower()}"
        if fetch.status is not AzureDiscoveryStatus.OK:
            msg = self._failure_message("resources", scope, fetch)
            cached = _LAST_GOOD.get(key)
            return AzureResourcesResponse(
                subscription_id=subscription_id,
                resource_group=resource_group,
                subscription_state=state,
                status=fetch.status,
                status_message=msg + (" Showing last successful inventory." if cached else ""),
                http_status=fetch.http_status,
                page_count=fetch.pages,
                auth_method=method,
                retrieved_at=now,
                last_success_at=cached[0] if cached else None,
                stale=bool(cached),
                count=len(cached[1]) if cached else None,
                items=list(cached[1]) if cached else [],
            )
        resources = []
        for r in fetch.items:
            rid = str(r.get("id", ""))
            match = _RG_FROM_ID.search(rid)
            resources.append(
                AzureResourceItem(
                    id=rid,
                    name=str(r.get("name", "")),
                    type=str(r.get("type", "")),
                    subscription_id=subscription_id,
                    resource_group=match.group(1) if match else None,
                    location=r.get("location"),
                    kind=r.get("kind"),
                    sku=r.get("sku"),
                    provisioning_state=r.get("provisioningState"),
                    created_time=r.get("createdTime"),
                    changed_time=r.get("changedTime"),
                    managed_by=r.get("managedBy"),
                    tags=r.get("tags") or {},
                )
            )
        _LAST_GOOD[key] = (now, resources)
        empty = not resources
        return AzureResourcesResponse(
            subscription_id=subscription_id,
            resource_group=resource_group,
            subscription_state=state,
            status=AzureDiscoveryStatus.EMPTY if empty else AzureDiscoveryStatus.OK,
            status_message=(
                (
                    "Authorized: no resources found in this scope."
                    if empty
                    else f"Discovered {len(resources)} resource(s) across {fetch.pages} page(s). "
                    "Inventory only: utilization and cost are not implied."
                )
                + self._disabled_note(state)
            ),
            http_status=200,
            page_count=fetch.pages,
            auth_method=method,
            retrieved_at=now,
            last_success_at=now,
            count=len(resources),
            items=resources,
        )
