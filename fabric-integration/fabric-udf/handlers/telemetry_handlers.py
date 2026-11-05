"""Azure Monitor telemetry RPC handlers for Microsoft Fabric UDF."""

from typing import Any
import urllib.error

from pydantic import ValidationError
from schemas.models import (
    GetMetricsArgs,
    UdfResponse,
)
from services.azure_real_client import AzureRealClient
from services.lakehouse_store import FabricLakehouseStore


async def handle_get_metrics(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve actual Azure Monitor metrics for a specific ARM resource."""
    try:
        parsed = GetMetricsArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    conn = store.get_connection(parsed.connection_id)
    if not conn:
        return UdfResponse(
            status="error",
            error_code="CONNECTION_NOT_FOUND",
            error_message=f"Connection '{parsed.connection_id}' not found.",
        ).model_dump(mode="json")

    secret = store.get_connection_secret(parsed.connection_id)
    token, _ = await azure_client.get_access_token(
        tenant_id=conn.tenant_or_org_id,
        client_id=conn.client_id,
        client_secret=secret,
    )

    if not token:
        return UdfResponse(
            status="error",
            error_code="UNAUTHENTICATED",
            error_message="Azure credentials unavailable or expired to query Azure Monitor.",
        ).model_dump(mode="json")

    try:
        metrics_resp = await azure_client.query_monitor_metrics(
            token=token,
            resource_id=parsed.resource_id,
            metric_names=parsed.metric_names,
            time_grain=parsed.time_grain,
            days=parsed.days,
        )
        return UdfResponse(
            status="success",
            data=metrics_resp.model_dump(mode="json"),
        ).model_dump(mode="json")
    except (RuntimeError, urllib.error.URLError, OSError) as exc:
        return UdfResponse(
            status="error",
            error_code="METRICS_QUERY_FAILED",
            error_message=f"Azure Monitor metrics query failed: {exc}",
        ).model_dump(mode="json")
