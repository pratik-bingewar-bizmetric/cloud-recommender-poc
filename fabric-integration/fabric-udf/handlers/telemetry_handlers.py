"""Azure Monitor telemetry RPC handlers for Microsoft Fabric UDF."""

import os
from typing import Any, Optional
import urllib.error

from pydantic import ValidationError
from schemas.models import (
    GetMetricsArgs,
    MetricPoint,
    MetricSeries,
    ResourceMetricsResult,
    UdfResponse,
)
from services.azure_real_client import AzureRealClient
from services.lakehouse_store import FabricLakehouseStore


async def handle_get_metrics(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    args: dict[str, Any],
    analytical_repo: Optional[Any] = None,
) -> dict[str, Any]:
    """Retrieve actual Azure Monitor metrics from OneLake Delta Lake or live Azure Monitor API."""
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

    # 1. Primary Path: OneLake Delta Analytical Storage
    analytics_source = os.getenv("FINOPS_ANALYTICS_SOURCE", "onelake").lower()
    if analytical_repo and analytics_source == "onelake":
        envelope = analytical_repo.get_metrics_summary(
            connection_id=parsed.connection_id,
            resource_id=parsed.resource_id,
            metric_names=parsed.metric_names,
            days=parsed.days,
        )
        if envelope.status == "success" and envelope.data and envelope.data.series:
            metric_series_list = []
            for s in envelope.data.series:
                pts = [
                    MetricPoint(
                        timestamp=p.timestamp,
                        average=p.average,
                        maximum=p.maximum,
                        minimum=p.minimum,
                    )
                    for p in s.points
                ]
                metric_series_list.append(
                    MetricSeries(
                        metric_name=s.metric_name,
                        unit=s.unit,
                        points=pts,
                    )
                )
            result = ResourceMetricsResult(
                resource_id=parsed.resource_id,
                time_grain=parsed.time_grain,
                series=metric_series_list,
            )
            resp_dict = UdfResponse(
                status="success",
                data=result.model_dump(mode="json"),
            ).model_dump(mode="json")
            resp_dict["data_source"] = "onelake_delta"
            resp_dict["points_count"] = envelope.data.total_points_evaluated
            resp_dict["distinct_buckets"] = envelope.data.distinct_time_buckets
            return resp_dict
        elif envelope.status == "error":
            return UdfResponse(
                status="error",
                error_code=envelope.error_code or "LAKEHOUSE_READ_ERROR",
                error_message=f"Failed reading metrics from OneLake Delta Lake: {envelope.error_message}",
            ).model_dump(mode="json")

    # 2. Local Fallback Path: Live Azure Monitor API
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
