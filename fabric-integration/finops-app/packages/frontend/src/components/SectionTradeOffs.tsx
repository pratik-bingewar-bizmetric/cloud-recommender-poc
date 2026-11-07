"use client";

import React from "react";
import {
  Award,
  Shield,
  TrendingUp,
  Cpu,
  Clock,
  CheckCircle2,
  AlertTriangle,
  FileCheck2,
} from "lucide-react";
import { TradeOffAssessment, TradeOffDimension } from "@/types";

interface SectionTradeOffsProps {
  tradeOffs: TradeOffAssessment | null;
  assumptions: string[];
  limitations: string[];
}

export const SectionTradeOffs: React.FC<SectionTradeOffsProps> = ({
  tradeOffs,
  assumptions,
  limitations,
}) => {
  if (!tradeOffs) return null;

  const pillars: Array<{
    key: keyof Omit<TradeOffAssessment, "summary">;
    title: string;
    subtitle: string;
    icon: React.ReactNode;
    barColor: string;
    badgeBg: string;
  }> = [
    {
      key: "cost_efficiency",
      title: "Cost Efficiency",
      subtitle: "FinOps & resource right-sizing",
      icon: <Award className="w-4 h-4 text-emerald-600" />,
      barColor: "bg-emerald-600",
      badgeBg: "bg-emerald-50 text-emerald-700 border-emerald-200",
    },
    {
      key: "security_compliance",
      title: "Security & Compliance",
      subtitle: "Identity, encryption & network isolation",
      icon: <Shield className="w-4 h-4 text-blue-600" />,
      barColor: "bg-blue-600",
      badgeBg: "bg-blue-50 text-blue-700 border-blue-200",
    },
    {
      key: "reliability_resilience",
      title: "Reliability & Resilience",
      subtitle: "Fault domains, failover & backup RPO/RTO",
      icon: <Cpu className="w-4 h-4 text-indigo-600" />,
      barColor: "bg-indigo-600",
      badgeBg: "bg-indigo-50 text-indigo-700 border-indigo-200",
    },
    {
      key: "scalability_performance",
      title: "Scalability & Performance",
      subtitle: "Elasticity, concurrency & throughput",
      icon: <TrendingUp className="w-4 h-4 text-cyan-600" />,
      barColor: "bg-cyan-600",
      badgeBg: "bg-cyan-50 text-cyan-800 border-cyan-200",
    },
    {
      key: "operational_complexity",
      title: "Operational Simplicity",
      subtitle: "Managed PaaS vs maintenance overhead",
      icon: <Clock className="w-4 h-4 text-amber-600" />,
      barColor: "bg-amber-500",
      badgeBg: "bg-amber-50 text-amber-800 border-amber-200",
    },
  ];

  // Calculate arithmetic average of the 5 actual backend scores for executive display
  const validScores = pillars
    .map((p) => (tradeOffs[p.key] as TradeOffDimension | undefined)?.score)
    .filter((s): s is number => typeof s === "number");
  const averageScore =
    validScores.length > 0
      ? Math.round(validScores.reduce((a, b) => a + b, 0) / validScores.length)
      : null;

  return (
    <section
      id="section-assessment"
      className="scroll-mt-28 bg-white rounded-2xl border border-slate-200/90 shadow-card p-5 sm:p-6 lg:p-7 mb-6 transition-shadow"
    >
      {/* Header Row */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-5 border-b border-slate-100 gap-3">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl bg-blue-50 border border-blue-200/70 text-blue-700 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
            05
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight">
                Well-Architected 5-Pillar Assessment
              </h2>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-medium">
                <FileCheck2 className="w-3 h-3 text-blue-600" />
                Trade-Off Scorecard
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Multi-dimensional architectural review across cost, security, reliability, performance, and operations.
            </p>
          </div>
        </div>

        {averageScore !== null && (
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-slate-900 text-white text-xs self-start sm:self-auto">
            <span className="text-slate-300 font-medium">Composite Index:</span>
            <span className="font-mono font-bold text-sm">{averageScore}/100</span>
          </div>
        )}
      </div>

      {/* Executive Summary Banner */}
      {tradeOffs.summary && (
        <div className="mb-5 p-4 bg-slate-50/80 border border-slate-200/90 rounded-xl text-xs leading-relaxed text-slate-700">
          <span className="text-slate-900 font-semibold block mb-1">
            Executive Architectural Summary
          </span>
          {tradeOffs.summary}
        </div>
      )}

      {/* 5-Pillar Scorecard Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3.5 mb-6">
        {pillars.map((pillar) => {
          const dimension = tradeOffs[pillar.key] as TradeOffDimension;
          if (!dimension) return null;

          return (
            <div
              key={pillar.key}
              className="p-4 rounded-xl border border-slate-200/90 bg-slate-50/50 hover:bg-white hover:border-slate-300 transition flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="p-2 rounded-lg bg-white border border-slate-200/80 shadow-2xs">
                    {pillar.icon}
                  </div>
                  <span
                    className={`text-xs font-bold font-mono px-2 py-0.5 rounded-md border ${pillar.badgeBg}`}
                  >
                    {dimension.score}/100
                  </span>
                </div>

                <h3 className="text-xs font-semibold text-slate-900">
                  {pillar.title}
                </h3>
                <p className="text-[10px] text-slate-400 mb-2.5">
                  {pillar.subtitle}
                </p>

                {/* Progress Bar */}
                <div
                  role="progressbar"
                  aria-valuenow={dimension.score}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${pillar.title} score`}
                  className="w-full bg-slate-200/80 h-1.5 rounded-full overflow-hidden mb-3"
                >
                  <div
                    className={`${pillar.barColor} h-full rounded-full transition-all duration-300`}
                    style={{
                      width: `${Math.min(100, Math.max(5, dimension.score))}%`,
                    }}
                  />
                </div>

                <p className="text-[11px] text-slate-600 leading-relaxed">
                  {dimension.assessment}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Assumptions & Known Limitations / Risk Factors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-slate-100 text-xs">
        {/* Verified Design Assumptions */}
        <div className="p-4 bg-emerald-50/30 rounded-xl border border-emerald-200/80">
          <div className="font-semibold text-slate-900 mb-2.5 flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>Explicit Architectural Assumptions</span>
          </div>
          {assumptions && assumptions.length > 0 ? (
            <ul className="space-y-1.5 text-slate-700">
              {assumptions.map((a, idx) => (
                <li key={idx} className="flex items-start gap-2 leading-relaxed">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-slate-500 italic">
              Standard single-region deployment assumptions apply.
            </div>
          )}
        </div>

        {/* Known Limitations & Risk Factors */}
        <div className="p-4 bg-amber-50/40 rounded-xl border border-amber-200/80">
          <div className="font-semibold text-slate-900 mb-2.5 flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>Known Limitations &amp; Risk Factors</span>
          </div>
          {limitations && limitations.length > 0 ? (
            <ul className="space-y-1.5 text-slate-700">
              {limitations.map((l, idx) => (
                <li key={idx} className="flex items-start gap-2 leading-relaxed">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                  <span>{l}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-slate-500 italic">
              No critical scaling blockers identified for current tier.
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
