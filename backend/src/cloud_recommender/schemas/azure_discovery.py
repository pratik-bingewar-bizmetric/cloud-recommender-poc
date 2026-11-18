"""Schemas for read-only Azure Resource Group and resource inventory discovery (M2.5)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AzureDiscoveryStatus(StrEnum):
    """Outcome of one ARM discovery call. EMPTY (authorized, nothing found) is not a failure."""

    OK = "OK"
    EMPTY = "EMPTY"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"


class AzureDiscoveryMeta(BaseModel):
    """Provenance shared by every discovery response."""

    subscription_id: str = Field(description="Subscription the call targeted.")
    subscription_state: str | None = Field(
        default=None, description="ARM subscription state (Enabled, Disabled, Warned, ...)."
    )
    status: AzureDiscoveryStatus = Field(description="Result of the ARM call.")
    status_message: str = Field(
        description="Human-readable explanation, including the missing role."
    )
    http_status: int | None = Field(default=None, description="HTTP status of the last ARM call.")
    page_count: int = Field(default=0, description="Number of ARM pages retrieved.")
    auth_method: str = Field(default="none", description="Identity type used (never a secret).")
    retrieved_at: datetime | None = Field(default=None, description="When this call completed.")
    last_success_at: datetime | None = Field(
        default=None, description="Last time this inventory was retrieved successfully."
    )
    stale: bool = Field(
        default=False,
        description="True when the call failed and the last successful inventory is returned.",
    )


class AzureResourceGroupItem(BaseModel):
    id: str
    name: str
    subscription_id: str
    location: str | None = None
    provisioning_state: str | None = None
    managed_by: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class AzureResourceGroupsResponse(AzureDiscoveryMeta):
    count: int | None = Field(default=None, description="None when the count is unknown.")
    items: list[AzureResourceGroupItem] = Field(default_factory=list)


class AzureResourceItem(BaseModel):
    id: str
    name: str
    type: str
    subscription_id: str
    resource_group: str | None = None
    location: str | None = None
    kind: str | None = None
    sku: dict[str, Any] | None = None
    provisioning_state: str | None = None
    created_time: str | None = None
    changed_time: str | None = None
    managed_by: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class AzureResourcesResponse(AzureDiscoveryMeta):
    resource_group: str | None = None
    count: int | None = Field(default=None, description="None when the count is unknown.")
    items: list[AzureResourceItem] = Field(default_factory=list)
