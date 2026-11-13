"use client";

import React from "react";
import { X, ShieldCheck, Calculator, Layers, AlertTriangle } from "lucide-react";
import { FinOpsKpiMetric } from "@/types";
import { statusBadgeClass, statusLabel } from "@/lib/finopsProvenance";

interface KpiDetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  kpiKey: string | null;
  kpi: FinOpsKpiMetric | null;
  workspaceId?: string;
}

const Row: React.FC<{ label: string; value?: React.ReactNode }> = ({ label, value }) => (
  <div className="flex justify-between gap-4 py-2 border-b border-slate-100 text-xs">
    <span className="text-slate-500 shrink-0">{label}</span>
    <span className="text-right font-medium text-navy-900 break-words min-w-0">{value ?? "n/a"}</span>
  </div>
);

/**
 * KPI lineage drawer. Everything shown comes from the KPI metric returned by the backend
 * (value, status, formula, source, caveats). Nothing is authored client-side.
 */
export const KpiDetailDrawer: React.FC<KpiDetailDrawerProps> = ({
  isOpen,
  onClose,
  kpiKey,
  kpi,
  workspaceId,
}) => {
  if (!isOpen || !kpi || !kpiKey) return null;

  const title = kpiKey.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  const hasValue = kpi.value !== null;
  const caveat = kpi.caveats || kpi.limitations;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40 backdrop-blur-2xs" role="dialog" aria-label={`${title} lineage`}>
      <div className="w-full max-w-md bg-white h-full shadow-2xl flex flex-col">
        <div className="p-5 border-b border-slate-200 flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">KPI lineage</div>
            <h3 className="text-base font-bold text-navy-900">{title}</h3>
            <span className={`mt-1 inline-block text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${statusBadgeClass(kpi.status)}`}>
              {statusLabel(kpi.status)}
            </span>
          </div>
          <button type="button" onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100" aria-label="Close">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
            <div className={`font-black text-navy-900 ${hasValue ? "text-3xl" : "text-lg text-slate-600"}`}>
              {kpi.formatted_value}
            </div>
            {kpi.delta_label && <div className="text-xs text-slate-600 mt-1">{kpi.delta_label}</div>}
          </div>

          {caveat && (
            <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <span>{caveat}</span>
            </div>
          )}

          <div>
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5 mb-1">
              <Calculator className="w-4 h-4 text-brand-600" />
              Calculation
            </h4>
            <Row label="Formula" value={kpi.formula ? <code className="text-[11px]">{kpi.formula}</code> : "Not applicable"} />
            <Row label="Aggregation" value={kpi.aggregation_method} />
            <Row label="Unit" value={kpi.unit} />
            <Row label="Records aggregated" value={kpi.record_count?.toLocaleString()} />
            <Row label="Price coverage" value={`${Math.round(kpi.coverage * 100)}%`} />
          </div>

          <div>
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5 mb-1">
              <Layers className="w-4 h-4 text-brand-600" />
              Source &amp; freshness
            </h4>
            <Row label="Source" value={kpi.source} />
            <Row label="Data source" value={kpi.data_source} />
            <Row label="Workspace" value={kpi.workspace_id || workspaceId} />
            <Row label="Resource scope" value={kpi.resource_id ? `${kpi.resource_type ?? "resource"}: ${kpi.resource_id}` : "Entire workspace"} />
            <Row label="Period" value={kpi.period_start ? `${kpi.period_start} to ${kpi.period_end ?? "n/a"}` : undefined} />
            <Row label="Last calculated" value={kpi.last_refreshed ? new Date(kpi.last_refreshed).toISOString().replace("T", " ").slice(0, 19) + " UTC" : undefined} />
            <Row label="Calculation version" value={kpi.calculation_version} />
          </div>
        </div>

        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span className="flex items-center gap-1.5 font-mono text-[11px]">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            Read-only lineage
          </span>
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-semibold transition">
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
