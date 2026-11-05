"""Real GenAI Token Telemetry & FinOps Economics Ingestion Engine.

Calculates deterministic unit economics for LLM calls based on official published rates:
- Ingests actual `usage` metadata from completions (Azure OpenAI, Azure AI Foundry, etc.)
- Calculates precise monetary cost ($/1k tokens) without generative estimation
- Aggregates genuine historical consumption without synthetic curve generation
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from schemas.models import (
    TokenEconomicsSummary,
    TokenUsageRecord,
)

from services.lakehouse_store import FabricLakehouseStore

# Official published rates per 1,000,000 tokens (USD)
# Source: Azure OpenAI Retail Prices / OpenAI Official Pricing Catalog
MODEL_RATES_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    # model: (prompt_rate_per_1M, completion_rate_per_1M)
    "gpt-4o": (Decimal("2.5000"), Decimal("10.0000")),
    "gpt-4o-mini": (Decimal("0.1500"), Decimal("0.6000")),
    "gpt-4-turbo": (Decimal("10.0000"), Decimal("30.0000")),
    "gpt-4": (Decimal("30.0000"), Decimal("60.0000")),
    "gpt-35-turbo": (Decimal("0.5000"), Decimal("1.5000")),
    "text-embedding-3-small": (Decimal("0.0200"), Decimal("0.0200")),
    "text-embedding-3-large": (Decimal("0.1300"), Decimal("0.1300")),
}

MILLION = Decimal(1000000)


def get_model_rates(model_name: str) -> tuple[tuple[Decimal, Decimal] | None, str]:
    """Retrieve published rates for a model or return None and 'unknown_model_rate'."""
    normalized_name = model_name.lower().strip()
    for known_model, rates in sorted(
        MODEL_RATES_PER_MILLION.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if known_model in normalized_name:
            return rates, "published_rate"
    return None, "unknown_model_rate"


def compute_token_cost(
    model_name: str, prompt_tokens: int, completion_tokens: int
) -> tuple[Decimal, str]:
    """Deterministically compute USD cost for prompt and completion tokens.

    If model rate is unknown, returns (Decimal('0.0000'), 'unknown_model_rate').
    Never uses synthetic or guessed rates.
    """
    rates, pricing_status = get_model_rates(model_name)
    if rates is None:
        return Decimal("0.0000"), pricing_status

    rate_prompt, rate_comp = rates
    cost_prompt = (Decimal(prompt_tokens) * rate_prompt) / MILLION
    cost_comp = (Decimal(completion_tokens) * rate_comp) / MILLION
    total_cost = (cost_prompt + cost_comp).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    return total_cost, pricing_status


class TokenTelemetryService:
    """Service managing real GenAI token consumption telemetry and economics."""

    def __init__(self, store: FabricLakehouseStore) -> None:
        self.store = store

    def record_usage(
        self,
        connection_id: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        deployment_name: str | None = None,
        latency_ms: int | None = None,
    ) -> TokenUsageRecord:
        """Record real model invocation telemetry into Lakehouse persistence."""
        cost, pricing_status = compute_token_cost(
            model_name, prompt_tokens, completion_tokens
        )
        record = TokenUsageRecord(
            event_id=f"evt-{uuid.uuid4()}",
            connection_id=connection_id,
            timestamp=datetime.now(UTC),
            model_name=model_name,
            deployment_name=deployment_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=cost,
            source="direct_inference_intercept",
            pricing_status=pricing_status,  # type: ignore[arg-type]
        )
        self.store.append_token_telemetry(record)
        return record

    def get_summary(self, connection_id: str, days: int = 30) -> TokenEconomicsSummary:
        """Aggregate actual telemetry records over the window into a TokenEconomicsSummary."""
        records = self.store.get_token_telemetry(connection_id=connection_id, days=days)
        cutoff = datetime.now(UTC) - timedelta(days=days)
        filtered_records = [r for r in records if r.timestamp >= cutoff]

        total_prompt = sum(r.prompt_tokens for r in filtered_records)
        total_completion = sum(r.completion_tokens for r in filtered_records)
        total_tokens = sum(r.total_tokens for r in filtered_records)
        total_cost = sum(
            (r.estimated_cost_usd for r in filtered_records), Decimal("0.0000")
        )

        efficiency_ratio = (
            round(total_completion / total_prompt, 3) if total_prompt > 0 else 0.0
        )

        # Breakdown by Model
        model_map: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": Decimal("0.0000"),
                "invocations": 0,
            }
        )
        # Breakdown by Day
        daily_map: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "promptTokens": 0,
                "completionTokens": 0,
                "totalTokens": 0,
                "costUsd": Decimal("0.00"),
                "requests": 0,
            }
        )

        for r in filtered_records:
            # Model stats
            m = model_map[r.model_name]
            m["prompt_tokens"] += r.prompt_tokens
            m["completion_tokens"] += r.completion_tokens
            m["total_tokens"] += r.total_tokens
            m["cost_usd"] += r.estimated_cost_usd
            m["invocations"] += 1

            # Day stats
            day_str = r.timestamp.strftime("%Y-%m-%d")
            d = daily_map[day_str]
            d["promptTokens"] += r.prompt_tokens
            d["completionTokens"] += r.completion_tokens
            d["totalTokens"] += r.total_tokens
            d["costUsd"] += r.estimated_cost_usd
            d["requests"] += 1

        models_list = [
            {
                "model_name": k,
                "prompt_tokens": v["prompt_tokens"],
                "completion_tokens": v["completion_tokens"],
                "total_tokens": v["total_tokens"],
                "cost_usd": float(v["cost_usd"]),
                "invocations": v["invocations"],
            }
            for k, v in model_map.items()
        ]

        timeseries_list = [
            {
                "timestamp": k,
                "promptTokens": v["promptTokens"],
                "completionTokens": v["completionTokens"],
                "totalTokens": v["totalTokens"],
                "costUsd": float(v["costUsd"]),
                "requests": v["requests"],
            }
            for k, v in sorted(daily_map.items(), key=lambda x: x[0])
        ]

        return TokenEconomicsSummary(
            connection_id=connection_id,
            window_days=days,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
            token_efficiency_ratio=efficiency_ratio,
            models_breakdown=models_list,
            daily_timeseries=timeseries_list,
        )
