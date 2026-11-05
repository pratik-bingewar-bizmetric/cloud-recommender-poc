"""Unit tests for Token Economics Telemetry and Unit Costing."""

from decimal import Decimal
from pathlib import Path

import pytest
from schemas.models import CloudConnection
from services.lakehouse_store import FabricLakehouseStore
from services.token_telemetry_service import (
    TokenTelemetryService,
    compute_token_cost,
)


@pytest.fixture
def token_service(tmp_path: Path) -> TokenTelemetryService:
    store = FabricLakehouseStore(db_path=tmp_path / "token_test.db")
    conn = CloudConnection(
        id="conn-ai-01",
        name="AI Scope",
        provider="azure",
        scope_id="sub-ai",
        auth_method="service_principal",
    )
    store.save_connection(conn)
    return TokenTelemetryService(store=store)


def test_deterministic_token_cost_calculation() -> None:
    # GPT-4o: prompt=$2.50 / 1M ($0.0000025), comp=$10.00 / 1M ($0.000010)
    # 1,000 prompt tokens = $0.0025, 500 comp tokens = $0.0050 -> Total = $0.0075
    cost_4o, status_4o = compute_token_cost("gpt-4o", prompt_tokens=1000, completion_tokens=500)
    assert cost_4o == Decimal("0.0075")
    assert status_4o == "published_rate"

    # GPT-4o-mini: prompt=$0.15 / 1M ($0.00000015), comp=$0.60 / 1M ($0.0000006)
    # 10,000 prompt = $0.0015, 2,000 comp = $0.0012 -> Total = $0.0027
    cost_mini, status_mini = compute_token_cost(
        "gpt-4o-mini", prompt_tokens=10000, completion_tokens=2000
    )
    assert cost_mini == Decimal("0.0027")
    assert status_mini == "published_rate"

    # Unknown model: returns $0.0000 and unknown_model_rate
    cost_unk, status_unk = compute_token_cost(
        "custom-fine-tuned-unknown", prompt_tokens=1000, completion_tokens=500
    )
    assert cost_unk == Decimal("0.0000")
    assert status_unk == "unknown_model_rate"


def test_record_and_aggregate_token_usage(token_service: TokenTelemetryService) -> None:
    # 1. Record two real usage events
    token_service.record_usage(
        connection_id="conn-ai-01",
        model_name="gpt-4o",
        prompt_tokens=2000,
        completion_tokens=1000,
        latency_ms=320,
    )
    token_service.record_usage(
        connection_id="conn-ai-01",
        model_name="gpt-4o-mini",
        prompt_tokens=5000,
        completion_tokens=2000,
        latency_ms=180,
    )

    # 2. Query summary
    summary = token_service.get_summary("conn-ai-01", days=7)
    assert summary.total_prompt_tokens == 7000
    assert summary.total_completion_tokens == 3000
    assert summary.total_tokens == 10000
    assert summary.token_efficiency_ratio == round(3000 / 7000, 3)
    assert summary.total_cost_usd > Decimal("0.0000")
    assert len(summary.models_breakdown) == 2
    assert len(summary.daily_timeseries) >= 1


def test_empty_token_telemetry_returns_zero_counts(
    token_service: TokenTelemetryService,
) -> None:
    # Ensure zero data does not generate fake sine waves
    summary = token_service.get_summary("conn-empty", days=30)
    assert summary.total_prompt_tokens == 0
    assert summary.total_completion_tokens == 0
    assert summary.total_tokens == 0
    assert summary.total_cost_usd == Decimal("0.0000")
    assert summary.token_efficiency_ratio == 0.0
    assert summary.models_breakdown == []
    assert summary.daily_timeseries == []
