"""Deterministic pricing calculation RPC handlers for Microsoft Fabric UDF."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import ValidationError
from schemas.models import (
    PricingCalculationArgs,
    UdfResponse,
)
from services.azure_real_client import AzureRealClient


async def handle_calculate_pricing(
    azure_client: AzureRealClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Deterministically calculate monthly cost using live official Azure Retail Prices API."""
    try:
        parsed = PricingCalculationArgs(**args)
    except (ValidationError, ValueError, TypeError) as exc:
        return UdfResponse(
            status="error",
            error_code="INVALID_ARGUMENTS",
            error_message=f"Validation error: {exc}",
        ).model_dump(mode="json")

    hourly_rate = await azure_client.fetch_retail_price(
        arm_sku_name=parsed.arm_sku_name,
        region=parsed.region,
    )

    if hourly_rate is None:
        return UdfResponse(
            status="error",
            error_code="SKU_NOT_FOUND",
            error_message=(
                f"SKU '{parsed.arm_sku_name}' in region '{parsed.region}' not found in "
                "Azure Retail Prices API catalog."
            ),
        ).model_dump(mode="json")

    monthly_cost = (hourly_rate * parsed.hours_per_month).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return UdfResponse(
        status="success",
        data={
            "arm_sku_name": parsed.arm_sku_name,
            "region": parsed.region,
            "hourly_rate_usd": float(hourly_rate),
            "monthly_cost_usd": float(monthly_cost),
            "annual_cost_usd": float(monthly_cost * Decimal("12.0")),
            "currency": "USD",
            "source": "Azure Retail Prices API (Public Consumption Tier)",
        },
    ).model_dump(mode="json")
