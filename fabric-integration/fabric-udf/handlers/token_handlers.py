"""Token Economics and AI FinOps RPC handlers for Microsoft Fabric UDF."""

from typing import Any

from pydantic import ValidationError
from schemas.models import (
    GetTokenEconomicsArgs,
    RecordTokenArgs,
    UdfResponse,
)
from services.token_telemetry_service import TokenTelemetryService


async def handle_get_token_economics(
    token_service: TokenTelemetryService,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve aggregated real token consumption and unit economics for a connection."""
    try:
        parsed = GetTokenEconomicsArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    summary = token_service.get_summary(
        connection_id=parsed.connection_id,
        days=parsed.days,
    )
    return UdfResponse(
        status="success",
        data=summary.model_dump(mode="json"),
    ).model_dump(mode="json")


async def handle_record_token_usage(
    token_service: TokenTelemetryService,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Record an authentic model inference event with actual token counts."""
    try:
        parsed = RecordTokenArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    record = token_service.record_usage(
        connection_id=parsed.connection_id,
        model_name=parsed.model_name,
        prompt_tokens=parsed.prompt_tokens,
        completion_tokens=parsed.completion_tokens,
        deployment_name=parsed.deployment_name,
        latency_ms=parsed.latency_ms,
    )
    return UdfResponse(
        status="success",
        data=record.model_dump(mode="json"),
    ).model_dump(mode="json")
