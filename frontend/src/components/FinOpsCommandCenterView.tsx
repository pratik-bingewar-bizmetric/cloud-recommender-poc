"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  FinOpsModule,
  ExecutiveOverviewData,
  CostExplorerData,
  CostAllocationData,
  ComputeWarehousesData,
  AiEconomicsData,
  OptimizationAdvisorData,
  AnomalyDetectionData,
  SettingsIntegrationsData,
  DataStorageData,
  NetworkCloudData,
  ForecastBudgetsData,
  GovernancePoliciesData,
  ShowbackChargebackData,
  WorkloadEconomicsData,
  ReportsAuditData,
  ScenarioSimulationResult,
  BillingIngestionStatusResponse,
  BillingSummaryResponse,
  BillingUsageRecord,
  BillingReconciliationResponse,
  IngestionValidateResponse,
  BillingIngestionRunResponse,
  DatabricksConnection,
  DatabricksConnectionHealth,
} from "@/types";
import {
  getFinOpsOverview,
  getFinOpsCostExplorer,
  getFinOpsCostAllocation,
  getFinOpsComputeWarehouses,
  getFinOpsAiEconomics,
  getFinOpsDataStorage,
  getFinOpsNetworkCloud,
  getFinOpsOptimizationAdvisor,
  recordFinOpsRecommendationAction,
  getFinOpsForecastBudgets,
  simulateFinOpsScenario,
  getFinOpsAnomalyDetection,
  getFinOpsGovernancePolicies,
  getFinOpsShowbackChargeback,
  getFinOpsWorkloadEconomics,
  getFinOpsReportsAudit,
  getFinOpsSettingsIntegrations,
  getFinOpsIngestionStatus,
  getFinOpsBillingSummary,
  previewFinOpsIngestion,
  validateFinOpsIngestion,
  runFinOpsIngestion,
  getFinOpsBillingReconciliation,
} from "@/lib/api";
import {
  Download,
  Plus,
  RefreshCw,
  Search,
  Info,
  CheckCircle2,
  Target,
  Database,
  Lock,
  ShieldAlert,
} from "lucide-react";
import { CloudScope } from "@/types/navigation";
import { AnomalyItemData, DiscoveredResourceItem, FinOpsKpiMetric } from "@/types";
import { KpiDetailDrawer } from "@/components/shared/KpiDetailDrawer";
import { ResourceDetailDrawer } from "@/components/shared/ResourceDetailDrawer";
import { AnomalyDetailDrawer } from "@/components/shared/AnomalyDetailDrawer";
import { FinOpsAiAnalysisSection } from "@/components/shared/FinOpsAiAnalysisSection";
import { ConnectionStatusIndicator } from "@/components/shared/ConnectionStatusIndicator";
import { environmentLabel, toIndicatorStatus } from "@/lib/connectionState";
import type { ConnectionView } from "@/lib/connectionState";
import { formatUpdatedAt } from "@/lib/refreshScheduler";
import { OPERATIONAL_REFRESH_MS } from "@/lib/useDatabricksConnection";
import { KpiCardGrid, ProvenanceBanner } from "@/components/shared/FinOpsProvenance";
import {
  fmtMoney,
  fmtNumber,
  statusBadgeClass,
  statusLabel,
} from "@/lib/finopsProvenance";
import {
  currencyColumnName,
  formatSourceMoney,
  singleCurrency,
  sourceCurrencyLabel,
  sourceCurrencyOf,
} from "@/lib/billing";
import {
  formatDeterministicDateTime,
} from "@/lib/dateTimeFormat";
import { downloadFinOpsPdfReport } from "@/lib/pdfGenerator";
import { downloadCsvFile } from "@/lib/csvGenerator";

interface FinOpsCommandCenterViewProps {
  activeModule: FinOpsModule;
  onSelectModule?: (mod: FinOpsModule) => void;
  selectedWorkspaceId?: string;
  activeScope?: CloudScope | null;
  onSelectScope?: (scope: CloudScope) => void;
  availableConnections?: DatabricksConnection[];
  connectionHealth?: DatabricksConnectionHealth | null;
  /** The single derived connection state; this view never computes its own badge. */
  connectionView?: ConnectionView;
}

export const FinOpsCommandCenterView: React.FC<FinOpsCommandCenterViewProps> = ({
  activeModule,
  onSelectModule,
  selectedWorkspaceId = "databricks-azure-dev",
  activeScope,
  onSelectScope,
  availableConnections = [],
  connectionView,
}) => {
  // Module Data States
  const [overviewData, setOverviewData] = useState<ExecutiveOverviewData | null>(null);
  const [costData, setCostData] = useState<CostExplorerData | null>(null);
  const [allocData, setAllocData] = useState<CostAllocationData | null>(null);
  const [computeData, setComputeData] = useState<ComputeWarehousesData | null>(null);
  const [aiData, setAiData] = useState<AiEconomicsData | null>(null);
  const [advisorData, setAdvisorData] = useState<OptimizationAdvisorData | null>(null);
  const [anomalyData, setAnomalyData] = useState<AnomalyDetectionData | null>(null);
  const [settingsData, setSettingsData] = useState<SettingsIntegrationsData | null>(null);
  const [storageData, setStorageData] = useState<DataStorageData | null>(null);
  const [networkData, setNetworkData] = useState<NetworkCloudData | null>(null);
  const [forecastData, setForecastData] = useState<ForecastBudgetsData | null>(null);
  const [govData, setGovData] = useState<GovernancePoliciesData | null>(null);
  const [chargebackData, setChargebackData] = useState<ShowbackChargebackData | null>(null);
  const [workloadData, setWorkloadData] = useState<WorkloadEconomicsData | null>(null);
  const [reportsData, setReportsData] = useState<ReportsAuditData | null>(null);

  // Interactive Drawers State
  const [selectedKpiKey, setSelectedKpiKey] = useState<string | null>(null);
  const [selectedKpiMetric, setSelectedKpiMetric] = useState<FinOpsKpiMetric | null>(null);
  const [selectedDrawerResource, setSelectedDrawerResource] =
    useState<DiscoveredResourceItem | null>(null);
  const [selectedAnomaly, setSelectedAnomaly] = useState<AnomalyItemData | null>(null);

  const handleKpiClick = (key: string, metric: FinOpsKpiMetric) => {
    setSelectedKpiKey(key);
    setSelectedKpiMetric(metric);
  };

  // Sub-tabs
  const [computeTab, setComputeTab] = useState<"clusters" | "warehouses" | "jobs" | "utilization">("clusters");
  const [aiTab, setAiTab] = useState<"token" | "models" | "genie" | "agents" | "training" | "unit">("token");

  // Filters
  const [costSearch, setCostSearch] = useState<string>("");
  const [costOriginFilter, setCostOriginFilter] = useState<string>("all");
  const [costSkuFilter, setCostSkuFilter] = useState<string>("all");
  const [costGroupBy, setCostGroupBy] = useState<string>("product");

  const [periodFilter, setPeriodFilter] = useState<string>("month");
  const [customStartDate, setCustomStartDate] = useState<string>(() =>
    new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10)
  );
  const [customEndDate, setCustomEndDate] = useState<string>(() =>
    new Date().toISOString().slice(0, 10)
  );

  // Optimization Advisor Filters
  const [recCategoryFilter, setRecCategoryFilter] = useState<string>("all");
  const [recImpactFilter, setRecImpactFilter] = useState<string>("all");
  const [recSearch, setRecSearch] = useState<string>("");

  // Anomaly Detection Filters
  const [anomalySeverityFilter, setAnomalySeverityFilter] = useState<string>("all");
  const [anomalyStatusFilter, setAnomalyStatusFilter] = useState<string>("all");
  const [anomalySearch, setAnomalySearch] = useState<string>("");

  // Export Modal State
  const [exportReportType, setExportReportType] = useState<string>("Executive Cost Snapshot");
  const [exportFormat, setExportFormat] = useState<string>("CSV (Direct Download)");


  // Scenario Simulator
  const [computeSlider, setComputeSlider] = useState<number>(10);
  const [tokenSlider, setTokenSlider] = useState<number>(15);
  const [growthSlider, setGrowthSlider] = useState<number>(8);
  const [simResult, setSimResult] = useState<ScenarioSimulationResult | null>(null);

  // Modals & Toast State
  const [modalTitle, setModalTitle] = useState<string>("");
  const [modalBody, setModalBody] = useState<string>("");
  const [isDetailModalOpen, setIsDetailModalOpen] = useState<boolean>(false);
  const [isActionModalOpen, setIsActionModalOpen] = useState<boolean>(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState<boolean>(false);
  const [, setIsTagModalOpen] = useState<boolean>(false);
  const [, setIsModelModalOpen] = useState<boolean>(false);

  // Milestone 3H: Live Databricks Financial Ingestion & Warehouse Gate State
  const [ingestionStatus, setIngestionStatus] = useState<BillingIngestionStatusResponse | null>(null);
  const [billingSummary, setBillingSummary] = useState<BillingSummaryResponse | null>(null);
  // Amounts are shown in the currency they were billed in. There is no conversion and no
  // assumed USD: an unknown or mixed currency is shown as unavailable, never guessed.
  const sourceCurrency = sourceCurrencyOf(billingSummary);
  const formatCost = (amount: number): string => formatSourceMoney(amount, sourceCurrency);
  const [isIngestionModalOpen, setIsIngestionModalOpen] = useState<boolean>(false);
  const [ingestionModalTab, setIngestionModalTab] = useState<"overview" | "preview" | "reconciliation" | "diagnostics">("overview");
  const [previewRecords, setPreviewRecords] = useState<BillingUsageRecord[]>([]);
  const [reconciliationData, setReconciliationData] = useState<BillingReconciliationResponse | null>(null);
  const reconCurrency = reconciliationData?.cost_by_currency && reconciliationData.cost_by_currency.length > 1
    ? { code: null, mixed: true, codes: reconciliationData.cost_by_currency.map((c) => c.currency) }
    : singleCurrency(reconciliationData?.currency);
  const [validationData, setValidationData] = useState<IngestionValidateResponse | null>(null);
  const [isApprovalChecked, setIsApprovalChecked] = useState<boolean>(false);
  const [runResult, setRunResult] = useState<BillingIngestionRunResponse | null>(null);
  const [isRunExecuting, setIsRunExecuting] = useState<boolean>(false);

  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const inFlightRef = useRef<boolean>(false);
  const simResultRef = useRef<ScenarioSimulationResult | null>(null);

  const showToast = useCallback((msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  }, []);

  // Resolve active Databricks connection & workspace ID cleanly
  const requestedScopeId = activeScope?.workspace_id || selectedWorkspaceId || "";
  const matchedConnection = availableConnections.find(
    (c) => c.workspace_id === requestedScopeId || c.connection_id === requestedScopeId
  );
  const effectiveConnectionId =
    matchedConnection?.connection_id ||
    (requestedScopeId.startsWith("databricks-") ? requestedScopeId : "");
  const effectiveWorkspaceId = matchedConnection?.workspace_id || requestedScopeId;
  const workspaceEnvironment = environmentLabel(connectionView?.environment ?? matchedConnection?.environment);

  // Fetch active module data
  const loadModuleData = useCallback(async (background = false) => {
    if (inFlightRef.current || !effectiveConnectionId) return; // never overlap requests
    inFlightRef.current = true;
    if (!background) {
      setIsLoading(true);
      setError(null);
    }
    try {
      const resId = activeScope?.selected_child_resource?.resource_id;
      const resType = activeScope?.selected_child_resource?.resource_type;
      const wsId = effectiveWorkspaceId;
      const effectivePeriod = periodFilter === "custom" ? `${customStartDate}:${customEndDate}` : periodFilter;

      if (activeModule === "overview") {
        const d = await getFinOpsOverview(
          effectiveConnectionId,
          effectivePeriod,
          workspaceEnvironment,
          wsId,
          resId,
          resType
        );
        setOverviewData(d);
      } else if (activeModule === "cost") {
        const d = await getFinOpsCostExplorer(effectiveConnectionId, wsId, resId, resType);
        setCostData(d);
      } else if (activeModule === "allocation") {
        const d = await getFinOpsCostAllocation(effectiveConnectionId, wsId, resId, resType);
        setAllocData(d);
      } else if (activeModule === "compute") {
        const d = await getFinOpsComputeWarehouses(effectiveConnectionId, wsId, resId, resType);
        setComputeData(d);
      } else if (activeModule === "ai") {
        const d = await getFinOpsAiEconomics(effectiveConnectionId, wsId, resId, resType);
        setAiData(d);
      } else if (activeModule === "data") {
        const d = await getFinOpsDataStorage(effectiveConnectionId, wsId, resId, resType);
        setStorageData(d);
      } else if (activeModule === "network") {
        const d = await getFinOpsNetworkCloud(effectiveConnectionId, wsId, resId, resType);
        setNetworkData(d);
      } else if (activeModule === "recommend") {
        const d = await getFinOpsOptimizationAdvisor(effectiveConnectionId, wsId, resId, resType);
        setAdvisorData(d);
      } else if (activeModule === "forecast") {
        const d = await getFinOpsForecastBudgets(effectiveConnectionId, wsId, resId, resType);
        setForecastData(d);
        if (d.default_scenario && !simResultRef.current) setSimResult(d.default_scenario);
      } else if (activeModule === "anomaly") {
        const d = await getFinOpsAnomalyDetection(effectiveConnectionId, wsId, resId, resType);
        setAnomalyData(d);
      } else if (activeModule === "governance") {
        const d = await getFinOpsGovernancePolicies(effectiveConnectionId, wsId, resId, resType);
        setGovData(d);
      } else if (activeModule === "chargeback") {
        const d = await getFinOpsShowbackChargeback(effectiveConnectionId, wsId, resId, resType);
        setChargebackData(d);
      } else if (activeModule === "workloads") {
        const d = await getFinOpsWorkloadEconomics(effectiveConnectionId, wsId, resId, resType);
        setWorkloadData(d);
      } else if (activeModule === "reports") {
        const d = await getFinOpsReportsAudit(effectiveConnectionId, wsId, resId, resType);
        setReportsData(d);
      } else if (activeModule === "settings") {
        const d = await getFinOpsSettingsIntegrations(effectiveConnectionId, wsId, resId, resType);
        setSettingsData(d);
      }

      // Milestone 3H: Ingestion status and summary
      try {
        const [ingStatus, bSummary] = await Promise.all([
          getFinOpsIngestionStatus(wsId),
          getFinOpsBillingSummary(effectiveConnectionId, wsId, resId),
        ]);
        setIngestionStatus(ingStatus);
        setBillingSummary(bSummary);
      } catch (e) {
        console.warn("Could not fetch ingestion status", e);
      }
      setLastUpdatedAt(Date.now());
      setRefreshError(null);
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error connecting to backend analytics engine";
      // Keep the last data but flag it stale; only a user-initiated load interrupts with a toast.
      setRefreshError(msg);
      if (!background) {
        setError(msg);
        showToast("Notice: Could not retrieve live metrics. Check backend connection.");
      }
    } finally {
      inFlightRef.current = false;
      setIsLoading(false);
    }
  }, [activeModule, effectiveConnectionId, effectiveWorkspaceId, periodFilter, customStartDate, customEndDate, workspaceEnvironment, activeScope, showToast]);

  useEffect(() => {
    simResultRef.current = simResult;
  }, [simResult]);

  // Selected workspace / resource scope changed: drop every previous value immediately so data
  // from another workspace can never be shown as current.
  useEffect(() => {
    setOverviewData(null);
    setCostData(null);
    setAllocData(null);
    setComputeData(null);
    setAiData(null);
    setAdvisorData(null);
    setAnomalyData(null);
    setSettingsData(null);
    setStorageData(null);
    setNetworkData(null);
    setForecastData(null);
    setGovData(null);
    setChargebackData(null);
    setWorkloadData(null);
    setReportsData(null);
    setIngestionStatus(null);
    setBillingSummary(null);
    setSimResult(null);
    setLastUpdatedAt(null);
    setRefreshError(null);
  }, [effectiveConnectionId, effectiveWorkspaceId, activeScope?.selected_child_resource?.resource_id]);

  useEffect(() => {
    void loadModuleData();
  }, [loadModuleData]);

  // Controlled live refresh (paused while the tab is hidden)
  useEffect(() => {
    const tick = () => {
      if (typeof document === "undefined" || document.visibilityState === "visible") {
        void loadModuleData(true);
      }
    };
    const t = setInterval(tick, OPERATIONAL_REFRESH_MS);
    return () => clearInterval(t);
  }, [loadModuleData]);

  // Milestone 3H: Ingestion modal helpers
  const handleFetchIngestionDetails = async () => {
    try {
      const targetWs = effectiveWorkspaceId;
      const targetWh = matchedConnection?.warehouse_id || ingestionStatus?.warehouse_id || "";
      const [prevRes, valRes, recRes] = await Promise.all([
        previewFinOpsIngestion(targetWs, 15),
        validateFinOpsIngestion(targetWs, targetWh),
        getFinOpsBillingReconciliation(effectiveConnectionId, targetWs),
      ]);
      setPreviewRecords(prevRes.preview_records || []);
      setValidationData(valRes);
      setReconciliationData(recRes);
    } catch (e) {
      console.warn("Error fetching ingestion modal data", e);
    }
  };

  const handleExecuteIngestionRun = async () => {
    setIsRunExecuting(true);
    try {
      const targetWs = effectiveWorkspaceId;
      const today = new Date();
      const startDay = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
      const res = await runFinOpsIngestion({
        workspace_id: targetWs,
        start_date: startDay.toISOString().slice(0, 10),
        end_date: today.toISOString().slice(0, 10),
        is_approved: isApprovalChecked,
        limit: 1000,
      });
      setRunResult(res);
      if (res.status === "approval_required") {
        showToast("Zero-Execution Gate Enforced: Approval Required to Resume Warehouse.");
      } else {
        showToast(`Ingestion completed: ${res.inserted_count} records inserted.`);
      }
    } catch (err: unknown) {
      showToast(`Ingestion run error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsRunExecuting(false);
    }
  };

  // Recalculate scenario simulation
  const handleRecalculateScenario = async (c: number, t: number, g: number) => {
    try {
      const res = await simulateFinOpsScenario(c, t, g);
      setSimResult(res);
    } catch {
      // No local formula: a scenario is only meaningful on top of a real forecast baseline.
      setSimResult(null);
      showToast("Scenario unavailable: could not reach the forecast engine.");
    }
  };

  // Decision action handler
  const handleDecisionAction = async (decisionId: string, action: string) => {
    try {
      await recordFinOpsRecommendationAction(decisionId, action);
      showToast(`Action recorded: ${action}`);
      if (advisorData) {
        setAdvisorData({
          ...advisorData,
          recommendations: advisorData.recommendations.map((r) =>
            r.id === decisionId ? { ...r, status: action } : r
          ),
        });
      }
    } catch {
      showToast(`Action updated to: ${action}`);
    }
  };

  // CSV Downloader
  const downloadCostCsv = () => {
    window.location.href = `/api/v1/finops/cost-explorer/csv`;
    showToast("Downloaded cost-explorer.csv");
  };

  return (
    <div className="min-h-screen bg-[#f4f7fb] text-[#182230] font-sans antialiased pb-16">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 bg-[#172b4d] text-white px-5 py-3 rounded-lg shadow-xl z-50 text-xs font-medium flex items-center gap-2 animate-in fade-in slide-in-from-bottom-3">
          <Info className="w-4 h-4 text-cyan-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Page Header — Full Width Responsive */}
      <div className="bg-white border-b border-[#e5eaf1] px-4 sm:px-6 lg:px-8 py-5">
        <div className="w-full flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-bold text-blue-600 uppercase tracking-wider">
              FinOps Application · Azure Databricks
            </div>
            <h1 className="text-2xl font-extrabold text-[#182230] mt-1 tracking-tight">
              {activeModule === "overview" && "Executive Cost Overview"}
              {activeModule === "cost" && "Cost Explorer"}
              {activeModule === "allocation" && "Cost Allocation"}
              {activeModule === "compute" && "Compute & Warehouses"}
              {activeModule === "ai" && "AI & Token Economics"}
              {activeModule === "data" && "Data & Storage"}
              {activeModule === "network" && "Network & Cloud Infrastructure"}
              {activeModule === "recommend" && "Optimization Advisor"}
              {activeModule === "forecast" && "Forecast & Budgets"}
              {activeModule === "anomaly" && "Anomaly Detection"}
              {activeModule === "governance" && "Governance & Policies"}
              {activeModule === "chargeback" && "Showback & Chargeback"}
              {activeModule === "workloads" && "Workload Economics"}
              {activeModule === "reports" && "Reports & Audit"}
              {activeModule === "settings" && "Settings & Integrations"}
            </h1>
            <div className="text-xs text-[#667085] mt-0.5">
              Unified cost intelligence, unit economics and rightsizing across connected Databricks workspaces.
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setIsExportModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-[#e5eaf1] bg-white text-xs font-semibold text-[#344054] hover:bg-slate-50 transition shadow-2xs"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export Snapshot</span>
            </button>
            <button
              onClick={() => setIsActionModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-2xs transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Create Cost Action</span>
            </button>
          </div>
        </div>
      </div>

      <div className="w-full px-4 sm:px-6 lg:px-8 pt-6 pb-12">
        {/* Global Filter Bar */}
        <div className="flex items-center gap-2.5 flex-wrap mb-6 text-xs text-[#344054]">
          <span
            className="bg-white border border-[#e5eaf1] px-3 py-1.5 rounded-lg font-medium shadow-2xs"
            title="Environment of the selected Databricks workspace"
            aria-label="Workspace environment"
          >
            Environment: {workspaceEnvironment}
          </span>

          <select
            value={activeScope?.workspace_id || effectiveWorkspaceId || "all"}
            onChange={(e) => {
              const newWsId = e.target.value;
              const chosen = availableConnections.find((c) => c.workspace_id === newWsId);
              if (onSelectScope && activeScope) {
                onSelectScope({
                  ...activeScope,
                  workspace_id: newWsId === "all" ? undefined : newWsId,
                  workspace_name: chosen?.workspace_name || activeScope.workspace_name,
                  workspace_url: chosen?.workspace_url || activeScope.workspace_url,
                });
              }
            }}
            className="bg-white border border-[#e5eaf1] px-3 py-1.5 rounded-lg font-medium shadow-2xs"
            aria-label="Databricks workspace selection"
          >
            {availableConnections.map((ws) => (
              <option key={ws.connection_id} value={ws.workspace_id}>
                {ws.workspace_name} ({ws.workspace_id})
              </option>
            ))}
          </select>

          <div className="flex items-center gap-1.5">
            <select
              value={periodFilter}
              onChange={(e) => setPeriodFilter(e.target.value)}
              className="bg-white border border-[#e5eaf1] px-3 py-1.5 rounded-lg font-medium shadow-2xs"
              aria-label="Time period selection"
            >
              <option value="7d">Last 7 Days</option>
              <option value="14d">Last 14 Days</option>
              <option value="30d">Last 30 Days</option>
              <option value="90d">Last 90 Days</option>
              <option value="month">This Month (MTD)</option>
              <option value="last">Last Month</option>
              <option value="quarter">This Quarter (QTD)</option>
              <option value="ytd">Year to Date (YTD)</option>
              <option value="custom">Custom Range</option>
            </select>

            {periodFilter === "custom" && (
              <div className="flex items-center gap-1.5 bg-white border border-[#e5eaf1] px-2 py-1 rounded-lg text-xs shadow-2xs">
                <input
                  type="date"
                  value={customStartDate}
                  onChange={(e) => setCustomStartDate(e.target.value)}
                  className="border-0 p-0 text-xs text-slate-700 focus:outline-none"
                  aria-label="Start date"
                />
                <span className="text-slate-400">→</span>
                <input
                  type="date"
                  value={customEndDate}
                  onChange={(e) => setCustomEndDate(e.target.value)}
                  className="border-0 p-0 text-xs text-slate-700 focus:outline-none"
                  aria-label="End date"
                />
              </div>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            <span
              className="inline-flex items-center bg-white border border-[#e5eaf1] px-2.5 py-1.5 rounded-lg text-xs font-semibold text-slate-700 shadow-2xs"
              aria-label="Billing currency"
              title="Amounts are shown in the currency reported by the billing source. No conversion is applied."
            >
              {sourceCurrencyLabel(sourceCurrency)}
            </span>
          </div>

          <ConnectionStatusIndicator
            status={connectionView ? toIndicatorStatus(connectionView) : "loading"}
            label={connectionView ? `${matchedConnection?.workspace_name || "Databricks"} ${connectionView.label}` : "Checking"}
          />
          {connectionView?.sqlWarehouse && (
            <span
              className="px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-slate-50 text-slate-700 border-slate-200"
              title={connectionView.sqlWarehouse.message}
            >
              SQL warehouse: {connectionView.sqlWarehouse.state ?? "-"}
            </span>
          )}
          <span className="text-[11px] text-slate-500" data-testid="last-updated">
            Updated {formatUpdatedAt(lastUpdatedAt)}
          </span>
          {(refreshError || connectionView?.stale) && (
            <span
              className="px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-amber-50 text-amber-800 border-amber-300"
              title={refreshError || connectionView?.reason || "Latest refresh failed"}
              data-testid="stale-badge"
            >
              Stale data: last refresh failed
            </span>
          )}

          {activeScope?.is_multi_scope && (
            <span className="bg-indigo-50 text-indigo-700 px-2.5 py-1 rounded-md text-[11px] font-bold border border-indigo-200">
              Multi-Scope: {activeScope.subscription_ids?.length || 1} Subs · {activeScope.workspace_ids?.length || 1} Workspaces
            </span>
          )}
          <button
            onClick={() => loadModuleData()}
            className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[#e5eaf1] bg-white hover:bg-slate-50 font-medium text-slate-600 transition text-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>

        {/* Milestone 3H: Live Databricks Financial Ingestion & Warehouse Gate Banner */}
        <div className="mb-6 bg-white border border-[#e5eaf1] rounded-xl p-4 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-bold text-[#182230]">Databricks System Tables Billing Pipeline</span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                  WH: {ingestionStatus?.warehouse_status || "UNKNOWN"}
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                  System Tables: {ingestionStatus?.system_tables_status || "UNKNOWN"}
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-50 text-slate-600 border border-slate-200">
                  Billing rows: {(ingestionStatus?.total_usage_records_ingested ?? 0) > 0 ? "INGESTED" : "NONE INGESTED"}
                </span>
              </div>
              <div className="text-[11px] text-[#667085] mt-1 flex items-center gap-3 flex-wrap">
                <span>Target: <code className="text-[#344054] font-medium">{ingestionStatus?.warehouse_name || "—"} ({ingestionStatus?.warehouse_id || "—"})</code></span>
                <span>•</span>
                {(ingestionStatus?.total_usage_records_ingested ?? 0) > 0 ? (
                  <span>Ingested: <strong className="text-[#182230]">{(ingestionStatus?.total_dbu_consumed ?? 0).toLocaleString()} DBU</strong> across <strong className="text-[#182230]">{ingestionStatus?.total_usage_records_ingested}</strong> usage records</span>
                ) : (
                  <span>No billing data ingested yet: spend figures stay <strong className="text-[#182230]">unavailable</strong> until an approved read-only ingestion runs.</span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setIsIngestionModalOpen(true);
                handleFetchIngestionDetails();
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-indigo-200 bg-indigo-50/60 hover:bg-indigo-100/70 text-indigo-700 text-xs font-semibold transition"
            >
              <Lock className="w-3.5 h-3.5 text-indigo-600" />
              <span>Inspect Warehouse & Approval Gate</span>
            </button>
          </div>
        </div>


        {/* ------------------------------------------------------------------ */}
        {/* MODULE 1: EXECUTIVE COST OVERVIEW */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "overview" && (
          <div className="space-y-6">
            {/* Active Child Scope Focused Alert Banner */}
            {activeScope?.selected_child_resource && (
              <div className="p-3.5 bg-blue-50 border border-blue-200 rounded-xl flex items-center justify-between text-xs text-blue-950">
                <div className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-brand-600 shrink-0" />
                  <div>
                    <span className="font-bold">Focused Resource Scope: </span>
                    <span className="font-semibold text-brand-700">
                      {activeScope.selected_child_resource.resource_name}
                    </span>{" "}
                    <span className="text-[10px] uppercase font-bold px-1.5 py-0.2 rounded bg-blue-100 text-blue-800">
                      {activeScope.selected_child_resource.resource_type}
                    </span>
                  </div>
                </div>
                {onSelectScope && (
                  <button
                    type="button"
                    onClick={() => {
                      onSelectScope({
                        ...activeScope,
                        scope_type: "databricks_workspace",
                        selected_child_resource: null,
                        display_name: activeScope.workspace_name || "Azure Databricks Dev",
                      });
                    }}
                    className="text-xs font-semibold text-brand-600 hover:underline"
                  >
                    Reset to Full Workspace Scope
                  </button>
                )}
              </div>
            )}

            <ProvenanceBanner provenance={overviewData?.provenance} />

            {/* 7 Interactive KPI Cards: values, status and caveats come only from the backend */}
            <KpiCardGrid
              kpis={overviewData?.kpis}
              specs={[
                { key: "total_spend", label: "Total spend" },
                { key: "databricks_spend", label: "Databricks spend" },
                { key: "ai_spend", label: "AI & GenAI spend" },
                { key: "dbu_consumption", label: "DBU consumption" },
                { key: "savings_opportunity", label: "Identified savings" },
                { key: "forecast_spend", label: "Forecast month-end" },
                { key: "anomalies", label: "Cost anomalies" },
              ]}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
              className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3"
            />

            {/* AI FinOps Intelligence & Cost Analysis (Moved below all 7 KPI cards with Integrated Decisions) */}
            <FinOpsAiAnalysisSection
              moduleId="overview"
              workspaceId={effectiveWorkspaceId}
              onNavigateToModule={(m) => onSelectModule?.(m as FinOpsModule)}
              decisions={advisorData?.recommendations || overviewData?.decisions_requiring_attention || []}
              onDecisionAction={handleDecisionAction}
              onViewEvidence={(item) => {
                setModalTitle(item.title);
                setModalBody(item.evidence);
                setIsDetailModalOpen(true);
              }}
            />

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              {/* Spend Trend and Forecast */}
              <div className="lg:col-span-7 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <h3 className="text-sm font-bold text-[#182230]">Spend trend and forecast</h3>
                    <p className="text-[11px] text-[#667085]">Daily actuals, forecast and approved budget · {currencyColumnName(sourceCurrency)}</p>
                  </div>
                  <span className="text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full">
                    Actuals · list-price basis
                  </span>
                </div>
                {(() => {
                  const trend = overviewData?.spend_trend || [];
                  if (trend.length === 0) {
                    return (
                      <div className="h-56 flex items-center justify-center text-center text-xs text-slate-500 px-6">
                        {overviewData?.provenance?.spend?.message ||
                          "No daily spend is available: billing rows have not been ingested."}
                      </div>
                    );
                  }
                  const max = Math.max(...trend.map((t) => t.actual ?? 0), 1);
                  const stepX = trend.length > 1 ? 480 / (trend.length - 1) : 0;
                  const pts = trend
                    .map((t, i) => `${10 + i * stepX},${170 - ((t.actual ?? 0) / max) * 160}`)
                    .join(" ");
                  return (
                    <div className="h-56 w-full flex items-end pt-4">
                      <svg className="w-full h-full overflow-visible" viewBox="0 0 500 180" role="img" aria-label="Daily actual spend">
                        <line x1="0" y1="170" x2="500" y2="170" stroke="#f1f5f9" strokeWidth="1" />
                        <line x1="0" y1="90" x2="500" y2="90" stroke="#f1f5f9" strokeWidth="1" />
                        <polyline points={pts} fill="none" stroke="#2563eb" strokeWidth="2.5" />
                        <text x="0" y="12" fontSize="9" fill="#667085">
                          peak ${max.toLocaleString(undefined, { maximumFractionDigits: 0 })}/day · {trend[0].day} – {trend[trend.length - 1].day}
                        </text>
                      </svg>
                    </div>
                  );
                })()}
                <div className="flex items-center gap-5 mt-2 text-[11px] text-[#667085]">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-blue-600"></span> Actual spend (from ingested system.billing.usage)
                  </span>
                  <span className="text-slate-400">Forecast and budget are shown on the Forecast &amp; Budgets page.</span>
                </div>
              </div>

              {/* Spend Composition */}
              <div className="lg:col-span-5 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230]">Spend composition</h3>
                <p className="text-[11px] text-[#667085] mb-4">Consolidated cost by service family</p>
                <div className="flex flex-col gap-3">
                  {(overviewData?.spend_composition || []).length === 0 && (
                    <div className="text-xs text-slate-500">No spend composition available: billing rows have not been ingested.</div>
                  )}
                  {(
                    (overviewData?.spend_composition || []).map((s) => ({
                        name: s.family,
                        pct: Math.round(s.share * 100),
                        cost: formatCost(s.amount),
                        color: s.color || "#2563eb",
                      }))
                  ).map((s, idx) => (
                    <div key={idx} className="space-y-1">
                      <div className="flex justify-between text-xs font-semibold">
                        <span>{s.name}</span>
                        <span className="text-[#667085]">
                          {s.cost} ({s.pct}%)
                        </span>
                      </div>
                      <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full ${s.color.startsWith("#") ? "" : s.color}`}
                          style={{
                            width: `${s.pct}%`,
                            backgroundColor: s.color.startsWith("#") ? s.color : undefined,
                          }}
                        ></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Tables Row: Cost Drivers */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              {/* Top Cost Drivers */}
              <div className="lg:col-span-12 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-bold text-[#182230]">Top cost drivers</h3>
                    <p className="text-[11px] text-[#667085]">Highest spend dimensions requiring management attention across connected scopes</p>
                  </div>
                  <span className="text-[10px] font-bold text-slate-500 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
                    {(overviewData?.top_cost_drivers || []).length} dimensions
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                        <th className="py-2.5 px-3">Cost Driver</th>
                        <th className="py-2.5 px-3">Workspace / Owner</th>
                        <th className="py-2.5 px-3 text-right">Spend</th>
                        <th className="py-2.5 px-3">Change</th>
                        <th className="py-2.5 px-3">Signal</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#e5eaf1]">
                      {(overviewData?.top_cost_drivers || []).length === 0 && (
                        <tr>
                          <td colSpan={5} className="py-6 text-center text-xs text-slate-500">
                            No cost drivers available: billing rows have not been ingested.
                          </td>
                        </tr>
                      )}
                      {(
                        (overviewData?.top_cost_drivers || []).map((drv) => ({
                            d: drv.driver,
                            w: drv.workspace_owner,
                            s: drv.formatted_spend,
                            c: drv.change,
                            sig: drv.signal,
                          }))
                      ).map((r, idx) => {
                        // Driver labels are "<type>: <id>" from the backend (real attribution keys).
                        const [drvType, ...drvRest] = r.d.split(": ");
                        const resType =
                          drvType === "warehouse" ? "warehouse"
                          : drvType === "serving" ? "serving_endpoint"
                          : drvType === "cluster" ? "cluster"
                          : drvType === "app" ? "app"
                          : drvType;
                        const resId = drvRest.join(": ") || r.d;
                        const resStatus = undefined;

                        return (
                          <tr
                            key={idx}
                            onClick={() => {
                              setSelectedDrawerResource({
                                id: resId,
                                name: r.d,
                                resource_type: resType,
                                workspace_id: effectiveWorkspaceId,
                                status: resStatus,
                                source_api: "system.billing.usage",
                                metadata: { spend: r.s, change: r.c, signal: r.sig, owner: r.w },
                                discovered_at: new Date().toISOString(),
                              });
                            }}
                            className="hover:bg-blue-50/60 cursor-pointer transition group"
                            title="Click to inspect underlying resource and telemetry"
                          >
                            <td className="py-2.5 px-3 font-semibold text-[#182230] group-hover:text-brand-600 flex items-center gap-2">
                              <span>{r.d}</span>
                              <span className="text-[10px] text-slate-400 opacity-0 group-hover:opacity-100 transition">
                                &rarr;
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-[#667085]">{r.w}</td>
                            <td className="py-2.5 px-3 text-right font-bold text-[#182230]">{r.s}</td>
                            <td className="py-2.5 px-3 text-rose-600 font-semibold">{r.c}</td>
                            <td className="py-2.5 px-3">
                              <span
                                className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                  r.sig === "High"
                                    ? "bg-rose-50 text-rose-700"
                                    : r.sig === "Review"
                                    ? "bg-amber-50 text-amber-700"
                                    : "bg-emerald-50 text-emerald-700"
                                }`}
                              >
                                {r.sig}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 2: COST EXPLORER */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "cost" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-2 flex-wrap text-xs">
                <select
                  value={costOriginFilter}
                  onChange={(e) => setCostOriginFilter(e.target.value)}
                  className="bg-white border border-[#e5eaf1] px-3 py-1.5 rounded-lg shadow-2xs text-xs font-medium text-slate-700"
                  aria-label="Billing origin filter"
                >
                  <option value="all">All billing origins</option>
                  <option value="JOBS">JOBS</option>
                  <option value="SQL">SQL</option>
                  <option value="MODEL_SERVING">MODEL_SERVING</option>
                  <option value="VECTOR_SEARCH">VECTOR_SEARCH</option>
                </select>
                <select
                  value={costSkuFilter}
                  onChange={(e) => setCostSkuFilter(e.target.value)}
                  className="bg-white border border-[#e5eaf1] px-3 py-1.5 rounded-lg shadow-2xs text-xs font-medium text-slate-700"
                  aria-label="SKU filter"
                >
                  <option value="all">All SKUs</option>
                  <option value="Jobs Compute">Jobs Compute</option>
                  <option value="SQL Pro">SQL Pro</option>
                  <option value="Serverless SQL">Serverless SQL</option>
                  <option value="Model Serving">Model Serving</option>
                </select>
                <select
                  value={costGroupBy}
                  onChange={(e) => setCostGroupBy(e.target.value)}
                  className="bg-white border border-[#e5eaf1] px-3 py-1.5 rounded-lg shadow-2xs text-xs font-medium text-slate-700"
                  aria-label="Group by selector"
                >
                  <option value="product">Group by: Product</option>
                  <option value="workspace">Group by: Workspace</option>
                  <option value="sku">Group by: SKU</option>
                  <option value="owner">Group by: Owner</option>
                </select>
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
                  <input
                    type="text"
                    value={costSearch}
                    onChange={(e) => setCostSearch(e.target.value)}
                    placeholder="Search SKU, job, workspace..."
                    className="bg-white border border-[#e5eaf1] pl-8 pr-3 py-1.5 rounded-lg shadow-2xs w-64 text-xs"
                    aria-label="Search billing ledger"
                  />
                </div>
              </div>
              <button
                onClick={downloadCostCsv}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white font-semibold text-xs hover:bg-blue-700 transition shadow-2xs"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download CSV</span>
              </button>
            </div>

            <ProvenanceBanner provenance={costData?.provenance} />

            <KpiCardGrid
              kpis={costData?.kpis}
              specs={[
                { key: "gross_consumption", label: "Gross consumption" },
                { key: "effective_rate", label: "Effective rate" },
                { key: "unallocated_spend", label: "Unallocated spend" },
                { key: "credits_discounts", label: "Credits / discounts" },
              ]}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
            />

            {/* Detailed Billing Ledger Table */}
            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-[#182230]">Detailed billing ledger</h3>
                  <p className="text-[11px] text-[#667085]">Usage rows ingested from system.billing.usage, priced at list rates, with allocation status from billing tags.</p>
                </div>
                <span className="text-[10px] font-bold bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                  {currencyColumnName(sourceCurrency)} · list-price basis
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                      <th className="py-2.5 px-3">Date</th>
                      <th className="py-2.5 px-3">Product</th>
                      <th className="py-2.5 px-3">SKU</th>
                      <th className="py-2.5 px-3">Workspace</th>
                      <th className="py-2.5 px-3 text-right">Usage Qty</th>
                      <th className="py-2.5 px-3">Unit</th>
                      <th className="py-2.5 px-3 text-right">List Cost</th>
                      <th className="py-2.5 px-3 text-right">Effective Cost</th>
                      <th className="py-2.5 px-3">Owner Tag</th>
                      <th className="py-2.5 px-3">Allocation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e5eaf1]">
                    {(costData?.billing_ledger || []).length === 0 && (
                      <tr>
                        <td colSpan={10} className="py-8 text-center text-xs text-slate-500">
                          {costData?.provenance?.ledger?.message || "No billing ledger rows available."}
                        </td>
                      </tr>
                    )}
                    {((costData?.billing_ledger || []).filter((row) => {
                      if (costOriginFilter !== "all") {
                        const m = costOriginFilter.toLowerCase();
                        if (!row.product.toLowerCase().includes(m) && !row.sku.toLowerCase().includes(m)) return false;
                      }
                      if (costSkuFilter !== "all") {
                        if (!row.sku.toLowerCase().includes(costSkuFilter.toLowerCase())) return false;
                      }
                      if (costSearch) {
                        const q = costSearch.toLowerCase();
                        if (
                          !row.product.toLowerCase().includes(q) &&
                          !row.sku.toLowerCase().includes(q) &&
                          !row.workspace.toLowerCase().includes(q) &&
                          !(row.owner_tag && row.owner_tag.toLowerCase().includes(q))
                        ) {
                          return false;
                        }
                      }
                      return true;
                    }).sort((a, b) => {
                      if (costGroupBy === "product") return a.product.localeCompare(b.product);
                      if (costGroupBy === "workspace") return a.workspace.localeCompare(b.workspace);
                      if (costGroupBy === "sku") return a.sku.localeCompare(b.sku);
                      if (costGroupBy === "owner") return (a.owner_tag || "").localeCompare(b.owner_tag || "");
                      return 0;
                    })).map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/50">
                        <td className="py-2.5 px-3 text-[#667085]">{row.date}</td>
                        <td className="py-2.5 px-3 font-semibold text-[#182230]">{row.product}</td>
                        <td className="py-2.5 px-3 text-[#667085]">{row.sku}</td>
                        <td className="py-2.5 px-3 text-[#667085] font-mono text-[11px]">{row.workspace}</td>
                        <td className="py-2.5 px-3 text-right font-medium">{row.usage_qty.toLocaleString()}</td>
                        <td className="py-2.5 px-3 text-[#667085]">{row.unit}</td>
                        <td className="py-2.5 px-3 text-right text-[#667085]">{formatCost(row.list_cost)}</td>
                        <td className="py-2.5 px-3 text-right font-bold text-[#182230]">
                          {formatCost(row.effective_cost)}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">{row.owner_tag}</td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              row.allocation_status === "Allocated"
                                ? "bg-emerald-50 text-emerald-700"
                                : row.allocation_status === "Partial"
                                ? "bg-amber-50 text-amber-700"
                                : "bg-rose-50 text-rose-700"
                            }`}
                          >
                            {row.allocation_status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 3: COST ALLOCATION */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "allocation" && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-base font-bold text-[#182230]">Cost Allocation Engine</h2>
                <p className="text-xs text-[#667085]">Map technical consumption to accountable owners and business units.</p>
              </div>
              <button
                onClick={() => setIsTagModalOpen(true)}
                className="px-3.5 py-1.5 rounded-lg bg-blue-600 text-white font-semibold text-xs hover:bg-blue-700 transition"
              >
                Configure Allocation Rule
              </button>
            </div>

            <ProvenanceBanner provenance={allocData?.provenance} />

            <KpiCardGrid
              kpis={allocData?.kpis}
              specs={[
                { key: "allocated_spend", label: "Allocated spend" },
                { key: "unallocated_spend", label: "Unallocated spend" },
                { key: "active_rules", label: "Active allocation rules" },
                { key: "shared_pool", label: "Shared cost pool" },
              ]}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
            />

            {/* Spend by real attribution key (billing tags); untagged spend stays Unallocated */}
            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-1">Spend by owner tag</h3>
              <p className="text-[11px] text-[#667085] mb-3">
                Attributed strictly from billing custom tags. Untagged spend is shown as Unallocated and is never distributed.
              </p>
              {(allocData?.spend_by_bu || []).length === 0 ? (
                <div className="text-xs text-slate-500">
                  {allocData?.provenance?.allocation?.message || "No attributed spend available."}
                </div>
              ) : (
                <div className="space-y-2">
                  {(allocData?.spend_by_bu || []).map((b, idx) => (
                    <div key={idx} className="flex justify-between items-center text-xs border-b border-slate-100 py-1.5">
                      <span className={`font-semibold ${b.business_unit === "Unallocated" ? "text-rose-700" : "text-slate-800"}`}>
                        {b.business_unit}
                      </span>
                      <span className="font-bold text-[#182230]">
                        {fmtMoney(b.spend, formatCost)}
                        {typeof (b as { share?: number }).share === "number" && (
                          <span className="ml-2 text-slate-500 font-normal">
                            ({Math.round(((b as { share?: number }).share ?? 0) * 100)}%)
                          </span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Rulebook Table */}
            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-1">Allocation rulebook</h3>
              <p className="text-[11px] text-[#667085] mb-3">Rules are evaluated in priority order. Records without a matching tag stay Unallocated.</p>
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                    <th className="py-2 px-3">Priority</th>
                    <th className="py-2 px-3">Rule Name</th>
                    <th className="py-2 px-3">Match Condition</th>
                    <th className="py-2 px-3">Allocation Target</th>
                    <th className="py-2 px-3">Method</th>
                    <th className="py-2 px-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#e5eaf1]">
                  {(allocData?.rulebook || []).map((r, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="py-2.5 px-3 font-bold">{r.priority}</td>
                      <td className="py-2.5 px-3 font-semibold">{r.rule_name}</td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">{r.match_condition}</td>
                      <td className="py-2.5 px-3">{r.allocation_target}</td>
                      <td className="py-2.5 px-3 text-[#667085]">{r.method}</td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700">
                          {r.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 4: COMPUTE & WAREHOUSES */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "compute" && (
          <div className="space-y-6">
            <ProvenanceBanner provenance={computeData?.provenance} />

            <KpiCardGrid
              kpis={computeData?.kpis}
              specs={[
                { key: "compute_spend", label: "Compute spend" },
                { key: "active_compute", label: "Running clusters / warehouses" },
                { key: "idle_capacity", label: "Idle capacity" },
                { key: "potential_savings", label: "Potential compute savings" },
              ]}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
            />

            {/* Sub-tabs */}
            <div className="flex gap-2 border-b border-[#e5eaf1]">
              {(["clusters", "warehouses", "jobs", "utilization"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setComputeTab(t)}
                  className={`pb-2.5 px-3 text-xs font-semibold capitalize border-b-2 transition ${
                    computeTab === t ? "border-blue-600 text-blue-600" : "border-transparent text-[#667085] hover:text-[#182230]"
                  }`}
                >
                  {t === "clusters" && "Clusters"}
                  {t === "warehouses" && "SQL Warehouses"}
                  {t === "jobs" && "Jobs & Workflows"}
                  {t === "utilization" && "Utilization Heatmap"}
                </button>
              ))}
            </div>

            {/* Clusters Tab */}
            {computeTab === "clusters" && (
              <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230] mb-3">Live Discovered Cluster Inventory</h3>
                {(computeData?.clusters || []).length === 0 && (
                  <div className="text-xs text-slate-500 mb-2">No clusters discovered in this workspace scope.</div>
                )}
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                      <th className="py-2 px-3">Cluster</th>
                      <th className="py-2 px-3">Type</th>
                      <th className="py-2 px-3">Owner</th>
                      <th className="py-2 px-3">Node Profile</th>
                      <th className="py-2 px-3">Runtime Hrs</th>
                      <th className="py-2 px-3">CPU Avg/Peak</th>
                      <th className="py-2 px-3 text-right">DBU MTD</th>
                      <th className="py-2 px-3 text-right">Cost MTD</th>
                      <th className="py-2 px-3">State</th>
                      <th className="py-2 px-3">Finding</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e5eaf1]">
                    {(computeData?.clusters || []).map((c, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-semibold text-[#182230]">{c.name}</td>
                        <td className="py-2.5 px-3 text-[#667085]">{c.type}</td>
                        <td className="py-2.5 px-3 text-[#667085]">{c.owner}</td>
                        <td className="py-2.5 px-3 font-mono text-[11px]">{c.node_profile}</td>
                        <td className="py-2.5 px-3 text-slate-500">{fmtNumber(c.runtime_hrs, " h")}</td>
                        <td className="py-2.5 px-3">{c.cpu_utilization}</td>
                        <td className="py-2.5 px-3 text-right">{fmtNumber(c.dbu_mtd)}</td>
                        <td className="py-2.5 px-3 text-right font-bold">{fmtMoney(c.cost_mtd, formatCost)}</td>
                        <td className="py-2.5 px-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                            {c.state}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700">
                            {c.finding}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* SQL Warehouses Tab */}
            {computeTab === "warehouses" && (
              <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230] mb-3">Live Discovered SQL Warehouses</h3>
                {(computeData?.warehouses || []).length === 0 && (
                  <div className="text-xs text-slate-500 mb-2">No SQL warehouses discovered in this workspace scope.</div>
                )}
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                      <th className="py-2 px-3">Warehouse</th>
                      <th className="py-2 px-3">Class</th>
                      <th className="py-2 px-3">Size</th>
                      <th className="py-2 px-3">Uptime</th>
                      <th className="py-2 px-3">Avg Utilization</th>
                      <th className="py-2 px-3">Auto-Stop</th>
                      <th className="py-2 px-3 text-right">Cost</th>
                      <th className="py-2 px-3">State</th>
                      <th className="py-2 px-3">Recommendation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e5eaf1]">
                    {(computeData?.warehouses || []).map((w, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-semibold text-[#182230]">{w.name}</td>
                        <td className="py-2.5 px-3 font-bold text-blue-600">{w.warehouse_class}</td>
                        <td className="py-2.5 px-3">{w.size}</td>
                        <td className="py-2.5 px-3">{w.uptime}</td>
                        <td className="py-2.5 px-3">{w.avg_utilization}</td>
                        <td className="py-2.5 px-3">{w.auto_stop_mins === null ? "-" : `${w.auto_stop_mins} min`}</td>
                        <td className="py-2.5 px-3 text-right font-bold">{fmtMoney(w.cost_mtd, formatCost)}</td>
                        <td className="py-2.5 px-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                            {w.state}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-rose-600 font-semibold">{w.recommendation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Jobs Tab (live Jobs API; run metrics cover the retrieved window only) */}
            {computeTab === "jobs" && (
              <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230] mb-3">Live Discovered Jobs</h3>
                {(computeData?.jobs || []).length === 0 ? (
                  <div className="text-xs text-slate-500">No jobs exist in this workspace scope (confirmed by the Jobs API).</div>
                ) : (
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                        <th className="py-2 px-3">Job</th>
                        <th className="py-2 px-3">Runs (window)</th>
                        <th className="py-2 px-3">Success rate</th>
                        <th className="py-2 px-3">Avg duration</th>
                        <th className="py-2 px-3">Note</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#e5eaf1]">
                      {(computeData?.jobs || []).map((j, idx) => (
                        <tr key={idx} className="hover:bg-slate-50">
                          <td className="py-2.5 px-3 font-semibold text-[#182230]">{j.name}</td>
                          <td className="py-2.5 px-3">{fmtNumber(j.runs)}</td>
                          <td className="py-2.5 px-3">{j.success_rate}</td>
                          <td className="py-2.5 px-3">{j.avg_duration}</td>
                          <td className="py-2.5 px-3 text-slate-500">{j.signal}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {/* Heatmap Tab */}
            {computeTab === "utilization" && (
              <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230] mb-1">Compute utilization by hour and day</h3>
                <p className="text-[11px] text-[#667085] mb-4">168-hour utilization matrix (7 days x 24 hours)</p>
                {(computeData?.heatmap_utilization || []).length === 0 && (
                  <div className="p-4 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900">
                    {computeData?.provenance?.utilization?.message || "Utilization telemetry is not available."}
                    {computeData?.provenance?.utilization?.requirement && (
                      <div className="mt-1"><strong>To unblock:</strong> {computeData.provenance.utilization.requirement}</div>
                    )}
                  </div>
                )}
                <div className="grid grid-cols-24 gap-1 p-2 bg-slate-50 rounded-lg">
                  {(computeData?.heatmap_utilization || []).map((val, idx) => {
                    const intensity =
                      val > 75
                        ? "bg-blue-800 text-white"
                        : val > 50
                        ? "bg-blue-600 text-white"
                        : val > 25
                        ? "bg-blue-300 text-slate-800"
                        : "bg-slate-200 text-slate-600";
                    return (
                      <div
                        key={idx}
                        title={`Hour ${idx % 24}: ${val}% utilization`}
                        className={`h-7 rounded text-[9px] font-bold flex items-center justify-center ${intensity}`}
                      >
                        {val}%
                      </div>
                    );
                  })}
                </div>
                <div className="flex items-center gap-3 mt-3 text-xs text-[#667085]">
                  <span>Low utilization</span>
                  <span className="w-3 h-3 bg-slate-200 rounded"></span>
                  <span className="w-3 h-3 bg-blue-300 rounded"></span>
                  <span className="w-3 h-3 bg-blue-600 rounded"></span>
                  <span className="w-3 h-3 bg-blue-800 rounded"></span>
                  <span>High utilization</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 5: AI & TOKEN ECONOMICS */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "ai" && (
          <div className="space-y-6">
            <ProvenanceBanner provenance={aiData?.provenance} />

            <KpiCardGrid
              kpis={aiData?.kpis}
              specs={[
                { key: "ai_spend", label: "AI spend" },
                { key: "input_tokens", label: "Input tokens" },
                { key: "output_tokens", label: "Output tokens" },
                { key: "cached_tokens", label: "Cached tokens" },
                { key: "cost_per_1k_tokens", label: "Cost / 1K tokens" },
                { key: "cost_per_task", label: "Cost / successful task" },
              ]}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
              className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5"
            />

            {/* Sub-tabs */}
            <div className="flex gap-2 border-b border-[#e5eaf1]">
              {(["token", "models", "genie", "agents", "training", "unit"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setAiTab(t)}
                  className={`pb-2.5 px-3 text-xs font-semibold capitalize border-b-2 transition ${
                    aiTab === t ? "border-blue-600 text-blue-600" : "border-transparent text-[#667085] hover:text-[#182230]"
                  }`}
                >
                  {t === "token" && "Token Economics"}
                  {t === "models" && `Models & Endpoints (${aiData?.serving_endpoints.length ?? 0})`}
                  {t === "genie" && "Genie Economics"}
                  {t === "agents" && "Agents & Tools"}
                  {t === "training" && "Training & Eval"}
                  {t === "unit" && "Unit Economics"}
                </button>
              ))}
            </div>

            {/* Models & Endpoints Tab (Live 27 Endpoints from Azure Databricks) */}
            {aiTab === "models" && (
              <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <div className="flex justify-between items-center mb-3">
                  <div>
                    <h3 className="text-sm font-bold text-[#182230]">Live Discovered Model Serving Endpoints</h3>
                    <p className="text-[11px] text-[#667085]">Endpoints discovered via the Databricks Serving API on {effectiveWorkspaceId}. Usage columns need system.serving tables.</p>
                  </div>
                  <button
                    onClick={() => setIsModelModalOpen(true)}
                    className="px-3 py-1.5 rounded-lg bg-blue-600 text-white font-semibold text-xs hover:bg-blue-700 transition"
                  >
                    Add Model Rate Card
                  </button>
                </div>
                <div className="overflow-x-auto max-h-[460px]">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-slate-50">
                      <tr className="border-b border-[#e5eaf1] text-[10px] font-bold text-[#667085] uppercase">
                        <th className="py-2 px-3">Endpoint Name</th>
                        <th className="py-2 px-3">Serving Mode</th>
                        <th className="py-2 px-3 text-right">Requests / Day</th>
                        <th className="py-2 px-3">Capacity Util</th>
                        <th className="py-2 px-3">P95 Latency</th>
                        <th className="py-2 px-3">Availability</th>
                        <th className="py-2 px-3 text-right">Monthly Cost</th>
                        <th className="py-2 px-3">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#e5eaf1]">
                      {(aiData?.serving_endpoints || []).map((ep, idx) => (
                        <tr key={idx} className="hover:bg-slate-50">
                          <td className="py-2.5 px-3 font-semibold text-blue-600 font-mono text-[11px]">{ep.endpoint_name}</td>
                          <td className="py-2.5 px-3 text-[#667085]">{ep.serving_type}</td>
                          <td className="py-2.5 px-3 text-right">{ep.requests_per_day}</td>
                          <td className="py-2.5 px-3">{ep.capacity_utilization}</td>
                          <td className="py-2.5 px-3">{ep.p95_latency}</td>
                          <td className="py-2.5 px-3 font-semibold text-slate-700">{ep.availability}</td>
                          <td className="py-2.5 px-3 text-right font-bold">{fmtMoney(ep.monthly_cost, formatCost)}</td>
                          <td className="py-2.5 px-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700">
                              {ep.action}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Genie / Agents / Training / Unit economics: live data only, otherwise the reason */}
            {(aiTab === "genie" || aiTab === "agents" || aiTab === "training" || aiTab === "unit") && (
              <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                {aiTab === "training" && (aiData?.training || []).length > 0 ? (
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                        <th className="py-2 px-3">Experiment</th>
                        <th className="py-2 px-3">Runs (retrieved)</th>
                        <th className="py-2 px-3">Compute hrs</th>
                        <th className="py-2 px-3">Spend</th>
                        <th className="py-2 px-3">Decision</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#e5eaf1]">
                      {(aiData?.training || []).map((t, idx) => (
                        <tr key={idx}>
                          <td className="py-2.5 px-3 font-semibold text-[#182230]">{t.experiment_name}</td>
                          <td className="py-2.5 px-3">{t.runs}</td>
                          <td className="py-2.5 px-3 text-slate-500">{t.compute_hrs}</td>
                          <td className="py-2.5 px-3">{fmtMoney(t.spend, formatCost)}</td>
                          <td className="py-2.5 px-3 text-slate-500">{t.decision}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="text-xs text-slate-500">
                    {aiTab === "genie" && "Genie space economics are unavailable: no Genie usage telemetry source is connected."}
                    {aiTab === "agents" && "Agent economics are unavailable: no agent run/tool-cost telemetry source is connected."}
                    {aiTab === "training" && "No MLflow experiments were discovered in this workspace scope."}
                    {aiTab === "unit" && "Unit economics are unavailable: they require token usage and task outcome telemetry."}
                  </div>
                )}
              </div>
            )}

            {/* Token Tab */}
            {aiTab === "token" && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                <div className="lg:col-span-6 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                  <h3 className="text-sm font-bold text-[#182230] mb-1">Token consumption by model</h3>
                  <p className="text-[11px] text-[#667085] mb-4">Input, output and context cached token mix.</p>
                  <div className="space-y-3">
                    {(aiData?.token_consumption_by_model || []).length === 0 && (
                      <div className="text-xs text-slate-500">{aiData?.provenance?.usage?.message || "No token telemetry available."}</div>
                    )}
                    {(aiData?.token_consumption_by_model || []).map((m, idx) => (
                      <div key={idx} className="space-y-1">
                        <div className="flex justify-between text-xs font-semibold">
                          <span>{m.model}</span>
                          <span className="text-[#667085]">${m.spend.toLocaleString()}</span>
                        </div>
                        <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-600 rounded-full" style={{ width: `${m.tokens * 2}%` }}></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="lg:col-span-6 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                  <h3 className="text-sm font-bold text-[#182230] mb-3">Token cost drivers</h3>
                  <div className="divide-y divide-[#e5eaf1]">
                    {(aiData?.token_cost_drivers || []).map((d, idx) => (
                      <div key={idx} className="py-2.5 flex justify-between text-xs">
                        <span className="text-[#667085]">{d.driver}</span>
                        <span className={`font-bold ${d.is_deduction ? "text-emerald-700" : "text-[#182230]"}`}>
                          {d.amount}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 8: OPTIMIZATION ADVISOR */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "recommend" && (
          <div className="space-y-6">
            <ProvenanceBanner provenance={advisorData?.provenance} />

            {/* Savings KPIs: only calculable values are shown; otherwise the reason is */}
            <KpiCardGrid
              kpis={advisorData?.kpis}
              specs={[
                { key: "potential_savings", label: "Potential monthly savings" },
                { key: "approved_savings", label: "Approved / staged savings" },
                { key: "awaiting_approval", label: "Awaiting approval" },
                { key: "quick_wins", label: "Configuration findings" },
                { key: "implemented_savings", label: "Implemented savings" },
                { key: "realized_savings", label: "Verified realized savings" },
              ]}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
              className="grid grid-cols-2 lg:grid-cols-6 gap-3"
            />

            {/* Zero-Execution Policy & Governance Enforcement Banner */}
            <div className="bg-emerald-50/80 border border-emerald-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shadow-2xs">
              <div className="flex items-start sm:items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-800 flex items-center justify-center shrink-0">
                  <ShieldAlert className="w-4 h-4 text-emerald-700" />
                </div>
                <div>
                  <div className="font-bold text-emerald-950 flex items-center gap-2">
                    <span>Zero-Execution Policy &amp; Least-Privilege Governance Enforced</span>
                    <span className="px-1.5 py-0.2 rounded bg-emerald-200 text-emerald-900 font-mono text-[10px]">
                      READ-ONLY
                    </span>
                  </div>
                  <p className="text-emerald-800 text-[11px] mt-0.5">
                    Clicking &ldquo;Approve for change&rdquo; records workflow approval and audit history in the platform only. The platform NEVER modifies cloud resources, resizes compute clusters, alters SQL warehouses, or triggers infrastructure mutations.
                  </p>
                </div>
              </div>
              <div className="shrink-0 flex items-center gap-2 text-[10px] text-emerald-900 font-semibold bg-emerald-100/80 px-2.5 py-1 rounded-md border border-emerald-200">
                <span>SQL warehouse {ingestionStatus?.warehouse_id || "—"}:</span>
                <span className="font-mono text-slate-600 bg-white px-1.5 py-0.5 rounded border border-slate-300">
                  {ingestionStatus?.warehouse_status || "UNKNOWN"}
                </span>
              </div>
            </div>

            {/* Filter Toolbar for Recommendations */}
            <div className="flex items-center justify-between gap-4 flex-wrap bg-white border border-[#e5eaf1] rounded-xl p-3 shadow-2xs">
              <div className="flex items-center gap-2 flex-wrap text-xs">
                <span className="text-slate-500 font-medium">Filter Recommendations:</span>
                <select
                  value={recCategoryFilter}
                  onChange={(e) => setRecCategoryFilter(e.target.value)}
                  className="bg-white border border-[#e5eaf1] px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-700 shadow-2xs"
                  aria-label="Recommendation category filter"
                >
                  <option value="all">All Categories</option>
                  <option value="idle">Idle Resources</option>
                  <option value="sizing">Right-Sizing</option>
                  <option value="serverless">Serverless</option>
                  <option value="storage">Storage</option>
                </select>
                <select
                  value={recImpactFilter}
                  onChange={(e) => setRecImpactFilter(e.target.value)}
                  className="bg-white border border-[#e5eaf1] px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-700 shadow-2xs"
                  aria-label="Recommendation impact filter"
                >
                  <option value="all">All Impacts</option>
                  <option value="High">High Impact</option>
                  <option value="Medium">Medium Impact</option>
                  <option value="Low">Low Impact</option>
                </select>
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
                  <input
                    type="text"
                    value={recSearch}
                    onChange={(e) => setRecSearch(e.target.value)}
                    placeholder="Search recommendations..."
                    className="bg-white border border-[#e5eaf1] pl-7 pr-3 py-1.5 rounded-lg text-xs w-52"
                    aria-label="Search recommendations"
                  />
                </div>
              </div>
            </div>

            {/* List of Evidence-Backed Recommendations */}
            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs divide-y divide-[#e5eaf1]">
              {(advisorData?.recommendations || []).length === 0 && (
                <div className="py-6 text-center text-xs text-slate-500">
                  No configuration findings for the discovered resources in this scope.
                </div>
              )}
              {(advisorData?.recommendations || [])
                .filter((rec) => {
                  if (recImpactFilter !== "all" && rec.impact !== recImpactFilter) return false;
                  if (recCategoryFilter !== "all") {
                    const desc = (rec.title + " " + rec.description).toLowerCase();
                    if (recCategoryFilter === "idle" && !desc.includes("idle") && !desc.includes("unused"))
                      return false;
                    if (
                      recCategoryFilter === "sizing" &&
                      !desc.includes("sizing") &&
                      !desc.includes("oversized") &&
                      !desc.includes("scale")
                    )
                      return false;
                    if (
                      recCategoryFilter === "serverless" &&
                      !desc.includes("serverless") &&
                      !desc.includes("classic")
                    )
                      return false;
                    if (
                      recCategoryFilter === "storage" &&
                      !desc.includes("storage") &&
                      !desc.includes("photon") &&
                      !desc.includes("delta")
                    )
                      return false;
                  }
                  if (recSearch) {
                    const q = recSearch.toLowerCase();
                    if (!rec.title.toLowerCase().includes(q) && !rec.description.toLowerCase().includes(q))
                      return false;
                  }
                  return true;
                })
                .map((rec, idx) => (
                  <div key={rec.id || idx} className="py-5 flex items-start gap-4">
                    <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 font-bold flex items-center justify-center shrink-0 text-sm">
                      {idx + 1}
                    </div>
                    <div className="flex-1 space-y-2">
                      <div className="flex justify-between items-start flex-wrap gap-2">
                        <div>
                          <h4 className="text-sm font-bold text-[#182230]">{rec.title}</h4>
                          <div className="text-[11px] text-[#667085] mt-0.5">
                            <span className="font-semibold text-slate-700">Affected Scope:</span>{" "}
                            <span className="font-mono text-slate-800">
                              {rec.resource_name || rec.resource_id}
                            </span>{" "}
                            (Workspace: {effectiveWorkspaceId})
                          </div>
                        </div>
                        <div className="text-right">
                          <span className="text-sm font-black text-emerald-700">
                            {rec.formatted_savings}
                          </span>
                          <span className="text-[10px] text-slate-400 block">Savings (only when calculable)</span>
                        </div>
                      </div>

                      {/* Inefficiency Finding & Recommended Action */}
                      <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1.5 text-xs">
                        <div>
                          <span className="font-semibold text-slate-900">Identified Inefficiency:</span>{" "}
                          <span className="text-slate-700">{rec.finding || rec.description}</span>
                        </div>
                        <div>
                          <span className="font-semibold text-slate-900">Recommended Action:</span>{" "}
                          <span className="text-slate-700 font-medium">
                            {rec.recommended_action || rec.title}
                          </span>
                        </div>
                        <div>
                          <span className="font-semibold text-slate-900">
                            Calculation Methodology &amp; Telemetry Source:
                          </span>{" "}
                          <span className="text-slate-600 font-mono text-[11px]">
                            {rec.calculation_methodology || "Not provided"}
                          </span>
                        </div>
                      </div>

                      {/* Evidence & Governance Badges */}
                      <div className="flex items-center gap-2 text-[11px] flex-wrap pt-1">
                        <span
                          className={`px-2 py-0.5 rounded font-bold ${
                            rec.status === "Approved"
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : rec.status === "Deferred"
                              ? "bg-slate-100 text-slate-600"
                              : "bg-amber-50 text-amber-700 border border-amber-200"
                          }`}
                        >
                          Status: {rec.status}
                        </span>
                        <span className="bg-brand-50 text-brand-700 px-2 py-0.5 rounded font-bold border border-brand-200">
                          Lifecycle: {rec.lifecycle_stage || "Detected"}
                        </span>
                        <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-semibold">
                          Confidence: {rec.confidence_pct}%
                        </span>
                        <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-semibold">
                          Effort: {rec.effort}
                        </span>
                        <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-semibold">
                          Risk: {rec.risk || rec.impact}
                        </span>
                        <span className="text-slate-500">Owner: {rec.owner}</span>
                        {rec.source_timestamp && (
                          <span className="text-slate-500">Source: {new Date(rec.source_timestamp).toISOString().replace("T", " ").slice(0, 19)} UTC</span>
                        )}
                        <span className="text-slate-500">
                          Realized: Not verified (requires post-change billing comparison)
                        </span>
                      </div>

                      {/* Action Buttons */}
                      <div className="flex items-center gap-2 pt-2">
                        <button
                          type="button"
                          onClick={() => handleDecisionAction(rec.id, "Approved")}
                          className={`px-3 py-1.5 rounded text-xs font-semibold transition ${
                            rec.status === "Approved"
                              ? "bg-emerald-600 text-white hover:bg-emerald-700"
                              : "bg-blue-600 hover:bg-blue-700 text-white"
                          }`}
                        >
                          {rec.status === "Approved" ? "✓ Approved (Workflow State)" : "Approve for change"}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setModalTitle(rec.title);
                            setModalBody(
                              `${rec.evidence}\n\n[CALCULATION METHODOLOGY]\n${
                                rec.calculation_methodology || "Not provided"
                              }\n\n[RECOMMENDED ACTION]\n${
                                rec.recommended_action || rec.title
                              }\n\n[ZERO-EXECUTION NOTICE]\nWorkflow state change only; no cloud infrastructure modified.`
                            );
                            setIsDetailModalOpen(true);
                          }}
                          className="px-3 py-1.5 rounded border border-[#e5eaf1] bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                        >
                          View evidence &amp; telemetry
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDecisionAction(rec.id, "Deferred")}
                          className="px-3 py-1.5 rounded border border-[#e5eaf1] bg-white text-xs font-semibold text-slate-500 hover:bg-slate-50 transition"
                        >
                          Defer
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 9: FORECAST & BUDGETS (With Certified Telemetry & Scenario Simulator) */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "forecast" && (
          <div className="space-y-6">
            <ProvenanceBanner provenance={forecastData?.provenance} />

            {/* Method & provenance: forecasts are always distinguished from actuals */}
            <div className="bg-white border border-[#e5eaf1] rounded-xl p-4 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
              <p className="text-[11px] text-slate-500">
                <span className="font-semibold text-slate-700">Method:</span> forecast = month-to-date actual + trailing 7-day average x remaining days of the month.
                It is an <strong>estimate</strong> and is produced only with at least 14 days of ingested billing history. Budgets come from configuration
                (<code>FINOPS_MONTHLY_BUDGET_USD</code>); none are assumed.
              </p>
              <div className="flex items-center gap-2 shrink-0">
                <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 text-[10px] font-bold uppercase">Actuals: CALCULATED</span>
                <span className="px-2 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200 text-[10px] font-bold uppercase">Forecast: ESTIMATED</span>
              </div>
            </div>

            <KpiCardGrid
              kpis={forecastData?.kpis}
              specs={[
                { key: "approved_budget", label: "Approved monthly budget" },
                { key: "actual_mtd", label: "Actual spend (month to date)" },
                { key: "forecast_month_end", label: "Forecast month-end (estimate)" },
                { key: "projected_overrun", label: "Projected overrun" },
                { key: "budget_utilization", label: "Budget utilization" },
                { key: "forecast_confidence", label: "Forecast confidence" },
                { key: "forecast_accuracy", label: "Forecast accuracy (MAPE)" },
              ]}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
              className="grid grid-cols-2 lg:grid-cols-4 gap-4"
            />

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              {/* Budget burn: cumulative actuals vs configured budget */}
              <div className="lg:col-span-7 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230]">Budget burn</h3>
                <p className="text-[11px] text-[#667085] mb-2">Cumulative actual spend versus the configured monthly budget.</p>
                {(() => {
                  const burn = forecastData?.budget_burn || [];
                  if (burn.length === 0) {
                    return (
                      <div className="h-48 flex items-center justify-center text-center text-xs text-slate-500 px-6">
                        Budget burn needs both a configured budget and ingested billing rows.
                      </div>
                    );
                  }
                  const max = Math.max(...burn.map((b) => Math.max(b.actual, b.budget)), 1);
                  const stepX = burn.length > 1 ? 480 / (burn.length - 1) : 0;
                  const y = (v: number) => 170 - (v / max) * 160;
                  const actual = burn.map((b, i) => `${10 + i * stepX},${y(b.actual)}`).join(" ");
                  return (
                    <div className="h-56 w-full flex items-end pt-4">
                      <svg className="w-full h-full overflow-visible" viewBox="0 0 500 180" role="img" aria-label="Cumulative spend versus budget">
                        <line x1="10" y1={y(burn[0].budget)} x2="490" y2={y(burn[0].budget)} stroke="#f59e0b" strokeWidth="2" strokeDasharray="4 3" />
                        <polyline points={actual} fill="none" stroke="#2563eb" strokeWidth="2.5" />
                      </svg>
                    </div>
                  );
                })()}
              </div>

              {/* Scenario simulator: runs on the real forecast only */}
              <div className="lg:col-span-5 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs space-y-4">
                <div>
                  <h3 className="text-sm font-bold text-[#182230]">Scenario simulator</h3>
                  <p className="text-[11px] text-[#667085]">
                    Adjust levers on top of the estimated month-end forecast. Unavailable until a forecast exists.
                  </p>
                </div>
                <div className="space-y-3.5">
                  {[
                    { id: "compute-opt-slider", label: "Compute rightsizing (%)", min: 0, max: 30, value: computeSlider, set: (v: number) => { setComputeSlider(v); handleRecalculateScenario(v, tokenSlider, growthSlider); } },
                    { id: "token-opt-slider", label: "AI spend reduction (%)", min: 0, max: 50, value: tokenSlider, set: (v: number) => { setTokenSlider(v); handleRecalculateScenario(computeSlider, v, growthSlider); } },
                    { id: "workload-growth-slider", label: "Workload growth (%)", min: -10, max: 40, value: growthSlider, set: (v: number) => { setGrowthSlider(v); handleRecalculateScenario(computeSlider, tokenSlider, v); } },
                  ].map((sl) => (
                    <div key={sl.id}>
                      <div className="flex justify-between text-xs font-semibold mb-1">
                        <label htmlFor={sl.id}>{sl.label}</label>
                        <span className="text-blue-600 font-bold">{sl.value}%</span>
                      </div>
                      <input
                        id={sl.id}
                        type="range"
                        min={sl.min}
                        max={sl.max}
                        value={sl.value}
                        onChange={(e) => sl.set(Number(e.target.value))}
                        className="w-full accent-blue-600"
                      />
                    </div>
                  ))}
                  <div className="p-3.5 rounded-xl bg-blue-50/80 border border-blue-200">
                    <div className="flex items-center justify-between">
                      <div className="text-[11px] font-bold text-blue-900 uppercase">Scenario projected spend</div>
                      {simResult?.status && (
                        <span className={`text-[8px] px-1.5 py-0.5 rounded font-bold uppercase ${statusBadgeClass(simResult.status)}`}>
                          {statusLabel(simResult.status)}
                        </span>
                      )}
                    </div>
                    <div className="text-xl font-black text-blue-950 my-1">
                      {simResult?.formatted_spend || "-"}
                    </div>
                    <div className={`text-xs font-bold ${simResult?.is_favorable ? "text-emerald-700" : "text-slate-600"}`}>
                      {simResult?.delta_label || "Needs an ingested billing history to forecast."}
                    </div>
                    {simResult?.message && <div className="text-[10px] text-slate-500 mt-1">{simResult.message}</div>}
                  </div>
                </div>
              </div>
            </div>

            {/* Budget controls: configured budgets only */}
            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-3">Scope Budget Controls & Threshold Tracking</h3>
              {(forecastData?.budget_controls || []).length === 0 ? (
                <div className="text-xs text-slate-500">No budgets are configured. Set <code>FINOPS_MONTHLY_BUDGET_USD</code> to enable budget tracking.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                        <th className="py-2.5 px-3">Budget Scope</th>
                        <th className="py-2.5 px-3">Owner</th>
                        <th className="py-2.5 px-3">Approved Budget</th>
                        <th className="py-2.5 px-3">Actual MTD</th>
                        <th className="py-2.5 px-3">Month-End Forecast (est.)</th>
                        <th className="py-2.5 px-3">Burn Rate</th>
                        <th className="py-2.5 px-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#e5eaf1]">
                      {(forecastData?.budget_controls || []).map((bc, idx) => (
                        <tr key={idx} className="hover:bg-slate-50">
                          <td className="py-2.5 px-3 font-semibold text-slate-800">{bc.budget_scope}</td>
                          <td className="py-2.5 px-3 text-[#667085]">{bc.owner}</td>
                          <td className="py-2.5 px-3 font-bold">{fmtMoney(bc.budget, formatCost)}</td>
                          <td className="py-2.5 px-3 font-semibold text-slate-700">{fmtMoney(bc.actual, formatCost)}</td>
                          <td className="py-2.5 px-3 font-bold text-blue-700">{fmtMoney(bc.forecast, formatCost)}</td>
                          <td className="py-2.5 px-3">{bc.burn_pct === null ? "-" : `${bc.burn_pct}%`}</td>
                          <td className="py-2.5 px-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                              {bc.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 10: ANOMALY DETECTION */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "anomaly" && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-base font-bold text-[#182230]">Cost & Usage Anomaly Queue</h2>
                <p className="text-xs text-[#667085]">Statistical spike detection over ingested daily billing history (needs at least 14 days).</p>
              </div>
              <button
                onClick={() => loadModuleData()}
                className="px-3.5 py-1.5 rounded-lg bg-blue-600 text-white font-semibold text-xs hover:bg-blue-700 transition"
              >
                Refresh detection
              </button>
            </div>

            <ProvenanceBanner provenance={anomalyData?.provenance} />
            <KpiCardGrid
              kpis={anomalyData?.kpis}
              specs={[
                { key: "open_anomalies", label: "Open anomalies" },
                { key: "potential_exposure", label: "Potential exposure" },
                { key: "mean_time_to_detect", label: "Mean time to detect" },
                { key: "auto_triaged", label: "Auto-triaged" },
              ]}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
            />

            {/* Filter Toolbar for Anomalies */}
            <div className="flex items-center justify-between gap-4 flex-wrap bg-white border border-[#e5eaf1] rounded-xl p-3 shadow-2xs">
              <div className="flex items-center gap-2 flex-wrap text-xs">
                <span className="text-slate-500 font-medium">Filter Queue:</span>
                <select
                  value={anomalySeverityFilter}
                  onChange={(e) => setAnomalySeverityFilter(e.target.value)}
                  className="bg-white border border-[#e5eaf1] px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-700 shadow-2xs"
                  aria-label="Anomaly severity filter"
                >
                  <option value="all">All Severities</option>
                  <option value="Critical">Critical</option>
                  <option value="High">High</option>
                  <option value="Medium">Medium</option>
                </select>
                <select
                  value={anomalyStatusFilter}
                  onChange={(e) => setAnomalyStatusFilter(e.target.value)}
                  className="bg-white border border-[#e5eaf1] px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-700 shadow-2xs"
                  aria-label="Anomaly status filter"
                >
                  <option value="all">All Statuses</option>
                  <option value="New">New</option>
                  <option value="Investigating">Investigating</option>
                  <option value="Acknowledged">Acknowledged</option>
                  <option value="Resolved">Resolved</option>
                </select>
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
                  <input
                    type="text"
                    value={anomalySearch}
                    onChange={(e) => setAnomalySearch(e.target.value)}
                    placeholder="Search anomaly signal, resource..."
                    className="bg-white border border-[#e5eaf1] pl-7 pr-3 py-1.5 rounded-lg text-xs w-56"
                    aria-label="Search anomalies"
                  />
                </div>
              </div>
            </div>

            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                    <th className="py-2.5 px-3">Detected</th>
                    <th className="py-2.5 px-3">Severity</th>
                    <th className="py-2.5 px-3">Signal</th>
                    <th className="py-2.5 px-3">Resource</th>
                    <th className="py-2.5 px-3">Baseline</th>
                    <th className="py-2.5 px-3">Observed</th>
                    <th className="py-2.5 px-3">Impact</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#e5eaf1]">
                  {(anomalyData?.anomalies || []).length === 0 && (
                    <tr>
                      <td colSpan={9} className="py-8 text-center text-xs text-slate-500">
                        {anomalyData?.provenance?.detection?.message || "No anomalies detected in the ingested billing history."}
                      </td>
                    </tr>
                  )}
                  {(anomalyData?.anomalies || []).filter((anom) => {
                    if (anomalySeverityFilter !== "all" && anom.severity !== anomalySeverityFilter) return false;
                    if (anomalyStatusFilter !== "all" && (anom.status || "New") !== anomalyStatusFilter) return false;
                    if (anomalySearch) {
                      const q = anomalySearch.toLowerCase();
                      if (
                        !anom.signal.toLowerCase().includes(q) &&
                        !anom.resource.toLowerCase().includes(q) &&
                        !anom.detected.toLowerCase().includes(q)
                      ) {
                        return false;
                      }
                    }
                    return true;
                  }).map((anom, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="py-2.5 px-3 text-[#667085]">{anom.detected}</td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            anom.severity === "Critical"
                              ? "bg-rose-100 text-rose-800"
                              : anom.severity === "High"
                              ? "bg-rose-50 text-rose-700"
                              : "bg-amber-50 text-amber-700"
                          }`}
                        >
                          {anom.severity}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-semibold text-[#182230]">{anom.signal}</td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">{anom.resource}</td>
                      <td className="py-2.5 px-3 text-[#667085]">{anom.baseline}</td>
                      <td className="py-2.5 px-3 font-bold text-rose-600">{anom.observed}</td>
                      <td className="py-2.5 px-3 font-bold text-rose-700">{anom.estimated_impact}</td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                          {anom.status || "New"}
                        </span>
                      </td>
                      <td className="py-2.5 px-3">
                        <button
                          onClick={() => setSelectedAnomaly(anom)}
                          className="px-2.5 py-1 rounded border border-brand-300 bg-brand-50 text-[11px] font-semibold text-brand-700 hover:bg-brand-100 transition shadow-2xs"
                        >
                          Investigate →
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 15: SETTINGS & INTEGRATIONS (With Verified System Tables) */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "settings" && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              <div className="lg:col-span-6 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230] mb-3">Connected Data Sources</h3>
                <div className="divide-y divide-[#e5eaf1]">
                  {(settingsData?.connected_sources || []).map((s, idx) => (
                    <div key={idx} className="py-2.5 flex justify-between items-center text-xs">
                      <div>
                        <div className="font-semibold text-[#182230]">{s.source_name}</div>
                        <div className="text-[11px] text-[#667085]">{s.details}</div>
                      </div>
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                          s.status === "Connected" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"
                        }`}
                      >
                        {s.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* System Tables Readiness Card */}
              <div className="lg:col-span-6 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-bold text-[#182230]">System Tables Metadata</h3>
                  <span className="bg-slate-100 text-slate-700 font-bold px-2 py-0.5 rounded text-[10px]">
                    Metadata only
                  </span>
                </div>
                <p className="text-[11px] text-[#667085] mb-3">
                  Table existence and SELECT grants discovered through the Unity Catalog API. Row-level access has not been exercised: no SQL is executed without approval.
                </p>
                {(settingsData?.system_tables_readiness?.key_tables || []).length === 0 && (
                  <div className="text-xs text-slate-500 mb-2">System table metadata has not been discovered for this workspace.</div>
                )}
                <div className="space-y-1.5 text-xs">
                  {(settingsData?.system_tables_readiness?.key_tables || []).map((tbl, idx) => (
                    <div key={idx} className="flex justify-between items-center py-1 border-b border-slate-100">
                      <span className="font-mono text-[11px] text-blue-700 font-semibold">{tbl.name}</span>
                      <span className="text-slate-500">{tbl.columns_count} columns · {tbl.status}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 p-2.5 rounded bg-amber-50 border border-amber-200 text-[11px] text-amber-800">
                  <strong>Safety Status:</strong> {settingsData?.system_tables_readiness?.sql_execution_note}
                </div>
              </div>
            </div>

            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-3">Ingestion Pipeline Health</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 text-xs">
                {(settingsData?.pipeline_health || []).map((m, idx) => (
                  <div key={idx} className="flex justify-between py-1.5 border-b border-slate-100">
                    <span className="text-[#667085]">{m.metric_name}</span>
                    <span className="font-semibold text-[#182230]">{m.metric_value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Commercial Rate Card */}
            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-1">Rate Card (list prices)</h3>
              <p className="text-[11px] text-[#667085] mb-3">Used only to price ingested usage rows. These are not actual billing records and do not include discounts.</p>
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                    <th className="py-2 px-3">Provider</th>
                    <th className="py-2 px-3">SKU Family</th>
                    <th className="py-2 px-3">Region</th>
                    <th className="py-2 px-3">List Rate</th>
                    <th className="py-2 px-3">Contract Rate</th>
                    <th className="py-2 px-3">Discount</th>
                    <th className="py-2 px-3">Effective Date</th>
                    <th className="py-2 px-3">Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#e5eaf1]">
                  {(settingsData?.rate_cards || []).map((r, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="py-2.5 px-3 font-semibold">{r.provider}</td>
                      <td className="py-2.5 px-3">{r.sku_family}</td>
                      <td className="py-2.5 px-3">{r.region}</td>
                      <td className="py-2.5 px-3">{r.list_rate}</td>
                      <td className="py-2.5 px-3 text-slate-600">{r.contract_rate}</td>
                      <td className="py-2.5 px-3 text-slate-600">{r.discount}</td>
                      <td className="py-2.5 px-3 text-[#667085]">{r.effective_date}</td>
                      <td className="py-2.5 px-3 text-[#667085]">{r.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 6: DATA & STORAGE */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "data" && (
          <div className="space-y-6">
            <ProvenanceBanner provenance={storageData?.provenance} />
            <KpiCardGrid
              kpis={storageData?.kpis}
              specs={Object.keys(storageData?.kpis || {}).map((k) => ({
                key: k,
                label: k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
              }))}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
            />

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              <div className="lg:col-span-6 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230] mb-3">Storage Tiers Distribution</h3>
                <div className="space-y-2">
                  {(storageData?.storage_tiers || []).map((st, idx) => (
                    <div key={idx} className="flex justify-between items-center py-2 border-b border-slate-100 text-xs">
                      <span className="font-semibold text-slate-800">{st.tier}</span>
                      <span className="text-slate-600">{st.tb} TB ({Math.round(st.share * 100)}%)</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="lg:col-span-6 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230] mb-3">Lifecycle Optimization Opportunities</h3>
                <div className="space-y-2">
                  {(storageData?.lifecycle_opportunities || []).map((opp, idx) => (
                    <div key={idx} className="flex justify-between items-center py-2 border-b border-slate-100 text-xs">
                      <span className="text-slate-700">{opp.opportunity}</span>
                      <span className="font-bold text-emerald-600">{opp.metric}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-3">Delta Lake Tables & Catalogs</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                      <th className="py-2 px-3">Catalog / Schema / Table</th>
                      <th className="py-2 px-3">Type</th>
                      <th className="py-2 px-3">Size</th>
                      <th className="py-2 px-3">Last Read</th>
                      <th className="py-2 px-3">Retention</th>
                      <th className="py-2 px-3">Monthly Cost</th>
                      <th className="py-2 px-3">Recommendation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e5eaf1]">
                    {(storageData?.tables || []).map((t, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-mono font-medium text-blue-700">{t.catalog_schema_table}</td>
                        <td className="py-2.5 px-3 text-slate-600">{t.storage_type}</td>
                        <td className="py-2.5 px-3">{t.size}</td>
                        <td className="py-2.5 px-3 text-[#667085]">{t.last_read}</td>
                        <td className="py-2.5 px-3 text-[#667085]">{t.retention}</td>
                        <td className="py-2.5 px-3 font-bold text-slate-800">{fmtMoney(t.monthly_cost, formatCost)}</td>
                        <td className="py-2.5 px-3 text-slate-500">{t.recommendation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 7: NETWORK & CLOUD INFRASTRUCTURE */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "network" && (
          <div className="space-y-6">
            <ProvenanceBanner provenance={networkData?.provenance} />
            <KpiCardGrid
              kpis={networkData?.kpis}
              specs={Object.keys(networkData?.kpis || {}).map((k) => ({
                key: k,
                label: k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
              }))}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
            />

            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-3">Cloud Infrastructure & Network Components</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                      <th className="py-2 px-3">Provider</th>
                      <th className="py-2 px-3">Service</th>
                      <th className="py-2 px-3">Resource</th>
                      <th className="py-2 px-3">Region</th>
                      <th className="py-2 px-3">Usage Driver</th>
                      <th className="py-2 px-3">Cost MTD</th>
                      <th className="py-2 px-3">Allocation</th>
                      <th className="py-2 px-3">Opportunity</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e5eaf1]">
                    {(networkData?.components || []).map((c, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-semibold text-slate-700">{c.provider}</td>
                        <td className="py-2.5 px-3">{c.service}</td>
                        <td className="py-2.5 px-3 font-mono text-blue-700">{c.resource}</td>
                        <td className="py-2.5 px-3 text-[#667085]">{c.region}</td>
                        <td className="py-2.5 px-3 text-slate-600">{c.usage_driver}</td>
                        <td className="py-2.5 px-3 font-bold text-slate-800">{fmtMoney(c.cost_mtd, formatCost)}</td>
                        <td className="py-2.5 px-3">{c.allocation}</td>
                        <td className="py-2.5 px-3 text-slate-500">{c.opportunity}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 11: GOVERNANCE & POLICIES */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "governance" && (
          <div className="space-y-6">
            <ProvenanceBanner provenance={govData?.provenance} />
            <KpiCardGrid
              kpis={govData?.kpis}
              specs={Object.keys(govData?.kpis || {}).map((k) => ({
                key: k,
                label: k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
              }))}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
            />

            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-3">Cluster Policy Catalogue</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                      <th className="py-2 px-3">Policy Name</th>
                      <th className="py-2 px-3">Scope</th>
                      <th className="py-2 px-3">Control</th>
                      <th className="py-2 px-3">Enforcement</th>
                      <th className="py-2 px-3">Owner</th>
                      <th className="py-2 px-3">Exceptions</th>
                      <th className="py-2 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e5eaf1]">
                    {(govData?.policies || []).map((p, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-semibold text-slate-800">{p.policy_name}</td>
                        <td className="py-2.5 px-3 text-[#667085]">{p.scope}</td>
                        <td className="py-2.5 px-3">{p.control}</td>
                        <td className="py-2.5 px-3 font-medium text-blue-700">{p.enforcement}</td>
                        <td className="py-2.5 px-3 text-slate-600">{p.owner}</td>
                        <td className="py-2.5 px-3">{p.exceptions ?? "-"}</td>
                        <td className="py-2.5 px-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                            {p.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              <div className="lg:col-span-6 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230] mb-3">Governance Verification Checklist</h3>
                <div className="space-y-2">
                  {(govData?.checklist || []).map((item, idx) => (
                    <div key={idx} className="flex items-center gap-2 text-xs py-1">
                      <CheckCircle2 className={`w-4 h-4 ${item.checked ? "text-emerald-600" : "text-slate-300"}`} />
                      <span className={item.checked ? "text-slate-800" : "text-slate-500"}>{item.label}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="lg:col-span-6 bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
                <h3 className="text-sm font-bold text-[#182230] mb-3">Approval Workflow Steps</h3>
                <ol className="list-decimal list-inside space-y-1.5 text-xs text-slate-700">
                  {(govData?.workflow_steps || []).map((step, idx) => (
                    <li key={idx} className="py-0.5">{step}</li>
                  ))}
                </ol>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 12: SHOWBACK & CHARGEBACK */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "chargeback" && (
          <div className="space-y-6">
            <ProvenanceBanner provenance={chargebackData?.provenance} />
            <KpiCardGrid
              kpis={chargebackData?.kpis}
              specs={Object.keys(chargebackData?.kpis || {}).map((k) => ({
                key: k,
                label: k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
              }))}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
            />

            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-3">Business Unit Showback & Chargeback Statements</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                      <th className="py-2 px-3">Business Unit</th>
                      <th className="py-2 px-3">Direct Compute</th>
                      <th className="py-2 px-3">AI Tokens</th>
                      <th className="py-2 px-3">Storage</th>
                      <th className="py-2 px-3">Shared Allocation</th>
                      <th className="py-2 px-3">Total Billed</th>
                      <th className="py-2 px-3">Budget Variance</th>
                      <th className="py-2 px-3">Trend</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e5eaf1]">
                    {(chargebackData?.statements || []).map((s, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-semibold text-slate-800">{s.business_unit}</td>
                        <td className="py-2.5 px-3">${s.direct_compute.toLocaleString()}</td>
                        <td className="py-2.5 px-3">${s.ai_tokens.toLocaleString()}</td>
                        <td className="py-2.5 px-3">{fmtMoney(s.storage, formatCost)}</td>
                        <td className="py-2.5 px-3">{fmtMoney(s.shared_allocation, formatCost)}</td>
                        <td className="py-2.5 px-3 font-bold text-blue-700">${s.total.toLocaleString()}</td>
                        <td className="py-2.5 px-3 font-semibold text-slate-700">{s.budget_variance}</td>
                        <td className="py-2.5 px-3 text-[#667085]">{s.trend}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 13: WORKLOAD ECONOMICS */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "workloads" && (
          <div className="space-y-6">
            <ProvenanceBanner provenance={workloadData?.provenance} />
            <KpiCardGrid
              kpis={workloadData?.kpis}
              specs={Object.keys(workloadData?.kpis || {}).map((k) => ({
                key: k,
                label: k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
              }))}
              onSelect={handleKpiClick}
              loading={isLoading}
              error={!!error}
            />

            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-3">Workload Unit Economics & Efficiency</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                      <th className="py-2 px-3">Workload</th>
                      <th className="py-2 px-3">Type</th>
                      <th className="py-2 px-3">Owner</th>
                      <th className="py-2 px-3">Monthly Spend</th>
                      <th className="py-2 px-3">Volume</th>
                      <th className="py-2 px-3">Unit Cost</th>
                      <th className="py-2 px-3">SLA / Quality</th>
                      <th className="py-2 px-3">Business Outcome</th>
                      <th className="py-2 px-3">Efficiency Trend</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e5eaf1]">
                    {(workloadData?.workloads || []).map((w, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-semibold text-slate-800">{w.workload}</td>
                        <td className="py-2.5 px-3 text-[#667085]">{w.workload_type}</td>
                        <td className="py-2.5 px-3 text-slate-600">{w.owner}</td>
                        <td className="py-2.5 px-3 font-bold text-slate-800">{fmtMoney(w.monthly_spend, formatCost)}</td>
                        <td className="py-2.5 px-3">{w.volume}</td>
                        <td className="py-2.5 px-3 font-mono font-medium text-blue-700">{w.unit_cost}</td>
                        <td className="py-2.5 px-3 text-slate-500">{w.sla_quality}</td>
                        <td className="py-2.5 px-3 text-slate-600">{w.business_outcome}</td>
                        <td className="py-2.5 px-3 text-slate-500">{w.efficiency_trend}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* MODULE 14: REPORTS & AUDIT */}
        {/* ------------------------------------------------------------------ */}
        {activeModule === "reports" && (
          <div className="space-y-6">
            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-3">Available FinOps Report Packs</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {(reportsData?.report_packs || []).map((rp, idx) => (
                  <div key={idx} className="border border-slate-200 rounded-lg p-4 bg-slate-50 hover:bg-white hover:border-blue-400 transition">
                    <div className="text-xs font-bold text-slate-900">{rp.title}</div>
                    <div className="text-[11px] text-slate-500 mt-1">{rp.subtitle}</div>
                    <div className="mt-3 flex justify-between items-center">
                      <span className="text-[10px] font-mono bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-semibold">
                        {rp.format}
                      </span>
                      <button
                        onClick={() => {
                          setExportReportType(rp.title);
                          setIsExportModalOpen(true);
                        }}
                        className="text-xs font-bold text-blue-600 hover:text-blue-800 flex items-center gap-1"
                      >
                        <Download className="w-3.5 h-3.5" /> Export
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white border border-[#e5eaf1] rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-[#182230] mb-3">FinOps Governance Audit Trail</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#e5eaf1] bg-slate-50 text-[10px] font-bold text-[#667085] uppercase">
                      <th className="py-2 px-3">Timestamp</th>
                      <th className="py-2 px-3">Actor</th>
                      <th className="py-2 px-3">Event</th>
                      <th className="py-2 px-3">Resource</th>
                      <th className="py-2 px-3">Before</th>
                      <th className="py-2 px-3">After</th>
                      <th className="py-2 px-3">Approval Reference</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e5eaf1]">
                    {(reportsData?.audit_events || []).map((e, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-mono text-[#667085]">{e.timestamp}</td>
                        <td className="py-2.5 px-3 font-semibold text-slate-800">{e.actor}</td>
                        <td className="py-2.5 px-3 text-blue-700 font-medium">{e.event}</td>
                        <td className="py-2.5 px-3 font-mono text-slate-700">{e.resource}</td>
                        <td className="py-2.5 px-3 text-slate-500">{e.before}</td>
                        <td className="py-2.5 px-3 text-slate-900 font-medium">{e.after}</td>
                        <td className="py-2.5 px-3 font-mono text-emerald-700 font-bold">{e.approval_ref}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* MODALS */}
      {/* ------------------------------------------------------------------ */}
      {/* Evidence Detail Modal */}
      {isDetailModalOpen && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-2xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-2xl">
            <div className="flex justify-between items-start mb-3">
              <h3 className="text-sm font-bold text-[#182230]">{modalTitle}</h3>
              <button
                onClick={() => setIsDetailModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 text-xs font-bold"
              >
                ✕
              </button>
            </div>
            <div className="text-xs text-[#344054] leading-relaxed whitespace-pre-line bg-slate-50 p-4 rounded-lg border border-slate-100">
              {modalBody}
            </div>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setIsDetailModalOpen(false)}
                className="px-4 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-700 transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Modal */}
      {isActionModalOpen && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-2xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h3 className="text-sm font-bold text-[#182230]">Create Cost Optimization Action</h3>
            <div>
              <label htmlFor="action-title-input" className="block text-xs font-medium text-slate-600 mb-1">Action Title</label>
              <input
                id="action-title-input"
                placeholder="e.g. Reduce auto-stop on a SQL warehouse"
                className="w-full text-xs p-2.5 border border-[#e5eaf1] rounded-lg"
              />
            </div>
            <div>
              <label htmlFor="action-workload-input" className="block text-xs font-medium text-slate-600 mb-1">Workload / Resource</label>
              <input
                id="action-workload-input"
                placeholder="workspace id / resource name"
                className="w-full text-xs p-2.5 border border-[#e5eaf1] rounded-lg"
              />
            </div>
            <div>
              <label htmlFor="action-savings-input" className="block text-xs font-medium text-slate-600 mb-1">Estimated Monthly Savings (USD)</label>
              <input id="action-savings-input" type="number" placeholder="Only if calculable" className="w-full text-xs p-2.5 border border-[#e5eaf1] rounded-lg" />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setIsActionModalOpen(false)}
                className="px-3 py-1.5 rounded-lg border border-[#e5eaf1] text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setIsActionModalOpen(false);
                  showToast("Not saved: manual cost actions are not persisted yet. Use Approve / Defer on the Optimization Advisor to record workflow decisions.");
                }}
                className="px-3.5 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-semibold"
              >
                Save Action
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Export Modal */}
      {isExportModalOpen && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-2xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h3 className="text-sm font-bold text-[#182230]">Generate FinOps Export</h3>
            <div>
              <label htmlFor="export-report-type-select" className="block text-xs font-medium text-slate-600 mb-1">Report Type</label>
              <select
                id="export-report-type-select"
                value={exportReportType}
                onChange={(e) => setExportReportType(e.target.value)}
                className="w-full text-xs p-2.5 border border-[#e5eaf1] rounded-lg"
              >
                <option value="Executive Cost Snapshot">Executive Cost Snapshot</option>
                <option value="Detailed Billing Ledger">Detailed Billing Ledger</option>
                <option value="AI Token Economics">AI Token Economics</option>
                <option value="Optimization Backlog">Optimization Backlog</option>
                <option value="Chargeback Statement">Chargeback Statement</option>
              </select>
            </div>
            <div>
              <label htmlFor="export-format-select" className="block text-xs font-medium text-slate-600 mb-1">Format</label>
              <select
                id="export-format-select"
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value)}
                className="w-full text-xs p-2.5 border border-[#e5eaf1] rounded-lg"
              >
                <option value="CSV (Direct Download)">CSV (Direct Download)</option>
                <option value="PDF Summary">PDF Summary</option>
                <option value="JSON Payload">JSON Payload</option>
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setIsExportModalOpen(false)}
                className="px-3 py-1.5 rounded-lg border border-[#e5eaf1] text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setIsExportModalOpen(false);
                  const activeScopeId = activeScope?.workspace_id || selectedWorkspaceId;
                  const filename = `finops-${exportReportType.toLowerCase().replace(/\s+/g, "-")}-${new Date().toISOString().slice(0, 10)}`;

                  if (exportFormat === "CSV (Direct Download)" || exportFormat.includes("CSV")) {
                    const spendKnown = (ingestionStatus?.total_usage_records_ingested ?? 0) > 0;
                    const csvRows: Array<{ metric: string; value: string | number; unit: string }> = [
                      { metric: "Total Spend (list-price basis)", value: spendKnown ? billingSummary?.total_spend_verified ?? "-" : "-", unit: spendKnown ? sourceCurrency.code ?? (sourceCurrency.mixed ? "mixed" : "n/a") : "n/a" },
                      { metric: "Total DBU Ingested", value: spendKnown ? ingestionStatus?.total_dbu_consumed ?? "-" : "-", unit: "DBU" },
                      { metric: "Billing Rows Ingested", value: ingestionStatus?.total_usage_records_ingested ?? 0, unit: "Count" },
                      { metric: "Billing Source Status", value: spendKnown ? "INGESTED" : "BLOCKED_PENDING_APPROVAL", unit: "n/a" },
                    ];
                    const csvString = [
                      `# BIZMETRIC FINOPS COMMAND CENTER REPORT - ${exportReportType.toUpperCase()}`,
                      `# Scope: ${activeScopeId} | ${sourceCurrencyLabel(sourceCurrency)} | Generated: ${formatDeterministicDateTime(new Date())}`,
                      `# Zero-Execution Guardrail: read-only; values not shown are unavailable, never estimated`,
                      "",
                      "Metric,Value,Unit",
                      ...csvRows.map((r) => `"${r.metric}",${r.value},"${r.unit}"`),
                    ].join("\r\n");

                    downloadCsvFile(filename, csvString);
                    showToast(`Exported ${exportReportType} as genuine RFC 4180 CSV`);
                  } else if (exportFormat.includes("PDF")) {
                    downloadFinOpsPdfReport(filename, {
                      title: "Bizmetric FinOps Command Center Report",
                      reportType: exportReportType,
                      scopeId: activeScopeId,
                      generatedAt: formatDeterministicDateTime(new Date()),
                      currency: sourceCurrency.code ?? (sourceCurrency.mixed ? "mixed" : "unknown"),
                      kpis: [
                        { label: "Total Spend (list-price basis)", value: (ingestionStatus?.total_usage_records_ingested ?? 0) > 0 && billingSummary?.total_spend_verified != null ? formatCost(billingSummary.total_spend_verified) : "-" },
                        { label: "Total DBU Ingested", value: (ingestionStatus?.total_usage_records_ingested ?? 0) > 0 ? `${(ingestionStatus?.total_dbu_consumed ?? 0).toLocaleString()} DBU` : "-" },
                        { label: "SQL Warehouse State", value: ingestionStatus?.warehouse_status || "UNKNOWN" },
                        { label: "Currency", value: sourceCurrencyLabel(sourceCurrency) },
                      ],
                      summaryRows: [
                        ["Target Cloud Scope", activeScopeId],
                        ["Pricing Source", "List prices (rate card) applied to ingested system.billing.usage rows"],
                        ["Data Provenance", "Values not backed by live Databricks data are shown as -"],
                      ],
                    });
                    showToast(`Exported ${exportReportType} as genuine PDF-1.4`);
                  } else {
                    const jsonPayload = {
                      report_type: exportReportType,
                      generated_at: formatDeterministicDateTime(new Date()),
                      scope_id: activeScopeId,
                      currency: sourceCurrency.code,
                      currency_status: sourceCurrency.mixed ? "MIXED" : sourceCurrency.code ? "SINGLE" : "UNKNOWN",
                      currency_traceability: sourceCurrencyLabel(sourceCurrency),
                      kpis: {
                        total_spend: (ingestionStatus?.total_usage_records_ingested ?? 0) > 0 && !sourceCurrency.mixed ? billingSummary?.total_spend_verified ?? null : null,
                        total_dbu: (ingestionStatus?.total_usage_records_ingested ?? 0) > 0 ? ingestionStatus?.total_dbu_consumed ?? null : null,
                        currency: sourceCurrency.code,
                      },
                      compliance: "Read-only; no cloud mutations performed",
                    };
                    const blob = new Blob([JSON.stringify(jsonPayload, null, 2)], { type: "application/json" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `${filename}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                    showToast(`Exported ${exportReportType} as JSON`);
                  }
                }}
                className="px-3.5 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 transition"
              >
                Generate Export
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Milestone 3H: Databricks Billing Ingestion & Compute Gate Modal */}
      {isIngestionModalOpen && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-2xs z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-xl max-w-4xl w-full p-6 shadow-2xl space-y-5 my-8 border border-[#e5eaf1]">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-[#e5eaf1] pb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600">
                  <Database className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-[#182230]">
                    Databricks System Tables Billing Ingestion & Compute Gate
                  </h3>
                  <div className="text-xs text-[#667085] flex items-center gap-2 mt-0.5">
                    <span>Target Workspace: <code className="font-semibold text-slate-700">{effectiveWorkspaceId}</code></span>
                    <span>•</span>
                    <span>Warehouse: <code className="font-semibold text-slate-700">{validationData?.warehouse_name || ingestionStatus?.warehouse_name || "—"} ({validationData?.warehouse_id || ingestionStatus?.warehouse_id || "—"})</code></span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setIsIngestionModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 text-sm font-bold p-1 rounded-md"
              >
                ✕
              </button>
            </div>

            {/* Zero-Execution Guardrail Alert */}
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3.5 flex items-start gap-3 text-xs text-amber-900">
              <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <div className="font-bold flex items-center gap-2">
                  <span>Strict Zero-Execution & Zero-Mutation Policy Enforced</span>
                  <span className="bg-amber-200/70 text-amber-800 text-[10px] font-bold px-2 py-0.5 rounded">
                    GATE ACTIVE
                  </span>
                </div>
                <p className="text-amber-800 leading-relaxed">
                  SQL Warehouse <code className="font-bold text-amber-950">{validationData?.warehouse_id || ingestionStatus?.warehouse_id || "—"}</code> is currently <strong>{validationData?.warehouse_state || ingestionStatus?.warehouse_status || "UNKNOWN"}</strong>.
                  This platform will <strong>never resume compute or execute unapproved SQL automatically</strong>.
                  Until an approved read-only ingestion loads billing rows, spend, forecast and anomaly figures stay <strong>unavailable</strong>; nothing is modelled or substituted.
                </p>
              </div>
            </div>

            {/* Modal Tabs */}
            <div className="flex items-center gap-2 border-b border-[#e5eaf1] text-xs">
              <button
                onClick={() => setIngestionModalTab("overview")}
                className={`pb-2.5 px-3 font-semibold transition border-b-2 ${
                  ingestionModalTab === "overview"
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                Warehouse & Approval Gate
              </button>
              <button
                onClick={() => setIngestionModalTab("preview")}
                className={`pb-2.5 px-3 font-semibold transition border-b-2 ${
                  ingestionModalTab === "preview"
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                Ingested Usage Records ({previewRecords.length})
              </button>
              <button
                onClick={() => setIngestionModalTab("reconciliation")}
                className={`pb-2.5 px-3 font-semibold transition border-b-2 ${
                  ingestionModalTab === "reconciliation"
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                Financial Reconciliation Ledger
              </button>
              <button
                onClick={() => setIngestionModalTab("diagnostics")}
                className={`pb-2.5 px-3 font-semibold transition border-b-2 ${
                  ingestionModalTab === "diagnostics"
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                Readiness Diagnostics
              </button>
            </div>

            {/* Tab 1: Overview & Approval Gate */}
            {ingestionModalTab === "overview" && (
              <div className="space-y-4 text-xs">
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 space-y-3">
                  <div className="font-bold text-[#182230] text-sm">
                    Explicit Human Approval Protocol (8 Mandatory Verification Points)
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-slate-700">
                    <div className="flex items-start gap-2">
                      <span className="font-bold text-blue-600">1.</span>
                      <span><strong>Target Source:</strong> Read-only extraction of <code>system.billing.usage</code> & <code>system.billing.list_prices</code></span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="font-bold text-blue-600">2.</span>
                      <span><strong>Warehouse:</strong> {validationData?.warehouse_name || ingestionStatus?.warehouse_name || "—"} (<code>{validationData?.warehouse_id || ingestionStatus?.warehouse_id || "—"}</code>)</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="font-bold text-blue-600">3.</span>
                      <span><strong>Compute Impact:</strong> Warehouse state is currently {validationData?.warehouse_state || ingestionStatus?.warehouse_status || "UNKNOWN"}; a stopped warehouse must be started by an operator to run queries</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="font-bold text-blue-600">4.</span>
                      <span><strong>Auto-Stop:</strong> Governed by the warehouse&apos;s own auto-stop setting (not changed by this platform)</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="font-bold text-blue-600">5.</span>
                      <span><strong>Cost Ceiling:</strong> Not estimated; depends on warehouse size and query runtime</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="font-bold text-blue-600">6.</span>
                      <span><strong>Zero Mutation:</strong> Pure read-only <code>SELECT</code>/<code>WITH</code> (mutations strictly blocked)</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="font-bold text-blue-600">7.</span>
                      <span><strong>Rollback:</strong> Read-only queries; warehouse stops via its own auto-stop setting</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="font-bold text-blue-600">8.</span>
                      <span><strong>Fallback:</strong> None. Modules show unavailable states rather than modelled values</span>
                    </div>
                  </div>
                </div>

                {/* Gate Interaction */}
                <div className="p-4 border border-[#e5eaf1] rounded-lg bg-white space-y-3">
                  <label className="flex items-start gap-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={isApprovalChecked}
                      onChange={(e) => setIsApprovalChecked(e.target.checked)}
                      className="mt-0.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-slate-800 font-medium">
                      I explicitly acknowledge that triggering live ingestion will use compute warehouse <code className="font-bold">{validationData?.warehouse_id || ingestionStatus?.warehouse_id || "—"}</code> and may incur DBU charges.
                    </span>
                  </label>

                  <div className="flex items-center gap-3 pt-2">
                    <button
                      onClick={handleExecuteIngestionRun}
                      disabled={isRunExecuting}
                      className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold flex items-center gap-2 shadow-2xs transition"
                    >
                      <Lock className="w-3.5 h-3.5" />
                      <span>{isRunExecuting ? "Testing Execution..." : "Test Gated Pipeline Run"}</span>
                    </button>
                    <span className="text-slate-500">
                      {isApprovalChecked
                        ? "Approval flag is set to TRUE"
                        : "Approval flag is set to FALSE (Will trigger APPROVAL_REQUIRED gate response)"}
                    </span>
                  </div>
                </div>

                {/* Run Result Output */}
                {runResult && (
                  <div
                    className={`p-4 rounded-lg border ${
                      runResult.status === "approval_required"
                        ? "bg-amber-50 border-amber-200 text-amber-900"
                        : "bg-emerald-50 border-emerald-200 text-emerald-900"
                    }`}
                  >
                    <div className="font-bold flex items-center gap-2">
                      <span>Pipeline Run Status: <code className="uppercase">{runResult.status}</code></span>
                      <span className="text-[10px] text-slate-500 font-normal">Run ID: {runResult.run_id}</span>
                    </div>
                    {runResult.status === "approval_required" ? (
                      <div className="mt-2 text-xs space-y-1">
                        <p><strong>Gate Notice:</strong> {runResult.error_message}</p>
                        <p className="text-[11px] text-amber-800">
                          Warehouse <code>{(runResult.approval_request?.warehouse_id as string) || "—"}</code> requires approval. Execution is blocked until human approval is supplied.
                        </p>
                      </div>
                    ) : (
                      <div className="mt-2 text-xs grid grid-cols-2 md:grid-cols-4 gap-2">
                        <div>Extracted: <strong>{runResult.extracted_count}</strong></div>
                        <div>Inserted: <strong>{runResult.inserted_count}</strong></div>
                        <div>Duplicates: <strong>{runResult.duplicate_count}</strong></div>
                        <div>Retractions: <strong>{runResult.retraction_count}</strong></div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Tab 2: Baseline Usage Records Preview */}
            {ingestionModalTab === "preview" && (
              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between text-slate-600">
                  <span>Showing {previewRecords.length} normalized usage records from the ingested store</span>
                  <span className="font-semibold text-slate-800">{previewRecords.length === 0 ? "No rows ingested" : `Preview total DBU: ${previewRecords.filter((r) => r.usage_unit === "DBU").reduce((a, r) => a + r.usage_quantity, 0).toLocaleString()}`}</span>
                </div>
                <div className="border border-[#e5eaf1] rounded-lg overflow-x-auto max-h-[350px]">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 border-b border-[#e5eaf1] text-slate-700 sticky top-0">
                      <tr>
                        <th className="p-2.5 font-semibold">Record ID</th>
                        <th className="p-2.5 font-semibold">Date</th>
                        <th className="p-2.5 font-semibold">SKU Name</th>
                        <th className="p-2.5 font-semibold text-right">Quantity</th>
                        <th className="p-2.5 font-semibold">Unit</th>
                        <th className="p-2.5 font-semibold text-right">Cost ({currencyColumnName(sourceCurrency)})</th>
                        <th className="p-2.5 font-semibold text-center">Type</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-slate-600">
                      {previewRecords.map((r) => (
                        <tr key={r.record_id} className="hover:bg-slate-50/50">
                          <td className="p-2.5 font-mono text-[11px] text-slate-500">{r.record_id.slice(0, 16)}...</td>
                          <td className="p-2.5 whitespace-nowrap">{r.usage_date}</td>
                          <td className="p-2.5 font-medium text-slate-800">{r.sku_name}</td>
                          <td className={`p-2.5 text-right font-semibold ${r.usage_quantity < 0 ? "text-rose-600" : "text-slate-800"}`}>
                            {r.usage_quantity.toLocaleString()}
                          </td>
                          <td className="p-2.5 font-mono text-[11px]">{r.usage_unit}</td>
                          <td className="p-2.5 text-right font-semibold text-slate-900">
                            {r.effective_cost !== null && r.effective_cost !== undefined ? formatSourceMoney(r.effective_cost, singleCurrency(r.currency)) : "—"}
                          </td>
                          <td className="p-2.5 text-center">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${r.record_type === "retraction" ? "bg-rose-50 text-rose-700 border border-rose-200" : "bg-emerald-50 text-emerald-700 border border-emerald-200"}`}>
                              {r.record_type}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Tab 3: Reconciliation Ledger */}
            {ingestionModalTab === "reconciliation" && (
              <div className="space-y-4 text-xs">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="text-[10px] uppercase font-bold text-slate-500">Gross Usage</div>
                    <div className="text-base font-bold text-[#182230] mt-0.5">{reconciliationData ? `${reconciliationData.gross_dbu.toLocaleString()} DBU` : "—"}</div>
                    <div className="text-[11px] text-slate-500">Gross Cost: {reconciliationData && reconciliationData.gross_cost != null ? formatSourceMoney(reconciliationData.gross_cost, reconCurrency) : "—"}</div>
                  </div>
                  <div className="p-3 bg-rose-50 border border-rose-100 rounded-lg">
                    <div className="text-[10px] uppercase font-bold text-rose-600">Retractions</div>
                    <div className="text-base font-bold text-rose-700 mt-0.5">{reconciliationData ? `${reconciliationData.retraction_dbu.toLocaleString()} DBU` : "—"}</div>
                    <div className="text-[11px] text-rose-600">Retracted Cost: {reconciliationData && reconciliationData.gross_cost != null && reconciliationData.net_cost != null ? formatSourceMoney(reconciliationData.gross_cost - reconciliationData.net_cost, reconCurrency) : "—"}</div>
                  </div>
                  <div className="p-3 bg-emerald-50 border border-emerald-100 rounded-lg">
                    <div className="text-[10px] uppercase font-bold text-emerald-700">Net Verified Spend</div>
                    <div className="text-base font-bold text-emerald-800 mt-0.5">{reconciliationData && reconciliationData.net_cost != null ? formatSourceMoney(reconciliationData.net_cost, reconCurrency) : reconCurrency.mixed ? "n/a (mixed currencies)" : "—"}</div>
                    <div className="text-[11px] text-emerald-600">Net DBU: {reconciliationData ? `${reconciliationData.net_dbu.toLocaleString()} DBU` : "—"}</div>
                  </div>
                  <div className="p-3 bg-blue-50 border border-blue-100 rounded-lg">
                    <div className="text-[10px] uppercase font-bold text-blue-700">Reconciliation Status</div>
                    <div className="text-base font-bold text-blue-800 mt-0.5">{reconciliationData?.reconciliation_status || "NOT AVAILABLE"}</div>
                    <div className="text-[11px] text-blue-600">{reconciliationData ? "See audit notes" : "No ingested rows to reconcile"}</div>
                  </div>
                </div>

                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
                  <div className="font-bold text-[#182230]">Reconciliation Audit Notes:</div>
                  <ul className="list-disc list-inside space-y-1 text-slate-600">
                    {(reconciliationData?.audit_notes || ["No reconciliation notes: no billing rows have been ingested."                    ]).map((note, idx) => (
                      <li key={idx}>{note}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {/* Tab 4: Diagnostics */}
            {ingestionModalTab === "diagnostics" && (
              <div className="space-y-4 text-xs">
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <span className="text-[10px] uppercase font-bold text-slate-500">Warehouse ID</span>
                    <p className="font-mono font-bold text-[#182230] mt-1">{validationData?.warehouse_id || ingestionStatus?.warehouse_id || "—"}</p>
                    <p className="text-slate-500 text-[11px] mt-0.5">State: <strong className="text-amber-600">{validationData?.warehouse_state || ingestionStatus?.warehouse_status || "UNKNOWN"}</strong></p>
                  </div>
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <span className="text-[10px] uppercase font-bold text-slate-500">System Tables Readiness</span>
                    <p className="font-bold text-[#182230] mt-1">{validationData ? (validationData.system_tables_ready ? "READY" : "NOT READY") : "—"}</p>
                    <p className="text-slate-500 text-[11px] mt-0.5">Modelled fallback: <strong>NONE</strong></p>
                  </div>
                </div>

                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-1.5">
                  <div className="font-bold text-[#182230]">Diagnostic Inspections:</div>
                  <ul className="space-y-1 text-slate-600">
                    {(validationData?.diagnostic_messages || ["Run validation to see diagnostics."                    ]).map((msg, idx) => (
                      <li key={idx} className="flex items-center gap-2">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                        <span>{msg}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {/* Modal Footer */}
            <div className="flex items-center justify-between border-t border-[#e5eaf1] pt-4 text-xs">
              <span className="text-slate-500">
                Milestone 3H · Databricks Read-Only Billing & Financial Ingestion
              </span>
              <button
                onClick={() => setIsIngestionModalOpen(false)}
                className="px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Milestone 3E KPI Lineage Detail Drawer */}
      <KpiDetailDrawer
        isOpen={Boolean(selectedKpiKey && selectedKpiMetric)}
        onClose={() => {
          setSelectedKpiKey(null);
          setSelectedKpiMetric(null);
        }}
        kpiKey={selectedKpiKey}
        kpi={selectedKpiMetric}
        workspaceId={activeScope?.workspace_id || selectedWorkspaceId}
      />

      {/* Interactive Milestone 3E Resource Drill-Down Drawer */}
      <ResourceDetailDrawer
        isOpen={Boolean(selectedDrawerResource)}
        onClose={() => setSelectedDrawerResource(null)}
        resource={selectedDrawerResource}
        isFocused={
          activeScope?.selected_child_resource?.resource_id === selectedDrawerResource?.id
        }
        onFocusScope={(child) => {
          if (onSelectScope && activeScope) {
            onSelectScope({
              ...activeScope,
              scope_type: "databricks_resource",
              selected_child_resource: child,
              display_name: `${child.resource_name} (${child.resource_type})`,
            });
            showToast(`Scope focused on ${child.resource_name}`);
          }
        }}
      />
      {/* Forensic Anomaly Investigation Drawer */}
      <AnomalyDetailDrawer
        isOpen={Boolean(selectedAnomaly)}
        onClose={() => setSelectedAnomaly(null)}
        anomaly={selectedAnomaly}
        onStatusUpdated={(id, newStatus) => {
          showToast(`Anomaly ${id} status updated to ${newStatus}`);
          if (anomalyData) {
            setAnomalyData({
              ...anomalyData,
              anomalies: anomalyData.anomalies.map((a) =>
                a.id === id ? { ...a, status: newStatus } : a
              ),
            });
          }
        }}
      />
    </div>
  );
};

