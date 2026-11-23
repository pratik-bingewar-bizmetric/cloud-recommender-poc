"""Independent read-only connectivity checks and discovery for Google Cloud Platform services.

Supported Services:
1. Cloud Resource Manager (Project access and state)
2. Cloud Asset Inventory (searchAllResources)
3. Cloud Storage (Bucket discovery)
4. Cloud SQL Admin (SQL database instances)
5. Compute Engine (Aggregated VM instances)
6. Cloud Monitoring (Metric descriptors and monitored resources)
7. Cloud Recommender (Optimization recommendations)
8. Service Usage (API enablement verification)

Strict Guardrails:
- 100% read-only operations.
- Failure in one service does not block others.
- Never automatically enables disabled APIs.
- Zero price or metric hallucinations.
- Redacts all secrets and tokens.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from cloud_recommender.schemas.gcp import (
    GcpDiscoveryResponse,
    GcpMonitoringSummary,
    GcpProjectMetadata,
    GcpRecommenderItem,
    GcpResourceItem,
    GcpServiceConnectivityState,
    GcpServiceStatus,
    GcpTestConnectionResponse,
)
from cloud_recommender.services.gcp.auth_service import GcpAuthService, get_gcp_auth_service

logger = structlog.get_logger(__name__)


def _classify_error(
    status_code: int,
    error_body: dict[str, Any] | str,
    service_id: str | None = None,
) -> tuple[GcpServiceConnectivityState, str]:
    """Map Google Cloud API HTTP errors to standard connectivity states and messages."""
    raw_str = json.dumps(error_body) if isinstance(error_body, dict) else str(error_body)
    raw_lower = raw_str.lower()

    if status_code == 401:
        return (
            GcpServiceConnectivityState.AUTHENTICATION_FAILED,
            "Authentication failed: Service Account token is invalid or expired.",
        )

    if status_code == 429:
        return (
            GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
            "Rate limited by Google Cloud API (HTTP 429). Retry after backoff.",
        )

    if status_code == 403:
        # Check if error is due to missing or required billing account
        if (
            "billing_disabled" in raw_lower
            or "billingaccount" in raw_lower
            or "billing is disabled" in raw_lower
            or "requires billing" in raw_lower
            or "billing has not been enabled" in raw_lower
        ):
            svc_name = "Compute Engine" if service_id == "compute_engine" else "Service"
            return (
                GcpServiceConnectivityState.DEFERRED,
                f"{svc_name} is deferred (API enablement requires an active Google Cloud Billing account, which is currently deferred).",
            )

        # Compute Engine API disabled in an unbilled project is explicitly deferred
        if service_id == "compute_engine" and (
            "service_disabled" in raw_str
            or "accessnotconfigured" in raw_lower
            or "has not been used in project" in raw_lower
            or "is disabled" in raw_lower
            or "api has not been enabled" in raw_lower
        ):
            return (
                GcpServiceConnectivityState.DEFERRED,
                "Compute Engine is deferred (API enablement requires an active Google Cloud Billing account, which is currently deferred).",
            )

        # Check if 403 is due to disabled API
        if (
            "SERVICE_DISABLED" in raw_str
            or "accessNotConfigured" in raw_str
            or "has not been used in project" in raw_str
            or "is disabled" in raw_str
            or "API has not been enabled" in raw_str
        ):
            return (
                GcpServiceConnectivityState.API_DISABLED,
                "API is disabled in target GCP project. Enablement required in Google Cloud Console.",
            )

        # IAM permission failure
        return (
            GcpServiceConnectivityState.PERMISSION_DENIED,
            "Permission denied: Service Account lacks required IAM role/permission.",
        )

    if status_code == 404:
        return (
            GcpServiceConnectivityState.RESOURCE_NOT_FOUND,
            "Project or target resource not found in GCP.",
        )

    if status_code in (500, 502, 503, 504):
        return (
            GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
            f"Google Cloud service endpoint unavailable (HTTP {status_code}).",
        )

    return (
        GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
        f"API request failed with HTTP {status_code}.",
    )


class GcpConnectivityService:
    """Orchestrates per-service connectivity probes and resource discovery."""

    def __init__(
        self,
        auth_service: GcpAuthService | None = None,
        timeout_seconds: float = 12.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.auth_service = auth_service or get_gcp_auth_service()
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        token: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "FinOps-CloudRecommender/1.0",
        }
        return await client.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            timeout=self.timeout_seconds,
        )

    # ------------------------------------------------------------------ Probes

    async def check_resource_manager(
        self, client: httpx.AsyncClient, token: str, project_id: str
    ) -> tuple[GcpServiceStatus, GcpProjectMetadata | None]:
        endpoint = f"https://cloudresourcemanager.googleapis.com/v3/projects/{project_id}"
        service_id = "cloud_resource_manager"
        service_name = "Cloud Resource Manager"
        role = "roles/resourcemanager.projectViewer or roles/browser"

        try:
            resp = await self._request(client, "GET", endpoint, token)
            if resp.status_code == 200:
                data = resp.json()
                meta = GcpProjectMetadata(
                    project_id=data.get("projectId", project_id),
                    project_name=data.get("displayName"),
                    project_number=data.get("projectNumber")
                    or data.get("name", "").replace("projects/", ""),
                    project_state=data.get("state"),
                    parent_type=data.get("parent", "").split("/")[0]
                    if "/" in data.get("parent", "")
                    else None,
                    parent_id=data.get("parent", "").split("/")[1]
                    if "/" in data.get("parent", "")
                    else None,
                )
                return (
                    GcpServiceStatus(
                        service=service_id,
                        service_name=service_name,
                        status=GcpServiceConnectivityState.SUCCESS,
                        api_endpoint=endpoint,
                        required_role_or_permission=role,
                        message="Successfully validated project access and state.",
                        details={"state": meta.project_state, "name": meta.project_name},
                    ),
                    meta,
                )
            state, msg = _classify_error(
                resp.status_code, resp.json() if resp.text else {}, service_id=service_id
            )
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=state,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=msg,
                ),
                None,
            )
        except Exception as exc:
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Request failed: {type(exc).__name__}",
                ),
                None,
            )

    async def check_service_usage(
        self,
        client: httpx.AsyncClient,
        token: str,
        project_id: str,
        max_pages: int = 5,
    ) -> tuple[GcpServiceStatus, set[str]]:
        endpoint = f"https://serviceusage.googleapis.com/v1/projects/{project_id}/services"
        service_id = "service_usage"
        service_name = "Service Usage"
        role = "roles/serviceusage.serviceUsageViewer"
        enabled_services: set[str] = set()

        params: dict[str, Any] = {"filter": "state:ENABLED", "pageSize": 100}
        page_count = 0

        try:
            while True:
                page_count += 1
                resp = await self._request(client, "GET", endpoint, token, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("services", []):
                        name = (
                            item.get("config", {}).get("name")
                            or item.get("name", "").split("/")[-1]
                        )
                        if name:
                            enabled_services.add(name)

                    next_page_token = data.get("nextPageToken")
                    if next_page_token and page_count < max_pages:
                        params["pageToken"] = next_page_token
                    else:
                        break
                else:
                    state, msg = _classify_error(
                        resp.status_code, resp.json() if resp.text else {}, service_id=service_id
                    )
                    return (
                        GcpServiceStatus(
                            service=service_id,
                            service_name=service_name,
                            status=state,
                            api_endpoint=endpoint,
                            required_role_or_permission=role,
                            message=msg,
                        ),
                        enabled_services,
                    )

            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SUCCESS,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Discovered {len(enabled_services)} enabled Google Cloud APIs across {page_count} page(s).",
                    details={"enabled_count": len(enabled_services), "pages_retrieved": page_count},
                ),
                enabled_services,
            )
        except Exception as exc:
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Request failed: {type(exc).__name__}",
                ),
                enabled_services,
            )

    async def check_asset_inventory(
        self,
        client: httpx.AsyncClient,
        token: str,
        project_id: str,
        page_size: int = 50,
        max_pages: int = 5,
        max_total_resources: int = 500,
    ) -> tuple[GcpServiceStatus, list[GcpResourceItem]]:
        endpoint = f"https://cloudasset.googleapis.com/v1/projects/{project_id}:searchAllResources"
        service_id = "cloud_asset_inventory"
        service_name = "Cloud Asset Inventory"
        role = "roles/cloudasset.viewer (cloudasset.assets.searchAllResources)"
        resources: list[GcpResourceItem] = []
        seen_ids: set[str] = set()

        params: dict[str, Any] = {"pageSize": min(page_size, 100)}
        page_count = 0
        has_more = False

        try:
            while True:
                page_count += 1
                resp = await self._request(client, "GET", endpoint, token, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = data.get("results", [])
                    for item in raw_items:
                        r_id = item.get("name", "")
                        if r_id in seen_ids:
                            continue
                        seen_ids.add(r_id)
                        r_name = r_id.split("/")[-1] or item.get("displayName", "Unnamed")
                        r_type = item.get("assetType", "gcp.unknown")
                        loc = item.get("location")
                        st = item.get("state")
                        labels = dict(item.get("labels") or {})
                        resources.append(
                            GcpResourceItem(
                                resource_id=r_id,
                                resource_name=r_name,
                                resource_type=r_type,
                                project_id=project_id,
                                location=loc,
                                creation_time=item.get("createTime"),
                                state=st,
                                labels=labels,
                                details={
                                    "asset_type": r_type,
                                    "parent_full_resource_name": item.get("parentFullResourceName"),
                                },
                            )
                        )
                        if len(resources) >= max_total_resources:
                            break

                    next_page_token = data.get("nextPageToken")
                    if (
                        next_page_token
                        and page_count < max_pages
                        and len(resources) < max_total_resources
                    ):
                        params["pageToken"] = next_page_token
                        has_more = True
                    else:
                        has_more = bool(next_page_token)
                        break
                else:
                    state, msg = _classify_error(
                        resp.status_code, resp.json() if resp.text else {}, service_id=service_id
                    )
                    return (
                        GcpServiceStatus(
                            service=service_id,
                            service_name=service_name,
                            status=state,
                            api_endpoint=endpoint,
                            required_role_or_permission=role,
                            message=msg,
                        ),
                        resources,
                    )

            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SUCCESS,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Asset Inventory queried successfully ({len(resources)} resources returned across {page_count} page(s)).",
                    details={
                        "resources_count": len(resources),
                        "pages_retrieved": page_count,
                        "has_next_page": has_more,
                    },
                ),
                resources,
            )
        except Exception as exc:
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Request failed: {type(exc).__name__}",
                ),
                resources,
            )

    async def check_storage(
        self,
        client: httpx.AsyncClient,
        token: str,
        project_id: str,
        max_pages: int = 5,
        max_total_buckets: int = 200,
    ) -> tuple[GcpServiceStatus, list[GcpResourceItem]]:
        endpoint = f"https://storage.googleapis.com/storage/v1/b?project={project_id}"
        service_id = "cloud_storage"
        service_name = "Cloud Storage"
        role = "roles/storage.objectViewer or roles/viewer"
        buckets: list[GcpResourceItem] = []
        seen_names: set[str] = set()

        params: dict[str, Any] = {"project": project_id, "maxResults": 100}
        page_count = 0

        try:
            while True:
                page_count += 1
                resp = await self._request(client, "GET", endpoint, token, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    for b in items:
                        b_name = b.get("name", "")
                        if b_name in seen_names:
                            continue
                        seen_names.add(b_name)
                        buckets.append(
                            GcpResourceItem(
                                resource_id=f"//storage.googleapis.com/projects/_/buckets/{b_name}",
                                resource_name=b_name,
                                resource_type="storage.googleapis.com/Bucket",
                                project_id=project_id,
                                location=b.get("location"),
                                creation_time=b.get("timeCreated"),
                                state="ACTIVE",
                                labels=dict(b.get("labels") or {}),
                                details={
                                    "storageClass": b.get("storageClass", "STANDARD"),
                                    "locationType": b.get("locationType", "region"),
                                },
                            )
                        )
                        if len(buckets) >= max_total_buckets:
                            break

                    next_page_token = data.get("nextPageToken")
                    if (
                        next_page_token
                        and page_count < max_pages
                        and len(buckets) < max_total_buckets
                    ):
                        params["pageToken"] = next_page_token
                    else:
                        break
                else:
                    state, msg = _classify_error(
                        resp.status_code, resp.json() if resp.text else {}, service_id=service_id
                    )
                    return (
                        GcpServiceStatus(
                            service=service_id,
                            service_name=service_name,
                            status=state,
                            api_endpoint=endpoint,
                            required_role_or_permission=role,
                            message=msg,
                        ),
                        buckets,
                    )

            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SUCCESS,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Cloud Storage queried successfully ({len(buckets)} bucket(s) found across {page_count} page(s)).",
                    details={"bucket_count": len(buckets), "pages_retrieved": page_count},
                ),
                buckets,
            )
        except Exception as exc:
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Request failed: {type(exc).__name__}",
                ),
                buckets,
            )

    async def check_sql(
        self, client: httpx.AsyncClient, token: str, project_id: str
    ) -> tuple[GcpServiceStatus, list[GcpResourceItem]]:
        endpoint = f"https://sqladmin.googleapis.com/v1/projects/{project_id}/instances"
        service_id = "cloud_sql"
        service_name = "Cloud SQL Admin"
        role = "roles/cloudsql.viewer"
        instances: list[GcpResourceItem] = []

        try:
            resp = await self._request(client, "GET", endpoint, token)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                for inst in items:
                    name = inst.get("name", "")
                    settings = inst.get("settings") or {}
                    instances.append(
                        GcpResourceItem(
                            resource_id=f"//sqladmin.googleapis.com/projects/{project_id}/instances/{name}",
                            resource_name=name,
                            resource_type="sqladmin.googleapis.com/Instance",
                            project_id=project_id,
                            location=inst.get("region"),
                            creation_time=inst.get("createTime"),
                            state=inst.get("state"),
                            labels=dict(settings.get("userLabels") or {}),
                            details={
                                "databaseVersion": inst.get("databaseVersion"),
                                "tier": settings.get("tier"),
                                "availabilityType": settings.get("availabilityType"),
                            },
                        )
                    )
                return (
                    GcpServiceStatus(
                        service=service_id,
                        service_name=service_name,
                        status=GcpServiceConnectivityState.SUCCESS,
                        api_endpoint=endpoint,
                        required_role_or_permission=role,
                        message=f"Cloud SQL queried successfully ({len(instances)} instance(s) found).",
                        details={"instance_count": len(instances)},
                    ),
                    instances,
                )
            state, msg = _classify_error(
                resp.status_code, resp.json() if resp.text else {}, service_id=service_id
            )
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=state,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=msg,
                ),
                instances,
            )
        except Exception as exc:
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Request failed: {type(exc).__name__}",
                ),
                instances,
            )

    async def check_compute(
        self,
        client: httpx.AsyncClient,
        token: str,
        project_id: str,
        max_pages: int = 5,
        max_total_vms: int = 200,
    ) -> tuple[GcpServiceStatus, list[GcpResourceItem]]:
        endpoint = (
            f"https://compute.googleapis.com/compute/v1/projects/{project_id}/aggregated/instances"
        )
        service_id = "compute_engine"
        service_name = "Compute Engine"
        role = "roles/compute.viewer"
        instances: list[GcpResourceItem] = []
        seen_names: set[str] = set()

        params: dict[str, Any] = {"maxResults": 50}
        page_count = 0

        try:
            while True:
                page_count += 1
                resp = await self._request(client, "GET", endpoint, token, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    items_by_scope = data.get("items", {})
                    for scope_key, scope_data in items_by_scope.items():
                        vm_list = scope_data.get("instances", [])
                        zone_name = scope_key.replace("zones/", "")
                        for vm in vm_list:
                            vm_name = vm.get("name", "")
                            r_id = f"//compute.googleapis.com/projects/{project_id}/zones/{zone_name}/instances/{vm_name}"
                            if r_id in seen_names:
                                continue
                            seen_names.add(r_id)
                            mtype = vm.get("machineType", "").split("/")[-1]
                            instances.append(
                                GcpResourceItem(
                                    resource_id=r_id,
                                    resource_name=vm_name,
                                    resource_type="compute.googleapis.com/Instance",
                                    project_id=project_id,
                                    location=zone_name,
                                    creation_time=vm.get("creationTimestamp"),
                                    state=vm.get("status"),
                                    labels=dict(vm.get("labels") or {}),
                                    details={
                                        "machineType": mtype,
                                        "status": vm.get("status"),
                                        "zone": zone_name,
                                    },
                                )
                            )
                            if len(instances) >= max_total_vms:
                                break
                        if len(instances) >= max_total_vms:
                            break

                    next_page_token = data.get("nextPageToken")
                    if (
                        next_page_token
                        and page_count < max_pages
                        and len(instances) < max_total_vms
                    ):
                        params["pageToken"] = next_page_token
                    else:
                        break
                else:
                    state, msg = _classify_error(
                        resp.status_code, resp.json() if resp.text else {}, service_id=service_id
                    )
                    return (
                        GcpServiceStatus(
                            service=service_id,
                            service_name=service_name,
                            status=state,
                            api_endpoint=endpoint,
                            required_role_or_permission=role,
                            message=msg,
                        ),
                        instances,
                    )

            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SUCCESS,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Compute Engine queried successfully ({len(instances)} VM(s) found across {page_count} page(s)).",
                    details={"vm_count": len(instances), "pages_retrieved": page_count},
                ),
                instances,
            )
        except Exception as exc:
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Request failed: {type(exc).__name__}",
                ),
                instances,
            )

    async def check_monitoring(
        self, client: httpx.AsyncClient, token: str, project_id: str
    ) -> tuple[GcpServiceStatus, GcpMonitoringSummary]:
        endpoint = f"https://monitoring.googleapis.com/v3/projects/{project_id}/metricDescriptors"
        service_id = "cloud_monitoring"
        service_name = "Cloud Monitoring"
        role = "roles/monitoring.viewer"
        summary = GcpMonitoringSummary()

        try:
            resp = await self._request(client, "GET", endpoint, token, params={"pageSize": 20})
            if resp.status_code == 200:
                data = resp.json()
                descriptors = data.get("metricDescriptors", [])
                summary.metric_descriptors_count = len(descriptors)
                res_types = list(
                    {
                        d.get("monitoredResourceTypes", ["gce_instance"])[0]
                        for d in descriptors
                        if d.get("monitoredResourceTypes")
                    }
                )
                summary.available_monitored_resources = res_types
                if descriptors:
                    summary.message = (
                        f"Monitoring active ({len(descriptors)} metric descriptors sampled)."
                    )
                else:
                    summary.message = "Cloud Monitoring queried successfully (0 metric descriptors found; no active workloads emitting metrics)."
                return (
                    GcpServiceStatus(
                        service=service_id,
                        service_name=service_name,
                        status=GcpServiceConnectivityState.SUCCESS,
                        api_endpoint=endpoint,
                        required_role_or_permission=role,
                        message=summary.message,
                        details={"sampled_descriptors": len(descriptors)},
                    ),
                    summary,
                )
            state, msg = _classify_error(
                resp.status_code, resp.json() if resp.text else {}, service_id=service_id
            )
            summary.message = msg
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=state,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=msg,
                ),
                summary,
            )
        except Exception as exc:
            summary.message = f"Request failed: {type(exc).__name__}"
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=summary.message,
                ),
                summary,
            )

    async def check_recommender(
        self, client: httpx.AsyncClient, token: str, project_id: str
    ) -> tuple[GcpServiceStatus, list[GcpRecommenderItem]]:
        endpoint = (
            f"https://recommender.googleapis.com/v1/projects/{project_id}/locations/global/recommenders/"
            "google.compute.instance.IdleResourceRecommender/recommendations"
        )
        service_id = "cloud_recommender"
        service_name = "Cloud Recommender"
        role = "roles/recommender.viewer"
        recommendations: list[GcpRecommenderItem] = []

        try:
            resp = await self._request(client, "GET", endpoint, token)
            if resp.status_code == 200:
                data = resp.json()
                raw_recs = data.get("recommendations", [])
                for r in raw_recs:
                    r_id = r.get("name", "").split("/")[-1]
                    recommendations.append(
                        GcpRecommenderItem(
                            recommendation_id=r_id,
                            category=r.get("recommenderSubtype", "COST_OPTIMIZATION"),
                            resource_id=r.get("targetResources", [""])[0]
                            if r.get("targetResources")
                            else "",
                            description=r.get("description", "GCP optimization recommendation."),
                            state=r.get("stateInfo", {}).get("state", "ACTIVE"),
                            estimated_impact=r.get("primaryImpact") or {},
                        )
                    )
                msg = (
                    f"Cloud Recommender queried ({len(recommendations)} recommendation(s) found)."
                    if recommendations
                    else "Cloud Recommender queried successfully (0 recommendations found)."
                )
                return (
                    GcpServiceStatus(
                        service=service_id,
                        service_name=service_name,
                        status=GcpServiceConnectivityState.SUCCESS,
                        api_endpoint=endpoint,
                        required_role_or_permission=role,
                        message=msg,
                        details={"count": len(recommendations)},
                    ),
                    recommendations,
                )
            state, msg = _classify_error(
                resp.status_code, resp.json() if resp.text else {}, service_id=service_id
            )
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=state,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=msg,
                ),
                recommendations,
            )
        except Exception as exc:
            return (
                GcpServiceStatus(
                    service=service_id,
                    service_name=service_name,
                    status=GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
                    api_endpoint=endpoint,
                    required_role_or_permission=role,
                    message=f"Request failed: {type(exc).__name__}",
                ),
                recommendations,
            )

    # ----------------------------------------------------------- Full Evaluation

    async def test_connection(
        self,
        service_account_json: str | dict[str, Any],
        project_id: str,
        connection_name: str = "GCP Connection",
    ) -> GcpTestConnectionResponse:
        """Validate Service Account credentials and probe all 8 GCP services independently."""
        _ = connection_name
        # 1. Parse & validate JSON structure
        creds_data, info = self.auth_service.parse_and_validate_json(
            service_account_json, expected_project_id=project_id
        )

        # 2. Acquire OAuth2 access token
        token = self.auth_service.acquire_token(creds_data)

        # 3. Verify principal identity via tokeninfo if running in live mode
        if self.transport is None:
            try:
                await self.auth_service.verify_principal(token, expected_client_id=info.client_id)
            except Exception as exc:
                logger.warning("gcp_principal_verification_note", error=str(exc))

        # 4. Probe all services independently via AsyncClient
        services_status: list[GcpServiceStatus] = []
        async with httpx.AsyncClient(
            transport=self.transport, timeout=self.timeout_seconds
        ) as client:
            # Service Usage & Resource Manager
            crm_status, _ = await self.check_resource_manager(client, token, info.project_id)
            services_status.append(crm_status)

            su_status, _ = await self.check_service_usage(client, token, info.project_id)
            services_status.append(su_status)

            asset_status, _ = await self.check_asset_inventory(client, token, info.project_id)
            services_status.append(asset_status)

            storage_status, _ = await self.check_storage(client, token, info.project_id)
            services_status.append(storage_status)

            sql_status, _ = await self.check_sql(client, token, info.project_id)
            services_status.append(sql_status)

            compute_status, _ = await self.check_compute(client, token, info.project_id)
            services_status.append(compute_status)

            monitoring_status, _ = await self.check_monitoring(client, token, info.project_id)
            services_status.append(monitoring_status)

            recommender_status, _ = await self.check_recommender(client, token, info.project_id)
            services_status.append(recommender_status)

        # Determine overall status excluding DEFERRED services from failure calculation
        non_deferred = [
            s for s in services_status if s.status != GcpServiceConnectivityState.DEFERRED
        ]
        non_deferred_success = sum(
            1 for s in non_deferred if s.status == GcpServiceConnectivityState.SUCCESS
        )
        non_deferred_failures = sum(
            1
            for s in non_deferred
            if s.status
            in (
                GcpServiceConnectivityState.PERMISSION_DENIED,
                GcpServiceConnectivityState.API_DISABLED,
                GcpServiceConnectivityState.SERVICE_UNAVAILABLE,
                GcpServiceConnectivityState.RESOURCE_NOT_FOUND,
            )
        )

        if crm_status.status == GcpServiceConnectivityState.SUCCESS:
            if non_deferred_failures == 0 and non_deferred_success >= 1:
                overall = "Connected"
                is_success = True
            else:
                overall = "Partially Connected"
                is_success = True
        elif crm_status.status == GcpServiceConnectivityState.PERMISSION_DENIED:
            overall = "Permission Denied"
            is_success = False
        else:
            overall = "Partially Connected" if non_deferred_success > 0 else "Authentication Failed"
            is_success = non_deferred_success > 0

        return GcpTestConnectionResponse(
            success=is_success,
            project_id=info.project_id,
            client_email=info.client_email,
            private_key_id=info.private_key_id,
            overall_status=overall,
            billing_status="DEFERRED",
            services=services_status,
            tested_at=datetime.now(UTC),
            error_summary=crm_status.message if not is_success else None,
        )

    async def discover_resources(
        self,
        service_account_json: str | dict[str, Any],
        project_id: str,
    ) -> GcpDiscoveryResponse:
        """Execute full read-only resource discovery across all connected GCP services with deduplication."""
        creds_data, info = self.auth_service.parse_and_validate_json(
            service_account_json, expected_project_id=project_id
        )
        token = self.auth_service.acquire_token(creds_data)

        services_status: list[GcpServiceStatus] = []
        all_resources: list[GcpResourceItem] = []
        seen_ids: set[str] = set()
        notes: list[str] = []
        is_partial = False

        async with httpx.AsyncClient(
            transport=self.transport, timeout=self.timeout_seconds
        ) as client:
            # 1. Project metadata
            crm_status, project_meta = await self.check_resource_manager(
                client, token, info.project_id
            )
            services_status.append(crm_status)
            if crm_status.status != GcpServiceConnectivityState.SUCCESS:
                is_partial = True
                notes.append(f"Resource Manager: {crm_status.status.value} ({crm_status.message})")

            # 2. Service Usage
            su_status, _ = await self.check_service_usage(client, token, info.project_id)
            services_status.append(su_status)

            # 3. Asset Inventory
            asset_status, asset_resources = await self.check_asset_inventory(
                client, token, info.project_id
            )
            services_status.append(asset_status)
            if asset_status.status == GcpServiceConnectivityState.SUCCESS:
                for r in asset_resources:
                    if r.resource_id not in seen_ids:
                        seen_ids.add(r.resource_id)
                        all_resources.append(r)
            else:
                is_partial = True
                notes.append(
                    f"Asset Inventory: {asset_status.status.value} ({asset_status.message})"
                )

            # 4. Storage Buckets
            storage_status, storage_buckets = await self.check_storage(
                client, token, info.project_id
            )
            services_status.append(storage_status)
            if storage_status.status == GcpServiceConnectivityState.SUCCESS:
                for b in storage_buckets:
                    if b.resource_id not in seen_ids:
                        seen_ids.add(b.resource_id)
                        all_resources.append(b)
            else:
                is_partial = True
                notes.append(
                    f"Cloud Storage: {storage_status.status.value} ({storage_status.message})"
                )

            # 5. Cloud SQL
            sql_status, sql_instances = await self.check_sql(client, token, info.project_id)
            services_status.append(sql_status)
            if sql_status.status == GcpServiceConnectivityState.SUCCESS:
                for s in sql_instances:
                    if s.resource_id not in seen_ids:
                        seen_ids.add(s.resource_id)
                        all_resources.append(s)
            else:
                is_partial = True
                notes.append(f"Cloud SQL: {sql_status.status.value} ({sql_status.message})")

            # 6. Compute Engine
            compute_status, compute_vms = await self.check_compute(client, token, info.project_id)
            services_status.append(compute_status)
            if compute_status.status == GcpServiceConnectivityState.SUCCESS:
                for vm in compute_vms:
                    if vm.resource_id not in seen_ids:
                        seen_ids.add(vm.resource_id)
                        all_resources.append(vm)
            elif compute_status.status == GcpServiceConnectivityState.DEFERRED:
                notes.append(f"Compute Engine: DEFERRED ({compute_status.message})")
            else:
                is_partial = True
                notes.append(
                    f"Compute Engine: {compute_status.status.value} ({compute_status.message})"
                )

            # 7. Cloud Monitoring
            mon_status, mon_summary = await self.check_monitoring(client, token, info.project_id)
            services_status.append(mon_status)

            # 8. Recommender
            rec_status, recs = await self.check_recommender(client, token, info.project_id)
            services_status.append(rec_status)

        return GcpDiscoveryResponse(
            project_id=info.project_id,
            project_metadata=project_meta,
            total_resources=len(all_resources),
            resources=all_resources,
            recommendations=recs,
            monitoring=mon_summary,
            services_status=services_status,
            discovered_at=datetime.now(UTC),
            partial_discovery=is_partial,
            discovery_notes=notes,
        )


# Singleton instance
_conn_service: GcpConnectivityService | None = None


def get_gcp_connectivity_service() -> GcpConnectivityService:
    global _conn_service
    if _conn_service is None:
        _conn_service = GcpConnectivityService()
    return _conn_service
