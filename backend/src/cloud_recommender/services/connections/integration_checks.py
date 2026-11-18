"""Per-integration validation for a connection (read-only probes).

Authentication success never implies every integration works. Each integration is evaluated and
reported on its own: connected / permission_denied / not_configured / unavailable / error.
Cost problems are reported as a state, never as zero spend.

Azure permissions are derived from the principal's OWN effective permissions on the subscription
(``Microsoft.Authorization/permissions``: a read that consumes no Cost Management quota), which
also reveals write-capable grants so a read-only policy can be enforced.
"""

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from cloud_recommender.schemas.connections import IntegrationState, IntegrationStatus
from cloud_recommender.services.azure_live.arm_client import ArmResponse, AzureArmClient

logger = structlog.get_logger(__name__)

API_PERMISSIONS = "2022-04-01"
READ_ACTIONS = {
    "resource_manager": "Microsoft.Resources/subscriptions/resourceGroups/read",
    "cost_management": "Microsoft.CostManagement/query/read",
    "monitor": "Microsoft.Insights/metrics/read",
}
REQUIRED_ROLES = {
    "resource_manager": "Reader",
    "cost_management": "Cost Management Reader",
    "monitor": "Monitoring Reader",
}
# Wildcards that grant nothing harmful (e.g. Reader includes support-ticket access).
BENIGN_WILDCARDS = {"microsoft.support/*"}
_DATABRICKS_HOSTS = (".azuredatabricks.net", ".databricks.azure.cn", ".databricks.azure.us")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


def _matches(pattern: str, action: str) -> bool:
    return fnmatch.fnmatchcase(action.lower(), pattern.lower())


@dataclass
class PermissionReport:
    """What the principal can do on the subscription, evaluated from its effective permissions."""

    resource_manager: bool = False
    cost_management: bool = False
    monitor: bool = False
    write_patterns: list[str] = field(default_factory=list)

    @property
    def has_write_access(self) -> bool:
        return bool(self.write_patterns)


def evaluate_permissions(blocks: list[dict[str, Any]]) -> PermissionReport:
    """Evaluate ARM permission blocks ({actions, notActions}) into capabilities."""
    report = PermissionReport()

    def allowed(action: str) -> bool:
        for block in blocks:
            if any(_matches(p, action) for p in block.get("notActions", [])):
                continue
            if any(_matches(p, action) for p in block.get("actions", [])):
                return True
        return False

    report.resource_manager = allowed(READ_ACTIONS["resource_manager"])
    report.cost_management = allowed(READ_ACTIONS["cost_management"])
    report.monitor = allowed(READ_ACTIONS["monitor"])
    for block in blocks:
        for pattern in block.get("actions", []):
            lowered = pattern.lower()
            if lowered in BENIGN_WILDCARDS:
                continue
            last = lowered.rsplit("/", 1)[-1]
            if lowered == "*" or last in ("write", "delete", "*"):
                if not any(
                    _matches(n, pattern)
                    for n in block.get("notActions", [])
                    if n.lower() == lowered
                ):
                    report.write_patterns.append(pattern)
    report.write_patterns = sorted(set(report.write_patterns))[:10]
    return report


def _status(
    integration: str,
    state: IntegrationState,
    message: str | None = None,
    required: str | None = None,
    **details: Any,
) -> IntegrationStatus:
    return IntegrationStatus(
        integration=integration,
        state=state,
        message=message,
        required_permission=required,
        details=details,
    )


async def fetch_permission_report(
    client: AzureArmClient, subscription_id: str
) -> tuple[PermissionReport | None, ArmResponse]:
    response = await client.get(
        f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/permissions",
        API_PERMISSIONS,
    )
    if not response.ok:
        return None, response
    return evaluate_permissions((response.body or {}).get("value", [])), response


def azure_integration_statuses(
    report: PermissionReport | None, response: ArmResponse
) -> list[IntegrationStatus]:
    """ARM, Cost Management and Monitor, evaluated separately."""
    if report is None:
        reason = (
            "The service principal could not read its own permissions on the subscription."
            if response.status_code in (401, 403)
            else "Permissions could not be verified (Azure returned an error)."
        )
        state = (
            IntegrationState.PERMISSION_DENIED
            if response.status_code == 403
            else IntegrationState.UNAVAILABLE
        )
        return [
            _status(name, state, reason, REQUIRED_ROLES[name], http_status=response.status_code)
            for name in ("resource_manager", "cost_management", "monitor")
        ]
    out: list[IntegrationStatus] = []
    for name, granted in (
        ("resource_manager", report.resource_manager),
        ("cost_management", report.cost_management),
        ("monitor", report.monitor),
    ):
        if granted:
            out.append(_status(name, IntegrationState.CONNECTED))
        else:
            out.append(
                _status(
                    name,
                    IntegrationState.PERMISSION_DENIED,
                    f"The service principal lacks the '{REQUIRED_ROLES[name]}' role on the subscription.",
                    REQUIRED_ROLES[name],
                )
            )
    return out


def _http_state(status_code: int | None) -> IntegrationState:
    if status_code in (401, 403):
        return IntegrationState.PERMISSION_DENIED
    if status_code in (400, 404):
        return IntegrationState.UNAVAILABLE
    return IntegrationState.ERROR


async def _get(
    url: str, token: str, transport: httpx.AsyncBaseTransport | None
) -> tuple[int | None, Any]:
    try:
        async with httpx.AsyncClient(
            timeout=20.0, transport=transport, follow_redirects=False
        ) as client:
            response = await client.get(
                url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
            )
    except httpx.HTTPError as exc:
        logger.warning("integration_probe_failed", error_type=type(exc).__name__)
        return None, None
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


def validate_databricks_url(url: str) -> str | None:
    """Return the normalized workspace URL, or None when it is not an Azure Databricks workspace."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host.endswith(_DATABRICKS_HOSTS)
        or parsed.username
        or parsed.port
    ):
        return None
    return f"https://{host}"


async def check_databricks(
    workspace_url: str | None,
    workspace_id: str | None,
    token: str | None,
    token_error: str | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> IntegrationStatus:
    if not workspace_url:
        return _status(
            "databricks",
            IntegrationState.NOT_CONFIGURED,
            "No Databricks workspace URL was provided.",
        )
    normalized = validate_databricks_url(workspace_url)
    if normalized is None:
        return _status(
            "databricks",
            IntegrationState.ERROR,
            "The workspace URL must be an https Azure Databricks URL (https://adb-<id>.<n>.azuredatabricks.net).",
        )
    if token is None:
        return _status(
            "databricks",
            IntegrationState.PERMISSION_DENIED,
            token_error or "No Databricks token could be obtained.",
        )
    status_code, body = await _get(f"{normalized}/api/2.0/preview/scim/v2/Me", token, transport)
    if status_code != 200:
        state = _http_state(status_code)
        message = (
            "The service principal is not a user of this workspace. Add it to the workspace "
            "(Admin settings > Identity and access) with at least Workspace access."
            if state == IntegrationState.PERMISSION_DENIED
            else "The workspace could not be validated (check the workspace URL)."
        )
        return _status("databricks", state, message, "Workspace user", http_status=status_code)
    wh_status, wh_body = await _get(f"{normalized}/api/2.0/sql/warehouses", token, transport)
    warehouses = (
        len((wh_body or {}).get("warehouses", []))
        if wh_status == 200 and isinstance(wh_body, dict)
        else None
    )
    return _status(
        "databricks",
        IntegrationState.CONNECTED,
        None,
        workspace_url=normalized,
        workspace_id=workspace_id,
        warehouses_visible=warehouses,
        warehouses_check=(
            "ok" if warehouses is not None else f"permission/availability: HTTP {wh_status}"
        ),
        system_tables="not verified: reading system tables needs an approved SQL execution",
    )


async def check_fabric(
    fabric_base_url: str,
    workspace_id: str | None,
    token: str | None,
    token_error: str | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> IntegrationStatus:
    if not workspace_id:
        return _status(
            "fabric", IntegrationState.NOT_CONFIGURED, "No Fabric workspace ID was provided."
        )
    if not _GUID.match(workspace_id.strip()):
        return _status("fabric", IntegrationState.ERROR, "The Fabric workspace ID must be a GUID.")
    if token is None:
        return _status(
            "fabric",
            IntegrationState.PERMISSION_DENIED,
            token_error or "No Fabric token could be obtained for this service principal.",
        )
    base = fabric_base_url.rstrip("/")
    ws = workspace_id.strip()
    status_code, body = await _get(f"{base}/v1/workspaces/{ws}", token, transport)
    if status_code != 200 or not isinstance(body, dict):
        state = _http_state(status_code)
        message = (
            "The service principal cannot access this workspace. Add it to the workspace (Viewer or "
            "higher) and allow service principals to use Fabric APIs in the Fabric tenant settings."
            if state == IntegrationState.PERMISSION_DENIED
            else "The Fabric workspace was not found, or it is not visible to this principal."
        )
        return _status("fabric", state, message, "Workspace Viewer", http_status=status_code)
    lh_status, lh_body = await _get(f"{base}/v1/workspaces/{ws}/lakehouses", token, transport)
    lakehouses = (
        [h.get("displayName") for h in (lh_body or {}).get("value", []) if isinstance(h, dict)]
        if lh_status == 200 and isinstance(lh_body, dict)
        else None
    )
    capacity_id = body.get("capacityId")
    return _status(
        "fabric",
        IntegrationState.CONNECTED,
        None,
        workspace_name=body.get("displayName"),
        capacity_id=capacity_id,
        lakehouses=lakehouses,
        lakehouses_check=(
            "ok" if lakehouses is not None else f"permission/availability: HTTP {lh_status}"
        ),
    )
