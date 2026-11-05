"""Inventory discovery RPC handlers for Microsoft Fabric UDF."""

from typing import Any
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
) -> dict[str, Any]:
    """Retrieve discovered resources for a connection from live Azure Resource Graph or Lakehouse snapshot."""
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
            # Persist live snapshot in Lakehouse
            store.save_inventory(parsed.connection_id, resources)
        except (RuntimeError, urllib.error.URLError, OSError) as arg_exc:
            # Fall back to direct ARM resources list API
            try:
                resources = await azure_client.query_arm_resources_direct(
                    token=token,
                    subscription_id=conn.scope_id,
                )
                store.save_inventory(parsed.connection_id, resources)
            except Exception:
                # Fall back to persisted Lakehouse snapshot if live ARM/ARG calls failed
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
        # Load persisted Lakehouse snapshot
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
