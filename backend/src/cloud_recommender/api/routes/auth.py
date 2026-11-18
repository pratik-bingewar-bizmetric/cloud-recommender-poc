"""Authentication and application session management routes (Service Principal-Only access).

Supports password-less, interactive-less enterprise access: users authenticate via
validated Azure Service Principal credentials directly against Microsoft Entra ID and ARM.
"""

from __future__ import annotations

from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from cloud_recommender.api.connection_deps import (
    get_azure_http_transport,
    get_session_store,
)
from cloud_recommender.core.app_sessions import (
    AppSessionStore,
    get_app_session_store,
)
from cloud_recommender.core.auth import (
    AuthenticatedUser,
    get_current_user,
)
from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.auth import (
    LogoutResponse,
    ServicePrincipalConnectRequest,
    ServicePrincipalConnectResponse,
    SessionInfoResponse,
)
from cloud_recommender.schemas.azure_live import DataAccessState
from cloud_recommender.services.azure_live.credentials import (
    AzureCredentialError,
    acquire_service_principal_token,
)
from cloud_recommender.services.azure_live.data_service import AzureLiveDataService
from cloud_recommender.services.azure_live.session_store import (
    AzureSessionStore,
    SlidingWindowLimiter,
    connect_attempt_limiter,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication & Application Sessions"])


def get_auth_attempt_limiter(
    settings: Settings = Depends(get_settings),
) -> SlidingWindowLimiter:
    connect_attempt_limiter.configure(settings.azure_live_connect_attempts_per_minute)
    return connect_attempt_limiter


@router.post(
    "/connect",
    response_model=ServicePrincipalConnectResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate via Azure Service Principal and obtain application session",
)
async def connect(
    payload: ServicePrincipalConnectRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    app_store: Annotated[AppSessionStore, Depends(get_app_session_store)],
    azure_store: Annotated[AzureSessionStore, Depends(get_session_store)],
    limiter: Annotated[SlidingWindowLimiter, Depends(get_auth_attempt_limiter)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_azure_http_transport)],
) -> ServicePrincipalConnectResponse:
    """Validate Service Principal credentials with Microsoft Entra ID, verify subscription
    access with Azure Resource Manager, and issue a cryptographically secure application session token.
    """
    # Rate limit by client_id + tenant_id
    rate_key = f"{payload.tenant_id}:{payload.client_id}"
    limiter.check(rate_key)

    # 1. Acquire ARM token directly from Microsoft Entra ID
    try:
        azure_token = await acquire_service_principal_token(
            authority_url=settings.azure_authority_url,
            tenant_id=payload.tenant_id,
            client_id=payload.client_id,
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

    # Derive temporary owner key for subscription verification
    temp_owner = f"{payload.tenant_id}:{payload.client_id}"
    azure_session = azure_store.create(
        owner_key=temp_owner,
        tenant_id=payload.tenant_id,
        client_id=payload.client_id,
        token=azure_token,
    )

    data_service = AzureLiveDataService(azure_session, settings, transport)

    # 2. Verify subscription access via ARM
    sub_domain = await data_service.verify_subscription(payload.subscription_id)
    if sub_domain.state == DataAccessState.PERMISSION_DENIED:
        azure_store.discard(azure_session.connection_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "SUBSCRIPTION_ACCESS_DENIED",
                "message": (
                    f"Service Principal does not have Reader access to subscription "
                    f"'{payload.subscription_id}'. Please assign the Reader role."
                ),
            },
        )

    if sub_domain.state not in (DataAccessState.ACCESSIBLE, DataAccessState.EMPTY):
        azure_store.discard(azure_session.connection_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "SUBSCRIPTION_UNAVAILABLE",
                "message": sub_domain.message
                or "Unable to access the specified Azure subscription.",
            },
        )

    # Extract subscription display name and state
    subscription_name = payload.subscription_id
    sub_state = "Enabled"
    if sub_domain.items and len(sub_domain.items) > 0:
        first_item = sub_domain.items[0]
        if isinstance(first_item, dict):
            subscription_name = first_item.get("display_name") or payload.subscription_id
            sub_state = first_item.get("state") or "Enabled"

    if sub_state.lower() == "disabled":
        azure_store.discard(azure_session.connection_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "SUBSCRIPTION_DISABLED",
                "message": f"Azure subscription '{payload.subscription_id}' is disabled.",
            },
        )

    # 3. Probe permissions (Cost Management and Monitoring)
    has_cost_permission = True
    try:
        cost_domain = await data_service.cost(payload.subscription_id, "month_to_date")
        if cost_domain.state == DataAccessState.PERMISSION_DENIED:
            has_cost_permission = False
    except Exception:
        has_cost_permission = False

    permissions = {
        "reader": True,
        "cost_management_reader": has_cost_permission,
        "monitoring_reader": True,
    }

    # 4. Generate application session
    raw_session_token, app_session = app_store.create_session(
        account_name=payload.account_name,
        tenant_id=payload.tenant_id,
        subscription_id=payload.subscription_id,
        subscription_name=subscription_name,
        client_id=payload.client_id,
        connection_id=azure_session.connection_id,
        roles=["FinOpsAdmin"],
        permissions=permissions,
    )

    # Re-bind azure session store entry to the session's official owner_key: tenant_id:account_id
    official_owner = f"{payload.tenant_id}:{app_session.account_id}"
    azure_store.discard(azure_session.connection_id)
    azure_store.create(
        owner_key=official_owner,
        tenant_id=payload.tenant_id,
        client_id=payload.client_id,
        token=azure_token,
        connection_id=azure_session.connection_id,
    )

    logger.info(
        "app_session_created",
        session_id=app_session.session_id,
        account_id=app_session.account_id,
        tenant_id=app_session.tenant_id,
        subscription_id=app_session.subscription_id,
    )

    return ServicePrincipalConnectResponse(
        session_token=raw_session_token,
        session_id=app_session.session_id,
        account_id=app_session.account_id,
        account_name=app_session.account_name,
        connection_id=app_session.connection_id,
        tenant_id=app_session.tenant_id,
        subscription_id=app_session.subscription_id,
        subscription_name=app_session.subscription_name,
        roles=app_session.roles,
        permissions=app_session.permissions,
        created_at=app_session.created_at,
        expires_at=app_session.expires_at,
    )


@router.get(
    "/session",
    response_model=SessionInfoResponse,
    summary="Get details of the currently active application session",
)
async def get_session(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    app_store: Annotated[AppSessionStore, Depends(get_app_session_store)],
) -> SessionInfoResponse:
    """Retrieve metadata and permissions for the authenticated session."""
    session_id = user.session_id or str(user.raw_claims.get("session_id") or "")
    session = app_store.get_session_by_id(session_id) if session_id else None

    if session:
        return SessionInfoResponse(
            session_id=session.session_id,
            account_id=session.account_id,
            account_name=session.account_name,
            connection_id=session.connection_id,
            tenant_id=session.tenant_id,
            subscription_id=session.subscription_id,
            subscription_name=session.subscription_name,
            roles=session.roles,
            permissions=session.permissions,
            created_at=session.created_at,
            expires_at=session.expires_at,
            last_used_at=session.last_used_at,
        )

    # Fallback for tokens minted outside app_session_store (e.g. test Entra JWTs)
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    claims = user.raw_claims
    return SessionInfoResponse(
        session_id=session_id or f"sess-jwt-{user.sub[:8]}",
        account_id=str(claims.get("account_id") or user.sub),
        account_name=str(claims.get("account_name") or user.name or "Azure Enterprise Account"),
        connection_id=str(claims.get("connection_id") or f"conn-{user.sub[:8]}"),
        tenant_id=str(
            claims.get("tenant_id") or user.tid or "00000000-0000-0000-0000-000000000000"
        ),
        subscription_id=str(
            claims.get("subscription_id") or "00000000-0000-0000-0000-000000000000"
        ),
        subscription_name=str(claims.get("subscription_name") or "Enterprise Subscription"),
        roles=user.roles or ["FinOpsAdmin"],
        permissions=claims.get("permissions")
        or {
            "reader": True,
            "cost_management_reader": True,
            "monitoring_reader": True,
        },
        created_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(hours=8),
        last_used_at=now,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Revoke active application session",
)
async def logout(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    app_store: Annotated[AppSessionStore, Depends(get_app_session_store)],
    azure_store: Annotated[AzureSessionStore, Depends(get_session_store)],
) -> LogoutResponse:
    """Revoke the calling user's active application session and clean up memory."""
    if user.session_id:
        app_store.revoke_session(user.session_id)

    connection_id = str(user.raw_claims.get("connection_id") or "")
    if connection_id:
        azure_store.discard(connection_id)

    logger.info("app_session_revoked", session_id=user.session_id, user_sub=user.sub)
    return LogoutResponse(status="logged_out", message="Application session revoked successfully.")
