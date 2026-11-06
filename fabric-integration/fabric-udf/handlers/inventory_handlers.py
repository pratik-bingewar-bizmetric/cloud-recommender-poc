"""Inventory discovery RPC handlers for Microsoft Fabric UDF."""

import os
from typing import Any, Optional
import urllib.error

from pydantic import ValidationError
from schemas.models import (
    DiscoveredResource,
    GetInventoryArgs,
    UdfResponse,
)
from services.azure_real_client import AzureRealClient
from services.lakehouse_store import FabricLakehouseStore


async def handle_get_inventory(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    args: dict[str, Any],
    analytical_repo: Optional[Any] = None,
) -> dict[str, Any]:
    """Retrieve discovered resources from OneLake Delta Lake or live Azure Resource Graph/SQLite."""
    try:
        parsed = GetInventoryArgs(**args)
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

    # 1. Primary Path: OneLake Delta Analytical Storage (when configured)
    analytics_source = os.getenv("FINOPS_ANALYTICS_SOURCE", "onelake").lower()
    if analytical_repo and analytics_source == "onelake":
        envelope = analytical_repo.get_inventory_summary(
            connection_id=parsed.connection_id,
            subscription_id=conn.scope_id if conn else None,
            resource_type_filter=parsed.resource_type_filter,
        )
        if envelope.status == "success" and envelope.data and envelope.data.resources:
            discovered = [
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
            resp_dict = UdfResponse(
                status="success",
                data=[r.model_dump(mode="json") for r in discovered],
            ).model_dump(mode="json")
            resp_dict["data_source"] = "onelake_delta"
            resp_dict["last_sync_at"] = envelope.data.snapshot_timestamp
            resp_dict["records_count"] = envelope.data.total_resources
            return resp_dict
        elif envelope.status == "error":
            # In strict onelake mode, report honest Lakehouse error without falling back to stale local data
            return UdfResponse(
                status="error",
                error_code=envelope.error_code or "LAKEHOUSE_READ_ERROR",
                error_message=f"Failed reading inventory from OneLake Delta Lake: {envelope.error_message}",
            ).model_dump(mode="json")

    # 2. Local / Development Fallback Path: Live Azure Resource Graph or SQLite snapshot
    secret = store.get_connection_secret(parsed.connection_id)
    token, _ = await azure_client.get_access_token(
        tenant_id=conn.tenant_or_org_id,
        client_id=conn.client_id,
        client_secret=secret,
    )

    resources: list[DiscoveredResource] = []
    if token:
        try:
            resources = await azure_client.query_resource_graph(
                token=token,
                subscription_id=conn.scope_id,
            )
            store.save_inventory(parsed.connection_id, resources)
        except (RuntimeError, urllib.error.URLError, OSError) as arg_exc:
            try:
                resources = await azure_client.query_arm_resources_direct(
                    token=token,
                    subscription_id=conn.scope_id,
                )
                store.save_inventory(parsed.connection_id, resources)
            except Exception:
                resources = store.get_inventory(
                    parsed.connection_id,
                    resource_type_filter=parsed.resource_type_filter,
                )
                if not resources:
                    return UdfResponse(
                        status="error",
                        error_code="LIVE_QUERY_FAILED",
                        error_message=f"Failed to query Azure Resource Graph/ARM and no snapshot exists: {arg_exc}",
                    ).model_dump(mode="json")
    else:
        resources = store.get_inventory(
            parsed.connection_id,
            resource_type_filter=parsed.resource_type_filter,
        )
        if not resources:
            return UdfResponse(
                status="error",
                error_code="UNAUTHENTICATED",
                error_message="Could not authenticate with Azure and no persisted inventory exists.",
            ).model_dump(mode="json")

    if parsed.resource_type_filter:
        resources = [
            r
            for r in resources
            if parsed.resource_type_filter.lower() in r.resource_type.lower()
        ]

    return UdfResponse(
        status="success",
        data=[r.model_dump(mode="json") for r in resources],
    ).model_dump(mode="json")
