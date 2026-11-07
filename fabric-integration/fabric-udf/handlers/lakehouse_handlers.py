"""Microsoft Fabric Lakehouse RPC handlers for User Data Functions.

Exposes dedicated analytical endpoints for cost breakdown, synchronization status,
storage health inspection, and telemetry diagnostics.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field

from lakehouse.diagnostics import LakehouseDiagnostics
from lakehouse.health import LakehouseHealthChecker
from lakehouse.repository import AnalyticalRepository
from schemas.models import UdfResponse


class GetCostAnalyticsArgs(BaseModel):
    """Arguments for querying OneLake cost analytics."""

    connection_id: str = Field(default="", description="Target connection ID.")
    start_date: Optional[str] = Field(default=None, description="Start date (YYYY-MM-DD).")
    end_date: Optional[str] = Field(default=None, description="End date (YYYY-MM-DD).")


class GetSyncStatusArgs(BaseModel):
    """Arguments for querying ingestion sync history."""

    connection_id: str = Field(default="", description="Target connection ID.")
    limit: int = Field(default=10, description="Max history entries to return.")


async def handle_get_cost_analytics(
    analytical_repo: AnalyticalRepository,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve multi-dimensional cost analytics grouped strictly by currency."""
    try:
        parsed = GetCostAnalyticsArgs(**args)
    except Exception as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    envelope = analytical_repo.get_cost_analytics(
        connection_id=parsed.connection_id,
        start_date=parsed.start_date,
        end_date=parsed.end_date,
    )
    if envelope.status == "error":
        return UdfResponse(
            status="error",
            error_code=envelope.error_code or "COST_QUERY_FAILED",
            error_message=envelope.error_message,
        ).model_dump(mode="json")

    return {
        "status": "success",
        "data": envelope.data.model_dump(mode="json") if envelope.data else None,
        "data_source": envelope.data_source,
        "records_count": envelope.records_count,
        "query_duration_ms": envelope.query_duration_ms,
        "cache_hit": envelope.cache_hit,
    }


async def handle_get_sync_status(
    analytical_repo: AnalyticalRepository,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve latest synchronization execution status and freshness information."""
    try:
        parsed = GetSyncStatusArgs(**args)
    except Exception as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    envelope = analytical_repo.get_sync_overview(
        connection_id=parsed.connection_id,
        limit=parsed.limit,
    )
    if envelope.status == "error":
        return UdfResponse(
            status="error",
            error_code=envelope.error_code or "SYNC_STATUS_FAILED",
            error_message=envelope.error_message,
        ).model_dump(mode="json")

    return {
        "status": "success",
        "data": envelope.data.model_dump(mode="json") if envelope.data else None,
        "data_source": envelope.data_source,
        "last_sync_at": envelope.last_sync_at,
        "data_freshness_seconds": envelope.data_freshness_seconds,
        "query_duration_ms": envelope.query_duration_ms,
    }


async def handle_get_lakehouse_health(
    health_checker: LakehouseHealthChecker,
) -> dict[str, Any]:
    """Inspect and report the health of all OneLake Delta tables."""
    health_status = health_checker.check_health()
    return {
        "status": "success",
        "data": health_status.model_dump(mode="json"),
    }


async def handle_diagnose_metrics(
    diagnostics: LakehouseDiagnostics,
) -> dict[str, Any]:
    """Execute deep metrics data quality audit on resource_metrics table."""
    diag_data = diagnostics.diagnose_metrics_quality()
    return {
        "status": "success",
        "data": diag_data,
    }

