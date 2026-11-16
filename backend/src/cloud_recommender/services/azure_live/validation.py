"""Strict input validation for identifiers that are placed into Azure URLs."""

import re

from fastapi import HTTPException

_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_RESOURCE_ID = re.compile(
    r"^/subscriptions/(?P<sub>[0-9a-fA-F-]{36})/resourceGroups/[A-Za-z0-9._()\-]{1,90}"
    r"(?:/providers/[A-Za-z0-9._\-]+(?:/[A-Za-z0-9._()\-~ ]+)+)?$"
)
MAX_RESOURCE_ID_LENGTH = 1500


def is_guid(value: str | None) -> bool:
    return bool(value and _GUID.match(value.strip()))


def require_guid(value: str, field: str) -> str:
    """Return the stripped GUID or raise 422 (prevents path/URL injection into Azure calls)."""
    if not is_guid(value):
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_IDENTIFIER",
                "message": f"{field} must be a GUID.",
            },
        )
    return value.strip()


def require_resource_id(resource_id: str, subscription_id: str) -> str:
    """Validate an ARM resource ID belonging to ``subscription_id`` (no traversal, no query)."""
    candidate = resource_id.strip()
    match = _RESOURCE_ID.match(candidate)
    if (
        not match
        or len(candidate) > MAX_RESOURCE_ID_LENGTH
        or ".." in candidate
        or match.group("sub").lower() != subscription_id.lower()
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_RESOURCE_ID",
                "message": "resource_id must be an Azure resource ID within the selected subscription.",
            },
        )
    return candidate
