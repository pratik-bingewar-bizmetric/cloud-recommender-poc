"""Service-principal token acquisition directly from Microsoft Entra ID.

OAuth2 client-credentials grant against the tenant's token endpoint. Deliberately NOT built on
the Azure CLI, ``DefaultAzureCredential`` or any ambient/server identity: the only identity
that can be used is the one whose tenant, client ID and secret the caller supplies.
"""

import re
import time
from dataclasses import dataclass, field

import httpx
import structlog

logger = structlog.get_logger(__name__)

ARM_SCOPE = "https://management.azure.com/.default"
_AADSTS = re.compile(r"AADSTS(\d{4,7})")

# AADSTS code -> (error category, safe user message). Descriptions from Entra are never echoed.
_CATEGORIES: dict[str, tuple[str, str]] = {
    "7000215": ("invalid_client_secret", "The client secret is incorrect."),
    "7000222": ("expired_client_secret", "The client secret has expired."),
    "700016": (
        "application_not_found",
        "No application with this client ID exists in the tenant.",
    ),
    "90002": ("tenant_not_found", "The tenant was not found."),
    "900023": ("tenant_not_found", "The tenant identifier is invalid."),
    "700027": ("invalid_client_credentials", "The client credentials were rejected."),
    "7000112": ("application_disabled", "The application is disabled in the tenant."),
    "500011": ("resource_principal_not_found", "The Azure Resource Manager API is not available."),
}


class AzureCredentialError(Exception):
    """Credential validation failed. ``str(error)`` is safe to show to the user."""

    def __init__(
        self, category: str, message: str, *, upstream: bool = False, aadsts: str | None = None
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.upstream = upstream  # True when Entra could not be reached (502 rather than 400)
        self.aadsts = aadsts


@dataclass(frozen=True)
class AzureToken:
    """Short-lived ARM access token. Never printed: ``repr`` hides the value."""

    value: str = field(repr=False)
    expires_at: float  # epoch seconds


async def acquire_service_principal_token(
    *,
    authority_url: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    timeout: float = 15.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AzureToken:
    """Exchange the service principal credentials for an ARM token (client credentials).

    ``tenant_id`` and ``client_id`` must already be validated GUIDs. The secret is sent only in
    the form body to Microsoft Entra ID and is not retained by this function.
    """
    url = f"{authority_url.rstrip('/')}/{tenant_id}/oauth2/v2.0/token"
    form = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": ARM_SCOPE,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            response = await client.post(url, data=form)
    except httpx.HTTPError as exc:
        # Log the exception *type* only: messages may embed request details.
        logger.warning("entra_token_request_failed", error_type=type(exc).__name__)
        raise AzureCredentialError(
            "entra_unreachable",
            "Microsoft Entra ID could not be reached. Try again shortly.",
            upstream=True,
        ) from None

    if response.status_code == 200:
        try:
            payload = response.json()
            token = str(payload["access_token"])
            lifetime = int(payload.get("expires_in", 3600))
        except (ValueError, KeyError, TypeError):
            raise AzureCredentialError(
                "invalid_token_response",
                "Microsoft Entra ID returned an unexpected response.",
                upstream=True,
            ) from None
        return AzureToken(value=token, expires_at=time.time() + max(lifetime, 60))

    if response.status_code >= 500 or response.status_code == 429:
        raise AzureCredentialError(
            "entra_unavailable",
            "Microsoft Entra ID is temporarily unavailable. Try again shortly.",
            upstream=True,
        )

    aadsts: str | None = None
    try:
        body = response.json()
        description = str(body.get("error_description", ""))
        found = _AADSTS.search(description)
        aadsts = found.group(1) if found else None
    except ValueError:
        pass
    category, message = _CATEGORIES.get(
        aadsts or "",
        (
            "invalid_credentials",
            "The service principal credentials were rejected by Microsoft Entra ID.",
        ),
    )
    logger.info("entra_token_request_rejected", category=category, aadsts=aadsts)
    raise AzureCredentialError(category, message, aadsts=f"AADSTS{aadsts}" if aadsts else None)
