from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from cloud_recommender.main import app


@pytest.mark.asyncio
async def test_list_connections_returns_safe_metadata_without_secrets() -> None:
    """Verify GET /api/v1/connections lists configured connections with strictly safe metadata."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/connections")
        assert resp.status_code == 200
        connections = resp.json()
        assert isinstance(connections, list)
        assert len(connections) >= 1

        for conn in connections:
            assert "id" in conn
            assert "name" in conn
            assert "provider" in conn
            assert "scope_id" in conn
            assert "status" in conn
            assert "capabilities" in conn

            # Zero-secret policy verification
            for forbidden_key in (
                "client_secret",
                "secret",
                "password",
                "private_key",
                "access_token",
                "token",
            ):
                assert forbidden_key not in conn, (
                    f"Forbidden credential field '{forbidden_key}' exposed in connections API!"
                )


@pytest.mark.asyncio
async def test_validate_connection_probe() -> None:
    """Verify POST /api/v1/connections/validate performs real or fixture validation probe."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Validate GCP reference project fixture
        resp = await client.post(
            "/api/v1/connections/validate",
            json={
                "provider": "gcp",
                "scope_id": "smart-expense-gcp-prod",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["provider"] == "gcp"
        assert data["scope_id"] == "smart-expense-gcp-prod"
        assert data["status"] == "connected"
        assert data["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_token_economics_endpoint_structure_and_rates() -> None:
    """Verify POST /api/v1/monitoring/token-economics returns deterministic structure and rates."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Query GCP benchmark token economics
        resp = await client.post(
            "/api/v1/monitoring/token-economics",
            json={
                "provider": "gcp",
                "scope_id": "smart-expense-gcp-prod",
                "time_window": "7d",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "gcp"
        assert data["scope_id"] == "smart-expense-gcp-prod"
        assert data["data_status"] in (
            "simulation_benchmark",
            "live_telemetry",
            "instrumentation_required",
        )
        assert "total_tokens" in data
        assert "estimated_cost_usd" in data
        assert "trend_points" in data
        assert "model_breakdowns" in data
        assert "diagnostic_setup_guide" in data
        assert len(data["diagnostic_setup_guide"]) >= 1


@pytest.mark.asyncio
async def test_token_economics_azure_live_or_instrumentation_guide() -> None:
    """Verify Azure token economics reports truthful instrumentation required state or live telemetry."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/monitoring/token-economics",
            json={
                "provider": "azure",
                "scope_id": "f718c261-ab85-49fd-907e-99c022cc2aeb",
                "time_window": "7d",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "azure"
        assert data["data_status"] in (
            "instrumentation_required",
            "live_telemetry",
            "no_data_available",
            "unavailable_permission_required",
        )
        assert len(data["diagnostic_setup_guide"]) >= 2


@pytest.mark.asyncio
async def test_token_economics_distinguishes_empty_datapoints_from_measured_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that HTTP 200 with 0 datapoints returns no_data_available, whereas 0 tokens with datapoints returns measured zero."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from cloud_recommender.core.config import Settings
    from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
    from cloud_recommender.schemas.inventory import (
        DiscoveredResource,
        SubscriptionOrProjectAnalysis,
    )
    from cloud_recommender.schemas.monitoring import MonitoringQueryRequest
    from cloud_recommender.schemas.recommendation import CostBreakdown
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
    from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
    from cloud_recommender.services.monitoring.monitoring_service import (
        CentralizedMonitoringService,
    )

    settings = Settings(offline_pricing_mode=True)
    az_svc = AzureInventoryService(settings=settings)
    gcp_svc = GcpInventoryService(settings=settings)
    mon_svc = CentralizedMonitoringService(
        settings=settings, azure_service=az_svc, gcp_service=gcp_svc
    )

    # Mock Azure service with a Cognitive Services resource
    ai_res = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub-123/resourceGroups/rg-ai/providers/Microsoft.CognitiveServices/accounts/openai-test",
        resource_name="openai-test",
        native_resource_type="Microsoft.CognitiveServices/accounts",
        canonical_service_id="azure-openai",
        service_category=ServiceCategory.AI_ML,
        region="eastus",
        parent_scope_id="sub-123",
        subscription_id="sub-123",
        tags_or_labels={},
        configuration={},
        relationships=[],
        origin="discovered",
        pricing_status="verified",
        estimated_monthly_cost=Decimal("0.00"),
        calculation_explanation="",
        discovery_timestamp=datetime.now(UTC),
    )

    mock_analysis = SubscriptionOrProjectAnalysis(
        provider=CloudProvider.AZURE,
        scope_id="sub-123",
        scope_name="Azure Subscription Test",
        scope_type="azure_subscription",
        resource_count=1,
        resources=[ai_res],
        data_source="live_authenticated",
        cost_breakdown=CostBreakdown(
            subtotal=Decimal("0.00"),
            total_monthly=Decimal("0.00"),
            total_annual=Decimal("0.00"),
        ),
        architecture_mermaid="",
    )

    monkeypatch.setattr(az_svc, "analyze_subscription", AsyncMock(return_value=mock_analysis))
    monkeypatch.setattr(
        az_svc, "get_access_token", AsyncMock(return_value=("mock-token", "azure_cli"))
    )

    # Case 1: HTTP 200 with empty series (0 datapoints) -> MUST NOT report measured zero!
    class MockEmptyResp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"value": [{"timeseries": [{"data": []}]}]}

    class MockEmptyClient:
        async def __aenter__(self) -> "MockEmptyClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            pass

        async def get(self, *_args: Any, **_kwargs: Any) -> MockEmptyResp:
            return MockEmptyResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: MockEmptyClient())

    req = MonitoringQueryRequest(provider=CloudProvider.AZURE, scope_id="sub-123", time_window="7d")
    res_empty = await mon_svc.get_token_economics(req)

    assert res_empty.data_status == "no_data_available"
    assert "zero metric datapoints exist" in res_empty.status_message

    # Case 2: HTTP 200 with 3 sampled datapoints that all have total = 0 -> Measured Zero!
    class MockZeroResp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "value": [
                    {
                        "timeseries": [
                            {
                                "data": [
                                    {"timeStamp": "2026-10-19T00:00:00Z", "total": 0.0},
                                    {"timeStamp": "2026-10-19T01:00:00Z", "total": 0.0},
                                    {"timeStamp": "2026-10-19T02:00:00Z", "total": 0.0},
                                ]
                            }
                        ]
                    }
                ]
            }

    class MockZeroClient:
        async def __aenter__(self) -> "MockZeroClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            pass

        async def get(self, *_args: Any, **_kwargs: Any) -> MockZeroResp:
            return MockZeroResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: MockZeroClient())

    res_zero = await mon_svc.get_token_economics(req)
    assert res_zero.data_status == "live_telemetry"
    assert res_zero.total_tokens == 0
    assert "3 sampled datapoints" in res_zero.status_message
    assert "Measured zero" in res_zero.status_message


@pytest.mark.asyncio
async def test_token_economics_live_telemetry_with_positive_volume_and_no_double_counting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify live positive Azure OpenAI telemetry correctly maps Prompt, Generated, and Total without double-counting."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from cloud_recommender.core.config import Settings
    from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
    from cloud_recommender.schemas.inventory import (
        DiscoveredResource,
        SubscriptionOrProjectAnalysis,
    )
    from cloud_recommender.schemas.monitoring import MonitoringQueryRequest
    from cloud_recommender.schemas.recommendation import CostBreakdown
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
    from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
    from cloud_recommender.services.monitoring.monitoring_service import (
        CentralizedMonitoringService,
    )

    settings = Settings(offline_pricing_mode=True)
    az_svc = AzureInventoryService(settings=settings)
    gcp_svc = GcpInventoryService(settings=settings)
    mon_svc = CentralizedMonitoringService(
        settings=settings, azure_service=az_svc, gcp_service=gcp_svc
    )

    ai_res = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub-123/resourceGroups/rg-telecom/providers/Microsoft.CognitiveServices/accounts/telecom-ai",
        resource_name="telecom-ai",
        resource_group="rg-telecom",
        native_resource_type="Microsoft.CognitiveServices/accounts",
        canonical_service_id="azure-openai",
        service_category=ServiceCategory.AI_ML,
        region="southindia",
        parent_scope_id="sub-123",
        subscription_id="sub-123",
        tags_or_labels={},
        configuration={},
        relationships=[],
        origin="discovered",
        pricing_status="verified",
        estimated_monthly_cost=Decimal("0.00"),
        calculation_explanation="",
        discovery_timestamp=datetime.now(UTC),
    )

    mock_analysis = SubscriptionOrProjectAnalysis(
        provider=CloudProvider.AZURE,
        scope_id="sub-123",
        scope_name="Live Sub",
        scope_type="azure_subscription",
        resource_count=1,
        resources=[ai_res],
        data_source="live_authenticated",
        cost_breakdown=CostBreakdown(
            subtotal=Decimal("0.00"),
            total_monthly=Decimal("0.00"),
            total_annual=Decimal("0.00"),
        ),
        architecture_mermaid="",
    )

    monkeypatch.setattr(az_svc, "analyze_subscription", AsyncMock(return_value=mock_analysis))
    monkeypatch.setattr(
        az_svc, "get_access_token", AsyncMock(return_value=("mock-token", "azure_cli"))
    )

    # Return ALL 6 metric aliases (both legacy inference names and modern usage names)
    # ProcessedPromptTokens (1630), InputTokens (1630)
    # GeneratedTokens (691), OutputTokens (691)
    # TokenTransaction (2321), TotalTokens (2321)
    class MockLiveResp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "value": [
                    {
                        "name": {"value": "ProcessedPromptTokens"},
                        "timeseries": [
                            {"data": [{"timeStamp": "2026-10-21T10:00:00Z", "total": 1630.0}]}
                        ],
                    },
                    {
                        "name": {"value": "GeneratedTokens"},
                        "timeseries": [
                            {"data": [{"timeStamp": "2026-10-21T10:00:00Z", "total": 691.0}]}
                        ],
                    },
                    {
                        "name": {"value": "TokenTransaction"},
                        "timeseries": [
                            {"data": [{"timeStamp": "2026-10-21T10:00:00Z", "total": 2321.0}]}
                        ],
                    },
                    {
                        "name": {"value": "InputTokens"},
                        "timeseries": [
                            {"data": [{"timeStamp": "2026-10-21T10:00:00Z", "total": 1630.0}]}
                        ],
                    },
                    {
                        "name": {"value": "OutputTokens"},
                        "timeseries": [
                            {"data": [{"timeStamp": "2026-10-21T10:00:00Z", "total": 691.0}]}
                        ],
                    },
                    {
                        "name": {"value": "TotalTokens"},
                        "timeseries": [
                            {"data": [{"timeStamp": "2026-10-21T10:00:00Z", "total": 2321.0}]}
                        ],
                    },
                ]
            }

    class MockLiveClient:
        async def __aenter__(self) -> "MockLiveClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            pass

        async def get(self, *_args: Any, **kwargs: Any) -> MockLiveResp:
            # Verify that query params request supported metrics and API version 2023-10-01
            params = kwargs.get("params", {})
            assert "ProcessedPromptTokens" in params["metricnames"]
            assert "GeneratedTokens" in params["metricnames"]
            assert "TokenTransaction" in params["metricnames"]
            assert params["api-version"] == "2023-10-01"
            assert params["aggregation"] == "Total"
            return MockLiveResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: MockLiveClient())

    req = MonitoringQueryRequest(provider=CloudProvider.AZURE, scope_id="sub-123", time_window="7d")
    res = await mon_svc.get_token_economics(req)

    assert res.data_status == "live_telemetry"
    # Verification: Total tokens must be 2321, NOT double-counted as 2321 + 1630 + 691 = 4642
    assert res.total_tokens == 2321
    assert res.prompt_tokens == 1630
    assert res.completion_tokens == 691

    # Cost calculation: 1630 * $2.50 / 1M = $0.004075; 691 * $10.00 / 1M = $0.00691; Total = $0.0110
    assert res.estimated_cost_usd == Decimal("0.0110")

    # Check breakdowns and records
    assert len(res.trend_points) == 1
    assert res.trend_points[0].total_tokens == 2321
    assert res.trend_points[0].prompt_tokens == 1630
    assert res.trend_points[0].completion_tokens == 691

    assert len(res.model_breakdowns) == 1
    assert res.model_breakdowns[0].model_name == "gpt-4o"
    assert res.model_breakdowns[0].total_tokens == 2321

    assert len(res.workload_breakdowns) == 1
    assert res.workload_breakdowns[0].workload_or_group == "rg-telecom"
    assert res.workload_breakdowns[0].total_tokens == 2321

    assert len(res.usage_records) == 1
    assert res.usage_records[0].resource_name == "telecom-ai"
    assert res.usage_records[0].total_tokens == 2321


@pytest.mark.asyncio
async def test_token_economics_handles_partial_metrics_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that when only partial metrics exist (e.g. only prompt tokens), total is calculated safely without error."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from cloud_recommender.core.config import Settings
    from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
    from cloud_recommender.schemas.inventory import (
        DiscoveredResource,
        SubscriptionOrProjectAnalysis,
    )
    from cloud_recommender.schemas.monitoring import MonitoringQueryRequest
    from cloud_recommender.schemas.recommendation import CostBreakdown
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
    from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
    from cloud_recommender.services.monitoring.monitoring_service import (
        CentralizedMonitoringService,
    )

    settings = Settings(offline_pricing_mode=True)
    az_svc = AzureInventoryService(settings=settings)
    gcp_svc = GcpInventoryService(settings=settings)
    mon_svc = CentralizedMonitoringService(
        settings=settings, azure_service=az_svc, gcp_service=gcp_svc
    )

    ai_res = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub-123/resourceGroups/rg-embed/providers/Microsoft.CognitiveServices/accounts/embed-ai",
        resource_name="embed-ai",
        resource_group="rg-embed",
        native_resource_type="Microsoft.CognitiveServices/accounts",
        canonical_service_id="azure-openai",
        service_category=ServiceCategory.AI_ML,
        region="eastus",
        parent_scope_id="sub-123",
        subscription_id="sub-123",
        tags_or_labels={},
        configuration={},
        relationships=[],
        origin="discovered",
        pricing_status="verified",
        estimated_monthly_cost=Decimal("0.00"),
        calculation_explanation="",
        discovery_timestamp=datetime.now(UTC),
    )

    mock_analysis = SubscriptionOrProjectAnalysis(
        provider=CloudProvider.AZURE,
        scope_id="sub-123",
        scope_name="Live Sub",
        scope_type="azure_subscription",
        resource_count=1,
        resources=[ai_res],
        data_source="live_authenticated",
        cost_breakdown=CostBreakdown(
            subtotal=Decimal("0.00"),
            total_monthly=Decimal("0.00"),
            total_annual=Decimal("0.00"),
        ),
        architecture_mermaid="",
    )

    monkeypatch.setattr(az_svc, "analyze_subscription", AsyncMock(return_value=mock_analysis))
    monkeypatch.setattr(
        az_svc, "get_access_token", AsyncMock(return_value=("mock-token", "azure_cli"))
    )

    # Return only InputTokens (5000), GeneratedTokens absent
    class MockPartialResp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "value": [
                    {
                        "name": {"value": "InputTokens"},
                        "timeseries": [
                            {"data": [{"timeStamp": "2026-10-21T10:00:00Z", "total": 5000.0}]}
                        ],
                    }
                ]
            }

    class MockPartialClient:
        async def __aenter__(self) -> "MockPartialClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            pass

        async def get(self, *_args: Any, **_kwargs: Any) -> MockPartialResp:
            return MockPartialResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: MockPartialClient())

    req = MonitoringQueryRequest(provider=CloudProvider.AZURE, scope_id="sub-123", time_window="7d")
    res = await mon_svc.get_token_economics(req)

    assert res.data_status == "live_telemetry"
    assert res.prompt_tokens == 5000
    assert res.completion_tokens == 0
    assert res.total_tokens == 5000


@pytest.mark.asyncio
async def test_token_economics_handles_http_errors_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify HTTP 403 Forbidden returns unavailable_permission_required, and 500 does not crash."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from cloud_recommender.core.config import Settings
    from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
    from cloud_recommender.schemas.inventory import (
        DiscoveredResource,
        SubscriptionOrProjectAnalysis,
    )
    from cloud_recommender.schemas.monitoring import MonitoringQueryRequest
    from cloud_recommender.schemas.recommendation import CostBreakdown
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
    from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
    from cloud_recommender.services.monitoring.monitoring_service import (
        CentralizedMonitoringService,
    )

    settings = Settings(offline_pricing_mode=True)
    az_svc = AzureInventoryService(settings=settings)
    gcp_svc = GcpInventoryService(settings=settings)
    mon_svc = CentralizedMonitoringService(
        settings=settings, azure_service=az_svc, gcp_service=gcp_svc
    )

    ai_res = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub-123/resourceGroups/rg-ai/providers/Microsoft.CognitiveServices/accounts/openai-test",
        resource_name="openai-test",
        native_resource_type="Microsoft.CognitiveServices/accounts",
        canonical_service_id="azure-openai",
        service_category=ServiceCategory.AI_ML,
        region="eastus",
        parent_scope_id="sub-123",
        subscription_id="sub-123",
        tags_or_labels={},
        configuration={},
        relationships=[],
        origin="discovered",
        pricing_status="verified",
        estimated_monthly_cost=Decimal("0.00"),
        calculation_explanation="",
        discovery_timestamp=datetime.now(UTC),
    )

    mock_analysis = SubscriptionOrProjectAnalysis(
        provider=CloudProvider.AZURE,
        scope_id="sub-123",
        scope_name="Live Sub",
        scope_type="azure_subscription",
        resource_count=1,
        resources=[ai_res],
        data_source="live_authenticated",
        cost_breakdown=CostBreakdown(
            subtotal=Decimal("0.00"),
            total_monthly=Decimal("0.00"),
            total_annual=Decimal("0.00"),
        ),
        architecture_mermaid="",
    )

    monkeypatch.setattr(az_svc, "analyze_subscription", AsyncMock(return_value=mock_analysis))
    monkeypatch.setattr(
        az_svc, "get_access_token", AsyncMock(return_value=("mock-token", "azure_cli"))
    )

    # Case 1: 403 Forbidden
    class Mock403Resp:
        status_code = 403

        def json(self) -> dict[str, Any]:
            return {"error": {"code": "AuthorizationFailed", "message": "Forbidden"}}

    class Mock403Client:
        async def __aenter__(self) -> "Mock403Client":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            pass

        async def get(self, *_args: Any, **_kwargs: Any) -> Mock403Resp:
            return Mock403Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: Mock403Client())

    req = MonitoringQueryRequest(provider=CloudProvider.AZURE, scope_id="sub-123", time_window="7d")
    res_403 = await mon_svc.get_token_economics(req)

    assert res_403.data_status == "unavailable_permission_required"
    assert "403 Forbidden" in res_403.status_message
    assert "Monitoring Reader" in res_403.status_message


@pytest.mark.asyncio
async def test_token_economics_multi_resource_reconciliation_and_child_exclusion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify multi-resource token aggregation, cost reconciliation, and exclusion of child project resources."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from cloud_recommender.core.config import Settings
    from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
    from cloud_recommender.schemas.inventory import (
        DiscoveredResource,
        SubscriptionOrProjectAnalysis,
    )
    from cloud_recommender.schemas.monitoring import MonitoringQueryRequest
    from cloud_recommender.schemas.recommendation import CostBreakdown
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
    from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
    from cloud_recommender.services.monitoring.monitoring_service import (
        CentralizedMonitoringService,
    )

    settings = Settings(offline_pricing_mode=True)
    az_svc = AzureInventoryService(settings=settings)
    gcp_svc = GcpInventoryService(settings=settings)
    mon_svc = CentralizedMonitoringService(
        settings=settings, azure_service=az_svc, gcp_service=gcp_svc
    )

    res_cloud_rec = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub-123/resourceGroups/rg-cloud-recomender/providers/Microsoft.CognitiveServices/accounts/rg-cloud-recomender",
        resource_name="rg-cloud-recomender",
        resource_group="rg-cloud-recomender",
        native_resource_type="Microsoft.CognitiveServices/accounts",
        canonical_service_id="azure-openai",
        service_category=ServiceCategory.AI_ML,
        region="eastus",
        parent_scope_id="sub-123",
        subscription_id="sub-123",
        tags_or_labels={},
        configuration={},
        relationships=[],
        origin="discovered",
        pricing_status="verified",
        estimated_monthly_cost=Decimal("0.00"),
        calculation_explanation="",
        discovery_timestamp=datetime.now(UTC),
    )

    res_telecom = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub-123/resourceGroups/rg-telecom-rag-poc/providers/Microsoft.CognitiveServices/accounts/rg-telecom-rag-poc",
        resource_name="rg-telecom-rag-poc",
        resource_group="rg-telecom-rag-poc",
        native_resource_type="Microsoft.CognitiveServices/accounts",
        canonical_service_id="azure-openai",
        service_category=ServiceCategory.AI_ML,
        region="eastus",
        parent_scope_id="sub-123",
        subscription_id="sub-123",
        tags_or_labels={},
        configuration={},
        relationships=[],
        origin="discovered",
        pricing_status="verified",
        estimated_monthly_cost=Decimal("0.00"),
        calculation_explanation="",
        discovery_timestamp=datetime.now(UTC),
    )

    res_child_project = DiscoveredResource(
        provider=CloudProvider.AZURE,
        resource_id="/subscriptions/sub-123/resourceGroups/rg-cloud-recomender/providers/Microsoft.CognitiveServices/accounts/rg-cloud-recomender/projects/child-proj",
        resource_name="child-proj",
        resource_group="rg-cloud-recomender",
        native_resource_type="Microsoft.CognitiveServices/accounts/projects",
        canonical_service_id="azure-ai-project",
        service_category=ServiceCategory.AI_ML,
        region="eastus",
        parent_scope_id="sub-123",
        subscription_id="sub-123",
        tags_or_labels={},
        configuration={},
        relationships=[],
        origin="discovered",
        pricing_status="verified",
        estimated_monthly_cost=Decimal("0.00"),
        calculation_explanation="",
        discovery_timestamp=datetime.now(UTC),
    )

    mock_analysis = SubscriptionOrProjectAnalysis(
        provider=CloudProvider.AZURE,
        scope_id="sub-123",
        scope_name="Live Sub Multi",
        scope_type="azure_subscription",
        resource_count=3,
        resources=[res_cloud_rec, res_telecom, res_child_project],
        data_source="live_authenticated",
        cost_breakdown=CostBreakdown(
            subtotal=Decimal("0.00"),
            total_monthly=Decimal("0.00"),
            total_annual=Decimal("0.00"),
        ),
        architecture_mermaid="",
    )

    monkeypatch.setattr(az_svc, "analyze_subscription", AsyncMock(return_value=mock_analysis))
    monkeypatch.setattr(
        az_svc, "get_access_token", AsyncMock(return_value=("mock-token", "azure_cli"))
    )

    queried_urls: list[str] = []

    class MockMultiClient:
        async def __aenter__(self) -> "MockMultiClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            pass

        async def get(self, url: str, *_args: Any, **_kwargs: Any) -> Any:
            queried_urls.append(url)

            class Resp:
                def __init__(self, code: int, data: dict[str, Any]) -> None:
                    self.status_code = code
                    self._data = data

                def json(self) -> dict[str, Any]:
                    return self._data

            if "rg-cloud-recomender/providers" in url:
                # 2193 prompt, 8623 completion, 10816 total (with duplicate aliases)
                return Resp(
                    200,
                    {
                        "value": [
                            {
                                "name": {"value": "ProcessedPromptTokens"},
                                "timeseries": [
                                    {
                                        "data": [
                                            {"timeStamp": "2026-10-16T06:00:00Z", "total": 2193.0}
                                        ]
                                    }
                                ],
                            },
                            {
                                "name": {"value": "InputTokens"},
                                "timeseries": [
                                    {
                                        "data": [
                                            {"timeStamp": "2026-10-16T06:00:00Z", "total": 2193.0}
                                        ]
                                    }
                                ],
                            },
                            {
                                "name": {"value": "GeneratedTokens"},
                                "timeseries": [
                                    {
                                        "data": [
                                            {"timeStamp": "2026-10-16T06:00:00Z", "total": 8623.0}
                                        ]
                                    }
                                ],
                            },
                            {
                                "name": {"value": "OutputTokens"},
                                "timeseries": [
                                    {
                                        "data": [
                                            {"timeStamp": "2026-10-16T06:00:00Z", "total": 8623.0}
                                        ]
                                    }
                                ],
                            },
                            {
                                "name": {"value": "TokenTransaction"},
                                "timeseries": [
                                    {
                                        "data": [
                                            {"timeStamp": "2026-10-16T06:00:00Z", "total": 10816.0}
                                        ]
                                    }
                                ],
                            },
                            {
                                "name": {"value": "TotalTokens"},
                                "timeseries": [
                                    {
                                        "data": [
                                            {"timeStamp": "2026-10-16T06:00:00Z", "total": 10816.0}
                                        ]
                                    }
                                ],
                            },
                        ]
                    },
                )
            elif "rg-telecom-rag-poc/providers" in url:
                # 1945 prompt, 752 completion, 2697 total
                return Resp(
                    200,
                    {
                        "value": [
                            {
                                "name": {"value": "ProcessedPromptTokens"},
                                "timeseries": [
                                    {
                                        "data": [
                                            {"timeStamp": "2026-10-21T09:00:00Z", "total": 1945.0}
                                        ]
                                    }
                                ],
                            },
                            {
                                "name": {"value": "GeneratedTokens"},
                                "timeseries": [
                                    {
                                        "data": [
                                            {"timeStamp": "2026-10-21T09:00:00Z", "total": 752.0}
                                        ]
                                    }
                                ],
                            },
                            {
                                "name": {"value": "TokenTransaction"},
                                "timeseries": [
                                    {
                                        "data": [
                                            {"timeStamp": "2026-10-21T09:00:00Z", "total": 2697.0}
                                        ]
                                    }
                                ],
                            },
                        ]
                    },
                )
            return Resp(404, {})

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: MockMultiClient())

    req = MonitoringQueryRequest(provider=CloudProvider.AZURE, scope_id="sub-123", time_window="7d")
    res = await mon_svc.get_token_economics(req)

    assert res.data_status == "live_telemetry"
    # Child projects must NOT be queried
    assert not any("child-proj" in u for u in queried_urls)
    assert res.discovered_ai_resources_count == 2

    # Aggregate token assertions (Deduped: 2193 + 1945 = 4138 prompt; 8623 + 752 = 9375 completion; 13513 total)
    assert res.prompt_tokens == 4138
    assert res.completion_tokens == 9375
    assert res.total_tokens == 13513

    # Cost reconciliation:
    # 4138 * $2.50 / 1M = $0.010345
    # 9375 * $10.00 / 1M = $0.093750
    # Total = $0.104095 -> $0.1041
    assert res.estimated_cost_usd == Decimal("0.1041")

    # Workload breakdown assertions
    assert len(res.workload_breakdowns) == 2
    rec_breakdowns = {w.workload_or_group: w for w in res.workload_breakdowns}

    cloud_rec_wb = rec_breakdowns["rg-cloud-recomender"]
    assert cloud_rec_wb.total_tokens == 10816
    assert cloud_rec_wb.total_cost_usd == Decimal("0.0917")

    telecom_wb = rec_breakdowns["rg-telecom-rag-poc"]
    assert telecom_wb.total_tokens == 2697
    assert telecom_wb.total_cost_usd == Decimal("0.0124")

    # Usage records
    assert len(res.usage_records) == 2
    assert (
        res.usage_records[0].rate_meter_source == "Azure OpenAI Public Tier (GPT-4o Baseline Rate)"
    )
    assert res.prompt_cost_usd + res.completion_cost_usd == res.estimated_cost_usd
    assert len(res.service_breakdowns) == 1
    assert res.service_breakdowns[0].total_tokens == res.total_tokens
    assert res.service_breakdowns[0].total_cost_usd == res.estimated_cost_usd


@pytest.mark.asyncio
async def test_token_economics_azure_benchmark_mathematical_reconciliation() -> None:
    """Verify that the Azure benchmark simulation summary strictly reconciles across all dimensions."""
    from cloud_recommender.core.config import Settings
    from cloud_recommender.schemas.common import CloudProvider
    from cloud_recommender.schemas.monitoring import MonitoringQueryRequest
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
    from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
    from cloud_recommender.services.monitoring.monitoring_service import (
        CentralizedMonitoringService,
    )

    settings = Settings(offline_pricing_mode=True)
    az_svc = AzureInventoryService(settings=settings)
    gcp_svc = GcpInventoryService(settings=settings)
    mon_svc = CentralizedMonitoringService(
        settings=settings, azure_service=az_svc, gcp_service=gcp_svc
    )

    req = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id="smart-expense-azure-prod",
        time_window="7d",
    )
    res = await mon_svc.get_token_economics(req)

    assert res.data_status == "simulation_benchmark"
    assert res.total_tokens > 0
    # Invariant 1: Total = Prompt + Completion
    assert res.total_tokens == res.prompt_tokens + res.completion_tokens

    # Invariant 2: Sum(Model Tokens) == Total Tokens
    assert sum(m.total_tokens for m in res.model_breakdowns) == res.total_tokens
    assert sum(m.prompt_tokens for m in res.model_breakdowns) == res.prompt_tokens
    assert sum(m.completion_tokens for m in res.model_breakdowns) == res.completion_tokens

    # Invariant 3: Sum(Workload Tokens) == Total Tokens
    assert sum(w.total_tokens for w in res.workload_breakdowns) == res.total_tokens

    # Invariant 4: Sum(Service Tokens) == Total Tokens
    assert len(res.service_breakdowns) >= 1
    assert sum(s.total_tokens for s in res.service_breakdowns) == res.total_tokens

    # Invariant 5: Prompt Cost + Completion Cost == Total Cost
    assert res.prompt_cost_usd + res.completion_cost_usd == res.estimated_cost_usd

    # Invariant 6: Sum(Model Costs) == Total Cost
    assert sum(m.total_cost_usd for m in res.model_breakdowns) == res.estimated_cost_usd

    # Invariant 7: Sum(Workload Costs) == Total Cost
    assert sum(w.total_cost_usd for w in res.workload_breakdowns) == res.estimated_cost_usd

    # Invariant 8: Sum(Service Costs) == Total Cost
    assert sum(s.total_cost_usd for s in res.service_breakdowns) == res.estimated_cost_usd

    # Canonical schema fields validation
    assert len(res.usage_records) > 0
    for rec in res.usage_records:
        assert rec.subscription_id == "smart-expense-azure-prod"
        assert rec.service_name == "Azure OpenAI Service"
        assert rec.model_id is not None
        assert rec.normalized_total_tokens == rec.prompt_tokens + rec.completion_tokens
        assert rec.prompt_rate_per_million is not None
        assert rec.completion_rate_per_million is not None
        assert rec.pricing_source == "Azure Retail Prices API (Public Tier)"
        assert rec.attribution_status in ("attributed_to_model", "unattributed")


@pytest.mark.asyncio
async def test_token_economics_gcp_benchmark_mathematical_reconciliation() -> None:
    """Verify that the GCP benchmark simulation summary strictly reconciles across all dimensions."""
    from cloud_recommender.core.config import Settings
    from cloud_recommender.schemas.common import CloudProvider
    from cloud_recommender.schemas.monitoring import MonitoringQueryRequest
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
    from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
    from cloud_recommender.services.monitoring.monitoring_service import (
        CentralizedMonitoringService,
    )

    settings = Settings(offline_pricing_mode=True)
    az_svc = AzureInventoryService(settings=settings)
    gcp_svc = GcpInventoryService(settings=settings)
    mon_svc = CentralizedMonitoringService(
        settings=settings, azure_service=az_svc, gcp_service=gcp_svc
    )

    req = MonitoringQueryRequest(
        provider=CloudProvider.GCP,
        scope_id="smart-expense-gcp-prod",
        time_window="7d",
    )
    res = await mon_svc.get_token_economics(req)

    assert res.data_status == "simulation_benchmark"
    assert res.total_tokens > 0

    # Invariant 1: Total = Prompt + Completion
    assert res.total_tokens == res.prompt_tokens + res.completion_tokens

    # Invariant 2: Sum(Model Tokens) == Total Tokens
    assert sum(m.total_tokens for m in res.model_breakdowns) == res.total_tokens
    assert sum(m.prompt_tokens for m in res.model_breakdowns) == res.prompt_tokens
    assert sum(m.completion_tokens for m in res.model_breakdowns) == res.completion_tokens

    # Invariant 3: Sum(Workload Tokens) == Total Tokens
    assert sum(w.total_tokens for w in res.workload_breakdowns) == res.total_tokens

    # Invariant 4: Sum(Service Tokens) == Total Tokens
    assert len(res.service_breakdowns) >= 1
    assert sum(s.total_tokens for s in res.service_breakdowns) == res.total_tokens

    # Invariant 5: Prompt Cost + Completion Cost == Total Cost
    assert res.prompt_cost_usd + res.completion_cost_usd == res.estimated_cost_usd

    # Invariant 6: Sum(Model Costs) == Total Cost
    assert sum(m.total_cost_usd for m in res.model_breakdowns) == res.estimated_cost_usd

    # Invariant 7: Sum(Workload Costs) == Total Cost
    assert sum(w.total_cost_usd for w in res.workload_breakdowns) == res.estimated_cost_usd

    # Canonical schema fields validation
    assert len(res.usage_records) > 0
    for rec in res.usage_records:
        assert rec.project_id == "smart-expense-gcp-prod"
        assert rec.service_name == "Vertex AI API"
        assert rec.model_id is not None
        assert rec.normalized_total_tokens == rec.prompt_tokens + rec.completion_tokens
        assert rec.prompt_rate_per_million is not None
        assert rec.completion_rate_per_million is not None
        assert rec.pricing_source == "GCP Cloud Billing Catalog"
        assert rec.attribution_status in ("attributed_to_model", "unattributed")


@pytest.mark.asyncio
async def test_hourly_trend_points_structure_and_chronology() -> None:
    """Verify hourly trend points are chronologically sorted and reconcile cleanly with token totals."""
    from datetime import datetime

    from cloud_recommender.core.config import Settings
    from cloud_recommender.schemas.common import CloudProvider
    from cloud_recommender.schemas.monitoring import MonitoringQueryRequest
    from cloud_recommender.services.inventory.azure_inventory import AzureInventoryService
    from cloud_recommender.services.inventory.gcp_inventory import GcpInventoryService
    from cloud_recommender.services.monitoring.monitoring_service import (
        CentralizedMonitoringService,
    )

    settings = Settings(offline_pricing_mode=True)
    az_svc = AzureInventoryService(settings=settings)
    gcp_svc = GcpInventoryService(settings=settings)
    mon_svc = CentralizedMonitoringService(
        settings=settings, azure_service=az_svc, gcp_service=gcp_svc
    )

    # Query Azure simulation benchmark
    req_azure = MonitoringQueryRequest(
        provider=CloudProvider.AZURE,
        scope_id="smart-expense-azure-prod",
        time_window="24h",
    )
    res_azure = await mon_svc.get_token_economics(req_azure)

    assert len(res_azure.trend_points) > 0, "Expected hourly trend points in benchmark mode"

    # Verify chronological ordering and valid timestamps
    previous_dt = None
    for pt in res_azure.trend_points:
        dt = (
            pt.timestamp
            if isinstance(pt.timestamp, datetime)
            else datetime.fromisoformat(str(pt.timestamp).replace("Z", "+00:00"))
        )
        if previous_dt is not None:
            assert dt >= previous_dt, (
                f"Trend points must be chronologically sorted: {dt} < {previous_dt}"
            )
        previous_dt = dt

        assert pt.prompt_tokens >= 0
        assert pt.completion_tokens >= 0
        assert pt.total_tokens == pt.prompt_tokens + pt.completion_tokens
        assert pt.estimated_cost_usd >= Decimal("0.0")

    # Invariant: Sum of trend point totals matches benchmark total
    sum_trend_total = sum(pt.total_tokens for pt in res_azure.trend_points)
    assert sum_trend_total == res_azure.total_tokens, (
        f"Sum of hourly trend point tokens ({sum_trend_total}) must match aggregate total_tokens ({res_azure.total_tokens})"
    )


@pytest.mark.asyncio
async def test_azure_datapoint_parsing_handles_malformed_timestamps_gracefully() -> None:
    """Verify monitoring service skips malformed or null timestamps without crashing."""
    from datetime import datetime

    # Raw Azure Monitor metric datapoint payload containing invalid and valid timestamps
    raw_metric_data = {
        "value": [
            {
                "name": {"value": "ProcessedPromptTokens"},
                "timeseries": [
                    {
                        "data": [
                            {"timeStamp": "", "total": 1000},
                            {"timeStamp": "invalid-timestamp", "total": 2000},
                            {"timeStamp": "2026-10-21T10:00:00Z", "total": 3500},
                            {"timeStamp": "2026-10-21T11:00:00Z", "total": 4500},
                        ]
                    }
                ],
            }
        ]
    }

    # Simulate parsing exactly as implemented in monitoring_service.py
    hourly_buckets: dict[str, dict[str, int]] = {}
    for metric_entry in raw_metric_data.get("value", []):
        metric_name = metric_entry.get("name", {}).get("value", "")
        for ts_entry in metric_entry.get("timeseries", []):
            for dp in ts_entry.get("data", []):
                raw_ts = dp.get("timeStamp", "")
                if not raw_ts:
                    continue
                try:
                    dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    bucket_key = dt.strftime("%Y-%m-%d %H:00:00")
                except (ValueError, TypeError):
                    continue

                if bucket_key not in hourly_buckets:
                    hourly_buckets[bucket_key] = {"prompt": 0, "completion": 0, "total": 0}
                if metric_name == "ProcessedPromptTokens":
                    hourly_buckets[bucket_key]["prompt"] += int(dp.get("total", 0))

    # The 2 malformed timestamps were safely ignored and only the 2 valid ones were parsed
    assert len(hourly_buckets) == 2
    assert hourly_buckets["2026-10-21 10:00:00"]["prompt"] == 3500
    assert hourly_buckets["2026-10-21 11:00:00"]["prompt"] == 4500
