"""Pydantic schemas for Service Principal-Only authentication and application sessions."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, SecretStr, field_validator

GUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _validate_guid(v: str, field_name: str) -> str:
    cleaned = v.strip()
    if not GUID_PATTERN.match(cleaned):
        raise ValueError(f"{field_name} must be a valid GUID (UUID).")
    return cleaned.lower()


class ServicePrincipalConnectRequest(BaseModel):
    """Payload for authenticating and starting a session via Azure Service Principal."""

    account_name: str = Field(
        default="Azure Production",
        min_length=1,
        max_length=120,
        description="User-friendly name for this cloud account connection",
    )
    subscription_id: str = Field(
        description="Azure subscription GUID",
        examples=["00000000-0000-0000-0000-000000000000"],
    )
    tenant_id: str = Field(
        description="Microsoft Entra tenant GUID",
        examples=["00000000-0000-0000-0000-000000000000"],
    )
    client_id: str = Field(
        description="Azure application / client GUID",
        examples=["00000000-0000-0000-0000-000000000000"],
    )
    client_secret: SecretStr = Field(
        description="Azure Service Principal client secret",
        examples=["secret-value-never-logged"],
    )

    @field_validator("subscription_id")
    @classmethod
    def validate_subscription_id(cls, v: str) -> str:
        return _validate_guid(v, "subscription_id")

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        return _validate_guid(v, "tenant_id")

    @field_validator("client_id")
    @classmethod
    def validate_client_id(cls, v: str) -> str:
        return _validate_guid(v, "client_id")

    @field_validator("client_secret")
    @classmethod
    def validate_client_secret(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("client_secret must not be empty.")
        return v


class ServicePrincipalConnectResponse(BaseModel):
    """Response returned upon successful Service Principal authentication."""

    session_token: str = Field(
        description="Bearer token for authenticating subsequent FinOps API requests",
    )
    session_id: str = Field(description="Unique application session identifier")
    account_id: str = Field(description="Internal account identifier")
    account_name: str = Field(description="User-friendly account name")
    connection_id: str = Field(description="Live Azure connection identifier")
    tenant_id: str = Field(description="Microsoft Entra tenant GUID")
    subscription_id: str = Field(description="Azure subscription GUID")
    subscription_name: str = Field(description="Azure subscription display name")
    roles: list[str] = Field(
        default_factory=lambda: ["FinOpsAdmin"],
        description="Granted platform roles",
    )
    permissions: dict[str, bool] = Field(
        description="Verified Azure RBAC permissions (Reader, Cost Management Reader, Monitoring Reader)"
    )
    created_at: datetime = Field(description="Session creation timestamp (UTC)")
    expires_at: datetime = Field(description="Session expiration timestamp (UTC)")


class SessionInfoResponse(BaseModel):
    """Active session status and metadata."""

    session_id: str = Field(description="Unique application session identifier")
    account_id: str = Field(description="Internal account identifier")
    account_name: str = Field(description="User-friendly account name")
    connection_id: str = Field(description="Live Azure connection identifier")
    tenant_id: str = Field(description="Microsoft Entra tenant GUID")
    subscription_id: str = Field(description="Azure subscription GUID")
    subscription_name: str = Field(description="Azure subscription display name")
    roles: list[str] = Field(description="Granted platform roles")
    permissions: dict[str, bool] = Field(description="Verified Azure RBAC permissions")
    created_at: datetime = Field(description="Session creation timestamp (UTC)")
    expires_at: datetime = Field(description="Session expiration timestamp (UTC)")
    last_used_at: datetime = Field(description="Timestamp of last API call (UTC)")


class LogoutResponse(BaseModel):
    """Outcome of session termination."""

    status: str = Field(default="logged_out", description="Session revocation status")
    message: str = Field(
        default="Application session terminated successfully.",
        description="Human-readable outcome",
    )
