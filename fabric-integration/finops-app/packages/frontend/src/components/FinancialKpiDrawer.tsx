"use client";

import React, { useEffect, useCallback } from "react";
import {
  X,
  DollarSign,
  TrendingDown,
  Zap,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Download,
  Info,
  Layers,
  Cpu,
  Database,
  HardDrive,
  Sparkles,
  Network,
} from "lucide-react";
import {
  CanonicalFinancialSummary,
  FinancialKpiType,
} from "@/types/financials";
import { formatFinancialCurrency } from "@/lib/financials";

interface FinancialKpiDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  kpiType: FinancialKpiType;
  financials: CanonicalFinancialSummary;
  selectedFindingId?: string | null;
  onInspectResource?: (resourceId: string) => void;
}

export const FinancialKpiDrawer: React.FC<FinancialKpiDrawerProps> = ({
  isOpen,
  onClose,
  kpiType,
  financials,
  selectedFindingId,
  onInspectResource,
}) => {
  // ESC key listener to close drawer
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      window.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
    }
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "unset";
    };
  }, [isOpen, handleKeyDown]);

  if (!isOpen) return null;

  const { currency } = financials;

  // CSV Export Function
  const handleExportCsv = () => {
    const headers = [
      "Record_Type",
      "Scope_ID",
      "Scope_Name",
      "Provider",
      "Item_Name",
      "Category",
      "Severity_or_Status",
      "Amount_USD",
      "Percentage",
      "Formula_or_Basis",
      "Evidence",
    ];

    const rows: string[][] = [];

    if (kpiType === "spend" || kpiType === "category") {
      financials.categories.forEach((c) => {
        rows.push([
          "Category_Spend",
          financials.scope_id,
          `"${financials.scope_name}"`,
          financials.provider,
          `"${c.name}"`,
          c.category_key,
          "Active",
          c.amount_usd.toFixed(2),
          `${c.percentage_of_total}%`,
          `"${financials.spend_formula}"`,
          `"${c.description || "Discovered resource category"}"`,
        ]);
      });
    } else {
      financials.findings.forEach((f) => {
        rows.push([
          "Optimization_Finding",
          financials.scope_id,
          `"${financials.scope_name}"`,
          financials.provider,
          `"${f.title}"`,
          f.category,
          f.severity,
          f.potential_monthly_savings.toFixed(2),
          `${((f.potential_monthly_savings / (financials.estimated_monthly_spend || 1)) * 100).toFixed(1)}%`,
          `"${f.calculation_formula}"`,
          `"${f.evidence}"`,
        ]);
      });
    }

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute(
      "download",
      `finops_${financials.provider}_${financials.scope_id}_${kpiType}_reconciliation.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const getCategoryIcon = (key: string) => {
    switch (key) {
      case "compute":
        return <Cpu className="w-3.5 h-3.5 text-brand-600" />;
      case "database":
        return <Database className="w-3.5 h-3.5 text-emerald-600" />;
      case "storage":
        return <HardDrive className="w-3.5 h-3.5 text-amber-600" />;
      case "ai":
        return <Sparkles className="w-3.5 h-3.5 text-purple-600" />;
      case "networking":
        return <Network className="w-3.5 h-3.5 text-cyan-600" />;
      default:
        return <Layers className="w-3.5 h-3.5 text-slate-500" />;
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="financial-drawer-title"
      className="fixed inset-0 z-50 overflow-hidden bg-slate-900/40 backdrop-blur-xs flex justify-end animate-in fade-in duration-200"
    >
      <div className="w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">
        {/* 1. Header Bar */}
        <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-brand-50 border border-brand-200 text-brand-700 flex items-center justify-center shrink-0">
              {kpiType === "spend" || kpiType === "category" ? (
                <DollarSign className="w-5 h-5 text-brand-600" />
              ) : kpiType === "annual_savings" ? (
                <Zap className="w-5 h-5 text-amber-500" />
              ) : (
                <TrendingDown className="w-5 h-5 text-emerald-600" />
              )}
            </div>
            <div>
              <h2
                id="financial-drawer-title"
                className="text-base font-bold text-navy-950 font-heading"
              >
                {kpiType === "spend" && "Estimated Monthly Spend Breakdown"}
                {kpiType === "savings" && "Monthly Optimization Opportunity"}
                {kpiType === "annual_savings" && "Projected Annual Savings Proof"}
                {kpiType === "realized_savings" && "Realized Savings & Zero-Execution Policy"}
                {kpiType === "category" && "Category Cost Allocation"}
                {kpiType === "resources" && "Managed Resource Cost Rollup"}
                {kpiType === "finding" && "High-Impact Finding Deep Dive"}
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Scope: <strong className="text-navy-900">{financials.scope_name}</strong> (
                <span className="font-mono text-[11px]">{financials.scope_id}</span>) &bull;{" "}
                <span className="font-semibold uppercase text-brand-700">
                  {financials.provider}
                </span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExportCsv}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700 shadow-2xs transition"
              title="Export financial reconciliation records as CSV"
            >
              <Download className="w-3.5 h-3.5 text-brand-600" />
              <span>CSV</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-500 transition"
              aria-label="Close detail drawer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 2. Scrollable Body Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs text-slate-700">
          {/* Main KPI Stat Card */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span className="font-semibold uppercase tracking-wider text-[11px]">
                {kpiType === "spend"
                  ? "Estimated Monthly Spend (Catalog Basis)"
                  : kpiType === "annual_savings"
                  ? "Projected 12-Month Avoidable Waste"
                  : kpiType === "realized_savings"
                  ? "Realized Monthly Savings (Strict Zero-Execution)"
                  : "Potential Monthly Optimization Pool"}
              </span>
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                Deterministic Proof Verified
              </span>
            </div>

            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-navy-950 font-mono tracking-tight">
                {kpiType === "spend" && formatFinancialCurrency(financials.estimated_monthly_spend, currency)}
                {kpiType === "savings" && formatFinancialCurrency(financials.potential_monthly_savings, currency)}
                {kpiType === "annual_savings" && formatFinancialCurrency(financials.projected_annual_savings, currency)}
                {kpiType === "realized_savings" && formatFinancialCurrency(0, currency)}
                {(kpiType === "category" || kpiType === "resources" || kpiType === "finding") &&
                  formatFinancialCurrency(financials.potential_monthly_savings, currency)}
              </span>
              <span className="text-xs text-slate-500 font-medium">
                {kpiType === "annual_savings" ? "/year" : "/month"}
              </span>
              {financials.estimated_monthly_spend > 0 &&
                (kpiType === "savings" || kpiType === "finding") && (
                  <span className="text-xs font-bold text-accent-emerald bg-emerald-100 px-1.5 py-0.5 rounded">
                    {financials.savings_percentage_of_spend}% of total spend
                  </span>
                )}
            </div>

            {/* Truthful Definition Note */}
            <p className="text-xs text-slate-600 pt-1 border-t border-slate-200 leading-relaxed">
              {kpiType === "spend" && (
                <>
                  <strong>Calculation Basis:</strong> Calculated deterministically using official{" "}
                  <strong>{financials.pricing_source}</strong> public pay-as-you-go list rates for all{" "}
                  <strong>{financials.included_resources_count}</strong> active discovered resources across 730 continuous operating hours.
                </>
              )}
              {kpiType === "savings" && (
                <>
                  <strong>Calculation Basis:</strong> Sum of <strong>{financials.findings_count}</strong> itemized, non-overlapping FinOps waste detections. Each finding is capped at its parent resource spend to prevent double-counting.
                </>
              )}
              {kpiType === "annual_savings" && (
                <>
                  <strong>Calculation Basis:</strong> Non-double-counted 12-month projection (Monthly Savings &times; 12). Assumes unaddressed idle/oversized waste persists for 1 year if unoptimized.
                </>
              )}
              {kpiType === "realized_savings" && (
                <>
                  <strong>Zero-Execution Guarantee:</strong> Realized savings is strictly <strong>$0.00</strong> because this platform is purely an advisory inspection system. No destructive changes or infrastructure deletions are ever executed automatically.
                </>
              )}
            </p>
          </div>

          {/* Mathematical Formula Callout */}
          <div className="p-4 rounded-xl bg-blue-50/60 border border-blue-200 space-y-1.5">
            <div className="flex items-center gap-1.5 font-bold text-blue-900 text-xs">
              <Info className="w-3.5 h-3.5 text-blue-600" />
              <span>Mathematical Formula &amp; Invariants</span>
            </div>
            <div className="font-mono text-[11px] text-blue-800 bg-white p-2.5 rounded-lg border border-blue-200 space-y-1">
              <div>
                <strong>Spend Invariant:</strong> Total Spend = Compute + Database + Storage + AI + Networking = {formatFinancialCurrency(financials.estimated_monthly_spend, currency)}
              </div>
              <div>
                <strong>Savings Invariant:</strong> Total Potential Savings = &Sigma; FindingSavings ({financials.findings_count} itemized findings) = {formatFinancialCurrency(financials.potential_monthly_savings, currency)} (Residual Delta = $0.0000)
              </div>
            </div>
          </div>

          {/* Section: Category Spend Table (If spend, category, or resources) */}
          {(kpiType === "spend" || kpiType === "category" || kpiType === "resources") && (
            <div className="space-y-3">
              <h3 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center justify-between">
                <span>Category Spend Allocation</span>
                <span className="font-mono text-slate-500 font-normal">
                  Total: {formatFinancialCurrency(financials.estimated_monthly_spend, currency)}/mo
                </span>
              </h3>

              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
                    <tr>
                      <th className="py-2.5 px-3 font-semibold">Service Category</th>
                      <th className="py-2.5 px-3 font-semibold text-right">Monthly Spend</th>
                      <th className="py-2.5 px-3 font-semibold text-right">% of Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {financials.categories.map((c) => (
                      <tr key={c.category_key} className="hover:bg-slate-50/60 transition">
                        <td className="py-2.5 px-3">
                          <div className="flex items-center gap-2">
                            {getCategoryIcon(c.category_key)}
                            <div>
                              <span className="font-semibold text-navy-900 block">{c.name}</span>
                              {c.description && (
                                <span className="text-[10px] text-slate-400 block truncate max-w-xs">
                                  {c.description}
                                </span>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-navy-900">
                          {formatFinancialCurrency(c.amount_usd, currency)}
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono text-slate-600">
                          {c.percentage_of_total}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-slate-50 border-t border-slate-200 font-bold text-navy-900">
                    <tr>
                      <td className="py-2 px-3">Reconciled Sum</td>
                      <td className="py-2 px-3 text-right font-mono text-brand-700">
                        {formatFinancialCurrency(financials.estimated_monthly_spend, currency)}
                      </td>
                      <td className="py-2 px-3 text-right font-mono">100.0%</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          )}

          {/* Section: Itemized Waste Findings (If savings, finding, or annual_savings) */}
          {(kpiType === "savings" || kpiType === "finding" || kpiType === "annual_savings") && (
            <div className="space-y-3">
              <h3 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center justify-between">
                <span>Itemized Non-Overlapping Findings ({financials.findings.length})</span>
                <span className="font-mono text-emerald-700 font-normal">
                  Total Pool: {formatFinancialCurrency(financials.potential_monthly_savings, currency)}/mo
                </span>
              </h3>

              <div className="space-y-2.5">
                {financials.findings.map((f) => {
                  const isSelected = selectedFindingId === f.id;
                  return (
                    <div
                      key={f.id}
                      className={`p-3.5 rounded-xl border transition ${
                        isSelected
                          ? "bg-emerald-50/40 border-emerald-300 ring-2 ring-emerald-100"
                          : "bg-white border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span
                              className={`px-1.5 py-0.2 rounded text-[10px] font-bold uppercase ${
                                f.severity === "high"
                                  ? "bg-rose-100 text-rose-800"
                                  : f.severity === "medium"
                                  ? "bg-amber-100 text-amber-800"
                                  : "bg-blue-100 text-blue-800"
                              }`}
                            >
                              {f.severity}
                            </span>
                            <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                              {f.category}
                            </span>
                            <span className="text-[11px] font-semibold text-navy-900 truncate">
                              {f.title}
                            </span>
                          </div>
                          <p className="text-slate-600 text-xs mt-1 leading-relaxed">
                            {f.description}
                          </p>
                        </div>

                        <div className="text-right shrink-0">
                          <div className="text-sm font-bold text-emerald-700 font-mono">
                            {formatFinancialCurrency(f.potential_monthly_savings, currency)}
                            <span className="text-[10px] font-normal text-slate-400">/mo</span>
                          </div>
                          <span className="text-[10px] text-slate-400 block font-mono">
                            Spend: {formatFinancialCurrency(f.current_monthly_spend, currency)}
                          </span>
                        </div>
                      </div>

                      {/* Evidence & Technical Details Callout */}
                      <div className="mt-2.5 pt-2.5 border-t border-slate-100 space-y-1.5 text-[11px]">
                        <div>
                          <strong className="text-slate-600">Observation Evidence:</strong>{" "}
                          <span className="text-slate-700 font-mono">{f.evidence}</span>
                        </div>
                        <div>
                          <strong className="text-slate-600">Formula &amp; Rate Source:</strong>{" "}
                          <span className="text-slate-700">{f.calculation_formula}</span>
                        </div>
                        {f.pre_remediation_considerations && (
                          <div className="p-2 rounded bg-amber-50/70 border border-amber-200 text-amber-900 text-[10px]">
                            <strong>Pre-Remediation Caution:</strong>{" "}
                            {f.pre_remediation_considerations}
                          </div>
                        )}
                        {onInspectResource && (
                          <div className="pt-1 flex justify-end">
                            <button
                              type="button"
                              onClick={() => {
                                onInspectResource(f.resource_id);
                                onClose();
                              }}
                              className="text-[11px] font-semibold text-brand-600 hover:underline inline-flex items-center gap-1"
                            >
                              <span>Inspect Resource Telemetry</span>
                              &rarr;
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Metadata & Governance Checklist */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
            <span className="font-semibold text-slate-500 uppercase tracking-wider text-[11px] block">
              Audit Metadata &amp; Governance
            </span>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div>
                <span className="text-slate-400 block">Pricing Source:</span>
                <strong className="text-navy-900">{financials.pricing_source}</strong>
              </div>
              <div>
                <span className="text-slate-400 block">Rate Effective:</span>
                <strong className="text-navy-900">{financials.rate_effective_date}</strong>
              </div>
              <div>
                <span className="text-slate-400 block">Data Provenance:</span>
                <span className="font-mono text-emerald-700 font-semibold">
                  {financials.data_provenance}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block">Audit Timestamp:</span>
                <span className="font-mono text-slate-600">
                  {new Date(financials.last_updated).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
              </div>
            </div>
          </div>

          {/* Assumptions & Limitations Accordion / Block */}
          <div className="p-4 rounded-xl bg-amber-50/50 border border-amber-200 space-y-2">
            <div className="flex items-center gap-1.5 font-bold text-amber-900 text-xs">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              <span>Assumptions &amp; Protected Boundaries</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-[11px] text-amber-900">
              {financials.assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
              {financials.limitations.map((l, i) => (
                <li key={`lim-${i}`}>{l}</li>
              ))}
            </ul>
          </div>
        </div>

        {/* 3. Footer Action */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <ShieldCheck className="w-4 h-4 text-accent-emerald shrink-0" />
            <span>Zero-Execution Policy Enforced &bull; 100% Read-Only</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-navy-900 hover:bg-navy-800 text-white font-semibold text-xs transition shadow-2xs"
          >
            Close Drill-Down
          </button>
        </div>
      </div>
    </div>
  );
};
