"use client";

import React from "react";
import {
  DollarSign,
  Calendar,
  ShieldAlert,
  ExternalLink,
  Layers,
  Zap,
  CheckCircle2,
  AlertTriangle,
  Database,
} from "lucide-react";
import { ArchitectureComponent, CostBreakdown, PricingReference } from "@/types";

interface SectionCostSimulatorProps {
  costBreakdown: CostBreakdown | null;
  components: ArchitectureComponent[];
  pricingProvenance: PricingReference[];
  unverifiedWarnings: string[];
  isSimulating: boolean;
}

const formatUsd = (val: number) =>
  val.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export const SectionCostSimulator: React.FC<SectionCostSimulatorProps> = ({
  costBreakdown,
  components,
  pricingProvenance,
  unverifiedWarnings,
  isSimulating,
}) => {
  if (!costBreakdown) return null;

  const subtotal = parseFloat(costBreakdown.subtotal) || 0;
  const verifiedSubtotal =
    parseFloat(costBreakdown.verified_subtotal ?? costBreakdown.subtotal) ||
    subtotal;
  const bufferAmount = parseFloat(costBreakdown.safety_buffer_amount) || 0;
  const monthlyTotal = parseFloat(costBreakdown.total_monthly) || 0;
  const fiveMonthTotal = parseFloat(costBreakdown.total_five_month) || 0;
  const annualTotal = parseFloat(costBreakdown.total_annual) || 0;

  const hasWarnings =
    (unverifiedWarnings && unverifiedWarnings.length > 0) ||
    costBreakdown.is_complete === false;
  const isComplete = !hasWarnings;
  const unpricedCount =
    costBreakdown.unpriced_component_count ??
    components.filter(
      (c) => c.pricing_status === "unpriced" || c.missing_price_warning != null
    ).length;

  const categories = [
    {
      label: "Compute",
      amount: parseFloat(costBreakdown.compute) || 0,
      barColor: "bg-blue-600",
      dotColor: "bg-blue-600",
    },
    {
      label: "Database",
      amount: parseFloat(costBreakdown.database) || 0,
      barColor: "bg-emerald-600",
      dotColor: "bg-emerald-600",
    },
    {
      label: "Storage",
      amount: parseFloat(costBreakdown.storage) || 0,
      barColor: "bg-amber-500",
      dotColor: "bg-amber-500",
    },
    {
      label: "AI / ML",
      amount: parseFloat(costBreakdown.ai) || 0,
      barColor: "bg-purple-600",
      dotColor: "bg-purple-600",
    },
    {
      label: "Networking",
      amount: parseFloat(costBreakdown.networking) || 0,
      barColor: "bg-cyan-500",
      dotColor: "bg-cyan-500",
    },
    {
      label: "Other / Security",
      amount: parseFloat(costBreakdown.other) || 0,
      barColor: "bg-slate-500",
      dotColor: "bg-slate-500",
    },
    {
      label: "Safety Buffer",
      amount: bufferAmount,
      barColor: "bg-indigo-400",
      dotColor: "bg-indigo-400",
    },
  ];

  const resolveComponentStatus = (
    comp: ArchitectureComponent,
    prov: PricingReference | undefined
  ): "verified" | "provisional" | "bundled" | "unpriced" => {
    if (
      comp.pricing_status === "unpriced" ||
      comp.missing_price_warning != null ||
      prov?.provenance_source === "unverified_missing_rate"
    ) {
      return "unpriced";
    }
    if (
      comp.pricing_status === "bundled" ||
      prov?.provenance_source === "bundled_in_front_door_premium"
    ) {
      return "bundled";
    }
    if (comp.pricing_status === "provisional") {
      return "provisional";
    }
    const notes = (prov?.pricing_tier_or_notes || "").toLowerCase();
    if (notes.includes("provisional") || notes.includes("fallback")) {
      return "provisional";
    }
    return "verified";
  };

  const getProvenanceBadge = (
    status: "verified" | "provisional" | "bundled" | "unpriced"
  ) => {
    if (status === "unpriced") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-300 text-[10px] font-semibold">
          <AlertTriangle className="w-3 h-3 text-amber-600 shrink-0" />
          Unpriced / Missing Rate
        </span>
      );
    }
    if (status === "bundled") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-teal-50 text-teal-800 border border-teal-200 text-[10px] font-semibold">
          <CheckCircle2 className="w-3 h-3 text-teal-600 shrink-0" />
          Bundled in Front Door Premium
        </span>
      );
    }
    if (status === "provisional") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 text-[10px] font-semibold">
          <Database className="w-3 h-3 text-indigo-600 shrink-0" />
          Provisional Benchmark
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-semibold">
        <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0" />
        Verified Retail Rate
      </span>
    );
  };

  return (
    <section
      id="section-cost"
      className="scroll-mt-28 bg-white rounded-2xl border border-slate-200/90 shadow-card p-5 sm:p-6 lg:p-7 mb-6 transition-shadow"
    >
      {/* Header Row */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-5 border-b border-slate-100 gap-3">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl bg-blue-50 border border-blue-200/70 text-blue-700 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
            04
          </div>
          <div>
            <div className="flex items-center flex-wrap gap-2">
              <h2 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight">
                Deterministic FinOps Cost Simulator
              </h2>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200 font-semibold">
                Currency: USD ($)
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Decimal-exact calculations backed by Azure Retail Prices API meters. Zero generative price estimation.
            </p>
          </div>
        </div>

        {/* Engine & Verification Status */}
        <div className="flex flex-wrap items-center gap-2">
          {!isComplete ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-300 text-xs font-semibold">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              <span>Incomplete Estimate ({unpricedCount} Unpriced)</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-medium">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              <span>All Meters Verified</span>
            </span>
          )}
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200 text-xs font-semibold">
            <Zap
              className={`w-3.5 h-3.5 text-blue-600 ${
                isSimulating ? "animate-spin" : ""
              }`}
            />
            <span>{isSimulating ? "Recalculating..." : "Deterministic Engine"}</span>
          </span>
        </div>
      </div>

      {/* Incomplete Estimate / Unverified Price Warnings Banner */}
      {!isComplete && (
        <div
          role="alert"
          className="mb-5 p-4 bg-amber-50/90 border border-amber-300 rounded-xl text-xs text-amber-950"
        >
          <div className="font-semibold flex items-center gap-1.5 mb-1.5">
            <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              Incomplete Cost Estimate — {unpricedCount} Component(s) Unpriced
            </span>
          </div>
          <p className="text-[11px] text-amber-800 mb-2">
            The overall estimate is marked <strong>incomplete</strong> because one or more required components have no verified retail price. Unpriced components are never assigned an invented default price and are not free services. The{" "}
            <strong>Verified Subtotal (${formatUsd(verifiedSubtotal)})</strong>{" "}
            and FinOps safety buffer (+${formatUsd(bufferAmount)}) cover{" "}
            <strong>only verified/priced components</strong> and do not conceal unpriced items:
          </p>
          <ul className="list-disc list-inside space-y-1 text-amber-900 font-medium">
            {unverifiedWarnings.map((w, idx) => (
              <li key={idx}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Cost Overview Projection Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-6">
        {/* 1. Verified Subtotal + Buffer Breakdown */}
        <div className="p-4 rounded-xl bg-slate-50/90 border border-slate-200/90 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-xs text-slate-600 font-semibold mb-1">
              <span>Verified Subtotal (Priced BOM)</span>
              <Layers className="w-4 h-4 text-slate-500" />
            </div>
            <div className="text-xl font-bold text-slate-900 font-mono tracking-tight">
              ${formatUsd(verifiedSubtotal)}
            </div>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-200/80 flex items-center justify-between text-[11px]">
            <span className="text-slate-500 font-medium">
              + Buffer (on verified only):
            </span>
            <span className="font-mono font-semibold text-indigo-700">
              +${formatUsd(bufferAmount)}
            </span>
          </div>
        </div>

        {/* 2. Estimated Monthly Total (or Incomplete Monthly Estimate) */}
        <div
          className={`p-4 rounded-xl shadow-2xs flex flex-col justify-between ${
            isComplete
              ? "bg-blue-50/50 border border-blue-200/90"
              : "bg-amber-50/60 border border-amber-300"
          }`}
        >
          <div>
            <div
              className={`flex items-center justify-between text-xs font-semibold mb-1 ${
                isComplete ? "text-blue-700" : "text-amber-900"
              }`}
            >
              <span>
                {isComplete
                  ? "Estimated Monthly Total"
                  : "Incomplete Monthly Estimate"}
              </span>
              <DollarSign
                className={`w-4 h-4 ${
                  isComplete ? "text-blue-600" : "text-amber-600"
                }`}
              />
            </div>
            <div className="text-2xl font-bold text-slate-900 font-mono tracking-tight transition-all">
              ${formatUsd(monthlyTotal)}
            </div>
          </div>
          <div
            className={`mt-2 pt-2 text-[11px] ${
              isComplete
                ? "border-t border-blue-200/60 text-slate-600"
                : "border-t border-amber-200 text-amber-800 font-medium"
            }`}
          >
            {isComplete
              ? "Includes verified BOM + contingency buffer"
              : `Excludes ${unpricedCount} unpriced service(s)`}
          </div>
        </div>

        {/* 3. 5-Month Projected Cost */}
        <div className="p-4 rounded-xl bg-slate-50/90 border border-slate-200/90 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-xs text-indigo-700 font-semibold mb-1">
              <span>
                {isComplete
                  ? "5-Month Projected Spend"
                  : "5-Month (Verified Only)"}
              </span>
              <Calendar className="w-4 h-4 text-indigo-600" />
            </div>
            <div className="text-2xl font-bold text-slate-900 font-mono tracking-tight">
              ${formatUsd(fiveMonthTotal)}
            </div>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-200/80 text-[11px] text-slate-500">
            5 × monthly run-rate projection
          </div>
        </div>

        {/* 4. Annual Projected Spend */}
        <div className="p-4 rounded-xl bg-slate-50/90 border border-slate-200/90 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-xs text-emerald-700 font-semibold mb-1">
              <span>
                {isComplete
                  ? "Annual Projected Spend"
                  : "Annual (Verified Only)"}
              </span>
              <Calendar className="w-4 h-4 text-emerald-600" />
            </div>
            <div className="text-2xl font-bold text-slate-900 font-mono tracking-tight">
              ${formatUsd(annualTotal)}
            </div>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-200/80 text-[11px] text-slate-500">
            12-month PAYG projection (pre-RI/Savings Plan)
          </div>
        </div>
      </div>

      {/* Category Cost Distribution Visualization */}
      <div className="mb-6 p-4 rounded-xl bg-slate-50/70 border border-slate-200/80">
        <div className="flex items-center justify-between text-xs font-semibold text-slate-800 mb-2.5">
          <span>Monthly Spend Distribution by Architectural Category</span>
          <span className="font-mono text-slate-500">
            100% = ${formatUsd(monthlyTotal)}
          </span>
        </div>

        {/* Proportional Bar */}
        <div className="h-3 w-full bg-slate-200/80 rounded-full overflow-hidden flex">
          {categories.map(
            (cat, idx) =>
              cat.amount > 0 &&
              monthlyTotal > 0 && (
                <div
                  key={idx}
                  className={`${cat.barColor} h-full transition-all duration-200`}
                  style={{ width: `${(cat.amount / monthlyTotal) * 100}%` }}
                  title={`${cat.label}: $${formatUsd(cat.amount)}`}
                />
              )
          )}
        </div>

        {/* Category Legend & Breakdown */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 mt-3">
          {categories
            .filter((c) => c.amount > 0)
            .map((cat, idx) => {
              const pct =
                monthlyTotal > 0
                  ? ((cat.amount / monthlyTotal) * 100).toFixed(1)
                  : "0.0";
              return (
                <div
                  key={idx}
                  className="p-2.5 rounded-lg bg-white border border-slate-200/80 flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between gap-1 text-[11px] text-slate-600">
                    <span className="inline-flex items-center gap-1.5 font-medium truncate">
                      <span className={`w-2 h-2 rounded-full ${cat.dotColor} shrink-0`} />
                      <span className="truncate">{cat.label}</span>
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">{pct}%</span>
                  </div>
                  <div className="text-xs font-bold font-mono text-slate-900 mt-1">
                    ${formatUsd(cat.amount)}
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {/* Bill of Materials (BOM) & Provenance Traceability */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs sm:text-sm font-semibold text-slate-900 flex items-center gap-1.5">
            <Layers className="w-4 h-4 text-blue-600" />
            <span>Bill of Materials (BOM) &amp; Pricing Provenance</span>
          </div>
          <span className="text-[11px] text-slate-400">
            {components.length} line items
          </span>
        </div>

        {/* Desktop & Tablet Table View */}
        <div className="hidden md:block border border-slate-200/90 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
                <tr>
                  <th className="py-3 px-4">Service &amp; SKU</th>
                  <th className="py-3 px-3">Category</th>
                  <th className="py-3 px-3 text-center">Qty</th>
                  <th className="py-3 px-3 text-right">Unit Rate (USD)</th>
                  <th className="py-3 px-3">Billing Unit</th>
                  <th className="py-3 px-3">Provenance &amp; Meter</th>
                  <th className="py-3 px-4 text-right">Monthly Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700 bg-white">
                {components.map((comp) => {
                  const prov = pricingProvenance.find(
                    (p) => p.service_id === comp.service_id
                  );
                  const status = resolveComponentStatus(comp, prov);
                  const isUnpriced = status === "unpriced";
                  const isBundled = status === "bundled";
                  const provenanceUrl =
                    prov?.source_url ||
                    prov?.source_api_or_url ||
                    "https://azure.microsoft.com/en-us/pricing/";

                  return (
                    <tr
                      key={comp.component_id}
                      className={`hover:bg-slate-50/80 transition ${
                        isUnpriced ? "bg-amber-50/30" : ""
                      }`}
                    >
                      <td className="py-3 px-4">
                        <div className="font-semibold text-slate-900">
                          {comp.service_name}
                        </div>
                        <div className="text-[11px] text-slate-500 font-mono">
                          {comp.sku_or_tier}
                        </div>
                        {comp.missing_price_warning && (
                          <div className="inline-flex items-center gap-1 text-[11px] text-amber-800 font-medium mt-1">
                            <AlertTriangle className="w-3 h-3 text-amber-600 shrink-0" />
                            <span>{comp.missing_price_warning}</span>
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-3 uppercase font-mono text-[10px]">
                        <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200 font-semibold">
                          {comp.category}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-center font-bold font-mono text-slate-900">
                        {comp.quantity}
                      </td>
                      <td className="py-3 px-3 text-right font-mono text-slate-700">
                        {isUnpriced
                          ? "Unpriced"
                          : isBundled
                            ? "$0.00 (Bundled)"
                            : prov
                              ? `$${parseFloat(prov.rate).toFixed(4)}`
                              : "—"}
                      </td>
                      <td className="py-3 px-3 text-slate-500">
                        {comp.workload_unit ||
                          prov?.unit_description ||
                          "Instance Hour"}
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex flex-col items-start gap-1">
                          {getProvenanceBadge(status)}
                          {prov && (
                            <a
                              href={provenanceUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[11px] font-mono text-blue-600 hover:text-blue-800 hover:underline inline-flex items-center gap-1"
                            >
                              <span>{prov.meter_or_sku_id}</span>
                              <ExternalLink className="w-3 h-3 shrink-0" />
                            </a>
                          )}
                          {prov?.product_name && prov?.meter_name && (
                            <span className="text-[10px] text-slate-400 font-mono">
                              {prov.product_name} • {prov.meter_name}
                              {prov.arm_region_name
                                ? ` (${prov.arm_region_name})`
                                : ""}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right font-bold font-mono text-sm">
                        {isUnpriced ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-amber-100 text-amber-900 border border-amber-300 text-xs font-bold">
                            Unpriced
                          </span>
                        ) : isBundled ? (
                          <span className="text-teal-800">
                            $0.00{" "}
                            <span className="text-[10px] font-sans font-medium text-teal-600 block">
                              Bundled in FD Premium
                            </span>
                          </span>
                        ) : (
                          <span className="text-slate-900">
                            ${formatUsd(parseFloat(comp.monthly_cost) || 0)}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot className="bg-slate-50/90 border-t border-slate-200 text-slate-900">
                <tr>
                  <td colSpan={6} className="py-2.5 px-4 text-right font-semibold text-slate-600">
                    Verified Subtotal (Priced BOM Items Only):
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono font-bold text-sm">
                    ${formatUsd(verifiedSubtotal)}
                  </td>
                </tr>
                <tr>
                  <td colSpan={6} className="py-2.5 px-4 text-right text-slate-600">
                    FinOps Contingency Buffer (Applies to Verified Subtotal Only):
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono font-semibold text-sm text-indigo-700">
                    +${formatUsd(bufferAmount)}
                  </td>
                </tr>
                <tr
                  className={`border-t border-slate-200 text-slate-900 ${
                    isComplete ? "bg-blue-50/50" : "bg-amber-50/70"
                  }`}
                >
                  <td colSpan={6} className="py-3 px-4 text-right font-bold text-sm">
                    {isComplete
                      ? "Estimated Total Monthly Cost (USD):"
                      : `Incomplete Monthly Estimate (Excludes ${unpricedCount} Unpriced Component(s)):`}
                  </td>
                  <td
                    className={`py-3 px-4 text-right font-mono text-base font-bold ${
                      isComplete ? "text-blue-700" : "text-amber-900"
                    }`}
                  >
                    ${formatUsd(monthlyTotal)}
                    {!isComplete && (
                      <span className="block text-[10px] font-sans font-semibold text-amber-700">
                        Incomplete (Excludes Unpriced)
                      </span>
                    )}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        {/* Mobile Responsive BOM Card List */}
        <div className="md:hidden space-y-2.5">
          {components.map((comp) => {
            const prov = pricingProvenance.find(
              (p) => p.service_id === comp.service_id
            );
            const status = resolveComponentStatus(comp, prov);
            const isUnpriced = status === "unpriced";
            const isBundled = status === "bundled";
            const provenanceUrl =
              prov?.source_url ||
              prov?.source_api_or_url ||
              "https://azure.microsoft.com/en-us/pricing/";

            return (
              <div
                key={comp.component_id}
                className={`p-3.5 rounded-xl border space-y-2 text-xs ${
                  isUnpriced
                    ? "border-amber-300 bg-amber-50/40"
                    : "border-slate-200 bg-slate-50/60"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-900">
                      {comp.service_name}
                    </div>
                    <div className="text-[11px] font-mono text-slate-500">
                      {comp.sku_or_tier}
                    </div>
                  </div>
                  <div className="text-right font-mono font-bold text-sm text-slate-900">
                    {isUnpriced ? (
                      <span className="text-amber-800">Unpriced</span>
                    ) : isBundled ? (
                      <span className="text-teal-800">$0.00 (Bundled)</span>
                    ) : (
                      `$${formatUsd(parseFloat(comp.monthly_cost) || 0)}`
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200/70 text-[11px] text-slate-600">
                  <span>
                    Qty: <strong className="font-mono">{comp.quantity}</strong> • Rate:{" "}
                    <span className="font-mono">
                      {isUnpriced
                        ? "Unpriced"
                        : isBundled
                          ? "$0.00 (Bundled)"
                          : prov
                            ? `$${parseFloat(prov.rate).toFixed(4)}`
                            : "—"}
                    </span>
                  </span>
                  {getProvenanceBadge(status)}
                </div>

                {prov && (
                  <div className="text-[11px] flex items-center justify-between text-slate-500">
                    <span>Unit: {comp.workload_unit || prov.unit_description}</span>
                    <a
                      href={provenanceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-blue-600 hover:underline inline-flex items-center gap-1"
                    >
                      <span>{prov.meter_or_sku_id}</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                )}

                {comp.missing_price_warning && (
                  <div className="p-2 rounded bg-amber-50 border border-amber-200 text-[11px] text-amber-800 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                    <span>{comp.missing_price_warning}</span>
                  </div>
                )}
              </div>
            );
          })}

          <div
            className={`p-3.5 rounded-xl border space-y-1 text-xs ${
              isComplete
                ? "bg-blue-50/60 border-blue-200"
                : "bg-amber-50/70 border-amber-300"
            }`}
          >
            <div className="flex justify-between text-slate-600">
              <span>Verified Subtotal:</span>
              <span className="font-mono font-semibold">
                ${formatUsd(verifiedSubtotal)}
              </span>
            </div>
            <div className="flex justify-between text-slate-600">
              <span>Safety Buffer (on Verified Only):</span>
              <span className="font-mono font-semibold text-indigo-700">
                +${formatUsd(bufferAmount)}
              </span>
            </div>
            <div className="flex justify-between pt-1.5 border-t border-slate-200 font-bold text-slate-900 text-sm">
              <span>
                {isComplete
                  ? "Total Monthly (USD):"
                  : `Incomplete Monthly (Excludes ${unpricedCount} Unpriced):`}
              </span>
              <span
                className={`font-mono ${
                  isComplete ? "text-blue-700" : "text-amber-900"
                }`}
              >
                ${formatUsd(monthlyTotal)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
