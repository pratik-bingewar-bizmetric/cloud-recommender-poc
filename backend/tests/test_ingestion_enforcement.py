"""Comprehensive test suite for Phase 2C Scope-Aware Ingestion and Configuration Enforcement.

Validates:
- Deterministic effective scope calculation with parent-child cascade and explicit exclusions.
- Partial resource-group selection and individual resource inclusion.
- Multiple subscriptions and multiple projects support.
- Databricks workspace extraction and scope restriction.
- Pre-flight readiness validation across all states (READY, NOT_CONFIGURED, NO_RESOURCES_SELECTED, PERMISSION_DENIED, etc.).
- Provider ingestion interfaces (Azure, Databricks, GCP, AWS).
- Configuration version lineage (v1 records preserved when v2 is active).
- Ingestion execution, duplicate protection, partial failure resilience, and retries.
- FastAPI /api/v1/ingestion/* lifecycle endpoints.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from cloud_recommender.schemas.configuration import (
    ConfiguredScopeItemCreate,
    ResourceConfigurationResponse,
    ScopeType,
    SelectionState,
)
from cloud_recommender.schemas.connections import ConnectionValidationResponse
from cloud_recommender.schemas.ingestion import (
    IngestionReadinessState,
    IngestionRunStatus,
    IngestionScope,
    ResourceIngestionStatus,
)
from cloud_recommender.services.configuration.configuration_service import (
    ConfigurationService,
)
from cloud_recommender.services.ingestion.ingestion_orchestrator import (
    IngestionConflictError,
    IngestionOrchestrator,
)
from cloud_recommender.services.ingestion.providers.aws import AwsProviderIngestor
from cloud_recommender.services.ingestion.providers.azure import AzureProviderIngestor
from cloud_recommender.services.ingestion.providers.databricks import (
    DatabricksWorkspaceIngestor,
)
from cloud_recommender.services.ingestion.providers.gcp import GcpProviderIngestor
from cloud_recommender.services.ingestion.readiness_service import (
    IngestionReadinessService,
)
from cloud_recommender.services.ingestion.scope_service import ScopeEnforcementService

# ---------------------------------------------------------------------------
# Workstream 2: Scope Enforcement & Calculation Tests
# ---------------------------------------------------------------------------


def test_scope_calculation_parent_child_and_partial_exclusion() -> None:
    """Verify parent 'all_children' includes children, but child with 'excluded' is strictly omitted."""
    scope_service = ScopeEnforcementService()

    rg_id = "/subscriptions/sub-1/resourceGroups/rg-prod"
    res1_id = f"{rg_id}/providers/Microsoft.Compute/virtualMachines/vm-app"
    res2_id = f"{rg_id}/providers/Microsoft.Storage/storageAccounts/stdata"
    res3_id = f"{rg_id}/providers/Microsoft.Sql/servers/sql-prod"

    config = ResourceConfigurationResponse(
        configuration_id=uuid.uuid4(),
        connection_id="test-conn-partial",
        provider="azure",
        configuration_version=1,
        active_status="active",
        created_by="tester",
        created_at="2026-11-06T00:00:00Z",  # type: ignore[arg-type]
        updated_at="2026-11-06T00:00:00Z",  # type: ignore[arg-type]
        scope_items=[
            {
                "item_id": uuid.uuid4(),
                "configuration_id": uuid.uuid4(),
                "scope_type": ScopeType.RESOURCE_GROUP.value,
                "scope_identifier": rg_id,
                "display_name": "rg-prod",
                "selection_state": SelectionState.ALL_CHILDREN.value,
                "metadata": {},
                "created_at": "2026-11-06T00:00:00Z",
                "updated_at": "2026-11-06T00:00:00Z",
            },
            {
                "item_id": uuid.uuid4(),
                "configuration_id": uuid.uuid4(),
                "scope_type": ScopeType.RESOURCE.value,
                "scope_identifier": res1_id,
                "parent_scope_identifier": rg_id,
                "display_name": "vm-app",
                "selection_state": SelectionState.INCLUDED.value,
                "metadata": {},
                "created_at": "2026-11-06T00:00:00Z",
                "updated_at": "2026-11-06T00:00:00Z",
            },
            {
                "item_id": uuid.uuid4(),
                "configuration_id": uuid.uuid4(),
                "scope_type": ScopeType.RESOURCE.value,
                "scope_identifier": res2_id,
                "parent_scope_identifier": rg_id,
                "display_name": "stdata",
                "selection_state": SelectionState.EXCLUDED.value,  # Deselected!
                "metadata": {},
                "created_at": "2026-11-06T00:00:00Z",
                "updated_at": "2026-11-06T00:00:00Z",
            },
            {
                "item_id": uuid.uuid4(),
                "configuration_id": uuid.uuid4(),
                "scope_type": ScopeType.RESOURCE.value,
                "scope_identifier": res3_id,
                "parent_scope_identifier": rg_id,
                "display_name": "sql-prod",
                "selection_state": SelectionState.INCLUDED.value,
                "metadata": {},
                "created_at": "2026-11-06T00:00:00Z",
                "updated_at": "2026-11-06T00:00:00Z",
            },
        ],  # type: ignore[arg-type]
        total_items=4,
    )

    scope = scope_service.resolve_scope_from_config(config)

    assert res1_id in scope.effective_resource_ids
    assert res3_id in scope.effective_resource_ids
    # Crucial test: Deselected resource is strictly omitted
    assert res2_id not in scope.effective_resource_ids
    assert len(scope.effective_resource_ids) == 2


def test_scope_calculation_individual_resource_selection() -> None:
    """Verify an individual resource with 'included' is retained even if parent container was unselected."""
    scope_service = ScopeEnforcementService()

    rg_unselected = "/subscriptions/sub-1/resourceGroups/rg-unselected"
    res_included = f"{rg_unselected}/providers/Microsoft.Compute/virtualMachines/vm-standalone"

    config = ResourceConfigurationResponse(
        configuration_id=uuid.uuid4(),
        connection_id="test-conn-ind",
        provider="azure",
        configuration_version=1,
        active_status="active",
        created_by="tester",
        created_at="2026-11-06T00:00:00Z",  # type: ignore[arg-type]
        updated_at="2026-11-06T00:00:00Z",  # type: ignore[arg-type]
        scope_items=[
            {
                "item_id": uuid.uuid4(),
                "configuration_id": uuid.uuid4(),
                "scope_type": ScopeType.RESOURCE.value,
                "scope_identifier": res_included,
                "parent_scope_identifier": rg_unselected,
                "display_name": "vm-standalone",
                "selection_state": SelectionState.INCLUDED.value,
                "metadata": {},
                "created_at": "2026-11-06T00:00:00Z",
                "updated_at": "2026-11-06T00:00:00Z",
            }
        ],  # type: ignore[arg-type]
        total_items=1,
    )

    scope = scope_service.resolve_scope_from_config(config)
    assert res_included in scope.effective_resource_ids
    assert len(scope.effective_resource_ids) == 1


def test_scope_calculation_multiple_subscriptions_and_projects() -> None:
    """Verify scope resolution spanning multiple subscriptions and Databricks workspaces."""
    scope_service = ScopeEnforcementService()

    sub1_res = (
        "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-1"
    )
    sub2_adb = "/subscriptions/sub-2/resourceGroups/rg-2/providers/Microsoft.Databricks/workspaces/adb-ws-prod"

    config = ResourceConfigurationResponse(
        configuration_id=uuid.uuid4(),
        connection_id="test-conn-multi-sub",
        provider="azure",
        configuration_version=1,
        active_status="active",
        created_by="tester",
        created_at="2026-11-06T00:00:00Z",  # type: ignore[arg-type]
        updated_at="2026-11-06T00:00:00Z",  # type: ignore[arg-type]
        scope_items=[
            {
                "item_id": uuid.uuid4(),
                "configuration_id": uuid.uuid4(),
                "scope_type": ScopeType.SUBSCRIPTION.value,
                "scope_identifier": "/subscriptions/sub-1",
                "display_name": "Subscription 1",
                "selection_state": SelectionState.INCLUDED.value,
                "metadata": {},
                "created_at": "2026-11-06T00:00:00Z",
                "updated_at": "2026-11-06T00:00:00Z",
            },
            {
                "item_id": uuid.uuid4(),
                "configuration_id": uuid.uuid4(),
                "scope_type": ScopeType.SUBSCRIPTION.value,
                "scope_identifier": "/subscriptions/sub-2",
                "display_name": "Subscription 2",
                "selection_state": SelectionState.INCLUDED.value,
                "metadata": {},
                "created_at": "2026-11-06T00:00:00Z",
                "updated_at": "2026-11-06T00:00:00Z",
            },
            {
                "item_id": uuid.uuid4(),
                "configuration_id": uuid.uuid4(),
                "scope_type": ScopeType.RESOURCE.value,
                "scope_identifier": sub1_res,
                "parent_scope_identifier": "/subscriptions/sub-1/resourceGroups/rg-1",
                "display_name": "vm-1",
                "selection_state": SelectionState.INCLUDED.value,
                "metadata": {},
                "created_at": "2026-11-06T00:00:00Z",
                "updated_at": "2026-11-06T00:00:00Z",
            },
            {
                "item_id": uuid.uuid4(),
                "configuration_id": uuid.uuid4(),
                "scope_type": ScopeType.DATABRICKS_WORKSPACE.value,
                "scope_identifier": sub2_adb,
                "parent_scope_identifier": "/subscriptions/sub-2/resourceGroups/rg-2",
                "display_name": "adb-ws-prod",
                "selection_state": SelectionState.INCLUDED.value,
                "metadata": {"workspace_url": "adb-prod.azuredatabricks.net"},
                "created_at": "2026-11-06T00:00:00Z",
                "updated_at": "2026-11-06T00:00:00Z",
            },
        ],  # type: ignore[arg-type]
        total_items=4,
    )

    scope = scope_service.resolve_scope_from_config(config)
    assert len(scope.subscriptions) == 2
    assert "/subscriptions/sub-1" in scope.subscriptions
    assert "/subscriptions/sub-2" in scope.subscriptions
    assert sub1_res in scope.effective_resource_ids
    assert sub2_adb in scope.effective_resource_ids
    assert sub2_adb in scope.effective_workspace_ids


def test_server_side_scope_record_filtering() -> None:
    """Verify unauthorized records outside scope are strictly rejected server-side."""
    scope = IngestionScope(
        connection_id="conn-sec",
        provider="azure",
        configuration_id=uuid.uuid4(),
        configuration_version=1,
        effective_resource_ids=["/res/allowed-1", "/res/allowed-2"],
        effective_workspace_ids=[],
        subscriptions=[],
        resource_groups=[],
    )

    raw_records = [
        {"id": "/res/allowed-1", "cost": 10.0},
        {"id": "/res/forbidden-victim", "cost": 999.0},
        {"id": "/res/allowed-2", "cost": 20.0},
        {"id": "/res/random-tenant-leak", "cost": 500.0},
    ]

    filtered = ScopeEnforcementService.filter_records_by_scope(
        raw_records, resource_id_field="id", scope=scope
    )

    assert len(filtered) == 2
    assert filtered[0]["id"] == "/res/allowed-1"
    assert filtered[1]["id"] == "/res/allowed-2"


# ---------------------------------------------------------------------------
# Workstream 1: Ingestion Readiness Service Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readiness_not_configured() -> None:
    """Connection without saved configuration returns NOT_CONFIGURED state."""
    config_service = ConfigurationService()
    readiness_service = IngestionReadinessService(config_service=config_service)

    resp = await readiness_service.validate_readiness("unconfigured-conn-xyz")
    assert resp.readiness_state == IngestionReadinessState.NOT_CONFIGURED
    assert resp.can_start_ingestion is False
    assert "saved_configuration" in resp.missing_requirements


@pytest.mark.asyncio
async def test_readiness_no_resources_selected() -> None:
    """Configuration with 0 selected resources returns NO_RESOURCES_SELECTED."""
    conn_id = f"conn-empty-sel-{uuid.uuid4().hex[:6]}"
    config_service = ConfigurationService()

    # Save a configuration with only an unselected or empty item set
    item = ConfiguredScopeItemCreate(
        scope_type=ScopeType.RESOURCE.value,
        scope_identifier="/res/excluded-1",
        display_name="excluded-1",
        selection_state=SelectionState.EXCLUDED.value,
    )
    await config_service.save_configuration(conn_id, "azure", [item])

    readiness_service = IngestionReadinessService(config_service=config_service)
    resp = await readiness_service.validate_readiness(conn_id)

    assert resp.readiness_state == IngestionReadinessState.NO_RESOURCES_SELECTED
    assert resp.can_start_ingestion is False
    assert resp.selected_resource_count == 0


@pytest.mark.asyncio
async def test_readiness_permission_denied() -> None:
    """Connection probe returning HTTP 403 maps cleanly to PERMISSION_DENIED state."""
    conn_id = f"conn-perm-denied-{uuid.uuid4().hex[:6]}"
    config_service = ConfigurationService()

    item = ConfiguredScopeItemCreate(
        scope_type=ScopeType.RESOURCE.value,
        scope_identifier="/res/vm-perm",
        display_name="vm-perm",
        selection_state=SelectionState.INCLUDED.value,
    )
    await config_service.save_configuration(conn_id, "azure", [item])

    readiness_service = IngestionReadinessService(config_service=config_service)

    mock_validation = ConnectionValidationResponse(
        success=False,
        connection_id=conn_id,
        provider="azure",  # type: ignore[arg-type]
        scope_id="sub-denied",
        scope_name="sub-denied",
        status="permission_denied",
        details="Missing Reader role on subscription.",
        is_live=True,
    )

    with patch.object(
        readiness_service.connection_service,
        "validate_connection",
        new_callable=AsyncMock,
        return_value=mock_validation,
    ):
        resp = await readiness_service.validate_readiness(conn_id)
        assert resp.readiness_state == IngestionReadinessState.PERMISSION_DENIED
        assert resp.can_start_ingestion is False
        assert "azure_reader_role" in resp.missing_requirements


@pytest.mark.asyncio
async def test_readiness_ready_simulation() -> None:
    """Valid configuration with selected resources in simulation mode returns READY."""
    conn_id = f"conn-ready-{uuid.uuid4().hex[:6]}"
    config_service = ConfigurationService()

    item = ConfiguredScopeItemCreate(
        scope_type=ScopeType.DATABRICKS_WORKSPACE.value,
        scope_identifier="/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Databricks/workspaces/adb-ws",
        display_name="adb-ws",
        selection_state=SelectionState.INCLUDED.value,
        metadata={"workspace_url": "adb-ws.azuredatabricks.net"},
    )
    await config_service.save_configuration(conn_id, "azure", [item])

    readiness_service = IngestionReadinessService(config_service=config_service)
    resp = await readiness_service.validate_readiness(conn_id)

    assert resp.readiness_state == IngestionReadinessState.READY
    assert resp.can_start_ingestion is True
    assert resp.selected_resource_count == 1
    assert resp.selected_workspace_count == 1


# ---------------------------------------------------------------------------
# Workstream 3: Provider Ingestion Interface Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_azure_provider_ingestor_scoped_extraction() -> None:
    """AzureProviderIngestor extracts inventory, cost, and metrics for scoped resources."""
    ingestor = AzureProviderIngestor()
    scope = IngestionScope(
        connection_id="test-az-ingest",
        provider="azure",
        configuration_id=uuid.uuid4(),
        configuration_version=1,
        effective_resource_ids=[
            "/subscriptions/s1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm-1"
        ],
        effective_workspace_ids=[],
        subscriptions=[],
        resource_groups=[],
    )

    with patch.object(
        ingestor.azure_service,
        "get_access_token",
        new_callable=AsyncMock,
        return_value=(None, "none"),
    ):
        results = await ingestor.ingest_scope(scope)
        assert len(results) == 1
        res = results[0]
        assert res.status == ResourceIngestionStatus.SUCCESS
        assert res.inventory_extracted is True
        assert res.cost_extracted is True
        assert res.metrics_extracted is True
        assert len(res.cost_records) >= 1


@pytest.mark.asyncio
async def test_databricks_workspace_ingestor_contract() -> None:
    """DatabricksWorkspaceIngestor extracts workspace compute telemetry without assuming System Tables."""
    ingestor = DatabricksWorkspaceIngestor()
    ws_id = "/subscriptions/s1/resourceGroups/rg1/providers/Microsoft.Databricks/workspaces/adb-lakehouse"
    scope = IngestionScope(
        connection_id="test-db-ingest",
        provider="azure",
        configuration_id=uuid.uuid4(),
        configuration_version=1,
        effective_resource_ids=[ws_id],
        effective_workspace_ids=[ws_id],
        subscriptions=[],
        resource_groups=[],
    )

    results = await ingestor.ingest_scope(scope)
    assert len(results) == 1
    res = results[0]
    assert res.status == ResourceIngestionStatus.SUCCESS
    assert res.resource_type == "Microsoft.Databricks/workspaces"
    assert res.inventory_payload is not None
    assert res.inventory_payload["system_tables_status"] == "unverified_permissions_required"


@pytest.mark.asyncio
async def test_aws_provider_ingestor_honest_unsupported() -> None:
    """AwsProviderIngestor reports honest unsupported/skipped status for any scoped AWS resources."""
    ingestor = AwsProviderIngestor()
    scope = IngestionScope(
        connection_id="test-aws-ingest",
        provider="aws",
        configuration_id=uuid.uuid4(),
        configuration_version=1,
        effective_resource_ids=["arn:aws:ec2:us-east-1:123456789012:instance/i-1234"],
        effective_workspace_ids=[],
        subscriptions=[],
        resource_groups=[],
    )

    results = await ingestor.ingest_scope(scope)
    assert len(results) == 1
    assert results[0].status == ResourceIngestionStatus.SKIPPED
    assert "AWS provider is not configured" in (results[0].error_message or "")


@pytest.mark.asyncio
async def test_gcp_provider_ingestor_scoped_extraction() -> None:
    """GcpProviderIngestor extracts telemetry for scoped GCP assets."""
    ingestor = GcpProviderIngestor()
    scope = IngestionScope(
        connection_id="test-gcp-ingest",
        provider="gcp",
        configuration_id=uuid.uuid4(),
        configuration_version=1,
        effective_resource_ids=[
            "//compute.googleapis.com/projects/proj-1/zones/us-central1-a/instances/vm-gcp"
        ],
        effective_workspace_ids=[],
        subscriptions=[],
        resource_groups=[],
    )

    results = await ingestor.ingest_scope(scope)
    assert len(results) == 1
    assert results[0].status == ResourceIngestionStatus.SUCCESS
    assert results[0].region == "us-central1"


# ---------------------------------------------------------------------------
# Workstream 4, 5 & 6: Lineage, Orchestration, Duplicate Protection, and Retries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingestion_orchestration_lifecycle_and_version_lineage() -> None:
    """Verify end-to-end ingestion execution stamps active configuration version and preserves history."""
    conn_id = f"conn-lineage-{uuid.uuid4().hex[:6]}"
    config_service = ConfigurationService()

    # Step 1: Save Configuration Revision v1
    res1_id = (
        "/subscriptions/s1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm-v1"
    )
    item1 = ConfiguredScopeItemCreate(
        scope_type=ScopeType.RESOURCE.value,
        scope_identifier=res1_id,
        display_name="vm-v1",
        selection_state=SelectionState.INCLUDED.value,
    )
    v1_config = await config_service.save_configuration(conn_id, "azure", [item1])
    assert v1_config.configuration_version == 1

    orchestrator = IngestionOrchestrator(config_service=config_service)

    # Step 2: Trigger Ingestion Run under v1
    run1 = await orchestrator.trigger_ingestion(conn_id)
    assert run1.configuration_version == 1
    assert run1.status == IngestionRunStatus.COMPLETED
    assert run1.total_resources_scoped == 1
    assert run1.successful_resources_count == 1

    # Step 3: User modifies selection and saves Configuration Revision v2
    res2_id = (
        "/subscriptions/s1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm-v2"
    )
    item2 = ConfiguredScopeItemCreate(
        scope_type=ScopeType.RESOURCE.value,
        scope_identifier=res2_id,
        display_name="vm-v2",
        selection_state=SelectionState.INCLUDED.value,
    )
    v2_config = await config_service.save_configuration(conn_id, "azure", [item1, item2])
    assert v2_config.configuration_version == 2

    # Step 4: Trigger Ingestion Run under v2
    run2 = await orchestrator.trigger_ingestion(conn_id)
    assert run2.configuration_version == 2
    assert run2.total_resources_scoped == 2
    assert run2.successful_resources_count == 2

    # Step 5: Verify historical lineage: Run 1 retains v1, Run 2 retains v2
    history = await orchestrator.list_runs(conn_id)
    assert len(history) == 2
    # Latest run is run2 with v2
    assert history[0].run_id == run2.run_id
    assert history[0].configuration_version == 2
    # Historical run is run1 with v1
    assert history[1].run_id == run1.run_id
    assert history[1].configuration_version == 1


@pytest.mark.asyncio
async def test_duplicate_run_protection() -> None:
    """Starting an ingestion run while another run is actively running raises IngestionConflictError."""
    conn_id = f"conn-dup-{uuid.uuid4().hex[:6]}"
    config_service = ConfigurationService()

    item = ConfiguredScopeItemCreate(
        scope_type=ScopeType.RESOURCE.value,
        scope_identifier="/res/vm-dup",
        display_name="vm-dup",
        selection_state=SelectionState.INCLUDED.value,
    )
    await config_service.save_configuration(conn_id, "azure", [item])

    orchestrator = IngestionOrchestrator(config_service=config_service)

    # Simulate an active run in memory
    from cloud_recommender.schemas.ingestion import IngestionRunResponse

    active_run = IngestionRunResponse(
        run_id=uuid.uuid4(),
        connection_id=conn_id,
        provider="azure",
        configuration_id=uuid.uuid4(),
        configuration_version=1,
        status=IngestionRunStatus.RUNNING,
        triggered_by="tester",
        started_at="2026-11-06T00:00:00Z",  # type: ignore[arg-type]
        total_resources_scoped=1,
        successful_resources_count=0,
        failed_resources_count=0,
        scope_snapshot={},
        resource_statuses=[],
    )
    orchestrator._memory_runs[conn_id] = [active_run]

    with pytest.raises(IngestionConflictError):
        await orchestrator.trigger_ingestion(conn_id)


@pytest.mark.asyncio
async def test_partial_failure_handling_and_retry() -> None:
    """Safe handling of partial failures: one failing resource does not abort the whole run, and retry succeeds."""
    conn_id = f"conn-partial-{uuid.uuid4().hex[:6]}"
    config_service = ConfigurationService()

    res1 = "/res/vm-good"
    res2 = "/res/vm-bad"

    items = [
        ConfiguredScopeItemCreate(
            scope_type=ScopeType.RESOURCE.value,
            scope_identifier=res1,
            display_name="vm-good",
            selection_state=SelectionState.INCLUDED.value,
        ),
        ConfiguredScopeItemCreate(
            scope_type=ScopeType.RESOURCE.value,
            scope_identifier=res2,
            display_name="vm-bad",
            selection_state=SelectionState.INCLUDED.value,
        ),
    ]
    await config_service.save_configuration(conn_id, "azure", items)

    orchestrator = IngestionOrchestrator(config_service=config_service)

    # Mock Azure ingestor to fail only res2
    from cloud_recommender.services.ingestion.providers.base import (
        ResourceExtractionResult,
    )

    async def mock_extract(_scope: IngestionScope) -> list[ResourceExtractionResult]:
        return [
            ResourceExtractionResult(
                resource_id=res1,
                status=ResourceIngestionStatus.SUCCESS,
                inventory_extracted=True,
                cost_extracted=True,
                metrics_extracted=True,
            ),
            ResourceExtractionResult(
                resource_id=res2,
                status=ResourceIngestionStatus.FAILED,
                error_message="HTTP 404 Resource Not Found in Azure Tenant",
                inventory_extracted=False,
                cost_extracted=False,
                metrics_extracted=False,
            ),
        ]

    with patch.object(AzureProviderIngestor, "ingest_scope", side_effect=mock_extract):
        run = await orchestrator.trigger_ingestion(conn_id)
        assert run.status == IngestionRunStatus.PARTIAL_FAILURE
        assert run.successful_resources_count == 1
        assert run.failed_resources_count == 1
        assert "1 of 2 resources failed extraction" in (run.error_message or "")

        # Now test retry succeeds
        async def mock_retry_extract(_scope: IngestionScope) -> list[ResourceExtractionResult]:
            return [
                ResourceExtractionResult(
                    resource_id=res1,
                    status=ResourceIngestionStatus.SUCCESS,
                    inventory_extracted=True,
                    cost_extracted=True,
                    metrics_extracted=True,
                ),
                ResourceExtractionResult(
                    resource_id=res2,
                    status=ResourceIngestionStatus.SUCCESS,
                    inventory_extracted=True,
                    cost_extracted=True,
                    metrics_extracted=True,
                ),
            ]

        with patch.object(AzureProviderIngestor, "ingest_scope", side_effect=mock_retry_extract):
            retry_run = await orchestrator.retry_run(run.run_id)
            assert retry_run.status == IngestionRunStatus.COMPLETED
            assert retry_run.successful_resources_count == 2
            assert retry_run.failed_resources_count == 0


# ---------------------------------------------------------------------------
# FastAPI Endpoints Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fastapi_ingestion_endpoints_lifecycle(client: "AsyncClient") -> None:  # type: ignore[name-defined]
    """Verify FastAPI /api/v1/ingestion/* routes: readiness, trigger run, get run, list runs, retry."""
    conn_id = f"api-ingest-conn-{uuid.uuid4().hex[:6]}"

    with patch(
        "cloud_recommender.services.inventory.azure_inventory.AzureInventoryService.get_access_token",
        new_callable=AsyncMock,
        return_value=(None, "none"),
    ):
        # Step 1: Pre-flight check when NOT_CONFIGURED -> returns 200 with can_start_ingestion=False
        ready_resp = await client.get(f"/api/v1/ingestion/{conn_id}/readiness")
        assert ready_resp.status_code == 200
        ready_data = ready_resp.json()
        assert ready_data["readiness_state"] == "not_configured"
        assert ready_data["can_start_ingestion"] is False

        # Step 2: Triggering run while not ready returns 400 Bad Request
        fail_trigger = await client.post(f"/api/v1/ingestion/{conn_id}/runs")
        assert fail_trigger.status_code == 400
        assert "readiness checks failed" in str(fail_trigger.json())

        # Step 3: Save a valid configuration
        save_payload = {
            "connection_id": conn_id,
            "provider": "azure",
            "created_by": "api-tester",
            "scope_items": [
                {
                    "scope_type": "subscription",
                    "scope_identifier": "/subscriptions/sub-api-ingest",
                    "display_name": "API Ingest Sub",
                    "selection_state": "all_children",
                },
                {
                    "scope_type": "resource",
                    "scope_identifier": "/subscriptions/sub-api-ingest/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-api",
                    "parent_scope_identifier": "/subscriptions/sub-api-ingest/resourceGroups/rg-1",
                    "display_name": "vm-api",
                    "selection_state": "included",
                },
            ],
        }
        config_resp = await client.post("/api/v1/configuration", json=save_payload)
        assert config_resp.status_code == 200

        # Step 4: Pre-flight check now returns READY
        ready_resp2 = await client.get(f"/api/v1/ingestion/{conn_id}/readiness")
        assert ready_resp2.status_code == 200
        assert ready_resp2.json()["readiness_state"] == "ready"
        assert ready_resp2.json()["can_start_ingestion"] is True

        # Step 5: Trigger Ingestion Run -> returns 200 with IngestionRunResponse
        trigger_resp = await client.post(f"/api/v1/ingestion/{conn_id}/runs")
        assert trigger_resp.status_code == 200
        run_data = trigger_resp.json()
        assert run_data["status"] == "completed"
        assert run_data["configuration_version"] == 1
        assert run_data["total_resources_scoped"] == 1
        assert run_data["successful_resources_count"] == 1
        run_id = run_data["run_id"]

        # Step 6: Get Run details by run_id
        detail_resp = await client.get(f"/api/v1/ingestion/runs/{run_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["run_id"] == run_id

        # Step 7: List Ingestion Runs for connection
        list_resp = await client.get(f"/api/v1/ingestion/{conn_id}/runs")
        assert list_resp.status_code == 200
        runs_list = list_resp.json()
        assert len(runs_list) >= 1
        assert runs_list[0]["run_id"] == run_id

        # Step 8: Retrying a completed run returns 400 Bad Request
        retry_fail = await client.post(f"/api/v1/ingestion/runs/{run_id}/retry")
        assert retry_fail.status_code == 400
