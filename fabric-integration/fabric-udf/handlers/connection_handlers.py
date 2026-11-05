"""Connection management RPC handlers for Microsoft Fabric UDF."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from schemas.models import (
    CloudConnection,
    CreateConnectionArgs,
    ListConnectionsArgs,
    UdfResponse,
    ValidateConnectionArgs,
)
from services.azure_real_client import AzureRealClient
from services.lakehouse_store import FabricLakehouseStore


async def handle_list_connections(
    store: FabricLakehouseStore,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """List all registered cloud connections from Lakehouse persistent store."""
    parsed = ListConnectionsArgs(**(args or {}))
    connections = store.list_connections(provider_filter=parsed.provider_filter)
    resp = UdfResponse(
        status="success",
        data=[c.model_dump(mode="json") for c in connections],
    )
    return resp.model_dump(mode="json")


async def handle_create_connection(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Register and validate a new cloud provider connection with real server-side verification."""
    try:
        parsed = CreateConnectionArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    if parsed.provider != "azure":
        return UdfResponse(
            status="error",
            error_code="PROVIDER_NOT_SUPPORTED",
            error_message=f"Provider '{parsed.provider}' is deferred for this Fabric POC. Please select Azure.",
        ).model_dump(mode="json")

    # Real authentication and RBAC validation check
    val_result = await azure_client.validate_arm_connection(
        tenant_id=parsed.tenant_id,
        client_id=parsed.client_id,
        client_secret=parsed.client_secret,
        subscription_id=parsed.subscription_id,
    )

    if not val_result.get("valid"):
        return UdfResponse(
            status="error",
            error_code=val_result.get("error_code", "AUTHENTICATION_FAILED"),
            error_message=val_result.get("error_message", (
                f"Failed to authenticate against Microsoft Entra tenant {parsed.tenant_id}. "
                "Verify Client ID, Client Secret, and required role assignments (Reader, Cost Management Reader)."
            )),
        ).model_dump(mode="json")

    conn_id = f"{parsed.provider}-{parsed.subscription_id[:8]}-{uuid.uuid4().hex[:4]}"
    display_name = parsed.name
    if not display_name or display_name.strip() == "":
        display_name = val_result.get("subscription_name") or f"Azure Subscription {parsed.subscription_id[:8]}"

    verified_caps = ["inventory", "waste_detection", "metrics", "token_economics"]
    if val_result.get("roles", {}).get("cost_management_reader"):
        verified_caps.append("cost_management")

    connection = CloudConnection(
        id=conn_id,
        name=display_name,
        provider=parsed.provider,
        scope_id=parsed.subscription_id,
        tenant_or_org_id=parsed.tenant_id,
        client_id=parsed.client_id,
        auth_method=val_result.get("auth_method", "service_principal"),
        status="connected",
        last_verified_at=datetime.now(UTC),
        is_live=True,
        capabilities=verified_caps,
    )

    store.save_connection(connection, secret=parsed.client_secret)
    return UdfResponse(
        status="success",
        data=connection.model_dump(mode="json"),
    ).model_dump(mode="json")


async def handle_validate_connection(
    store: FabricLakehouseStore,
    azure_client: AzureRealClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Test connectivity and permissions for an existing or newly submitted connection."""
    try:
        parsed = ValidateConnectionArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    if parsed.provider != "azure":
        return UdfResponse(
            status="error",
            error_code="PROVIDER_NOT_SUPPORTED",
            error_message=f"Provider '{parsed.provider}' is deferred for this Fabric POC. Please select Azure.",
        ).model_dump(mode="json")

    tenant_id = parsed.tenant_id
    sub_id = parsed.subscription_id
    secret = parsed.client_secret
    client_id = parsed.client_id

    if parsed.connection_id:
        existing = store.get_connection(parsed.connection_id)
        if not existing:
            return UdfResponse(
                status="error",
                error_code="CONNECTION_NOT_FOUND",
                error_message=f"Connection '{parsed.connection_id}' does not exist.",
            ).model_dump(mode="json")
        tenant_id = tenant_id or existing.tenant_or_org_id
        sub_id = sub_id or existing.scope_id
        client_id = client_id or existing.client_id
        secret = secret or store.get_connection_secret(parsed.connection_id)

    val_result = await azure_client.validate_arm_connection(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=secret,
        subscription_id=sub_id,
    )

    if not val_result.get("valid"):
        return UdfResponse(
            status="error",
            error_code=val_result.get("error_code", "AUTHENTICATION_FAILED"),
            error_message=val_result.get(
                "error_message",
                "Authentication check failed. Could not acquire Azure Resource Manager token.",
            ),
        ).model_dump(mode="json")

    return UdfResponse(
        status="success",
        data=val_result,
    ).model_dump(mode="json")


async def handle_delete_connection(
    store: FabricLakehouseStore,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Delete a connection and cascading records from Lakehouse storage."""
    conn_id = args.get("connection_id")
    if not conn_id:
        return UdfResponse(
            status="error",
            error_code="MISSING_CONNECTION_ID",
            error_message="connection_id parameter is required.",
        ).model_dump(mode="json")

    deleted = store.delete_connection(conn_id)
    if not deleted:
        return UdfResponse(
            status="error",
            error_code="CONNECTION_NOT_FOUND",
            error_message=f"Connection '{conn_id}' was not found.",
        ).model_dump(mode="json")

    return UdfResponse(
        status="success",
        data={"deleted": True, "connection_id": conn_id},
    ).model_dump(mode="json")
