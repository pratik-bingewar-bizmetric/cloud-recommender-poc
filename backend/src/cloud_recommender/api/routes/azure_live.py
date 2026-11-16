"""Live Azure connection API (user-supplied service principal, stateless demo scope).

Flow: the signed-in user posts a service principal (tenant, client, secret); the backend obtains
an Azure token directly from Microsoft Entra ID, discards the secret, and returns an opaque
connection id. Every later call uses that connection's token, never the server's identity or an
Azure CLI session. Connections are visible only to the user that created them (404 otherwise).
"""

import re
from datetime import UTC, datetime
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from cloud_recommender.core.auth import AuthenticatedUser, get_current_user, owner_key_for
from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.azure_live import (
    AzureConnectionInfo,
    ConnectAzureRequest,
    ConnectResponse,
    DataDomain,
    MetricValuesResponse,
    OverviewResponse,
    ResourceListResponse,
    ValidateResponse,
)
from cloud_recommender.services.azure_live.credentials import (
    AzureCredentialError,
    acquire_service_principal_token,
)
from cloud_recommender.services.azure_live.data_service import COST_PERIODS, AzureLiveDataService
from cloud_recommender.services.azure_live.session_store import (
    AzureSession,
    AzureSessionStore,
    SlidingWindowLimiter,
    azure_session_store,
    connect_attempt_limiter,
)
from cloud_recommender.services.azure_live.validation import (
    require_guid,
    require_resource_id,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/azure/connections", tags=["Azure Live Connection"])

_RESOURCE_GROUP = re.compile(r"^[A-Za-z0-9._()\-]{1,90}$")
_METRIC_NAME = re.compile(r"^[A-Za-z0-9_./ ]{1,100}$")
_INTERVALS = {"PT1M", "PT5M", "PT15M", "PT30M", "PT1H", "PT6H", "PT12H", "P1D"}
_AGGREGATIONS = {"Average", "Minimum", "Maximum", "Total", "Count"}


def get_azure_http_transport() -> httpx.AsyncBaseTransport | None:
    """Transport override point (tests inject a mock; production uses the default)."""
    return None


def get_session_store(settings: Settings = Depends(get_settings)) -> AzureSessionStore:
    azure_session_store.configure(
        settings.azure_live_session_ttl_seconds, settings.azure_live_max_connections_per_user
    )
    return azure_session_store


def get_attempt_limiter(settings: Settings = Depends(get_settings)) -> SlidingWindowLimiter:
    connect_attempt_limiter.configure(settings.azure_live_connect_attempts_per_minute)
    return connect_attempt_limiter


def connection_info(session: AzureSession) -> AzureConnectionInfo:
    return AzureConnectionInfo(
        connection_id=session.connection_id,
        tenant_id=session.tenant_id,
        client_id=session.client_id,
        connected_at=datetime.fromtimestamp(session.created_at, UTC),
        expires_at=datetime.fromtimestamp(session.expires_at, UTC),
    )


def _owned_service(
    connection_id: str,
    user: AuthenticatedUser,
    settings: Settings,
    store: AzureSessionStore,
    transport: httpx.AsyncBaseTransport | None,
) -> AzureLiveDataService:
    session = store.get(connection_id, owner_key_for(user))  # 404 for foreign/unknown/expired
    return AzureLiveDataService(session, settings, transport)


def _group(value: str | None) -> str | None:
    if value is None:
        return None
    if not _RESOURCE_GROUP.match(value):
        raise HTTPException(
            status_code=422,
            detail={"error_code": "INVALID_IDENTIFIER", "message": "Invalid resource group name."},
        )
    return value


@router.post(
    "",
    response_model=ConnectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect an Azure service principal and discover accessible subscriptions",
)
async def connect_azure(
    payload: ConnectAzureRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
    limiter: Annotated[SlidingWindowLimiter, Depends(get_attempt_limiter)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
) -> ConnectResponse:
    """Validate the supplied credentials directly with Microsoft Entra ID.

    The secret is used once and discarded; only a short-lived token is kept in memory.
    """
    owner = owner_key_for(user)
    limiter.check(owner)
    tenant_id = require_guid(payload.tenant_id, "tenant_id")
    client_id = require_guid(payload.client_id, "client_id")
    requested_subscription = (
        require_guid(payload.subscription_id, "subscription_id")
        if payload.subscription_id
        else None
    )

    try:
        token = await acquire_service_principal_token(
            authority_url=settings.azure_authority_url,
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=payload.client_secret.get_secret_value(),
            timeout=float(settings.azure_live_request_timeout_seconds),
            transport=transport,
        )
    except AzureCredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY
            if exc.upstream
            else status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "ENTRA_UNAVAILABLE" if exc.upstream else "INVALID_AZURE_CREDENTIALS",
                "category": exc.category,
                "message": exc.message,
                "aadsts": exc.aadsts,
            },
        ) from None

    session = store.create(owner, tenant_id, client_id, token)
    service = AzureLiveDataService(session, settings, transport)
    subscriptions = await service.list_subscriptions()
    requested = (
        await service.verify_subscription(requested_subscription)
        if requested_subscription
        else None
    )
    logger.info(
        "azure_connection_established",
        connection_id=session.connection_id,
        tenant_id=tenant_id,
        client_id=client_id,
        subscriptions_state=subscriptions.state.value,
    )
    return ConnectResponse(
        connection=connection_info(session),
        subscriptions=subscriptions,
        requested_subscription=requested,
    )


@router.post(
    "/{connection_id}/validate",
    response_model=ValidateResponse,
    summary="Re-validate an active connection against Azure",
)
async def validate_azure_connection(
    connection_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
    limiter: Annotated[SlidingWindowLimiter, Depends(get_attempt_limiter)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
) -> ValidateResponse:
    service = _owned_service(connection_id, user, settings, store, transport)
    limiter.check(owner_key_for(user))
    subscriptions = await service.list_subscriptions()
    valid = subscriptions.state.value in ("accessible", "empty")
    return ValidateResponse(
        valid=valid, connection=connection_info(service.session), subscriptions=subscriptions
    )


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect: forget the connection token",
)
async def disconnect_azure(
    connection_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
) -> Response:
    store.delete(connection_id, owner_key_for(user))
    logger.info("azure_connection_closed", connection_id=connection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{connection_id}/subscriptions", response_model=DataDomain)
async def list_subscriptions(
    connection_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
) -> DataDomain:
    return await _owned_service(
        connection_id, user, settings, store, transport
    ).list_subscriptions()


@router.get(
    "/{connection_id}/subscriptions/{subscription_id}/resource-groups", response_model=DataDomain
)
async def list_resource_groups(
    connection_id: str,
    subscription_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
) -> DataDomain:
    sub = require_guid(subscription_id, "subscription_id")
    service = _owned_service(connection_id, user, settings, store, transport)
    return await service.list_resource_groups(sub)


@router.get(
    "/{connection_id}/subscriptions/{subscription_id}/resources",
    response_model=ResourceListResponse,
)
async def list_resources(
    connection_id: str,
    subscription_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
    resource_group: Annotated[str | None, Query()] = None,
) -> ResourceListResponse:
    sub = require_guid(subscription_id, "subscription_id")
    service = _owned_service(connection_id, user, settings, store, transport)
    domain, breakdown = await service.list_resources(sub, _group(resource_group))
    return ResourceListResponse(resources=domain, type_breakdown=breakdown)


@router.get("/{connection_id}/subscriptions/{subscription_id}/resource", response_model=DataDomain)
async def get_resource_detail(
    connection_id: str,
    subscription_id: str,
    resource_id: Annotated[str, Query()],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
) -> DataDomain:
    sub = require_guid(subscription_id, "subscription_id")
    rid = require_resource_id(resource_id, sub)
    service = _owned_service(connection_id, user, settings, store, transport)
    return await service.get_resource(sub, rid)


@router.get(
    "/{connection_id}/subscriptions/{subscription_id}/metrics/definitions",
    response_model=DataDomain,
)
async def get_metric_definitions(
    connection_id: str,
    subscription_id: str,
    resource_id: Annotated[str, Query()],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
) -> DataDomain:
    sub = require_guid(subscription_id, "subscription_id")
    rid = require_resource_id(resource_id, sub)
    service = _owned_service(connection_id, user, settings, store, transport)
    return await service.metric_definitions(sub, rid)


@router.get(
    "/{connection_id}/subscriptions/{subscription_id}/metrics", response_model=MetricValuesResponse
)
async def get_metric_values(
    connection_id: str,
    subscription_id: str,
    resource_id: Annotated[str, Query()],
    metric_names: Annotated[str, Query(description="Comma separated metric names (max 20).")],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
    interval: Annotated[str, Query()] = "PT1H",
    aggregation: Annotated[str, Query()] = "Average",
) -> MetricValuesResponse:
    sub = require_guid(subscription_id, "subscription_id")
    rid = require_resource_id(resource_id, sub)
    names = [n.strip() for n in metric_names.split(",") if n.strip()]
    if not names or len(names) > 20 or any(not _METRIC_NAME.match(n) for n in names):
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_METRIC_NAMES",
                "message": "Provide 1-20 valid metric names.",
            },
        )
    if interval not in _INTERVALS or aggregation not in _AGGREGATIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_METRIC_QUERY",
                "message": "Unsupported interval or aggregation.",
            },
        )
    service = _owned_service(connection_id, user, settings, store, transport)
    domain = await service.metric_values(sub, rid, names, hours, interval, aggregation)
    return MetricValuesResponse(metrics=domain)


@router.get("/{connection_id}/subscriptions/{subscription_id}/cost", response_model=DataDomain)
async def get_cost(
    connection_id: str,
    subscription_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
    period: Annotated[str, Query()] = "month_to_date",
) -> DataDomain:
    sub = require_guid(subscription_id, "subscription_id")
    if period not in COST_PERIODS:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_PERIOD",
                "message": f"period must be one of {sorted(COST_PERIODS)}.",
            },
        )
    service = _owned_service(connection_id, user, settings, store, transport)
    return await service.cost(sub, period)


@router.get(
    "/{connection_id}/subscriptions/{subscription_id}/overview", response_model=OverviewResponse
)
async def get_overview(
    connection_id: str,
    subscription_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[AzureSessionStore, Depends(get_session_store)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
) -> OverviewResponse:
    """All dashboard domains for one subscription; each carries its own access state."""
    sub = require_guid(subscription_id, "subscription_id")
    service = _owned_service(connection_id, user, settings, store, transport)
    return await service.overview(connection_info, sub)
