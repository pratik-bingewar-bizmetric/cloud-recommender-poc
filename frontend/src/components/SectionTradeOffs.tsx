"use client";

import React from "react";
import {
  Award,
  Shield,
  TrendingUp,
  Cpu,
  Clock,
  CheckCircle,
  AlertTriangle,
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
    icon: React.ReactNode;
    color: string;
    barColor: string;
  }> = [
    {
      key: "cost_efficiency",
      title: "Cost Efficiency",
      icon: <Award className="w-4 h-4 text-emerald-600" />,
      color: "border-emerald-200 bg-emerald-50/40",
      barColor: "bg-emerald-500",
    },
    {
      key: "security_compliance",
      title: "Security & Compliance",
      icon: <Shield className="w-4 h-4 text-blue-600" />,
      color: "border-blue-200 bg-blue-50/40",
      barColor: "bg-blue-500",
    },
    {
      key: "reliability_resilience",
      title: "Reliability & Resilience",
      icon: <Cpu className="w-4 h-4 text-purple-600" />,
      color: "border-purple-200 bg-purple-50/40",
      barColor: "bg-purple-500",
    },
    {
      key: "scalability_performance",
      title: "Scalability & Performance",
      icon: <TrendingUp className="w-4 h-4 text-cyan-600" />,
      color: "border-cyan-200 bg-cyan-50/40",
      barColor: "bg-cyan-500",
    },
    {
      key: "operational_complexity",
      title: "Operational Complexity",
      icon: <Clock className="w-4 h-4 text-amber-600" />,
      color: "border-amber-200 bg-amber-50/40",
      barColor: "bg-amber-500",
    },
  ];

  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="pb-4 mb-5 border-b border-slate-100">
        <h2 className="text-lg font-bold text-slate-900 flex items-center">
          <span className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center mr-2">
            E
          </span>
          Architecture Analysis & 5-Pillar Trade-Offs
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Multi-dimensional architectural assessment evaluating trade-offs across cloud architecture pillars.
        </p>
      </div>

      {/* Trade-Off Summary */}
      {tradeOffs.summary && (
        <div className="mb-5 p-4 bg-slate-50 border border-slate-200 rounded-lg text-xs leading-relaxed text-slate-700">
          <strong className="text-slate-900 font-semibold block mb-1">
            Executive Trade-Off Assessment:
          </strong>
          {tradeOffs.summary}
        </div>
      )}

      {/* 5 Architectural Pillars Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        {pillars.map((pillar) => {
          const dimension = tradeOffs[pillar.key] as TradeOffDimension;
          if (!dimension) return null;

          return (
            <div
              key={pillar.key}
              className={`p-4 rounded-xl border ${pillar.color} flex flex-col justify-between`}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-1.5 text-xs font-bold text-slate-900">
                    {pillar.icon}
                    <span>{pillar.title}</span>
                  </div>
                  <span className="text-xs font-bold font-mono px-2 py-0.5 rounded bg-white border border-slate-200 shadow-2xs">
                    {dimension.score}/100
                  </span>
                </div>

                <div className="w-full bg-white h-2 rounded-full overflow-hidden mb-2.5 border border-slate-200">
                  <div
                    className={`${pillar.barColor} h-full rounded-full transition-all duration-500`}
                    style={{ width: `${Math.min(100, Math.max(5, dimension.score))}%` }}
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

      {/* Assumptions & Limitations / Risks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-slate-100 text-xs">
        {/* Assumptions */}
        <div className="p-4 bg-slate-50 rounded-lg border border-slate-200">
          <div className="font-bold text-slate-900 mb-2 flex items-center">
            <CheckCircle className="w-4 h-4 text-emerald-600 mr-1.5" />
            Architectural Assumptions:
          </div>
          {assumptions && assumptions.length > 0 ? (
            <ul className="list-disc list-inside space-y-1 text-slate-600">
              {assumptions.map((a, idx) => (
                <li key={idx}>{a}</li>
              ))}
            </ul>
          ) : (
            <div className="text-slate-400 italic">Standard single-region deployment assumptions apply.</div>
          )}
        </div>

        {/* Known Limitations */}
        <div className="p-4 bg-slate-50 rounded-lg border border-slate-200">
          <div className="font-bold text-slate-900 mb-2 flex items-center">
            <AlertTriangle className="w-4 h-4 text-amber-600 mr-1.5" />
            Known Limitations & Risk Factors:
          </div>
          {limitations && limitations.length > 0 ? (
            <ul className="list-disc list-inside space-y-1 text-slate-600">
              {limitations.map((l, idx) => (
                <li key={idx}>{l}</li>
              ))}
            </ul>
          ) : (
            <div className="text-slate-400 italic">No critical scaling blockers identified for current tier.</div>
          )}
        </div>
      </div>
    </section>
  );
};

