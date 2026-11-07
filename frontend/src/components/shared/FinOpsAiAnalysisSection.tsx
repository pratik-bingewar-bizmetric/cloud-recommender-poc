"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Sparkles,
  ShieldCheck,
  TrendingUp,
  AlertTriangle,
  Zap,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  CheckCircle2,
  ArrowRight,
} from "lucide-react";
import { FinOpsAiAnalysis } from "@/types";
import { getFinOpsAiAnalysis } from "@/lib/api";

interface FinOpsAiAnalysisSectionProps {
  moduleId: string;
  workspaceId?: string;
  connectionId?: string;
  resourceId?: string;
  resourceType?: string;
  onNavigateToModule?: (targetModule: string) => void;
}

export const FinOpsAiAnalysisSection: React.FC<FinOpsAiAnalysisSectionProps> = ({
  moduleId,
  workspaceId = "642006393507276",
  connectionId = "databricks-azure-dev",
  resourceId,
  resourceType,
  onNavigateToModule,
}) => {
  const [analysis, setAnalysis] = useState<FinOpsAiAnalysis | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState<boolean>(true);

  const fetchAnalysis = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getFinOpsAiAnalysis(
        moduleId,
        connectionId,
        workspaceId,
        resourceId,
        resourceType
      );
      setAnalysis(data);
    } catch (err) {
      console.error(`Failed to fetch AI analysis for module ${moduleId}:`, err);
      setError(err instanceof Error ? err.message : "Failed to load AI intelligence");
    } finally {
      setIsLoading(false);
    }
  }, [moduleId, connectionId, workspaceId, resourceId, resourceType]);

  useEffect(() => {
    fetchAnalysis();
  }, [fetchAnalysis]);

  if (isLoading) {
    return (
      <div className="p-4 rounded-xl border border-brand-200 bg-brand-50/30 flex items-center justify-between text-xs text-brand-900 shadow-2xs">
        <div className="flex items-center gap-2">
          <RefreshCw className="w-4 h-4 animate-spin text-brand-600" />
          <span className="font-semibold">Synthesizing AI FinOps Telemetry for {moduleId}...</span>
        </div>
        <span className="text-[11px] text-slate-500 font-mono">system.billing.usage + REST Lineage</span>
      </div>
    );
  }

  if (error || !analysis) {
    return null; // Gracefully hide if unavailable
  }

  return (
    <div className="rounded-xl border border-brand-200 bg-gradient-to-br from-brand-50/60 via-white to-slate-50 shadow-2xs overflow-hidden">
      {/* Header Banner */}
      <div className="p-4 border-b border-brand-100 bg-brand-50/40 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-brand-600 text-white flex items-center justify-center shadow-2xs">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                AI FinOps Intelligence &amp; Cost Analysis
              </h3>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-brand-100 text-brand-800 border border-brand-200">
                {analysis.is_ai_live ? "Azure AI Foundry Live" : "Deterministic Engine Certified"}
              </span>
              <span className="text-[10px] font-semibold text-slate-500">
                Confidence: {(analysis.confidence_score * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-[11px] text-slate-500 font-mono mt-0.5">
              Workspace {workspaceId} · Verified System Tables Lineage
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchAnalysis}
            className="p-1 rounded text-slate-400 hover:text-navy-900 hover:bg-white transition"
            title="Refresh AI Analysis"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 rounded text-slate-400 hover:text-navy-900 hover:bg-white transition"
          >
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="p-5 space-y-4">
          {/* Executive Summary */}
          <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-1.5 shadow-2xs">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
              Executive Narrative
            </span>
            <p className="text-xs text-slate-700 leading-relaxed font-medium">
              {analysis.executive_summary}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Key Findings */}
            {analysis.important_findings.length > 0 && (
              <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-2.5 shadow-2xs">
                <span className="text-[10px] font-bold uppercase tracking-wider text-navy-900 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-brand-600" />
                  Key Operational Findings
                </span>
                <ul className="space-y-1.5 text-xs text-slate-600">
                  {analysis.important_findings.map((f, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-brand-600 font-bold mt-0.5">•</span>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Primary Cost Drivers */}
            {analysis.cost_drivers.length > 0 && (
              <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-2.5 shadow-2xs">
                <span className="text-[10px] font-bold uppercase tracking-wider text-navy-900 flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5 text-sky-600" />
                  Primary Spending Drivers
                </span>
                <ul className="space-y-1.5 text-xs text-slate-600">
                  {analysis.cost_drivers.map((d, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-sky-600 font-bold mt-0.5">•</span>
                      <span>{d}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Unusual Changes / Spikes Callout */}
          {analysis.unusual_changes.length > 0 && (
            <div className="p-3.5 rounded-xl border border-amber-200 bg-amber-50/60 text-xs text-amber-900 space-y-1">
              <div className="flex items-center gap-1.5 font-semibold text-[11px]">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                <span>Detected Telemetry Deviations &amp; Anomalies:</span>
              </div>
              <ul className="space-y-1 pl-5 list-disc text-[11px] text-amber-800">
                {analysis.unusual_changes.map((u, idx) => (
                  <li key={idx}>{u}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Targeted Optimization Opportunities */}
          {analysis.optimization_opportunities.length > 0 && (
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-navy-900 flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-emerald-600" />
                  Targeted Optimization Opportunities ({analysis.expected_savings})
                </span>
                {onNavigateToModule && (
                  <button
                    type="button"
                    onClick={() => onNavigateToModule("recommend")}
                    className="text-[11px] font-semibold text-brand-700 hover:text-brand-900 flex items-center gap-1"
                  >
                    <span>View Advisor</span>
                    <ArrowRight className="w-3 h-3" />
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {analysis.optimization_opportunities.map((opp, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl border border-slate-200 bg-white hover:border-brand-300 transition text-xs space-y-1.5 shadow-2xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-navy-900 truncate">{opp.title}</span>
                      <span className="font-extrabold text-emerald-700 shrink-0">
                        {opp.estimated_savings}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-600 line-clamp-2">{opp.description}</p>
                    <div className="flex items-center justify-between pt-1 border-t border-slate-100 text-[10px] text-slate-400">
                      <span>Effort: {opp.effort || "Low"} · Risk: {opp.risk || "Low"}</span>
                      <span>Confidence: {opp.confidence_pct || 90}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Zero-Execution Guardrail Footer */}
          <div className="pt-2 border-t border-slate-200 flex items-center justify-between text-[11px] text-slate-500">
            <span className="flex items-center gap-1.5 font-mono">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              Zero-execution guardrails enforced: human authorization required before changes
            </span>
            <span>Refreshed: {new Date(analysis.analysis_timestamp).toLocaleTimeString()}</span>
          </div>
        </div>
      )}
    </div>
  );
};
