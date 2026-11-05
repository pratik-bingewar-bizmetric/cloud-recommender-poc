"""FinOps cost waste analysis RPC handlers for Microsoft Fabric UDF."""

import logging
import urllib.error
from typing import Any

from pydantic import ValidationError
from schemas.models import (
    GetWasteArgs,
    UdfResponse,
    WasteSummary,
)
from services.azure_real_client import AzureRealClient
from services.lakehouse_store import FabricLakehouseStore
from services.waste_detector import FinOpsWasteDetector

logger = logging.getLogger(__name__)


async def handle_get_waste(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    waste_detector: FinOpsWasteDetector,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Execute deterministic FinOps waste detection on actual discovered resources."""
    try:
        parsed = GetWasteArgs(**args)
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

    # Fetch resources
    resources = store.get_inventory(parsed.connection_id)
    secret = store.get_connection_secret(parsed.connection_id)
    token, _ = await azure_client.get_access_token(
        tenant_id=conn.tenant_or_org_id,
        client_id=conn.client_id,
        client_secret=secret,
    )

    if (parsed.force_refresh or not resources) and token:
        try:
            resources = await azure_client.query_resource_graph(
                token=token,
                subscription_id=conn.scope_id,
            )
            store.save_inventory(parsed.connection_id, resources)
        except (RuntimeError, urllib.error.URLError, OSError) as exc:
            logger.debug(f"live_arg_waste_query_failed: {exc}")

    if not resources:
        # Return empty waste summary with honest zero counts
        empty_summary = WasteSummary(connection_id=parsed.connection_id)
        return UdfResponse(
            status="success",
            data=empty_summary.model_dump(mode="json"),
        ).model_dump(mode="json")

    # Collect CPU metrics for running VMs if token is available
    vm_cpu_metrics: dict[str, float] = {}
    if token:
        running_vms = [
            r
            for r in resources
            if "microsoft.compute/virtualmachines" in r.resource_type.lower()
            and (r.power_state or "").lower() in ("running", "powerstate/running")
        ]
        for vm in running_vms[:10]:  # Limit to 10 for latency bounds
            try:
                metrics_resp = await azure_client.query_monitor_metrics(
                    token=token,
                    resource_id=vm.resource_id,
                    metric_names=["Percentage CPU"],
                    time_grain="PT1H",
                    days=7,
                )
                # Find max CPU across series
                for s in metrics_resp.series:
                    max_val = max(
                        (p.maximum for p in s.points if p.maximum is not None),
                        default=None,
                    )
                    if max_val is not None:
                        vm_cpu_metrics[vm.resource_id] = float(max_val)
            except (RuntimeError, urllib.error.URLError, OSError) as exc:
                logger.debug(
                    f"vm_cpu_metric_query_failed vm_id={vm.resource_id} error={exc}"
                )

    summary = waste_detector.analyze_waste(
        connection_id=parsed.connection_id,
        resources=resources,
        vm_cpu_metrics=vm_cpu_metrics,
    )

    return UdfResponse(
        status="success",
        data=summary.model_dump(mode="json"),
    ).model_dump(mode="json")
