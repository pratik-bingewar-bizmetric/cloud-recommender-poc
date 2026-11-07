"use client";

import React, { useState, useMemo } from "react";
import {
  CloudProvider,
  MonitoringOverviewResponse,
  SubscriptionOrProjectAnalysis,
  ResourceWasteFinding,
  TechnicalDebtItem,
} from "@/types";
import { FinancialKpiDrawer } from "@/components/FinancialKpiDrawer";
import { buildCanonicalFinancialSummary } from "@/lib/financials";
import { FinancialKpiType } from "@/types/financials";
import {
  TrendingDown,
  ShieldAlert,
  ArrowRight,
  X,
  RefreshCw,
  DollarSign,
  Layers,
  ChevronRight,
  AlertCircle,
  Copy,
  Check,
  Zap,
} from "lucide-react";

interface SectionCostWasteProps {
  provider: CloudProvider;
  scopeId: string;
  scopeName: string;
  overview: MonitoringOverviewResponse | null;
  analysisData: SubscriptionOrProjectAnalysis | null;
  isLoading: boolean;
  onRefresh: () => void;
  onInspectResource?: (resourceId: string) => void;
}

export const SectionCostWaste: React.FC<SectionCostWasteProps> = ({
  provider,
  scopeId,
  scopeName,
  overview,
  analysisData,
  isLoading,
  onRefresh,
  onInspectResource,
}) => {
  const [selectedFinding, setSelectedFinding] = useState<ResourceWasteFinding | null>(null);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>("all");

  const [financialDrawerKpi, setFinancialDrawerKpi] =
    useState<FinancialKpiType | null>(null);
  const [drillFindingId, setDrillFindingId] = useState<string | null>(null);

  const canonicalFinancials = useMemo(() => {
    return buildCanonicalFinancialSummary(
      provider,
      scopeId || scopeName || "",
      scopeName || scopeId || "",
      "30d",
      "USD",
      overview,
      analysisData
    );
  }, [provider, scopeId, scopeName, overview, analysisData]);

  const monthlySpend = canonicalFinancials.estimated_monthly_spend;
  const monthlySavings = canonicalFinancials.potential_monthly_savings;
  const annualSavings = canonicalFinancials.projected_annual_savings;

  const rawFindings: ResourceWasteFinding[] =
    analysisData?.waste_findings && analysisData.waste_findings.length > 0
      ? analysisData.waste_findings
      : [];

  const techDebtItems: TechnicalDebtItem[] =
    analysisData?.technical_debt_items && analysisData.technical_debt_items.length > 0
      ? analysisData.technical_debt_items
      : [];

  // Filtered findings
  const filteredFindings = rawFindings.filter((f) => {
    if (categoryFilter === "all") return true;
    return f.category.toLowerCase().includes(categoryFilter.toLowerCase());
  });

  // Calculate waste categories for distribution chart
  const categoryTotals = rawFindings.reduce((acc, f) => {
    const cat = f.category || "General Waste";
    acc[cat] = (acc[cat] || 0) + parseFloat(f.potential_monthly_savings.toString());
    return acc;
  }, {} as Record<string, number>);

  const handleCopyCode = (text: string, index: number) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 2000);
    }
  };

  const getInspectionCommand = (finding: ResourceWasteFinding, p: CloudProvider) => {
    if (finding.category === "unattached_storage") {
      return p === "gcp"
        ? `gcloud compute disks describe ${finding.resource_name} --format="yaml(status,users,lastAttachTimestamp)"`
        : `az disk show --ids "${finding.resource_id}" --query "{name:name, diskState:diskState, timeCreated:timeCreated}"`;
    }
    if (finding.category === "unattached_ip") {
      return p === "gcp"
        ? `gcloud compute addresses describe ${finding.resource_name} --format="yaml(status,users,address)"`
        : `az network public-ip show --ids "${finding.resource_id}" --query "{name:name, ipAddress:ipAddress, ipConfiguration:ipConfiguration}"`;
    }
    if (finding.category.includes("compute")) {
      return p === "gcp"
        ? `gcloud compute instances describe ${finding.resource_name} --format="yaml(status,machineType,disks)"`
        : `az vm get-instance-view --ids "${finding.resource_id}" --query "instanceView.statuses"`;
    }
    return p === "gcp"
      ? `gcloud asset search-all-resources --query="name:${finding.resource_name}"`
      : `az resource show --ids "${finding.resource_id}"`;
  };

  const getRemediationCommand = (finding: ResourceWasteFinding, p: CloudProvider) => {
    if (finding.category === "unattached_storage") {
      return p === "gcp"
        ? `gcloud compute disks delete ${finding.resource_name} --quiet`
        : `az disk delete --ids "${finding.resource_id}" --yes`;
    }
    if (finding.category === "unattached_ip") {
      return p === "gcp"
        ? `gcloud compute addresses delete ${finding.resource_name} --quiet`
        : `az network public-ip delete --ids "${finding.resource_id}"`;
    }
    if (finding.category === "idle_compute" || finding.category === "stopped_compute") {
      return p === "gcp"
        ? `gcloud compute instances stop ${finding.resource_name}`
        : `az vm deallocate --ids "${finding.resource_id}"`;
    }
    return p === "gcp"
      ? `# Review resource tags and usage in GCP Console before manual modification`
      : `# Review resource in Azure Portal before manual modification`;
  };

  return (
    <div className="space-y-6">
      {/* 1. Header Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-white border border-slate-200 rounded-2xl shadow-xs">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-navy-950 font-heading">
              Cost &amp; FinOps Waste Intelligence
            </h3>
            <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase bg-emerald-50 text-emerald-700 border border-emerald-200">
              Deterministic Pricing Verified
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Scope: <strong className="text-navy-800">{scopeName}</strong> (
            <span className="font-mono text-[11px]">{scopeId}</span>) &bull; Provider:{" "}
            <span className="font-semibold uppercase text-brand-700">{provider}</span>
          </p>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 transition shadow-2xs self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
          <span>{isLoading ? "Analyzing..." : "Re-evaluate Scope"}</span>
        </button>
      </div>

      {/* 2. Four Executive FinOps KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {/* KPI 1: Estimated Monthly Spend */}
        <button
          type="button"
          onClick={() => setFinancialDrawerKpi("spend")}
          className="text-left bg-white border border-slate-200 rounded-xl p-4 shadow-2xs hover:border-slate-400 hover:shadow-xs transition group focus:outline-none focus:ring-2 focus:ring-brand-500/20"
          title="Click to view itemized spend breakdown and calculation formula"
        >
          <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
            <span className="font-medium">Estimated Monthly Spend</span>
            <DollarSign className="w-3.5 h-3.5 text-slate-400" />
          </div>
          <div className="text-xl font-bold text-navy-950 font-mono tracking-tight">
            ${monthlySpend.toFixed(2)}
            <span className="text-xs font-normal text-slate-400">/mo</span>
          </div>
          <div className="flex items-center justify-between text-[11px] text-slate-400 mt-0.5">
            <span>{provider === "gcp" ? "GCP Catalog list" : "Azure Retail Prices"}</span>
            <span className="text-brand-600 font-semibold opacity-0 group-hover:opacity-100 transition">
              Drill-down &rarr;
            </span>
          </div>
        </button>

        {/* KPI 2: Identified Waste Savings */}
        <button
          type="button"
          onClick={() => setFinancialDrawerKpi("savings")}
          className="text-left bg-white border border-emerald-200 bg-emerald-50/20 rounded-xl p-4 shadow-2xs hover:border-emerald-400 hover:shadow-xs transition group focus:outline-none focus:ring-2 focus:ring-emerald-500/20"
          title="Click to inspect non-double-counted potential monthly savings"
        >
          <div className="flex items-center justify-between text-xs text-emerald-800 mb-1">
            <span className="font-medium">Potential Monthly Savings</span>
            <TrendingDown className="w-3.5 h-3.5 text-emerald-600" />
          </div>
          <div className="text-xl font-bold text-emerald-700 font-mono tracking-tight">
            ${monthlySavings.toFixed(2)}
            <span className="text-xs font-normal text-emerald-600">/mo</span>
          </div>
          <div className="flex items-center justify-between text-[11px] text-emerald-700 font-semibold mt-0.5">
            <span>
              {monthlySpend > 0
                ? `${((monthlySavings / monthlySpend) * 100).toFixed(1)}% spend reduction`
                : "Identified optimization"}
            </span>
            <span className="opacity-0 group-hover:opacity-100 transition">
              Drill-down &rarr;
            </span>
          </div>
        </button>

        {/* KPI 3: Deduplicated Annual Impact */}
        <button
          type="button"
          onClick={() => setFinancialDrawerKpi("annual_savings")}
          className="text-left bg-white border border-slate-200 rounded-xl p-4 shadow-2xs hover:border-amber-400 hover:shadow-xs transition group focus:outline-none focus:ring-2 focus:ring-amber-500/20"
          title="Click to inspect projected annual savings formula"
        >
          <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
            <span className="font-medium">Projected Annual Savings</span>
            <Zap className="w-3.5 h-3.5 text-amber-500" />
          </div>
          <div className="text-xl font-bold text-navy-950 font-mono tracking-tight">
            ${annualSavings.toFixed(2)}
            <span className="text-xs font-normal text-slate-400">/yr</span>
          </div>
          <div className="flex items-center justify-between text-[11px] text-slate-400 mt-0.5">
            <span>Non-double-counted guarantee</span>
            <span className="text-amber-600 font-semibold opacity-0 group-hover:opacity-100 transition">
              Drill-down &rarr;
            </span>
          </div>
        </button>

        {/* KPI 4: Actionable Findings Count */}
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
            <span className="font-medium">Actionable Opportunities</span>
            <Layers className="w-3.5 h-3.5 text-blue-500" />
          </div>
          <div className="text-xl font-bold text-navy-950 font-mono tracking-tight">
            {rawFindings.length + techDebtItems.length}
          </div>
          <span className="text-[11px] text-slate-400 block mt-0.5">
            {rawFindings.length} waste &bull; {techDebtItems.length} tech debt
          </span>
        </div>
      </div>

      {/* 3. Waste Category Distribution Visual Bar */}
      {Object.keys(categoryTotals).length > 0 && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
              FinOps Waste Category Distribution
            </h4>
            <span className="text-xs font-mono text-slate-500">
              Total Waste Pool: ${monthlySavings.toFixed(2)}/mo
            </span>
          </div>

          {/* Stacked Progress Bar */}
          <div className="w-full bg-slate-100 rounded-lg h-3 flex overflow-hidden">
            {Object.entries(categoryTotals).map(([cat, val], idx) => {
              const pct = monthlySavings > 0 ? (val / monthlySavings) * 100 : 0;
              const colors = [
                "bg-emerald-500",
                "bg-blue-500",
                "bg-purple-500",
                "bg-amber-500",
                "bg-rose-500",
              ];
              const color = colors[idx % colors.length];
              return (
                <div
                  key={cat}
                  className={`${color} h-full transition-all`}
                  style={{ width: `${pct}%` }}
                  title={`${cat}: $${val.toFixed(2)}/mo (${pct.toFixed(1)}%)`}
                />
              );
            })}
          </div>

          {/* Category Legend Chips */}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            {Object.entries(categoryTotals).map(([cat, val], idx) => {
              const pct = monthlySavings > 0 ? (val / monthlySavings) * 100 : 0;
              const dotColors = [
                "bg-emerald-500",
                "bg-blue-500",
                "bg-purple-500",
                "bg-amber-500",
                "bg-rose-500",
              ];
              const dotColor = dotColors[idx % dotColors.length];
              return (
                <button
                  key={cat}
                  type="button"
                  onClick={() =>
                    setCategoryFilter((prev) => (prev === cat ? "all" : cat))
                  }
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition ${
                    categoryFilter === cat
                      ? "bg-slate-900 text-white border-slate-900"
                      : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${dotColor}`} />
                  <span>{cat}</span>
                  <span className="font-mono text-[11px] opacity-75">
                    ${val.toFixed(2)} ({pct.toFixed(0)}%)
                  </span>
                </button>
              );
            })}
            {categoryFilter !== "all" && (
              <button
                type="button"
                onClick={() => setCategoryFilter("all")}
                className="text-xs text-brand-600 hover:underline font-medium"
              >
                Reset Category Filter
              </button>
            )}
          </div>
        </div>
      )}

      {/* 4. Ranked Waste Findings Table & Cards */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
          <div>
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-2">
              <TrendingDown className="w-4 h-4 text-emerald-600" />
              <span>Ranked Cloud Waste Findings &amp; Rightsizing Candidates</span>
            </h4>
            <p className="text-xs text-slate-500 mt-0.5">
              Ranked in descending order by monthly savings impact. Click any finding to inspect evidence and safe remediation.
            </p>
          </div>
          <span className="text-xs font-mono text-slate-400">
            {filteredFindings.length} findings
          </span>
        </div>

        {filteredFindings.length > 0 ? (
          <div className="space-y-3">
            {filteredFindings.map((finding, idx) => (
              <div
                key={finding.id}
                onClick={() => setSelectedFinding(finding)}
                className={`p-4 rounded-xl border transition cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-3 ${
                  selectedFinding?.id === finding.id
                    ? "border-emerald-500 bg-emerald-50/40 ring-1 ring-emerald-400"
                    : "border-slate-200 bg-slate-50/30 hover:border-emerald-300 hover:bg-emerald-50/20"
                }`}
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-7 h-7 rounded-lg bg-emerald-100 text-emerald-800 font-bold font-mono text-xs flex items-center justify-center shrink-0 mt-0.5">
                    #{idx + 1}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-100 text-emerald-800">
                        {finding.category}
                      </span>
                      <h5 className="text-sm font-bold text-navy-900 truncate">
                        {finding.title}
                      </h5>
                    </div>
                    <p className="text-xs text-slate-600 mt-1 line-clamp-2">
                      {finding.description}
                    </p>
                    <div className="flex items-center gap-3 mt-2 text-[11px] text-slate-400 font-mono">
                      <span>Resource: <strong className="text-slate-700">{finding.resource_name}</strong></span>
                      {finding.group_name && <span>Group: {finding.group_name}</span>}
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between md:justify-end gap-4 shrink-0 pt-2 md:pt-0 border-t md:border-t-0 border-slate-100">
                  <div className="text-right">
                    <div className="text-base font-bold text-emerald-700 font-mono">
                      +${parseFloat(finding.potential_monthly_savings.toString()).toFixed(2)}/mo
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono">
                      +${(parseFloat(finding.potential_monthly_savings.toString()) * 12).toFixed(2)}/yr
                    </span>
                  </div>

                  <button
                    type="button"
                    className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-700 hover:bg-emerald-100 transition"
                    title="Inspect Remediation Drawer"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-8 text-center text-slate-400 italic">
            Zero unattached disks, oversized compute, or idle storage detected in current scope.
          </div>
        )}
      </div>

      {/* 5. Architectural Technical Debt & Reliability Risks */}
      {techDebtItems.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-indigo-600" />
                <span>Architectural Technical Debt &amp; Reliability Risks</span>
              </h4>
              <p className="text-xs text-slate-500 mt-0.5">
                Configuration hygiene, missing backup policies, and single-instance bottlenecks.
              </p>
            </div>
            <span className="text-xs font-mono text-slate-400">
              {techDebtItems.length} items
            </span>
          </div>

          <div className="space-y-3">
            {techDebtItems.map((td) => (
              <div
                key={td.id}
                className="p-4 rounded-xl border border-indigo-200 bg-indigo-50/20 hover:bg-indigo-50/40 transition space-y-2"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                        td.severity === "high"
                          ? "bg-rose-100 text-rose-800"
                          : td.severity === "medium"
                          ? "bg-amber-100 text-amber-800"
                          : "bg-blue-100 text-blue-800"
                      }`}
                    >
                      {td.severity}
                    </span>
                    <h5 className="text-sm font-bold text-slate-900">{td.title}</h5>
                  </div>
                  <span className="text-[11px] font-mono text-slate-500">
                    Category: {td.debt_category}
                  </span>
                </div>

                <p className="text-xs text-slate-700 leading-relaxed">
                  {td.description}
                </p>

                <div className="p-2.5 rounded-lg bg-indigo-50 border border-indigo-100 text-xs text-indigo-900 font-medium">
                  <strong>Architectural Risk &amp; Remediation:</strong>{" "}
                  {td.remediation_steps?.join(" ") || td.architectural_risk}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 6. Expandable Right-Side Detail Drawer for Waste Remediation */}
      {selectedFinding && (
        <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
          <div
            onClick={() => setSelectedFinding(null)}
            className="fixed inset-0 bg-navy-950/40 backdrop-blur-xs transition-opacity"
          />

          <div className="relative w-full max-w-lg bg-white h-full shadow-2xl flex flex-col justify-between overflow-y-auto border-l border-slate-200 z-10">
            <div>
              {/* Drawer Header */}
              <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-slate-50/80 sticky top-0 bg-white z-10">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-100 text-emerald-800">
                    {selectedFinding.category}
                  </span>
                  <span className="text-xs font-mono text-slate-500">
                    Finding Details
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedFinding(null)}
                  className="p-1 rounded-lg text-slate-400 hover:text-navy-900 hover:bg-slate-100 transition"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Drawer Content */}
              <div className="p-6 space-y-6">
                <div>
                  <h3 className="text-lg font-bold text-navy-950 font-heading">
                    {selectedFinding.title}
                  </h3>
                  <p className="text-xs text-slate-600 mt-2 leading-relaxed">
                    {selectedFinding.description}
                  </p>
                </div>

                {/* Savings Callout Card */}
                <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-between">
                  <div>
                    <span className="text-xs text-emerald-800 font-medium block">
                      Potential Monthly Savings
                    </span>
                    <span className="text-2xl font-bold font-mono text-emerald-700">
                      +${parseFloat(selectedFinding.potential_monthly_savings.toString()).toFixed(2)}
                      <span className="text-xs font-normal">/mo</span>
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-xs text-emerald-800 font-medium block">
                      Annualized Return
                    </span>
                    <span className="text-lg font-bold font-mono text-emerald-800">
                      +${(parseFloat(selectedFinding.potential_monthly_savings.toString()) * 12).toFixed(2)}
                      <span className="text-xs font-normal">/yr</span>
                    </span>
                  </div>
                </div>

                {/* Target Resource Metadata */}
                <div className="space-y-2 text-xs">
                  <span className="font-bold text-navy-900 block uppercase tracking-wider text-[11px]">
                    Affected Resource Scope
                  </span>
                  <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 font-mono space-y-1">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Resource:</span>
                      <strong className="text-navy-900">{selectedFinding.resource_name}</strong>
                    </div>
                    {selectedFinding.group_name && (
                      <div className="flex justify-between">
                        <span className="text-slate-500">Group / Project:</span>
                        <span className="text-slate-700">{selectedFinding.group_name}</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-slate-500">Resource ID:</span>
                      <span className="text-slate-700 truncate max-w-[200px]" title={selectedFinding.resource_id}>
                        {selectedFinding.resource_id}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Evidence Metrics */}
                {(selectedFinding.metric_observed || selectedFinding.evidence) && (
                  <div className="space-y-2 text-xs">
                    <span className="font-bold text-navy-900 block uppercase tracking-wider text-[11px]">
                      Supporting Telemetry Evidence
                    </span>
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 font-mono space-y-1.5">
                      {selectedFinding.metric_observed && (
                        <div className="flex justify-between text-slate-700">
                          <span className="text-slate-500">Metric Observed:</span>
                          <span className="font-bold">{selectedFinding.metric_observed}</span>
                        </div>
                      )}
                      {selectedFinding.evidence && (
                        <div className="text-slate-700">
                          <span className="text-slate-500">Evidence: </span>
                          <span className="font-sans text-slate-800">{selectedFinding.evidence}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Pre-Remediation Verification Considerations */}
                {selectedFinding.pre_remediation_considerations &&
                  selectedFinding.pre_remediation_considerations.length > 0 && (
                    <div className="space-y-2 text-xs">
                      <span className="font-bold text-navy-900 block uppercase tracking-wider text-[11px]">
                        Pre-Remediation Safety Checklist
                      </span>
                      <ul className="p-3.5 rounded-xl bg-amber-50/70 border border-amber-200 text-amber-950 space-y-1.5 list-disc list-inside">
                        {selectedFinding.pre_remediation_considerations.map((c, idx) => (
                          <li key={idx} className="leading-relaxed">
                            {c}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                {/* Section A: Safe Read-Only Inspection Command */}
                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-navy-900 block uppercase tracking-wider text-[11px]">
                      1. Read-Only Inspection Command
                    </span>
                    <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      Safe &bull; Zero Mutation
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 leading-relaxed">
                    Execute in your local shell to inspect current status and tags before taking any action.
                  </p>
                  <div className="bg-navy-950 text-slate-200 p-3 rounded-lg font-mono text-[11px] flex items-center justify-between gap-2 border border-slate-800">
                    <span className="truncate">
                      {getInspectionCommand(selectedFinding, provider)}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        handleCopyCode(
                          getInspectionCommand(selectedFinding, provider),
                          1
                        )
                      }
                      className="text-slate-400 hover:text-white p-1"
                      title="Copy inspection command"
                    >
                      {copiedIndex === 1 ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Section B: Manual Remediation Guidance (External Action) */}
                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-navy-900 block uppercase tracking-wider text-[11px]">
                      2. Manual Remediation Action
                    </span>
                    <span className="text-[10px] font-semibold text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                      Admin Shell Only &bull; Destructive
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
                    <p className="leading-relaxed text-slate-700">
                      {selectedFinding.remediation_recommendation}
                    </p>

                    <div className="bg-navy-950 text-slate-200 p-3 rounded-lg font-mono text-[11px] flex items-center justify-between gap-2 border border-rose-900/40">
                      <span className="truncate">
                        {getRemediationCommand(selectedFinding, provider)}
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          handleCopyCode(
                            getRemediationCommand(selectedFinding, provider),
                            2
                          )
                        }
                        className="text-slate-400 hover:text-white p-1"
                        title="Copy remediation command"
                      >
                        {copiedIndex === 2 ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                    </div>

                    <p className="text-[11px] text-rose-700 font-medium">
                      &bull; Ensure backups or disk snapshots exist prior to executing manual deletions.
                    </p>
                  </div>
                </div>

                {/* Zero-Execution Safety Notice */}
                <div className="p-3 rounded-lg bg-blue-50/60 border border-blue-200 text-[11px] text-blue-900 flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
                  <span>
                    <strong>Strict Read-Only Architecture:</strong> The Cloud Recommender platform NEVER automatically deletes, modifies, stops, or reprovisions customer resources. All modifications require manual cloud administrator execution with explicit human authorization.
                  </span>
                </div>
              </div>
            </div>

            {/* Drawer Footer Actions */}
            <div className="p-4 border-t border-slate-200 bg-white flex items-center justify-between sticky bottom-0">
              <button
                type="button"
                onClick={() => setSelectedFinding(null)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
              >
                Close Drawer
              </button>

              {onInspectResource && (
                <button
                  type="button"
                  onClick={() => {
                    onInspectResource(selectedFinding.resource_id);
                    setSelectedFinding(null);
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold shadow-2xs transition"
                >
                  <span>Inspect Telemetry</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 5. Interactive Canonical Financial KPI Drawer */}
      {financialDrawerKpi && (
        <FinancialKpiDrawer
          isOpen={Boolean(financialDrawerKpi)}
          onClose={() => {
            setFinancialDrawerKpi(null);
            setDrillFindingId(null);
          }}
          kpiType={financialDrawerKpi}
          financials={canonicalFinancials}
          selectedFindingId={drillFindingId}
          onInspectResource={(resId) => {
            setFinancialDrawerKpi(null);
            if (onInspectResource) onInspectResource(resId);
          }}
        />
      )}
    </div>
  );
};

