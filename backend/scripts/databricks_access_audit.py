"""Read-only Databricks access audit (M2.5).

Independently probes every API the application uses with a chosen identity and prints a
JSON matrix. Guarantees:
- never prints a secret or access token (only non-secret JWT claims),
- never executes SQL, never starts a warehouse or cluster, never mutates anything,
- every API is tested on its own (a successful token request proves nothing about APIs).

Usage (from the repository root so `.env` is found):
    PYTHONPATH=backend/src python backend/scripts/databricks_access_audit.py <connection_id> <sp|cli>
"""

import base64
import json
import sys
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError

from cloud_recommender.core.config import get_settings
from cloud_recommender.services.databricks.workspace_service import DatabricksWorkspaceService

SAFE_CLAIMS = ("iss", "sub", "aud", "azp", "scope", "scp", "exp", "iat", "client_id")
STATUS_BY_CODE = {
    "PERMISSION_DENIED": 403,
    "UNAUTHENTICATED": 401,
    "NOT_FOUND": 404,
    "RESOURCE_DOES_NOT_EXIST": 404,
    "BAD_REQUEST": 400,
    "INVALID_PARAMETER_VALUE": 400,
    "FEATURE_DISABLED": 403,
    "TEMPORARILY_UNAVAILABLE": 503,
}


def _claims(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:  # noqa: BLE001 - opaque tokens have no claims
        return {}
    return {k: data[k] for k in SAFE_CLAIMS if k in data}


def probe_token(host: str, client_id: str, secret: str) -> dict[str, Any]:
    """Client-credentials token request against the workspace OIDC endpoint."""
    started = time.monotonic()
    try:
        r = httpx.post(
            f"{host.rstrip('/')}/oidc/v1/token",
            auth=(client_id, secret),
            data={"grant_type": "client_credentials", "scope": "all-apis"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        return {"ok": False, "http_status": None, "error": type(exc).__name__}
    out: dict[str, Any] = {
        "ok": r.status_code == 200,
        "http_status": r.status_code,
        "latency_ms": int((time.monotonic() - started) * 1000),
    }
    if r.status_code == 200:
        body = r.json()
        out.update(
            token_type=body.get("token_type"),
            scope=body.get("scope"),
            expires_in=body.get("expires_in"),
            claims=_claims(body.get("access_token", "")),
        )
    else:
        out["error"] = (r.text or "")[:200].replace(secret, "[REDACTED]")
    return out


def _record(fn: Any) -> dict[str, Any]:
    """Run one probe; return status/permission/count/pagination/error, never raise."""
    started = time.monotonic()
    try:
        count, has_more, extra = fn()
        res: dict[str, Any] = {
            "http_status": 200,
            "auth": "OK",
            "permission": "GRANTED",
            "count": count,
            "pagination": "COMPLETE" if not has_more else "MORE_PAGES",
        }
        res.update(extra or {})
    except DatabricksError as exc:
        code = getattr(exc, "error_code", None) or type(exc).__name__
        status = STATUS_BY_CODE.get(str(code).upper(), None)
        auth = "FAILED" if status == 401 else "OK"
        perm = "DENIED" if status == 403 else ("NOT_FOUND" if status == 404 else "UNKNOWN")
        res = {
            "http_status": status,
            "auth": auth,
            "permission": perm,
            "count": None,
            "pagination": None,
            "error": f"{code}: {str(exc)[:220]}",
        }
    except Exception as exc:  # noqa: BLE001
        res = {
            "http_status": None,
            "auth": "UNKNOWN",
            "permission": "UNKNOWN",
            "count": None,
            "pagination": None,
            "error": f"{type(exc).__name__}: {str(exc)[:220]}",
        }
    res["latency_ms"] = int((time.monotonic() - started) * 1000)
    res["retrieved_at"] = datetime.now(UTC).isoformat() if res.get("http_status") == 200 else None
    return res


def _listing(it: Any, cap: int = 2000) -> tuple[int, bool, dict[str, Any]]:
    n = 0
    for _ in it:
        n += 1
        if n >= cap:
            return n, True, {}
    return n, False, {}


def run(w: WorkspaceClient) -> dict[str, Any]:
    api: dict[str, Any] = {}
    me: dict[str, Any] = {}

    def current_user() -> tuple[int, bool, dict[str, Any]]:
        u = w.current_user.me()
        me.update(user_name=u.user_name, id=u.id, active=u.active)
        return 1, False, {"identity": {"user_name": u.user_name, "id": u.id}}

    api["current_user"] = _record(current_user)
    api["clusters"] = _record(lambda: _listing(w.clusters.list()))
    whs: list[Any] = []

    def warehouses() -> tuple[int, bool, dict[str, Any]]:
        whs.extend(w.warehouses.list())
        return len(whs), False, {"states": {x.name: str(x.state) for x in whs}}

    api["sql_warehouses"] = _record(warehouses)
    api["jobs"] = _record(lambda: _listing(w.jobs.list(limit=25)))
    api["job_runs"] = _record(lambda: _listing(w.jobs.list_runs(limit=25), cap=100))
    api["pipelines"] = _record(lambda: _listing(w.pipelines.list_pipelines()))
    api["model_serving"] = _record(lambda: _listing(w.serving_endpoints.list()))
    api["databricks_apps"] = _record(lambda: _listing(w.apps.list()))
    api["mlflow_experiments"] = _record(
        lambda: _listing(w.experiments.list_experiments(max_results=100), cap=500)
    )
    api["query_history"] = _record(
        lambda: _listing(w.query_history.list(max_results=50).res or [], cap=50)
    )
    api["unity_catalog_catalogs"] = _record(lambda: _listing(w.catalogs.list()))

    def metastore() -> tuple[int, bool, dict[str, Any]]:
        s = w.metastores.summary()
        return (
            1,
            False,
            {
                "metastore_id": s.metastore_id,
                "cloud": s.cloud,
                "region": s.region,
                "privilege_model_version": s.privilege_model_version,
            },
        )

    api["metastore_summary"] = _record(metastore)
    api["system_schemas_list"] = _record(lambda: _listing(w.schemas.list(catalog_name="system")))
    api["system_billing_tables"] = _record(
        lambda: _listing(w.tables.list(catalog_name="system", schema_name="billing"))
    )
    api["system_serving_tables"] = _record(
        lambda: _listing(w.tables.list(catalog_name="system", schema_name="serving"))
    )
    api["system_ai_gateway_tables"] = _record(
        lambda: _listing(w.tables.list(catalog_name="system", schema_name="ai_gateway"))
    )
    api["system_compute_tables"] = _record(
        lambda: _listing(w.tables.list(catalog_name="system", schema_name="compute"))
    )
    api["system_query_tables"] = _record(
        lambda: _listing(w.tables.list(catalog_name="system", schema_name="query"))
    )

    def grants(full: str) -> Any:
        def inner() -> tuple[int, bool, dict[str, Any]]:

            eff = w.grants.get_effective("table", full)
            who = me.get("user_name")
            mine = [a for a in (eff.privilege_assignments or []) if a.principal == who]
            privs = sorted({str(p.privilege) for a in mine for p in (a.privileges or [])})
            principals = sorted(
                {a.principal for a in (eff.privilege_assignments or []) if a.principal}
            )
            return (
                len(privs),
                False,
                {
                    "effective_privileges_for_caller": privs,
                    "principals_with_grants": principals[:20],
                },
            )

        return inner

    api["grants_system.billing.usage"] = _record(grants("system.billing.usage"))
    api["grants_system.billing.list_prices"] = _record(grants("system.billing.list_prices"))
    api["grants_system.query.history"] = _record(grants("system.query.history"))
    for wh in whs[:3]:
        api[f"warehouse_permissions:{wh.id}"] = _record(
            lambda wh=wh: (
                len(list(w.warehouses.get_permissions(wh.id).access_control_list or [])),
                False,
                {},
            )
        )
    return api


def main() -> None:
    conn_id, mode = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "sp")
    settings = get_settings()
    conn = DatabricksWorkspaceService().get_connection(conn_id)
    if conn is None:
        sys.exit("unknown connection")
    host = conn.workspace_url.rstrip("/")
    out: dict[str, Any] = {
        "connection_id": conn_id,
        "workspace_id": conn.workspace_id,
        "host": host,
        "mode": mode,
        "audited_at": datetime.now(UTC).isoformat(),
    }
    if mode == "sp":
        cid, secret = settings.databricks_client_id, settings.databricks_client_secret
        if not cid or not secret:
            sys.exit("DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET not configured")
        out["client_id"] = cid
        out["token"] = probe_token(host, cid, secret)
        if not out["token"]["ok"]:
            print(json.dumps(out, indent=1))
            return
        w = WorkspaceClient(host=host, client_id=cid, client_secret=secret, auth_type="oauth-m2m")
    else:
        w = WorkspaceClient(host=host, auth_type="azure-cli")
    out["apis"] = run(w)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
