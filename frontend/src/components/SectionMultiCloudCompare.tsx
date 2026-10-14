"use client";

import React, { useState } from "react";
import {
  MultiCloudComparisonRequest,
  MultiCloudComparisonResponse,
  WorkloadAssumptions,
  WorkloadCategory,
} from "@/types";
import { compareMultiCloud } from "@/lib/api";
import {
  Scale,
  RefreshCw,
  Sparkles,
  Layers,
  Database,
  Cpu,
  HardDrive,
  Network,
  Key,
  Info,
} from "lucide-react";
import { MermaidDiagram } from "@/components/MermaidDiagram";

interface SectionMultiCloudCompareProps {
  currentAssumptions: WorkloadAssumptions;
  currentBufferPct: string;
}

export function SectionMultiCloudCompare({
  currentAssumptions,
  currentBufferPct,
}: SectionMultiCloudCompareProps) {
  const [azureRegion, setAzureRegion] = useState<string>("eastus");
  const [gcpRegion, setGcpRegion] = useState<string>("us-central1");
  const [isComparing, setIsComparing] = useState<boolean>(false);
  const [comparison, setComparison] = useState<MultiCloudComparisonResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [selectedArchTab, setSelectedArchTab] = useState<"azure" | "gcp">("azure");

  const handleRunComparison = async () => {
    setIsComparing(true);
    setErrorMsg(null);
    try {
      const payload: MultiCloudComparisonRequest = {
        workload_profile: {
          name: "Smart Expense Platform",
          description: "Microservices platform with database, storage, AI, and edge routing",
          category: "web_app" as WorkloadCategory,
          target_traffic_rps: currentAssumptions.peak_rps,
          monthly_active_users: currentAssumptions.monthly_active_users,
          primary_region: azureRegion,
          cost_buffer_percentage: currentBufferPct,
        },
        workload_assumptions: {
          ...currentAssumptions,
          target_region: azureRegion,
        },
        azure_region: azureRegion,
        gcp_region: gcpRegion,
      };

      const res = await compareMultiCloud(payload);
      setComparison(res);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Multi-cloud comparison failed.");
    } finally {
      setIsComparing(false);
    }
  };

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

  return (
    <section className="mt-8 space-y-6">
      {/* Control Header */}
      <div className="rounded-2xl glass-card p-6 border border-slate-200/80 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200/80 uppercase tracking-wide">
                Multi-Cloud Comparison (Azure vs. GCP)
              </span>
              <span className="text-xs text-slate-400 font-mono">Architecture Parity &amp; Pricing</span>
            </div>
            <h2 className="text-xl font-bold text-slate-900 mt-1">
              Side-by-Side Architectural Alignment & Deterministic Cost Intelligence
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Identical workload scale, storage volume, and HA posture priced against official provider retail rates.
            </p>
          </div>

          <button
            type="button"
            onClick={handleRunComparison}
            disabled={isComparing}
            className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-xs font-semibold shadow-sm transition shrink-0"
          >
            {isComparing ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Pricing Both Clouds...</span>
              </>
            ) : (
              <>
                <Scale className="w-3.5 h-3.5" />
                <span>Compare Azure vs. GCP</span>
              </>
            )}
          </button>
        </div>

        {/* Region & Workload Context */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div>
            <label className="block text-[11px] font-medium text-slate-600 uppercase mb-1">
              Azure Target Region
            </label>
            <select
              value={azureRegion}
              onChange={(e) => setAzureRegion(e.target.value)}
              disabled={isComparing}
              className="w-full text-xs rounded-xl border border-slate-300 bg-white px-3 py-2 font-mono text-slate-800"
            >
              <option value="eastus">East US (eastus)</option>
              <option value="westus2">West US 2 (westus2)</option>
              <option value="westeurope">West Europe (westeurope)</option>
              <option value="centralindia">Central India (centralindia)</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-slate-600 uppercase mb-1">
              GCP Target Region
            </label>
            <select
              value={gcpRegion}
              onChange={(e) => setGcpRegion(e.target.value)}
              disabled={isComparing}
              className="w-full text-xs rounded-xl border border-slate-300 bg-white px-3 py-2 font-mono text-slate-800"
            >
              <option value="us-central1">Iowa (us-central1)</option>
              <option value="us-east1">South Carolina (us-east1)</option>
              <option value="europe-west1">Belgium (europe-west1)</option>
              <option value="asia-south1">Mumbai (asia-south1)</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-slate-600 uppercase mb-1">
              Current Workload Sizing Basis
            </label>
            <div className="p-2 rounded-xl bg-slate-50 border border-slate-200 font-mono text-[11px] text-slate-700">
              {currentAssumptions.customer_count.toLocaleString()} customers •{" "}
              {currentAssumptions.monthly_active_users.toLocaleString()} MAU •{" "}
              {currentAssumptions.peak_rps} RPS • {currentAssumptions.db_storage_gb} GB DB
            </div>
          </div>
        </div>

        {errorMsg && (
          <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700">
            {errorMsg}
          </div>
        )}
      </div>

      {/* Comparison Results */}
      {comparison && (
        <div className="space-y-6">
          {/* Executive Overview Banner */}
          <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-sm space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-100">
              <div className="space-y-1">
                <span className="text-[10px] font-semibold uppercase text-slate-400 font-mono">
                  Comparative Analysis Result
                </span>
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-bold text-slate-900">
                    Monthly Delta:{" "}
                    <span
                      className={
                        parseFloat(comparison.monthly_delta_gcp_minus_azure) < 0
                          ? "text-emerald-700"
                          : "text-blue-700"
                      }
                    >
                      {parseFloat(comparison.monthly_delta_gcp_minus_azure) < 0
                        ? `GCP is $${Math.abs(parseFloat(comparison.monthly_delta_gcp_minus_azure)).toFixed(2)}/mo lower`
                        : `Azure is $${Math.abs(parseFloat(comparison.monthly_delta_gcp_minus_azure)).toFixed(2)}/mo lower`}
                    </span>
                  </h3>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase ${
                      comparison.cheaper_provider === "gcp"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : "bg-blue-50 text-blue-700 border border-blue-200"
                    }`}
                  >
                    Lowest Estimate: {comparison.cheaper_provider?.toUpperCase()}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-6 font-mono text-xs">
                <div className="p-3 rounded-xl bg-blue-50/70 border border-blue-200 text-right">
                  <span className="text-[10px] text-blue-600 uppercase font-sans font-semibold block">
                    Azure Total ({azureRegion})
                  </span>
                  <span className="text-base font-bold text-blue-950">
                    ${parseFloat(comparison.azure_total_monthly).toFixed(2)}
                    <span className="text-xs font-normal text-blue-700">/mo</span>
                  </span>
                  <span className="text-[10px] text-blue-600 block">
                    ${parseFloat(comparison.azure_report.cost_breakdown.total_annual).toFixed(2)}/yr
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-emerald-50/70 border border-emerald-200 text-right">
                  <span className="text-[10px] text-emerald-600 uppercase font-sans font-semibold block">
                    GCP Total ({gcpRegion})
                  </span>
                  <span className="text-base font-bold text-emerald-950">
                    ${parseFloat(comparison.gcp_total_monthly).toFixed(2)}
                    <span className="text-xs font-normal text-emerald-700">/mo</span>
                  </span>
                  <span className="text-[10px] text-emerald-600 block">
                    ${parseFloat(comparison.gcp_report.cost_breakdown.total_annual).toFixed(2)}/yr
                  </span>
                </div>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              {comparison.trade_off_summary}
            </p>
          </div>

          {/* Side-by-Side Capability Alignment Table */}
          <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Architectural Capability Alignment & SKU Parity
                </h3>
                <p className="text-xs text-slate-500">
                  Detailed cost breakdown mapping equivalent cloud services across hyperscalers.
                </p>
              </div>
              <span className="text-xs font-mono text-slate-400">
                {comparison.service_mappings.length} capabilities aligned
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-100/70 text-[10px] uppercase text-slate-500 border-b border-slate-200 font-semibold font-mono">
                  <tr>
                    <th className="py-2.5 px-4">Architectural Capability</th>
                    <th className="py-2.5 px-3">Azure Service & SKU</th>
                    <th className="py-2.5 px-3 text-right">Azure Cost</th>
                    <th className="py-2.5 px-3">GCP Service & SKU</th>
                    <th className="py-2.5 px-3 text-right">GCP Cost</th>
                    <th className="py-2.5 px-3 text-right">Monthly Delta (GCP - Az)</th>
                    <th className="py-2.5 px-4">Billing Parity Notes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-sans">
                  {comparison.service_mappings.map((m, i) => {
                    const deltaNum = parseFloat(m.monthly_delta_gcp_minus_azure);
                    return (
                      <tr key={i} className="hover:bg-slate-50/60 transition">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            {getCategoryIcon(m.category)}
                            <span className="font-semibold text-slate-900">{m.capability}</span>
                          </div>
                        </td>

                        <td className="py-3 px-3">
                          <span className="font-semibold text-blue-900 block">
                            {m.azure_service_name}
                          </span>
                          <span className="text-[10px] font-mono text-slate-500">
                            {m.azure_sku}
                          </span>
                        </td>

                        <td className="py-3 px-3 text-right font-mono font-bold text-slate-900">
                          ${parseFloat(m.azure_monthly_cost).toFixed(2)}
                        </td>

                        <td className="py-3 px-3">
                          <span className="font-semibold text-emerald-900 block">
                            {m.gcp_service_name}
                          </span>
                          <span className="text-[10px] font-mono text-slate-500">
                            {m.gcp_sku}
                          </span>
                        </td>

                        <td className="py-3 px-3 text-right font-mono font-bold text-slate-900">
                          ${parseFloat(m.gcp_monthly_cost).toFixed(2)}
                        </td>

                        <td className="py-3 px-3 text-right font-mono font-bold">
                          <span
                            className={
                              deltaNum < 0
                                ? "text-emerald-700"
                                : deltaNum > 0
                                  ? "text-blue-700"
                                  : "text-slate-500"
                            }
                          >
                            {deltaNum > 0 ? `+$${deltaNum.toFixed(2)}` : `$${deltaNum.toFixed(2)}`}
                          </span>
                        </td>

                        <td className="py-3 px-4 text-slate-600 text-[11px] max-w-xs leading-snug">
                          {m.notes}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Architecture Topology Viewers (Azure vs GCP) */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Visual Architecture Topology Comparison
                </h3>
                <p className="text-xs text-slate-500">
                  Toggle between the Azure PaaS topology and equivalent GCP project architecture.
                </p>
              </div>

              <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg text-xs font-semibold">
                <button
                  type="button"
                  onClick={() => setSelectedArchTab("azure")}
                  className={`px-3 py-1 rounded-md transition ${
                    selectedArchTab === "azure"
                      ? "bg-white text-blue-700 shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  Azure Blueprint
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedArchTab("gcp")}
                  className={`px-3 py-1 rounded-md transition ${
                    selectedArchTab === "gcp"
                      ? "bg-white text-emerald-700 shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  GCP Blueprint
                </button>
              </div>
            </div>

            <div className="rounded-xl overflow-hidden">
              <MermaidDiagram
                chart={
                  selectedArchTab === "azure"
                    ? comparison.azure_report.mermaid_diagram
                    : comparison.gcp_report.mermaid_diagram
                }
                title={
                  selectedArchTab === "azure"
                    ? `Azure Cloud Blueprint (${azureRegion})`
                    : `GCP Equivalent Blueprint (${gcpRegion})`
                }
                provider={selectedArchTab === "azure" ? "azure" : "gcp"}
              />
            </div>
          </div>

          {/* Comparison Disclosures */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs space-y-2 text-slate-600">
            <div className="flex items-center gap-2 font-semibold text-slate-800">
              <Info className="w-4 h-4 text-slate-500" />
              <span>Multi-Cloud Sizing Assumptions & Scope Notes</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-[11px] text-slate-600">
              {comparison.comparison_assumptions.map((assump, i) => (
                <li key={i}>{assump}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
