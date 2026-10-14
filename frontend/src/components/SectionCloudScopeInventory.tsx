"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  CloudProvider,
  ProviderConnectionStatus,
  CloudScopeSummary,
  SubscriptionOrProjectAnalysis,
  DiscoveredResource,
} from "@/types";
import {
  getProvidersStatus,
  listAzureSubscriptions,
  analyzeAzureSubscription,
  listGcpProjects,
  analyzeGcpProject,
} from "@/lib/api";
import {
  Layers,
  ShieldAlert,
  ShieldCheck,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Database,
  Cpu,
  HardDrive,
  Network,
  Sparkles,
  Key,
  FolderTree,
  AlertTriangle,
  CheckCircle2,
  TrendingDown,
  Info,
  Activity,
  Clock,
  AlertOctagon,
  ArrowRight,
} from "lucide-react";
import { MermaidDiagram } from "@/components/MermaidDiagram";

export function SectionCloudScopeInventory() {
  const [activeProvider, setActiveProvider] = useState<CloudProvider>("azure");
  const [providersStatus, setProvidersStatus] = useState<ProviderConnectionStatus[]>([]);
  const [scopes, setScopes] = useState<CloudScopeSummary[]>([]);
  const [selectedScopeId, setSelectedScopeId] = useState<string>("");
  const [resourceGroupFilter, setResourceGroupFilter] = useState<string>("");
  const [metricWindowDays, setMetricWindowDays] = useState<number>(30);
  const [refreshTelemetry, setRefreshTelemetry] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isDiscovering, setIsDiscovering] = useState<boolean>(false);
  const [analysis, setAnalysis] = useState<SubscriptionOrProjectAnalysis | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const [selectedResource, setSelectedResource] = useState<DiscoveredResource | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // FinOps Findings Filter State
  const [finopsTab, setFinopsTab] = useState<"waste" | "debt" | "all">("waste");
  const [severityFilter, setSeverityFilter] = useState<"all" | "critical" | "high" | "medium" | "low">("all");

  // Load connection statuses
  const loadStatuses = async () => {
    try {
      const stats = await getProvidersStatus();
      setProvidersStatus(stats);
    } catch (err) {
      console.warn("Failed to load provider statuses:", err);
    }
  };

  // Load available scopes (subscriptions or projects)
  const loadScopes = async (provider: CloudProvider) => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      if (provider === "azure") {
        const subs = await listAzureSubscriptions();
        setScopes(subs);
        if (subs.length > 0) {
          setSelectedScopeId(subs[0].scope_id);
        }
      } else if (provider === "gcp") {
        const projs = await listGcpProjects();
        setScopes(projs);
        if (projs.length > 0) {
          setSelectedScopeId(projs[0].scope_id);
        }
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load cloud scopes.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStatuses();
    loadScopes(activeProvider);
  }, [activeProvider]);

  // Run discovery & analysis
  const handleAnalyze = async () => {
    setIsDiscovering(true);
    setErrorMsg(null);
    setSelectedResource(null);
    try {
      if (activeProvider === "azure") {
        const res = await analyzeAzureSubscription({
          scope_id: selectedScopeId || null,
          resource_group_filter: resourceGroupFilter || null,
          metric_window_days: metricWindowDays,
          refresh_telemetry: refreshTelemetry,
        });
        setAnalysis(res);
        // Expand first 2 groups by default
        const initExp: Record<string, boolean> = {};
        res.groups.slice(0, 2).forEach((g) => {
          initExp[g.group_id] = true;
        });
        setExpandedGroups(initExp);
      } else if (activeProvider === "gcp") {
        const res = await analyzeGcpProject({
          scope_id: selectedScopeId || null,
          metric_window_days: metricWindowDays,
          refresh_telemetry: refreshTelemetry,
        });
        setAnalysis(res);
        const initExp: Record<string, boolean> = {};
        res.groups.slice(0, 2).forEach((g) => {
          initExp[g.group_id] = true;
        });
        setExpandedGroups(initExp);
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Scope analysis failed.");
    } finally {
      setIsDiscovering(false);
    }
  };

  const toggleGroup = (groupId: string) => {
    setExpandedGroups((prev) => ({
      ...prev,
      [groupId]: !prev[groupId],
    }));
  };

  const currentProviderStatus = providersStatus.find((p) => p.provider === activeProvider);

  // Filtered waste findings and tech debt
  const filteredWasteFindings = useMemo(() => {
    if (!analysis?.waste_findings) return [];
    return analysis.waste_findings.filter((w) => {
      if (severityFilter !== "all" && w.severity !== severityFilter) return false;
      return true;
    });
  }, [analysis?.waste_findings, severityFilter]);

  const filteredDebtItems = useMemo(() => {
    if (!analysis?.technical_debt_items) return [];
    return analysis.technical_debt_items.filter((d) => {
      if (severityFilter !== "all" && d.severity !== severityFilter) return false;
      return true;
    });
  }, [analysis?.technical_debt_items, severityFilter]);

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case "compute":
        return <Cpu className="w-3.5 h-3.5 text-blue-500" />;
      case "database":
        return <Database className="w-3.5 h-3.5 text-emerald-500" />;
      case "storage":
        return <HardDrive className="w-3.5 h-3.5 text-amber-500" />;
      case "networking":
        return <Network className="w-3.5 h-3.5 text-indigo-500" />;
      case "ai_ml":
        return <Sparkles className="w-3.5 h-3.5 text-purple-500" />;
      case "security":
        return <Key className="w-3.5 h-3.5 text-rose-500" />;
      default:
        return <Layers className="w-3.5 h-3.5 text-slate-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "verified":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-2.5 h-2.5" /> Verified Rate
          </span>
        );
      case "provisional":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            <Info className="w-2.5 h-2.5" /> Usage Consumption
          </span>
        );
      case "bundled":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            Bundled / Free Tier
          </span>
        );
      case "unpriced":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangle className="w-2.5 h-2.5" /> Unpriced
          </span>
        );
      default:
        return null;
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case "critical":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-rose-100 text-rose-800 border border-rose-300">
            <AlertOctagon className="w-3 h-3 text-rose-600" /> Critical
          </span>
        );
      case "high":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-100 text-amber-800 border border-amber-300">
            <AlertTriangle className="w-3 h-3 text-amber-600" /> High
          </span>
        );
      case "medium":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-blue-100 text-blue-800 border border-blue-300">
            Medium
          </span>
        );
      case "low":
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-slate-100 text-slate-700 border border-slate-300">
            Low
          </span>
        );
    }
  };

  const getConfidenceBadge = (confidence: string) => {
    switch (confidence) {
      case "high":
        return (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            High Confidence
          </span>
        );
      case "medium":
        return (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            Medium Confidence
          </span>
        );
      case "provisional":
      default:
        return (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-50 text-slate-600 border border-slate-200">
            Provisional
          </span>
        );
    }
  };

  const getSpendBasisBadge = (basis: string) => {
    if (basis === "observed_billing") {
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-purple-50 text-purple-700 border border-purple-200">
          Observed Billing
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-sky-50 text-sky-700 border border-sky-200">
        Catalog Rate
      </span>
    );
  };

  return (
    <section className="mt-8 space-y-6">
      {/* Header & Controls Panel */}
      <div className="rounded-2xl glass-card p-6 border border-slate-200/80 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-5 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200/80 uppercase tracking-wide">
                Subscription & Project Intelligence
              </span>
              <span className="text-xs text-slate-400 font-mono">FinOps & Technical Debt</span>
            </div>
            <h2 className="text-xl font-bold text-slate-900 mt-1">
              Multi-Cloud Resource Inventory & Hierarchical Cost Rollup
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Strictly read-only inspection of live subscriptions, resource groups, telemetry, waste detection, and deterministic pricing.
            </p>
          </div>

          {/* Provider Toggle: Azure vs GCP */}
          <div className="flex items-center gap-2 p-1 bg-slate-100/90 rounded-xl border border-slate-200/80">
            <button
              type="button"
              onClick={() => {
                setActiveProvider("azure");
                setAnalysis(null);
              }}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                activeProvider === "azure"
                  ? "bg-white text-blue-700 shadow-sm border border-slate-200"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <div className="w-2 h-2 rounded-full bg-blue-600" />
              <span>Azure Subscription</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveProvider("gcp");
                setAnalysis(null);
              }}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                activeProvider === "gcp"
                  ? "bg-white text-emerald-700 shadow-sm border border-slate-200"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <div className="w-2 h-2 rounded-full bg-emerald-600" />
              <span>Google Cloud Project</span>
            </button>
          </div>
        </div>

        {/* Connection Status Banner */}
        {currentProviderStatus && (
          <div className="mt-4 p-3.5 rounded-xl bg-slate-50 border border-slate-200/90 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div className="flex items-start sm:items-center gap-2.5">
              {currentProviderStatus.inventory_auth_ready ? (
                <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5 sm:mt-0" />
              ) : (
                <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5 sm:mt-0" />
              )}
              <div>
                <span className="font-semibold text-slate-800">
                  {currentProviderStatus.inventory_auth_ready ? "Authenticated: " : "Notice: "}
                </span>
                <span className="text-slate-600">{currentProviderStatus.status_message}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="px-2 py-0.5 rounded-md bg-white border border-slate-200 text-[11px] font-mono text-slate-700">
                {currentProviderStatus.pricing_api_source}
              </span>
            </div>
          </div>
        )}

        {/* Scope Selector Form */}
        <div className="mt-5 grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
          <div className={activeProvider === "azure" ? "sm:col-span-4" : "sm:col-span-6"}>
            <label className="block text-[11px] font-medium text-slate-600 uppercase mb-1">
              {activeProvider === "azure" ? "Authorized Subscription" : "Target GCP Project"}
            </label>
            <select
              value={selectedScopeId}
              onChange={(e) => setSelectedScopeId(e.target.value)}
              disabled={isLoading || isDiscovering}
              className="w-full text-xs rounded-xl border border-slate-300 bg-white px-3 py-2 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            >
              {scopes.map((s) => (
                <option key={s.scope_id} value={s.scope_id}>
                  {s.display_name} ({s.scope_id}) {s.data_source === "mock_fixture" ? "[Demo Fixture]" : ""}
                </option>
              ))}
            </select>
          </div>

          {activeProvider === "azure" && (
            <div className="sm:col-span-3">
              <label className="block text-[11px] font-medium text-slate-600 uppercase mb-1">
                Resource Group Filter (Optional)
              </label>
              <input
                type="text"
                placeholder="e.g. rg-smart-expense"
                value={resourceGroupFilter}
                onChange={(e) => setResourceGroupFilter(e.target.value)}
                disabled={isDiscovering}
                className="w-full text-xs rounded-xl border border-slate-300 bg-white px-3 py-2 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
          )}

          <div className="sm:col-span-2">
            <label className="block text-[11px] font-medium text-slate-600 uppercase mb-1">
              Telemetry Window
            </label>
            <select
              value={metricWindowDays}
              onChange={(e) => setMetricWindowDays(Number(e.target.value))}
              disabled={isDiscovering}
              className="w-full text-xs rounded-xl border border-slate-300 bg-white px-3 py-2 font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            >
              <option value={7}>7 Days (Recent)</option>
              <option value={14}>14 Days (Bi-Weekly)</option>
              <option value={30}>30 Days (Standard)</option>
              <option value={60}>60 Days (Extended)</option>
              <option value={90}>90 Days (Quarterly)</option>
            </select>
          </div>

          <div className={activeProvider === "azure" ? "sm:col-span-3" : "sm:col-span-4"}>
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={isDiscovering || isLoading}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-xs font-semibold shadow-sm transition"
            >
              {isDiscovering ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Discovering & Evaluating...</span>
                </>
              ) : (
                <>
                  <FolderTree className="w-3.5 h-3.5" />
                  <span>
                    {activeProvider === "azure"
                      ? "Analyze Subscription & Waste"
                      : "Analyze Project & Waste"}
                  </span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Telemetry Refresh & Advisory Notice Row */}
        <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500">
          <label className="inline-flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={refreshTelemetry}
              onChange={(e) => setRefreshTelemetry(e.target.checked)}
              disabled={isDiscovering}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5"
            />
            <span className="text-slate-700 font-medium">Bypass cache and force refresh live telemetry</span>
          </label>
          <span className="text-slate-400">
            Advisory read-only mode • Zero automated changes executed against cloud resources
          </span>
        </div>

        {errorMsg && (
          <div className="mt-3 p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}
      </div>

      {/* Analysis Output Section */}
      {analysis && (
        <div className="space-y-6">
          {/* Hierarchy Breadcrumbs */}
          <div className="p-3.5 rounded-xl bg-white border border-slate-200 shadow-sm flex flex-wrap items-center gap-2 text-xs font-mono">
            <span className="text-slate-400 uppercase font-sans text-[10px]">Hierarchy:</span>
            {analysis.hierarchy_nodes.map((node, i) => (
              <React.Fragment key={node.node_id}>
                {i > 0 && <span className="text-slate-300">/</span>}
                <span
                  className={`px-2 py-0.5 rounded-md border text-[11px] ${
                    node.node_type === "azure_subscription" || node.node_type === "gcp_project"
                      ? "bg-blue-50 border-blue-200 text-blue-800 font-semibold"
                      : node.node_type.includes("group")
                        ? "bg-purple-50 border-purple-200 text-purple-800"
                        : "bg-slate-50 border-slate-200 text-slate-700"
                  }`}
                >
                  <span className="text-[10px] text-slate-400 block font-sans">
                    {node.node_type.replace(/_/g, " ")}
                  </span>
                  {node.name}
                </span>
              </React.Fragment>
            ))}
          </div>

          {/* Rollup KPI Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-4 gap-3">
            {/* Total Monthly Spend */}
            <div className="p-3.5 rounded-xl glass-card border border-slate-200/80">
              <span className="text-[10px] uppercase text-slate-500 font-semibold block">
                Total Monthly Spend
              </span>
              <span className="text-lg font-bold font-mono text-slate-900 block mt-0.5">
                ${parseFloat(analysis.cost_breakdown.total_monthly).toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
              <span className="text-[10px] text-slate-400 block mt-0.5">
                {analysis.spend_label === "estimated_public_list_pricing"
                  ? "Public Catalog Rates"
                  : "Actual Billed Spend"}
              </span>
            </div>

            {/* Potential Monthly Savings */}
            <div className="p-3.5 rounded-xl glass-card border border-emerald-200/90 bg-emerald-50/40">
              <span className="text-[10px] uppercase text-emerald-800 font-bold block flex items-center justify-between">
                <span>Potential Monthly Savings</span>
                <TrendingDown className="w-3.5 h-3.5 text-emerald-600" />
              </span>
              <span className="text-lg font-bold font-mono text-emerald-700 block mt-0.5">
                ${parseFloat(analysis.total_potential_monthly_savings || "0.00").toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
                <span className="text-xs font-normal text-emerald-600">/mo</span>
              </span>
              <span className="text-[10px] text-emerald-700 font-medium block mt-0.5">
                Non-double-counted FinOps
              </span>
            </div>

            {/* Projected Annual Savings */}
            <div className="p-3.5 rounded-xl glass-card border border-slate-200/80">
              <span className="text-[10px] uppercase text-slate-500 font-semibold block">
                Projected Annual Savings
              </span>
              <span className="text-lg font-bold font-mono text-emerald-700 block mt-0.5">
                ${parseFloat(analysis.total_potential_annual_savings || "0.00").toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
                <span className="text-xs font-normal text-slate-500">/yr</span>
              </span>
              <span className="text-[10px] text-slate-400 block mt-0.5">12-Month Projected Run-Rate</span>
            </div>

            {/* Waste Findings & Technical Debt Counts */}
            <div className="p-3.5 rounded-xl glass-card border border-slate-200/80">
              <span className="text-[10px] uppercase text-slate-500 font-semibold block">
                FinOps & Debt Findings
              </span>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="px-2 py-0.5 rounded-md text-xs font-bold font-mono bg-amber-50 text-amber-800 border border-amber-200">
                  {(analysis.waste_findings || []).length} Waste
                </span>
                <span className="px-2 py-0.5 rounded-md text-xs font-bold font-mono bg-rose-50 text-rose-800 border border-rose-200">
                  {(analysis.technical_debt_items || []).length} Debt
                </span>
              </div>
              <span className="text-[10px] text-slate-400 block mt-1">
                {analysis.groups.reduce((acc, g) => acc + (g.critical_findings_count || 0), 0)} Critical findings
              </span>
            </div>

            {/* Discovered Resources */}
            <div className="p-3.5 rounded-xl glass-card border border-slate-200/80">
              <span className="text-[10px] uppercase text-slate-500 font-semibold block">
                Discovered Resources
              </span>
              <span className="text-lg font-bold font-mono text-slate-900 block mt-0.5">
                {analysis.resource_count}
              </span>
              <span className="text-[10px] text-slate-400 block mt-0.5">Normalized inventory</span>
            </div>

            {/* Resource Groups / Scopes */}
            <div className="p-3.5 rounded-xl glass-card border border-slate-200/80">
              <span className="text-[10px] uppercase text-slate-500 font-semibold block">
                {activeProvider === "azure" ? "Resource Groups" : "Service Domains"}
              </span>
              <span className="text-lg font-bold font-mono text-slate-900 block mt-0.5">
                {analysis.group_count}
              </span>
              <span className="text-[10px] text-slate-400 block mt-0.5">Scope partitions</span>
            </div>

            {/* Telemetry Coverage */}
            <div className="p-3.5 rounded-xl glass-card border border-slate-200/80">
              <span className="text-[10px] uppercase text-slate-500 font-semibold block">
                Telemetry Coverage
              </span>
              <span className="text-lg font-bold font-mono text-blue-700 block mt-0.5">
                {analysis.telemetry_coverage ? `${parseFloat(analysis.telemetry_coverage.coverage_percentage).toFixed(0)}%` : "100%"}
              </span>
              <span className="text-[10px] text-slate-400 block mt-0.5">
                {analysis.telemetry_coverage ? `${analysis.telemetry_coverage.metric_window_days}d window` : `${metricWindowDays}d window`}
              </span>
            </div>

            {/* Pricing Completeness */}
            <div className="p-3.5 rounded-xl glass-card border border-slate-200/80">
              <span className="text-[10px] uppercase text-slate-500 font-semibold block">
                Pricing Completeness
              </span>
              <div className="mt-1">
                {analysis.cost_breakdown.is_complete ? (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
                    <CheckCircle2 className="w-3.5 h-3.5" /> 100% Priced
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700">
                    <AlertTriangle className="w-3.5 h-3.5" /> {analysis.cost_breakdown.unpriced_component_count} Unpriced
                  </span>
                )}
              </div>
              <span className="text-[10px] text-slate-400 block mt-0.5">
                {analysis.data_source === "live_authenticated" ? "Live Cloud Rates" : "Reference Fixture"}
              </span>
            </div>
          </div>

          {/* FinOps Waste Detection & Technical Debt Intelligence Panel */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
            {/* Panel Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b border-slate-100">
              <div>
                <div className="flex items-center gap-2">
                  <span className="p-1 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200">
                    <TrendingDown className="w-4 h-4" />
                  </span>
                  <h3 className="text-sm font-bold text-slate-900">
                    FinOps Waste Detection & Technical Debt Intelligence
                  </h3>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Automated analysis of compute utilization, idle storage, orphaned IPs, architectural resilience, and security posture.
                </p>
              </div>

              {/* Zero-Execution Advisory Badge */}
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-slate-600 text-[11px]">
                <ShieldCheck className="w-4 h-4 text-blue-600 shrink-0" />
                <span>Zero automated modifications executed • Advisory FinOps analysis</span>
              </div>
            </div>

            {/* Telemetry Coverage Details */}
            {analysis.telemetry_coverage && (
              <div className="p-3 rounded-xl bg-slate-50/80 border border-slate-200/90 flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-blue-600" />
                    <span className="font-semibold text-slate-800">Source:</span>
                    <span className="text-slate-600">{analysis.telemetry_coverage.telemetry_source}</span>
                  </div>
                  <span className="text-slate-300">•</span>
                  <div className="flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-slate-500" />
                    <span className="font-semibold text-slate-800">Window:</span>
                    <span className="font-mono text-slate-600">{analysis.telemetry_coverage.metric_window_days} Days</span>
                  </div>
                  <span className="text-slate-300">•</span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-slate-800">Coverage:</span>
                    <span className="font-mono font-semibold text-emerald-700">
                      {parseFloat(analysis.telemetry_coverage.coverage_percentage).toFixed(0)}%
                    </span>
                    <span className="text-slate-500">
                      ({analysis.telemetry_coverage.monitored_resources_count} monitored, {analysis.telemetry_coverage.unmonitored_resources_count} unmonitored)
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-white border border-slate-200 text-slate-600">
                    Confidence: {parseFloat(analysis.telemetry_coverage.confidence_score) >= 0.85 ? "High (0.90)" : "Medium (0.75)"}
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-white border border-slate-200 text-slate-600">
                    {analysis.telemetry_coverage.is_cached ? "Cached Metric Window" : "Live Telemetry Sync"}
                  </span>
                </div>
              </div>
            )}

            {/* Filter Tabs and Controls */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
              {/* Tab Pills */}
              <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl border border-slate-200/80">
                <button
                  type="button"
                  onClick={() => setFinopsTab("waste")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    finopsTab === "waste"
                      ? "bg-white text-emerald-800 shadow-sm border border-slate-200"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <TrendingDown className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Cloud Waste Findings</span>
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-emerald-100 text-emerald-800 font-mono">
                    {(analysis.waste_findings || []).length}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setFinopsTab("debt")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    finopsTab === "debt"
                      ? "bg-white text-rose-800 shadow-sm border border-slate-200"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <ShieldAlert className="w-3.5 h-3.5 text-rose-600" />
                  <span>Technical Debt & Risk</span>
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-rose-100 text-rose-800 font-mono">
                    {(analysis.technical_debt_items || []).length}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setFinopsTab("all")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    finopsTab === "all"
                      ? "bg-white text-slate-900 shadow-sm border border-slate-200"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <span>All Findings</span>
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-200 text-slate-700 font-mono">
                    {(analysis.waste_findings || []).length + (analysis.technical_debt_items || []).length}
                  </span>
                </button>
              </div>

              {/* Severity Filter Pills */}
              <div className="flex items-center gap-1.5 text-xs">
                <span className="text-[11px] text-slate-400 font-mono uppercase mr-1">Severity:</span>
                {(["all", "critical", "high", "medium", "low"] as const).map((sev) => (
                  <button
                    key={sev}
                    type="button"
                    onClick={() => setSeverityFilter(sev)}
                    className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold capitalize transition ${
                      severityFilter === sev
                        ? "bg-slate-900 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {sev}
                  </button>
                ))}
              </div>
            </div>

            {/* Waste Findings Cards */}
            {(finopsTab === "waste" || finopsTab === "all") && (
              <div className="space-y-3">
                {finopsTab === "all" && (
                  <div className="flex items-center gap-2 pt-2">
                    <TrendingDown className="w-4 h-4 text-emerald-600" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 font-mono">
                      Cloud Resource Waste Findings ({filteredWasteFindings.length})
                    </h4>
                  </div>
                )}

                {filteredWasteFindings.length === 0 ? (
                  <div className="p-6 text-center rounded-xl bg-slate-50 border border-slate-200 text-slate-500 text-xs">
                    No resource waste findings match the active severity filter.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                    {filteredWasteFindings.map((finding) => (
                      <div
                        key={finding.id}
                        className="p-4 rounded-xl border border-slate-200/90 bg-white shadow-xs hover:border-slate-300 transition space-y-3"
                      >
                        {/* Header Row */}
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            {getSeverityBadge(finding.severity)}
                            {getConfidenceBadge(finding.confidence)}
                            {getSpendBasisBadge(finding.spend_basis)}
                          </div>
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-600">
                            {finding.group_name}
                          </span>
                        </div>

                        {/* Title & Description */}
                        <div>
                          <h4 className="font-bold text-slate-900 text-sm">{finding.title}</h4>
                          <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                            {finding.description}
                          </p>
                        </div>

                        {/* Telemetry Evidence Box */}
                        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80 space-y-1.5 text-xs">
                          {finding.metric_observed && (
                            <div className="flex items-center gap-1.5">
                              <Activity className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                              <span className="font-semibold text-slate-800">Metric Observed:</span>
                              <span className="font-mono text-slate-700">{finding.metric_observed}</span>
                            </div>
                          )}
                          <div className="flex items-start gap-1.5 text-slate-600 text-[11px]">
                            <Info className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                            <span>{finding.evidence}</span>
                          </div>
                        </div>

                        {/* Financial Impact Row */}
                        <div className="p-2.5 rounded-lg bg-emerald-50/50 border border-emerald-200/80 flex items-center justify-between text-xs">
                          <div>
                            <span className="text-[10px] text-slate-500 uppercase block font-mono">
                              Current Spend
                            </span>
                            <span className="font-mono font-semibold text-slate-800">
                              ${parseFloat(finding.current_monthly_spend).toFixed(2)}/mo
                            </span>
                          </div>
                          <ArrowRight className="w-4 h-4 text-emerald-600" />
                          <div className="text-right">
                            <span className="text-[10px] text-emerald-800 uppercase block font-mono font-bold">
                              Achievable Savings
                            </span>
                            <span className="font-mono font-bold text-sm text-emerald-700">
                              ${parseFloat(finding.potential_monthly_savings).toFixed(2)}/mo
                            </span>
                          </div>
                        </div>

                        {/* Double Counting Note */}
                        {finding.double_counting_prevention_note && (
                          <div className="text-[10px] text-slate-500 font-mono italic">
                            * {finding.double_counting_prevention_note}
                          </div>
                        )}

                        {/* Advisory Recommendation */}
                        <div className="text-xs space-y-1 pt-1 border-t border-slate-100">
                          <span className="text-[10px] uppercase font-bold text-slate-500 font-mono block">
                            Advisory Remediation:
                          </span>
                          <p className="text-slate-800 leading-relaxed font-medium">
                            {finding.remediation_recommendation}
                          </p>
                        </div>

                        {/* Pre-Remediation Considerations Checklist */}
                        {finding.pre_remediation_considerations.length > 0 && (
                          <div className="pt-2 border-t border-slate-100 space-y-1 text-[11px]">
                            <span className="text-[10px] uppercase font-bold text-amber-700 font-mono block flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3 text-amber-600" /> Pre-Remediation Checklist:
                            </span>
                            <ul className="space-y-1 pl-1">
                              {finding.pre_remediation_considerations.map((consideration, idx) => (
                                <li key={idx} className="flex items-start gap-1.5 text-slate-600">
                                  <span className="text-slate-400">•</span>
                                  <span>{consideration}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Technical Debt Cards */}
            {(finopsTab === "debt" || finopsTab === "all") && (
              <div className="space-y-3 pt-2">
                {finopsTab === "all" && (
                  <div className="flex items-center gap-2 pt-2">
                    <ShieldAlert className="w-4 h-4 text-rose-600" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 font-mono">
                      Technical Debt & Architectural Risks ({filteredDebtItems.length})
                    </h4>
                  </div>
                )}

                {filteredDebtItems.length === 0 ? (
                  <div className="p-6 text-center rounded-xl bg-slate-50 border border-slate-200 text-slate-500 text-xs">
                    No technical debt items match the active severity filter.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                    {filteredDebtItems.map((item) => (
                      <div
                        key={item.id}
                        className="p-4 rounded-xl border border-slate-200/90 bg-white shadow-xs hover:border-slate-300 transition space-y-3"
                      >
                        {/* Header Row */}
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            {getSeverityBadge(item.severity)}
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200 uppercase font-mono">
                              {item.debt_category.replace(/_/g, " ")}
                            </span>
                          </div>
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-600">
                            {item.group_name}
                          </span>
                        </div>

                        {/* Title & Description */}
                        <div>
                          <h4 className="font-bold text-slate-900 text-sm">{item.title}</h4>
                          <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                            {item.description}
                          </p>
                        </div>

                        {/* Architectural Risk Warning Box */}
                        <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200/80 text-rose-900 text-xs space-y-1">
                          <div className="flex items-center gap-1.5 font-bold text-rose-800">
                            <ShieldAlert className="w-3.5 h-3.5 text-rose-600 shrink-0" />
                            <span>Architectural Risk:</span>
                          </div>
                          <p className="text-[11px] leading-relaxed text-rose-800/90">
                            {item.architectural_risk}
                          </p>
                        </div>

                        {/* Observed Evidence */}
                        <div className="p-2 rounded-lg bg-slate-50 border border-slate-200/80 text-[11px] text-slate-600 flex items-start gap-1.5">
                          <Info className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                          <span>{item.evidence}</span>
                        </div>

                        {/* Remediation Steps */}
                        {item.remediation_steps.length > 0 && (
                          <div className="pt-2 border-t border-slate-100 space-y-1.5 text-xs">
                            <span className="text-[10px] uppercase font-bold text-slate-500 font-mono block">
                              Recommended Modernization Steps:
                            </span>
                            <ol className="list-decimal list-inside space-y-1 text-slate-700 text-[11px]">
                              {item.remediation_steps.map((step, sIdx) => (
                                <li key={sIdx} className="leading-relaxed">
                                  {step}
                                </li>
                              ))}
                            </ol>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Group-by-Group Hierarchical Rollup */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-800">
                {activeProvider === "azure"
                  ? "Hierarchical Resource Group Cost Aggregations"
                  : "Hierarchical Project Service Domain Aggregations"}
              </h3>
              <span className="text-xs text-slate-500">
                {analysis.groups.length} group scopes discovered
              </span>
            </div>

            {analysis.groups.map((group) => {
              const isExpanded = !!expandedGroups[group.group_id];
              return (
                <div
                  key={group.group_id}
                  className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden"
                >
                  {/* Group Summary Row */}
                  <div
                    onClick={() => toggleGroup(group.group_id)}
                    className="p-4 bg-slate-50/70 hover:bg-slate-100/70 cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition"
                  >
                    <div className="flex items-center gap-3">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400" />
                      )}
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-slate-900 text-xs sm:text-sm">
                            {group.group_name}
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-slate-200/80 text-slate-700">
                            {group.location}
                          </span>

                          {/* Potential Monthly Savings Badge on Group */}
                          {group.potential_monthly_savings && parseFloat(group.potential_monthly_savings) > 0 && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                              <TrendingDown className="w-2.5 h-2.5" /> Save ${parseFloat(group.potential_monthly_savings).toFixed(2)}/mo
                            </span>
                          )}

                          {/* Waste Findings Count Badge on Group */}
                          {group.waste_findings_count && group.waste_findings_count > 0 && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800 border border-amber-300">
                              {group.waste_findings_count} waste finding(s)
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] text-slate-500 block mt-0.5">
                          {group.resource_count} resource(s) •{" "}
                          {group.unpriced_resource_count > 0
                            ? `${group.unpriced_resource_count} unpriced`
                            : "100% verified"}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 text-right">
                      <div>
                        <span className="text-[10px] text-slate-400 uppercase block font-mono">
                          Monthly Subtotal
                        </span>
                        <span className="text-sm font-bold font-mono text-slate-900">
                          ${parseFloat(group.total_monthly).toFixed(2)}
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-400 uppercase block font-mono">
                          Annualized
                        </span>
                        <span className="text-xs font-semibold font-mono text-slate-600">
                          ${parseFloat(group.total_annual).toFixed(2)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Expanded Resources Table */}
                  {isExpanded && (
                    <div className="border-t border-slate-200 overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-50/50 text-[10px] uppercase text-slate-500 border-b border-slate-200 font-semibold font-mono">
                          <tr>
                            <th className="py-2.5 px-4">Resource & Service</th>
                            <th className="py-2.5 px-3">Native Type</th>
                            <th className="py-2.5 px-3">SKU / Tier</th>
                            <th className="py-2.5 px-3">Location</th>
                            <th className="py-2.5 px-3">Pricing Status</th>
                            <th className="py-2.5 px-4 text-right">Monthly Cost</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 font-sans">
                          {group.resources.map((res) => {
                            const resWasteCount = res.waste_findings ? res.waste_findings.length : 0;
                            const resDebtCount = res.technical_debt_items ? res.technical_debt_items.length : 0;
                            return (
                              <tr
                                key={res.resource_id}
                                onClick={() => setSelectedResource(res)}
                                className={`hover:bg-blue-50/40 cursor-pointer transition ${
                                  selectedResource?.resource_id === res.resource_id
                                    ? "bg-blue-50/70"
                                    : ""
                                }`}
                              >
                                <td className="py-2.5 px-4">
                                  <div className="flex items-center gap-2">
                                    {getCategoryIcon(res.service_category)}
                                    <div>
                                      <div className="flex items-center gap-1.5 flex-wrap">
                                        <span className="font-semibold text-slate-900">
                                          {res.resource_name}
                                        </span>
                                        {resWasteCount > 0 && (
                                          <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                                            {resWasteCount} Waste
                                          </span>
                                        )}
                                        {resDebtCount > 0 && (
                                          <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
                                            {resDebtCount} Risk
                                          </span>
                                        )}
                                      </div>
                                      <span className="text-[10px] font-mono text-slate-400">
                                        {res.canonical_service_id}
                                      </span>
                                    </div>
                                  </div>
                                </td>
                                <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">
                                  {res.native_resource_type.split("/").pop()}
                                </td>
                                <td className="py-2.5 px-3 font-mono text-[11px] text-slate-700">
                                  {res.sku_or_tier || "Standard"}
                                </td>
                                <td className="py-2.5 px-3 font-mono text-[11px] text-slate-500">
                                  {res.region}
                                </td>
                                <td className="py-2.5 px-3">{getStatusBadge(res.pricing_status)}</td>
                                <td className="py-2.5 px-4 text-right font-mono font-bold text-slate-900">
                                  ${parseFloat(res.estimated_monthly_cost).toFixed(2)}
                                </td>
                              </tr>
                            );
                          })}
                          {group.resources.length === 0 && (
                            <tr>
                              <td colSpan={6} className="py-4 text-center text-slate-400 text-xs">
                                No resources in this group.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Selected Resource Detail Drawer */}
          {selectedResource && (
            <div className="p-4 rounded-xl bg-slate-900 text-slate-100 shadow-md border border-slate-800 text-xs space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded bg-blue-900/60 text-blue-300 font-mono text-[10px]">
                    {selectedResource.native_resource_type}
                  </span>
                  <span className="font-bold text-sm text-white">
                    {selectedResource.resource_name}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedResource(null)}
                  className="text-slate-400 hover:text-white text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 transition"
                >
                  Close
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px] font-mono">
                <div>
                  <span className="text-slate-400 block">Resource ID:</span>
                  <span className="text-slate-200 break-all">{selectedResource.resource_id}</span>
                </div>
                <div>
                  <span className="text-slate-400 block">Pricing Calculation Formula:</span>
                  <span className="text-emerald-300 font-sans">
                    {selectedResource.calculation_explanation || "Standard catalog calculation."}
                  </span>
                </div>
              </div>

              {/* Resource-specific Waste Findings in Drawer */}
              {selectedResource.waste_findings && selectedResource.waste_findings.length > 0 && (
                <div className="p-3 rounded-lg bg-amber-950/40 border border-amber-800/60 space-y-2">
                  <span className="text-amber-400 text-[10px] uppercase font-bold font-mono block">
                    Detected Waste Inefficiencies ({selectedResource.waste_findings.length}):
                  </span>
                  {selectedResource.waste_findings.map((w) => (
                    <div key={w.id} className="text-[11px] space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-amber-200">{w.title}</span>
                        <span className="font-mono text-emerald-300 font-bold">
                          Save ${parseFloat(w.potential_monthly_savings).toFixed(2)}/mo
                        </span>
                      </div>
                      <p className="text-slate-300 text-[10px]">{w.description}</p>
                      <p className="text-emerald-300/90 text-[10px]">Action: {w.remediation_recommendation}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Resource-specific Technical Debt in Drawer */}
              {selectedResource.technical_debt_items && selectedResource.technical_debt_items.length > 0 && (
                <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/60 space-y-2">
                  <span className="text-rose-400 text-[10px] uppercase font-bold font-mono block">
                    Technical Debt & Risk Items ({selectedResource.technical_debt_items.length}):
                  </span>
                  {selectedResource.technical_debt_items.map((d) => (
                    <div key={d.id} className="text-[11px] space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-rose-200">{d.title}</span>
                        <span className="font-mono text-rose-300 uppercase text-[9px] px-1.5 py-0.5 rounded bg-rose-900/60">
                          {d.debt_category}
                        </span>
                      </div>
                      <p className="text-slate-300 text-[10px]">{d.description}</p>
                      <p className="text-rose-300/90 text-[10px]">Risk: {d.architectural_risk}</p>
                    </div>
                  ))}
                </div>
              )}

              {selectedResource.relationships.length > 0 && (
                <div className="pt-2 border-t border-slate-800">
                  <span className="text-slate-400 text-[10px] uppercase block mb-1">
                    Architectural Relationships & Dependencies:
                  </span>
                  <div className="space-y-1">
                    {selectedResource.relationships.map((rel, i) => (
                      <div
                        key={i}
                        className="p-1.5 rounded bg-slate-800/80 flex items-center justify-between gap-2 text-[10px]"
                      >
                        <span className="text-slate-300">
                          {rel.direction.toUpperCase()}: {rel.target_resource_name}
                        </span>
                        <span
                          className={`px-1.5 py-0.5 rounded ${
                            rel.is_verified
                              ? "bg-emerald-950 text-emerald-400"
                              : "bg-amber-950 text-amber-400"
                          }`}
                        >
                          {rel.relationship_type}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Architecture Graph Viewer */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Discovered Architecture Topology (Mermaid Flowchart)
                </h3>
                <p className="text-xs text-slate-500">
                  Evidence-based hierarchy with solid lines for verified ARM/GCP relationships and dashed lines for co-located application tiers.
                </p>
              </div>
            </div>
            <div className="rounded-xl overflow-hidden">
              <MermaidDiagram
                chart={analysis.architecture_mermaid}
                title={`${analysis.provider === "azure" ? "Azure Subscription" : "GCP Project"} Topology (${analysis.resource_count} Resources)`}
                provider={analysis.provider}
              />
            </div>
          </div>

          {/* Subscription / Project Recommendations */}
          {analysis.recommendations.length > 0 && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-blue-600" />
                <h3 className="text-sm font-bold text-slate-900">
                  Environment Optimization & Architecture Modernization
                </h3>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {analysis.recommendations.map((rec) => (
                  <div
                    key={rec.id}
                    className="p-4 rounded-xl border border-slate-200/90 bg-slate-50/60 space-y-2 text-xs"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase bg-slate-200 text-slate-700">
                        {rec.category.replace(/_/g, " ")}
                      </span>
                      {rec.impact_type === "monthly_savings" ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 font-mono">
                          <TrendingDown className="w-3.5 h-3.5" />
                          {parseFloat(rec.estimated_monthly_impact) < 0
                            ? `Save $${Math.abs(parseFloat(rec.estimated_monthly_impact)).toFixed(2)}/mo`
                            : "Cost Neutral"}
                        </span>
                      ) : (
                        <span className="text-[11px] font-bold text-blue-700 font-mono">
                          Invest ${parseFloat(rec.estimated_monthly_impact).toFixed(2)}/mo
                        </span>
                      )}
                    </div>

                    <h4 className="font-bold text-slate-900 text-sm">{rec.title}</h4>
                    <p className="text-slate-600 leading-relaxed">{rec.rationale}</p>

                    <div className="pt-2 border-t border-slate-200/60 text-[11px]">
                      <span className="text-slate-400 block font-mono text-[10px] uppercase">
                        Evidence:
                      </span>
                      <span className="text-slate-700">{rec.evidence}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
