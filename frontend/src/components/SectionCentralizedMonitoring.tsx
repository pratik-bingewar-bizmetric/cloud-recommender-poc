"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  CloudConnection,
  CloudProvider,
  CloudScopeSummary,
  TimeWindowPreset,
  MetricInterval,
  MonitoringOverviewResponse,
  ResourceDetailMonitoringResponse,
  LogSearchResponse,
  LogSeverity,
  MetricTimeSeries,
  SubscriptionOrProjectAnalysis,
} from "@/types";
import {
  listAzureSubscriptions,
  listGcpProjects,
  getMonitoringOverview,
  getResourceMonitoringDetail,
  searchMonitoringLogs,
  analyzeAzureSubscription,
  analyzeGcpProject,
} from "@/lib/api";
import { SectionTokenEconomics } from "@/components/SectionTokenEconomics";
import { SectionCostWaste } from "@/components/SectionCostWaste";
import { TelemetryCoverageDrawer } from "@/components/TelemetryCoverageDrawer";
import { FinancialKpiDrawer } from "@/components/FinancialKpiDrawer";
import { buildCanonicalFinancialSummary } from "@/lib/financials";
import { FinancialKpiType } from "@/types/financials";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  AlertOctagon,
  Clock,
  Cpu,
  FolderTree,
  Layers,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  TrendingDown,
  X,
  ChevronDown,
  ChevronRight,
  Info,
  Terminal,
  SlidersHorizontal,
  ArrowRight,
  BellRing,
  Filter,
} from "lucide-react";

export type MonitoringSubTab =
  | "overview"
  | "resources"
  | "health"
  | "alerts"
  | "hierarchy"
  | "logs"
  | "tokens"
  | "cost_waste";

interface SectionCentralizedMonitoringProps {
  initialConnection?: CloudConnection | null;
  activeTab?: MonitoringSubTab;
  onTabChange?: (tab: MonitoringSubTab) => void;
  onSwitchConnection?: () => void;
}

export interface GranularityOption {
  interval: MetricInterval;
  supported: boolean;
  reason?: string;
  recommended?: boolean;
}

export function getSupportedGranularities(
  range: TimeWindowPreset,
  provider: CloudProvider
): GranularityOption[] {
  switch (range) {
    case "1h":
      return [
        { interval: "1m", supported: true, recommended: true },
        { interval: "5m", supported: true },
        { interval: "15m", supported: true },
        { interval: "1h", supported: true },
        {
          interval: "1d",
          supported: false,
          reason: "1d interval exceeds 1h window duration",
        },
      ];
    case "24h":
      return [
        {
          interval: "1m",
          supported: provider === "gcp",
          reason:
            provider === "azure"
              ? "1m over 24h exceeds Azure Monitor multi-metric query limits (max 1,440 points)"
              : undefined,
        },
        { interval: "5m", supported: true },
        { interval: "15m", supported: true },
        { interval: "1h", supported: true, recommended: true },
        { interval: "1d", supported: true },
      ];
    case "7d":
      return [
        {
          interval: "1m",
          supported: false,
          reason: "1m over 7d requires 10,080 points; exceeds cloud provider query limits",
        },
        {
          interval: "5m",
          supported: false,
          reason: "5m over 7d exceeds multi-metric single query limits (>2,000 points)",
        },
        { interval: "15m", supported: true },
        { interval: "1h", supported: true, recommended: true },
        { interval: "1d", supported: true },
      ];
    case "30d":
      return [
        {
          interval: "1m",
          supported: false,
          reason: "1m telemetry is not retained beyond 30 days and exceeds query limits",
        },
        {
          interval: "5m",
          supported: false,
          reason: "5m telemetry exceeds cloud provider query limits for 30d",
        },
        {
          interval: "15m",
          supported: false,
          reason: "15m telemetry exceeds single-query metric limits for 30d",
        },
        { interval: "1h", supported: true },
        { interval: "1d", supported: true, recommended: true },
      ];
    case "90d":
      return [
        {
          interval: "1m",
          supported: false,
          reason: "Sub-hourly metrics are pruned after 30 days by provider retention policies",
        },
        {
          interval: "5m",
          supported: false,
          reason: "Sub-hourly metrics are pruned after 30 days by provider retention policies",
        },
        {
          interval: "15m",
          supported: false,
          reason: "Sub-hourly metrics are pruned after 30 days by provider retention policies",
        },
        {
          interval: "1h",
          supported: false,
          reason: "1h over 90d exceeds provider query limits; use 1d aggregation",
        },
        { interval: "1d", supported: true, recommended: true },
      ];
    default:
      return [
        { interval: "1m", supported: true },
        { interval: "5m", supported: true },
        { interval: "15m", supported: true },
        { interval: "1h", supported: true },
        { interval: "1d", supported: true },
      ];
  }
}

export function SectionCentralizedMonitoring({
  initialConnection,
  activeTab,
  onTabChange,
}: SectionCentralizedMonitoringProps) {
  // Provider and Scope Selection
  const [provider, setProvider] = useState<CloudProvider>(
    initialConnection?.provider ?? "azure"
  );
  const [scopes, setScopes] = useState<CloudScopeSummary[]>([]);
  const [selectedScopeId, setSelectedScopeId] = useState<string>(
    initialConnection?.scope_id ?? ""
  );
  const [selectedScopeName, setSelectedScopeName] = useState<string>(
    initialConnection?.display_name ?? initialConnection?.name ?? ""
  );

  // Time Window & Metric Interval Controls
  const [timeWindow, setTimeWindow] = useState<TimeWindowPreset>("7d");
  const [metricInterval, setMetricInterval] = useState<MetricInterval>("1h");
  const [granularityNotice, setGranularityNotice] = useState<string | null>(null);
  const [isCoverageDrawerOpen, setIsCoverageDrawerOpen] = useState<boolean>(false);

  const granularityOptions = useMemo(
    () => getSupportedGranularities(timeWindow, provider),
    [timeWindow, provider]
  );

  const handleTimeWindowChange = (newWindow: TimeWindowPreset) => {
    setTimeWindow(newWindow);
    const options = getSupportedGranularities(newWindow, provider);
    const currentOption = options.find((o) => o.interval === metricInterval);
    if (!currentOption || !currentOption.supported) {
      const fallback =
        options.find((o) => o.recommended && o.supported) ||
        options.find((o) => o.supported);
      if (fallback) {
        setMetricInterval(fallback.interval);
        setGranularityNotice(
          `Granularity adjusted to ${fallback.interval} (${currentOption?.reason || "exceeds limits for " + newWindow + " range"})`
        );
      }
    } else {
      setGranularityNotice(null);
    }
  };

  const handleMetricIntervalChange = (newInterval: MetricInterval) => {
    const options = getSupportedGranularities(timeWindow, provider);
    const target = options.find((o) => o.interval === newInterval);
    if (target && !target.supported) {
      setGranularityNotice(
        `Cannot select ${newInterval}: ${target.reason || "unsupported for " + timeWindow + " range"}`
      );
      return;
    }
    setMetricInterval(newInterval);
    setGranularityNotice(null);
  };

  // Contextual Filters State
  const [selectedGroupFilter, setSelectedGroupFilter] = useState<string>("");
  const [healthFilter, setHealthFilter] = useState<string>("all");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [searchFilter, setSearchFilter] = useState<string>("");
  const [isFiltersOpen, setIsFiltersOpen] = useState<boolean>(false);

  // Sub-Navigation Tab State (Synchronized with Sidebar and URL)
  const [internalSubTab, setInternalSubTab] =
    useState<MonitoringSubTab>("overview");
  const monitoringSubTab = activeTab ?? internalSubTab;

  const handleSubTabChange = (newTab: MonitoringSubTab) => {
    if (onTabChange) {
      onTabChange(newTab);
    } else {
      setInternalSubTab(newTab);
    }
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", newTab);
      window.history.replaceState({}, "", url.toString());
    }
  };

  // Safe Provider Switcher: Clears scope to prevent Azure UUID leakage into GCP
  const handleSwitchProvider = (newProvider: CloudProvider) => {
    if (newProvider === provider) return;
    setProvider(newProvider);
    setSelectedScopeId("");
    setSelectedScopeName("");
    setSelectedGroupFilter("");
    setOverview(null);
    setAnalysisData(null);
    setErrorMsg(null);
  };

  // Sync with initialConnection when changed from outside
  useEffect(() => {
    if (initialConnection) {
      setProvider(initialConnection.provider);
      setSelectedScopeId(initialConnection.scope_id);
      setSelectedScopeName(
        initialConnection.display_name || initialConnection.name
      );
    }
  }, [initialConnection]);

  // Telemetry & Overview State
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [overview, setOverview] = useState<MonitoringOverviewResponse | null>(
    null
  );
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>(
    {}
  );

  // Cost & Waste Analysis State
  const [analysisData, setAnalysisData] =
    useState<SubscriptionOrProjectAnalysis | null>(null);
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState<boolean>(false);

  // Financial KPI Drill-Down Drawer State & Canonical Calculation
  const [financialDrawerKpi, setFinancialDrawerKpi] =
    useState<FinancialKpiType | null>(null);

  const canonicalFinancials = useMemo(() => {
    return buildCanonicalFinancialSummary(
      provider,
      selectedScopeId || selectedScopeName || "",
      selectedScopeName || selectedScopeId || "",
      timeWindow,
      "USD",
      overview,
      analysisData
    );
  }, [provider, selectedScopeId, selectedScopeName, timeWindow, overview, analysisData]);

  // Single Resource Deep Dive Modal / Drawer State (7 Diagnostic Tabs)
  const [inspectedResourceId, setInspectedResourceId] = useState<string | null>(
    null
  );
  const [resourceDetail, setResourceDetail] =
    useState<ResourceDetailMonitoringResponse | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);
  const [resourceActiveTab, setResourceActiveTab] = useState<
    | "overview"
    | "metrics"
    | "logs"
    | "alerts"
    | "dependencies"
    | "cost"
    | "debt"
  >("overview");

  // Log Explorer Search State
  const [logQuery, setLogQuery] = useState<string>("");
  const [logSeverity, setLogSeverity] = useState<string>("all");
  const [logResults, setLogResults] = useState<LogSearchResponse | null>(null);
  const [isSearchingLogs, setIsSearchingLogs] = useState<boolean>(false);

  // 1. Load Available Scopes
  const loadScopes = useCallback(
    async (targetProvider: CloudProvider, preferredScopeId?: string) => {
      setErrorMsg(null);
      try {
        if (targetProvider === "azure") {
          const azSubs = await listAzureSubscriptions();
          setScopes(azSubs);
          if (azSubs.length > 0) {
            const match = preferredScopeId
              ? azSubs.find((s) => s.scope_id === preferredScopeId)
              : null;
            const chosen = match || azSubs[0];
            setSelectedScopeId(chosen.scope_id);
            setSelectedScopeName(chosen.display_name);
          }
        } else {
          const gcpProjs = await listGcpProjects();
          setScopes(gcpProjs);
          if (gcpProjs.length > 0) {
            const match = preferredScopeId
              ? gcpProjs.find((s) => s.scope_id === preferredScopeId)
              : null;
            const chosen = match || gcpProjs[0];
            setSelectedScopeId(chosen.scope_id);
            setSelectedScopeName(chosen.display_name);
          }
        }
      } catch (err: unknown) {
        setErrorMsg(
          err instanceof Error ? err.message : "Failed to load cloud scopes."
        );
      }
    },
    []
  );

  useEffect(() => {
    loadScopes(provider);
  }, [provider, loadScopes]);

  // 2. Fetch Monitoring Overview with Request Sequencing & Stale Cancellation
  const overviewSeqRef = useRef<number>(0);
  const overviewAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      overviewAbortRef.current?.abort();
    };
  }, []);

  const fetchOverview = useCallback(
    async (forceRefresh = false) => {
      if (!selectedScopeId) return;
      overviewAbortRef.current?.abort();
      const abortController = new AbortController();
      overviewAbortRef.current = abortController;
      const seq = ++overviewSeqRef.current;

      if (forceRefresh) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }
      setErrorMsg(null);
      try {
        const data = await getMonitoringOverview(
          {
            provider,
            scope_id: selectedScopeId,
            resource_group_filter: selectedGroupFilter || undefined,
            time_window: timeWindow,
            interval: metricInterval,
            force_refresh: forceRefresh,
          },
          abortController.signal
        );
        if (seq === overviewSeqRef.current) {
          setOverview(data);
        }
      } catch (err: unknown) {
        if (
          abortController.signal.aborted ||
          (err instanceof DOMException && err.name === "AbortError")
        ) {
          return;
        }
        if (seq === overviewSeqRef.current) {
          setErrorMsg(
            err instanceof Error
              ? err.message
              : "Failed to load monitoring overview."
          );
        }
      } finally {
        if (seq === overviewSeqRef.current) {
          setIsLoading(false);
          setIsRefreshing(false);
        }
      }
    },
    [
      provider,
      selectedScopeId,
      selectedGroupFilter,
      timeWindow,
      metricInterval,
    ]
  );

  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

  // 3. Fetch Single Resource Deep Dive
  const inspectResource = async (resId: string) => {
    setInspectedResourceId(resId);
    setIsLoadingDetail(true);
    setResourceActiveTab("overview");
    try {
      const detail = await getResourceMonitoringDetail({
        provider,
        scope_id: selectedScopeId,
        resource_id: resId,
        time_window: timeWindow,
        interval: metricInterval,
      });
      setResourceDetail(detail);
    } catch (err) {
      console.warn("Failed to inspect resource telemetry:", err);
    } finally {
      setIsLoadingDetail(false);
    }
  };

  // 4. Log Explorer Query
  const executeLogSearch = useCallback(async () => {
    if (!selectedScopeId) return;
    setIsSearchingLogs(true);
    try {
      const logsData = await searchMonitoringLogs({
        provider,
        scope_id: selectedScopeId,
        query: logQuery || undefined,
        severity:
          logSeverity !== "all" ? (logSeverity as LogSeverity) : undefined,
        time_window: timeWindow,
        page: 1,
        page_size: 50,
      });
      setLogResults(logsData);
    } catch (err) {
      console.warn("Log search error:", err);
    } finally {
      setIsSearchingLogs(false);
    }
  }, [provider, selectedScopeId, logQuery, logSeverity, timeWindow]);

  useEffect(() => {
    if (monitoringSubTab === "logs") {
      executeLogSearch();
    }
  }, [monitoringSubTab, executeLogSearch]);

  // 5. Fetch Cost & Waste Analysis
  const fetchAnalysis = useCallback(async () => {
    if (!selectedScopeId) return;
    setIsLoadingAnalysis(true);
    try {
      if (provider === "azure") {
        const res = await analyzeAzureSubscription({
          scope_id: selectedScopeId,
          resource_group_filter: selectedGroupFilter || undefined,
        });
        setAnalysisData(res);
      } else {
        const res = await analyzeGcpProject({
          scope_id: selectedScopeId,
        });
        setAnalysisData(res);
      }
    } catch (err) {
      console.warn("Waste analysis query error:", err);
    } finally {
      setIsLoadingAnalysis(false);
    }
  }, [provider, selectedScopeId, selectedGroupFilter]);

  useEffect(() => {
    if (monitoringSubTab === "cost_waste" && !analysisData) {
      fetchAnalysis();
    }
  }, [monitoringSubTab, analysisData, fetchAnalysis]);

  const toggleGroupExpand = (grpName: string) => {
    setExpandedGroups((prev) => ({ ...prev, [grpName]: !prev[grpName] }));
  };

  // Render SVG Timeseries Chart
  const renderSimpleTimeSeries = (
    series: MetricTimeSeries,
    strokeColor = "#3b82f6"
  ) => {
    if (!series || !series.data_points || series.data_points.length === 0) {
      return (
        <div className="h-32 flex items-center justify-center text-xs text-slate-400 italic">
          No timeseries data samples available in this interval
        </div>
      );
    }

    const points = series.data_points;
    const maxVal = Math.max(...points.map((p) => p.value), 10);
    const minVal = Math.min(...points.map((p) => p.value), 0);
    const range = maxVal - minVal || 1;

    const width = 500;
    const height = 120;
    const padding = 10;

    const svgPoints = points
      .map((p, idx) => {
        const x =
          padding +
          (idx / Math.max(points.length - 1, 1)) * (width - 2 * padding);
        const y =
          height -
          padding -
          ((p.value - minVal) / range) * (height - 2 * padding);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

    const areaPoints = `${padding},${height - padding} ${svgPoints} ${
      width - padding
    },${height - padding}`;

    return (
      <div className="w-full">
        <div className="flex items-center justify-between text-xs mb-1.5">
          <span className="font-semibold text-slate-800">
            {series.display_name}
          </span>
          <span className="font-mono text-slate-500">
            Avg: {series.summary.avg ?? "N/A"}% &bull; Peak:{" "}
            {series.summary.max ?? "N/A"}% &bull; Current:{" "}
            {series.summary.current ?? "N/A"}%
          </span>
        </div>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-28 overflow-visible"
        >
          <defs>
            <linearGradient
              id={`grad-${series.metric_name}-${series.resource_name}`}
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.25" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
            </linearGradient>
          </defs>
          <polyline
            fill={`url(#grad-${series.metric_name}-${series.resource_name})`}
            points={areaPoints}
          />
          <polyline
            fill="none"
            stroke={strokeColor}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            points={svgPoints}
          />
          {points.map((p, idx) => {
            const x =
              padding +
              (idx / Math.max(points.length - 1, 1)) * (width - 2 * padding);
            const y =
              height -
              padding -
              ((p.value - minVal) / range) * (height - 2 * padding);
            return (
              <circle
                key={idx}
                cx={x}
                cy={y}
                r="3"
                className="fill-white"
                stroke={strokeColor}
                strokeWidth="2"
              >
                <title>{`${new Date(p.timestamp).toLocaleTimeString()}: ${
                  p.value
                }${series.unit === "Percent" ? "%" : ""}`}</title>
              </circle>
            );
          })}
        </svg>
      </div>
    );
  };

  // Filtered resources helper
  const filteredHealthRecords = overview
    ? overview.health_records.filter((h) => {
        const matchesGroup =
          !selectedGroupFilter || h.resource_id.includes(selectedGroupFilter);
        const matchesHealth =
          healthFilter === "all" || h.health_state === healthFilter;
        const matchesSearch =
          !searchFilter ||
          h.resource_name.toLowerCase().includes(searchFilter.toLowerCase()) ||
          h.native_type.toLowerCase().includes(searchFilter.toLowerCase());
        return matchesGroup && matchesHealth && matchesSearch;
      })
    : [];

  return (
    <section id="section-monitoring" className="space-y-6">
      {/* Structured Provider Error Banner */}
      {errorMsg && (
        <div className="p-4 bg-white border border-rose-200 rounded-2xl shadow-xs flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center shrink-0 mt-0.5">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-rose-100 text-rose-800">
                  {errorMsg.includes("403")
                    ? "403 Forbidden"
                    : errorMsg.includes("UUID") || errorMsg.includes("400")
                    ? "Scope Mismatch"
                    : "Provider Notice"}
                </span>
                <span className="text-xs font-bold text-navy-900">
                  {errorMsg.includes("403")
                    ? "Read-Only Cloud Permissions Required"
                    : errorMsg.includes("UUID")
                    ? "Cross-Provider Scope Mismatch"
                    : "Cloud Monitoring Diagnostic"}
                </span>
              </div>
              <p className="text-xs text-slate-700 leading-relaxed font-mono">
                {errorMsg}
              </p>
              {errorMsg.includes("403") && (
                <p className="text-xs text-slate-500 pt-0.5">
                  <strong>Recommended Next Step:</strong> Project discovery requires least-privilege read-only role{" "}
                  <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">
                    roles/browser
                  </code>{" "}
                  (for project hierarchy) or{" "}
                  <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">
                    roles/cloudasset.viewer
                  </code>{" "}
                  (for asset inventory listing). Verify permissions in Google Cloud Console IAM or select an active project.
                </p>
              )}
              {errorMsg.includes("UUID") && (
                <p className="text-xs text-slate-500 pt-0.5">
                  <strong>Recommended Next Step:</strong> Please select an authorized Google Cloud Project from the scope dropdown.
                </p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setErrorMsg(null)}
            className="text-slate-400 hover:text-slate-600 p-1 shrink-0"
            title="Dismiss error notice"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* 1. Header & Controls Bar */}
      <div className="rounded-2xl bg-white border border-slate-200/90 p-5 shadow-xs space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 text-xs font-semibold">
                <Activity className="w-3.5 h-3.5 text-blue-600 animate-pulse" />
                Live Observability &amp; FinOps Intelligence
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-medium">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                Zero-Execution Policy &bull; Read-Only
              </span>
              <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold text-xs border border-slate-200 capitalize">
                {monitoringSubTab.replace("_", " & ")}
              </span>
            </div>
            <h2 className="text-xl font-extrabold text-slate-900 tracking-tight mt-1.5">
              Centralized Infrastructure Monitoring &amp; Log Intelligence
            </h2>
            <p className="text-xs text-slate-500 font-light mt-0.5">
              Continuous multi-cloud telemetry, historical logs, capacity bottlenecks, and evidence-backed FinOps waste diagnosis
              {selectedScopeName ? ` for ${selectedScopeName}` : ""}.
            </p>
          </div>

          {/* Provider & Scope Switchers */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Provider Switcher */}
            <div className="inline-flex p-1 bg-slate-100 rounded-xl border border-slate-200/80">
              <button
                type="button"
                onClick={() => handleSwitchProvider("azure")}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition ${
                  provider === "azure"
                    ? "bg-white text-blue-700 shadow-xs border border-slate-200/60"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Microsoft Azure
              </button>
              <button
                type="button"
                onClick={() => handleSwitchProvider("gcp")}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition ${
                  provider === "gcp"
                    ? "bg-white text-indigo-700 shadow-xs border border-slate-200/60"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Google Cloud
              </button>
            </div>

            {/* Scope Selector */}
            <select
              value={selectedScopeId}
              onChange={(e) => {
                const sId = e.target.value;
                setSelectedScopeId(sId);
                const found = scopes.find((s) => s.scope_id === sId);
                if (found) setSelectedScopeName(found.display_name);
              }}
              className="text-xs bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500 max-w-[220px] truncate"
            >
              {scopes.map((s) => (
                <option key={s.scope_id} value={s.scope_id}>
                  {s.display_name} ({s.scope_id.substring(0, 14)}...)
                </option>
              ))}
            </select>

            {/* Manual Force Refresh */}
            <button
              type="button"
              disabled={isRefreshing || isLoading}
              onClick={() => fetchOverview(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 transition shadow-xs"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`}
              />
              <span>{isRefreshing ? "Querying..." : "Refresh"}</span>
            </button>
          </div>
        </div>

        {/* 2. Streamlined Contextual Controls & Filter Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs pt-1">
          {/* Left: Filters Button & Search Input */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Contextual Filters Popover Trigger */}
            <button
              type="button"
              onClick={() => setIsFiltersOpen((prev) => !prev)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition ${
                searchFilter ||
                selectedGroupFilter ||
                healthFilter !== "all" ||
                severityFilter !== "all"
                  ? "bg-brand-50 border-brand-300 text-brand-700 shadow-2xs"
                  : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
            >
              <Filter className="w-3.5 h-3.5 text-slate-500" />
              <span>Filters</span>
              {(searchFilter ? 1 : 0) +
                (selectedGroupFilter ? 1 : 0) +
                (healthFilter !== "all" ? 1 : 0) +
                (severityFilter !== "all" ? 1 : 0) >
                0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-brand-600 text-white font-bold text-[10px]">
                  {(searchFilter ? 1 : 0) +
                    (selectedGroupFilter ? 1 : 0) +
                    (healthFilter !== "all" ? 1 : 0) +
                    (severityFilter !== "all" ? 1 : 0)}
                </span>
              )}
            </button>

            {/* Quick Search Input */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                placeholder="Quick filter services..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                className="text-xs pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-blue-500 w-44"
              />
            </div>
          </div>

          {/* Right: Time Range, Granularity, Provenance */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* 1. TIME RANGE Control */}
            <div
              className="flex items-center gap-1.5 bg-slate-100/90 px-2 py-1 rounded-xl border border-slate-200"
              role="group"
              aria-label="Time range selector"
            >
              <div
                className="flex items-center gap-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider pr-1.5 border-r border-slate-200"
                title="TIME RANGE: Total historical query window polled from cloud telemetry (1 hour to 90 days)."
              >
                <Clock className="w-3 h-3 text-slate-400" />
                <span>TIME RANGE</span>
              </div>
              <div className="flex items-center gap-1">
                {(
                  [
                    { key: "1h", label: "1h", title: "1 Hour — near real-time operational diagnostics" },
                    { key: "24h", label: "24h", title: "24 Hours — daily workload patterns" },
                    { key: "7d", label: "7d", title: "7 Days — rolling weekly trend" },
                    { key: "30d", label: "30d", title: "30 Days — monthly billing period reconciliation" },
                    { key: "90d", label: "90d", title: "90 Days — quarterly sizing evaluation" },
                  ] as const
                ).map((w) => (
                  <button
                    key={w.key}
                    type="button"
                    onClick={() => handleTimeWindowChange(w.key)}
                    aria-pressed={timeWindow === w.key}
                    title={w.title}
                    className={`px-2 py-0.5 rounded-md font-semibold text-[11px] transition focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:outline-hidden ${
                      timeWindow === w.key
                        ? "bg-white text-blue-700 shadow-2xs"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {w.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 2. GRANULARITY Control */}
            <div
              className="flex items-center gap-1.5 bg-slate-100/90 px-2 py-1 rounded-xl border border-slate-200"
              role="group"
              aria-label="Metric granularity selector"
            >
              <div
                className="flex items-center gap-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider pr-1.5 border-r border-slate-200"
                title="GRANULARITY: Time-bucket resolution and sampling frequency for timeseries data points (1 minute to 1 day)."
              >
                <SlidersHorizontal className="w-3 h-3 text-slate-400" />
                <span>GRANULARITY</span>
              </div>
              <div className="flex items-center gap-1">
                {granularityOptions.map((opt: GranularityOption) => {
                  const isSelected = metricInterval === opt.interval;
                  const isDisabled = !opt.supported;
                  const buttonTitle = isDisabled
                    ? `${opt.interval} (Disabled): ${opt.reason || "unsupported for " + timeWindow + " range"}`
                    : `${opt.interval} resolution${opt.recommended ? " (Recommended)" : ""}`;

                  return (
                    <button
                      key={opt.interval}
                      type="button"
                      disabled={isDisabled}
                      onClick={() => handleMetricIntervalChange(opt.interval)}
                      aria-pressed={isSelected}
                      aria-disabled={isDisabled}
                      title={buttonTitle}
                      className={`px-1.5 py-0.5 rounded-md font-mono text-[10px] transition focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:outline-hidden ${
                        isSelected
                          ? "bg-slate-900 text-white font-bold shadow-2xs"
                          : isDisabled
                          ? "text-slate-300 opacity-40 cursor-not-allowed"
                          : "text-slate-600 hover:text-slate-900 font-medium"
                      }`}
                    >
                      {opt.interval}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Data Provenance Badge */}
            {overview && (
              <span
                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${
                  overview.is_live
                    ? "bg-emerald-50 text-emerald-700 border-emerald-300"
                    : "bg-amber-50 text-amber-700 border-amber-300"
                }`}
              >
                {overview.is_live ? (
                  <>
                    <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                    Live API
                  </>
                ) : (
                  <>
                    <Info className="w-3 h-3 text-amber-600" />
                    Verified Benchmark
                  </>
                )}
              </span>
            )}
          </div>
        </div>

        {/* Granularity Adjustment Notice Banner */}
        {granularityNotice && (
          <div className="flex items-center justify-between gap-2 px-3 py-1.5 rounded-xl bg-blue-50/80 border border-blue-200 text-blue-900 text-[11px]">
            <div className="flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5 text-blue-600 shrink-0" />
              <span>{granularityNotice}</span>
            </div>
            <button
              type="button"
              onClick={() => setGranularityNotice(null)}
              className="text-blue-500 hover:text-blue-800 p-0.5"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        )}

        {/* 3. Contextual Filter Popover Drawer (When Toggled) */}
        {isFiltersOpen && (
          <div className="pt-3 border-t border-slate-100 bg-slate-50/70 p-4 rounded-xl space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-200/80">
              <h4 className="text-xs font-bold text-navy-950 uppercase tracking-wider flex items-center gap-1.5">
                <Filter className="w-3.5 h-3.5 text-brand-600" />
                <span>Contextual View Filters</span>
              </h4>
              <button
                type="button"
                onClick={() => setIsFiltersOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              {/* Group / Project Filter */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                  Resource Group / Scope Domain
                </label>
                <select
                  value={selectedGroupFilter}
                  onChange={(e) => setSelectedGroupFilter(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">All Groups</option>
                  {overview?.resource_groups_summary.map((rg) => (
                    <option key={rg.group_name} value={rg.group_name}>
                      {rg.group_name} ({rg.resource_count} resources)
                    </option>
                  ))}
                </select>
              </div>

              {/* Health State Filter */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                  Resource Health State
                </label>
                <select
                  value={healthFilter}
                  onChange={(e) => setHealthFilter(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                >
                  <option value="all">All Health States</option>
                  <option value="healthy">Healthy Only</option>
                  <option value="degraded">Degraded Only</option>
                  <option value="failing">Failing Only</option>
                  <option value="stopped">Stopped Only</option>
                </select>
              </div>

              {/* Alert Severity Filter */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                  Alert Severity Threshold
                </label>
                <select
                  value={severityFilter}
                  onChange={(e) => setSeverityFilter(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                >
                  <option value="all">All Severities</option>
                  <option value="critical">Critical Only</option>
                  <option value="high">High &amp; Critical</option>
                  <option value="medium">Medium, High &amp; Critical</option>
                  <option value="low">Low Severity Only</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-slate-200/80">
              <button
                type="button"
                onClick={() => {
                  setSelectedGroupFilter("");
                  setHealthFilter("all");
                  setSeverityFilter("all");
                  setSearchFilter("");
                }}
                className="text-[11px] font-semibold text-rose-600 hover:underline"
              >
                Reset All Filters
              </button>

              <button
                type="button"
                onClick={() => setIsFiltersOpen(false)}
                className="px-3 py-1 rounded-lg bg-brand-600 text-white text-xs font-semibold hover:bg-brand-700 transition"
              >
                Done
              </button>
            </div>
          </div>
        )}

        {/* 4. Active Filter Chips Row (When Filters are Applied and Drawer is Closed) */}
        {!isFiltersOpen &&
          (searchFilter ||
            selectedGroupFilter ||
            healthFilter !== "all" ||
            severityFilter !== "all") && (
            <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-slate-100">
              <span className="text-[11px] font-medium text-slate-400">
                Active filters:
              </span>
              {searchFilter && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200 text-[11px]">
                  <span>Query: &quot;{searchFilter}&quot;</span>
                  <button
                    type="button"
                    onClick={() => setSearchFilter("")}
                    className="hover:text-blue-900"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
              {selectedGroupFilter && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200 text-[11px]">
                  <span>Group: {selectedGroupFilter}</span>
                  <button
                    type="button"
                    onClick={() => setSelectedGroupFilter("")}
                    className="hover:text-blue-900"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
              {healthFilter !== "all" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px]">
                  <span>Health: {healthFilter}</span>
                  <button
                    type="button"
                    onClick={() => setHealthFilter("all")}
                    className="hover:text-emerald-900"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
              {severityFilter !== "all" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200 text-[11px]">
                  <span>Severity: {severityFilter}</span>
                  <button
                    type="button"
                    onClick={() => setSeverityFilter("all")}
                    className="hover:text-amber-900"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
              <button
                type="button"
                onClick={() => {
                  setSearchFilter("");
                  setSelectedGroupFilter("");
                  setHealthFilter("all");
                  setSeverityFilter("all");
                }}
                className="text-[11px] text-slate-500 hover:text-slate-800 hover:underline ml-1"
              >
                Clear all
              </button>
            </div>
          )}
      </div>

      {/* 4. KPI STRIP (Interactive: click to switch tabs & set filters) */}
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {/* 1. Total Resources -> Resources Tab */}
          <div
            onClick={() => handleSubTabChange("resources")}
            className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs hover:border-blue-400 hover:shadow-xs transition cursor-pointer group"
          >
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Resources & Services</span>
              <Layers className="w-3.5 h-3.5 text-slate-400 group-hover:text-blue-500 transition" />
            </div>
            <div className="text-xl font-extrabold text-slate-900 mt-1">
              {overview.kpis.total_resources}
            </div>
            <div className="text-[10px] text-slate-500 font-medium mt-0.5 truncate">
              {(overview.kpis.api_services_count ?? 0) > 0 ? (
                <span className="text-brand-600 font-semibold">
                  {overview.kpis.infrastructure_resources_count ?? 0} infra · {overview.kpis.api_services_count} APIs
                </span>
              ) : (
                <span className="text-brand-600 font-semibold flex items-center gap-0.5">
                  <span>Inspect all</span> &rarr;
                </span>
              )}
            </div>
          </div>

          {/* 2. Health State -> Health Tab */}
          <div
            onClick={() => {
              if (
                overview.kpis.degraded_count > 0 ||
                overview.kpis.failing_count > 0
              ) {
                setHealthFilter("degraded");
              } else {
                setHealthFilter("all");
              }
              handleSubTabChange("health");
            }}
            className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs hover:border-emerald-400 hover:shadow-xs transition cursor-pointer group"
          >
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Health State</span>
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            </div>
            <div className="text-xl font-extrabold text-emerald-600 mt-1">
              {overview.kpis.healthy_count}{" "}
              <span className="text-xs text-slate-400 font-normal">
                / {overview.kpis.total_resources}
              </span>
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              {overview.kpis.degraded_count > 0 && (
                <span className="text-amber-600 font-semibold">
                  {overview.kpis.degraded_count} degraded &bull;{" "}
                </span>
              )}
              {overview.kpis.failing_count} failing
            </div>
          </div>

          {/* 3. Active Alerts -> Active Alerts Tab */}
          <div
            onClick={() => handleSubTabChange("alerts")}
            className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs hover:border-amber-400 hover:shadow-xs transition cursor-pointer group"
          >
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Active Alerts</span>
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500 group-hover:scale-110 transition" />
            </div>
            <div className="text-xl font-extrabold text-amber-600 mt-1">
              {overview.kpis.active_alerts_count}
            </div>
            <div className="text-[10px] text-amber-700 font-medium mt-0.5 flex items-center gap-0.5">
              <span>View alerts</span> &rarr;
            </div>
          </div>

          {/* 4. Error Rate -> Log Explorer Tab */}
          <div
            onClick={() => {
              setLogSeverity("error");
              handleSubTabChange("logs");
            }}
            className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs hover:border-rose-400 hover:shadow-xs transition cursor-pointer group"
          >
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Error Rate</span>
              <AlertOctagon className="w-3.5 h-3.5 text-rose-500" />
            </div>
            <div className="text-xl font-extrabold text-rose-600 mt-1">
              {overview.kpis.error_rate_percentage ?? "0.00"}%
            </div>
            <div className="text-[10px] text-rose-600 font-medium mt-0.5 flex items-center gap-0.5">
              <span>{overview.kpis.error_event_count} errors</span> &rarr;
            </div>
          </div>

          {/* 5. Telemetry Coverage (Clickable & Keyboard-Accessible Audit Drawer Trigger) */}
          <button
            type="button"
            role="button"
            tabIndex={0}
            aria-haspopup="dialog"
            aria-expanded={isCoverageDrawerOpen}
            onClick={() => setIsCoverageDrawerOpen(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setIsCoverageDrawerOpen(true);
              }
            }}
            className="text-left bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs hover:border-blue-400 hover:shadow-xs transition cursor-pointer group focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:outline-hidden"
          >
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span className="group-hover:text-blue-700 transition font-semibold">Telemetry Cov.</span>
              <Activity className="w-3.5 h-3.5 text-blue-500 group-hover:scale-110 transition-transform" />
            </div>
            <div className="text-xl font-extrabold text-blue-600 mt-1 flex items-baseline gap-1.5">
              <span>{overview.kpis.telemetry_coverage_percentage}%</span>
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5 flex items-center justify-between">
              <span>{overview.kpis.unmonitored_count} unmonitored</span>
              <span className="text-blue-600 opacity-0 group-hover:opacity-100 transition text-[10px] font-semibold flex items-center gap-0.5">
                <span>Audit</span> &rarr;
              </span>
            </div>
          </button>

          {/* 6. Estimated Monthly Cost -> Interactive Financial Drill-Down */}
          <button
            type="button"
            onClick={() => setFinancialDrawerKpi("spend")}
            className="text-left bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs hover:border-slate-400 hover:shadow-xs transition cursor-pointer group focus:outline-none focus:ring-2 focus:ring-brand-500/20"
            title="Click to view detailed spend breakdown and formula"
          >
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Est. Spend</span>
              <span className="text-[10px] text-slate-400 font-mono">USD</span>
            </div>
            <div className="text-xl font-extrabold text-slate-900 mt-1">
              ${canonicalFinancials.estimated_monthly_spend.toFixed(2)}
            </div>
            <div className="text-[10px] text-brand-600 font-semibold mt-0.5 flex items-center justify-between">
              <span>Catalog basis</span>
              <span className="opacity-0 group-hover:opacity-100 transition text-[10px]">
                Drill-down &rarr;
              </span>
            </div>
          </button>

          {/* 7. Waste Savings -> Interactive Financial Drill-Down */}
          <button
            type="button"
            onClick={() => setFinancialDrawerKpi("savings")}
            className="text-left bg-white rounded-xl border border-emerald-200/90 bg-emerald-50/20 p-3 shadow-2xs hover:border-emerald-400 hover:shadow-xs transition cursor-pointer group focus:outline-none focus:ring-2 focus:ring-emerald-500/20"
            title="Click to inspect non-double-counted potential monthly savings"
          >
            <div className="text-[11px] font-medium text-emerald-800 flex items-center justify-between">
              <span>Waste Savings</span>
              <TrendingDown className="w-3.5 h-3.5 text-emerald-600" />
            </div>
            <div className="text-xl font-extrabold text-emerald-700 mt-1">
              ${canonicalFinancials.potential_monthly_savings.toFixed(2)}
              <span className="text-xs font-normal">/mo</span>
            </div>
            <div className="text-[10px] text-emerald-700 font-semibold mt-0.5 flex items-center justify-between">
              <span>Non-double-counted</span>
              <span className="opacity-0 group-hover:opacity-100 transition text-[10px]">
                Drill-down &rarr;
              </span>
            </div>
          </button>

          {/* 8. Technical Debt -> Cost & Waste Tab */}
          <div
            onClick={() => handleSubTabChange("cost_waste")}
            className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs hover:border-indigo-400 hover:shadow-xs transition cursor-pointer group"
          >
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Tech Debt</span>
              <ShieldAlert className="w-3.5 h-3.5 text-indigo-500" />
            </div>
            <div className="text-xl font-extrabold text-indigo-700 mt-1">
              {overview.kpis.technical_debt_items_count}
            </div>
            <div className="text-[10px] text-indigo-600 font-medium mt-0.5 flex items-center gap-0.5">
              <span>Hygiene risks</span> &rarr;
            </div>
          </div>
        </div>
      )}

      {/* 5. SUB-TAB 1: Overview & Metrics Trends */}
      {monitoringSubTab === "overview" && overview && (
        <div className="space-y-6">
          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Compute CPU Utilization Timeseries */}
            <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <Cpu className="w-4 h-4 text-blue-600" />
                    Top Compute CPU Utilization Timeseries
                  </h3>
                  <p className="text-xs text-slate-500">
                    Historical {timeWindow} aggregated telemetry
                  </p>
                </div>
                <span className="text-[11px] font-mono text-slate-400">
                  Interval: {overview.time_window}
                </span>
              </div>
              <div className="space-y-4">
                {overview.cpu_utilization_series.slice(0, 2).map((series, idx) => (
                  <div
                    key={idx}
                    className="p-3 bg-slate-50/70 rounded-xl border border-slate-100"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-slate-800">
                        {series.resource_name}
                      </span>
                      <button
                        type="button"
                        onClick={() => inspectResource(series.resource_id)}
                        className="text-[11px] text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-0.5"
                      >
                        Deep Dive <ArrowRight className="w-3 h-3" />
                      </button>
                    </div>
                    {renderSimpleTimeSeries(
                      series,
                      idx === 0 ? "#2563eb" : "#7c3aed"
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Error Events & Failure Rate Timeline */}
            <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <AlertOctagon className="w-4 h-4 text-rose-600" />
                    Chronological Failure &amp; Error Events Timeline
                  </h3>
                  <p className="text-xs text-slate-500">
                    HTTP 5xx and database timeout spikes
                  </p>
                </div>
                <span className="text-[11px] font-mono text-slate-400">
                  Total: {overview.kpis.error_event_count}
                </span>
              </div>
              {overview.error_rate_series.length > 0 && (
                <div className="p-3 bg-slate-50/70 rounded-xl border border-slate-100">
                  {renderSimpleTimeSeries(overview.error_rate_series[0], "#e11d48")}
                </div>
              )}

              {/* Memory Timeseries if available */}
              {overview.memory_utilization_series.length > 0 && (
                <div className="mt-4 p-3 bg-slate-50/70 rounded-xl border border-slate-100">
                  <div className="text-xs font-semibold text-slate-800 mb-1">
                    {overview.memory_utilization_series[0].resource_name}{" "}
                    (Memory)
                  </div>
                  {renderSimpleTimeSeries(
                    overview.memory_utilization_series[0],
                    "#059669"
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Active Operational Alerts Summary */}
          <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  Active Operational Alerts &amp; Capacity Bottlenecks
                </h3>
                <p className="text-xs text-slate-500">
                  Evidence-backed operational findings evaluated against
                  deterministic thresholds
                </p>
              </div>
              <button
                type="button"
                onClick={() => handleSubTabChange("alerts")}
                className="text-xs px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-semibold hover:bg-amber-100 transition"
              >
                View all {overview.active_alerts.length} findings &rarr;
              </button>
            </div>

            <div className="space-y-3">
              {overview.active_alerts.slice(0, 3).map((alert) => (
                <div
                  key={alert.id}
                  onClick={() => inspectResource(alert.affected_resource_id)}
                  className="p-4 rounded-xl border border-slate-200/80 hover:border-blue-400 hover:shadow-xs transition cursor-pointer bg-white"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                          alert.severity === "critical"
                            ? "bg-rose-100 text-rose-800"
                            : alert.severity === "high"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-blue-100 text-blue-800"
                        }`}
                      >
                        {alert.severity}
                      </span>
                      <h4 className="text-sm font-bold text-slate-900">
                        {alert.title}
                      </h4>
                    </div>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Target: {alert.affected_resource_name}
                    </span>
                  </div>

                  <p className="text-xs text-slate-600 mb-2 leading-relaxed">
                    <strong className="text-slate-800">Evidence:</strong>{" "}
                    {alert.supporting_evidence}
                  </p>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 text-xs">
                    <div className="text-slate-500">
                      <span className="font-semibold text-slate-700">
                        Threshold:
                      </span>{" "}
                      {alert.threshold_rule}
                    </div>
                    <div className="text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-1">
                      Inspect {alert.affected_resource_name} Telemetry{" "}
                      <ArrowRight className="w-3 h-3" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Top Recurring Errors Cluster Table */}
          <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                  <Terminal className="w-4 h-4 text-purple-600" />
                  Top Recurring Errors &amp; Incident Signatures
                </h3>
                <p className="text-xs text-slate-500">
                  Clustered by error signature, HTTP status code, and frequency
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setLogSeverity("error");
                  handleSubTabChange("logs");
                }}
                className="text-xs font-semibold text-blue-600 hover:text-blue-800"
              >
                Open Log Explorer &rarr;
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-semibold bg-slate-50/50">
                    <th className="py-2.5 px-3">Error Signature</th>
                    <th className="py-2.5 px-3">Code</th>
                    <th className="py-2.5 px-3">Frequency</th>
                    <th className="py-2.5 px-3">Affected Services</th>
                    <th className="py-2.5 px-3">Last Seen</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {overview.recurring_errors.map((rec, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/60 transition">
                      <td className="py-2.5 px-3 font-semibold text-slate-900 font-sans">
                        {rec.error_signature}
                      </td>
                      <td className="py-2.5 px-3 text-rose-600 font-bold">
                        {rec.error_code ?? "N/A"}
                      </td>
                      <td className="py-2.5 px-3 text-slate-900 font-bold">
                        {rec.frequency} events
                      </td>
                      <td className="py-2.5 px-3 text-slate-600 font-sans">
                        {rec.affected_resources.join(", ")}
                      </td>
                      <td className="py-2.5 px-3 text-slate-400">
                        {new Date(rec.last_seen).toLocaleTimeString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Limitations & Telemetry Gaps Banner */}
          {overview.limitations_and_gaps.length > 0 && (
            <div className="rounded-2xl bg-amber-50/60 border border-amber-200/80 p-4 text-xs">
              <div className="flex items-center gap-1.5 font-bold text-amber-900 mb-1.5">
                <Info className="w-4 h-4 text-amber-700" />
                <span>
                  Explicit Observability Limitations &amp; Monitoring Gaps
                </span>
              </div>
              <ul className="list-disc list-inside space-y-1 text-amber-800">
                {overview.limitations_and_gaps.map((gap, idx) => (
                  <li key={idx}>{gap}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* 6. SUB-TAB 2: Resources List */}
      {monitoringSubTab === "resources" && overview && (
        <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-brand-600" />
                Discovered Cloud Resources & Services ({filteredHealthRecords.length})
              </h3>
              <p className="text-xs text-slate-500">
                Comprehensive inventory of infrastructure resources, enabled API services, and configurations discovered in the selected scope.
                {(overview.kpis.api_services_count ?? 0) > 0 && (
                  <span className="block mt-1 text-[11px] font-medium text-slate-700 bg-slate-50 px-2.5 py-1 rounded-lg border border-slate-200/60">
                    <strong>Inventory Classification:</strong> {overview.kpis.infrastructure_resources_count ?? 0} provisioned infrastructure (VMs, DBs, Disks) · {overview.kpis.api_services_count} enabled API services · {overview.kpis.configuration_records_count ?? 0} configuration & logging records.
                  </span>
                )}
              </p>
            </div>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-xl">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500 font-semibold bg-slate-50/50">
                  <th className="py-2.5 px-3">Service Name</th>
                  <th className="py-2.5 px-3">Classification</th>
                  <th className="py-2.5 px-3">Native Resource Type</th>
                  <th className="py-2.5 px-3">Health Status</th>
                  <th className="py-2.5 px-3">Telemetry Source</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredHealthRecords.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="py-8 text-center text-slate-400 italic"
                    >
                      No resources match the selected filters.
                    </td>
                  </tr>
                ) : (
                  filteredHealthRecords.map((res) => (
                    <tr
                      key={res.resource_id}
                      className="hover:bg-slate-50/80 transition"
                    >
                      <td className="py-2.5 px-3 font-semibold text-slate-900">
                        {res.resource_name}
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                            res.resource_kind === "api_service"
                              ? "bg-purple-50 text-purple-700 border border-purple-200"
                              : res.resource_kind === "configuration_metadata"
                              ? "bg-slate-100 text-slate-700 border border-slate-200"
                              : res.resource_kind === "security_credential"
                              ? "bg-amber-50 text-amber-700 border border-amber-200"
                              : "bg-blue-50 text-blue-700 border border-blue-200"
                          }`}
                        >
                          {res.resource_kind === "api_service"
                            ? "API Service"
                            : res.resource_kind === "configuration_metadata"
                            ? "Config / Sink"
                            : res.resource_kind === "security_credential"
                            ? "Credential"
                            : "Infrastructure"}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-500 text-[11px]">
                        {res.native_type}
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            res.health_state === "healthy"
                              ? "bg-emerald-100 text-emerald-800"
                              : res.health_state === "degraded"
                              ? "bg-amber-100 text-amber-800"
                              : res.health_state === "stopped"
                              ? "bg-slate-200 text-slate-700"
                              : "bg-rose-100 text-rose-800"
                          }`}
                        >
                          {res.health_state}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-slate-500 text-[11px]">
                        {res.telemetry_source}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          type="button"
                          onClick={() => inspectResource(res.resource_id)}
                          className="px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 font-semibold text-[11px] transition shadow-2xs"
                        >
                          Inspect Telemetry
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 7. SUB-TAB 3: Service Health Breakdown */}
      {monitoringSubTab === "health" && overview && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-4 bg-emerald-50/40 rounded-xl border border-emerald-200">
              <span className="text-xs text-emerald-800 font-medium">
                Healthy Services
              </span>
              <div className="text-2xl font-bold text-emerald-700 mt-1">
                {overview.kpis.healthy_count}
              </div>
            </div>
            <div className="p-4 bg-amber-50/40 rounded-xl border border-amber-200">
              <span className="text-xs text-amber-800 font-medium">
                Degraded Services
              </span>
              <div className="text-2xl font-bold text-amber-700 mt-1">
                {overview.kpis.degraded_count}
              </div>
            </div>
            <div className="p-4 bg-rose-50/40 rounded-xl border border-rose-200">
              <span className="text-xs text-rose-800 font-medium">
                Failing / Outages
              </span>
              <div className="text-2xl font-bold text-rose-700 mt-1">
                {overview.kpis.failing_count}
              </div>
            </div>
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
              <span className="text-xs text-slate-600 font-medium">
                Unmonitored Services
              </span>
              <div className="text-2xl font-bold text-slate-700 mt-1">
                {overview.kpis.unmonitored_count}
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs space-y-3">
            <h3 className="text-sm font-bold text-slate-900">
              Resource Health Diagnoses &amp; Root Causes
            </h3>
            <div className="space-y-3">
              {filteredHealthRecords.map((h) => (
                <div
                  key={h.resource_id}
                  className="p-4 rounded-xl border border-slate-200 bg-slate-50/40 hover:bg-white transition flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          h.health_state === "healthy"
                            ? "bg-emerald-100 text-emerald-800"
                            : h.health_state === "degraded"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {h.health_state}
                      </span>
                      <h4 className="text-xs font-bold text-slate-900">
                        {h.resource_name}
                      </h4>
                      <span className="font-mono text-[11px] text-slate-400">
                        ({h.native_type})
                      </span>
                    </div>
                    <p className="text-xs text-slate-600">{h.summary}</p>
                    {h.reason && (
                      <div className="p-2 rounded bg-amber-50 border border-amber-200 text-amber-800 text-[11px] font-mono">
                        <strong>Root Diagnostic:</strong> {h.reason}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => inspectResource(h.resource_id)}
                    className="px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 font-semibold text-xs transition shadow-2xs shrink-0"
                  >
                    Deep Dive Telemetry
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 8. SUB-TAB 4: Active Alerts */}
      {monitoringSubTab === "alerts" && overview && (
        <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                <BellRing className="w-4 h-4 text-amber-600" />
                Active Operational Alerts ({overview.active_alerts.length})
              </h3>
              <p className="text-xs text-slate-500">
                Deterministic threshold bottlenecks, capacity saturation, and
                service error rate spikes.
              </p>
            </div>
          </div>

          <div className="space-y-3">
            {overview.active_alerts
              .filter(
                (al) =>
                  (severityFilter === "all" || al.severity === severityFilter) &&
                  (!searchFilter ||
                    al.title.toLowerCase().includes(searchFilter.toLowerCase()) ||
                    al.affected_resource_name
                      .toLowerCase()
                      .includes(searchFilter.toLowerCase()))
              )
              .map((al) => (
                <div
                  key={al.id}
                  className="p-4 rounded-xl border border-slate-200 hover:border-blue-400 bg-white transition space-y-2"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          al.severity === "critical"
                            ? "bg-rose-100 text-rose-800"
                            : al.severity === "high"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-blue-100 text-blue-800"
                        }`}
                      >
                        {al.severity}
                      </span>
                      <h4 className="text-sm font-bold text-slate-900">
                        {al.title}
                      </h4>
                    </div>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Target: {al.affected_resource_name} &bull; Scope:{" "}
                      {al.hierarchy_path}
                    </span>
                  </div>

                  <p className="text-xs text-slate-600">
                    <strong className="text-slate-800">Evidence:</strong>{" "}
                    {al.supporting_evidence}
                  </p>
                  <div className="text-xs text-slate-500">
                    <span className="font-semibold text-slate-700">
                      Threshold Rule:
                    </span>{" "}
                    {al.threshold_rule}
                  </div>
                  <div className="p-2.5 rounded-lg bg-blue-50/60 border border-blue-100 text-xs text-blue-900">
                    <strong>Recommendation:</strong> {al.recommendation}
                  </div>

                  <div className="flex items-center justify-end pt-2">
                    <button
                      type="button"
                      onClick={() => inspectResource(al.affected_resource_id)}
                      className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
                    >
                      Inspect {al.affected_resource_name} Telemetry{" "}
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* 9. SUB-TAB 5: Resource Group & Hierarchy Explorer */}
      {monitoringSubTab === "hierarchy" && overview && (
        <div className="space-y-4">
          <div className="text-xs text-slate-500 font-medium">
            Displaying resources grouped by parent scope (Subscription &rarr;
            Resource Group &rarr; Resource)
          </div>

          {overview.resource_groups_summary
            .filter(
              (rg) =>
                !selectedGroupFilter || rg.group_name === selectedGroupFilter
            )
            .map((rg) => {
              const isExpanded = !!expandedGroups[rg.group_name];
              const groupResources = overview.health_records.filter(
                (h) =>
                  (h.resource_id.includes(rg.group_name) ||
                    !overview.health_records.length) &&
                  (healthFilter === "all" || h.health_state === healthFilter) &&
                  (!searchFilter ||
                    h.resource_name
                      .toLowerCase()
                      .includes(searchFilter.toLowerCase()))
              );

              return (
                <div
                  key={rg.group_id}
                  className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden"
                >
                  {/* Group Header Card */}
                  <div
                    onClick={() => toggleGroupExpand(rg.group_name)}
                    className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-slate-50/60 cursor-pointer transition"
                  >
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        className="p-1 rounded hover:bg-slate-200/60 text-slate-500"
                      >
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4" />
                        ) : (
                          <ChevronRight className="w-4 h-4" />
                        )}
                      </button>
                      <div>
                        <div className="flex items-center gap-2">
                          <FolderTree className="w-4 h-4 text-blue-600" />
                          <h4 className="text-sm font-bold text-slate-900">
                            {rg.group_name}
                          </h4>
                          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-mono">
                            {rg.resource_count} resources
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Group Rollup KPIs */}
                    <div className="flex flex-wrap items-center gap-4 text-xs font-mono">
                      <span className="text-slate-600">
                        <strong className="text-emerald-600">
                          {rg.healthy_count}
                        </strong>{" "}
                        healthy
                      </span>
                      {rg.failing_count > 0 && (
                        <span className="text-rose-600 font-bold">
                          {rg.failing_count} degraded/failing
                        </span>
                      )}
                      {rg.active_alerts_count > 0 && (
                        <span className="text-amber-600 font-bold">
                          {rg.active_alerts_count} alerts
                        </span>
                      )}
                      <span className="text-slate-900 font-bold font-sans">
                        ${parseFloat(rg.total_monthly_cost).toFixed(2)}/mo
                      </span>
                      {parseFloat(rg.potential_monthly_savings) > 0 && (
                        <span className="text-emerald-700 font-semibold px-2 py-0.5 rounded bg-emerald-50 border border-emerald-200">
                          -${parseFloat(rg.potential_monthly_savings).toFixed(2)}{" "}
                          waste
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Expanded Resource Table */}
                  {isExpanded && (
                    <div className="border-t border-slate-100 p-4 bg-slate-50/40">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                            <th className="py-2 px-3">Service Name</th>
                            <th className="py-2 px-3">Resource Type</th>
                            <th className="py-2 px-3">Health Status</th>
                            <th className="py-2 px-3">Telemetry Source</th>
                            <th className="py-2 px-3 text-right">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {groupResources.map((res) => (
                            <tr
                              key={res.resource_id}
                              className="hover:bg-white transition"
                            >
                              <td className="py-2.5 px-3 font-semibold text-slate-900">
                                {res.resource_name}
                              </td>
                              <td className="py-2.5 px-3 font-mono text-slate-500 text-[11px]">
                                {res.native_type}
                              </td>
                              <td className="py-2.5 px-3">
                                <span
                                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                    res.health_state === "healthy"
                                      ? "bg-emerald-100 text-emerald-800"
                                      : res.health_state === "degraded"
                                      ? "bg-amber-100 text-amber-800"
                                      : res.health_state === "stopped"
                                      ? "bg-slate-200 text-slate-700"
                                      : "bg-rose-100 text-rose-800"
                                  }`}
                                >
                                  {res.health_state}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 text-slate-500 text-[11px]">
                                {res.telemetry_source}
                              </td>
                              <td className="py-2.5 px-3 text-right">
                                <button
                                  type="button"
                                  onClick={() =>
                                    inspectResource(res.resource_id)
                                  }
                                  className="px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 font-semibold text-[11px] transition shadow-2xs"
                                >
                                  Inspect Telemetry
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      )}

      {/* 10. SUB-TAB 6: Centralized Log Explorer */}
      {monitoringSubTab === "logs" && (
        <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                <Terminal className="w-4 h-4 text-slate-800" />
                Historical Cloud Log Explorer
              </h3>
              <p className="text-xs text-slate-500">
                Search activity logs, HTTP error events, and database
                operational messages with credentials automatically redacted
              </p>
            </div>

            {/* Severity Filter Pills */}
            <div className="flex items-center gap-1.5">
              {["all", "critical", "error", "warning", "informational"].map(
                (sev) => (
                  <button
                    key={sev}
                    type="button"
                    onClick={() => setLogSeverity(sev)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold capitalize transition ${
                      logSeverity === sev
                        ? "bg-slate-900 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {sev}
                  </button>
                )
              )}
            </div>
          </div>

          {/* Search Input Bar */}
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search error messages, operations, correlation IDs (e.g. 504 Gateway Timeout, connection pool)..."
                value={logQuery}
                onChange={(e) => setLogQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && executeLogSearch()}
                className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <button
              type="button"
              disabled={isSearchingLogs}
              onClick={executeLogSearch}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl transition shadow-xs flex items-center gap-1.5"
            >
              {isSearchingLogs && (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              )}
              <span>{isSearchingLogs ? "Searching..." : "Search Logs"}</span>
            </button>
          </div>

          {/* Logs Table */}
          {logResults && (
            <div className="space-y-2">
              <div className="text-xs text-slate-400 font-mono">
                Showing {logResults.logs.length} of {logResults.total_matched}{" "}
                matching audit events
              </div>

              <div className="overflow-x-auto border border-slate-200 rounded-xl">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 font-semibold bg-slate-50/50">
                      <th className="py-2.5 px-3">Timestamp (UTC)</th>
                      <th className="py-2.5 px-3">Severity</th>
                      <th className="py-2.5 px-3">Resource</th>
                      <th className="py-2.5 px-3">Operation</th>
                      <th className="py-2.5 px-3">Code</th>
                      <th className="py-2.5 px-3">Message</th>
                      <th className="py-2.5 px-3">Correlation ID</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                    {logResults.logs.map((l) => (
                      <tr
                        key={l.id}
                        className="hover:bg-slate-50/80 transition"
                      >
                        <td className="py-2.5 px-3 text-slate-500 whitespace-nowrap">
                          {new Date(l.timestamp).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                              l.severity === "error" ||
                              l.severity === "critical"
                                ? "bg-rose-100 text-rose-800"
                                : l.severity === "warning"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-blue-50 text-blue-700"
                            }`}
                          >
                            {l.severity}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-semibold text-slate-900 font-sans">
                          {l.resource_name}
                        </td>
                        <td className="py-2.5 px-3 text-slate-600">
                          {l.operation_name}
                        </td>
                        <td className="py-2.5 px-3 text-rose-600 font-bold">
                          {l.error_code ?? "-"}
                        </td>
                        <td
                          className="py-2.5 px-3 text-slate-700 font-sans max-w-md truncate"
                          title={l.message}
                        >
                          {l.message}
                        </td>
                        <td className="py-2.5 px-3 text-slate-400">
                          {l.correlation_id ?? "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 11. SUB-TAB 7: Token Economics (Dedicated Component) */}
      {monitoringSubTab === "tokens" && (
        <SectionTokenEconomics
          provider={provider}
          scopeId={selectedScopeId}
          scopeName={selectedScopeName}
          timeWindow={timeWindow}
          metricInterval={metricInterval}
        />
      )}

      {/* 12. SUB-TAB 8: Cost Analysis / Waste Findings / Technical Debt */}
      {monitoringSubTab === "cost_waste" && (
        <SectionCostWaste
          provider={provider}
          scopeId={selectedScopeId}
          scopeName={selectedScopeName}
          overview={overview}
          analysisData={analysisData}
          isLoading={isLoadingAnalysis}
          onRefresh={() => fetchAnalysis()}
          onInspectResource={inspectResource}
        />
      )}

      {/* 13. INDIVIDUAL SERVICE DETAIL MODAL (7 Diagnostic Tabs) */}
      {inspectedResourceId && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-5xl rounded-3xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh]">
            {isLoadingDetail || !resourceDetail ? (
              <div className="p-16 flex flex-col items-center justify-center text-slate-500">
                <RefreshCw className="w-8 h-8 animate-spin text-blue-600 mb-3" />
                <p className="text-sm font-semibold text-slate-800">
                  Inspecting Resource Telemetry...
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  Querying performance metrics, log audits, alerts, and FinOps findings
                </p>
                <button
                  type="button"
                  onClick={() => setInspectedResourceId(null)}
                  className="mt-6 px-4 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <>
                {/* Modal Header */}
                <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-blue-500/10 text-blue-600 flex items-center justify-center font-bold">
                      <Activity className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-extrabold text-slate-900">
                          {resourceDetail.resource.resource_name}
                        </h3>
                        <span
                          className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                            resourceDetail.health.health_state === "healthy"
                              ? "bg-emerald-100 text-emerald-800"
                              : resourceDetail.health.health_state === "degraded"
                              ? "bg-amber-100 text-amber-800"
                              : "bg-rose-100 text-rose-800"
                          }`}
                        >
                          {resourceDetail.health.health_state}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 font-mono mt-0.5 truncate max-w-xl">
                        {resourceDetail.resource.resource_id}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setInspectedResourceId(null)}
                    className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* 7-Tab Navigation */}
                <div className="flex items-center border-b border-slate-200 px-6 bg-white overflow-x-auto text-xs font-semibold">
                  {[
                    { id: "overview", label: "Overview & Config" },
                    { id: "metrics", label: "Metrics & Performance" },
                    { id: "logs", label: "Logs & Errors" },
                    { id: "alerts", label: "Alerts & Events" },
                    { id: "dependencies", label: "Dependencies" },
                    { id: "cost", label: "Cost & Utilization" },
                    { id: "debt", label: "Debt & FinOps" },
                  ].map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() =>
                        setResourceActiveTab(
                          t.id as
                            | "overview"
                            | "metrics"
                            | "logs"
                            | "alerts"
                            | "dependencies"
                            | "cost"
                            | "debt"
                        )
                      }
                      className={`py-3 px-3 border-b-2 transition whitespace-nowrap ${
                        resourceActiveTab === t.id
                          ? "border-blue-600 text-blue-600"
                          : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                {/* Tab Body */}
                <div className="p-6 overflow-y-auto space-y-4 flex-1 text-xs">
                  {/* Tab 1: Overview & Config */}
                  {resourceActiveTab === "overview" && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                          <div className="text-slate-400">Native Type</div>
                          <div className="font-mono text-slate-900 mt-1">
                            {resourceDetail.resource.native_resource_type}
                          </div>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                          <div className="text-slate-400">Region</div>
                          <div className="font-semibold text-slate-900 mt-1">
                            {resourceDetail.resource.region}
                          </div>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                          <div className="text-slate-400">
                            SKU / Machine Tier
                          </div>
                          <div className="font-mono text-slate-900 mt-1">
                            {resourceDetail.resource.sku_or_tier ?? "N/A"}
                          </div>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                          <div className="text-slate-400">Monthly Cost Basis</div>
                          <div className="font-bold text-slate-900 mt-1">
                            $
                            {parseFloat(
                              resourceDetail.resource.estimated_monthly_cost.toString()
                            ).toFixed(2)}
                            /mo
                          </div>
                        </div>
                      </div>

                      <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-100 space-y-2">
                        <div className="font-bold text-slate-800">
                          Health Summary
                        </div>
                        <p className="text-slate-600">
                          {resourceDetail.health.summary}
                        </p>
                        {resourceDetail.health.reason && (
                          <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 font-mono text-[11px]">
                            <strong>Root Diagnostic:</strong>{" "}
                            {resourceDetail.health.reason}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Tab 2: Metrics & Performance */}
                  {resourceActiveTab === "metrics" && (
                    <div className="space-y-4">
                      {resourceDetail.metrics.map((series, idx) => (
                        <div
                          key={idx}
                          className="p-4 bg-slate-50/70 rounded-2xl border border-slate-100"
                        >
                          {renderSimpleTimeSeries(
                            series,
                            idx === 0 ? "#2563eb" : "#059669"
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Tab 3: Logs & Errors */}
                  {resourceActiveTab === "logs" && (
                    <div className="space-y-2">
                      <div className="overflow-x-auto border border-slate-200 rounded-xl">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="border-b border-slate-200 bg-slate-50/50 text-slate-500 font-semibold">
                              <th className="py-2 px-3">Timestamp</th>
                              <th className="py-2 px-3">Severity</th>
                              <th className="py-2 px-3">Operation</th>
                              <th className="py-2 px-3">Message</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 font-mono">
                            {resourceDetail.logs.map((l) => (
                              <tr key={l.id} className="hover:bg-slate-50/60">
                                <td className="py-2 px-3 whitespace-nowrap text-slate-400">
                                  {new Date(l.timestamp).toLocaleTimeString()}
                                </td>
                                <td className="py-2 px-3">
                                  <span
                                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                      l.severity === "error"
                                        ? "bg-rose-100 text-rose-800"
                                        : "bg-blue-50 text-blue-700"
                                    }`}
                                  >
                                    {l.severity}
                                  </span>
                                </td>
                                <td className="py-2 px-3 text-slate-700 font-sans">
                                  {l.operation_name}
                                </td>
                                <td
                                  className="py-2 px-3 text-slate-600 font-sans max-w-sm truncate"
                                  title={l.message}
                                >
                                  {l.message}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Tab 4: Alerts & Events */}
                  {resourceActiveTab === "alerts" && (
                    <div className="space-y-3">
                      {resourceDetail.alerts.map((al) => (
                        <div
                          key={al.id}
                          className="p-4 bg-slate-50 rounded-xl border border-slate-200"
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-bold text-slate-900">
                              {al.title}
                            </span>
                            <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-800 font-bold uppercase text-[10px]">
                              {al.severity}
                            </span>
                          </div>
                          <p className="text-slate-600 mb-2">
                            {al.supporting_evidence}
                          </p>
                          <div className="font-semibold text-slate-800">
                            Recommendation:
                          </div>
                          <p className="text-slate-600">{al.recommendation}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Tab 5: Dependencies & Architecture */}
                  {resourceActiveTab === "dependencies" && (
                    <div className="space-y-3">
                      <div className="text-slate-500 font-medium">
                        Inbound and Outbound Topological Connections
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {resourceDetail.dependencies.map((dep, idx) => (
                          <div
                            key={idx}
                            className="p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-center justify-between"
                          >
                            <div>
                              <div className="font-bold text-slate-900">
                                {dep.target_name}
                              </div>
                              <div className="text-[11px] text-slate-500 font-mono">
                                {dep.relation}
                              </div>
                            </div>
                            <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-semibold text-[10px]">
                              {dep.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Tab 6: Cost & Utilization */}
                  {resourceActiveTab === "cost" && (
                    <div className="space-y-3">
                      <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-slate-400">
                            Monthly Sizing Basis
                          </div>
                          <div className="text-base font-bold text-slate-900 mt-1">
                            $
                            {String(
                              resourceDetail.cost_and_utilization
                                ?.monthly_cost ?? "0.00"
                            )}
                            /month
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-400">
                            CPU Utilization Mean
                          </div>
                          <div className="text-base font-bold text-blue-600 mt-1">
                            {String(
                              resourceDetail.cost_and_utilization
                                .utilization_summary
                            )}
                            %
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Tab 7: Technical Debt & Recommendations */}
                  {resourceActiveTab === "debt" && (
                    <div className="space-y-3">
                      {resourceDetail.waste_findings.length === 0 &&
                      resourceDetail.technical_debt_items.length === 0 ? (
                        <div className="p-6 text-center text-slate-400 italic">
                          Zero technical debt or waste detected on this
                          resource.
                        </div>
                      ) : (
                        <>
                          {resourceDetail.waste_findings.map((wf) => (
                            <div
                              key={wf.id}
                              className="p-3.5 bg-emerald-50/50 rounded-xl border border-emerald-200"
                            >
                              <div className="flex items-center justify-between mb-1">
                                <span className="font-bold text-emerald-900">
                                  {wf.title}
                                </span>
                                <span className="font-bold text-emerald-700">
                                  +$
                                  {parseFloat(
                                    wf.potential_monthly_savings.toString()
                                  ).toFixed(2)}
                                  /mo savings
                                </span>
                              </div>
                              <p className="text-emerald-800 text-[11px]">
                                {wf.description}
                              </p>
                            </div>
                          ))}

                          {resourceDetail.technical_debt_items.map((td) => (
                            <div
                              key={td.id}
                              className="p-3.5 bg-indigo-50/50 rounded-xl border border-indigo-200"
                            >
                              <div className="flex items-center justify-between mb-1">
                                <span className="font-bold text-indigo-900">
                                  {td.title}
                                </span>
                                <span className="font-bold text-indigo-700 uppercase text-[10px]">
                                  {td.severity}
                                </span>
                              </div>
                              <p className="text-indigo-800 text-[11px]">
                                {td.description}
                              </p>
                            </div>
                          ))}
                        </>
                      )}
                    </div>
                  )}
                </div>

                {/* Modal Footer */}
                <div className="p-4 border-t border-slate-100 bg-slate-50 flex items-center justify-end">
                  <button
                    type="button"
                    onClick={() => setInspectedResourceId(null)}
                    className="px-4 py-2 rounded-xl bg-slate-900 text-white font-semibold text-xs hover:bg-slate-800 transition"
                  >
                    Close Deep Dive
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
      {/* 13. Telemetry Coverage Audit Drawer */}
      <TelemetryCoverageDrawer
        isOpen={isCoverageDrawerOpen}
        onClose={() => setIsCoverageDrawerOpen(false)}
        overview={overview}
        provider={provider}
        scopeId={selectedScopeId}
        scopeName={selectedScopeName}
      />

      {/* 14. Canonical Financial KPI Drill-Down Drawer */}
      {financialDrawerKpi && (
        <FinancialKpiDrawer
          isOpen={Boolean(financialDrawerKpi)}
          onClose={() => setFinancialDrawerKpi(null)}
          kpiType={financialDrawerKpi}
          financials={canonicalFinancials}
          onInspectResource={(resId) => {
            setFinancialDrawerKpi(null);
            inspectResource(resId);
          }}
        />
      )}
    </section>
  );
}
