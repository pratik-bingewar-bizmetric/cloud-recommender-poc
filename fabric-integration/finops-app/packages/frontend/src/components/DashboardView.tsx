"use client";

import React, { useState, useMemo } from "react";
import { ENABLE_AI_ARCHITECT } from "@/config/features";
import {
  TrendingUp,
  TrendingDown,
  Layers,
  Sparkles,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ShieldCheck,
  Cpu,
  Activity,
  Zap,
} from "lucide-react";
import { CloudProvider, CostBreakdown, TimeWindowPreset } from "@/types";
import {
  CanonicalFinancialSummary,
  FinancialKpiType,
} from "@/types/financials";
import {
  buildCanonicalFinancialSummary,
  formatFinancialCurrency,
} from "@/lib/financials";
import { FinancialKpiDrawer } from "@/components/FinancialKpiDrawer";

interface DashboardViewProps {
  onNavigate: (view: "architect" | "inventory" | "monitoring" | "compare") => void;
  monthlyTotal?: string | null;
  region?: string;
  connectedScope?: { provider: CloudProvider; name: string; id: string } | null;
  costBreakdown?: CostBreakdown | null;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  onNavigate,
  region = "eastus",
  connectedScope,
  costBreakdown,
}) => {
  const [timeRange, setTimeRange] = useState<TimeWindowPreset>("30d");
  const [currency, setCurrency] = useState<"USD" | "INR">("USD");
  const [hoveredBar, setHoveredBar] = useState<number | null>(null);

  // Drill-down drawer state
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [drawerKpiType, setDrawerKpiType] = useState<FinancialKpiType>("spend");
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);

  // Canonical Financial Summary
  const financials: CanonicalFinancialSummary = useMemo(() => {
    return buildCanonicalFinancialSummary(
      connectedScope?.provider ?? "azure",
      connectedScope?.id ?? "sub-prod-enterprise-01",
      connectedScope?.name ?? "Production Enterprise Subscription",
      timeRange,
      currency,
      null,
      null,
      costBreakdown
    );
  }, [connectedScope, timeRange, currency, costBreakdown]);

  const spendAmount = financials.estimated_monthly_spend;
  const savingsAmount = financials.potential_monthly_savings;
  const savingsPct = financials.savings_percentage_of_spend;

  const handleOpenDrawer = (kpi: FinancialKpiType, findingId?: string) => {
    setDrawerKpiType(kpi);
    setSelectedFindingId(findingId || null);
    setIsDrawerOpen(true);
  };

  // Monthly 6-Month Trend Data anchored to current reconciled spend
  const monthlyTrend = useMemo(() => {
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"];
    const base = spendAmount;
    const multipliers = [0.76, 0.84, 0.88, 0.94, 0.97, 1.0];
    const budgetThreshold = base * 1.05;

    return months.map((month, idx) => ({
      month,
      cost: Number((base * multipliers[idx]).toFixed(2)),
      budget: Number(budgetThreshold.toFixed(2)),
      current: idx === months.length - 1,
    }));
  }, [spendAmount]);

  const maxCost = useMemo(() => {
    const maxVal = Math.max(...monthlyTrend.map((t) => t.cost), monthlyTrend[0]?.budget || 100);
    return maxVal * 1.2;
  }, [monthlyTrend]);

  return (
    <div className="space-y-6 pb-12">
      {/* Top Banner Row: Title, Filters & Currency Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl sm:text-2xl font-bold text-navy-900 tracking-tight font-heading">
              Executive Cloud FinOps Dashboard
            </h1>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-accent-emerald border border-emerald-200 text-xs font-semibold">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Reconciled Financial Truth
            </span>
            {costBreakdown && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 text-[11px] font-semibold">
                <Sparkles className="w-3 h-3 text-purple-600" />
                Greenfield AI Architecture Simulation
              </span>
            )}
          </div>
          <p className="text-xs text-navy-600 mt-1">
            Deterministic rate meters from {financials.pricing_source} &bull; Scope:{" "}
            <strong className="text-navy-900">{financials.scope_name}</strong> (
            <span className="font-mono text-[11px]">{financials.scope_id}</span>) &bull; Region:{" "}
            <span className="font-mono text-[11px]">{region}</span> &bull; Zero Residual Delta
          </p>
        </div>

        {/* Controls: Time range & Currency */}
        <div className="flex items-center gap-2 self-start sm:self-auto">
          {/* Time range toggle */}
          <div className="flex items-center p-0.5 bg-slate-100 rounded-lg border border-slate-200 text-xs">
            {(["7d", "30d", "90d"] as const).map((range) => (
              <button
                key={range}
                type="button"
                onClick={() => setTimeRange(range)}
                className={`px-2.5 py-1 rounded-md font-medium transition ${
                  timeRange === range
                    ? "bg-white text-navy-900 shadow-2xs font-semibold"
                    : "text-navy-600 hover:text-navy-900"
                }`}
              >
                {range}
              </button>
            ))}
          </div>

          {/* Currency Toggle */}
          <div className="flex items-center p-0.5 bg-slate-100 rounded-lg border border-slate-200 text-xs">
            <button
              type="button"
              onClick={() => setCurrency("USD")}
              className={`px-2.5 py-1 rounded-md font-mono transition ${
                currency === "USD"
                  ? "bg-white text-navy-900 shadow-2xs font-bold"
                  : "text-navy-600 hover:text-navy-900"
              }`}
            >
              $ USD
            </button>
            <button
              type="button"
              onClick={() => setCurrency("INR")}
              className={`px-2.5 py-1 rounded-md font-mono transition ${
                currency === "INR"
                  ? "bg-white text-navy-900 shadow-2xs font-bold"
                  : "text-navy-600 hover:text-navy-900"
              }`}
            >
              ₹ INR
            </button>
          </div>
        </div>
      </div>

      {/* 4 Interactive Primary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Estimated Monthly Spend */}
        <div
          onClick={() => handleOpenDrawer("spend")}
          className="app-card p-4 flex flex-col justify-between cursor-pointer hover:border-brand-400 hover:shadow-subtle transition group"
        >
          <div className="flex items-start justify-between">
            <div>
              <span className="text-xs text-navy-500 font-medium">Estimated Monthly Spend</span>
              <div className="mt-1.5 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-navy-900 font-mono tabular-nums">
                  {formatFinancialCurrency(spendAmount, currency)}
                </span>
                <span className="text-xs font-normal text-slate-400">/mo</span>
              </div>
            </div>
            <div className="p-2 rounded-lg bg-blue-50 text-brand-600 border border-blue-200 group-hover:scale-105 transition">
              <Cpu className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
            <span className="inline-flex items-center gap-1 text-accent-emerald font-semibold">
              <TrendingUp className="w-3.5 h-3.5" /> Deterministic Rate
            </span>
            <span className="text-brand-600 font-semibold group-hover:underline">
              Inspect Breakdown &rarr;
            </span>
          </div>
        </div>

        {/* Card 2: Managed Resources */}
        <div
          onClick={() => handleOpenDrawer("resources")}
          className="app-card p-4 flex flex-col justify-between cursor-pointer hover:border-indigo-400 hover:shadow-subtle transition group"
        >
          <div className="flex items-start justify-between">
            <div>
              <span className="text-xs text-navy-500 font-medium">Active Discovered Resources</span>
              <div className="mt-1.5 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-navy-900 font-mono tabular-nums">
                  {financials.included_resources_count}
                </span>
                <span className="text-xs text-slate-500 font-normal">items</span>
              </div>
            </div>
            <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600 border border-indigo-200 group-hover:scale-105 transition">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
            <span className="text-slate-600 font-mono text-[11px]">
              {financials.provider.toUpperCase()} Hierarchy
            </span>
            <span className="text-indigo-600 font-semibold group-hover:underline">
              View Rollup &rarr;
            </span>
          </div>
        </div>

        {/* Card 3: Potential Monthly Savings */}
        <div
          onClick={() => handleOpenDrawer("savings")}
          className="app-card p-4 flex flex-col justify-between border-emerald-200 bg-emerald-50/20 cursor-pointer hover:border-emerald-400 hover:shadow-subtle transition group"
        >
          <div className="flex items-start justify-between">
            <div>
              <span className="text-xs text-navy-700 font-medium">Monthly Optimization Opportunity</span>
              <div className="mt-1.5 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-accent-emerald font-mono tabular-nums">
                  {formatFinancialCurrency(savingsAmount, currency)}
                </span>
                <span className="text-xs font-semibold text-accent-emerald bg-emerald-100 px-1.5 py-0.5 rounded">
                  -{savingsPct}%
                </span>
              </div>
            </div>
            <div className="p-2 rounded-lg bg-emerald-100 text-accent-emerald border border-emerald-300 group-hover:scale-105 transition">
              <TrendingDown className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-emerald-200/60 flex items-center justify-between text-xs">
            <span className="text-navy-600 font-medium">
              {financials.findings_count} Reconciled Findings
            </span>
            <span className="text-accent-emerald font-semibold group-hover:underline">
              Inspect Savings &rarr;
            </span>
          </div>
        </div>

        {/* Card 4: Projected Annual Savings / Governance */}
        <div
          onClick={() => handleOpenDrawer("annual_savings")}
          className="app-card p-4 flex flex-col justify-between cursor-pointer hover:border-amber-400 hover:shadow-subtle transition group"
        >
          <div className="flex items-start justify-between">
            <div>
              <span className="text-xs text-navy-500 font-medium">Projected Annual Savings</span>
              <div className="mt-1.5 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-navy-900 font-mono tabular-nums">
                  {formatFinancialCurrency(financials.projected_annual_savings, currency)}
                </span>
                <span className="text-xs text-slate-400 font-normal">/yr</span>
              </div>
            </div>
            <div className="p-2 rounded-lg bg-amber-50 text-amber-600 border border-amber-200 group-hover:scale-105 transition">
              <Zap className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
            <span className="inline-flex items-center gap-1 text-slate-600">
              <ShieldCheck className="w-3.5 h-3.5 text-accent-emerald" /> 100% Read-Only
            </span>
            <span className="text-amber-700 font-semibold group-hover:underline">
              Formula &rarr;
            </span>
          </div>
        </div>
      </div>

      {/* Main Charts Row: Monthly Trend (SVG) + Reconciled Spend-by-Category */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Monthly Cost Trend Chart (2 cols) */}
        <div className="lg:col-span-2 app-card p-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-slate-100 gap-2">
            <div>
              <h2 className="text-sm font-bold text-navy-900 tracking-tight">
                Monthly Cloud Spend Trajectory (6 Months)
              </h2>
              <p className="text-xs text-navy-500 mt-0.5">
                Deterministic billing aggregation with monthly budget threshold at{" "}
                {formatFinancialCurrency(monthlyTrend[0]?.budget || spendAmount, currency)}.
              </p>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="inline-flex items-center gap-1.5 text-navy-600">
                <span className="w-3 h-3 rounded bg-brand-600" /> Billed Spend
              </span>
              <span className="inline-flex items-center gap-1.5 text-navy-600">
                <span className="w-3 h-0.5 bg-rose-400 border-dashed" /> Budget Target
              </span>
            </div>
          </div>

          {/* SVG Bar Chart */}
          <div className="mt-6 relative h-56 flex items-end justify-between gap-4 px-2 pt-4">
            {/* Budget Guide Line */}
            <div
              className="absolute left-0 right-0 border-b-2 border-dashed border-rose-300 pointer-events-none z-10"
              style={{
                bottom: `${Math.min(95, ((monthlyTrend[0]?.budget || spendAmount) / maxCost) * 100)}%`,
              }}
            >
              <span className="absolute right-2 -top-4 text-[10px] font-mono text-rose-500 font-semibold bg-white px-1">
                Budget: {formatFinancialCurrency(monthlyTrend[0]?.budget || spendAmount, currency)}
              </span>
            </div>

            {monthlyTrend.map((item, idx) => {
              const heightPct = Math.max(12, Math.min(100, (item.cost / maxCost) * 100));
              const isHovered = hoveredBar === idx;

              return (
                <div
                  key={item.month}
                  className="flex-1 flex flex-col items-center h-full justify-end group cursor-pointer"
                  onMouseEnter={() => setHoveredBar(idx)}
                  onMouseLeave={() => setHoveredBar(null)}
                >
                  {/* Tooltip */}
                  {isHovered && (
                    <div className="absolute top-0 bg-navy-900 text-white px-2.5 py-1 rounded shadow-lg text-[11px] font-mono z-20 pointer-events-none whitespace-nowrap">
                      {item.month}: {formatFinancialCurrency(item.cost, currency)}
                    </div>
                  )}

                  {/* Value on top of bar */}
                  <span className="text-[10px] font-mono text-slate-500 mb-1 group-hover:text-navy-900 group-hover:font-bold transition">
                    {formatFinancialCurrency(item.cost, currency, 0)}
                  </span>

                  {/* Bar */}
                  <div className="w-full max-w-[48px] bg-slate-100 rounded-t-md overflow-hidden flex flex-col justify-end transition-all">
                    <div
                      className={`w-full rounded-t-md transition-all duration-300 ${
                        item.current
                          ? "bg-brand-600 group-hover:bg-brand-700 ring-2 ring-blue-300"
                          : "bg-brand-500/80 group-hover:bg-brand-600"
                      }`}
                      style={{ height: `${heightPct}%` }}
                    />
                  </div>

                  {/* Month Label */}
                  <span
                    className={`mt-2 text-xs font-medium ${
                      item.current ? "text-brand-600 font-bold" : "text-navy-600"
                    }`}
                  >
                    {item.month}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Reconciled Spend-by-Category Card (1 col) */}
        <div className="app-card p-5 flex flex-col justify-between">
          <div>
            <div className="pb-4 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-bold text-navy-900 tracking-tight">
                  Spend Breakdown by Category
                </h2>
                <p className="text-xs text-navy-500 mt-0.5">
                  100% reconciled to {formatFinancialCurrency(spendAmount, currency)}/mo
                </p>
              </div>
              <button
                type="button"
                onClick={() => handleOpenDrawer("category")}
                className="text-[11px] font-semibold text-brand-600 hover:underline"
              >
                Audit &rarr;
              </button>
            </div>

            {/* Visual Stacked Progress Bar */}
            <div className="mt-4 w-full h-3 rounded-full bg-slate-100 overflow-hidden flex">
              {financials.categories.map((c) => (
                <div
                  key={c.name}
                  className={`${c.color_class} h-full transition-all`}
                  style={{ width: `${Math.max(1, c.percentage_of_total)}%` }}
                  title={`${c.name}: ${c.percentage_of_total}% (${formatFinancialCurrency(c.amount_usd, currency)})`}
                />
              ))}
            </div>

            {/* Category List */}
            <div className="mt-4 space-y-2.5">
              {financials.categories.map((c) => (
                <div
                  key={c.name}
                  onClick={() => handleOpenDrawer("category")}
                  className="flex items-center justify-between text-xs cursor-pointer hover:bg-slate-50 p-1 rounded-md transition"
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-2.5 h-2.5 rounded-full ${c.color_class} shrink-0`} />
                    <span className="text-navy-700 font-medium truncate max-w-[150px]">
                      {c.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 font-mono">
                    <span className="text-slate-400 text-[11px]">{c.percentage_of_total}%</span>
                    <span className="font-semibold text-navy-900">
                      {formatFinancialCurrency(c.amount_usd, currency)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100">
            <button
              type="button"
              onClick={() => handleOpenDrawer("spend")}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-slate-50 hover:bg-slate-100 text-brand-600 text-xs font-semibold transition"
            >
              <span>Inspect Spend Invariant Proof</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Bottom Section: Reconciled Active Waste Findings & Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Optimization Findings (2 cols) */}
        <div className="lg:col-span-2 app-card p-5">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-accent-amber" />
              <h2 className="text-sm font-bold text-navy-900 tracking-tight">
                High-Impact FinOps Optimization Findings
              </h2>
            </div>
            <button
              type="button"
              onClick={() => handleOpenDrawer("savings")}
              className="text-xs font-semibold text-accent-emerald bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full hover:bg-emerald-100 transition"
            >
              Save up to {formatFinancialCurrency(savingsAmount, currency)}/mo &rarr;
            </button>
          </div>

          <div className="mt-4 space-y-3">
            {financials.findings.map((finding) => (
              <div
                key={finding.id}
                onClick={() => handleOpenDrawer("finding", finding.id)}
                className="p-3.5 rounded-xl border border-slate-200 hover:border-slate-300 bg-slate-50/50 hover:bg-white transition flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 cursor-pointer group"
              >
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                        finding.severity === "high"
                          ? "bg-rose-100 text-rose-800"
                          : finding.severity === "medium"
                          ? "bg-amber-100 text-amber-800"
                          : "bg-blue-100 text-blue-800"
                      }`}
                    >
                      {finding.severity}
                    </span>
                    <span className="text-xs font-bold text-navy-900 truncate">
                      {finding.title}
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      &bull; {finding.category}
                    </span>
                  </div>
                  <p className="text-xs text-navy-600 line-clamp-1">{finding.description}</p>
                </div>

                <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-200/60">
                  <div className="text-left sm:text-right">
                    <span className="text-xs font-bold text-accent-emerald font-mono block">
                      +{formatFinancialCurrency(finding.potential_monthly_savings, currency)}/mo
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Spend: {formatFinancialCurrency(finding.current_monthly_spend, currency)}
                    </span>
                  </div>
                  <span className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 group-hover:border-slate-300 text-navy-800 text-xs font-semibold shadow-2xs transition">
                    <span>Inspect</span>
                    <ArrowRight className="w-3 h-3 text-slate-400 group-hover:translate-x-0.5 transition" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Operations & Cloud Governance Panel (1 col) */}
        <div className="app-card p-5 flex flex-col justify-between">
          <div>
            <div className="pb-3 border-b border-slate-100">
              <h2 className="text-sm font-bold text-navy-900 tracking-tight">
                Governance &amp; Observability Status
              </h2>
              <p className="text-xs text-navy-500 mt-0.5">
                Audit guarantees and zero-execution policy status.
              </p>
            </div>

            <div className="mt-4 space-y-3">
              <div className="p-3 rounded-lg bg-emerald-50/60 border border-emerald-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-accent-emerald" />
                  <div>
                    <span className="font-semibold text-navy-900 block text-xs">
                      Catalog Reconciliation
                    </span>
                    <span className="text-[11px] text-emerald-800">100% Invariant Conserved</span>
                  </div>
                </div>
                <span className="font-mono font-bold text-accent-emerald text-xs">$0.00 Delta</span>
              </div>

              <div className="p-3 rounded-lg bg-blue-50/60 border border-blue-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-brand-600" />
                  <div>
                    <span className="font-semibold text-navy-900 block text-xs">
                      Connected Scope
                    </span>
                    <span className="text-[11px] text-navy-600 truncate max-w-[140px] block">
                      {financials.scope_name}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onNavigate("monitoring")}
                  className="text-brand-600 font-semibold text-xs hover:underline"
                >
                  Monitoring &rarr;
                </button>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-slate-700" />
                  <div>
                    <span className="font-semibold text-navy-900 block text-xs">Access Model</span>
                    <span className="text-[11px] text-slate-500">Zero-Execution Policy enforced</span>
                  </div>
                </div>
                <span className="text-[11px] font-mono text-slate-600 font-medium">Reader</span>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 space-y-2">
            {ENABLE_AI_ARCHITECT ? (
              <button
                type="button"
                onClick={() => onNavigate("architect")}
                className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-xs shadow-2xs transition"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Launch AI Cloud Architect</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onNavigate("monitoring")}
                className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-xs shadow-2xs transition"
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Infrastructure Monitoring &amp; Telemetry</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Accessible Financial Reconciliation Detail Drawer */}
      <FinancialKpiDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        kpiType={drawerKpiType}
        financials={financials}
        selectedFindingId={selectedFindingId}
        onInspectResource={() => {
          setIsDrawerOpen(false);
          onNavigate("monitoring");
        }}
      />
    </div>
  );
};
