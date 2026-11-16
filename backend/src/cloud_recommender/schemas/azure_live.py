"""Schemas for the live Azure connection demo (user-supplied service principal).

Every data domain is returned with an explicit access state so that "no permission",
"not available", "genuinely empty" and "error" are never confused, and so that every dataset
names the connection and subscription it was fetched with.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class DataAccessState(StrEnum):
    """Outcome of fetching one data domain."""

    ACCESSIBLE = "accessible"
    PERMISSION_DENIED = "permission_denied"
    UNAVAILABLE = "unavailable"
    EMPTY = "empty"
    ERROR = "error"


class ConnectAzureRequest(BaseModel):
    """Service principal credentials supplied by the signed-in user.

    The secret is a ``SecretStr`` (masked in repr/logs), is used once to obtain a token from
    Microsoft Entra ID and is never stored, logged or returned.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., description="Directory (tenant) ID of the service principal.")
    client_id: str = Field(..., description="Application (client) ID of the service principal.")
    client_secret: SecretStr = Field(..., description="Client secret value (never stored).")
    subscription_id: str | None = Field(
        default=None, description="Optional subscription to verify access to during connect."
    )


class AzureConnectionInfo(BaseModel):
    """Non-secret description of an active connection."""

    connection_id: str = Field(description="Opaque identifier of this connection session.")
    tenant_id: str
    client_id: str
    auth_method: str = Field(default="service_principal_client_secret")
    identity_source: str = Field(
        default="user_supplied_service_principal",
        description="Credentials come from the user, never from the server identity or CLI.",
    )
    connected_at: datetime
    expires_at: datetime = Field(description="When the Azure token (and session) expires.")


class DataSource(BaseModel):
    """Which connection and scope produced a dataset."""

    connection_id: str
    tenant_id: str
    client_id: str
    subscription_id: str | None = None
    api: str = Field(description="Azure API the data came from.")
    auth_method: str = "service_principal_client_secret"
    fetched_at: datetime


class DataDomain(BaseModel):
    """One data domain with explicit access state."""

    domain: str
    state: DataAccessState
    items: list[Any] | None = Field(
        default=None, description="Items when accessible/empty; null when not retrievable."
    )
    count: int | None = Field(default=None, description="Number of items; null when unknown.")
    message: str | None = Field(default=None, description="Human-readable explanation.")
    required_permission: str | None = Field(
        default=None, description="Azure role needed when permission was denied."
    )
    http_status: int | None = None
    azure_error_code: str | None = None
    retry_after_seconds: int | None = None
    truncated: bool = False
    source: DataSource


class ConnectResponse(BaseModel):
    connection: AzureConnectionInfo
    subscriptions: DataDomain
    requested_subscription: DataDomain | None = None


class ValidateResponse(BaseModel):
    valid: bool
    connection: AzureConnectionInfo
    subscriptions: DataDomain


class ResourceTypeCount(BaseModel):
    resource_type: str
    count: int


class ResourceListResponse(BaseModel):
    resources: DataDomain
    type_breakdown: list[ResourceTypeCount] = Field(default_factory=list)


class MetricValuesResponse(BaseModel):
    metrics: DataDomain


class CostSummary(BaseModel):
    """Actual cost for the period; ``total`` is null (never zero) when nothing was returned."""

    period: str
    period_start: str | None = None
    period_end: str | None = None
    currency: str | None = None
    total: float | None = None
    by_service: list[dict[str, Any]] = Field(default_factory=list)


class OverviewResponse(BaseModel):
    """Independent domains: a failure in one never hides another."""

    connection: AzureConnectionInfo
    subscription_id: str
    subscriptions: DataDomain
    resource_groups: DataDomain
    resources: DataDomain
    type_breakdown: list[ResourceTypeCount] = Field(default_factory=list)
    cost: DataDomain
