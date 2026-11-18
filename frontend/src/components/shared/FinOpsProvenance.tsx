"use client";

import React from "react";
import { Info } from "lucide-react";
import type { FinOpsKpiMetric, FinOpsProvenanceMap } from "@/types";
import { kpiDisplay, statusBadgeClass, statusLabel, unresolvedSections } from "@/lib/finopsProvenance";

/** Banner listing every section of a module that is not backed by live or calculated data. */
export const ProvenanceBanner: React.FC<{ provenance?: FinOpsProvenanceMap | null }> = ({
  provenance,
}) => {
  const items = unresolvedSections(provenance);
  if (items.length === 0) return null;
  return (
    <div
      className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 text-xs text-amber-950 space-y-2"
      role="status"
      data-testid="provenance-banner"
    >
      <div className="flex items-center gap-2 font-bold">
        <Info className="w-4 h-4 text-amber-600 shrink-0" />
        <span>Some data on this page is not available from live Databricks sources</span>
      </div>
      <ul className="space-y-1.5">
        {items.map(([name, p]) => (
          <li key={name} className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold capitalize">{name.replace(/_/g, " ")}</span>
              <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${statusBadgeClass(p.classification)}`}>
                {statusLabel(p.classification)}
              </span>
              <span className="text-[10px] text-amber-800 font-mono">{p.source}</span>
            </div>
            {p.message && <span className="text-amber-900">{p.message}</span>}
            {p.requirement && (
              <span className="text-amber-800">
                <strong>To unblock:</strong> {p.requirement}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

export interface KpiCardSpec {
  key: string;
  label: string;
}

/** Grid of KPI cards rendered strictly from backend metrics (value, status badge, caveat). */
export const KpiCardGrid: React.FC<{
  kpis?: Record<string, FinOpsKpiMetric> | null;
  specs: KpiCardSpec[];
  onSelect: (key: string, metric: FinOpsKpiMetric) => void;
  loading?: boolean;
  error?: boolean;
  className?: string;
}> = ({ kpis, specs, onSelect, loading, error, className }) => (
  <div className={className ?? "grid grid-cols-2 md:grid-cols-4 gap-4"}>
    {specs.map(({ key, label }) => {
      const metric = kpis?.[key];
      return (
        <button
          key={key}
          type="button"
          disabled={!metric}
          title={metric?.value === null ? metric.reason || metric.caveats || undefined : metric?.source}
          onClick={() => metric && onSelect(key, metric)}
          className="bg-white border border-[#e5eaf1] rounded-xl p-4 shadow-2xs text-left cursor-pointer hover:border-blue-400 transition disabled:cursor-default"
        >
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] font-semibold text-[#667085]">{label}</div>
            {metric && (
              <span className={`text-[8px] px-1.5 py-0.5 rounded font-bold uppercase ${statusBadgeClass(metric.status)}`}>
                {statusLabel(metric.status)}
              </span>
            )}
          </div>
          <div
            className={`my-1 font-black text-[#182230] ${
              metric && metric.value === null ? "text-base text-slate-500" : "text-2xl"
            }`}
          >
            {kpiDisplay(metric, { loading, error })}
          </div>
          <div className="text-[10px] text-slate-500 line-clamp-2">
            {metric?.delta_label || metric?.caveats || metric?.source || ""}
          </div>
        </button>
      );
    })}
  </div>
);
