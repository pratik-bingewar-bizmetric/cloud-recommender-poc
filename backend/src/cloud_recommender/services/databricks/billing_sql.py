"""Validated query construction and helpers for Databricks billing system tables (M7.1).

Everything here is pure: no SQL is executed and no network call is made.

Responsibilities
----------------
* D8  - strict validation of every value interpolated into SQL text (workspace id, dates,
        row limit) so request fields can never inject SQL.
* D11 - fixed, minimal column projections. ``identity_metadata`` and free-text names
        (notebook paths, run/job names, user identifiers) are never selected.
* D5  - exact resource attribution over the full set of ``usage_metadata`` ID keys.
* D3  - lossless ``Decimal`` parsing of source numerics (``decimal(38,18)``).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

_WORKSPACE_ID_RE = re.compile(r"^[0-9]{1,20}$")
MAX_ROW_LIMIT = 50_000
# The rate card is fetched in full with one fixed bound (independent of the usage row
# limit). A result that reaches this bound is reported as INCOMPLETE, never as success.
PRICE_ROW_LIMIT = MAX_ROW_LIMIT


class CostBasis(StrEnum):
    """What a monetary figure (or the absence of one) actually represents."""

    METERED_USAGE = "METERED_USAGE"
    """Quantity only (e.g. DBU). No money has been derived."""

    LIST_PRICE_ESTIMATE = "LIST_PRICE_ESTIMATE"
    """metered quantity x published ``system.billing.list_prices``. An estimate, not an invoice."""

    AZURE_INVOICED = "AZURE_INVOICED"
    """Amount invoiced by Azure. Reserved: nothing in this module produces it."""


class MatchStatus(StrEnum):
    """Outcome of joining a usage record to the ingested rate card."""

    MATCHED = "MATCHED"
    NO_PRICE = "NO_PRICE"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    AMBIGUOUS = "AMBIGUOUS"
    MIXED_CURRENCY = "MIXED_CURRENCY"
    """Priced rows in scope use more than one currency; costs are withheld, never merged."""


class BillingQueryValidationError(ValueError):
    """Raised when a value destined for SQL text fails strict validation."""


def validate_workspace_id(value: Any) -> str:
    """Return ``value`` if it is a numeric Databricks workspace id, else raise."""
    text = str(value).strip() if value is not None else ""
    if not _WORKSPACE_ID_RE.fullmatch(text):
        raise BillingQueryValidationError("workspace_id must contain only digits (1-20).")
    return text


def validate_iso_date(value: Any, field: str = "date") -> str:
    """Return ``value`` as a canonical ``YYYY-MM-DD`` string, else raise."""
    text = str(value).strip() if value is not None else ""
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        raise BillingQueryValidationError(f"{field} must be an ISO date (YYYY-MM-DD).")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise BillingQueryValidationError(f"{field} is not a valid calendar date.") from exc


def validate_limit(value: Any) -> int:
    """Return a bounded positive integer row limit, else raise."""
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise BillingQueryValidationError("limit must be an integer.")
    try:
        number = int(value)
    except ValueError as exc:
        raise BillingQueryValidationError("limit must be an integer.") from exc
    if not 1 <= number <= MAX_ROW_LIMIT:
        raise BillingQueryValidationError(f"limit must be between 1 and {MAX_ROW_LIMIT}.")
    return number


def validate_window(start_date: Any, end_date: Any) -> tuple[str, str]:
    """Validate an inclusive date window (start <= end)."""
    start = validate_iso_date(start_date, "start_date")
    end = validate_iso_date(end_date, "end_date")
    if start > end:
        raise BillingQueryValidationError("start_date must not be after end_date.")
    return start, end


# Columns selected from system.billing.usage. No identity columns, no free-text names.
USAGE_COLUMNS: tuple[str, ...] = (
    "account_id",
    "workspace_id",
    "record_id",
    "sku_name",
    "cloud",
    "usage_start_time",
    "usage_end_time",
    "usage_date",
    "usage_unit",
    "usage_quantity",
    "record_type",
    "ingestion_date",
    "billing_origin_product",
    "usage_type",
    "custom_tags",
    "product_features",
)

# usage_metadata sub-fields projected individually (IDs only). Order = attribution priority.
ATTRIBUTION_RULES: tuple[tuple[str, str], ...] = (
    ("warehouse_id", "SQL_WAREHOUSE"),
    ("endpoint_id", "SERVING_ENDPOINT"),
    ("endpoint_name", "SERVING_ENDPOINT"),
    ("app_id", "APP"),
    ("job_id", "JOB"),
    ("dlt_pipeline_id", "PIPELINE"),
    ("cluster_id", "CLUSTER"),
    ("instance_pool_id", "POOL"),
    ("notebook_id", "NOTEBOOK"),
    ("serverless_compute_id", "SERVERLESS"),
)
ATTRIBUTION_KEYS: tuple[str, ...] = tuple(k for k, _ in ATTRIBUTION_RULES)

PRICE_COLUMNS: tuple[str, ...] = (
    "account_id",
    "sku_name",
    "cloud",
    "currency_code",
    "usage_unit",
    "price_start_time",
    "price_end_time",
    "pricing",
)


def build_usage_query(workspace_id: Any, start_date: Any, end_date: Any, limit: Any) -> str:
    """Build the bounded, workspace-scoped, minimal-projection usage SELECT (no ``SELECT *``)."""
    ws = validate_workspace_id(workspace_id)
    start, end = validate_window(start_date, end_date)
    n = validate_limit(limit)
    meta_cols = ", ".join(f"usage_metadata.{k} AS {k}" for k in ATTRIBUTION_KEYS)
    cols = ", ".join(USAGE_COLUMNS)
    return (
        f"SELECT {cols}, {meta_cols} "
        "FROM system.billing.usage "
        f"WHERE workspace_id = '{ws}' "
        f"AND usage_date >= '{start}' AND usage_date <= '{end}' "
        f"ORDER BY usage_date, record_id LIMIT {n}"
    )


def build_list_prices_query(limit: Any = PRICE_ROW_LIMIT, cloud: str = "AZURE") -> str:
    """Build the bounded list-price SELECT. ``cloud`` is restricted to a fixed set."""
    if cloud.upper() not in {"AZURE", "AWS", "GCP"}:
        raise BillingQueryValidationError("cloud must be one of AZURE, AWS, GCP.")
    n = validate_limit(limit)
    cols = ", ".join(PRICE_COLUMNS)
    return (
        f"SELECT {cols} FROM system.billing.list_prices "
        f"WHERE cloud = '{cloud.upper()}' ORDER BY sku_name, price_start_time LIMIT {n}"
    )


def parse_map(value: Any) -> dict[str, Any]:
    """Normalise a MAP/STRUCT result that may arrive as a dict or JSON text."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def to_decimal(value: Any) -> Decimal:
    """Convert a source numeric to ``Decimal`` without float rounding; reject NaN/inf."""
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, bool) or value is None:
        raise ValueError("not a number")
    elif isinstance(value, float):
        result = Decimal(repr(value))
    else:
        try:
            result = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValueError("not a number") from exc
    if not result.is_finite():
        raise ValueError("non-finite number")
    return result


def to_decimal_or_none(value: Any) -> Decimal | None:
    """Like :func:`to_decimal` but missing/blank/invalid values become ``None``."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return to_decimal(value)
    except ValueError:
        return None


def canonical_timestamp(value: Any) -> str:
    """Parsed-UTC ISO text of a timestamp so formatting differences never change identity.

    ``...00Z``, ``...00.000+00:00`` and ``... 00:00:00`` (naive = UTC) all map to the same
    text. An unparsable value is kept verbatim (stripped) rather than guessed at.
    """
    parsed = parse_timestamp(value)
    if parsed is None:
        return str(value).strip() if value is not None else ""
    return parsed.astimezone(UTC).isoformat()


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp (``Z`` or offset); naive values are treated as UTC."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00").replace(" ", "T", 1)
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def resolve_resource(usage_metadata: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(resource_type, resource_id)`` by ordered exact key lookup, or ``None``."""
    for key, rtype in ATTRIBUTION_RULES:
        val = usage_metadata.get(key)
        if val not in (None, ""):
            return rtype, str(val)
    return None


def matches_resource(usage_metadata: dict[str, Any], resource_id: str) -> bool:
    """Exact (never substring) match of ``resource_id`` against any attribution key."""
    return any(
        usage_metadata.get(k) not in (None, "") and str(usage_metadata[k]) == resource_id
        for k in ATTRIBUTION_KEYS
    )
