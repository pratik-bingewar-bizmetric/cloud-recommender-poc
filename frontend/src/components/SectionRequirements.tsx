"use client";

import React from "react";
import {
  Sparkles,
  HelpCircle,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Globe,
  Users,
  Database,
  ShieldCheck,
  Activity,
  Loader2,
  FileText,
  Layers,
  Check,
} from "lucide-react";
import { ClarifyingQuestion, WorkloadProfile } from "@/types";

interface SectionRequirementsProps {
  idea: string;
  setIdea: (val: string) => void;
  targetRegion: string;
  setTargetRegion: (val: string) => void;
  customerPreset: number;
  setCustomerPreset: (val: number) => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
  workloadProfile: WorkloadProfile | null;
  clarifyingQuestions: ClarifyingQuestion[];
  clarifyingAnswers: Record<string, string>;
  onAnswerChange: (questionId: string, answer: string) => void;
  missingRequirements: string[];
  onGenerateArchitecture: () => void;
  isGeneratingArch: boolean;
}

const PRESET_IDEAS = [
  {
    label: "Enterprise Customer Platform",
    badge: "10,000 Customers",
    preset: 10000,
    summary: "Web portal, REST APIs, HA PostgreSQL, document storage & AI support.",
    text: "I want a customer management platform for 10,000 customers with user authentication, a web frontend, REST APIs, PostgreSQL, document storage, monitoring, high availability, and AI-powered customer support.",
  },
  {
    label: "B2B Multi-Tenant SME Portal",
    badge: "51 Tenants",
    preset: 51,
    summary: "REST API backend, daily backups, 50 GB object storage & Azure Monitor.",
    text: "Build a multi-tenant business portal for 51 client companies. Requires secure REST API backend, relational database with daily backups, file uploads up to 50GB total, and standard Azure monitoring.",
  },
  {
    label: "Internal Pilot API Service",
    badge: "21 Users",
    preset: 21,
    summary: "Lightweight serverless container hosting, PostgreSQL & basic telemetry.",
    text: "We need a pilot API service for 21 internal business users with lightweight serverless container hosting, PostgreSQL database, and basic log telemetry on East US.",
  },
];

const REGION_OPTIONS = [
  { id: "eastus", label: "East US (Virginia)" },
  { id: "westus2", label: "West US 2 (Washington)" },
  { id: "westeurope", label: "West Europe (Netherlands)" },
  { id: "northeurope", label: "North Europe (Ireland)" },
  { id: "southeastasia", label: "Southeast Asia (Singapore)" },
];

const SCALE_PRESETS = [
  { value: 21, title: "Pilot", subtitle: "21 Customers" },
  { value: 51, title: "SME Growth", subtitle: "51 Customers" },
  { value: 10000, title: "Production Scale", subtitle: "10,000 Customers" },
];

export const SectionRequirements: React.FC<SectionRequirementsProps> = ({
  idea,
  setIdea,
  targetRegion,
  setTargetRegion,
  customerPreset,
  setCustomerPreset,
  onAnalyze,
  isAnalyzing,
  workloadProfile,
  clarifyingQuestions,
  clarifyingAnswers,
  onAnswerChange,
  missingRequirements,
  onGenerateArchitecture,
  isGeneratingArch,
}) => {
  const isValidIdea = idea.trim().length >= 10;

  return (
    <section
      id="section-requirements"
      className="scroll-mt-28 bg-white rounded-2xl border border-slate-200/90 shadow-card p-5 sm:p-6 lg:p-7 mb-6 transition-shadow"
    >
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-5 border-b border-slate-100 gap-3">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl bg-blue-50 border border-blue-200/70 text-blue-700 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
            01
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight">
                Application Requirements &amp; AI Ingestion
              </h2>
              {workloadProfile && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-medium">
                  <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                  Profile Extracted
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Describe your workload in plain language. Azure AI Foundry extracts functional and non-functional requirements and identifies ambiguities.
            </p>
          </div>
        </div>
      </div>

      {/* Main Input Grid: Left (Archetypes + Prompt) | Right (Region, Scale & Action) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left Column: Presets + Textarea */}
        <div className="lg:col-span-8 space-y-4">
          {/* Archetype Cards */}
          <div>
            <span className="text-xs font-semibold text-slate-700 block mb-2">
              Quick-Start Workload Archetypes
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              {PRESET_IDEAS.map((p) => {
                const isSelected = idea === p.text && customerPreset === p.preset;
                return (
                  <button
                    key={p.preset}
                    type="button"
                    disabled={isAnalyzing}
                    onClick={() => {
                      setIdea(p.text);
                      setCustomerPreset(p.preset);
                    }}
                    className={`group text-left p-3 rounded-xl border transition-all ${
                      isSelected
                        ? "bg-blue-50/70 border-blue-500 shadow-2xs ring-1 ring-blue-500/20"
                        : "bg-slate-50/70 border-slate-200/90 hover:bg-white hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span
                        className={`text-xs font-semibold truncate ${
                          isSelected ? "text-blue-900" : "text-slate-800 group-hover:text-blue-700"
                        }`}
                      >
                        {p.label}
                      </span>
                      <span
                        className={`text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded shrink-0 ${
                          isSelected
                            ? "bg-blue-600 text-white"
                            : "bg-slate-200/70 text-slate-600"
                        }`}
                      >
                        {p.badge}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 line-clamp-2 leading-relaxed">
                      {p.summary}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Spacious Natural Language Input Surface */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label
                htmlFor="app-idea-input"
                className="text-xs font-semibold text-slate-700 flex items-center gap-1.5"
              >
                <FileText className="w-3.5 h-3.5 text-blue-600" />
                <span>Workload &amp; Architecture Prompt</span>
                <span className="text-rose-500" aria-hidden="true">
                  *
                </span>
              </label>
              <span
                className={`text-[11px] font-mono ${
                  isValidIdea ? "text-slate-400" : "text-amber-600 font-medium"
                }`}
              >
                {idea.trim().length} chars {!isValidIdea && "(min 10 required)"}
              </span>
            </div>
            <div className="relative">
              <textarea
                id="app-idea-input"
                rows={4}
                disabled={isAnalyzing}
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                placeholder="Example: We are building a multi-region B2B SaaS platform for 10,000 customers with Next.js frontend, containerized Python APIs, PostgreSQL database, blob document storage, 99.95% SLA, and an AI support assistant..."
                className="w-full text-sm leading-relaxed p-3.5 rounded-xl border border-slate-300/90 bg-slate-50/40 focus:bg-white focus:border-blue-600 text-slate-900 placeholder:text-slate-400 transition resize-y min-h-[112px]"
              />
            </div>
          </div>
        </div>

        {/* Right Column: Target Region, Scale Tier & Submit Action */}
        <div className="lg:col-span-4 flex flex-col justify-between bg-slate-50/80 rounded-xl border border-slate-200/80 p-4 space-y-4">
          <div className="space-y-4">
            {/* Target Region */}
            <div>
              <label
                htmlFor="target-region-select"
                className="text-xs font-semibold text-slate-700 flex items-center gap-1.5 mb-1.5"
              >
                <Globe className="w-3.5 h-3.5 text-blue-600" />
                <span>Primary Azure Region</span>
              </label>
              <select
                id="target-region-select"
                disabled={isAnalyzing}
                value={targetRegion}
                onChange={(e) => setTargetRegion(e.target.value)}
                className="w-full text-xs sm:text-sm font-medium p-2.5 rounded-xl border border-slate-300 bg-white text-slate-800 hover:border-slate-400 transition"
              >
                {REGION_OPTIONS.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label} ({r.id})
                  </option>
                ))}
              </select>
            </div>

            {/* Customer Scale Tier */}
            <div>
              <span className="text-xs font-semibold text-slate-700 flex items-center gap-1.5 mb-1.5">
                <Users className="w-3.5 h-3.5 text-blue-600" />
                <span>Target Customer Scale</span>
              </span>
              <div className="grid grid-cols-3 gap-2">
                {SCALE_PRESETS.map((preset) => {
                  const active = customerPreset === preset.value;
                  return (
                    <button
                      key={preset.value}
                      type="button"
                      disabled={isAnalyzing}
                      onClick={() => setCustomerPreset(preset.value)}
                      className={`p-2 rounded-xl border text-center transition ${
                        active
                          ? "bg-blue-600 text-white border-blue-600 shadow-2xs"
                          : "bg-white text-slate-700 border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                      }`}
                    >
                      <div className="text-xs font-bold leading-tight">{preset.title}</div>
                      <div
                        className={`text-[10px] mt-0.5 font-mono ${
                          active ? "text-blue-100" : "text-slate-400"
                        }`}
                      >
                        {preset.subtitle}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Primary Submit CTA */}
          <div className="pt-2 border-t border-slate-200/70">
            <button
              type="button"
              onClick={onAnalyze}
              disabled={isAnalyzing || !isValidIdea}
              className={`w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-semibold text-white transition shadow-2xs ${
                isAnalyzing || !isValidIdea
                  ? "bg-slate-300 text-slate-500 cursor-not-allowed"
                  : "bg-blue-600 hover:bg-blue-700 active:scale-[0.99]"
              }`}
            >
              {isAnalyzing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Analyzing with Azure AI Foundry...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Analyze Workload Requirements</span>
                </>
              )}
            </button>
            <p className="text-[11px] text-slate-500 text-center mt-2">
              {isAnalyzing
                ? "Extracting workload profile, SLA targets, and clarifying questions..."
                : "Runs live inference on Azure AI Foundry to structure your specification."}
            </p>
          </div>
        </div>
      </div>

      {/* Extracted Workload Profile & Clarifying Questions */}
      {workloadProfile && (
        <div className="mt-6 pt-6 border-t border-slate-200/80 space-y-5">
          {/* Extracted Profile Header & Summary */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <h3 className="text-sm font-semibold text-slate-900">
                Extracted Workload Profile
              </h3>
              <span className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200/80 uppercase">
                {workloadProfile.category.replace(/_/g, " ")}
              </span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-slate-500">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200/70 font-medium">
                Confirmed Input
              </span>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200/70 font-medium">
                AI Assumption
              </span>
              {missingRequirements.length > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200/70 font-medium">
                  Needs Confirmation
                </span>
              )}
            </div>
          </div>

          {/* Structured Profile Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Application Identity */}
            <div className="p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/90">
              <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium mb-1">
                <span className="flex items-center gap-1">
                  <Layers className="w-3.5 h-3.5 text-blue-600" />
                  Application Name
                </span>
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200/70">
                  Confirmed
                </span>
              </div>
              <div className="text-sm font-semibold text-slate-900 truncate">
                {workloadProfile.name || "Not specified"}
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5 font-mono">
                Region: {workloadProfile.target_regions?.[0] || targetRegion}
              </div>
            </div>

            {/* Availability & SLA Target */}
            <div className="p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/90">
              <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium mb-1">
                <span className="flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                  Availability Target
                </span>
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200/70">
                  Target SLA
                </span>
              </div>
              <div className="text-sm font-semibold text-slate-900 font-mono">
                {workloadProfile.target_availability_percentage != null
                  ? `${workloadProfile.target_availability_percentage}% SLA`
                  : "Needs confirmation"}
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">
                HA Required:{" "}
                <span className="font-medium text-slate-700">
                  {workloadProfile.estimation_assumptions?.ha_required === "True" ||
                  workloadProfile.estimation_assumptions?.ha_required === "true"
                    ? "Yes (Multi-Zone)"
                    : "Single-Zone / Configurable"}
                </span>
              </div>
            </div>

            {/* Storage & Egress */}
            <div className="p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/90">
              <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium mb-1">
                <span className="flex items-center gap-1">
                  <Database className="w-3.5 h-3.5 text-amber-600" />
                  Storage &amp; Egress
                </span>
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200/70">
                  Assumption
                </span>
              </div>
              <div className="text-sm font-semibold text-slate-900 font-mono">
                {workloadProfile.storage_volume_gb != null
                  ? `${workloadProfile.storage_volume_gb} GB Total`
                  : "Not specified"}
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5 font-mono">
                Outbound Egress:{" "}
                {workloadProfile.monthly_data_egress_gb != null
                  ? `${workloadProfile.monthly_data_egress_gb} GB/mo`
                  : "Not specified"}
              </div>
            </div>

            {/* Scale & AI Token Estimate */}
            <div className="p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/90">
              <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium mb-1">
                <span className="flex items-center gap-1">
                  <Activity className="w-3.5 h-3.5 text-purple-600" />
                  Scale &amp; AI Volume
                </span>
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200/70">
                  Assumption
                </span>
              </div>
              <div className="text-sm font-semibold text-slate-900 font-mono">
                {workloadProfile.estimation_assumptions?.customer_count
                  ? `${Number(workloadProfile.estimation_assumptions.customer_count).toLocaleString()} Customers`
                  : `${customerPreset.toLocaleString()} Customers`}
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5 font-mono">
                AI Tokens:{" "}
                {workloadProfile.estimation_assumptions?.ai_support_monthly_tokens
                  ? `${(Number(workloadProfile.estimation_assumptions.ai_support_monthly_tokens) / 1_000_000).toFixed(1)}M / mo`
                  : "Configurable below"}
              </div>
            </div>
          </div>

          {/* Technical Description Banner */}
          <div className="p-3.5 rounded-xl bg-slate-50/60 border border-slate-200/80 text-xs text-slate-600 leading-relaxed">
            <span className="font-semibold text-slate-900 mr-1.5">
              Technical Scope Summary:
            </span>
            {workloadProfile.description || "No additional summary provided."}
          </div>

          {/* Unresolved / Missing Critical Requirements */}
          {missingRequirements.length > 0 && (
            <div className="p-3.5 rounded-xl bg-amber-50/80 border border-amber-200/90">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-900 mb-2">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>Parameters Needing Confirmation ({missingRequirements.length})</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {missingRequirements.map((mr, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1 text-xs bg-white text-amber-900 px-2.5 py-1 rounded-lg border border-amber-200/90 font-mono shadow-2xs"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                    {mr.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Clarifying Questions Loop */}
          {clarifyingQuestions.length > 0 && (
            <div className="rounded-2xl border border-blue-200/80 bg-gradient-to-b from-blue-50/50 to-slate-50/40 p-4 sm:p-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-blue-600 text-white">
                    <HelpCircle className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs sm:text-sm font-semibold text-slate-900">
                      Architecture Clarifying Questions ({clarifyingQuestions.length})
                    </h4>
                    <p className="text-[11px] text-slate-500">
                      Your selections directly influence SKU selection, redundancy tiers, and monthly cost estimates.
                    </p>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {clarifyingQuestions.map((q, qIdx) => (
                  <div
                    key={q.id}
                    className="p-4 bg-white rounded-xl border border-slate-200/90 shadow-2xs flex flex-col justify-between gap-3"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <span className="text-xs font-semibold text-slate-900 leading-snug">
                          {qIdx + 1}. {q.question}
                        </span>
                        <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200 font-semibold shrink-0">
                          {q.category}
                        </span>
                      </div>

                      {q.rationale && (
                        <p className="text-[11px] text-slate-500 leading-relaxed">
                          {q.rationale}
                        </p>
                      )}

                      {q.impact_on_architecture && (
                        <div className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-indigo-700 bg-indigo-50/80 border border-indigo-200/60 px-2 py-1 rounded-md font-medium">
                          <span>Impact: {q.impact_on_architecture}</span>
                        </div>
                      )}
                    </div>

                    {/* Selectable Answer Options */}
                    <div
                      role="radiogroup"
                      aria-label={q.question}
                      className="pt-2 border-t border-slate-100 flex flex-wrap gap-1.5"
                    >
                      {q.options.map((opt, oIdx) => {
                        const isSelected = clarifyingAnswers[q.id] === opt;
                        return (
                          <button
                            key={oIdx}
                            type="button"
                            role="radio"
                            aria-checked={isSelected}
                            disabled={isGeneratingArch}
                            onClick={() => onAnswerChange(q.id, opt)}
                            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border font-medium transition ${
                              isSelected
                                ? "bg-blue-600 text-white border-blue-600 shadow-2xs"
                                : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-white hover:border-blue-300"
                            }`}
                          >
                            {isSelected && <Check className="w-3.5 h-3.5 shrink-0" />}
                            <span>{opt}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Bar: Generate Production Architecture */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
            <p className="text-xs text-slate-500">
              Ready to synthesize the Azure topology and calculate deterministic retail pricing.
            </p>
            <button
              type="button"
              onClick={onGenerateArchitecture}
              disabled={isGeneratingArch}
              className={`inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold text-white transition shadow-card ${
                isGeneratingArch
                  ? "bg-slate-400 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-700 active:scale-[0.99]"
              }`}
            >
              {isGeneratingArch ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Synthesizing Azure Architecture &amp; Pricing...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Generate Production Architecture</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </section>
  );
};
