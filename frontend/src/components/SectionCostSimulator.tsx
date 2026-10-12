"use client";

import React from "react";
import {
  DollarSign,
  Calendar,
  ShieldAlert,
  ExternalLink,
  Layers,
  Zap,
} from "lucide-react";
import { ArchitectureComponent, CostBreakdown, PricingReference } from "@/types";

interface SectionCostSimulatorProps {
  costBreakdown: CostBreakdown | null;
  components: ArchitectureComponent[];
  pricingProvenance: PricingReference[];
  unverifiedWarnings: string[];
  isSimulating: boolean;
}

export const SectionCostSimulator: React.FC<SectionCostSimulatorProps> = ({
  costBreakdown,
  components,
  pricingProvenance,
  unverifiedWarnings,
  isSimulating,
}) => {
  if (!costBreakdown) return null;

  const monthlyTotal = parseFloat(costBreakdown.total_monthly) || 0;
  const fiveMonthTotal = parseFloat(costBreakdown.total_five_month) || 0;
  const annualTotal = parseFloat(costBreakdown.total_annual) || 0;

  const categories = [
    { label: "Compute", amount: parseFloat(costBreakdown.compute) || 0, color: "bg-blue-500" },
    { label: "Database", amount: parseFloat(costBreakdown.database) || 0, color: "bg-emerald-500" },
    { label: "Storage", amount: parseFloat(costBreakdown.storage) || 0, color: "bg-amber-500" },
    { label: "AI Models", amount: parseFloat(costBreakdown.ai) || 0, color: "bg-purple-500" },
    { label: "Networking", amount: parseFloat(costBreakdown.networking) || 0, color: "bg-cyan-500" },
    { label: "Safety Buffer", amount: parseFloat(costBreakdown.safety_buffer_amount) || 0, color: "bg-indigo-400" },
  ];

  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-5 border-b border-slate-100 gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center">
            <span className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center mr-2">
              D
            </span>
            Deterministic Cost Simulator
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Transparent pricing based on official Azure Retail Prices API rates. Recalculates immediately with zero LLM dependency.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-blue-50 text-blue-700 text-xs font-semibold border border-blue-200">
            <Zap className="w-3.5 h-3.5 mr-1 text-blue-600 animate-pulse" />
            {isSimulating ? "Recalculating..." : "Real-Time Deterministic Engine"}
          </span>
        </div>
      </div>

      {/* Unverified Price Warnings */}
      {unverifiedWarnings && unverifiedWarnings.length > 0 && (
        <div className="mb-5 p-3.5 bg-amber-50 border border-amber-300 rounded-lg text-xs text-amber-900">
          <div className="font-bold flex items-center mb-1">
            <ShieldAlert className="w-4 h-4 mr-1.5 text-amber-600" />
            Pricing Notice:
          </div>
          <ul className="list-disc list-inside space-y-0.5 text-amber-800">
            {unverifiedWarnings.map((w, idx) => (
              <li key={idx}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Projections Headline Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* Monthly Projection */}
        <div className="p-4 bg-gradient-to-br from-blue-50/70 to-white rounded-xl border border-blue-200 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-blue-700 font-semibold mb-1">
            <span>Estimated Monthly Cost</span>
            <DollarSign className="w-4 h-4 text-blue-600" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 font-mono tracking-tight">
            ${monthlyTotal.toFixed(2)}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            Subtotal: ${parseFloat(costBreakdown.subtotal).toFixed(2)} + Buffer: ${parseFloat(costBreakdown.safety_buffer_amount).toFixed(2)}
          </div>
        </div>

        {/* 5-Month Projection */}
        <div className="p-4 bg-gradient-to-br from-indigo-50/70 to-white rounded-xl border border-indigo-200 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-indigo-700 font-semibold mb-1">
            <span>5-Month Projected Cost</span>
            <Calendar className="w-4 h-4 text-indigo-600" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 font-mono tracking-tight">
            ${fiveMonthTotal.toFixed(2)}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            Runway projection for initial deployment & pilot phases
          </div>
        </div>

        {/* Annual Projection */}
        <div className="p-4 bg-gradient-to-br from-emerald-50/70 to-white rounded-xl border border-emerald-200 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-emerald-700 font-semibold mb-1">
            <span>Annual Projected Spend</span>
            <Calendar className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 font-mono tracking-tight">
            ${annualTotal.toFixed(2)}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            12-month annualized projection (excluding reservation discounts)
          </div>
        </div>
      </div>

      {/* Cost Breakdown Visual Bar */}
      <div className="mb-6">
        <div className="text-xs font-bold text-slate-700 mb-2">
          Cost Distribution by Category:
        </div>
        <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden flex shadow-inner">
          {categories.map(
            (cat, idx) =>
              cat.amount > 0 && (
                <div
                  key={idx}
                  className={`${cat.color} h-full transition-all duration-300`}
                  style={{ width: `${(cat.amount / monthlyTotal) * 100}%` }}
                  title={`${cat.label}: $${cat.amount.toFixed(2)}`}
                />
              )
          )}
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-2.5 text-[11px]">
          {categories.map(
            (cat, idx) =>
              cat.amount > 0 && (
                <div key={idx} className="flex items-center space-x-1.5">
                  <span className={`w-2.5 h-2.5 rounded-full ${cat.color}`} />
                  <span className="text-slate-600 font-medium">{cat.label}:</span>
                  <span className="font-bold text-slate-800 font-mono">
                    ${cat.amount.toFixed(2)}
                  </span>
                </div>
              )
          )}
        </div>
      </div>

      {/* Bill of Materials (BOM) & Provenance Table */}
      <div>
        <div className="text-xs font-bold text-slate-700 mb-2.5 flex items-center">
          <Layers className="w-4 h-4 mr-1 text-blue-600" />
          Bill of Materials (BOM) & Pricing Provenance Traceability:
        </div>

        <div className="border border-slate-200 rounded-lg overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
              <tr>
                <th className="p-3">Service & SKU</th>
                <th className="p-3">Category</th>
                <th className="p-3 text-center">Qty</th>
                <th className="p-3">Unit Rate</th>
                <th className="p-3">Unit of Measure</th>
                <th className="p-3">Official Meter ID</th>
                <th className="p-3 text-right">Monthly Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {components.map((comp) => {
                const prov = pricingProvenance.find((p) => p.service_id === comp.service_id);
                const hasWarning = comp.missing_price_warning != null;

                return (
                  <tr key={comp.component_id} className="hover:bg-slate-50/70 transition">
                    <td className="p-3">
                      <div className="font-bold text-slate-900">{comp.service_name}</div>
                      <div className="text-[11px] text-slate-500 font-mono">{comp.sku_or_tier}</div>
                      {hasWarning && (
                        <div className="text-[10px] text-amber-700 font-medium mt-0.5">
                          ⚠️ {comp.missing_price_warning}
                        </div>
                      )}
                    </td>
                    <td className="p-3 uppercase font-mono text-[10px]">
                      <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                        {comp.category}
                      </span>
                    </td>
                    <td className="p-3 text-center font-bold font-mono">{comp.quantity}</td>
                    <td className="p-3 font-mono">
                      {prov ? `$${parseFloat(prov.rate).toFixed(5)}` : "—"}
                    </td>
                    <td className="p-3 text-slate-500">
                      {prov?.unit_description || comp.workload_unit || "Instance Hour"}
                    </td>
                    <td className="p-3 font-mono text-[11px] text-slate-500">
                      {prov ? (
                        <a
                          href={prov.source_api_or_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline inline-flex items-center"
                        >
                          {prov.meter_or_sku_id}
                          <ExternalLink className="w-2.5 h-2.5 ml-1" />
                        </a>
                      ) : (
                        "Local Reference"
                      )}
                    </td>
                    <td className="p-3 text-right font-bold text-slate-900 font-mono text-sm">
                      ${parseFloat(comp.monthly_cost).toFixed(2)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot className="bg-slate-50 border-t border-slate-200 font-bold text-slate-900">
              <tr>
                <td colSpan={6} className="p-3 text-right">
                  Subtotal:
                </td>
                <td className="p-3 text-right font-mono text-sm">
                  ${parseFloat(costBreakdown.subtotal).toFixed(2)}
                </td>
              </tr>
              <tr>
                <td colSpan={6} className="p-3 text-right text-slate-600 font-normal">
                  Safety Buffer (+{costBreakdown.safety_buffer_amount !== "0.00" ? "Active" : "0%"}):
                </td>
                <td className="p-3 text-right font-mono text-sm text-slate-600">
                  ${parseFloat(costBreakdown.safety_buffer_amount).toFixed(2)}
                </td>
              </tr>
              <tr className="border-t border-slate-300 text-blue-900 bg-blue-50/50">
                <td colSpan={6} className="p-3 text-right font-extrabold text-sm">
                  Total Monthly Cost:
                </td>
                <td className="p-3 text-right font-mono text-base font-extrabold text-blue-700">
                  ${monthlyTotal.toFixed(2)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </section>
  );
};

