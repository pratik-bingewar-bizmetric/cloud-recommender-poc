"""Offline TEST-ONLY workspace inventory and service factories.

The inventory mirrors the *shape* of the verified Dev workspace (one cluster, one SQL
warehouse, serving endpoints, apps, catalogs, a cluster policy) so tests can exercise the
live-inventory code paths without Databricks credentials. Values are synthetic test data.
"""

from datetime import UTC, datetime

from cloud_recommender.schemas.databricks import (
    CategoryDiscoveryStatus,
    DatabricksCloud,
    DatabricksResourceState,
    DatabricksWorkspaceDiscoveryResponse,
    DiscoveredResourceItem,
    LiveQueryHistoryItem,
    LiveQueryHistoryResponse,
)
from cloud_recommender.services.databricks.billing_ingestion_service import BillingIngestionService
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService
from tests.fixtures.billing_baseline import load_baseline_usage

WORKSPACE_ID = "642006393507276"
CONNECTION_ID = "databricks-azure-dev"
_NOW = datetime(2026, 11, 13, 4, 0, tzinfo=UTC)


def _res(
    rid: str,
    name: str,
    rtype: str,
    status: str | None = None,
    creator: str | None = "tester@example.com",
    **metadata: object,
) -> DiscoveredResourceItem:
    return DiscoveredResourceItem(
        id=rid,
        name=name,
        resource_type=rtype,
        workspace_id=WORKSPACE_ID,
        status=status,
        creator=creator,
        source_api=f"test-fixture/{rtype}",
        metadata=dict(metadata),
        discovered_at=_NOW,
    )


def fixture_resources() -> list[DiscoveredResourceItem]:
    return [
        _res(
            "1102-081455-7t3bqp3v",
            "adf-deaccelator-compute",
            "cluster",
            "TERMINATED",
            node_type_id="Standard_D3_v2",
            num_workers=1,
            autotermination_minutes=None,
        ),
        _res(
            "05ed10a52697a344",
            "Serverless Starter Warehouse",
            "warehouse",
            "STOPPED",
            cluster_size="2X-Small",
            auto_stop_mins=15,
            enable_serverless_compute=True,
        ),
        _res(
            "databricks-claude-fable-5",
            "databricks-claude-fable-5",
            "serving_endpoint",
            "READY",
            task="llm/v1/chat",
            served_entities=[
                {
                    "name": "e1",
                    "entity_name": "claude",
                    "workload_size": "Small",
                    "scale_to_zero_enabled": False,
                }
            ],
        ),
        _res("cement-demand-forecasting", "cement-demand-forecasting", "app", "RUNNING"),
        _res("deaccelerator", "deaccelerator", "catalog", "ACTIVE", catalog_type="MANAGED_CATALOG"),
        _res("policy-1", "Personal Compute", "cluster_policy", None),
    ]


def make_analytics_service(
    *, with_billing: bool, with_inventory: bool = True
) -> FinOpsAnalyticsService:
    """Analytics service wired to offline fixtures. Billing rows only when requested."""
    billing = BillingIngestionService()
    if with_billing:
        load_baseline_usage(billing)
    service = FinOpsAnalyticsService(billing_service=billing)
    # The workspace service caches live at CLASS level; isolate this instance so test
    # fixtures can neither leak into nor read from other tests / the app singleton.
    ws = service.workspace_service
    ws._discovery_cache = {}
    ws._uc_cache = {}
    ws._system_tables_cache = {}
    if with_inventory:
        resources = fixture_resources()
        service.workspace_service._discovery_cache[CONNECTION_ID] = (
            DatabricksWorkspaceDiscoveryResponse(
                connection_id=CONNECTION_ID,
                workspace_id=WORKSPACE_ID,
                workspace_name="test",
                workspace_url="https://example.invalid",
                cloud=DatabricksCloud.AZURE,
                overall_status="completed",
                categories={},
                resources=resources,
                total_resources_count=len(resources),
                discovered_at=_NOW,
            )
        )
    return service


def stub_query_history(
    service: FinOpsAnalyticsService,
    records: list[LiveQueryHistoryItem] | None = None,
    *,
    state: DatabricksResourceState = DatabricksResourceState.UNAVAILABLE,
    has_next_page: bool = False,
    next_page_token: str | None = None,
    error_message: str | None = "offline test stub",
) -> list[dict[str, object]]:
    """Replace the live Query History call with an offline stub; returns the captured call kwargs."""
    calls: list[dict[str, object]] = []

    async def fake(**kwargs: object) -> LiveQueryHistoryResponse:
        calls.append(kwargs)
        return LiveQueryHistoryResponse(
            connection_id=CONNECTION_ID,
            workspace_id=WORKSPACE_ID,
            workspace_url="https://example.invalid",
            status=CategoryDiscoveryStatus.AVAILABLE,
            discovery_state=state,
            retrieved_at=_NOW,
            records=records or [],
            total_returned=len(records or []),
            has_next_page=has_next_page,
            next_page_token=next_page_token,
            error_message=error_message if state != DatabricksResourceState.LIVE else None,
        )

    service.workspace_service.get_query_history = fake  # type: ignore[method-assign,assignment]
    return calls
