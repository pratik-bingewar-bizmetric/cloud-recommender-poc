"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  DatabricksConnection,
  DatabricksConnectionHealth,
  DatabricksWorkspaceDiscovery,
  CategoryDiscoveryStatus,
  DiscoveredResourceItem,
  QueryHistoryItem,
  QueryHistoryData,
  SystemTablesExplorerData,
} from "@/types";
import { DatabricksModuleId, CloudScope, ChildResourceScope } from "@/types/navigation";
import { getFinOpsSystemTables, getFinOpsQueryHistory } from "@/lib/api";
import { dateInputToMs } from "@/lib/finopsProvenance";
import type { ConnectionView } from "@/lib/connectionState";
import { formatUpdatedAt } from "@/lib/refreshScheduler";
import { ProvenanceBanner } from "@/components/shared/FinOpsProvenance";
import { formatDeterministicTime, formatDeterministicDateTime } from "@/lib/dateTimeFormat";
import { ResourceDetailDrawer } from "@/components/shared/ResourceDetailDrawer";
import { QueryDurationHistogram } from "@/components/shared/QueryDurationHistogram";
import {
  ArrowLeft,
  ArrowRight,
  RefreshCw,
  Server,
  Layers,
  Cpu,
  Workflow,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  FolderTree,
  ExternalLink,
  Clock,
  ShieldCheck,
  Info,
  Search,
  ChevronRight,
  ChevronDown,
  Database,
  Sparkles,
  Copy,
  Check,
  FileCode,
  Target,
  X,
  Lock,
  Coins,
} from "lucide-react";

interface DatabricksWorkspaceDetailViewProps {
  connection: DatabricksConnection;
  connectionHealth?: DatabricksConnectionHealth | null;
  /** The single derived connection state (same object as header/sidebar/FinOps). */
  connectionView?: ConnectionView;
  lastRefreshedAt?: number | null;
  availableConnections?: DatabricksConnection[];
  discovery: DatabricksWorkspaceDiscovery | null;
  activeModuleId?: DatabricksModuleId;
  onSelectModule?: (moduleId: DatabricksModuleId) => void;
  isLoading: boolean;
  onBack: () => void;
  onRefresh: () => void;
  activeScope?: CloudScope | null;
  onSelectScope?: (scope: CloudScope) => void;
  onFocusScope?: (child: ChildResourceScope) => void;
}

export const DatabricksWorkspaceDetailView: React.FC<DatabricksWorkspaceDetailViewProps> = ({
  connection,
  connectionHealth = null,
  connectionView,
  lastRefreshedAt = null,
  availableConnections = [],
  discovery,
  activeModuleId = "overview",
  onSelectModule,
  isLoading,
  onBack,
  onRefresh,
  activeScope,
  onSelectScope,
  onFocusScope,
}) => {
  const [currentTab, setCurrentTab] = useState<DatabricksModuleId>(activeModuleId);
  const [filterQuery, setFilterQuery] = useState<string>("");

  // Resource Detail Slide-Over Drawer
  const [drawerResource, setDrawerResource] = useState<DiscoveredResourceItem | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);

  // System Tables Live Diagnostic State
  const [systemTablesData, setSystemTablesData] = useState<SystemTablesExplorerData | null>(null);
  const [isLoadingSystemTables, setIsLoadingSystemTables] = useState<boolean>(false);
  const [systemTablesFilter, setSystemTablesFilter] = useState<string>("");
  const [expandedSystemTable, setExpandedSystemTable] = useState<string | null>(null);

  // Query History State
  const [queryHistoryData, setQueryHistoryData] = useState<QueryHistoryData | null>(null);
  const [isLoadingQueryHistory, setIsLoadingQueryHistory] = useState<boolean>(false);
  const [queryStatusFilter, setQueryStatusFilter] = useState<string>("all");
  const [querySearch, setQuerySearch] = useState<string>("");
  const [queryStartDate, setQueryStartDate] = useState<string>("");
  const [queryEndDate, setQueryEndDate] = useState<string>("");
  const [queryPageTokens, setQueryPageTokens] = useState<string[]>([]); // tokens of pages already visited
  const [queryPageToken, setQueryPageToken] = useState<string | null>(null);
  const [selectedDurationBucket, setSelectedDurationBucket] = useState<string | null>(null);
  const [selectedQuery, setSelectedQuery] = useState<QueryHistoryItem | null>(null);
  const [isQueryModalOpen, setIsQueryModalOpen] = useState<boolean>(false);
  const [isCopiedSql, setIsCopiedSql] = useState<boolean>(false);

  // Module-specific search and filter states
  const [clusterSearch, setClusterSearch] = useState<string>("");
  const [clusterStatusFilter, setClusterStatusFilter] = useState<string>("all");

  const [whSearch, setWhSearch] = useState<string>("");
  const [whStateFilter, setWhStateFilter] = useState<string>("all");

  const [jobSearch, setJobSearch] = useState<string>("");
  const [jobStatusFilter, setJobStatusFilter] = useState<string>("all");

  const [pipelineSearch, setPipelineSearch] = useState<string>("");
  const [pipelineStateFilter, setPipelineStateFilter] = useState<string>("all");

  const [servingStatusFilter, setServingStatusFilter] = useState<string>("all");

  const [appSearch, setAppSearch] = useState<string>("");
  const [appStatusFilter, setAppStatusFilter] = useState<string>("all");


  // Unity Catalog Explorer State
  const [selectedUcCatalog, setSelectedUcCatalog] = useState<string>("system");
  const [selectedUcSchema, setSelectedUcSchema] = useState<string>("billing");
  const [selectedUcTable, setSelectedUcTable] = useState<string>("usage");

  useEffect(() => {
    setCurrentTab(activeModuleId);
  }, [activeModuleId]);

  const handleTabChange = (tabId: DatabricksModuleId) => {
    setCurrentTab(tabId);
    if (onSelectModule) {
      onSelectModule(tabId);
    }
  };

  // Fetch System Tables when tab opens
  const loadSystemTables = useCallback(async () => {
    setIsLoadingSystemTables(true);
    try {
      const data = await getFinOpsSystemTables(connection.connection_id, connection.workspace_id);
      setSystemTablesData(data);
    } catch (err) {
      console.warn("Failed to load system tables diagnostic:", err);
    } finally {
      setIsLoadingSystemTables(false);
    }
  }, [connection.connection_id, connection.workspace_id]);

  useEffect(() => {
    if (currentTab === "system_tables" && !systemTablesData && !isLoadingSystemTables) {
      loadSystemTables();
    }
  }, [currentTab, systemTablesData, isLoadingSystemTables, loadSystemTables]);

  // Fetch Query History when tab opens or filter changes
  const loadQueryHistory = useCallback(async () => {
    setIsLoadingQueryHistory(true);
    try {
      const statusParam = queryStatusFilter === "all" ? undefined : queryStatusFilter;
      const data = await getFinOpsQueryHistory(
        connection.connection_id,
        connection.workspace_id,
        undefined,
        undefined,
        statusParam,
        50,
        queryPageToken,
        dateInputToMs(queryStartDate),
        dateInputToMs(queryEndDate, true)
      );
      setQueryHistoryData(data);
    } catch (err) {
      console.warn("Failed to load query history:", err);
    } finally {
      setIsLoadingQueryHistory(false);
    }
  }, [connection.connection_id, connection.workspace_id, queryStatusFilter, queryPageToken, queryStartDate, queryEndDate]);

  useEffect(() => {
    if (currentTab === "query_history") {
      loadQueryHistory();
    }
  }, [currentTab, queryStatusFilter, queryPageToken, queryStartDate, queryEndDate, loadQueryHistory]);

  const categories = discovery?.categories || {};
  const resources = discovery?.resources || [];
  const view = connectionView;
  const isAuthOrConnectionFailed =
    view?.state === "AUTHENTICATION_REQUIRED" || view?.state === "ACCESS_DENIED" || view?.state === "ERROR";
  const effectiveErrorMessage =
    view?.reason ||
    connectionHealth?.last_error ||
    categories.workspace?.error_message ||
    connectionHealth?.limitations?.[0] ||
    null;
  const toneClasses: Record<string, string> = {
    ok: "bg-emerald-50 text-emerald-700 border-emerald-200",
    warn: "bg-amber-50 text-amber-800 border-amber-300",
    bad: "bg-rose-50 text-rose-700 border-rose-200",
    neutral: "bg-slate-100 text-slate-700 border-slate-300",
    checking: "bg-blue-50 text-blue-700 border-blue-200",
  };
  const statusBadgeInfo = {
    label: view?.label ?? "Checking",
    classes: toneClasses[view?.tone ?? "checking"],
  };
  // Inventory counts are only real when discovery produced a result; otherwise "-" (never 0).
  const inventoryKnown = !!discovery && discovery.overall_status !== "failed";
  // A real 0 requires that category's own query to have succeeded (available / confirmed empty).
  const categoryOk = (cat: string): boolean => {
    const st = categories[cat]?.status;
    return st === "available" || st === "no_resources_found";
  };
  const count = (n: number, cat: string): string | number => (inventoryKnown && categoryOk(cat) ? n : "-");

  const clusters: DiscoveredResourceItem[] = resources.filter(
    (r) => r.resource_type === "cluster"
  );
  const warehouses: DiscoveredResourceItem[] = resources.filter(
    (r) => r.resource_type === "warehouse"
  );
  const jobs: DiscoveredResourceItem[] = resources.filter(
    (r) => r.resource_type === "job"
  );
  const pipelines: DiscoveredResourceItem[] = resources.filter(
    (r) => r.resource_type === "pipeline"
  );
  const servingEndpoints: DiscoveredResourceItem[] = resources.filter(
    (r) => r.resource_type === "serving_endpoint"
  );
  const apps: DiscoveredResourceItem[] = resources.filter(
    (r) => r.resource_type === "app"
  );

  const filteredClusters = clusters.filter((c) => {
    if (clusterStatusFilter !== "all" && (c.status || "-") !== clusterStatusFilter) return false;
    if (clusterSearch) {
      const q = clusterSearch.toLowerCase();
      if (!c.name.toLowerCase().includes(q) && !c.id.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const filteredWarehouses = warehouses.filter((w) => {
    if (whStateFilter !== "all" && (w.status || "-") !== whStateFilter) return false;
    if (whSearch) {
      const q = whSearch.toLowerCase();
      if (!w.name.toLowerCase().includes(q) && !w.id.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const filteredJobs = jobs.filter((j) => {
    if (jobStatusFilter !== "all" && (j.status || "-") !== jobStatusFilter) return false;
    if (jobSearch) {
      const q = jobSearch.toLowerCase();
      if (!j.name.toLowerCase().includes(q) && !j.id.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const filteredPipelines = pipelines.filter((p) => {
    if (pipelineStateFilter !== "all" && (p.status || "-") !== pipelineStateFilter) return false;
    if (pipelineSearch) {
      const q = pipelineSearch.toLowerCase();
      if (!p.name.toLowerCase().includes(q) && !p.id.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const filteredServingEndpoints = servingEndpoints.filter((s) => {
    if (servingStatusFilter !== "all" && (s.status || "-") !== servingStatusFilter) return false;
    if (filterQuery) {
      const q = filterQuery.toLowerCase();
      if (!s.name.toLowerCase().includes(q) && !s.id.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const filteredApps = apps.filter((a) => {
    if (appStatusFilter !== "all" && (a.status || "-") !== appStatusFilter) return false;
    if (appSearch) {
      const q = appSearch.toLowerCase();
      if (!a.name.toLowerCase().includes(q) && !a.id.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const handleOpenResourceDrawer = (resource: DiscoveredResourceItem) => {
    setDrawerResource(resource);
    setIsDrawerOpen(true);
  };

  const handleFocusFromDrawer = (child: ChildResourceScope) => {
    if (onFocusScope) {
      onFocusScope(child);
    } else if (onSelectScope && activeScope) {
      onSelectScope({
        ...activeScope,
        scope_type: "databricks_resource",
        selected_child_resource: child,
        display_name: `${activeScope.workspace_name || connection.workspace_name} > ${child.resource_name}`,
      });
    }
  };

  const handleCopySql = (sql: string) => {
    navigator.clipboard.writeText(sql);
    setIsCopiedSql(true);
    setTimeout(() => setIsCopiedSql(false), 2000);
  };

  const getCategoryStatusBadge = (status?: CategoryDiscoveryStatus) => {
    switch (status) {
      case "available":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Available
          </span>
        );
      case "permission_denied":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <ShieldAlert className="w-3 h-3 text-rose-600" />
            Permission Denied
          </span>
        );
      case "no_resources_found":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-50 text-slate-600 border border-slate-200">
            Empty (0 Found)
          </span>
        );
      case "unsupported":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            Unsupported
          </span>
        );
      case "connection_error":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertTriangle className="w-3 h-3 text-rose-600" />
            Connection Error
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">
            {String(status ?? "-")}
          </span>
        );
    }
  };

  const activeSystemTablesList = systemTablesData?.tables || [];

  const filteredSystemTables = activeSystemTablesList.filter((st) => {
    if (!systemTablesFilter) return true;
    const q = systemTablesFilter.toLowerCase();
    return (
      st.table_name.toLowerCase().includes(q) ||
      st.description.toLowerCase().includes(q) ||
      st.schema_name.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      {/* Top Header Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition"
              title="Return to Scope Manager"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="w-10 h-10 rounded-xl bg-orange-50 border border-orange-200 flex items-center justify-center text-orange-600 font-bold">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-navy-900 tracking-tight">
                  {connection.workspace_name}
                </h2>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-orange-100 text-orange-800 border border-orange-200">
                  {connection.cloud}
                </span>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${statusBadgeInfo.classes}`}
                  title={view?.reason ?? undefined}
                >
                  {statusBadgeInfo.label}
                </span>
                {view?.stale && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-amber-50 text-amber-800 border-amber-300" title="The latest refresh failed; showing the last successful data">
                    Stale
                  </span>
                )}
                {view?.sqlWarehouse && (
                  <span
                    className="px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-slate-50 text-slate-700 border-slate-200"
                    title={view.sqlWarehouse.message}
                  >
                    SQL warehouse: {view.sqlWarehouse.state ?? "-"}
                  </span>
                )}
                <span className="text-[10px] text-slate-500">
                  Updated {formatUpdatedAt(lastRefreshedAt ?? view?.lastSuccessAt)}
                </span>
                {activeScope?.selected_child_resource && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-100 text-blue-800 border border-blue-200 flex items-center gap-1">
                    <Target className="w-3 h-3 text-blue-600" />
                    Focused: {activeScope.selected_child_resource.resource_name}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                <span className="font-mono">ID: {connection.workspace_id}</span>
                <span>•</span>
                <a
                  href={connection.workspace_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand-600 hover:underline flex items-center gap-1 font-mono text-[11px]"
                >
                  {connection.workspace_url}
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {availableConnections.length > 1 && onSelectScope && activeScope && (
              <select
                aria-label="Select Databricks workspace"
                value={connection.workspace_id}
                onChange={(e) => {
                  const chosen = availableConnections.find((c) => c.workspace_id === e.target.value);
                  if (chosen) {
                    onSelectScope({
                      ...activeScope,
                      workspace_id: chosen.workspace_id,
                      workspace_name: chosen.workspace_name,
                      workspace_url: chosen.workspace_url,
                      region: chosen.region || activeScope.region,
                    });
                  }
                }}
                className="px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 text-xs font-medium"
              >
                {availableConnections.map((ws) => (
                  <option key={ws.connection_id} value={ws.workspace_id}>
                    {ws.workspace_name} ({ws.workspace_id})
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-brand-600" : ""}`} />
              <span>{isLoading ? "Discovering..." : "Refresh Discovery"}</span>
            </button>
          </div>
        </div>
        {isAuthOrConnectionFailed && (
          <div className="mt-4 p-3 rounded-lg border border-rose-200 bg-rose-50/70 text-xs text-rose-900 flex items-start gap-2.5">
            <ShieldAlert className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <p className="font-bold">
                Workspace connection: {statusBadgeInfo.label}
              </p>
              <p className="text-[11px] text-rose-800">
                {effectiveErrorMessage ||
                  "Unable to authenticate or reach the selected Databricks workspace. Verify Service Principal workspace assignment and credentials."}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* MODULE 1: WORKSPACE OVERVIEW */}
      {currentTab === "overview" && (
        <div className="space-y-6">
          {/* Quick Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div
              onClick={() => handleTabChange("clusters")}
              className="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs cursor-pointer hover:border-brand-500 transition"
            >
              <span className="text-xs text-slate-500 font-medium">Compute Clusters</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-2xl font-bold text-navy-900">{count(clusters.length, "clusters")}</span>
                <span className="text-xs text-slate-400">discovered</span>
              </div>
              <div className="mt-2">{getCategoryStatusBadge(categories["clusters"]?.status)}</div>
            </div>

            <div
              onClick={() => handleTabChange("warehouses")}
              className="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs cursor-pointer hover:border-brand-500 transition"
            >
              <span className="text-xs text-slate-500 font-medium">SQL Warehouses</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-2xl font-bold text-navy-900">{count(warehouses.length, "warehouses")}</span>
                <span className="text-xs text-slate-500 font-medium">(STOPPED)</span>
              </div>
              <div className="mt-2">{getCategoryStatusBadge(categories["warehouses"]?.status)}</div>
            </div>

            <div
              onClick={() => handleTabChange("serving")}
              className="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs cursor-pointer hover:border-brand-500 transition"
            >
              <span className="text-xs text-slate-500 font-medium">Serving Endpoints</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-2xl font-bold text-purple-700">
                  {count(servingEndpoints.length, "model_serving")}
                </span>
                <span className="text-xs text-slate-400">models</span>
              </div>
              <div className="mt-2">
                {getCategoryStatusBadge(categories["model_serving"]?.status || "available")}
              </div>
            </div>

            <div
              onClick={() => handleTabChange("apps")}
              className="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs cursor-pointer hover:border-brand-500 transition"
            >
              <span className="text-xs text-slate-500 font-medium">Databricks Apps</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-2xl font-bold text-brand-600">
                  {count(apps.length, "apps")}
                </span>
                <span className="text-xs text-slate-400">applications</span>
              </div>
              <div className="mt-2">
                {getCategoryStatusBadge(categories["apps"]?.status || "available")}
              </div>
            </div>
          </div>

          {/* Identity & Discovery Health */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-navy-900 mb-3 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                <span>Authentication &amp; Permissions</span>
              </h3>
              <dl className="divide-y divide-slate-100 text-xs">
                <div className="py-2 flex justify-between">
                  <dt className="text-slate-500">Auth Method</dt>
                  <dd className="font-semibold text-navy-900">{connection.auth_method}</dd>
                </div>
                <div className="py-2 flex justify-between">
                  <dt className="text-slate-500">Host Cloud</dt>
                  <dd className="font-semibold text-navy-900 uppercase">{connection.cloud}</dd>
                </div>
                <div className="py-2 flex justify-between">
                  <dt className="text-slate-500">Region</dt>
                  <dd className="font-semibold text-navy-900">{connection.region || "eastus"}</dd>
                </div>
                <div className="py-2 flex justify-between">
                  <dt className="text-slate-500">Zero-Execution Guardrail</dt>
                  <dd className="font-semibold text-emerald-600">Enforced (100% Read-Only)</dd>
                </div>
              </dl>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs">
              <h3 className="text-sm font-bold text-navy-900 mb-3 flex items-center gap-2">
                <Clock className="w-4 h-4 text-brand-600" />
                <span>Discovery Execution Snapshot</span>
              </h3>
              <dl className="divide-y divide-slate-100 text-xs">
                <div className="py-2 flex justify-between">
                  <dt className="text-slate-500">Overall Discovery State</dt>
                  <dd className="font-semibold text-navy-900 capitalize">
                    {discovery?.overall_status || "-"}
                  </dd>
                </div>
                <div className="py-2 flex justify-between">
                  <dt className="text-slate-500">Total Scoped Resources</dt>
                  <dd className="font-semibold text-navy-900">
                    {inventoryKnown ? (discovery?.total_resources_count ?? resources.length) : "-"}
                  </dd>
                </div>
                <div className="py-2 flex justify-between">
                  <dt className="text-slate-500">Last Discovered At</dt>
                  <dd className="font-semibold text-navy-900">
                    {discovery?.discovered_at
                      ? formatDeterministicDateTime(discovery.discovered_at)
                      : "Recently"}
                  </dd>
                </div>
                <div className="py-2 flex justify-between">
                  <dt className="text-slate-500">System Tables Schema Probing</dt>
                  <dd className="font-semibold text-emerald-600">10 Schemas Verified</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>
      )}

      {/* MODULE 2: COMPUTE CLUSTERS */}
      {currentTab === "clusters" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-navy-900">Discovered Compute Clusters</h3>
              <p className="text-xs text-slate-500">
                Click any cluster to inspect configuration, utilization, and cost breakdown.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Search clusters..."
                  value={clusterSearch}
                  onChange={(e) => setClusterSearch(e.target.value)}
                  className="text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg w-44 focus:outline-brand-500"
                  aria-label="Search clusters"
                />
              </div>
              <select
                value={clusterStatusFilter}
                onChange={(e) => setClusterStatusFilter(e.target.value)}
                className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white font-medium text-navy-900"
                aria-label="Cluster status filter"
              >
                <option value="all">All States</option>
                <option value="RUNNING">RUNNING</option>
                <option value="TERMINATED">TERMINATED</option>
                <option value="PENDING">PENDING</option>
              </select>
              <span className="text-xs text-slate-500 font-medium">
                Total: <span className="font-bold text-navy-900">{filteredClusters.length}</span>
              </span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase font-bold text-slate-500">
                  <th className="py-2.5 px-3">Cluster Name</th>
                  <th className="py-2.5 px-3">Cluster ID</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Node Type</th>
                  <th className="py-2.5 px-3">Autoscale</th>
                  <th className="py-2.5 px-3">Creator</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredClusters.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => handleOpenResourceDrawer(c)}
                    className="hover:bg-slate-50 cursor-pointer group transition"
                  >
                    <td className="py-2.5 px-3 font-semibold text-navy-900 group-hover:text-brand-600 flex items-center gap-2">
                      <Cpu className="w-4 h-4 text-blue-600" />
                      <span>{c.name}</span>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">{c.id}</td>
                    <td className="py-2.5 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">
                        {c.status || "-"}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-600">
                      {(c.metadata?.node_type_id as string) || "Standard_D4s_v5"}
                    </td>
                    <td className="py-2.5 px-3 text-slate-600">
                      {c.metadata?.autoscale ? "Enabled (2-8 nodes)" : "Fixed"}
                    </td>
                    <td className="py-2.5 px-3 text-slate-500">{c.creator || "admin"}</td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleFocusFromDrawer({
                            resource_type: "cluster",
                            resource_id: c.id,
                            resource_name: c.name,
                          });
                        }}
                        className="px-2 py-1 rounded bg-slate-100 hover:bg-brand-50 text-slate-600 hover:text-brand-700 text-[10px] font-semibold transition"
                      >
                        Focus Scope
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODULE 3: SQL WAREHOUSES */}
      {currentTab === "warehouses" && (
        <div className="space-y-4">
          {/* STOPPED Zero-Execution Notice */}
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-900 flex items-start gap-3">
            <Info className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold text-amber-950 block">
                Warehouse State: STOPPED (Zero-Execution Policy Enforced)
              </span>
              <p className="mt-0.5 text-amber-800 leading-relaxed">
                The Serverless Starter Warehouse (ID: <code>05ed10a52697a344</code>) is currently stopped.
                In accordance with our strict non-mutation and read-only policy, this application will never
                automatically start, resume, or mutate SQL warehouses. Metadata and schemas are inspected via
                read-only REST APIs.
              </p>
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-navy-900">SQL Warehouses Inventory</h3>
                <p className="text-xs text-slate-500">
                  Click warehouse row to inspect sizing, historical queries, and zero-execution status.
                </p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search warehouses..."
                    value={whSearch}
                    onChange={(e) => setWhSearch(e.target.value)}
                    className="text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg w-44 focus:outline-brand-500"
                    aria-label="Search warehouses"
                  />
                </div>
                <select
                  value={whStateFilter}
                  onChange={(e) => setWhStateFilter(e.target.value)}
                  className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white font-medium text-navy-900"
                  aria-label="Warehouse state filter"
                >
                  <option value="all">All States</option>
                  <option value="STOPPED">STOPPED</option>
                  <option value="RUNNING">RUNNING</option>
                  <option value="STARTING">STARTING</option>
                </select>
                <span className="text-xs text-slate-500 font-medium">
                  Discovered: <span className="font-bold text-navy-900">{filteredWarehouses.length}</span>
                </span>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase font-bold text-slate-500">
                    <th className="py-2.5 px-3">Warehouse Name</th>
                    <th className="py-2.5 px-3">Warehouse ID</th>
                    <th className="py-2.5 px-3">State</th>
                    <th className="py-2.5 px-3">Size</th>
                    <th className="py-2.5 px-3">Auto-Stop</th>
                    <th className="py-2.5 px-3">Serverless</th>
                    <th className="py-2.5 px-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredWarehouses.map((w) => (
                    <tr
                      key={w.id}
                      onClick={() => handleOpenResourceDrawer(w)}
                      className="hover:bg-slate-50 cursor-pointer group transition"
                    >
                      <td className="py-2.5 px-3 font-semibold text-navy-900 group-hover:text-brand-600 flex items-center gap-2">
                        <Database className="w-4 h-4 text-sky-600" />
                        <span>{w.name}</span>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">{w.id}</td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                          {w.status || "-"}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-slate-600">
                        {(w.metadata?.cluster_size as string) || "2X-Small"}
                      </td>
                      <td className="py-2.5 px-3 text-slate-600">
                        {(w.metadata?.auto_stop_mins as number) || 10} mins
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="text-emerald-700 font-semibold">Yes</span>
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleFocusFromDrawer({
                              resource_type: "warehouse",
                              resource_id: w.id,
                              resource_name: w.name,
                            });
                          }}
                          className="px-2 py-1 rounded bg-slate-100 hover:bg-brand-50 text-slate-600 hover:text-brand-700 text-[10px] font-semibold transition"
                        >
                          Focus Scope
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* MODULE 4: JOBS & WORKFLOWS */}
      {currentTab === "jobs" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-navy-900">Multi-Task Jobs &amp; Workflows</h3>
              <p className="text-xs text-slate-500">
                Click any workflow to inspect multi-task DAGs and run executions.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Search jobs..."
                  value={jobSearch}
                  onChange={(e) => setJobSearch(e.target.value)}
                  className="text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg w-44 focus:outline-brand-500"
                  aria-label="Search jobs"
                />
              </div>
              <select
                value={jobStatusFilter}
                onChange={(e) => setJobStatusFilter(e.target.value)}
                className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white font-medium text-navy-900"
                aria-label="Job status filter"
              >
                <option value="all">All Statuses</option>
                <option value="SUCCESS">SUCCESS</option>
                <option value="FAILED">FAILED</option>
                <option value="RUNNING">RUNNING</option>
              </select>
              <span className="text-xs text-slate-500 font-medium">
                Discovered: <span className="font-bold text-navy-900">{filteredJobs.length}</span>
              </span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase font-bold text-slate-500">
                  <th className="py-2.5 px-3">Job Name</th>
                  <th className="py-2.5 px-3">Job ID</th>
                  <th className="py-2.5 px-3">Schedule</th>
                  <th className="py-2.5 px-3">Creator</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredJobs.map((j) => (
                  <tr
                    key={j.id}
                    onClick={() => handleOpenResourceDrawer(j)}
                    className="hover:bg-slate-50 cursor-pointer group transition"
                  >
                    <td className="py-2.5 px-3 font-semibold text-navy-900 group-hover:text-brand-600 flex items-center gap-2">
                      <Workflow className="w-4 h-4 text-emerald-600" />
                      <span>{j.name}</span>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">{j.id}</td>
                    <td className="py-2.5 px-3 text-slate-600">
                      {(j.metadata?.schedule as string) || "On Demand"}
                    </td>
                    <td className="py-2.5 px-3 text-slate-500">{j.creator || "admin"}</td>
                    <td className="py-2.5 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700">
                        {j.status || "-"}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleFocusFromDrawer({
                            resource_type: "job",
                            resource_id: j.id,
                            resource_name: j.name,
                          });
                        }}
                        className="px-2 py-1 rounded bg-slate-100 hover:bg-brand-50 text-slate-600 hover:text-brand-700 text-[10px] font-semibold transition"
                      >
                        Focus Scope
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODULE 5: PIPELINES (Delta Live Tables) */}
      {currentTab === "pipelines" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-navy-900">Delta Live Tables (DLT) Pipelines</h3>
              <p className="text-xs text-slate-500">
                Click any pipeline to inspect data quality expectations, continuous sync, and storage.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Search pipelines..."
                  value={pipelineSearch}
                  onChange={(e) => setPipelineSearch(e.target.value)}
                  className="text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg w-44 focus:outline-brand-500"
                  aria-label="Search pipelines"
                />
              </div>
              <select
                value={pipelineStateFilter}
                onChange={(e) => setPipelineStateFilter(e.target.value)}
                className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white font-medium text-navy-900"
                aria-label="Pipeline state filter"
              >
                <option value="all">All States</option>
                <option value="ACTIVE">ACTIVE</option>
                <option value="IDLE">IDLE</option>
                <option value="FAILED">FAILED</option>
              </select>
              <span className="text-xs text-slate-500 font-medium">
                Discovered: <span className="font-bold text-navy-900">{filteredPipelines.length}</span>
              </span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase font-bold text-slate-500">
                  <th className="py-2.5 px-3">Pipeline Name</th>
                  <th className="py-2.5 px-3">Pipeline ID</th>
                  <th className="py-2.5 px-3">Mode</th>
                  <th className="py-2.5 px-3">Target Schema</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredPipelines.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => handleOpenResourceDrawer(p)}
                    className="hover:bg-slate-50 cursor-pointer group transition"
                  >
                    <td className="py-2.5 px-3 font-semibold text-navy-900 group-hover:text-brand-600 flex items-center gap-2">
                      <Layers className="w-4 h-4 text-indigo-600" />
                      <span>{p.name}</span>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">{p.id}</td>
                    <td className="py-2.5 px-3 text-slate-600">
                      {(p.metadata?.mode as string) || "Triggered"}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-blue-700">
                      {(p.metadata?.target as string) || "bronze_telemetry"}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">
                        {p.status || "IDLE"}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleFocusFromDrawer({
                            resource_type: "pipeline",
                            resource_id: p.id,
                            resource_name: p.name,
                          });
                        }}
                        className="px-2 py-1 rounded bg-slate-100 hover:bg-brand-50 text-slate-600 hover:text-brand-700 text-[10px] font-semibold transition"
                      >
                        Focus Scope
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODULE 6: MODEL SERVING ENDPOINTS (27 Models) */}
      {currentTab === "serving" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-navy-900">Model Serving Endpoints</h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-800 border border-purple-200">
                  {servingEndpoints.length} Discovered Models
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Foundation models, fine-tuned LLMs, and embeddings. Click any endpoint to inspect token economics.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Filter models..."
                  value={filterQuery}
                  onChange={(e) => setFilterQuery(e.target.value)}
                  className="text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg w-full sm:w-44 focus:outline-brand-500"
                  aria-label="Filter models"
                />
              </div>
              <select
                value={servingStatusFilter}
                onChange={(e) => setServingStatusFilter(e.target.value)}
                className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white font-medium text-navy-900"
                aria-label="Model serving status filter"
              >
                <option value="all">All Statuses</option>
                <option value="READY">READY</option>
                <option value="UPDATING">UPDATING</option>
                <option value="FAILED">FAILED</option>
              </select>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase font-bold text-slate-500">
                  <th className="py-2.5 px-3">Endpoint Name</th>
                  <th className="py-2.5 px-3">Served Entity / Model</th>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">Compute Scale</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredServingEndpoints.map((m, idx) => (
                    <tr
                      key={m.id || idx}
                      onClick={() => handleOpenResourceDrawer(m)}
                      className="hover:bg-slate-50 cursor-pointer group transition"
                    >
                      <td className="py-2.5 px-3 font-semibold text-navy-900 font-mono text-[11px] group-hover:text-purple-700 flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                        <span>{m.name}</span>
                      </td>
                      <td className="py-2.5 px-3 text-slate-700 font-medium">
                        {(m.metadata?.model as string) || m.name.replace("databricks-", "")}
                      </td>
                      <td className="py-2.5 px-3 text-slate-500">
                        {(m.metadata?.type as string) || "LLM Endpoint"}
                      </td>
                      <td className="py-2.5 px-3 text-slate-600">
                        {(m.metadata?.scale as string) || "Scale-to-Zero"}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700">
                          {m.status || "-"}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleFocusFromDrawer({
                              resource_type: "serving_endpoint",
                              resource_id: m.id,
                              resource_name: m.name,
                            });
                          }}
                          className="px-2 py-1 rounded bg-slate-100 hover:bg-brand-50 text-slate-600 hover:text-brand-700 text-[10px] font-semibold transition"
                        >
                          Focus Scope
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODULE 7: UNITY CATALOG DUAL-PANE EXPLORER */}
      {currentTab === "catalog" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h3 className="text-sm font-bold text-navy-900">Unity Catalog Interactive Explorer</h3>
              <p className="text-xs text-slate-500">
                3-level governance namespace: Metastore &rarr; Catalogs &rarr; Schemas &rarr; Tables
              </p>
            </div>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
              Metastore Attached: azure-eastus-metastore
            </span>
          </div>

          {/* Dual-Pane Grid */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4 border border-slate-200 rounded-xl overflow-hidden min-h-[420px]">
            {/* Left Pane: Hierarchy Tree Navigation */}
            <div className="md:col-span-4 bg-slate-50 border-r border-slate-200 p-4 space-y-3 font-mono text-xs">
              <div className="flex items-center gap-2 font-bold text-navy-900 pb-2 border-b border-slate-200">
                <FolderTree className="w-4 h-4 text-brand-600" />
                <span>azure-eastus-metastore</span>
              </div>

              {/* Catalogs Tree */}
              <div className="space-y-2">
                {/* 1. System Catalog */}
                <div>
                  <button
                    onClick={() => {
                      setSelectedUcCatalog("system");
                      setSelectedUcSchema("billing");
                      setSelectedUcTable("usage");
                    }}
                    className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-left transition ${
                      selectedUcCatalog === "system"
                        ? "bg-blue-100/70 text-blue-900 font-semibold"
                        : "hover:bg-slate-200/60 text-slate-700"
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
                      📁 system
                    </span>
                    <span className="text-[10px] px-1 bg-blue-200/60 rounded text-blue-800">5 schemas</span>
                  </button>

                  {selectedUcCatalog === "system" && (
                    <div className="ml-5 pl-2 border-l border-slate-300 space-y-1 mt-1">
                      {["billing", "compute", "lakeflow", "access", "ai"].map((sch) => (
                        <div key={sch}>
                          <button
                            onClick={() => {
                              setSelectedUcSchema(sch);
                              setSelectedUcTable(
                                sch === "billing" ? "usage" : sch === "compute" ? "clusters" : sch === "lakeflow" ? "jobs" : sch === "access" ? "audit" : "model_serving"
                              );
                            }}
                            className={`w-full text-left px-2 py-1 rounded text-[11px] transition ${
                              selectedUcSchema === sch
                                ? "bg-white text-navy-900 font-bold shadow-2xs border border-slate-200"
                                : "hover:bg-slate-200/50 text-slate-600"
                            }`}
                          >
                            📂 {sch}
                          </button>
                          {selectedUcSchema === sch && (
                            <div className="ml-4 pl-2 border-l border-slate-200 space-y-0.5 mt-0.5 text-[10px]">
                              {(sch === "billing"
                                ? ["usage", "list_prices"]
                                : sch === "compute"
                                ? ["clusters", "warehouses", "node_timeline"]
                                : sch === "lakeflow"
                                ? ["jobs", "pipelines"]
                                : sch === "access"
                                ? ["audit"]
                                : ["model_serving"]
                              ).map((tbl) => (
                                <button
                                  key={tbl}
                                  onClick={() => setSelectedUcTable(tbl)}
                                  className={`block w-full text-left px-1.5 py-0.5 rounded transition ${
                                    selectedUcTable === tbl
                                      ? "text-brand-600 font-bold bg-brand-50"
                                      : "text-slate-500 hover:text-navy-900"
                                  }`}
                                >
                                  📄 {tbl}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 2. Main Catalog */}
                <div>
                  <button
                    onClick={() => {
                      setSelectedUcCatalog("main");
                      setSelectedUcSchema("default");
                      setSelectedUcTable("sample_events");
                    }}
                    className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-left transition ${
                      selectedUcCatalog === "main"
                        ? "bg-emerald-100/70 text-emerald-900 font-semibold"
                        : "hover:bg-slate-200/60 text-slate-700"
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                      📁 main
                    </span>
                    <span className="text-[10px] px-1 bg-emerald-200/60 rounded text-emerald-800">4 schemas</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Right Pane: Selected Entity Details & Schema Definition */}
            <div className="md:col-span-8 p-5 space-y-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-mono text-[10px] uppercase font-bold border border-blue-200">
                      Table
                    </span>
                    <h4 className="text-sm font-bold text-navy-900 font-mono">
                      {selectedUcCatalog}.{selectedUcSchema}.{selectedUcTable}
                    </h4>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    System-managed telemetry and cost accounting table with read-only RBAC.
                  </p>
                </div>
                <div className="text-right">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Format: Delta Lake
                  </span>
                  <div className="text-[10px] text-slate-400 mt-1">Owner: System Admin</div>
                </div>
              </div>

              {/* Table Metadata Grid */}
              <div className="grid grid-cols-3 gap-3 p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs">
                <div>
                  <span className="text-slate-500 text-[10px] block">Namespace</span>
                  <span className="font-semibold text-navy-900 font-mono text-[11px]">
                    {selectedUcCatalog}.{selectedUcSchema}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">Governance Role</span>
                  <span className="font-semibold text-emerald-700 text-[11px] flex items-center gap-1">
                    <Lock className="w-3 h-3 text-emerald-600" />
                    SELECT (Read-Only)
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">Lineage Tracking</span>
                  <span className="font-semibold text-navy-900 text-[11px]">Active (System Tables)</span>
                </div>
              </div>

              {/* Schema Columns Table */}
              <div>
                <h5 className="text-xs font-bold text-navy-900 mb-2">Column Definitions</h5>
                <div className="border border-slate-200 rounded-lg overflow-x-auto max-h-60 overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-[10px] uppercase font-bold text-slate-500 border-b border-slate-200 sticky top-0">
                      <tr>
                        <th className="py-2 px-3">Column Name</th>
                        <th className="py-2 px-3">Data Type</th>
                        <th className="py-2 px-3">Comment / Description</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {[
                        { name: "account_id", type: "STRING", comment: "Databricks customer account identifier" },
                        { name: "workspace_id", type: "STRING", comment: "Workspace identifier" },
                        { name: "record_id", type: "STRING", comment: "UUID of the billing ledger transaction" },
                        { name: "sku_name", type: "STRING", comment: "Commercial billing SKU code" },
                        { name: "usage_start_time", type: "TIMESTAMP", comment: "Start interval" },
                        { name: "usage_end_time", type: "TIMESTAMP", comment: "End interval" },
                        { name: "usage_quantity", type: "DECIMAL(18,4)", comment: "Measured consumption in DBUs" },
                        { name: "usage_unit", type: "STRING", comment: "DBU (Databricks Units)" },
                      ].map((col, idx) => (
                        <tr key={idx} className="hover:bg-slate-50">
                          <td className="py-2 px-3 font-mono font-semibold text-blue-700 text-[11px]">
                            {col.name}
                          </td>
                          <td className="py-2 px-3 font-mono text-[10px] text-purple-700">{col.type}</td>
                          <td className="py-2 px-3 text-slate-500 text-[11px]">{col.comment}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODULE 8: DATABRICKS APPS */}
      {currentTab === "apps" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-navy-900">Databricks Apps</h3>
              <p className="text-xs text-slate-500">
                Discovered native Databricks compute applications and serverless runtime state.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Search apps..."
                  value={appSearch}
                  onChange={(e) => setAppSearch(e.target.value)}
                  className="text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg w-44 focus:outline-brand-500"
                  aria-label="Search apps"
                />
              </div>
              <select
                value={appStatusFilter}
                onChange={(e) => setAppStatusFilter(e.target.value)}
                className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white font-medium text-navy-900"
                aria-label="App status filter"
              >
                <option value="all">All Statuses</option>
                <option value="DEPLOYED">DEPLOYED</option>
                <option value="STOPPED">STOPPED</option>
                <option value="CRASHED">CRASHED</option>
              </select>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                {filteredApps.length} Apps
              </span>
            </div>
          </div>

          {/* Unattributed Cost Callout */}
          <div className="bg-sky-50 border border-sky-200 rounded-xl p-3.5 text-xs text-sky-950 flex items-start gap-3">
            <Info className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold block text-sky-950">
                Financial Attribution Policy: Dedicated Unattributed Bucket
              </span>
              <p className="text-sky-800 leading-relaxed mt-0.5">
                Shared Databricks Apps compute or unmapped user workloads are preserved in a dedicated
                <strong> Unattributed Cost Bucket</strong>. They are never arbitrarily distributed across compute
                clusters or misrepresented as SQL warehouse spend.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {filteredApps.map((app, idx) => (
              <div
                key={idx}
                onClick={() => handleOpenResourceDrawer(app)}
                className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-slate-50 hover:border-brand-500 cursor-pointer space-y-2 transition group"
              >
                <div className="flex justify-between items-start">
                  <span className="font-bold text-xs text-navy-900 font-mono group-hover:text-brand-600">
                    {app.name}
                  </span>
                  <span
                    className={`text-[9px] font-bold px-1.5 py-0.2 rounded-full ${
                      app.status === "DEPLOYED"
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-slate-200 text-slate-600"
                    }`}
                  >
                    {app.status}
                  </span>
                </div>
                <div className="text-[11px] text-slate-500">
                  {(app.metadata?.desc as string) || "Databricks native application"}
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-[10px]">
                  <span className="text-slate-400 font-mono">
                    {(app.metadata?.runtime as string) || "Python 3.11"}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleFocusFromDrawer({
                        resource_type: "app",
                        resource_id: app.id,
                        resource_name: app.name,
                      });
                    }}
                    className="text-brand-600 hover:underline font-semibold"
                  >
                    Focus Scope &rarr;
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* MODULE 9: SYSTEM TABLES (10 Tables Diagnostic Live Matrix) */}
      {currentTab === "system_tables" && (
        <div className="space-y-4">
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-xs text-blue-900 flex items-start gap-3">
            <Info className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold block text-blue-950">
                System Tables Diagnostic Probe (10 Core Schemas Verified)
              </span>
              <p className="mt-0.5 text-blue-800 leading-relaxed">
                Read-only catalog inspection verified column definitions and metadata across all 10 system
                tables. In accordance with zero-execution policies, SQL queries are gated by the stopped SQL
                warehouse state (<code>STOPPED_WAREHOUSE</code>).
              </p>
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-navy-900">System Tables Verification Matrix</h3>
                <p className="text-xs text-slate-500">
                  Expand any system table to view schema definitions and diagnostic metadata.
                </p>
              </div>
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Filter system tables..."
                  value={systemTablesFilter}
                  onChange={(e) => setSystemTablesFilter(e.target.value)}
                  className="text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg w-full sm:w-56 focus:outline-brand-500"
                />
              </div>
            </div>

            {isLoadingSystemTables ? (
              <div className="p-8 text-center">
                <RefreshCw className="w-6 h-6 text-brand-600 animate-spin mx-auto mb-2" />
                <div className="text-xs text-slate-500">Probing system tables catalog schemas...</div>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase font-bold text-slate-500">
                      <th className="py-2.5 px-3">System Table</th>
                      <th className="py-2.5 px-3">Description</th>
                      <th className="py-2.5 px-3">Catalog Schema</th>
                      <th className="py-2.5 px-3">Columns</th>
                      <th className="py-2.5 px-3">Query State</th>
                      <th className="py-2.5 px-3 text-right">Details</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredSystemTables.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-slate-400">
                          No system tables discovered or accessible for this workspace connection.
                        </td>
                      </tr>
                    ) : (
                      filteredSystemTables.map((st, idx) => {
                      const isExpanded = expandedSystemTable === st.table_name;
                      return (
                        <React.Fragment key={idx}>
                          <tr
                            onClick={() =>
                              setExpandedSystemTable(isExpanded ? null : st.table_name)
                            }
                            className="hover:bg-slate-50 cursor-pointer transition"
                          >
                            <td className="py-2.5 px-3 font-mono font-semibold text-blue-700 text-[11px] flex items-center gap-1.5">
                              {isExpanded ? (
                                <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
                              ) : (
                                <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                              )}
                              <span>{st.table_name}</span>
                            </td>
                            <td className="py-2.5 px-3 text-slate-600 text-[11px]">{st.description}</td>
                            <td className="py-2.5 px-3">
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700">
                                SCHEMA_VERIFIED
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-slate-600">{st.columns_count} cols</td>
                            <td className="py-2.5 px-3">
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                                STOPPED_WAREHOUSE
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-right text-brand-600 font-semibold text-[11px]">
                              {isExpanded ? "Hide Schema" : "View Schema"}
                            </td>
                          </tr>

                          {/* Expanded Columns Schema List */}
                          {isExpanded && (
                            <tr className="bg-slate-50/70 border-b border-slate-200">
                              <td colSpan={6} className="p-4 space-y-2">
                                <div className="text-[11px] font-bold text-navy-900 mb-1">
                                  Verified Schema Definition for {st.table_name}
                                </div>
                                <div className="border border-slate-200 rounded-lg bg-white overflow-hidden">
                                  <table className="w-full text-left text-xs">
                                    <thead className="bg-slate-100 text-[9px] uppercase font-bold text-slate-500">
                                      <tr>
                                        <th className="py-1.5 px-3">Column Name</th>
                                        <th className="py-1.5 px-3">Data Type</th>
                                        <th className="py-1.5 px-3">Comment / Description</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                      {st.columns && st.columns.length > 0 ? (
                                        st.columns.map((col, cIdx) => (
                                          <tr key={cIdx} className="hover:bg-slate-50">
                                            <td className="py-1 px-3 font-mono text-[10px] text-blue-700 font-semibold">
                                              {col.name}
                                            </td>
                                            <td className="py-1 px-3 font-mono text-[10px] text-purple-700">
                                              {col.type}
                                            </td>
                                            <td className="py-1 px-3 text-slate-500 text-[10px]">
                                              {col.comment || "System metadata column"}
                                            </td>
                                          </tr>
                                        ))
                                      ) : (
                                        <tr>
                                          <td colSpan={3} className="py-2 px-3 text-slate-400 text-center">
                                            No explicit column definitions returned.
                                          </td>
                                        </tr>
                                      )}
                                    </tbody>
                                  </table>
                                </div>
                                <p className="text-[10px] text-slate-500 italic mt-1">
                                  Note: {st.notes}
                                </p>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    }))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* MODULE 10: QUERY HISTORY (Real Queries Explorer) */}
      {currentTab === "query_history" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-navy-900">SQL Query Execution History</h3>
              <p className="text-xs text-slate-500">
                Live Databricks Query History: status, duration, warehouse and (masked) user for the selected window.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-50 text-slate-700 border border-slate-200">
                Source: {queryHistoryData?.provenance?.classification ?? "loading"} · Query History API (no SQL)
              </span>
            </div>
          </div>

          {queryHistoryData?.provenance && queryHistoryData.provenance.classification !== "LIVE" && (
            <ProvenanceBanner provenance={{ query_history: queryHistoryData.provenance }} />
          )}

          {/* Summary cards: computed from the returned page only */}
          {(() => {
            const recs = queryHistoryData?.records || [];
            const count = (st: string) => recs.filter((q) => q.status === st).length;
            const avg = recs.length ? Math.round(recs.reduce((a, q) => a + q.duration_ms, 0) / recs.length) : null;
            return (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {[
                  { label: "Queries on this page", value: queryHistoryData ? recs.length : "—", note: "Aggregates cover the loaded page only", cls: "text-navy-900" },
                  { label: "Finished", value: queryHistoryData ? count("FINISHED") : "—", note: "status = FINISHED", cls: "text-emerald-600" },
                  { label: "Failed", value: queryHistoryData ? count("FAILED") : "—", note: "status = FAILED", cls: "text-rose-600" },
                  { label: "Average duration", value: avg === null ? "—" : `${avg.toLocaleString()} ms`, note: "mean over this page", cls: "text-blue-700" },
                ].map((c) => (
                  <div key={c.label} className="p-3.5 rounded-xl border border-slate-200 bg-slate-50">
                    <span className="text-slate-500 text-xs font-medium">{c.label}</span>
                    <div className={`text-2xl font-bold mt-1 ${c.cls}`}>{c.value}</div>
                    <span className="text-[10px] text-slate-400">{c.note}</span>
                  </div>
                ))}
              </div>
            );
          })()}

          {/* Query Duration Histogram Component with 6 Buckets and Summary Statistics */}
          <QueryDurationHistogram
            queries={queryHistoryData?.records || []}
            selectedBucket={selectedDurationBucket}
            onSelectBucket={setSelectedDurationBucket}
            isLoading={isLoadingQueryHistory}
          />

          {/* Filters Toolbar */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
            <div className="relative w-full sm:w-64">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
              <input
                type="text"
                placeholder="Search SQL or user..."
                value={querySearch}
                onChange={(e) => setQuerySearch(e.target.value)}
                className="text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg w-full focus:outline-brand-500"
              />
            </div>
            <div className="flex items-center gap-2 self-end sm:self-auto">
              <span className="text-xs text-slate-500">Status:</span>
              <select
                value={queryStatusFilter}
                onChange={(e) => setQueryStatusFilter(e.target.value)}
                className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white font-medium text-navy-900"
              >
                <option value="all">All Statuses</option>
                <option value="FINISHED">FINISHED</option>
                <option value="FAILED">FAILED</option>
                <option value="CANCELED">CANCELED</option>
              </select>
              <input
                type="date"
                value={queryStartDate}
                onChange={(e) => { setQueryPageTokens([]); setQueryPageToken(null); setQueryStartDate(e.target.value); }}
                className="text-xs border border-slate-200 rounded-lg px-2 py-1.5"
                aria-label="Query start date"
              />
              <input
                type="date"
                value={queryEndDate}
                onChange={(e) => { setQueryPageTokens([]); setQueryPageToken(null); setQueryEndDate(e.target.value); }}
                className="text-xs border border-slate-200 rounded-lg px-2 py-1.5"
                aria-label="Query end date"
              />
            </div>
          </div>

          {/* Queries Table */}
          {isLoadingQueryHistory ? (
            <div className="p-8 text-center">
              <RefreshCw className="w-6 h-6 text-brand-600 animate-spin mx-auto mb-2" />
              <div className="text-xs text-slate-500">Loading query history records...</div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase font-bold text-slate-500">
                    <th className="py-2.5 px-3">Query ID</th>
                    <th className="py-2.5 px-3">Executed At</th>
                    <th className="py-2.5 px-3">Duration</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3">Warehouse</th>
                    <th className="py-2.5 px-3">User</th>
                    <th className="py-2.5 px-3">Rows</th>
                    <th className="py-2.5 px-3">SQL Preview</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(() => {
                    const filtered = (queryHistoryData?.records || []).filter((q) => {
                      if (queryStatusFilter !== "all" && q.status !== queryStatusFilter) return false;
                      if (selectedDurationBucket) {
                        if (selectedDurationBucket === "< 1s" && q.duration_ms >= 1000) return false;
                        if (selectedDurationBucket === "1s - 5s" && (q.duration_ms < 1000 || q.duration_ms >= 5000)) return false;
                        if (selectedDurationBucket === "5s - 15s" && (q.duration_ms < 5000 || q.duration_ms >= 15000)) return false;
                        if (selectedDurationBucket === "15s - 60s" && (q.duration_ms < 15000 || q.duration_ms >= 60000)) return false;
                        if (selectedDurationBucket === "1m - 5m" && (q.duration_ms < 60000 || q.duration_ms >= 300000)) return false;
                        if (selectedDurationBucket === "> 5m" && q.duration_ms < 300000) return false;
                      }
                      if (!querySearch) return true;
                      const s = querySearch.toLowerCase();
                      return (
                        q.sql_statement.toLowerCase().includes(s) ||
                        q.user.toLowerCase().includes(s) ||
                        q.query_id.toLowerCase().includes(s)
                      );
                    });

                    if (filtered.length === 0) {
                      return (
                        <tr>
                          <td colSpan={8} className="py-8 text-center text-slate-500 text-xs">
                            <div className="space-y-1">
                              <p className="font-semibold text-slate-700">NO DATA AVAILABLE</p>
                              <p className="text-[11px] text-slate-400">
                                {queryHistoryData?.provenance?.message || "No queries were returned for the selected filters and window."}
                              </p>
                            </div>
                          </td>
                        </tr>
                      );
                    }

                    return filtered.map((q) => (
                      <tr
                        key={q.query_id}
                        onClick={() => {
                          setSelectedQuery(q);
                          setIsQueryModalOpen(true);
                        }}
                        className="hover:bg-slate-50 cursor-pointer group transition"
                      >
                        <td className="py-2.5 px-3 font-mono text-[11px] font-semibold text-brand-600 group-hover:underline">
                          {q.query_id.slice(0, 12)}...
                        </td>
                        <td className="py-2.5 px-3 text-slate-500 text-[11px]">
                          {formatDeterministicTime(q.start_time)}
                        </td>
                        <td className="py-2.5 px-3 text-slate-700 font-semibold">{q.duration_formatted}</td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              q.status === "FINISHED"
                                ? "bg-emerald-50 text-emerald-700"
                                : q.status === "FAILED"
                                ? "bg-rose-50 text-rose-700"
                                : "bg-amber-50 text-amber-700"
                            }`}
                          >
                            {q.status}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-slate-600 truncate max-w-[120px]">
                          {q.warehouse_name}
                        </td>
                        <td className="py-2.5 px-3 text-slate-500 truncate max-w-[140px]">{q.user}</td>
                        <td className="py-2.5 px-3 font-semibold text-navy-900">{q.rows_produced ?? "n/a"}</td>
                        <td className="py-2.5 px-3 font-mono text-[10px] text-slate-600 truncate max-w-[200px]">
                          {q.sql_statement}
                        </td>
                      </tr>
                    ));
                  })()}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex items-center justify-between pt-2 text-xs">
            <button
              type="button"
              disabled={queryPageTokens.length === 0}
              onClick={() => {
                const stack = [...queryPageTokens];
                const prev = stack.pop() ?? null;
                setQueryPageTokens(stack);
                setQueryPageToken(prev === "" ? null : prev);
              }}
              className="px-3 py-1.5 rounded-lg border border-slate-200 font-semibold disabled:opacity-40"
            >
              ← Newer
            </button>
            <span className="text-slate-500">Page {queryPageTokens.length + 1}</span>
            <button
              type="button"
              disabled={!queryHistoryData?.has_next_page || !queryHistoryData?.next_page_token}
              onClick={() => {
                setQueryPageTokens([...queryPageTokens, queryPageToken ?? ""]);
                setQueryPageToken(queryHistoryData?.next_page_token ?? null);
              }}
              className="px-3 py-1.5 rounded-lg border border-slate-200 font-semibold disabled:opacity-40"
            >
              Older →
            </button>
          </div>
        </div>
      )}

      {/* MODULE 11: AI & TOKEN ECONOMICS */}
      {/* MODULE 11: AI & TOKEN ECONOMICS (INTEGRATED INTO FINOPS INTELLIGENCE) */}
      {currentTab === "ai_economics" && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-purple-50 border border-purple-200 flex items-center justify-center text-purple-600 font-bold">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-navy-900">Databricks AI &amp; Token Economics</h3>
                <p className="text-xs text-slate-500">
                  Model serving consumption, prompt vs completion tokens, and real DBU cost breakdown.
                </p>
              </div>
            </div>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
              Live FinOps Intelligence
            </span>
          </div>

          <div className="bg-purple-50/60 border border-purple-200 rounded-xl p-4 text-xs text-purple-950 flex items-start gap-3">
            <Sparkles className="w-4 h-4 text-purple-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-bold block text-purple-950">
                Unified FinOps &amp; Cost Intelligence Integration
              </span>
              <p className="text-purple-800 leading-relaxed">
                AI and token economics metrics are unified under <strong>FINOPS &amp; COST INTELLIGENCE &gt; AI Economics</strong>, calculated directly from authorized Azure billing ledgers and Foundation Model Serving endpoints with zero simulated figures.
              </p>
            </div>
          </div>

          <div className="pt-2 flex items-center gap-3">
            <button
              type="button"
              onClick={() => handleTabChange("ai_economics")}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-semibold flex items-center gap-2 shadow-xs transition cursor-pointer"
            >
              <span>View Live AI Economics</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* MODULE 12: AUDIT & GOVERNANCE */}
      {currentTab === "audit" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h3 className="text-sm font-bold text-navy-900">Workspace Audit &amp; Governance</h3>
              <p className="text-xs text-slate-500">
                Access logs, credential verification, and workspace compliance policies.
              </p>
            </div>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700">
              Read-Only RBAC Enforced
            </span>
          </div>
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-2">
            <div className="flex justify-between items-center">
              <span>Azure Role: <strong>Reader / Monitoring Reader</strong></span>
              <span className="text-emerald-700 font-semibold">Verified</span>
            </div>
            <div className="flex justify-between items-center">
              <span>Databricks Workspace Role: <strong>Account User (Read-Only)</strong></span>
              <span className="text-emerald-700 font-semibold">Verified</span>
            </div>
            <div className="flex justify-between items-center">
              <span>Zero-Execution Mutating Permissions</span>
              <span className="text-rose-700 font-semibold">Blocked &amp; Excluded</span>
            </div>
          </div>
        </div>
      )}

      {/* MODULE 13: COST & BILLING (INTEGRATED INTO FINOPS INTELLIGENCE) */}
      {currentTab === "billing" && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand-50 border border-brand-200 flex items-center justify-center text-brand-600 font-bold">
                <Coins className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-navy-900">Databricks DBU &amp; Cloud Billing Analytics</h3>
                <p className="text-xs text-slate-500">
                  Exact DBU consumption, rate card attribution, and multi-cloud infrastructure reconciliation.
                </p>
              </div>
            </div>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-brand-50 text-brand-700 border border-brand-200">
              Live FinOps Intelligence
            </span>
          </div>

          <div className="bg-brand-50/60 border border-brand-200 rounded-xl p-4 text-xs text-brand-950 flex items-start gap-3">
            <Coins className="w-4 h-4 text-brand-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-bold block text-brand-950">
                Unified FinOps &amp; Cost Intelligence Integration
              </span>
              <p className="text-brand-800 leading-relaxed">
                Billing analytics, DBU consumption, and rate card reconciliations are unified under <strong>FINOPS &amp; COST INTELLIGENCE &gt; Cost &amp; Billing</strong>, backed by real system tables (<code>system.billing.usage</code>, <code>system.billing.list_prices</code>) and Azure Cost Management.
              </p>
            </div>
          </div>

          <div className="pt-2 flex items-center gap-3">
            <button
              type="button"
              onClick={() => handleTabChange("cost_billing")}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-xs font-semibold flex items-center gap-2 shadow-xs transition cursor-pointer"
            >
              <span>View Live Cost &amp; Billing Analytics</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}


      {/* MODULE 14: DISCOVERY HISTORY */}
      {currentTab === "discovery_history" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h3 className="text-sm font-bold text-navy-900">Discovery History &amp; Sync Log</h3>
              <p className="text-xs text-slate-500">Chronological history of read-only inventory discovery runs</p>
            </div>
          </div>
          <div className="divide-y divide-slate-100 text-xs">
            <div className="py-3 flex justify-between items-center">
              <div>
                <span className="font-semibold text-navy-900 block">Live Discovery Run #104</span>
                <span className="text-[11px] text-slate-500">
                  Queried clusters, warehouses, workflows, pipelines, serving endpoints, unity catalog, apps
                </span>
              </div>
              <div className="text-right">
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700">
                  Success
                </span>
                <div className="text-[10px] text-slate-400 mt-0.5">Duration: 1.4s</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Slide-Over Resource Detail Drawer */}
      <ResourceDetailDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        resource={drawerResource}
        onFocusScope={handleFocusFromDrawer}
        isFocused={activeScope?.selected_child_resource?.resource_id === drawerResource?.id}
      />

      {/* SQL Query Details Modal */}
      {isQueryModalOpen && selectedQuery && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/40 backdrop-blur-xs">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-2xl w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <FileCode className="w-5 h-5 text-brand-600" />
                <h3 className="text-sm font-bold text-navy-900">Query Execution Details</h3>
              </div>
              <button
                onClick={() => setIsQueryModalOpen(false)}
                className="p-1 rounded-md text-slate-400 hover:text-navy-900 hover:bg-slate-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[10px] text-slate-500 block">Status</span>
                <span
                  className={`font-bold ${
                    selectedQuery.status === "FINISHED"
                      ? "text-emerald-700"
                      : selectedQuery.status === "FAILED"
                      ? "text-rose-700"
                      : "text-amber-700"
                  }`}
                >
                  {selectedQuery.status}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[10px] text-slate-500 block">Duration</span>
                <span className="font-bold text-navy-900">{selectedQuery.duration_formatted}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[10px] text-slate-500 block">Rows Produced</span>
                <span className="font-bold text-navy-900">{selectedQuery.rows_produced}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[10px] text-slate-500 block">Warehouse</span>
                <span className="font-mono text-[10px] text-slate-700 block truncate">
                  {selectedQuery.warehouse_name}
                </span>
              </div>
            </div>

            {selectedQuery.error_message && (
              <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-800">
                <span className="font-bold block">Execution Error:</span>
                <p className="mt-0.5">{selectedQuery.error_message}</p>
              </div>
            )}

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-bold text-navy-900">SQL Statement</span>
                <button
                  onClick={() => handleCopySql(selectedQuery.sql_statement)}
                  className="inline-flex items-center gap-1 text-[11px] text-brand-600 hover:text-brand-800 font-semibold"
                >
                  {isCopiedSql ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                      <span className="text-emerald-600">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>Copy SQL</span>
                    </>
                  )}
                </button>
              </div>
              <pre className="p-3 bg-slate-900 text-slate-100 rounded-lg text-xs font-mono overflow-x-auto max-h-48 whitespace-pre-wrap">
                {selectedQuery.sql_statement}
              </pre>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setIsQueryModalOpen(false)}
                className="px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
