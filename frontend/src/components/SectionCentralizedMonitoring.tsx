"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  CloudProvider,
  CloudScopeSummary,
  TimeWindowPreset,
  MetricInterval,
  MonitoringOverviewResponse,
  ResourceDetailMonitoringResponse,
  LogSearchResponse,
  LogSeverity,
  MetricTimeSeries,
} from "@/types";
import {
  listAzureSubscriptions,
  listGcpProjects,
  getMonitoringOverview,
  getResourceMonitoringDetail,
  searchMonitoringLogs,
} from "@/lib/api";
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
  Filter,
  BarChart3,
  Terminal,
  SlidersHorizontal,
  ArrowRight,
} from "lucide-react";

export function SectionCentralizedMonitoring() {
  // Provider and Scope Selection
  const [provider, setProvider] = useState<CloudProvider>("azure");
  const [scopes, setScopes] = useState<CloudScopeSummary[]>([]);
  const [selectedScopeId, setSelectedScopeId] = useState<string>("");
  const [selectedScopeName, setSelectedScopeName] = useState<string>("");

  // Time Window & Metric Interval Controls
  const [timeWindow, setTimeWindow] = useState<TimeWindowPreset>("7d");
  const [metricInterval, setMetricInterval] = useState<MetricInterval>("1h");
  const [customStart, setCustomStart] = useState<string>("");
  const [customEnd, setCustomEnd] = useState<string>("");

  // Filters
  const [selectedGroupFilter, setSelectedGroupFilter] = useState<string>("");
  const [healthFilter, setHealthFilter] = useState<string>("all");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [searchFilter, setSearchFilter] = useState<string>("");

  // Sub-Navigation Tabs within Monitoring Module
  const [monitoringSubTab, setMonitoringSubTab] = useState<"overview" | "hierarchy" | "logs">("overview");

  // Telemetry & Overview State
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [overview, setOverview] = useState<MonitoringOverviewResponse | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  // Single Resource Deep Dive Modal / Drawer State (7 Diagnostic Tabs)
  const [inspectedResourceId, setInspectedResourceId] = useState<string | null>(null);
  const [resourceDetail, setResourceDetail] = useState<ResourceDetailMonitoringResponse | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);
  const [resourceActiveTab, setResourceActiveTab] = useState<
    "overview" | "metrics" | "logs" | "alerts" | "dependencies" | "cost" | "debt"
  >("overview");

  // Log Explorer Search State
  const [logQuery, setLogQuery] = useState<string>("");
  const [logSeverity, setLogSeverity] = useState<string>("all");
  const [logResults, setLogResults] = useState<LogSearchResponse | null>(null);
  const [isSearchingLogs, setIsSearchingLogs] = useState<boolean>(false);

  // 1. Load Available Scopes
  const loadScopes = useCallback(async (targetProvider: CloudProvider) => {
    setErrorMsg(null);
    try {
      if (targetProvider === "azure") {
        const azSubs = await listAzureSubscriptions();
        setScopes(azSubs);
        if (azSubs.length > 0) {
          setSelectedScopeId(azSubs[0].scope_id);
          setSelectedScopeName(azSubs[0].display_name);
        }
      } else {
        const gcpProjs = await listGcpProjects();
        setScopes(gcpProjs);
        if (gcpProjs.length > 0) {
          setSelectedScopeId(gcpProjs[0].scope_id);
          setSelectedScopeName(gcpProjs[0].display_name);
        }
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load cloud scopes.");
    }
  }, []);

  useEffect(() => {
    loadScopes(provider);
  }, [provider, loadScopes]);

  // 2. Fetch Monitoring Overview
  const fetchOverview = useCallback(
    async (forceRefresh = false) => {
      if (!selectedScopeId) return;
      if (forceRefresh) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }
      setErrorMsg(null);
      try {
        const data = await getMonitoringOverview({
          provider,
          scope_id: selectedScopeId,
          resource_group_filter: selectedGroupFilter || undefined,
          time_window: timeWindow,
          custom_start_time: timeWindow === "custom" && customStart ? customStart : undefined,
          custom_end_time: timeWindow === "custom" && customEnd ? customEnd : undefined,
          interval: metricInterval,
          force_refresh: forceRefresh,
        });
        setOverview(data);
      } catch (err: unknown) {
        setErrorMsg(err instanceof Error ? err.message : "Failed to load monitoring overview.");
      } finally {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    },
    [provider, selectedScopeId, selectedGroupFilter, timeWindow, customStart, customEnd, metricInterval]
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
        severity: logSeverity !== "all" ? (logSeverity as LogSeverity) : undefined,
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

  const toggleGroupExpand = (grpName: string) => {
    setExpandedGroups((prev) => ({ ...prev, [grpName]: !prev[grpName] }));
  };

  // Render SVG Timeseries Chart
  const renderSimpleTimeSeries = (series: MetricTimeSeries, strokeColor = "#3b82f6") => {
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
        const x = padding + (idx / Math.max(points.length - 1, 1)) * (width - 2 * padding);
        const y = height - padding - ((p.value - minVal) / range) * (height - 2 * padding);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

    const areaPoints = `${padding},${height - padding} ${svgPoints} ${width - padding},${height - padding}`;

    return (
      <div className="w-full">
        <div className="flex items-center justify-between text-xs mb-1.5">
          <span className="font-semibold text-slate-800">{series.display_name}</span>
          <span className="font-mono text-slate-500">
            Avg: {series.summary.avg ?? "N/A"}% &bull; Peak: {series.summary.max ?? "N/A"}% &bull; Current:{" "}
            {series.summary.current ?? "N/A"}%
          </span>
        </div>
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-28 overflow-visible">
          <defs>
            <linearGradient id={`grad-${series.metric_name}-${series.resource_name}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.25" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
            </linearGradient>
          </defs>
          <polyline fill={`url(#grad-${series.metric_name}-${series.resource_name})`} points={areaPoints} />
          <polyline fill="none" stroke={strokeColor} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" points={svgPoints} />
          {points.map((p, idx) => {
            const x = padding + (idx / Math.max(points.length - 1, 1)) * (width - 2 * padding);
            const y = height - padding - ((p.value - minVal) / range) * (height - 2 * padding);
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
                <title>{`${new Date(p.timestamp).toLocaleTimeString()}: ${p.value}${series.unit === "Percent" ? "%" : ""}`}</title>
              </circle>
            );
          })}
        </svg>
      </div>
    );
  };

  return (
    <section id="section-monitoring" className="space-y-6">
      {errorMsg && (
        <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-xl flex items-center justify-between">
          <span>{errorMsg}</span>
          <button type="button" onClick={() => setErrorMsg(null)} className="text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* 1. Header & Controls Bar */}
      <div className="rounded-2xl bg-white border border-slate-200/90 p-5 shadow-xs">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 text-xs font-semibold">
                <Activity className="w-3.5 h-3.5 text-blue-600 animate-pulse" />
                Live Observability &amp; FinOps Intelligence
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-medium">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                Zero-Execution Policy &bull; Read-Only
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
                onClick={() => setProvider("azure")}
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
                onClick={() => setProvider("gcp")}
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
              className="text-xs bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
            >
              {scopes.map((s) => (
                <option key={s.scope_id} value={s.scope_id}>
                  {s.display_name} ({s.scope_id.substring(0, 18)}...)
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
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
              <span>{isRefreshing ? "Querying..." : "Refresh Telemetry"}</span>
            </button>
          </div>
        </div>

        {/* Time-Window & Granularity Filter Strip */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 text-xs">
          {/* Time Windows */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-slate-500 font-medium mr-1 flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-slate-400" />
              Time Window:
            </span>
            {(["1h", "24h", "7d", "30d", "90d", "custom"] as TimeWindowPreset[]).map((w) => (
              <button
                key={w}
                type="button"
                onClick={() => setTimeWindow(w)}
                className={`px-2.5 py-1 rounded-lg font-medium transition ${
                  timeWindow === w
                    ? "bg-blue-600 text-white shadow-2xs"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {w === "1h"
                  ? "Last Hour"
                  : w === "24h"
                    ? "24 Hours"
                    : w === "7d"
                      ? "7 Days"
                      : w === "30d"
                        ? "30 Days"
                        : w === "90d"
                          ? "90 Days"
                          : "Custom"}
              </button>
            ))}
            {timeWindow === "custom" && (
              <div className="flex items-center gap-1.5 ml-2">
                <input
                  type="datetime-local"
                  value={customStart}
                  onChange={(e) => setCustomStart(e.target.value)}
                  className="px-2 py-0.5 border border-slate-200 rounded-md text-[11px]"
                />
                <span className="text-slate-400">to</span>
                <input
                  type="datetime-local"
                  value={customEnd}
                  onChange={(e) => setCustomEnd(e.target.value)}
                  className="px-2 py-0.5 border border-slate-200 rounded-md text-[11px]"
                />
              </div>
            )}
          </div>

          {/* Metric Aggregation Interval */}
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500 font-medium mr-1 flex items-center gap-1">
              <SlidersHorizontal className="w-3.5 h-3.5 text-slate-400" />
              Interval:
            </span>
            {(["1m", "5m", "15m", "1h", "1d"] as MetricInterval[]).map((int) => (
              <button
                key={int}
                type="button"
                onClick={() => setMetricInterval(int)}
                className={`px-2 py-0.5 rounded-md font-mono text-[11px] transition ${
                  metricInterval === int
                    ? "bg-slate-800 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {int}
              </button>
            ))}
          </div>

          {/* Data Provenance Badge */}
          {overview && (
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
                  overview.is_live
                    ? "bg-emerald-50 text-emerald-700 border-emerald-300"
                    : "bg-amber-50 text-amber-700 border-amber-300"
                }`}
              >
                {overview.is_live ? (
                  <>
                    <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                    Live Authenticated API
                  </>
                ) : (
                  <>
                    <Info className="w-3 h-3 text-amber-600" />
                    Verified Benchmark Simulation
                  </>
                )}
              </span>
              <span className="text-[11px] text-slate-400 font-mono">
                Updated {new Date(overview.query_timestamp).toLocaleTimeString()}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* 2. KPI Strip */}
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {/* Total Resources */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs">
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Resources</span>
              <Layers className="w-3.5 h-3.5 text-slate-400" />
            </div>
            <div className="text-xl font-extrabold text-slate-900 mt-1">{overview.kpis.total_resources}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">Discovered in scope</div>
          </div>

          {/* Health Distribution */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs">
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Health State</span>
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            </div>
            <div className="text-xl font-extrabold text-emerald-600 mt-1">
              {overview.kpis.healthy_count} <span className="text-xs text-slate-400 font-normal">/ {overview.kpis.total_resources}</span>
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              {overview.kpis.degraded_count > 0 && (
                <span className="text-amber-600 font-semibold">{overview.kpis.degraded_count} degraded &bull; </span>
              )}
              {overview.kpis.failing_count} failing
            </div>
          </div>

          {/* Active Alerts */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs">
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Active Alerts</span>
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
            </div>
            <div className="text-xl font-extrabold text-amber-600 mt-1">{overview.kpis.active_alerts_count}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">Threshold bottlenecks</div>
          </div>

          {/* Error Rate */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs">
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Error Rate</span>
              <AlertOctagon className="w-3.5 h-3.5 text-rose-500" />
            </div>
            <div className="text-xl font-extrabold text-rose-600 mt-1">
              {overview.kpis.error_rate_percentage ?? "0.00"}%
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">{overview.kpis.error_event_count} failed operations</div>
          </div>

          {/* Telemetry Coverage */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs">
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Telemetry Cov.</span>
              <Activity className="w-3.5 h-3.5 text-blue-500" />
            </div>
            <div className="text-xl font-extrabold text-blue-600 mt-1">
              {overview.kpis.telemetry_coverage_percentage}%
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              {overview.kpis.unmonitored_count} unmonitored services
            </div>
          </div>

          {/* Estimated Monthly Cost */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs">
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Est. Spend</span>
              <span className="text-[10px] text-slate-400 font-mono">USD</span>
            </div>
            <div className="text-xl font-extrabold text-slate-900 mt-1">
              ${parseFloat(overview.kpis.estimated_monthly_cost).toFixed(0)}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">Catalog monthly basis</div>
          </div>

          {/* FinOps Potential Savings */}
          <div className="bg-white rounded-xl border border-emerald-200/90 bg-emerald-50/20 p-3 shadow-2xs">
            <div className="text-[11px] font-medium text-emerald-800 flex items-center justify-between">
              <span>Waste Savings</span>
              <TrendingDown className="w-3.5 h-3.5 text-emerald-600" />
            </div>
            <div className="text-xl font-extrabold text-emerald-700 mt-1">
              ${parseFloat(overview.kpis.potential_monthly_savings).toFixed(0)}
              <span className="text-xs font-normal">/mo</span>
            </div>
            <div className="text-[10px] text-emerald-600 mt-0.5 font-medium">Non-double-counted</div>
          </div>

          {/* Technical Debt Items */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-3 shadow-2xs">
            <div className="text-[11px] font-medium text-slate-500 flex items-center justify-between">
              <span>Tech Debt</span>
              <ShieldAlert className="w-3.5 h-3.5 text-indigo-500" />
            </div>
            <div className="text-xl font-extrabold text-indigo-700 mt-1">
              {overview.kpis.technical_debt_items_count}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">Hygiene &amp; resilience risks</div>
          </div>
        </div>
      )}

      {/* 3. Sub-View Mode Navigation */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setMonitoringSubTab("overview")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
              monitoringSubTab === "overview"
                ? "bg-slate-900 text-white shadow-xs"
                : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200/80"
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Overview &amp; Metrics Trends</span>
          </button>

          <button
            type="button"
            onClick={() => setMonitoringSubTab("hierarchy")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
              monitoringSubTab === "hierarchy"
                ? "bg-slate-900 text-white shadow-xs"
                : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200/80"
            }`}
          >
            <FolderTree className="w-4 h-4" />
            <span>Resource Group &amp; Hierarchy Explorer</span>
          </button>

          <button
            type="button"
            onClick={() => setMonitoringSubTab("logs")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
              monitoringSubTab === "logs"
                ? "bg-slate-900 text-white shadow-xs"
                : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200/80"
            }`}
          >
            <Terminal className="w-4 h-4" />
            <span>Centralized Log Explorer</span>
          </button>
        </div>

        {/* Global Filter Bar */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 text-slate-400 text-xs font-medium mr-0.5">
            <Filter className="w-3.5 h-3.5" />
            <span>Filters:</span>
          </div>
          {overview && overview.resource_groups_summary.length > 0 && (
            <select
              value={selectedGroupFilter}
              onChange={(e) => setSelectedGroupFilter(e.target.value)}
              className="text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded-xl font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Groups</option>
              {overview.resource_groups_summary.map((rg) => (
                <option key={rg.group_name} value={rg.group_name}>
                  {rg.group_name}
                </option>
              ))}
            </select>
          )}

          <select
            value={healthFilter}
            onChange={(e) => setHealthFilter(e.target.value)}
            className="text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded-xl font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Health</option>
            <option value="healthy">Healthy</option>
            <option value="degraded">Degraded</option>
            <option value="failing">Failing</option>
            <option value="stopped">Stopped</option>
          </select>

          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded-xl font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Filter services by name..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="text-xs pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-blue-500 w-44"
            />
          </div>
        </div>
      </div>

      {/* 4. Tab 1: Overview & Timeseries Trends */}
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
                  <p className="text-xs text-slate-500">Historical {timeWindow} aggregated telemetry</p>
                </div>
                <span className="text-[11px] font-mono text-slate-400">Interval: {overview.time_window}</span>
              </div>
              <div className="space-y-4">
                {overview.cpu_utilization_series.slice(0, 2).map((series, idx) => (
                  <div key={idx} className="p-3 bg-slate-50/70 rounded-xl border border-slate-100">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-slate-800">{series.resource_name}</span>
                      <button
                        type="button"
                        onClick={() => inspectResource(series.resource_id)}
                        className="text-[11px] text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-0.5"
                      >
                        Deep Dive <ArrowRight className="w-3 h-3" />
                      </button>
                    </div>
                    {renderSimpleTimeSeries(series, idx === 0 ? "#2563eb" : "#7c3aed")}
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
                  <p className="text-xs text-slate-500">HTTP 5xx and database timeout spikes</p>
                </div>
                <span className="text-[11px] font-mono text-slate-400">Total: {overview.kpis.error_event_count}</span>
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
                    {overview.memory_utilization_series[0].resource_name} (Memory)
                  </div>
                  {renderSimpleTimeSeries(overview.memory_utilization_series[0], "#059669")}
                </div>
              )}
            </div>
          </div>

          {/* Operational Alerts & Capacity Nudges */}
          <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  Active Operational Alerts &amp; Capacity Bottlenecks
                </h3>
                <p className="text-xs text-slate-500">
                  Evidence-backed operational findings evaluated against deterministic thresholds
                </p>
              </div>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-semibold">
                {overview.active_alerts.length} Active Findings
              </span>
            </div>

            <div className="space-y-3">
              {overview.active_alerts
                .filter(
                  (alert) =>
                    (severityFilter === "all" || alert.severity === severityFilter) &&
                    (!searchFilter ||
                      alert.affected_resource_name.toLowerCase().includes(searchFilter.toLowerCase()) ||
                      alert.title.toLowerCase().includes(searchFilter.toLowerCase()))
                )
                .map((alert) => (
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
                      <h4 className="text-sm font-bold text-slate-900">{alert.title}</h4>
                    </div>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Target: {alert.affected_resource_name} &bull; Scope: {alert.hierarchy_path}
                    </span>
                  </div>

                  <p className="text-xs text-slate-600 mb-2 leading-relaxed">
                    <strong className="text-slate-800">Evidence:</strong> {alert.supporting_evidence}
                  </p>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 text-xs">
                    <div className="text-slate-500">
                      <span className="font-semibold text-slate-700">Threshold:</span> {alert.threshold_rule}
                    </div>
                    <div className="text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-1">
                      Inspect {alert.affected_resource_name} Telemetry <ArrowRight className="w-3 h-3" />
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
                <p className="text-xs text-slate-500">Clustered by error signature, HTTP status code, and frequency</p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-semibold bg-slate-50/50">
                    <th className="py-2.5 px-3">Error Signature</th>
                    <th className="py-2.5 px-3">Code</th>
                    <th className="py-2.5 px-3">Frequency</th>
                    <th className="py-2.5 px-3">Affected Services</th>
                    <th className="py-2.5 px-3">First Seen</th>
                    <th className="py-2.5 px-3">Last Seen</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {overview.recurring_errors.map((rec, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/60 transition">
                      <td className="py-2.5 px-3 font-semibold text-slate-900 font-sans">{rec.error_signature}</td>
                      <td className="py-2.5 px-3 text-rose-600 font-bold">{rec.error_code ?? "N/A"}</td>
                      <td className="py-2.5 px-3 text-slate-900 font-bold">{rec.frequency} events</td>
                      <td className="py-2.5 px-3 text-slate-600 font-sans">{rec.affected_resources.join(", ")}</td>
                      <td className="py-2.5 px-3 text-slate-400">{new Date(rec.first_seen).toLocaleDateString()}</td>
                      <td className="py-2.5 px-3 text-slate-400">{new Date(rec.last_seen).toLocaleTimeString()}</td>
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
                <span>Explicit Observability Limitations &amp; Monitoring Gaps</span>
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

      {/* 5. Tab 2: Resource Group & Hierarchy Explorer */}
      {monitoringSubTab === "hierarchy" && overview && (
        <div className="space-y-4">
          <div className="text-xs text-slate-500 font-medium">
            Displaying resources grouped by parent scope (Subscription &rarr; Resource Group &rarr; Resource)
          </div>

          {overview.resource_groups_summary
            .filter((rg) => !selectedGroupFilter || rg.group_name === selectedGroupFilter)
            .map((rg) => {
              const isExpanded = !!expandedGroups[rg.group_name];
              const groupResources = overview.health_records.filter(
                (h) =>
                  (h.resource_id.includes(rg.group_name) || !overview.health_records.length) &&
                  (healthFilter === "all" || h.health_state === healthFilter) &&
                  (!searchFilter || h.resource_name.toLowerCase().includes(searchFilter.toLowerCase()))
              );

            return (
              <div key={rg.group_id} className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden">
                {/* Group Header Card */}
                <div
                  onClick={() => toggleGroupExpand(rg.group_name)}
                  className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-slate-50/60 cursor-pointer transition"
                >
                  <div className="flex items-center gap-3">
                    <button type="button" className="p-1 rounded hover:bg-slate-200/60 text-slate-500">
                      {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </button>
                    <div>
                      <div className="flex items-center gap-2">
                        <FolderTree className="w-4 h-4 text-blue-600" />
                        <h4 className="text-sm font-bold text-slate-900">{rg.group_name}</h4>
                        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-mono">
                          {rg.resource_count} resources
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Group Rollup KPIs */}
                  <div className="flex flex-wrap items-center gap-4 text-xs font-mono">
                    <span className="text-slate-600">
                      <strong className="text-emerald-600">{rg.healthy_count}</strong> healthy
                    </span>
                    {rg.failing_count > 0 && (
                      <span className="text-rose-600 font-bold">{rg.failing_count} degraded/failing</span>
                    )}
                    {rg.active_alerts_count > 0 && (
                      <span className="text-amber-600 font-bold">{rg.active_alerts_count} alerts</span>
                    )}
                    <span className="text-slate-900 font-bold font-sans">
                      ${parseFloat(rg.total_monthly_cost).toFixed(2)}/mo
                    </span>
                    {parseFloat(rg.potential_monthly_savings) > 0 && (
                      <span className="text-emerald-700 font-semibold px-2 py-0.5 rounded bg-emerald-50 border border-emerald-200">
                        -${parseFloat(rg.potential_monthly_savings).toFixed(2)} waste
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
                          <tr key={res.resource_id} className="hover:bg-white transition">
                            <td className="py-2.5 px-3 font-semibold text-slate-900">{res.resource_name}</td>
                            <td className="py-2.5 px-3 font-mono text-slate-500 text-[11px]">{res.native_type}</td>
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
                            <td className="py-2.5 px-3 text-slate-500 text-[11px]">{res.telemetry_source}</td>
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

      {/* 6. Tab 3: Centralized Log Explorer */}
      {monitoringSubTab === "logs" && (
        <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                <Terminal className="w-4 h-4 text-slate-800" />
                Historical Cloud Log Explorer
              </h3>
              <p className="text-xs text-slate-500">
                Search activity logs, HTTP error events, and database operational messages with credentials automatically redacted
              </p>
            </div>

            {/* Severity Filter Pills */}
            <div className="flex items-center gap-1.5">
              {["all", "critical", "error", "warning", "informational"].map((sev) => (
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
              ))}
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
              {isSearchingLogs && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
              <span>{isSearchingLogs ? "Searching..." : "Search Logs"}</span>
            </button>
          </div>

          {/* Logs Table */}
          {logResults && (
            <div className="space-y-2">
              <div className="text-xs text-slate-400 font-mono">
                Showing {logResults.logs.length} of {logResults.total_matched} matching audit events
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
                      <tr key={l.id} className="hover:bg-slate-50/80 transition">
                        <td className="py-2.5 px-3 text-slate-500 whitespace-nowrap">
                          {new Date(l.timestamp).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                              l.severity === "error" || l.severity === "critical"
                                ? "bg-rose-100 text-rose-800"
                                : l.severity === "warning"
                                  ? "bg-amber-100 text-amber-800"
                                  : "bg-blue-50 text-blue-700"
                            }`}
                          >
                            {l.severity}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-semibold text-slate-900 font-sans">{l.resource_name}</td>
                        <td className="py-2.5 px-3 text-slate-600">{l.operation_name}</td>
                        <td className="py-2.5 px-3 text-rose-600 font-bold">{l.error_code ?? "-"}</td>
                        <td className="py-2.5 px-3 text-slate-700 font-sans max-w-md truncate" title={l.message}>
                          {l.message}
                        </td>
                        <td className="py-2.5 px-3 text-slate-400">{l.correlation_id ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 7. Individual Service Detail Modal (7 Diagnostic Tabs) */}
      {inspectedResourceId && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-5xl rounded-3xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh]">
            {isLoadingDetail || !resourceDetail ? (
              <div className="p-16 flex flex-col items-center justify-center text-slate-500">
                <RefreshCw className="w-8 h-8 animate-spin text-blue-600 mb-3" />
                <p className="text-sm font-semibold text-slate-800">Inspecting Resource Telemetry...</p>
                <p className="text-xs text-slate-400 mt-1">Querying performance metrics, log audits, alerts, and FinOps findings</p>
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
                        <h3 className="text-lg font-extrabold text-slate-900">{resourceDetail.resource.resource_name}</h3>
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
                          t.id as "overview" | "metrics" | "logs" | "alerts" | "dependencies" | "cost" | "debt"
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
                      <div className="font-mono text-slate-900 mt-1">{resourceDetail.resource.native_resource_type}</div>
                    </div>
                    <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                      <div className="text-slate-400">Region</div>
                      <div className="font-semibold text-slate-900 mt-1">{resourceDetail.resource.region}</div>
                    </div>
                    <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                      <div className="text-slate-400">SKU / Machine Tier</div>
                      <div className="font-mono text-slate-900 mt-1">{resourceDetail.resource.sku_or_tier ?? "N/A"}</div>
                    </div>
                    <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                      <div className="text-slate-400">Monthly Cost Basis</div>
                      <div className="font-bold text-slate-900 mt-1">
                        ${parseFloat(resourceDetail.resource.estimated_monthly_cost.toString()).toFixed(2)}/mo
                      </div>
                    </div>
                  </div>

                  <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-100 space-y-2">
                    <div className="font-bold text-slate-800">Health Summary</div>
                    <p className="text-slate-600">{resourceDetail.health.summary}</p>
                    {resourceDetail.health.reason && (
                      <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 font-mono text-[11px]">
                        <strong>Root Diagnostic:</strong> {resourceDetail.health.reason}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Tab 2: Metrics & Performance */}
              {resourceActiveTab === "metrics" && (
                <div className="space-y-4">
                  {resourceDetail.metrics.map((series, idx) => (
                    <div key={idx} className="p-4 bg-slate-50/70 rounded-2xl border border-slate-100">
                      {renderSimpleTimeSeries(series, idx === 0 ? "#2563eb" : "#059669")}
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
                                  l.severity === "error" ? "bg-rose-100 text-rose-800" : "bg-blue-50 text-blue-700"
                                }`}
                              >
                                {l.severity}
                              </span>
                            </td>
                            <td className="py-2 px-3 text-slate-700 font-sans">{l.operation_name}</td>
                            <td className="py-2 px-3 text-slate-600 font-sans max-w-sm truncate" title={l.message}>
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
                    <div key={al.id} className="p-4 bg-slate-50 rounded-xl border border-slate-200">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold text-slate-900">{al.title}</span>
                        <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-800 font-bold uppercase text-[10px]">
                          {al.severity}
                        </span>
                      </div>
                      <p className="text-slate-600 mb-2">{al.supporting_evidence}</p>
                      <div className="font-semibold text-slate-800">Recommendation:</div>
                      <p className="text-slate-600">{al.recommendation}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Tab 5: Dependencies & Architecture */}
              {resourceActiveTab === "dependencies" && (
                <div className="space-y-3">
                  <div className="text-slate-500 font-medium">Inbound and Outbound Topological Connections</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {resourceDetail.dependencies.map((dep, idx) => (
                      <div key={idx} className="p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-center justify-between">
                        <div>
                          <div className="font-bold text-slate-900">{dep.target_name}</div>
                          <div className="text-[11px] text-slate-500 font-mono">{dep.relation}</div>
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
                      <div className="text-slate-400">Monthly Sizing Basis</div>
                      <div className="text-base font-bold text-slate-900 mt-1">
                        ${String(resourceDetail.cost_and_utilization?.monthly_cost ?? "0.00")}/month
                      </div>
                    </div>
                    <div>
                      <div className="text-slate-400">CPU Utilization Mean</div>
                      <div className="text-base font-bold text-blue-600 mt-1">
                        {String(resourceDetail.cost_and_utilization.utilization_summary)}%
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 7: Technical Debt & Recommendations */}
              {resourceActiveTab === "debt" && (
                <div className="space-y-3">
                  {resourceDetail.waste_findings.length === 0 && resourceDetail.technical_debt_items.length === 0 ? (
                    <div className="p-6 text-center text-slate-400 italic">
                      Zero technical debt or waste detected on this resource.
                    </div>
                  ) : (
                    <>
                      {resourceDetail.waste_findings.map((wf) => (
                        <div key={wf.id} className="p-3.5 bg-emerald-50/50 rounded-xl border border-emerald-200">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-bold text-emerald-900">{wf.title}</span>
                            <span className="font-bold text-emerald-700">
                              +${parseFloat(wf.potential_monthly_savings.toString()).toFixed(2)}/mo savings
                            </span>
                          </div>
                          <p className="text-emerald-800 text-[11px]">{wf.description}</p>
                        </div>
                      ))}

                      {resourceDetail.technical_debt_items.map((td) => (
                        <div key={td.id} className="p-3.5 bg-indigo-50/50 rounded-xl border border-indigo-200">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-bold text-indigo-900">{td.title}</span>
                            <span className="font-bold text-indigo-700 uppercase text-[10px]">{td.severity}</span>
                          </div>
                          <p className="text-indigo-800 text-[11px]">{td.description}</p>
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
    </section>
  );
}
