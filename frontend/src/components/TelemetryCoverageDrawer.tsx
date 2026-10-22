"use client";

import React, { useState, useMemo, useEffect } from "react";
import {
  CloudProvider,
  MonitoringOverviewResponse,
  ResourceHealthRecord,
} from "@/types";
import {
  X,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Search,
  ShieldCheck,
  Terminal,
  FileText,
  Clock,
} from "lucide-react";

interface TelemetryCoverageDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  overview: MonitoringOverviewResponse | null;
  provider: CloudProvider;
  scopeId: string;
  scopeName: string;
}

interface ResourceCoverageItem {
  id: string;
  name: string;
  type: string;
  group: string;
  isEligible: boolean;
  isMonitored: boolean;
  healthState: string;
  telemetrySource: string;
  lastChecked: Date;
  reason: string;
}

export const TelemetryCoverageDrawer: React.FC<TelemetryCoverageDrawerProps> = ({
  isOpen,
  onClose,
  overview,
  provider,
  scopeId,
  scopeName,
}) => {
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [filterTab, setFilterTab] = useState<
    "all" | "monitored" | "unmonitored" | "eligible" | "ineligible"
  >("all");

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Helper to extract resource group or namespace from resource identifier
  const extractGroup = (resId: string): string => {
    const rgMatch = resId.match(/resource[Gg]roups\/([^/]+)/);
    if (rgMatch) return rgMatch[1];
    const projectMatch = resId.match(/projects\/([^/]+)/);
    if (projectMatch) return projectMatch[1];
    return "Global Scope";
  };

  // Compute coverage analytics and classify eligibility
  const coverageData = useMemo(() => {
    if (!overview || !overview.health_records) {
      return {
        totalResources: 0,
        eligibleCount: 0,
        monitoredCount: 0,
        unmonitoredCount: 0,
        ineligibleCount: 0,
        coveragePct: "0.00",
        isKnown: false,
        items: [] as ResourceCoverageItem[],
      };
    }

    const items: ResourceCoverageItem[] = overview.health_records.map(
      (r: ResourceHealthRecord) => {
        const nativeType = r.native_type || "";
        const isApi =
          r.resource_kind === "api_service" ||
          nativeType.toLowerCase().includes("serviceusage.googleapis.com");
        const isConfig =
          r.resource_kind === "configuration_metadata" ||
          r.resource_kind === "security_credential" ||
          nativeType.startsWith("Microsoft.Features/");

        // Ineligible resources are pure API registrations or configuration metadata records
        const isEligible = !isApi && !isConfig;

        const isMonitored =
          isEligible && r.health_state !== "unmonitored";

        let reason = r.reason || r.summary || "";
        if (!isEligible) {
          reason = isApi
            ? "API Service Activation (no operational metrics emitted)"
            : "Configuration Metadata / Policy (not an operational workload)";
        } else if (!isMonitored) {
          reason =
            reason ||
            "Missing diagnostic settings or metric streaming sink not routed";
        } else {
          reason =
            reason || "Streaming active metrics to provider telemetry store";
        }

        return {
          id: r.resource_id,
          name: r.resource_name,
          type: nativeType,
          group: extractGroup(r.resource_id),
          isEligible,
          isMonitored,
          healthState: r.health_state,
          telemetrySource:
            r.telemetry_source ||
            (overview.is_live
              ? "Provider Metrics REST API"
              : "Verified Benchmark Telemetry"),
          lastChecked: new Date(r.last_checked || overview.query_timestamp),
          reason,
        };
      }
    );

    const eligible = items.filter((i) => i.isEligible);
    const monitored = eligible.filter((i) => i.isMonitored);
    const unmonitored = eligible.filter((i) => !i.isMonitored);
    const ineligible = items.filter((i) => !i.isEligible);

    const isKnown = overview.is_live || overview.data_source === "mock_fixture";
    const coveragePct =
      eligible.length > 0
        ? ((monitored.length / eligible.length) * 100).toFixed(1)
        : isKnown
        ? "100.0"
        : "N/A";

    return {
      totalResources: items.length,
      eligibleCount: eligible.length,
      monitoredCount: monitored.length,
      unmonitoredCount: unmonitored.length,
      ineligibleCount: ineligible.length,
      coveragePct,
      isKnown,
      items,
    };
  }, [overview]);

  // Filter and search items
  const filteredItems = useMemo(() => {
    let result = coverageData.items;

    if (filterTab === "monitored") {
      result = result.filter((i) => i.isMonitored);
    } else if (filterTab === "unmonitored") {
      result = result.filter((i) => i.isEligible && !i.isMonitored);
    } else if (filterTab === "eligible") {
      result = result.filter((i) => i.isEligible);
    } else if (filterTab === "ineligible") {
      result = result.filter((i) => !i.isEligible);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (i) =>
          i.name.toLowerCase().includes(q) ||
          i.type.toLowerCase().includes(q) ||
          i.group.toLowerCase().includes(q) ||
          i.reason.toLowerCase().includes(q)
      );
    }

    return result;
  }, [coverageData.items, filterTab, searchQuery]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden bg-slate-900/60 backdrop-blur-xs flex justify-end transition-opacity"
      role="dialog"
      aria-modal="true"
      aria-labelledby="coverage-drawer-title"
    >
      {/* Click outside backdrop */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Drawer Panel */}
      <div className="relative w-full max-w-3xl bg-white shadow-2xl h-full flex flex-col z-10 overflow-hidden border-l border-slate-200">
        {/* Drawer Header */}
        <div className="p-5 border-b border-slate-200 bg-slate-50/80 flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-8 h-8 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center shrink-0">
                <Activity className="w-4 h-4" />
              </span>
              <div>
                <h3
                  id="coverage-drawer-title"
                  className="text-base font-bold text-navy-950 tracking-tight"
                >
                  Telemetry Coverage &amp; Monitoring Readiness Audit
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Detailed inspection of monitored vs. unmonitored resources across scope.
                </p>
              </div>
            </div>

            {/* Scope & Provenance Badges */}
            <div className="flex flex-wrap items-center gap-2 mt-3 text-xs">
              <span className="font-mono text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200 font-semibold">
                {provider.toUpperCase()}: {scopeName || scopeId}
              </span>
              <span
                className={`px-2 py-0.5 rounded-full font-semibold border ${
                  overview?.is_live
                    ? "bg-emerald-50 text-emerald-700 border-emerald-300"
                    : "bg-amber-50 text-amber-700 border-amber-300"
                }`}
              >
                {overview?.is_live ? "Live Authenticated API" : "Verified Benchmark Telemetry"}
              </span>
              {overview?.query_timestamp && (
                <span className="text-slate-400 text-[11px] flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  <span>
                    Last Polled:{" "}
                    {new Date(overview.query_timestamp).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </span>
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close telemetry coverage drawer"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/80 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs">
          {/* 1. Summary KPI Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
              <div className="text-[11px] text-slate-500 font-medium">Eligible Workloads</div>
              <div className="text-xl font-bold text-navy-900 mt-0.5">
                {coverageData.eligibleCount}
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                Exclude {coverageData.ineligibleCount} metadata entries
              </div>
            </div>

            <div className="p-3 bg-emerald-50/60 rounded-xl border border-emerald-200">
              <div className="text-[11px] text-emerald-700 font-medium">Actively Monitored</div>
              <div className="text-xl font-bold text-emerald-800 mt-0.5">
                {coverageData.monitoredCount}
              </div>
              <div className="text-[10px] text-emerald-600 mt-0.5">Streaming metric points</div>
            </div>

            <div className="p-3 bg-amber-50/60 rounded-xl border border-amber-200">
              <div className="text-[11px] text-amber-700 font-medium">Unmonitored Gaps</div>
              <div className="text-xl font-bold text-amber-800 mt-0.5">
                {coverageData.unmonitoredCount}
              </div>
              <div className="text-[10px] text-amber-600 mt-0.5">Missing diagnostic settings</div>
            </div>

            <div className="p-3 bg-blue-50/60 rounded-xl border border-blue-200">
              <div className="text-[11px] text-blue-700 font-medium">Effective Coverage</div>
              <div className="text-xl font-bold text-blue-800 mt-0.5">
                {coverageData.isKnown ? `${coverageData.coveragePct}%` : "Unknown"}
              </div>
              <div className="text-[10px] text-blue-600 mt-0.5">
                {coverageData.isKnown ? "Mathematical ratio" : "Unprobed scope"}
              </div>
            </div>
          </div>

          {/* 2. Coverage Formula & Methodology Explanation */}
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
            <div className="flex items-center gap-1.5 font-bold text-navy-900 uppercase tracking-wider text-[11px]">
              <FileText className="w-3.5 h-3.5 text-blue-600" />
              <span>Coverage Formula &amp; Mathematical Definition</span>
            </div>
            <div className="bg-white p-2.5 rounded-lg border border-slate-200 font-mono text-[11px] text-navy-950 flex flex-wrap items-center justify-between gap-2">
              <span>
                Coverage (%) = (Monitored Eligible Resources / Total Eligible Resources) &times; 100
              </span>
              <span className="font-bold text-blue-700">
                {coverageData.monitoredCount} / {coverageData.eligibleCount} = {coverageData.coveragePct}%
              </span>
            </div>
            <p className="text-[11px] text-slate-600 leading-relaxed">
              <strong>Denominator Exclusivity:</strong> The denominator strictly counts provisioned infrastructure workloads (Compute, App Services, Databases, Managed Disks, and AI services) capable of emitting operational metrics. Pure API service declarations (e.g. <code className="font-mono text-[10px] bg-slate-100 px-1 py-0.5 rounded">serviceusage.googleapis.com</code>) and static configuration entries (<code className="font-mono text-[10px] bg-slate-100 px-1 py-0.5 rounded">Microsoft.Features/</code>) are classified as <em>Ineligible</em> so they never dilute the denominator.
            </p>
          </div>

          {/* 3. Provider Permission & Diagnostics Guide */}
          <div className="p-4 bg-indigo-50/50 border border-indigo-200 rounded-xl space-y-2 text-indigo-950">
            <div className="flex items-center gap-1.5 font-bold uppercase tracking-wider text-[11px] text-indigo-900">
              <Terminal className="w-3.5 h-3.5 text-indigo-600" />
              <span>Read-Only Telemetry Ingestion Guide</span>
            </div>
            <p className="text-[11px] text-indigo-900 leading-relaxed">
              {provider === "azure" ? (
                <>
                  Azure Monitor metrics require the <strong className="font-semibold">Monitoring Reader</strong> role over the subscription. Unmonitored resources lack active Diagnostic Settings routing metrics to a Log Analytics Workspace.
                </>
              ) : (
                <>
                  Google Cloud Monitoring requires <strong className="font-semibold">roles/monitoring.viewer</strong>. Ensure Cloud Logging export sinks are configured for full log stream coverage.
                </>
              )}
            </p>
            <div className="flex items-center gap-1.5 text-[10px] font-semibold text-emerald-700 bg-white/80 px-2.5 py-1.5 rounded-lg border border-emerald-200">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
              <span>Zero-Execution Policy: This tool is strictly read-only and will never modify customer subscriptions or configure sinks automatically.</span>
            </div>
          </div>

          {/* 4. Search and Filter Controls */}
          <div className="space-y-3 pt-2">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="relative flex-1">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  placeholder="Filter by resource name, type, or group..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full text-xs pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* Filter Tabs */}
              <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200 text-[11px] overflow-x-auto">
                <button
                  type="button"
                  onClick={() => setFilterTab("all")}
                  className={`px-2 py-0.5 rounded-md font-medium transition ${
                    filterTab === "all"
                      ? "bg-white text-navy-950 font-semibold shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  All ({coverageData.totalResources})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterTab("monitored")}
                  className={`px-2 py-0.5 rounded-md font-medium transition ${
                    filterTab === "monitored"
                      ? "bg-white text-emerald-700 font-semibold shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  Monitored ({coverageData.monitoredCount})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterTab("unmonitored")}
                  className={`px-2 py-0.5 rounded-md font-medium transition ${
                    filterTab === "unmonitored"
                      ? "bg-white text-amber-700 font-semibold shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  Unmonitored ({coverageData.unmonitoredCount})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterTab("eligible")}
                  className={`px-2 py-0.5 rounded-md font-medium transition ${
                    filterTab === "eligible"
                      ? "bg-white text-blue-700 font-semibold shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  Eligible ({coverageData.eligibleCount})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterTab("ineligible")}
                  className={`px-2 py-0.5 rounded-md font-medium transition ${
                    filterTab === "ineligible"
                      ? "bg-white text-slate-800 font-semibold shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  Ineligible ({coverageData.ineligibleCount})
                </button>
              </div>
            </div>

            {/* 5. Resource Table */}
            <div className="border border-slate-200 rounded-xl overflow-hidden bg-white shadow-2xs">
              <div className="overflow-x-auto max-h-96">
                <table className="w-full text-left border-collapse">
                  <thead className="bg-slate-50 text-[10px] text-slate-500 uppercase font-semibold sticky top-0 z-10 border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3">Resource &amp; Type</th>
                      <th className="py-2.5 px-3">Resource Group</th>
                      <th className="py-2.5 px-3">Eligibility</th>
                      <th className="py-2.5 px-3">Telemetry Status</th>
                      <th className="py-2.5 px-3">Diagnostic Observation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                    {filteredItems.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-slate-400 font-sans">
                          No resources matched the filter query.
                        </td>
                      </tr>
                    ) : (
                      filteredItems.map((item) => (
                        <tr key={item.id} className="hover:bg-slate-50/70 transition">
                          <td className="py-2.5 px-3 font-sans">
                            <div className="font-semibold text-navy-950 truncate max-w-xs" title={item.name}>
                              {item.name}
                            </div>
                            <div className="font-mono text-[10px] text-slate-400 truncate max-w-xs" title={item.type}>
                              {item.type}
                            </div>
                          </td>
                          <td className="py-2.5 px-3 font-sans text-slate-600">
                            {item.group}
                          </td>
                          <td className="py-2.5 px-3 font-sans">
                            {item.isEligible ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                                <CheckCircle2 className="w-2.5 h-2.5 text-blue-600" />
                                <span>Eligible Workload</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                                <span>Ineligible Metadata</span>
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-sans">
                            {item.isMonitored ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                <span>Monitored</span>
                              </span>
                            ) : item.isEligible ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                                <AlertTriangle className="w-2.5 h-2.5 text-amber-600" />
                                <span>Unmonitored Gap</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium text-slate-500">
                                <span>N/A (Metadata)</span>
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-sans text-slate-600 text-[10px] leading-relaxed max-w-xs">
                            {item.reason}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        {/* Drawer Footer */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
          <span className="text-[11px] text-slate-500">
            Showing {filteredItems.length} of {coverageData.totalResources} evaluated resources
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-navy-950 text-white font-semibold text-xs hover:bg-navy-900 transition"
          >
            Close Audit Drawer
          </button>
        </div>
      </div>
    </div>
  );
};
