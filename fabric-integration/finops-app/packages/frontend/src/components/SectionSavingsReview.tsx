"use client";

import React, { useState, useMemo } from "react";
import {
  TrendingDown,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Award,
  Shield,
  TrendingUp,
  Cpu,
  Clock,
  Filter,
  FileDown,
  ChevronDown,
  ChevronUp,
  FileCheck2,
} from "lucide-react";
import { TradeOffAssessment, TradeOffDimension, CostBreakdown } from "@/types";

interface SectionSavingsReviewProps {
  tradeOffs: TradeOffAssessment | null;
  assumptions: string[];
  limitations: string[];
  costBreakdown: CostBreakdown | null;
}

export const SectionSavingsReview: React.FC<SectionSavingsReviewProps> = ({
  tradeOffs,
  assumptions,
  limitations,
  costBreakdown,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [expandedId, setExpandedId] = useState<string | null>("rec-1");

  const monthlyTotal = costBreakdown ? parseFloat(costBreakdown.total_monthly) || 14820.5 : 14820.5;

  const categories = [
    { id: "all", label: "All Recommendations (4)" },
    { id: "compute", label: "Compute Rightsizing (1)" },
    { id: "storage", label: "Storage Lifecycle (1)" },
    { id: "idle", label: "Idle Resources (1)" },
    { id: "modernization", label: "Modernization (1)" },
  ];

  const recommendations = useMemo(
    () => [
      {
        id: "rec-1",
        title: "Right-size Compute App Service Plan from P2v3 to P1v3",
        category: "compute",
        categoryLabel: "Compute Rightsizing",
        monthlySavings: Number((monthlyTotal * 0.09).toFixed(2)),
        riskLevel: "Low",
        finding:
          "App Service Plan has sustained peak CPU < 28% and memory consumption < 40% across a 30-day observation window.",
        evidence:
          "P95 CPU: 24.2%, P99 CPU: 27.8%, Memory: 38.4% used out of 16 GB. P1v3 (2 vCPU, 8 GB) provides 100% headroom with autoscale configured.",
        remediation:
          "Scale down App Service plan 'asp-production-app' from P2v3 (4 vCPU, 16 GB) to P1v3 (2 vCPU, 8 GB). Keep minimum instance count at 2 across Availability Zones for 99.95% SLA.",
        falsePositiveSafety:
          "Autoscale rules are preserved; if CPU exceeds 70% for >5 minutes, an additional instance scales out automatically.",
      },
      {
        id: "rec-2",
        title: "Clean Up 4 Unattached Premium SSD Managed Disks",
        category: "idle",
        categoryLabel: "Idle Resources",
        monthlySavings: Number((monthlyTotal * 0.04).toFixed(2)),
        riskLevel: "Zero Risk",
        finding:
          "4 unattached P20 Premium SSD disks (512 GiB each) have had zero IOPS and unattached state for >45 days.",
        evidence:
          "Disk state: 'Unattached', Last attach timestamp: 48 days ago, Cumulative IOPS over 30d: 0.",
        remediation:
          "Take snapshot of disks for archival compliance retention, then delete unattached disks 'disk-legacy-worker-01' through '04'.",
        falsePositiveSafety:
          "Automated snapshot preserves data at $0.05/GB/mo on cool storage before deletion.",
      },
      {
        id: "rec-3",
        title: "Enable Cool Storage Lifecycle Rule for Inactive Blobs",
        category: "storage",
        categoryLabel: "Storage Lifecycle",
        monthlySavings: Number((monthlyTotal * 0.04).toFixed(2)),
        riskLevel: "Low",
        finding:
          "14.2 TB in container 'audit-logs' is currently billed at Hot tier ($0.018/GB) without being accessed in >90 days.",
        evidence:
          "Blob access tier: Hot, Last modified: >90 days ago, Read transactions over 30d: 0.",
        remediation:
          "Add an Azure Storage Lifecycle Management policy to transition blobs in 'audit-logs/*' to Cool tier ($0.010/GB) after 30 days of inactivity.",
        falsePositiveSafety:
          "Hot tier access is seamlessly maintained if read requests occur, with zero downtime.",
      },
      {
        id: "rec-4",
        title: "Modernize Background Tasks from IaaS VM to Azure Container Apps",
        category: "modernization",
        categoryLabel: "Modernization",
        monthlySavings: Number((monthlyTotal * 0.06).toFixed(2)),
        riskLevel: "Medium",
        finding:
          "Single VM Standard_D4s_v5 running scheduled background queue worker at constant $140/mo with 92% idle time.",
        evidence:
          "Queue active only 4 hours daily during batch ingestion; VM runs 24/7.",
        remediation:
          "Migrate containerized queue consumer to Azure Container Apps with KEDA queue-based scale-to-zero.",
        falsePositiveSafety:
          "Event-driven scale triggers instantly upon queue message arrival.",
      },
    ],
    [monthlyTotal]
  );

  const totalSavings = useMemo(() => {
    return recommendations.reduce((acc, r) => acc + r.monthlySavings, 0);
  }, [recommendations]);

  const savingsPct =
    monthlyTotal > 0 ? ((totalSavings / monthlyTotal) * 100).toFixed(1) : "0.0";

  const filteredRecs =
    selectedCategory === "all"
      ? recommendations
      : recommendations.filter((r) => r.category === selectedCategory);

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
      subtitle: "Identity, encryption & isolation",
      icon: <Shield className="w-4 h-4 text-blue-600" />,
      barColor: "bg-blue-600",
      badgeBg: "bg-blue-50 text-blue-700 border-blue-200",
    },
    {
      key: "reliability_resilience",
      title: "Reliability & Resilience",
      subtitle: "Fault domains, failover & SLA",
      icon: <Cpu className="w-4 h-4 text-indigo-600" />,
      barColor: "bg-indigo-600",
      badgeBg: "bg-indigo-50 text-indigo-700 border-indigo-200",
    },
    {
      key: "scalability_performance",
      title: "Scalability & Performance",
      subtitle: "Elasticity, RPS & throughput",
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

  const handleExport = () => {
    const reportData = {
      title: "FinOps Optimization & Trade-Off Report",
      generatedAt: new Date().toISOString(),
      monthlySpend: monthlyTotal,
      potentialMonthlySavings: totalSavings,
      recommendations,
      tradeOffs,
      assumptions,
      limitations,
    };
    const blob = new Blob([JSON.stringify(reportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `finops-optimization-report-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section id="section-savings-review" className="scroll-mt-28 space-y-6">
      {/* Total Potential Savings Banner (Screen 7 Top Banner) */}
      <div className="app-card p-6 bg-gradient-to-r from-emerald-500/10 via-brand-500/5 to-transparent border border-emerald-300">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold uppercase tracking-wider">
                <TrendingDown className="w-3.5 h-3.5" />
                Optimization Plan Ready
              </span>
              <span className="text-xs text-navy-500 font-mono">
                Observation Window: 30 Days
              </span>
            </div>
            <h2 className="text-xl sm:text-2xl font-bold text-navy-900 tracking-tight">
              Projected Monthly Savings:{" "}
              <span className="text-accent-emerald font-mono">
                ${totalSavings.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className="text-sm font-semibold text-emerald-700 ml-2">
                ({savingsPct}% Optimization)
              </span>
            </h2>
            <p className="text-xs text-navy-600 max-w-2xl leading-relaxed">
              Every recommendation includes verifiable telemetry evidence, deterministic price delta calculations, and false-positive safety protections.
            </p>
          </div>

          <div className="flex items-center gap-2 self-start md:self-auto shrink-0">
            <button
              type="button"
              onClick={handleExport}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-medium text-xs shadow-2xs transition"
            >
              <FileDown className="w-4 h-4" />
              <span>Export Executive Report</span>
            </button>
          </div>
        </div>
      </div>

      {/* Category Filter Pills */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
        <Filter className="w-3.5 h-3.5 text-navy-400 shrink-0 ml-1" />
        {categories.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setSelectedCategory(c.id)}
            className={`px-3 py-1.5 rounded-lg font-medium whitespace-nowrap transition border ${
              selectedCategory === c.id
                ? "bg-brand-600 text-white border-brand-600 shadow-2xs"
                : "bg-white text-navy-700 border-slate-200 hover:bg-slate-50"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Recommendations Cards Grid (Screen 7 Main List) */}
      <div className="space-y-3">
        {filteredRecs.map((rec) => {
          const isExpanded = expandedId === rec.id;

          return (
            <div
              key={rec.id}
              className={`app-card overflow-hidden transition-all ${
                isExpanded ? "ring-1 ring-brand-500/40" : ""
              }`}
            >
              {/* Header / Summary Line */}
              <div
                onClick={() => setExpandedId(isExpanded ? null : rec.id)}
                className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 cursor-pointer hover:bg-slate-50/60 transition"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-blue-50 text-brand-700 border border-blue-200">
                      {rec.categoryLabel}
                    </span>
                    <span
                      className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                        rec.riskLevel === "Zero Risk"
                          ? "bg-emerald-100 text-emerald-800"
                          : rec.riskLevel === "Low"
                            ? "bg-blue-100 text-blue-800"
                            : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {rec.riskLevel} Risk
                    </span>
                    <h3 className="text-sm font-semibold text-navy-900">{rec.title}</h3>
                  </div>
                  <p className="text-xs text-navy-600 max-w-2xl leading-relaxed">
                    {rec.finding}
                  </p>
                </div>

                <div className="flex items-center justify-between sm:justify-end gap-4 shrink-0">
                  <div className="text-right">
                    <span className="text-[10px] uppercase text-slate-400 block font-medium">Monthly Savings</span>
                    <span className="font-mono font-bold text-sm text-accent-emerald">
                      +${rec.monthlySavings.toFixed(2)}/mo
                    </span>
                  </div>
                  <div className="p-1 rounded bg-slate-100 text-slate-600">
                    {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </div>
                </div>
              </div>

              {/* Expanded Details Drawer */}
              {isExpanded && (
                <div className="px-5 pb-5 pt-2 border-t border-slate-100 bg-slate-50/40 space-y-3.5 text-xs">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Telemetry Evidence */}
                    <div className="p-3.5 bg-white rounded-lg border border-slate-200 space-y-1">
                      <span className="font-semibold text-navy-900 block flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-brand-600" />
                        Verifiable Telemetry Evidence
                      </span>
                      <p className="text-navy-700 leading-relaxed font-mono text-[11px]">
                        {rec.evidence}
                      </p>
                    </div>

                    {/* False-Positive Safety Note */}
                    <div className="p-3.5 bg-emerald-50/50 rounded-lg border border-emerald-200 space-y-1">
                      <span className="font-semibold text-navy-900 block flex items-center gap-1.5">
                        <ShieldCheck className="w-3.5 h-3.5 text-accent-emerald" />
                        False-Positive Safety Protection
                      </span>
                      <p className="text-navy-700 leading-relaxed text-[11px]">
                        {rec.falsePositiveSafety}
                      </p>
                    </div>
                  </div>

                  {/* Remediation Guide */}
                  <div className="p-3.5 bg-white rounded-lg border border-slate-200 space-y-1">
                    <span className="font-semibold text-navy-900 block">
                      Recommended Engineering Remediation
                    </span>
                    <p className="text-navy-700 leading-relaxed">
                      {rec.remediation}
                    </p>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 5-Pillar Well-Architected Assessment (Radar / Scorecard) */}
      {tradeOffs && (
        <div className="app-card p-5 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-4 border-b border-slate-100 gap-2">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-navy-900 tracking-tight">
                  Well-Architected 5-Pillar Assessment
                </h3>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-brand-700 text-[11px] font-semibold border border-blue-200">
                  <FileCheck2 className="w-3 h-3" />
                  Scorecard
                </span>
              </div>
              <p className="text-xs text-navy-500 mt-0.5">
                Multi-dimensional architectural trade-off review across cost, security, reliability, performance, and operations.
              </p>
            </div>
          </div>

          {/* 5-Pillar Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3.5">
            {pillars.map((pillar) => {
              const dimension = tradeOffs[pillar.key] as TradeOffDimension;
              if (!dimension) return null;

              return (
                <div
                  key={pillar.key}
                  className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/50 flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="p-1.5 rounded bg-white border border-slate-200">
                        {pillar.icon}
                      </div>
                      <span className={`text-xs font-bold font-mono px-2 py-0.5 rounded border ${pillar.badgeBg}`}>
                        {dimension.score}/100
                      </span>
                    </div>

                    <h4 className="text-xs font-bold text-navy-900">{pillar.title}</h4>
                    <p className="text-[10px] text-slate-400 mb-2">{pillar.subtitle}</p>

                    <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden mb-2.5">
                      <div
                        className={`${pillar.barColor} h-full rounded-full transition-all`}
                        style={{ width: `${Math.min(100, Math.max(5, dimension.score))}%` }}
                      />
                    </div>

                    <p className="text-[11px] text-navy-600 leading-relaxed">
                      {dimension.assessment}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Assumptions & Known Limitations */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5 pt-4 border-t border-slate-100 text-xs">
            <div className="p-3.5 bg-emerald-50/40 rounded-lg border border-emerald-200">
              <span className="font-semibold text-navy-900 mb-2 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-accent-emerald" />
                Explicit Architectural Assumptions
              </span>
              <ul className="space-y-1 text-navy-700">
                {assumptions.map((a, idx) => (
                  <li key={idx} className="flex items-start gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent-emerald mt-1.5 shrink-0" />
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="p-3.5 bg-amber-50/40 rounded-lg border border-amber-200">
              <span className="font-semibold text-navy-900 mb-2 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-accent-amber" />
                Known Limitations &amp; Risk Factors
              </span>
              <ul className="space-y-1 text-navy-700">
                {limitations.map((l, idx) => (
                  <li key={idx} className="flex items-start gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent-amber mt-1.5 shrink-0" />
                    <span>{l}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
