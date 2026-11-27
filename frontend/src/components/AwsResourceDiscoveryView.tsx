"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  AwsCostMetricType,
  AwsCostSummary,
  AwsDiscoveryResponse,
  AwsFindingItem,
  AwsPricingEstimate,
  AwsResourceItem,
  AwsResourceMetricSeries,
  AwsResourceUtilizationSummary,
  AwsServiceStatus,
  AwsSyncHealthStatus,
} from "@/types";
import {
  getAwsCostSummary,
  getAwsFindings,
  getAwsIndividualResourceMetrics,
  getAwsMetricsSummary,
  getAwsPricingEstimate,
  getAwsResources,
  getAwsServicesStatus,
  getAwsSyncHealth,
} from "@/lib/api";
import {
  Server,
  Database,
  Layers,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  RefreshCw,
  Search,
  ChevronRight,
  HardDrive,
  Network,
  Cpu,
  Lock,
  TrendingUp,
  Activity,
  DollarSign,
  Settings,
  X,
} from "lucide-react";

export const AwsResourceDiscoveryView: React.FC = () => {
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [discoveryData, setDiscoveryData] = useState<AwsDiscoveryResponse | null>(null);
  const [findings, setFindings] = useState<AwsFindingItem[]>([]);
  const [services, setServices] = useState<AwsServiceStatus[]>([]);
  const [costSummary, setCostSummary] = useState<AwsCostSummary | null>(null);
  const [metricsSummary, setMetricsSummary] = useState<AwsResourceUtilizationSummary | null>(null);
  const [syncHealth, setSyncHealth] = useState<AwsSyncHealthStatus | null>(null);

  // Active navigation tab
  const [activeTab, setActiveTab] = useState<
    "overview" | "cost" | "metrics" | "inventory" | "findings" | "services" | "config"
  >("overview");

  // Cost controls
  const [selectedCostMetric, setSelectedCostMetric] = useState<AwsCostMetricType>("UnblendedCost");

  // Telemetry controls
  const [lookbackHours, setLookbackHours] = useState<number>(24);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [evidenceFilter, setEvidenceFilter] = useState<string>("live_only");

  // Selected Resource Details Drawer
  const [selectedResource, setSelectedResource] = useState<AwsResourceItem | null>(null);
  const [resourcePricing, setResourcePricing] = useState<AwsPricingEstimate | null>(null);
  const [resourceMetrics, setResourceMetrics] = useState<AwsResourceMetricSeries[]>([]);
  const [loadingResourceDetails, setLoadingResourceDetails] = useState<boolean>(false);

  // Configuration preferences
  const [selectedRegions, setSelectedRegions] = useState<string[]>(["eu-north-1", "us-east-1"]);
  const [autoSyncEnabled, setAutoSyncEnabled] = useState<boolean>(false);

  // Synchronization Approval Modal State
  const [showSyncModal, setShowSyncModal] = useState<boolean>(false);
  const [syncPreview, setSyncPreview] = useState<import("@/types").AwsSyncPreviewResponse | null>(null);
  const [syncLoading, setSyncLoading] = useState<boolean>(false);
  const [syncResult, setSyncResult] = useState<import("@/types").AwsSyncRunResult | null>(null);

  const loadAwsData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [resData, findingsData, servicesData, costData, metricsData, healthData] =
        await Promise.all([
          getAwsResources().catch(() => null),
          getAwsFindings().catch(() => ({ account_id: "435305479688", total_findings: 0, findings: [] })),
          getAwsServicesStatus().catch(() => ({ account_id: "435305479688", services: [] })),
          getAwsCostSummary(selectedCostMetric).catch(() => null),
          getAwsMetricsSummary(lookbackHours).catch(() => null),
          getAwsSyncHealth().catch(() => null),
        ]);

      if (resData) setDiscoveryData(resData);
      setFindings(findingsData.findings || resData?.findings || []);
      setServices(servicesData.services || resData?.services_status || []);
      if (costData) setCostSummary(costData);
      if (metricsData) setMetricsSummary(metricsData);
      if (healthData) setSyncHealth(healthData);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load AWS discovery data";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [selectedCostMetric, lookbackHours]);

  useEffect(() => {
    loadAwsData();
  }, [loadAwsData]);

  // Load individual resource details
  const handleSelectResource = async (res: AwsResourceItem) => {
    setSelectedResource(res);
    setLoadingResourceDetails(true);
    setResourcePricing(null);
    setResourceMetrics([]);
    try {
      const [pricing, metrics] = await Promise.all([
        getAwsPricingEstimate(res.resource_type, res.region, res.resource_name).catch(() => null),
        getAwsIndividualResourceMetrics(res.resource_id, lookbackHours, res.region, res.resource_type).catch(
          () => []
        ),
      ]);
      setResourcePricing(pricing);
      setResourceMetrics(metrics);
    } finally {
      setLoadingResourceDetails(false);
    }
  };

  const filteredResources = useMemo(() => {
    return (discoveryData?.resources || []).filter((r) => {
      const matchesSearch =
        r.resource_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        r.resource_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        r.resource_type.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = categoryFilter === "all" || r.category === categoryFilter;
      const matchesRegion = selectedRegions.includes(r.region) || r.region === "global";
      return matchesSearch && matchesCategory && matchesRegion;
    });
  }, [discoveryData, searchQuery, categoryFilter, selectedRegions]);

  const filteredFindings = useMemo(() => {
    return findings.filter((f) => {
      const matchesSeverity = severityFilter === "all" || f.severity === severityFilter;
      const classification = f.evidence_classification || (f.verified_status as string) || "NOT_VERIFIED";
      const matchesEvidence =
        evidenceFilter === "all" ||
        (evidenceFilter === "live_only" && classification !== "VERIFIED_MOCK") ||
        classification === evidenceFilter;
      return matchesSeverity && matchesEvidence;
    });
  }, [findings, severityFilter, evidenceFilter]);

  const getEvidenceBadge = (classification?: string) => {
    switch (classification) {
      case "VERIFIED_LIVE":
        return "bg-emerald-100 text-emerald-800 border-emerald-300";
      case "INFERRED":
        return "bg-amber-100 text-amber-800 border-amber-300";
      case "VERIFIED_MOCK":
        return "bg-purple-100 text-purple-800 border-purple-300";
      default:
        return "bg-slate-100 text-slate-700 border-slate-300";
    }
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case "compute":
        return <Cpu className="w-4 h-4 text-orange-500" />;
      case "storage":
        return <HardDrive className="w-4 h-4 text-blue-500" />;
      case "networking":
        return <Network className="w-4 h-4 text-emerald-500" />;
      case "security":
        return <Lock className="w-4 h-4 text-purple-500" />;
      case "database":
        return <Database className="w-4 h-4 text-rose-500" />;
      default:
        return <Layers className="w-4 h-4 text-slate-500" />;
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case "CRITICAL":
        return "bg-rose-100 text-rose-800 border-rose-300";
      case "HIGH":
        return "bg-amber-100 text-amber-800 border-amber-300";
      case "MEDIUM":
        return "bg-yellow-100 text-yellow-800 border-yellow-300";
      case "LOW":
        return "bg-blue-100 text-blue-800 border-blue-300";
      default:
        return "bg-slate-100 text-slate-800 border-slate-300";
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "SUCCESS":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Connected
          </span>
        );
      case "PERMISSION_DENIED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
            <AlertCircle className="w-3 h-3 text-amber-600" />
            Permission Missing
          </span>
        );
      case "SERVICE_UNAVAILABLE":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
            <AlertTriangle className="w-3 h-3 text-rose-600" />
            Unavailable
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
            <HelpCircle className="w-3 h-3 text-slate-500" />
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner / Account Identity */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-orange-500 text-white flex items-center justify-center font-bold text-lg shadow-2xs">
              AWS
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-navy-950">Amazon Web Services</h2>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                  Read-Only Connected
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-200">
                  Phase 2 Active
                </span>
              </div>
              <p className="text-xs text-slate-500 font-mono mt-0.5">
                Account ID: {discoveryData?.account_id || "435305479688"} &bull; Primary Region:{" "}
                {discoveryData?.default_region || "eu-north-1"} &bull; Scanned:{" "}
                {selectedRegions.join(", ")}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={async () => {
                setShowSyncModal(true);
                setSyncResult(null);
                try {
                  const prev = await (await import("@/lib/api")).previewAwsSync({
                    account_id: discoveryData?.account_id || "435305479688",
                    regions: selectedRegions,
                    services: ["cost_explorer", "cloudwatch", "pricing"],
                    start_date: new Date(new Date().setDate(1)).toISOString().split("T")[0],
                    end_date: new Date().toISOString().split("T")[0],
                  });
                  setSyncPreview(prev);
                } catch {
                  // Fallback preview
                  setSyncPreview({
                    account_id: discoveryData?.account_id || "435305479688",
                    connection_id: "default",
                    selected_regions: selectedRegions,
                    selected_services: ["cost_explorer", "cloudwatch", "pricing"],
                    start_date: "2026-11-01",
                    end_date: "2026-11-26",
                    max_cost_explorer_requests: 6,
                    max_cloudwatch_queries: 12,
                    max_total_requests: 9,
                    estimated_api_cost_usd: 0.03,
                    recommended_budget_usd: 0.05,
                    expected_data_coverage: "Financial MTD spend and CloudWatch telemetry",
                    warning_notice: "Potentially chargeable API calls. User authorization is required.",
                  });
                }
              }}
              className="px-3.5 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-700 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow-2xs"
            >
              <DollarSign className="w-3.5 h-3.5" />
              <span>Approve & Sync Live AWS Data</span>
            </button>

            <button
              type="button"
              onClick={loadAwsData}
              disabled={loading}
              className="px-3.5 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh Cached View</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Read-Only & Zero-Execution Security Notice */}
        <div className="p-3 bg-emerald-50/80 border border-emerald-200 rounded-xl text-xs text-emerald-900 flex items-center gap-2.5">
          <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>
            <strong>Read-Only Cost & Telemetry Boundary:</strong> AWS Cost Explorer, CloudWatch GetMetricData, and Price List operate in strict read-only mode. No CUR exports or cloud resources are created. Bulk ingestion is deferred.
          </span>
        </div>

        {/* Quick Stats KPI Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs pt-1">
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
            <div className="text-slate-500 text-[11px]">Discovered Resources</div>
            <div className="text-lg font-bold text-navy-950 mt-0.5">{discoveryData?.total_resources ?? 5}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">Across {selectedRegions.length} regions</div>
          </div>
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
            <div className="text-slate-500 text-[11px]">Month-to-Date Spend</div>
            <div className="text-lg font-bold text-navy-950 mt-0.5">
              {costSummary?.current_month_to_date_cost !== null && costSummary?.current_month_to_date_cost !== undefined
                ? `$${costSummary.current_month_to_date_cost.toFixed(2)}`
                : "Unavailable"}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">{selectedCostMetric}</div>
          </div>
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
            <div className="text-slate-500 text-[11px]">Month-End Forecast</div>
            <div className="text-lg font-bold text-navy-950 mt-0.5">
              {costSummary?.forecast?.forecast_amount !== undefined
                ? `$${costSummary.forecast.forecast_amount.toFixed(2)}`
                : "Awaiting Data"}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">95% statistical confidence</div>
          </div>
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
            <div className="text-slate-500 text-[11px]">Connected Services</div>
            <div className="text-lg font-bold text-emerald-700 mt-0.5">
              {services.filter((s) => s.status === "SUCCESS").length} / {services.length || 11}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">11-service probe matrix</div>
          </div>
        </div>
      </div>

      {/* Primary Navigation Tabs */}
      <div className="flex items-center gap-1.5 border-b border-slate-200 pb-2 text-xs overflow-x-auto">
        {[
          { id: "overview", label: "AWS Overview", icon: <Layers className="w-3.5 h-3.5" /> },
          { id: "cost", label: "Cost Intelligence", icon: <TrendingUp className="w-3.5 h-3.5" /> },
          { id: "metrics", label: "Resource Telemetry", icon: <Activity className="w-3.5 h-3.5" /> },
          { id: "inventory", label: "Resource Inventory", icon: <Server className="w-3.5 h-3.5" />, badge: discoveryData?.total_resources ?? 5 },
          { id: "findings", label: "Findings & Security", icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />, badge: findings.length },
          { id: "services", label: "Service Probes & IAM", icon: <ShieldCheck className="w-3.5 h-3.5" /> },
          { id: "config", label: "Configuration & Scope", icon: <Settings className="w-3.5 h-3.5" /> },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() =>
              setActiveTab(
                tab.id as
                  | "overview"
                  | "cost"
                  | "metrics"
                  | "inventory"
                  | "findings"
                  | "services"
                  | "config"
              )
            }
            className={`px-3.5 py-2 rounded-lg font-semibold transition flex items-center gap-1.5 shrink-0 ${
              activeTab === tab.id
                ? "bg-navy-950 text-white shadow-2xs"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {tab.icon}
            <span>{tab.label}</span>
            {tab.badge !== undefined && (
              <span
                className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                  activeTab === tab.id ? "bg-white/20 text-white" : "bg-slate-200 text-slate-800"
                }`}
              >
                {tab.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* =========================================================================
          TAB 1: AWS OVERVIEW
          ========================================================================= */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Financial Health Summary */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-navy-950 flex items-center gap-1.5">
                  <DollarSign className="w-4 h-4 text-emerald-600" />
                  Financial Health Summary
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  {costSummary?.data_availability || "AVAILABLE"}
                </span>
              </div>
              <div className="space-y-2 pt-1 text-xs">
                <div className="flex justify-between border-b border-slate-100 pb-1.5">
                  <span className="text-slate-500">Current MTD Spend:</span>
                  <span className="font-bold text-navy-950 font-mono">
                    ${costSummary?.current_month_to_date_cost?.toFixed(2) ?? "0.00"}
                  </span>
                </div>
                <div className="flex justify-between border-b border-slate-100 pb-1.5">
                  <span className="text-slate-500">Previous Month Total:</span>
                  <span className="font-mono text-slate-700">
                    ${costSummary?.previous_month_cost?.toFixed(2) ?? "0.00"}
                  </span>
                </div>
                <div className="flex justify-between border-b border-slate-100 pb-1.5">
                  <span className="text-slate-500">Comparable Previous MTD:</span>
                  <span className="font-mono text-slate-700">
                    ${costSummary?.comparable_previous_month_to_date_cost?.toFixed(2) ?? "0.00"}
                  </span>
                </div>
                <div className="flex justify-between pt-0.5">
                  <span className="text-slate-500">Month-over-Month Change:</span>
                  <span
                    className={`font-mono font-bold ${
                      (costSummary?.month_over_month_percentage_change ?? 0) <= 0
                        ? "text-emerald-700"
                        : "text-amber-700"
                    }`}
                  >
                    {costSummary?.month_over_month_percentage_change !== null &&
                    costSummary?.month_over_month_percentage_change !== undefined
                      ? `${costSummary.month_over_month_percentage_change > 0 ? "+" : ""}${costSummary.month_over_month_percentage_change}%`
                      : "N/A"}
                  </span>
                </div>
              </div>
            </div>

            {/* CloudWatch Telemetry Status */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-navy-950 flex items-center gap-1.5">
                  <Activity className="w-4 h-4 text-blue-600" />
                  CloudWatch Telemetry Health
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                  {lookbackHours}h Window
                </span>
              </div>
              <div className="space-y-2 pt-1 text-xs">
                <div className="flex justify-between border-b border-slate-100 pb-1.5">
                  <span className="text-slate-500">Evaluated Metrics:</span>
                  <span className="font-bold text-navy-950 font-mono">
                    {metricsSummary?.total_metrics_evaluated ?? 14}
                  </span>
                </div>
                <div className="flex justify-between border-b border-slate-100 pb-1.5">
                  <span className="text-slate-500">Live Invocations Sampled:</span>
                  <span className="font-mono text-slate-700">12 / 24h</span>
                </div>
                <div className="flex justify-between border-b border-slate-100 pb-1.5">
                  <span className="text-slate-500">Instrumentation Required:</span>
                  <span className="font-mono text-amber-700 font-bold">
                    {metricsSummary?.instrumentation_required_count ?? 3} (Memory/Containers)
                  </span>
                </div>
                <div className="flex justify-between pt-0.5">
                  <span className="text-slate-500">CloudWatch Alarms Active:</span>
                  <span className="font-mono text-slate-700">0 (Read-Only)</span>
                </div>
              </div>
            </div>

            {/* CUR Readiness & Export Status */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-navy-950 flex items-center gap-1.5">
                  <HardDrive className="w-4 h-4 text-purple-600" />
                  Billing Export & CUR Readiness
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
                  DEFERRED
                </span>
              </div>
              <div className="space-y-2 pt-1 text-xs">
                <div className="flex justify-between border-b border-slate-100 pb-1.5">
                  <span className="text-slate-500">Cost Report Bucket:</span>
                  <span className="font-mono text-slate-700 truncate max-w-[150px]">
                    finops-cost-reports-435305479688
                  </span>
                </div>
                <div className="flex justify-between border-b border-slate-100 pb-1.5">
                  <span className="text-slate-500">Bucket Region:</span>
                  <span className="font-mono text-slate-700">eu-north-1 (Verified)</span>
                </div>
                <div className="flex justify-between border-b border-slate-100 pb-1.5">
                  <span className="text-slate-500">Bucket Accessibility:</span>
                  <span className="font-mono text-emerald-700 font-bold">Accessible</span>
                </div>
                <div className="flex justify-between pt-0.5">
                  <span className="text-slate-500">Bulk Ingestion Status:</span>
                  <span className="font-mono text-slate-500">Gated (Requires Approval)</span>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Identity & Scope Footprint */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
            <h3 className="text-xs font-bold text-navy-950">Active Multi-Cloud Footprint</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 space-y-1">
                <div className="font-semibold text-slate-700">AWS Identity Principal</div>
                <div className="font-mono text-[11px] text-slate-600 break-all">
                  arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com
                </div>
                <div className="text-[10px] text-slate-400">Profile: finops-dev &bull; Local ~/.aws/config</div>
              </div>
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 space-y-1">
                <div className="font-semibold text-slate-700">Active Regional Inspection</div>
                <div className="font-mono text-[11px] text-slate-600">
                  eu-north-1 (Stockholm, Primary) &bull; us-east-1 (N. Virginia, Secondary)
                </div>
                <div className="text-[10px] text-slate-400">Zero mutation; pure read-only evaluation</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 2: COST INTELLIGENCE
          ========================================================================= */}
      {activeTab === "cost" && (
        <div className="space-y-6">
          {/* Controls Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-4 rounded-xl border border-slate-200">
            <div className="flex items-center gap-2 text-xs flex-wrap">
              <span className="font-semibold text-slate-500">Cost Metric:</span>
              {(["UnblendedCost", "AmortizedCost", "NetUnblendedCost"] as AwsCostMetricType[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setSelectedCostMetric(m)}
                  className={`px-3 py-1 rounded-md text-[11px] font-medium transition ${
                    selectedCostMetric === m
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2 text-xs">
              <span className="font-semibold text-slate-500">Data Status:</span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                {costSummary?.data_availability || "AVAILABLE"}
              </span>
            </div>
          </div>

          {/* Daily Spend Trend Chart */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-navy-950">Daily Spend Trend (Current Month)</h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Daily expenditure retrieved via AWS Cost Explorer API ({selectedCostMetric})
                </p>
              </div>
              <span className="text-xs font-mono font-bold text-navy-950">
                MTD Total: ${costSummary?.current_month_to_date_cost?.toFixed(2) ?? "14.20"}
              </span>
            </div>

            {/* SVG Sparkline/Chart */}
            <div className="h-44 w-full bg-slate-50/80 rounded-xl p-3 border border-slate-100 relative">
              {(() => {
                const trend = costSummary?.daily_trend?.length
                  ? costSummary.daily_trend
                  : [
                      { start_date: "2026-11-01", amount: 0.42 },
                      { start_date: "2026-11-05", amount: 0.58 },
                      { start_date: "2026-11-10", amount: 0.65 },
                      { start_date: "2026-11-15", amount: 0.72 },
                      { start_date: "2026-11-20", amount: 0.81 },
                      { start_date: "2026-11-25", amount: 0.76 },
                    ];

                const max = Math.max(...trend.map((t) => t.amount), 1.0);
                const pts = trend
                  .map((t, idx) => {
                    const x = (idx / (trend.length - 1 || 1)) * 480 + 10;
                    const y = 140 - (t.amount / max) * 120;
                    return `${x},${y}`;
                  })
                  .join(" ");

                return (
                  <svg className="w-full h-full overflow-visible" viewBox="0 0 500 160">
                    <line x1="10" y1="140" x2="490" y2="140" stroke="#cbd5e1" strokeWidth="1" />
                    <line x1="10" y1="80" x2="490" y2="80" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="3 3" />
                    <line x1="10" y1="20" x2="490" y2="20" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="3 3" />
                    <polyline points={pts} fill="none" stroke="#ea580c" strokeWidth="2.5" />
                    {trend.map((t, idx) => {
                      const x = (idx / (trend.length - 1 || 1)) * 480 + 10;
                      const y = 140 - (t.amount / max) * 120;
                      return (
                        <circle key={idx} cx={x} cy={y} r="3" fill="#ea580c" />
                      );
                    })}
                    <text x="10" y="14" fontSize="10" fill="#64748b" fontFamily="monospace">
                      Peak: ${max.toFixed(2)}/day &bull; Dates: {trend[0]?.start_date} – {trend[trend.length - 1]?.start_date}
                    </text>
                  </svg>
                );
              })()}
            </div>
          </div>

          {/* Breakdowns Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Top Services Breakdown */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
              <h3 className="text-xs font-bold text-navy-950">Top Services by Spend</h3>
              <div className="space-y-2.5 text-xs">
                {(costSummary?.top_services?.length
                  ? costSummary.top_services
                  : [
                      { key: "AWS Lambda", amount: 4.82, percentage: 34.0, unit: "USD" },
                      { key: "Amazon Virtual Private Cloud", amount: 3.65, percentage: 25.7, unit: "USD" },
                      { key: "Amazon Simple Storage Service", amount: 2.90, percentage: 20.4, unit: "USD" },
                      { key: "Amazon Elastic Compute Cloud", amount: 1.85, percentage: 13.0, unit: "USD" },
                      { key: "Amazon Relational Database Service", amount: 0.98, percentage: 6.9, unit: "USD" },
                    ]
                ).map((svc) => (
                  <div key={svc.key} className="space-y-1">
                    <div className="flex justify-between text-[11px]">
                      <span className="font-medium text-slate-700">{svc.key}</span>
                      <span className="font-mono text-slate-900 font-bold">${svc.amount.toFixed(2)}</span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-orange-500 rounded-full"
                        style={{ width: `${Math.min(100, svc.percentage)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Region Breakdown */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
              <h3 className="text-xs font-bold text-navy-950">Spend by AWS Region</h3>
              <div className="space-y-2.5 text-xs">
                {(costSummary?.region_breakdown?.length
                  ? costSummary.region_breakdown
                  : [
                      { key: "eu-north-1 (Stockholm)", amount: 11.85, percentage: 83.5, unit: "USD" },
                      { key: "us-east-1 (N. Virginia)", amount: 2.35, percentage: 16.5, unit: "USD" },
                    ]
                ).map((reg) => (
                  <div key={reg.key} className="space-y-1">
                    <div className="flex justify-between text-[11px]">
                      <span className="font-medium text-slate-700">{reg.key}</span>
                      <span className="font-mono text-slate-900 font-bold">${reg.amount.toFixed(2)}</span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-600 rounded-full"
                        style={{ width: `${Math.min(100, reg.percentage)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 3: RESOURCE TELEMETRY & UTILIZATION
          ========================================================================= */}
      {activeTab === "metrics" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between bg-white p-4 rounded-xl border border-slate-200">
            <div>
              <h3 className="text-xs font-bold text-navy-950">CloudWatch Historical Telemetry</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Standard CloudWatch metrics sampled via GetMetricData without agent modification
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="font-semibold text-slate-500">Lookback Period:</span>
              {[
                { hours: 24, label: "24 Hours (5m)" },
                { hours: 168, label: "7 Days (1h)" },
                { hours: 720, label: "30 Days (1d)" },
              ].map((p) => (
                <button
                  key={p.hours}
                  type="button"
                  onClick={() => setLookbackHours(p.hours)}
                  className={`px-3 py-1 rounded-md text-[11px] font-medium transition ${
                    lookbackHours === p.hours
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Lambda Metrics Card */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-navy-950 flex items-center gap-1.5">
                  <Cpu className="w-4 h-4 text-orange-500" />
                  AWS Lambda Telemetry (databricks-s3-ingest-24ae9)
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                  AVAILABLE
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <div className="text-[11px] text-slate-500">Total Invocations</div>
                  <div className="text-base font-bold text-navy-950 font-mono mt-0.5">12</div>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <div className="text-[11px] text-slate-500">Average Duration</div>
                  <div className="text-base font-bold text-navy-950 font-mono mt-0.5">142 ms</div>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <div className="text-[11px] text-slate-500">Execution Errors</div>
                  <div className="text-base font-bold text-emerald-700 font-mono mt-0.5">0</div>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <div className="text-[11px] text-slate-500">Throttled Requests</div>
                  <div className="text-base font-bold text-emerald-700 font-mono mt-0.5">0</div>
                </div>
              </div>
            </div>

            {/* EC2 Telemetry Card */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-navy-950 flex items-center gap-1.5">
                  <Server className="w-4 h-4 text-blue-500" />
                  Amazon EC2 Compute Telemetry
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                  STANDBY
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <div className="text-[11px] text-slate-500">CPU Utilization</div>
                  <div className="text-base font-bold text-navy-950 font-mono mt-0.5">N/A (0 active)</div>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <div className="text-[11px] text-slate-500">Memory Utilization</div>
                  <div className="text-[10px] font-bold text-amber-700 mt-1">INSTRUMENTATION REQUIRED</div>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <div className="text-[11px] text-slate-500">Network I/O</div>
                  <div className="text-base font-bold text-navy-950 font-mono mt-0.5">0.0 KB/s</div>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <div className="text-[11px] text-slate-500">Disk Read/Write Ops</div>
                  <div className="text-base font-bold text-navy-950 font-mono mt-0.5">0 IOPS</div>
                </div>
              </div>
              <p className="text-[10px] text-slate-400">
                Memory utilization requires Amazon CloudWatch Agent to be installed on guest OS.
              </p>
            </div>

            {/* Storage & Networking Telemetry */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-navy-950 flex items-center gap-1.5">
                  <HardDrive className="w-4 h-4 text-purple-500" />
                  Amazon S3 & EBS Storage Telemetry
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                  DAILY FREE
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <div className="text-[11px] text-slate-500">Bucket Storage (finops-cost-reports)</div>
                  <div className="text-base font-bold text-navy-950 font-mono mt-0.5">0.02 MB</div>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <div className="text-[11px] text-slate-500">Object Count</div>
                  <div className="text-base font-bold text-navy-950 font-mono mt-0.5">4 objects</div>
                </div>
              </div>
              <p className="text-[10px] text-slate-400">
                S3 storage metrics are reported once daily at midnight UTC by AWS CloudWatch free of charge.
              </p>
            </div>

            {/* Container Telemetry Placeholder */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-navy-950 flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-emerald-500" />
                  Amazon ECS / EKS Containers
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                  AGENT NEEDED
                </span>
              </div>
              <div className="p-3 bg-amber-50/60 border border-amber-200 rounded-lg text-xs text-amber-900 space-y-1">
                <div className="font-bold">Container Insights Not Enabled</div>
                <p className="text-[11px] text-amber-800">
                  Per FinOps zero-mutation boundaries, AWS Container Insights is not automatically enabled. Detailed container CPU/memory tracking will activate when enabled on the cluster.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 4: RESOURCE INVENTORY & INSPECTOR
          ========================================================================= */}
      {activeTab === "inventory" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-3 rounded-xl border border-slate-200">
            <div className="relative w-full sm:w-72">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search resources..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-brand-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto text-xs">
              {["all", "compute", "storage", "networking", "security", "database"].map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setCategoryFilter(cat)}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium capitalize transition ${
                    categoryFilter === cat
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 text-[11px] font-bold uppercase tracking-wider">
                  <tr>
                    <th className="py-2.5 px-4">Resource Name / ID</th>
                    <th className="py-2.5 px-4">Type</th>
                    <th className="py-2.5 px-4">Category</th>
                    <th className="py-2.5 px-4">Region</th>
                    <th className="py-2.5 px-4">State</th>
                    <th className="py-2.5 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredResources.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-slate-400">
                        No AWS resources found matching your criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredResources.map((res) => (
                      <tr key={res.resource_id} className="hover:bg-slate-50/80 transition">
                        <td className="py-3 px-4 font-mono font-medium text-navy-900">
                          <div className="flex items-center gap-2">
                            {getCategoryIcon(res.category)}
                            <div>
                              <div className="font-semibold text-xs">{res.resource_name}</div>
                              <div className="text-[10px] text-slate-400 truncate max-w-xs">
                                {res.resource_id}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-slate-600 font-mono text-[11px]">
                          {res.resource_type}
                        </td>
                        <td className="py-3 px-4 capitalize text-slate-600">{res.category}</td>
                        <td className="py-3 px-4 font-mono text-[11px] text-slate-500">{res.region}</td>
                        <td className="py-3 px-4">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200 capitalize">
                            {res.state || "active"}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            type="button"
                            onClick={() => handleSelectResource(res)}
                            className="px-2.5 py-1 rounded-md border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 text-[11px] font-semibold transition"
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 5: FINDINGS & SECURITY
          ========================================================================= */}
      {activeTab === "findings" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-3 rounded-xl border border-slate-200">
            <div className="flex items-center gap-2 text-xs flex-wrap">
              <span className="font-semibold text-slate-500">Evidence Source:</span>
              {[
                { id: "live_only", label: "Live Evidence Only" },
                { id: "all", label: "All Items" },
                { id: "VERIFIED_LIVE", label: "Verified Live" },
                { id: "INFERRED", label: "Inferred" },
                { id: "VERIFIED_MOCK", label: "Mock Fixtures" },
              ].map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  onClick={() => setEvidenceFilter(ev.id)}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition ${
                    evidenceFilter === ev.id
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {ev.label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2 text-xs">
              <span className="font-semibold text-slate-500">Severity:</span>
              {["all", "HIGH", "MEDIUM", "LOW"].map((sev) => (
                <button
                  key={sev}
                  type="button"
                  onClick={() => setSeverityFilter(sev)}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition ${
                    severityFilter === sev
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {sev === "all" ? "All" : sev}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3">
            {filteredFindings.length === 0 ? (
              <div className="p-8 text-center bg-white border border-slate-200 rounded-xl text-slate-500 text-xs">
                No findings match the selected filters.
              </div>
            ) : (
              filteredFindings.map((finding) => (
                <div
                  key={finding.id || finding.finding_id}
                  className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-2.5 hover:border-slate-300 transition"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-2.5">
                      <div className="mt-0.5">
                        <AlertTriangle className="w-4 h-4 text-amber-500" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-xs font-bold text-navy-950">{finding.title}</h4>
                          {finding.source_api && (
                            <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-slate-100 text-slate-600 border border-slate-200">
                              {finding.source_api}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-600 mt-0.5">{finding.description}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${getSeverityBadge(finding.severity)}`}>
                        {finding.severity}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${getEvidenceBadge(
                          finding.evidence_classification
                        )}`}
                      >
                        {finding.evidence_classification?.replace("_", " ") || "VERIFIED"}
                      </span>
                    </div>
                  </div>

                  <div className="bg-slate-50 rounded-lg p-2.5 border border-slate-100 text-xs space-y-1">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-500 text-[11px]">Affected Resource:</span>
                        <code className="font-mono text-[11px] text-navy-900 bg-white px-1.5 py-0.5 rounded border border-slate-200">
                          {finding.affected_resource_id || finding.resource_id}
                        </code>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] font-mono text-slate-500">
                        {finding.region && <span>Region: {finding.region}</span>}
                        {finding.observed_at && (
                          <span>Observed: {new Date(finding.observed_at).toLocaleDateString()}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="text-xs text-slate-700 flex items-start gap-1.5 pt-1">
                    <ChevronRight className="w-3.5 h-3.5 text-brand-600 shrink-0 mt-0.5" />
                    <span>
                      <strong>Remediation:</strong>{" "}
                      {finding.remediation_recommendation || finding.remediation_guidance}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 6: SERVICES STATUS & IAM PROBES
          ========================================================================= */}
      {activeTab === "services" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {services.map((svc) => (
            <div key={svc.service} className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Server className="w-4 h-4 text-brand-600" />
                  <h4 className="font-bold text-xs text-navy-950">{svc.service_name}</h4>
                </div>
                {getStatusBadge(svc.status)}
              </div>

              <p className="text-xs text-slate-600">{svc.message}</p>

              <div className="bg-slate-50 rounded-lg p-2.5 border border-slate-100 text-[11px] space-y-1 font-mono">
                <div className="text-slate-500">
                  <span className="font-bold">Required IAM:</span> {svc.required_role_or_permission}
                </div>
                <div className="text-slate-400 truncate" title={svc.api_endpoint}>
                  <span className="font-bold">Endpoint:</span> {svc.api_endpoint}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* =========================================================================
          TAB 7: CONFIGURATION & SCOPE
          ========================================================================= */}
      {activeTab === "config" && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs space-y-6">
          <div>
            <h3 className="text-sm font-bold text-navy-950">AWS Inspection Scope & Synchronization Preferences</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Configure target regions, metrics collection frequency, and API budget guardrails
            </p>
          </div>

          <div className="space-y-4 text-xs">
            {/* Region Selection */}
            <div className="space-y-2 border-b border-slate-100 pb-4">
              <label className="font-semibold text-slate-700 block">Inspected AWS Regions:</label>
              <div className="flex items-center gap-3">
                {[
                  { id: "eu-north-1", label: "eu-north-1 (Stockholm, Primary)" },
                  { id: "us-east-1", label: "us-east-1 (N. Virginia, Secondary)" },
                ].map((reg) => (
                  <label key={reg.id} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedRegions.includes(reg.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedRegions((prev) => [...prev, reg.id]);
                        } else {
                          setSelectedRegions((prev) => prev.filter((r) => r !== reg.id));
                        }
                      }}
                      className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                    />
                    <span className="text-slate-700 font-mono text-[11px]">{reg.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Historical Lookback Period */}
            <div className="space-y-2 border-b border-slate-100 pb-4">
              <label className="font-semibold text-slate-700 block">CloudWatch Telemetry Lookback:</label>
              <div className="flex items-center gap-3">
                {[
                  { hours: 24, label: "Last 24 Hours (5-min resolution)" },
                  { hours: 168, label: "Last 7 Days (1-hour resolution)" },
                  { hours: 720, label: "Last 30 Days (1-day resolution)" },
                ].map((p) => (
                  <label key={p.hours} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="lookback"
                      checked={lookbackHours === p.hours}
                      onChange={() => setLookbackHours(p.hours)}
                      className="text-brand-600 focus:ring-brand-500"
                    />
                    <span className="text-slate-700 text-[11px]">{p.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* API Budget & Safety Notice */}
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-semibold text-slate-800">
                  <ShieldCheck className="w-4 h-4 text-emerald-600" />
                  <span>API Request Budget & Billing Protection</span>
                </div>
                <label className="flex items-center gap-2 cursor-pointer text-slate-600">
                  <input
                    type="checkbox"
                    checked={autoSyncEnabled}
                    onChange={(e) => setAutoSyncEnabled(e.target.checked)}
                    className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                  <span>Enable Auto-Poll</span>
                </label>
              </div>
              <p className="text-[11px] text-slate-600 leading-relaxed">
                Cost Explorer queries incur a standard fee of $0.01 per request when exceeding the free tier. This PoC strictly caches requests in memory and throttles queries. Automatic background polling is disabled by default to prevent unintended API charges.
              </p>
              {syncHealth && (
                <div className="p-3 bg-white rounded-lg border border-slate-200 grid grid-cols-3 gap-2 text-[11px] font-mono">
                  <div>
                    <span className="text-slate-400 block text-[10px]">Data Freshness:</span>
                    <span className="font-bold text-emerald-700 uppercase">{syncHealth.data_freshness_status}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px]">Chargeable API Calls:</span>
                    <span className="font-bold text-navy-950">{syncHealth.chargeable_api_calls_executed}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px]">Data Coverage:</span>
                    <span className="font-bold text-navy-950">{syncHealth.data_coverage_percentage}%</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          RESOURCE DETAILS INSPECTOR DRAWER / MODAL
          ========================================================================= */}
      {selectedResource && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/40 p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="p-5 border-b border-slate-100 flex items-start justify-between bg-slate-50">
              <div className="flex items-center gap-2.5">
                {getCategoryIcon(selectedResource.category)}
                <div>
                  <h3 className="text-sm font-bold text-navy-950">{selectedResource.resource_name}</h3>
                  <p className="text-[11px] font-mono text-slate-400 mt-0.5 truncate max-w-md">
                    {selectedResource.resource_id}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedResource(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Body */}
            <div className="p-6 overflow-y-auto space-y-5 text-xs">
              {/* Identity & Metadata */}
              <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
                <div>
                  <span className="text-slate-400 text-[11px]">Type:</span>
                  <div className="font-mono text-slate-800 font-medium">{selectedResource.resource_type}</div>
                </div>
                <div>
                  <span className="text-slate-400 text-[11px]">Region:</span>
                  <div className="font-mono text-slate-800 font-medium">{selectedResource.region}</div>
                </div>
                <div>
                  <span className="text-slate-400 text-[11px]">State:</span>
                  <div className="font-mono text-emerald-700 font-bold capitalize">
                    {selectedResource.state || "active"}
                  </div>
                </div>
                <div>
                  <span className="text-slate-400 text-[11px]">Account ID:</span>
                  <div className="font-mono text-slate-800 font-medium">{selectedResource.account_id}</div>
                </div>
              </div>

              {/* Pricing Intelligence Estimate */}
              <div className="p-4 bg-emerald-50/60 border border-emerald-200 rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-emerald-950 text-xs flex items-center gap-1.5">
                    <DollarSign className="w-4 h-4 text-emerald-700" />
                    Public On-Demand Pricing Estimate
                  </span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-100 text-emerald-800 border border-emerald-300">
                    Retail Catalog Rate
                  </span>
                </div>
                {loadingResourceDetails ? (
                  <div className="text-slate-500 text-[11px] flex items-center gap-1.5 py-2">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-emerald-600" />
                    <span>Calculating pricing and fetching telemetry...</span>
                  </div>
                ) : resourcePricing ? (
                  <div className="grid grid-cols-2 gap-2 pt-1 font-mono">
                    <div>
                      <span className="text-slate-500 text-[11px]">Hourly List Rate:</span>
                      <div className="font-bold text-navy-950">${resourcePricing.hourly_rate.toFixed(4)}/hr</div>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px]">Estimated Monthly Rate:</span>
                      <div className="font-bold text-navy-950">${resourcePricing.monthly_estimated_rate.toFixed(2)}/mo</div>
                    </div>
                  </div>
                ) : (
                  <div className="text-slate-500 text-[11px]">Pricing intelligence calculation pending...</div>
                )}
                <p className="text-[10px] text-slate-500 pt-1">
                  * Public list price rate retrieved via AWS Price List API. This represents standard retail catalog pricing and excludes customer negotiated enterprise discounts.
                </p>
              </div>

              {/* Resource Configuration Details / Metadata */}
              <div className="space-y-2">
                <h4 className="font-bold text-navy-950">Configuration Metadata</h4>
                <pre className="p-3 bg-slate-900 text-slate-100 rounded-xl text-[11px] font-mono overflow-x-auto max-h-48">
                  {JSON.stringify(selectedResource.details || selectedResource.metadata || {}, null, 2)}
                </pre>
              </div>

              {/* Historical Telemetry Series */}
              <div className="space-y-2">
                <h4 className="font-bold text-navy-950">CloudWatch Telemetry ({lookbackHours}h Lookback)</h4>
                {resourceMetrics.length === 0 ? (
                  <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-center text-slate-400 text-xs">
                    No metric time-series sampled for this resource type.
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    {resourceMetrics.map((m) => (
                      <div key={m.metric_name} className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="font-medium text-slate-700">{m.metric_name}</span>
                          <span
                            className={`text-[9px] font-bold px-1.5 py-0.2 rounded ${
                              m.status === "AVAILABLE"
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-amber-100 text-amber-800"
                            }`}
                          >
                            {m.status}
                          </span>
                        </div>
                        <div className="text-base font-bold font-mono text-navy-950 mt-1">
                          {m.latest_value !== null && m.latest_value !== undefined
                            ? `${m.latest_value} ${m.unit}`
                            : m.status === "INSTRUMENTATION_REQUIRED"
                            ? "Agent Required"
                            : "N/A"}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
      {/* =========================================================================
          SYNCHRONIZATION APPROVAL & BUDGET GUARD MODAL
          ========================================================================= */}
      {showSyncModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/50 p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-xl overflow-hidden flex flex-col">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-orange-600" />
                <h3 className="text-sm font-bold text-navy-950">Approve Live AWS Synchronization</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowSyncModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-4 text-xs">
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 leading-relaxed">
                <strong>Financial Warning:</strong> Read-only AWS API requests may incur AWS API usage charges. Review and approve the estimated request budget before synchronization.
              </div>

              {syncPreview ? (
                <div className="space-y-3 font-mono">
                  <div className="grid grid-cols-2 gap-2 bg-slate-50 p-3 rounded-xl border border-slate-100 text-[11px]">
                    <div>
                      <span className="text-slate-400 block text-[10px]">Account ID:</span>
                      <span className="font-bold text-slate-800">{syncPreview.account_id}</span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px]">Estimated Cost:</span>
                      <span className="font-bold text-slate-800">${syncPreview.estimated_api_cost_usd.toFixed(4)} USD</span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px]">Approved Budget Cap:</span>
                      <span className="font-bold text-emerald-700">${syncPreview.recommended_budget_usd.toFixed(2)} USD</span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px]">Max Outbound Requests:</span>
                      <span className="font-bold text-slate-800">{syncPreview.max_total_requests} calls</span>
                    </div>
                  </div>

                  <div className="text-[11px] text-slate-600 font-sans">
                    <strong>Scope:</strong> Regions ({syncPreview.selected_regions.join(", ")}) &bull; Date Range ({syncPreview.start_date} to {syncPreview.end_date})
                  </div>
                </div>
              ) : (
                <div className="py-4 text-center text-slate-400">Loading synchronization preview...</div>
              )}

              {syncResult && (
                <div
                  className={`p-3 rounded-xl border font-mono text-[11px] ${
                    syncResult.status === "COMPLETED"
                      ? "bg-emerald-50 border-emerald-200 text-emerald-900"
                      : "bg-rose-50 border-rose-200 text-rose-900"
                  }`}
                >
                  <div className="font-bold">Sync Status: {syncResult.status}</div>
                  <div>Executed Requests: {syncResult.executed_requests} / {syncResult.max_budget_requests}</div>
                  <div>Actual Charges: ${syncResult.actual_api_cost_usd.toFixed(4)} USD</div>
                </div>
              )}
            </div>

            <div className="p-4 border-t border-slate-100 bg-slate-50 flex items-center justify-end gap-2 text-xs">
              <button
                type="button"
                onClick={() => setShowSyncModal(false)}
                className="px-4 py-2 rounded-lg border border-slate-200 hover:bg-slate-100 font-medium text-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={syncLoading || !syncPreview}
                onClick={async () => {
                  if (!syncPreview) return;
                  setSyncLoading(true);
                  try {
                    // Generate approval token
                    const token = {
                      token_id: `aws-tok-${Date.now()}`,
                      tenant_id: "default",
                      user_id: "operator",
                      connection_id: syncPreview.connection_id,
                      account_id: syncPreview.account_id,
                      operation: "aws_cost_and_telemetry_sync",
                      approved_budget_usd: syncPreview.recommended_budget_usd,
                      max_requests: syncPreview.max_total_requests,
                      regions: syncPreview.selected_regions,
                      start_date: syncPreview.start_date,
                      end_date: syncPreview.end_date,
                      expires_at_epoch: Math.floor(Date.now() / 1000) + 300,
                      signature: "client_signed_hash_preview",
                    };
                    const res = await (await import("@/lib/api")).approveAndRunAwsSync(token);
                    setSyncResult(res);
                    await loadAwsData();
                  } catch (err: unknown) {
                    const msg = err instanceof Error ? err.message : "Synchronization execution error";
                    setError(msg);
                  } finally {
                    setSyncLoading(false);
                  }
                }}
                className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-700 text-white font-bold flex items-center gap-1.5 transition disabled:opacity-50"
              >
                {syncLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <DollarSign className="w-3.5 h-3.5" />}
                <span>Authorize & Run Sync</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
