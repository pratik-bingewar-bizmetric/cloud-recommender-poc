"use client";

import React from "react";
import { ENABLE_AI_ARCHITECT } from "@/config/features";
import {
  Sparkles,
  ShieldCheck,
  Calculator,
  FolderTree,
  Activity,
  ArrowRight,
  LayoutDashboard,
  CheckCircle2,
  Layers,
  Lock,
  Coins,
} from "lucide-react";

interface LandingViewProps {
  onNavigate: (view: "architect" | "dashboard" | "inventory" | "monitoring" | "compare") => void;
  monthlyTotal?: string | null;
  connectedScope?: string | null;
  potentialSavings?: string | null;
}

export const LandingView: React.FC<LandingViewProps> = ({
  onNavigate,
  monthlyTotal,
  connectedScope,
  potentialSavings,
}) => {
  return (
    <div className="space-y-12 pb-16">
      {/* Hero Section */}
      <section className="relative pt-6 sm:pt-10 pb-8 text-center max-w-4xl mx-auto px-4">
        {/* Subtle top badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-xs font-semibold mb-6">
          <Sparkles className="w-3.5 h-3.5 text-blue-600" />
          <span>Enterprise FinOps &amp; Infrastructure Intelligence</span>
          <span className="w-1 h-1 rounded-full bg-blue-400" />
          <span className="text-blue-600 font-medium">Read-Only Advisory</span>
        </div>

        {/* Main Headline */}
        <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-navy-900 leading-[1.15]">
          Understand your infrastructure.{" "}
          <span className="text-brand-600">Optimize your costs.</span>{" "}
          Engineer what comes next.
        </h1>

        {/* Subtitle */}
        <p className="mt-5 text-base sm:text-lg text-navy-600 max-w-2xl mx-auto font-normal leading-relaxed">
          AI-powered cloud architecture blueprinting, live subscription hierarchy discovery,
          centralized telemetry analytics, and zero-hallucination deterministic pricing.
        </p>

        {/* Primary CTAs */}
        <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
          {ENABLE_AI_ARCHITECT ? (
            <button
              type="button"
              onClick={() => onNavigate("architect")}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-sm shadow-subtle hover:shadow-card transition"
            >
              <Sparkles className="w-4 h-4" />
              <span>Open AI Architect</span>
              <ArrowRight className="w-4 h-4 ml-0.5" />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => onNavigate("monitoring")}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-sm shadow-subtle hover:shadow-card transition"
            >
              <Activity className="w-4 h-4" />
              <span>Launch Infrastructure Monitoring</span>
              <ArrowRight className="w-4 h-4 ml-0.5" />
            </button>
          )}

          <button
            type="button"
            onClick={() => onNavigate("dashboard")}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-white hover:bg-slate-50 text-navy-800 font-medium text-sm border border-slate-200 shadow-subtle transition"
          >
            <LayoutDashboard className="w-4 h-4 text-slate-500" />
            <span>Explore Dashboard</span>
          </button>
        </div>

        {/* Trust & Guardrail indicators */}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-6 text-xs text-navy-500">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-accent-emerald" />
            <span>Zero-Execution Policy (Strictly Read-Only)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Calculator className="w-4 h-4 text-brand-600" />
            <span>Official Azure Retail Prices API</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Lock className="w-4 h-4 text-slate-500" />
            <span>Enterprise Secret Scrubbing</span>
          </div>
        </div>
      </section>

      {/* Platform Preview Showcase (Screen 1 Main Mockup Card) */}
      <section className="max-w-5xl mx-auto px-4">
        <div className="app-card overflow-hidden shadow-card border border-slate-200">
          {/* Mock Browser / Window Chrome */}
          <div className="h-10 bg-slate-100 border-b border-slate-200 px-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-rose-400" />
              <span className="w-3 h-3 rounded-full bg-amber-400" />
              <span className="w-3 h-3 rounded-full bg-emerald-400" />
              <span className="ml-3 text-xs font-mono text-slate-500">
                cloud-recommender.finops.internal
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              {connectedScope ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-medium text-[10px]">
                  <CheckCircle2 className="w-3 h-3" /> Live Scope: {connectedScope.substring(0, 18)}...
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-100 text-amber-800 font-medium text-[10px]" title="East US multi-tier reference benchmark model">
                  <Layers className="w-3 h-3" /> Benchmark: sub-prod-enterprise-01
                </span>
              )}
              <span className="text-slate-400 font-mono text-[11px]">eastus</span>
            </div>
          </div>

          {/* Inner Preview Content */}
          <div className="p-6 bg-slate-50/50 space-y-6">
            {/* Quick KPI Row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-white p-3.5 rounded-lg border border-slate-200 shadow-2xs">
                <span className="text-[11px] text-slate-500 font-medium block">Monthly Spend</span>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-xl font-bold text-navy-900 font-mono tabular-nums">
                    {monthlyTotal ? `$${parseFloat(monthlyTotal).toFixed(2)}` : "$225.11"}
                  </span>
                  <span className="text-[10px] text-accent-emerald font-semibold">
                    {monthlyTotal ? "Live BOM" : "Retail Catalog"}
                  </span>
                </div>
              </div>

              <div className="bg-white p-3.5 rounded-lg border border-slate-200 shadow-2xs">
                <span className="text-[11px] text-slate-500 font-medium block">Monitored Resources</span>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-xl font-bold text-navy-900 font-mono tabular-nums">8</span>
                  <span className="text-[10px] text-slate-500">100% telemetry</span>
                </div>
              </div>

              <div className="bg-white p-3.5 rounded-lg border border-slate-200 shadow-2xs">
                <span className="text-[11px] text-slate-500 font-medium block">Potential Savings</span>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-xl font-bold text-accent-emerald font-mono tabular-nums">
                    {potentialSavings ? `$${parseFloat(potentialSavings).toFixed(2)}` : "$118.27"}
                  </span>
                  <span className="text-[10px] text-accent-emerald font-semibold">
                    {monthlyTotal
                      ? `${((parseFloat(potentialSavings || "0") / (parseFloat(monthlyTotal) || 1)) * 100).toFixed(0)}%`
                      : "52.5%"}
                  </span>
                </div>
              </div>

              <div className="bg-white p-3.5 rounded-lg border border-slate-200 shadow-2xs">
                <span className="text-[11px] text-slate-500 font-medium block">Target SLA</span>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-xl font-bold text-navy-900 font-mono tabular-nums">99.95%</span>
                  <span className="text-[10px] text-blue-600 font-medium">HA Active</span>
                </div>
              </div>
            </div>

            {/* Split Preview: Mini Blueprint & Cost Bar */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Architecture Blueprint Mock */}
              <div className="md:col-span-2 bg-white p-4 rounded-lg border border-slate-200">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-brand-600" />
                    <span className="text-xs font-semibold text-navy-900">
                      Multi-Tier Production Architecture (East US)
                    </span>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-medium border border-blue-200">
                    High Availability
                  </span>
                </div>

                <div className="mt-4 grid grid-cols-4 gap-2 text-center text-xs">
                  <div className="p-2.5 rounded bg-slate-50 border border-slate-200">
                    <span className="text-[10px] text-slate-400 uppercase font-semibold block">Ingress</span>
                    <span className="font-semibold text-navy-900 text-xs mt-1 block">Front Door</span>
                    <span className="text-[10px] text-slate-500">WAF &bull; SSL Offload</span>
                  </div>
                  <div className="p-2.5 rounded bg-blue-50/60 border border-blue-200">
                    <span className="text-[10px] text-blue-500 uppercase font-semibold block">Compute</span>
                    <span className="font-semibold text-navy-900 text-xs mt-1 block">App Service</span>
                    <span className="text-[10px] text-slate-500">P2v3 &bull; Autoscale</span>
                  </div>
                  <div className="p-2.5 rounded bg-emerald-50/60 border border-emerald-200">
                    <span className="text-[10px] text-emerald-600 uppercase font-semibold block">Data Tier</span>
                    <span className="font-semibold text-navy-900 text-xs mt-1 block">Azure PostgreSQL</span>
                    <span className="text-[10px] text-slate-500">Flexible &bull; Multi-AZ</span>
                  </div>
                  <div className="p-2.5 rounded bg-purple-50/60 border border-purple-200">
                    <span className="text-[10px] text-purple-600 uppercase font-semibold block">AI Inference</span>
                    <span className="font-semibold text-navy-900 text-xs mt-1 block">Foundry AI</span>
                    <span className="text-[10px] text-slate-500">gpt-5.4-mini</span>
                  </div>
                </div>
              </div>

              {/* Spend Breakdown Preview */}
              <div className="bg-white p-4 rounded-lg border border-slate-200 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                    <span className="text-xs font-semibold text-navy-900">Spend Distribution</span>
                    <span className="text-[10px] text-slate-400 font-mono">BOM Meters</span>
                  </div>
                  <div className="mt-3 space-y-2">
                    <div>
                      <div className="flex justify-between text-[11px] mb-1">
                        <span className="text-slate-600">Compute (App Service, VMs)</span>
                        <span className="font-mono font-medium text-navy-900">$91.25 (41%)</span>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-slate-100 overflow-hidden">
                        <div className="h-full bg-brand-600 rounded-full" style={{ width: "41%" }} />
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-[11px] mb-1">
                        <span className="text-slate-600">Databases &amp; Disks</span>
                        <span className="font-mono font-medium text-navy-900">$105.21 (47%)</span>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-slate-100 overflow-hidden">
                        <div className="h-full bg-accent-emerald rounded-full" style={{ width: "47%" }} />
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-[11px] mb-1">
                        <span className="text-slate-600">AI / ML Tokens</span>
                        <span className="font-mono font-medium text-navy-900">$25.00 (11%)</span>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-slate-100 overflow-hidden">
                        <div className="h-full bg-purple-600 rounded-full" style={{ width: "11%" }} />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
                  <span className="text-[11px] text-slate-500">Retail Prices Meter Confidence</span>
                  <span className="text-xs font-bold text-accent-emerald font-mono">100% Verified</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 5 Core Platform Capabilities */}
      <section className="max-w-5xl mx-auto px-4">
        <div className="text-center mb-8">
          <h2 className="text-xl sm:text-2xl font-bold text-navy-900 tracking-tight">
            Comprehensive Cloud Intelligence Engines
          </h2>
          <p className="text-sm text-navy-600 mt-1 max-w-xl mx-auto">
            Five coordinated engines that power requirements synthesis, hierarchy discovery, cost governance, and observability.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Card 1: AI Cloud Architect or Token Economics */}
          {ENABLE_AI_ARCHITECT ? (
            <div
              onClick={() => onNavigate("architect")}
              className="app-card-interactive p-5 cursor-pointer flex flex-col justify-between"
            >
              <div>
                <div className="w-9 h-9 rounded-lg bg-blue-50 border border-blue-200 text-brand-600 flex items-center justify-center mb-3">
                  <Sparkles className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-bold text-navy-900">AI Cloud Architect</h3>
                <p className="text-xs text-navy-600 mt-1.5 leading-relaxed">
                  Ingest application requirements, validate functional &amp; non-functional constraints, and synthesize production topologies with interactive clarifying question loops.
                </p>
              </div>
              <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-brand-600">
                <span>Launch Architect</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            </div>
          ) : (
            <div
              onClick={() => onNavigate("monitoring")}
              className="app-card-interactive p-5 cursor-pointer flex flex-col justify-between"
            >
              <div>
                <div className="w-9 h-9 rounded-lg bg-blue-50 border border-blue-200 text-brand-600 flex items-center justify-center mb-3">
                  <Coins className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-bold text-navy-900">Token Economics &amp; AI FinOps</h3>
                <p className="text-xs text-navy-600 mt-1.5 leading-relaxed">
                  Monitor token consumption, prompt vs completion distributions, model-level pricing rates, and honest diagnostic settings guidance.
                </p>
              </div>
              <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-brand-600">
                <span>Inspect Token Telemetry</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            </div>
          )}

          {/* Card 2: Subscription Hierarchy */}
          <div
            onClick={() => onNavigate("inventory")}
            className="app-card-interactive p-5 cursor-pointer flex flex-col justify-between"
          >
            <div>
              <div className="w-9 h-9 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center mb-3">
                <FolderTree className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-navy-900">Subscription Hierarchy</h3>
              <p className="text-xs text-navy-600 mt-1.5 leading-relaxed">
                Explore authorized Azure subscriptions, resource groups, and GCP projects with interactive dependency graphs and multi-level FinOps spend rollups.
              </p>
            </div>
            <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-indigo-600">
              <span>Explore Hierarchy</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </div>
          </div>

          {/* Card 3: Centralized Monitoring */}
          <div
            onClick={() => onNavigate("monitoring")}
            className="app-card-interactive p-5 cursor-pointer flex flex-col justify-between"
          >
            <div>
              <div className="w-9 h-9 rounded-lg bg-emerald-50 border border-emerald-200 text-accent-emerald flex items-center justify-center mb-3">
                <Activity className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-navy-900">Centralized Monitoring</h3>
              <p className="text-xs text-navy-600 mt-1.5 leading-relaxed">
                Live timeseries telemetry, historical error analysis, active alert monitoring, and a 7-pillar resource inspector with automated secret redaction.
              </p>
            </div>
            <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-accent-emerald">
              <span>View Telemetry</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </div>
          </div>

          {/* Card 4: Deterministic Pricing Engine or FinOps Waste */}
          {ENABLE_AI_ARCHITECT ? (
            <div
              onClick={() => onNavigate("architect")}
              className="app-card-interactive p-5 cursor-pointer flex flex-col justify-between"
            >
              <div>
                <div className="w-9 h-9 rounded-lg bg-amber-50 border border-amber-200 text-accent-amber flex items-center justify-center mb-3">
                  <Calculator className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-bold text-navy-900">Deterministic Pricing Engine</h3>
                <p className="text-xs text-navy-600 mt-1.5 leading-relaxed">
                  Eliminate generative pricing hallucination. Every line item is calculated using real meters from the Azure Retail Prices API with offline cache fallback.
                </p>
              </div>
              <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-accent-amber">
                <span>Simulate Pricing</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            </div>
          ) : (
            <div
              onClick={() => onNavigate("monitoring")}
              className="app-card-interactive p-5 cursor-pointer flex flex-col justify-between"
            >
              <div>
                <div className="w-9 h-9 rounded-lg bg-amber-50 border border-amber-200 text-accent-amber flex items-center justify-center mb-3">
                  <Calculator className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-bold text-navy-900">Deterministic List Pricing</h3>
                <p className="text-xs text-navy-600 mt-1.5 leading-relaxed">
                  Eliminate generative hallucination. Catalog rates query official provider pricing APIs with local offline cache fallback.
                </p>
              </div>
              <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-accent-amber">
                <span>View Cost Telemetry</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            </div>
          )}

          {/* Card 5: Azure vs. GCP Multi-Cloud */}
          <div
            onClick={() => onNavigate("compare")}
            className="app-card-interactive p-5 cursor-pointer flex flex-col justify-between"
          >
            <div>
              <div className="w-9 h-9 rounded-lg bg-purple-50 border border-purple-200 text-accent-purple flex items-center justify-center mb-3">
                <Layers className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-navy-900">Multi-Cloud Alignment</h3>
              <p className="text-xs text-navy-600 mt-1.5 leading-relaxed">
                Direct side-by-side architectural mapping between Microsoft Azure and Google Cloud Platform with exact cost differential calculations.
              </p>
            </div>
            <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-accent-purple">
              <span>Compare Clouds</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </div>
          </div>

          {/* Card 6: Zero-Execution Policy */}
          <div className="app-card p-5 bg-slate-50/70 border border-slate-200 flex flex-col justify-between">
            <div>
              <div className="w-9 h-9 rounded-lg bg-slate-200/80 text-navy-700 flex items-center justify-center mb-3">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-navy-900">Strict Zero-Execution Guardrail</h3>
              <p className="text-xs text-navy-600 mt-1.5 leading-relaxed">
                The platform is 100% read-only and advisory. It will never deploy, modify, or terminate client infrastructure without explicit manual engineering review.
              </p>
            </div>
            <div className="mt-4 text-[11px] font-mono text-slate-500">
              Role: Reader &bull; Cost Management Reader
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
