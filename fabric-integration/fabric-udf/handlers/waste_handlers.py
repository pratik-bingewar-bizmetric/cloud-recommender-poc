"""FinOps cost waste analysis RPC handlers for Microsoft Fabric UDF."""

import logging
import os
from typing import Any, Optional
import urllib.error

from pydantic import ValidationError
from schemas.models import (
    DiscoveredResource,
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
    analytical_repo: Optional[Any] = None,
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

    resources: list[DiscoveredResource] = []
    vm_cpu_metrics: dict[str, float] = {}

    # 1. Primary Path: OneLake Delta Analytical Storage
    analytics_source = os.getenv("FINOPS_ANALYTICS_SOURCE", "onelake").lower()
    if analytical_repo and analytics_source == "onelake":
        envelope = analytical_repo.get_inventory_summary(
            connection_id=parsed.connection_id,
            subscription_id=conn.scope_id if conn else None,
        )
        if envelope.status == "success" and envelope.data and envelope.data.resources:
            resources = [
                DiscoveredResource(
                    resource_id=item.resource_id,
                    name=item.name,
                    resource_type=item.resource_type,
                    resource_group=item.resource_group,
                    location=item.location,
                    sku_name=item.sku_name,
                    power_state=item.power_state,
                    tags=item.tags or {},
                    monthly_retail_cost=item.monthly_retail_cost,
                )
                for item in envelope.data.resources
            ]
            # Check metrics for running VMs from OneLake
            running_vms = [
                r
                for r in resources
                if "microsoft.compute/virtualmachines" in r.resource_type.lower()
                and (r.power_state or "").lower() in ("running", "powerstate/running")
            ]
            for vm in running_vms[:10]:
                m_env = analytical_repo.get_metrics_summary(
                    connection_id=parsed.connection_id,
                    resource_id=vm.resource_id,
                    metric_names=["Percentage CPU", "cpu_percent"],
                    days=7,
                )
                if m_env.status == "success" and m_env.data and m_env.data.series:
                    for s in m_env.data.series:
                        if s.peak_utilization is not None:
                            vm_cpu_metrics[vm.resource_id] = s.peak_utilization

            waste_summary = waste_detector.analyze_waste(
                connection_id=parsed.connection_id,
                resources=resources,
                vm_cpu_metrics=vm_cpu_metrics,
            )
            waste_summary.connection_id = parsed.connection_id
            resp_dict = UdfResponse(
                status="success",
                data=waste_summary.model_dump(mode="json"),
            ).model_dump(mode="json")
            resp_dict["data_source"] = "onelake_delta"
            resp_dict["last_sync_at"] = envelope.data.snapshot_timestamp
            return resp_dict

    # 2. Local Fallback Path: SQLite or live Azure query
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
        empty_summary = WasteSummary(connection_id=parsed.connection_id)
        return UdfResponse(
            status="success",
            data=empty_summary.model_dump(mode="json"),
        ).model_dump(mode="json")

    # Collect CPU metrics for running VMs if token is available
    if token:
        running_vms = [
            r
            for r in resources
            if "microsoft.compute/virtualmachines" in r.resource_type.lower()
            and (r.power_state or "").lower() in ("running", "powerstate/running")
        ]
        for vm in running_vms[:10]:
            try:
                metrics_resp = await azure_client.query_monitor_metrics(
                    token=token,
                    resource_id=vm.resource_id,
                    metric_names=["Percentage CPU"],
                    time_grain="PT1H",
                    days=7,
                )
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

    waste_summary = waste_detector.analyze_waste(
        connection_id=parsed.connection_id,
        resources=resources,
        vm_cpu_metrics=vm_cpu_metrics,
    )
    waste_summary.connection_id = parsed.connection_id
    return UdfResponse(
        status="success",
        data=waste_summary.model_dump(mode="json"),
    ).model_dump(mode="json")
