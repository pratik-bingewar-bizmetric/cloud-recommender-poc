"""FastAPI endpoints for the 15-module FinOps Command Center.

Provides certified REST endpoints for Azure Databricks FinOps analytics,
KPI cards, charts, ledgers, scenario simulator, and CSV reports.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from cloud_recommender.core.auth import AuthenticatedUser, get_current_user
from cloud_recommender.core.config import Settings, get_settings
from cloud_recommender.schemas.billing_ingestion import (
    BillingApprovalTokenRequest,
    BillingApprovalTokenResponse,
    BillingIngestionRunResponse,
    BillingIngestionStatusResponse,
    BillingPriceEnvelope,
    BillingPriceRecord,
    BillingReconciliationResponse,
    BillingSummaryResponse,
    BillingUsageEnvelope,
    BillingUsageRecord,
    IngestionPreviewResponse,
    IngestionRunCreateRequest,
    IngestionValidateResponse,
)
from cloud_recommender.schemas.finops import (
    AiEconomicsResponse,
    AnomalyDetectionResponse,
    AnomalyStatusUpdateRequest,
    CanonicalKpiResponse,
    ComputeWarehousesResponse,
    CostAllocationResponse,
    CostExplorerResponse,
    DataStorageResponse,
    DecisionItem,
    ExecutiveOverviewResponse,
    FinOpsAiAnalysis,
    ForecastBudgetsResponse,
    GovernancePoliciesResponse,
    NetworkCloudResponse,
    OptimizationAdvisorResponse,
    QueryHistoryResponse,
    RecommendationActionRequest,
    ReportsAuditResponse,
    ScenarioSimulationRequest,
    ScenarioSimulationResponse,
    SettingsIntegrationsResponse,
    ShowbackChargebackResponse,
    SystemTablesExplorerResponse,
    WorkloadEconomicsResponse,
)
from cloud_recommender.services.databricks.billing_ingestion_service import (
    BillingIngestionService,
)
from cloud_recommender.services.databricks.finops_analytics_service import FinOpsAnalyticsService
from cloud_recommender.services.databricks.refresher import get_refresher
from cloud_recommender.services.databricks.sql_client import ApprovalLedgerError, LedgerHandle

logger = structlog.get_logger(__name__)

_FIRST_LOAD_TIMEOUT_SECONDS = 25

# Shared service singletons
_service_instance: FinOpsAnalyticsService | None = None
_billing_service_instance: BillingIngestionService | None = None


def get_finops_service() -> FinOpsAnalyticsService:
    global _service_instance
    if _service_instance is None:
        _service_instance = FinOpsAnalyticsService(billing_service=get_billing_service())
    return _service_instance


def get_billing_service() -> BillingIngestionService:
    global _billing_service_instance
    if _billing_service_instance is None:
        _billing_service_instance = BillingIngestionService()
    return _billing_service_instance


async def get_billing_ledger(
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[LedgerHandle | None, None]:
    """Durable approval-token ledger handle (AsyncSession + owning loop).

    Offline/mock/testing runs return ``None`` and keep the in-memory single-use set. In every
    other mode the handle is mandatory for live execution; if PostgreSQL (or the migrated
    ``billing_approval_tokens`` table) is unavailable, token operations fail closed.
    """
    if settings.databricks_auth_type == "mock" or settings.app_env == "testing":
        yield None
        return
    from cloud_recommender.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield LedgerHandle(session=session, loop=asyncio.get_running_loop())


def _as_ledger(value: Any) -> LedgerHandle | None:
    """Normalise a dependency value (a Depends object when the route is called directly)."""
    return value if isinstance(value, LedgerHandle) else None


async def warm_live_metadata(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    settings: Settings = Depends(get_settings),
) -> None:
    """Keep live inventory caches warm without blocking dashboard requests.

    The background refresher owns periodic refresh. A request only waits (bounded) when no
    inventory has ever been cached; slow Unity Catalog / system-table metadata is scheduled
    in the background. Read-only REST only: no SQL, no compute start.
    Skipped under the testing environment so the suite stays offline.
    """
    if settings.app_env == "testing":
        return
    refresher = get_refresher(get_finops_service().workspace_service)
    refresher.touch(connection_id)
    ws = refresher.workspace_service
    cid = connection_id
    try:
        if not ws._discovery_cache.get(cid):
            await asyncio.wait_for(
                ws.get_or_discover_workspace(cid), timeout=_FIRST_LOAD_TIMEOUT_SECONDS
            )
        if cid not in ws._uc_cache or cid not in ws._system_tables_cache:
            asyncio.create_task(refresher.refresh_once(cid, force=True))
    except TimeoutError:
        logger.info("finops_first_load_still_running", connection_id=cid)
        asyncio.create_task(refresher.refresh_once(cid, force=True))
    except Exception as exc:  # noqa: BLE001 - never fail a dashboard request on warm-up
        logger.warning("finops_live_metadata_warmup_failed", error=type(exc).__name__)


router = APIRouter(
    prefix="/finops", tags=["FinOps Command Center"], dependencies=[Depends(warm_live_metadata)]
)


@router.get("/overview", response_model=ExecutiveOverviewResponse)
def get_overview(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    period: str = Query("month", description="Period: month, last, quarter"),
    environment: str | None = Query(None, description="Environment filter"),
    workspace_id: str | None = Query(None, description="Databricks workspace ID filter"),
    resource_id: str | None = Query(None, description="Child resource ID filter"),
    resource_type: str | None = Query(None, description="Child resource type filter"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> ExecutiveOverviewResponse:
    """Get Executive Cost Overview KPIs, spend trend, composition, cost drivers and decisions with scope enforcement."""
    try:
        return service.get_executive_overview(
            connection_id=connection_id,
            period=period,
            environment=environment,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# =============================================================================
@router.get("/cost-explorer", response_model=CostExplorerResponse)
def get_cost_explorer(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Databricks workspace ID filter"),
    resource_id: str | None = Query(None, description="Child resource ID filter"),
    resource_type: str | None = Query(None, description="Child resource type filter"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> CostExplorerResponse:
    """Get Cost Explorer KPIs, daily trend, product family share and detailed billing ledger with scope enforcement."""
    try:
        return service.get_cost_explorer(
            connection_id=connection_id,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# =============================================================================
@router.get("/query-history", response_model=QueryHistoryResponse)
async def get_query_history(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID filter"),
    warehouse_id: str | None = Query(None, description="Warehouse ID filter"),
    user: str | None = Query(None, description="User filter (applied to the returned page)"),
    execution_status: str | None = Query(
        None, alias="status", description="Status filter: FINISHED, FAILED, CANCELED"
    ),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    page_token: str | None = Query(None, description="Opaque token from a previous page"),
    start_time_ms: int | None = Query(None, ge=0, description="Window start (epoch ms)"),
    end_time_ms: int | None = Query(None, ge=0, description="Window end (epoch ms)"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> QueryHistoryResponse:
    """Live, paginated query history from the Databricks Query History REST API (no SQL executed)."""
    try:
        return await service.get_query_history(
            connection_id=connection_id,
            workspace_id=workspace_id,
            warehouse_id=warehouse_id,
            user=user,
            status=execution_status,
            limit=limit,
            page_token=page_token,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# =============================================================================
@router.get("/system-tables", response_model=SystemTablesExplorerResponse)
def get_system_tables(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID filter"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> SystemTablesExplorerResponse:
    """Inspect the 10 System Tables with verified catalog schemas and stopped warehouse probe."""
    try:
        return service.get_system_tables(
            connection_id=connection_id,
            workspace_id=workspace_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# =============================================================================
@router.get("/cost-explorer/csv")
def export_cost_explorer_csv(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> Response:
    """Export the current Cost Explorer billing ledger as an actual CSV file."""
    csv_content = service.export_cost_ledger_csv(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="finops-cost-explorer.csv"'},
    )


@router.get("/cost-allocation", response_model=CostAllocationResponse)
def get_cost_allocation(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> CostAllocationResponse:
    """Get Cost Allocation KPIs, business unit breakdown, completeness meters and rulebook."""
    return service.get_cost_allocation(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.get("/compute-warehouses", response_model=ComputeWarehousesResponse)
def get_compute_warehouses(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> ComputeWarehousesResponse:
    """Get Compute & Warehouses module with live clusters, SQL warehouses, and 168-hr heatmap."""
    return service.get_compute_warehouses(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.get("/ai-economics", response_model=AiEconomicsResponse)
def get_ai_economics(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> AiEconomicsResponse:
    """Get AI & Token Economics module with live model serving endpoints, Genie, and agents."""
    return service.get_ai_economics(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.get("/data-storage", response_model=DataStorageResponse)
def get_data_storage(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> DataStorageResponse:
    """Get Data & Storage module with live Unity Catalog tables and storage tiers."""
    return service.get_data_storage(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.get("/network-cloud", response_model=NetworkCloudResponse)
def get_network_cloud(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> NetworkCloudResponse:
    """Get Network & Cloud Infrastructure module (Azure only)."""
    return service.get_network_cloud(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.get("/optimization-advisor", response_model=OptimizationAdvisorResponse)
def get_optimization_advisor(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> OptimizationAdvisorResponse:
    """Get Optimization Advisor recommendations and savings summary."""
    return service.get_optimization_advisor(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.post("/optimization-advisor/{decision_id}/action", response_model=DecisionItem)
def record_decision_action(
    decision_id: str,
    req: RecommendationActionRequest,
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> DecisionItem:
    """Record an action (Approved, Deferred) on a recommendation with audit tracking."""
    return service.record_decision_action(
        decision_id=decision_id, action=req.action, notes=req.notes
    )


@router.get("/forecast-budgets", response_model=ForecastBudgetsResponse)
def get_forecast_budgets(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> ForecastBudgetsResponse:
    """Get Forecast & Budgets module with burn pace and scenario baseline."""
    return service.get_forecast_budgets(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.post("/forecast-budgets/simulate", response_model=ScenarioSimulationResponse)
def simulate_scenario(
    req: ScenarioSimulationRequest,
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> ScenarioSimulationResponse:
    """Simulate month-end spend based on compute, token, and growth adjustments."""
    return service.simulate_forecast_scenario(req=req)


@router.get("/anomaly-detection", response_model=AnomalyDetectionResponse)
def get_anomaly_detection(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> AnomalyDetectionResponse:
    """Get Anomaly Detection queue, severity signals and investigation evidence."""
    return service.get_anomaly_detection(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.post("/anomalies/{anomaly_id}/status")
def update_finops_anomaly_status(
    anomaly_id: str,
    payload: AnomalyStatusUpdateRequest,
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> dict[str, Any]:
    """Update anomaly investigation lifecycle status with audit tracking."""
    try:
        return service.update_anomaly_status(
            anomaly_id=anomaly_id,
            new_status=payload.status,
            actor="finops.operator",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/governance-policies", response_model=GovernancePoliciesResponse)
def get_governance_policies(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> GovernancePoliciesResponse:
    """Get Governance & Policies catalogue, checklist and approval steps."""
    return service.get_governance_policies(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.get("/showback-chargeback", response_model=ShowbackChargebackResponse)
def get_showback_chargeback(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> ShowbackChargebackResponse:
    """Get Showback & Chargeback business unit statements."""
    return service.get_showback_chargeback(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.get("/workload-economics", response_model=WorkloadEconomicsResponse)
def get_workload_economics(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> WorkloadEconomicsResponse:
    """Get Workload Economics unit costs across pipelines, apps and GenAI."""
    return service.get_workload_economics(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.get("/reports-audit", response_model=ReportsAuditResponse)
def get_reports_audit(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> ReportsAuditResponse:
    """Get Reports & Audit packs and operational change event log."""
    return service.get_reports_audit(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.get("/settings-integrations", response_model=SettingsIntegrationsResponse)
def get_settings_integrations(
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> SettingsIntegrationsResponse:
    """Get Settings & Integrations status, System Tables readiness, and commercial rate card."""
    return service.get_settings_integrations(
        connection_id=connection_id,
        workspace_id=workspace_id,
        resource_id=resource_id,
        resource_type=resource_type,
    )


@router.get("/kpis/{metric_id}", response_model=CanonicalKpiResponse)
def get_canonical_kpi(
    metric_id: str,
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str | None = Query(None, description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> CanonicalKpiResponse:
    """Fetch a certified canonical KPI metric with exact lineage, formula, and caveats."""
    try:
        return service.get_canonical_kpi(
            metric_id=metric_id,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
            connection_id=connection_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/ai-analysis/{module_id}", response_model=FinOpsAiAnalysis)
def get_finops_ai_analysis(
    module_id: str,
    connection_id: str = Query("databricks-azure-dev", description="Connection identifier"),
    workspace_id: str = Query("642006393507276", description="Workspace ID"),
    resource_id: str | None = Query(None, description="Resource ID"),
    resource_type: str | None = Query(None, description="Resource type"),
    service: FinOpsAnalyticsService = Depends(get_finops_service),
) -> FinOpsAiAnalysis:
    """Retrieve structured, evidence-grounded AI analysis and optimization intelligence for any FinOps module."""
    try:
        return service.get_module_ai_analysis(
            module_id=module_id,
            workspace_id=workspace_id,
            resource_id=resource_id,
            resource_type=resource_type,
            connection_id=connection_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# =============================================================================
# Milestone 3H: Live Databricks Financial Ingestion & Reconciliation Endpoints
# =============================================================================


@router.get("/ingestion/status", response_model=BillingIngestionStatusResponse)
def get_ingestion_status(
    workspace_id: str = Query("642006393507276", description="Target workspace ID"),
    service: BillingIngestionService = Depends(get_billing_service),
) -> BillingIngestionStatusResponse:
    """Fetch live status of the Databricks billing ingestion pipeline and warehouse readiness."""
    return service.get_ingestion_status(workspace_id=workspace_id)


@router.get("/ingestion/runs", response_model=list[BillingIngestionRunResponse])
def get_ingestion_runs(
    workspace_id: str = Query("642006393507276", description="Target workspace ID"),
    service: BillingIngestionService = Depends(get_billing_service),
) -> list[BillingIngestionRunResponse]:
    """Fetch historical audit log of ingestion run attempts."""
    return service.get_ingestion_runs(workspace_id=workspace_id)


@router.post("/ingestion/validate", response_model=IngestionValidateResponse)
def validate_ingestion(
    workspace_id: str = Query("642006393507276", description="Target workspace ID"),
    service: BillingIngestionService = Depends(get_billing_service),
) -> IngestionValidateResponse:
    """Validate ingestion parameters and warehouse accessibility without executing SQL."""
    return service.validate_ingestion(workspace_id=workspace_id)


def _param(val: Any, default: Any = None) -> Any:
    """Safely extract parameter value when endpoint is called directly as a function."""
    if hasattr(val, "default"):
        return default if val.default is None else val.default
    return val if val is not None else default


@router.post("/ingestion/preview", response_model=IngestionPreviewResponse)
def preview_ingestion(
    workspace_id: str = Query("642006393507276", description="Target workspace ID"),
    start_date: str | None = Query(
        None, description="Start date YYYY-MM-DD (default: first day of the current month)"
    ),
    end_date: str | None = Query(None, description="End date YYYY-MM-DD (default: today, UTC)"),
    limit: int = Query(50, ge=1, le=1000, description="Max preview records"),
    service: BillingIngestionService = Depends(get_billing_service),
) -> IngestionPreviewResponse:
    """Preview available billing records without starting the SQL warehouse."""
    return service.preview_ingestion(
        workspace_id=_param(workspace_id, "642006393507276"),
        start_date=_param(start_date, None),
        end_date=_param(end_date, None),
        limit=_param(limit, 50),
    )


@router.post("/ingestion/run", response_model=BillingIngestionRunResponse)
def execute_ingestion_run(
    request: IngestionRunCreateRequest,
    service: BillingIngestionService = Depends(get_billing_service),
    ledger: Any = Depends(get_billing_ledger),
) -> BillingIngestionRunResponse:
    """Attempt an ingestion execution run. Gated by strict Human Approval policy."""
    return service.run_ingestion(request, ledger=_as_ledger(ledger))


@router.post("/ingestion/approval-token", response_model=BillingApprovalTokenResponse)
def issue_approval_token(
    request: BillingApprovalTokenRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    service: BillingIngestionService = Depends(get_billing_service),
    ledger: Any = Depends(get_billing_ledger),
) -> BillingApprovalTokenResponse:
    """Issue a cryptographically signed, role-authorized approval token for live execution."""
    import base64
    import hashlib
    import json
    from datetime import UTC, datetime

    # If invoked directly in test harnesses without FastAPI dependency injection:
    if not isinstance(current_user, AuthenticatedUser):
        if request.approver_roles is not None:
            current_user = AuthenticatedUser(
                sub=request.approver_sub or "test-user",
                preferred_username=request.approver_sub or "test-user@local.internal",
                roles=request.approver_roles,
                is_authenticated=True,
            )
        else:
            current_user = get_current_user()

    # 1. Enforce authentication
    if not current_user or not getattr(current_user, "is_authenticated", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "UNAUTHENTICATED",
                "message": "Authentication is required to request approval tokens.",
            },
        )

    # 2. Enforce RBAC
    allowed_roles = {"Admin", "FinOpsAdministrator", "PlatformAdministrator"}
    caller_roles = getattr(current_user, "roles", []) or []
    if not any(r in allowed_roles for r in caller_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "INSUFFICIENT_PERMISSIONS",
                "message": (
                    f"Caller lacks required roles to issue approval tokens. "
                    f"Required one of: {sorted(allowed_roles)}. Assigned roles: {caller_roles}."
                ),
            },
        )

    # 3. Server-derived identity: strictly ignore or reject client spoofing
    approver_sub = (
        getattr(current_user, "preferred_username", None)
        or getattr(current_user, "sub", None)
        or "authenticated-operator"
    )
    approver_roles = caller_roles

    try:
        token = service.sql_service.issue_approval_token(
            query=request.query,
            warehouse_id=request.warehouse_id,
            start_date=request.start_date,
            end_date=request.end_date,
            ttl_seconds=request.ttl_seconds,
            approver_sub=approver_sub,
            approver_roles=approver_roles,
            max_rows=request.max_rows,
            approval_purpose=request.approval_purpose,
            session=_as_ledger(ledger),
        )

        if token.startswith("v2:"):
            parts = token.split(":")
            kid = parts[1]
            b64_p = parts[2]
            pad = -len(b64_p) % 4
            p_dict = json.loads(base64.urlsafe_b64decode(b64_p + ("=" * pad)).decode("utf-8"))
            return BillingApprovalTokenResponse(
                token=token,
                token_id=p_dict.get("token_id", "tok-unknown"),
                kid=kid,
                approver_sub=approver_sub,
                approver_roles=approver_roles,
                workspace_id=request.workspace_id,
                warehouse_id=request.warehouse_id,
                query_hash=p_dict.get("query_hash", ""),
                max_rows=p_dict.get("max_rows", request.max_rows),
                approval_purpose=request.approval_purpose,
                expires_at=p_dict.get("expires_at", datetime.now(UTC).isoformat()),
                status="ISSUED",
            )
        else:
            parts = token.split(":")
            nonce = parts[4] if len(parts) == 7 else "token"
            sig = parts[6] if len(parts) == 7 else parts[3]
            qhash = hashlib.sha256(request.query.strip().encode()).hexdigest()
            exp_ts = int(parts[5]) if len(parts) == 7 else int(parts[2])
            exp_iso = datetime.fromtimestamp(exp_ts, UTC).isoformat()
            return BillingApprovalTokenResponse(
                token=token,
                token_id=f"tok-{nonce}-{sig[:16]}",
                kid="k1-2026",
                approver_sub=approver_sub,
                approver_roles=approver_roles,
                workspace_id=request.workspace_id,
                warehouse_id=request.warehouse_id,
                query_hash=qhash,
                max_rows=request.max_rows,
                approval_purpose=request.approval_purpose,
                expires_at=exp_iso,
                status="ISSUED",
            )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe)) from pe
    except ApprovalLedgerError as le:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "APPROVAL_LEDGER_UNAVAILABLE", "message": str(le)},
        ) from le
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/billing/summary", response_model=BillingSummaryResponse)
def get_billing_summary(
    workspace_id: str = Query("642006393507276", description="Target workspace ID"),
    resource_id: str | None = Query(None, description="Exact resource ID filter"),
    resource_type: str | None = Query(None, description="Resource type filter"),
    service: BillingIngestionService = Depends(get_billing_service),
) -> BillingSummaryResponse:
    """Retrieve canonical DBU consumption and spend summary with exact scope filtering."""
    return service.get_billing_summary(
        workspace_id=_param(workspace_id, "642006393507276"),
        resource_id=_param(resource_id, None),
        resource_type=_param(resource_type, None),
    )


@router.get("/billing/usage", response_model=BillingUsageEnvelope | list[BillingUsageRecord])
def get_billing_usage(
    workspace_id: str = Query("642006393507276", description="Target workspace ID"),
    sku_name: str | None = Query(None, description="Filter by SKU name"),
    product: str | None = Query(None, description="Filter by product family"),
    resource_id: str | None = Query(None, description="Filter by exact resource ID"),
    start_date: str | None = Query(None, description="Start date filter"),
    end_date: str | None = Query(None, description="End date filter"),
    limit: int | None = Query(None, description="Maximum number of records to return"),
    offset: int = Query(0, description="Offset for pagination"),
    record_type: str | None = Query(None, description="Filter by record_type"),
    envelope: bool = Query(
        False, description="Return {total, offset, limit, records} instead of a bare list"
    ),
    service: BillingIngestionService = Depends(get_billing_service),
) -> BillingUsageEnvelope | list[BillingUsageRecord]:
    """List normalized billing usage events with parameter filtering.

    Default response is the legacy bare list. ``envelope=true`` returns the paginated envelope
    the frontend contract expects (``total`` is the pre-pagination match count).
    """
    matches = service.list_usage_records(
        workspace_id=_param(workspace_id, "642006393507276"),
        sku_name=_param(sku_name, None),
        product=_param(product, None),
        resource_id=_param(resource_id, None),
        start_date=_param(start_date, None),
        end_date=_param(end_date, None),
    )
    rtype = _param(record_type, None)
    if rtype:
        matches = [m for m in matches if m.record_type.lower() == str(rtype).lower()]
    off = max(int(_param(offset, 0)), 0)
    lim = _param(limit, None)
    page = matches[off:] if lim is None else matches[off : off + int(lim)]
    if _param(envelope, False) is True:
        return BillingUsageEnvelope(
            total=len(matches),
            offset=off,
            limit=len(page) if lim is None else int(lim),
            records=page,
        )
    return page


@router.get("/billing/pricing", response_model=BillingPriceEnvelope | list[BillingPriceRecord])
def get_billing_pricing(
    sku_name: str | None = Query(None, description="Filter by SKU name"),
    limit: int | None = Query(None, ge=1, description="Maximum number of records to return"),
    envelope: bool = Query(False, description="Return {total, records} instead of a bare list"),
    service: BillingIngestionService = Depends(get_billing_service),
) -> BillingPriceEnvelope | list[BillingPriceRecord]:
    """List the ingested rate card (empty until an approved list_prices ingestion)."""
    prices = service.list_price_records()
    sku = _param(sku_name, None)
    if sku:
        prices = [p for p in prices if p.sku_name.upper() == str(sku).upper()]
    total = len(prices)
    lim = _param(limit, None)
    if lim is not None:
        prices = prices[: int(lim)]
    if _param(envelope, False) is True:
        return BillingPriceEnvelope(total=total, records=prices)
    return prices


@router.get("/billing/reconciliation", response_model=BillingReconciliationResponse)
def get_billing_reconciliation(
    workspace_id: str = Query("642006393507276", description="Target workspace ID"),
    service: BillingIngestionService = Depends(get_billing_service),
) -> BillingReconciliationResponse:
    """Retrieve mathematical reconciliation between usage records, list prices, and retractions."""
    return service.get_billing_reconciliation(workspace_id=workspace_id)
