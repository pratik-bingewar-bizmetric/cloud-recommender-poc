"use client";

import React, { useState } from "react";
import {
  X,
  ShieldCheck,
  CheckCircle2,
  Sparkles,
  FileSearch,
  Activity,
  RefreshCw,
} from "lucide-react";
import { AnomalyItemData } from "@/types";
import { updateFinOpsAnomalyStatus } from "@/lib/api";

interface AnomalyDetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  anomaly: AnomalyItemData | null;
  onStatusUpdated?: (anomalyId: string, newStatus: string) => void;
}

export const AnomalyDetailDrawer: React.FC<AnomalyDetailDrawerProps> = ({
  isOpen,
  onClose,
  anomaly,
  onStatusUpdated,
}) => {
  const [currentStatus, setCurrentStatus] = useState<string>(anomaly?.status || "New");
  const [isUpdating, setIsUpdating] = useState<boolean>(false);
  const [updateError, setUpdateError] = useState<string | null>(null);

  React.useEffect(() => {
    if (anomaly?.status) {
      setCurrentStatus(anomaly.status);
    }
  }, [anomaly?.id, anomaly?.status]);

  if (!isOpen || !anomaly) return null;

  const handleStatusChange = async (newStatus: string) => {
    setIsUpdating(true);
    setUpdateError(null);
    try {
      await updateFinOpsAnomalyStatus(anomaly.id, newStatus);
      setCurrentStatus(newStatus);
      if (onStatusUpdated) {
        onStatusUpdated(anomaly.id, newStatus);
      }
    } catch (err) {
      setUpdateError(err instanceof Error ? err.message : "Failed to update anomaly status");
    } finally {
      setIsUpdating(false);
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity.toLowerCase()) {
      case "critical":
        return "bg-rose-100 text-rose-800 border-rose-300";
      case "high":
        return "bg-amber-100 text-amber-800 border-amber-300";
      case "medium":
        return "bg-yellow-100 text-yellow-800 border-yellow-300";
      default:
        return "bg-slate-100 text-slate-800 border-slate-300";
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-navy-950/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="relative w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col z-10 overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-5 border-b border-slate-200 bg-slate-50 flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Forensic Anomaly Investigation
              </span>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${getSeverityBadge(anomaly.severity)}`}>
                {anomaly.severity} Severity
              </span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-slate-200 text-slate-700">
                {anomaly.id}
              </span>
            </div>
            <h3 className="text-base font-bold text-navy-900 tracking-tight">{anomaly.signal}</h3>
            <p className="text-xs text-slate-500 font-mono">Resource: {anomaly.resource}</p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-navy-900 hover:bg-slate-200 transition"
            aria-label="Close drawer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body (10 Forensic Sections) */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* SECTION 1: Summary & Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
              <span className="text-[10px] uppercase font-bold text-slate-400 block">Baseline</span>
              <span className="text-sm font-bold text-navy-900 mt-0.5 block">{anomaly.baseline}</span>
            </div>
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200">
              <span className="text-[10px] uppercase font-bold text-rose-600 block">Observed Spike</span>
              <span className="text-sm font-bold text-rose-900 mt-0.5 block">{anomaly.observed}</span>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
              <span className="text-[10px] uppercase font-bold text-slate-400 block">Deviation</span>
              <span className="text-sm font-bold text-navy-900 mt-0.5 block">
                {anomaly.percentage_deviation || "n/a"}
              </span>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
              <span className="text-[10px] uppercase font-bold text-slate-400 block">Est. Impact</span>
              <span className="text-sm font-bold text-rose-700 mt-0.5 block">{anomaly.estimated_impact}</span>
            </div>
          </div>

          {/* SECTION 2: Interactive Lifecycle Classifier */}
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Investigation Lifecycle Status
              </span>
              {isUpdating && (
                <span className="text-[11px] text-slate-500 flex items-center gap-1">
                  <RefreshCw className="w-3 h-3 animate-spin text-brand-600" />
                  Updating...
                </span>
              )}
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {["New", "Investigating", "Acknowledged", "Resolved", "False positive"].map((st) => (
                <button
                  key={st}
                  type="button"
                  disabled={isUpdating}
                  onClick={() => handleStatusChange(st)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    currentStatus.toLowerCase() === st.toLowerCase()
                      ? "bg-navy-900 text-white shadow-2xs"
                      : "bg-white border border-slate-300 text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>

            {updateError && (
              <p className="text-[11px] text-rose-600 mt-1">{updateError}</p>
            )}
          </div>

          {/* SECTION 3: Grounded AI Explanation */}
          <div className="p-4 rounded-xl border border-brand-200 bg-brand-50/40 space-y-2">
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-brand-600" />
              Grounded AI Root-Cause Narrative
            </h4>
            <p className="text-xs text-slate-700 leading-relaxed">
              {anomaly.ai_explanation ||
                "No root-cause narrative is available. The detector only reports a statistical deviation; the cause is not inferred."}
            </p>
          </div>

          {/* SECTION 4: Ranked Candidate Root Causes */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
              <FileSearch className="w-4 h-4 text-sky-600" />
              Candidate Root-Cause Hypotheses
            </h4>
            <div className="space-y-2">
              {(anomaly.root_cause_hypotheses && anomaly.root_cause_hypotheses.length > 0
                ? anomaly.root_cause_hypotheses
                : [anomaly.likely_cause]
              ).map((hyp, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-lg border border-slate-200 bg-white flex items-start gap-2.5 text-xs"
                >
                  <span className="w-5 h-5 rounded-full bg-slate-100 text-slate-700 font-bold flex items-center justify-center shrink-0 text-[11px]">
                    {idx + 1}
                  </span>
                  <span className="text-slate-800">{hyp}</span>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 5: Detection Methodology & Confidence */}
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-2 text-xs">
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
              Detection Methodology &amp; Mathematical Rigor
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
              <div>
                <span className="text-slate-500 block">Methodology:</span>
                <span className="font-semibold text-navy-900">
                  {anomaly.detection_methodology || "n/a"}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Confidence Level:</span>
                <span className="font-semibold text-slate-700">{anomaly.confidence || "n/a"}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Detection Timestamp:</span>
                <span className="font-semibold text-navy-900">{anomaly.detected}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Workspace ID:</span>
                <span className="font-mono font-semibold text-navy-900">{anomaly.workspace_id || "n/a"}</span>
              </div>
            </div>
          </div>

          {/* SECTION 6: Historical Trend Timeline */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-brand-600" />
              Historical Daily Spend (list-price basis)
            </h4>
            <div className="p-3 rounded-xl border border-slate-200 bg-white">
              <div className="grid grid-cols-7 gap-1 text-center text-xs">
                {(anomaly.historical_trend || []
                ).map((day, idx) => (
                  <div
                    key={idx}
                    className={`p-2 rounded-lg ${
                      idx === (anomaly.historical_trend?.length ?? 0) - 1 ? "bg-rose-100 border border-rose-300" : "bg-slate-50"
                    }`}
                  >
                    <span className="text-[10px] text-slate-500 block font-semibold">{day.date}</span>
                    <span
                      className={`text-xs font-bold mt-1 block ${
                        idx === (anomaly.historical_trend?.length ?? 0) - 1 ? "text-rose-700" : "text-slate-800"
                      }`}
                    >
                      ${day.spend.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* SECTION 7: SKU Contribution Breakdown */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
              SKU &amp; Meter Contribution Breakdown
            </h4>
            <div className="border border-slate-200 rounded-xl overflow-hidden text-xs">
              <table className="w-full text-left">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="py-2 px-3">Contributing Meter SKU</th>
                    <th className="py-2 px-3 text-right">Share</th>
                    <th className="py-2 px-3 text-right">Spike Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {(anomaly.sku_contribution || []
                  ).map((sku, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/80">
                      <td className="py-2 px-3 font-medium text-navy-900">{sku.sku}</td>
                      <td className="py-2 px-3 text-right text-slate-600">{sku.pct}%</td>
                      <td className="py-2 px-3 text-right font-semibold text-rose-700">{sku.amount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* SECTION 8: Related Workloads & Client Identifiers */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
              Associated Workloads &amp; Consumers
            </h4>
            <div className="flex items-center gap-2 flex-wrap text-xs">
              {(anomaly.related_workloads || []).map(
                (w, idx) => (
                  <span
                    key={idx}
                    className="px-2.5 py-1 rounded-lg bg-slate-100 border border-slate-200 font-mono text-[11px] text-slate-700"
                  >
                    {w}
                  </span>
                )
              )}
            </div>
          </div>

          {/* SECTION 9: Recommended Corrective Action */}
          <div className="p-4 rounded-xl border border-emerald-200 bg-emerald-50/60 space-y-2">
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              Recommended Corrective Action
            </h4>
            <p className="text-xs text-slate-700 leading-relaxed">
              {anomaly.recommended_action ||
                "Review the contributing SKUs and workloads for this date. No automated remediation is suggested."}
            </p>
            <div className="pt-2 border-t border-emerald-200 flex justify-between items-center text-xs">
              <span className="text-slate-600">Potential Savings:</span>
              <span className="font-bold text-emerald-800">
                {anomaly.potential_savings || "Not calculable"}
              </span>
            </div>
          </div>

          {/* SECTION 10: Verification Procedure */}
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-2 text-xs">
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
              Post-Remediation Verification Procedure
            </h4>
            <p className="text-[11px] text-slate-600 leading-relaxed">
              {anomaly.verification_procedure ||
                "Re-check daily spend in system.billing.usage after any change and confirm it returns to the trailing baseline."}
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span className="flex items-center gap-1.5 font-mono text-[11px]">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            Forensic audit record
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-semibold transition"
          >
            Close Investigation
          </button>
        </div>
      </div>
    </div>
  );
};
