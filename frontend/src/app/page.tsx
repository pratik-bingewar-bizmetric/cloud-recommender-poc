"use client";

import React, { useState, useCallback, useEffect } from "react";
import { Header } from "@/components/Header";
import { FoundryConfigAlert } from "@/components/FoundryConfigAlert";
import { SectionRequirements } from "@/components/SectionRequirements";
import { SectionAssumptions } from "@/components/SectionAssumptions";
import { SectionArchitecture } from "@/components/SectionArchitecture";
import { SectionCostSimulator } from "@/components/SectionCostSimulator";
import { SectionTradeOffs } from "@/components/SectionTradeOffs";
import { SectionCloudScopeInventory } from "@/components/SectionCloudScopeInventory";
import { SectionMultiCloudCompare } from "@/components/SectionMultiCloudCompare";
import {
  ApiErrorDetail,
  ArchitectureComponent,
  ClarifyingAnswer,
  ClarifyingQuestion,
  CostBreakdown,
  PricingReference,
  RecommendationReport,
  TradeOffAssessment,
  WorkloadAssumptions,
  WorkloadProfile,
} from "@/types";
import {
  analyzeRequirements,
  checkBackendHealth,
  generateArchitecture,
  simulatePricing,
  ApiError,
} from "@/lib/api";
import { Calculator, Layers, Sparkles, Loader2, ArrowDown } from "lucide-react";

const DEFAULT_ASSUMPTIONS: WorkloadAssumptions = {
  customer_count: 10000,
  monthly_active_users: 2500,
  requests_per_user_per_day: 20,
  peak_rps: 50.0,
  db_storage_gb: 100.0,
  blob_storage_gb: 200.0,
  monthly_egress_gb: 150.0,
  ai_support_monthly_tokens: 5000000,
  target_sla_percentage: 99.95,
  ha_required: true,
  backup_retention_days: 30,
  target_region: "eastus",
};

export default function Home() {
  // Backend Connectivity State
  const [backendStatus, setBackendStatus] = useState<
    "checking" | "online" | "offline"
  >("checking");

  // Top-Level View Mode: Architect (Phase A) | Subscription Hierarchy (Phase B) | Multi-Cloud Compare
  const [activeViewMode, setActiveViewMode] = useState<
    "architect" | "inventory" | "compare"
  >("architect");

  // Section 01 State: Requirements & Clarifications
  const [idea, setIdea] = useState<string>(
    "I want a customer management platform for 10,000 customers with user authentication, a web frontend, REST APIs, PostgreSQL, document storage, monitoring, high availability, and AI-powered customer support."
  );
  const [targetRegion, setTargetRegion] = useState<string>("eastus");
  const [customerPreset, setCustomerPreset] = useState<number>(10000);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [workloadProfile, setWorkloadProfile] =
    useState<WorkloadProfile | null>(null);
  const [clarifyingQuestions, setClarifyingQuestions] = useState<
    ClarifyingQuestion[]
  >([]);
  const [clarifyingAnswers, setClarifyingAnswers] = useState<
    Record<string, string>
  >({});
  const [missingRequirements, setMissingRequirements] = useState<string[]>([]);
  const [foundryError, setFoundryError] = useState<ApiErrorDetail | null>(null);

  // Section 02 State: Workload Sizing
  const [assumptions, setAssumptions] =
    useState<WorkloadAssumptions>(DEFAULT_ASSUMPTIONS);
  const [safetyBufferPct, setSafetyBufferPct] = useState<string>("15.00");

  // Section 03 State: Architecture Blueprint
  const [isGeneratingArch, setIsGeneratingArch] = useState<boolean>(false);
  const [architectureDescription, setArchitectureDescription] =
    useState<string>("");
  const [mermaidDiagram, setMermaidDiagram] = useState<string>("");
  const [components, setComponents] = useState<ArchitectureComponent[]>([]);

  // Section 04 & 05 State: Cost Simulator & Assessment
  const [costBreakdown, setCostBreakdown] = useState<CostBreakdown | null>(
    null
  );
  const [pricingProvenance, setPricingProvenance] = useState<
    PricingReference[]
  >([]);
  const [tradeOffs, setTradeOffs] = useState<TradeOffAssessment | null>(null);
  const [archAssumptions, setArchAssumptions] = useState<string[]>([]);
  const [archLimitations, setArchLimitations] = useState<string[]>([]);
  const [unverifiedWarnings, setUnverifiedWarnings] = useState<string[]>([]);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);

  // Check real backend health on mount
  useEffect(() => {
    let active = true;
    checkBackendHealth()
      .then((res) => {
        if (active) {
          setBackendStatus(res.status === "healthy" || res.status === "ok" ? "online" : "online");
        }
      })
      .catch(() => {
        if (active) {
          setBackendStatus("offline");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  // 1. Analyze Requirements Handler
  const handleAnalyze = async () => {
    setIsAnalyzing(true);
    setFoundryError(null);
    try {
      const res = await analyzeRequirements(idea, targetRegion, customerPreset);
      setBackendStatus("online");
      setWorkloadProfile(res.workload_profile);
      setClarifyingQuestions(res.clarifying_questions);
      setAssumptions(res.workload_assumptions);
      setMissingRequirements(res.missing_critical_requirements);

      const initialAnswers: Record<string, string> = {};
      res.clarifying_questions.forEach((q) => {
        if (q.default_answer) {
          initialAnswers[q.id] = q.default_answer;
        } else if (q.options && q.options.length > 0) {
          initialAnswers[q.id] = q.options[0];
        }
      });
      setClarifyingAnswers(initialAnswers);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFoundryError(err.detail);
      } else {
        setFoundryError({
          message:
            err instanceof Error
              ? err.message
              : "Failed to analyze requirements.",
        });
      }
    } finally {
      setIsAnalyzing(false);
    }
  };

  // 2. Clarifying Answer Handler
  const handleClarifyingAnswer = (questionId: string, answer: string) => {
    setClarifyingAnswers((prev) => ({
      ...prev,
      [questionId]: answer,
    }));
  };

  // 3. Generate Architecture Handler
  const handleGenerateArchitecture = async () => {
    if (!workloadProfile) return;
    setIsGeneratingArch(true);
    setFoundryError(null);

    const answersList: ClarifyingAnswer[] = Object.entries(
      clarifyingAnswers
    ).map(([qId, ans]) => ({
      question_id: qId,
      selected_option: ans,
    }));

    try {
      const report: RecommendationReport = await generateArchitecture(
        workloadProfile,
        assumptions,
        answersList,
        targetRegion
      );

      setBackendStatus("online");
      setArchitectureDescription(report.architecture_description);
      setMermaidDiagram(report.mermaid_diagram);
      setComponents(report.components);
      setCostBreakdown(report.cost_breakdown);
      setPricingProvenance(report.pricing_provenance);
      setTradeOffs(report.trade_offs);
      setArchAssumptions(report.assumptions);
      setArchLimitations(report.limitations);

      const warnings = report.components
        .map((c) => c.missing_price_warning)
        .filter((w): w is string => !!w);
      setUnverifiedWarnings(warnings);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFoundryError(err.detail);
      } else {
        setFoundryError({
          message:
            err instanceof Error
              ? err.message
              : "Architecture generation failed.",
        });
      }
    } finally {
      setIsGeneratingArch(false);
    }
  };

  // 4. Instant Deterministic Pricing Simulation Trigger
  const triggerSimulation = useCallback(
    async (
      compsToPrice: ArchitectureComponent[],
      assumpToPrice: WorkloadAssumptions,
      buffer: string,
      regionOverride?: string
    ) => {
      if (compsToPrice.length === 0) return;
      setIsSimulating(true);
      const effectiveRegion = regionOverride || targetRegion;

      try {
        const sim = await simulatePricing(
          compsToPrice,
          assumpToPrice,
          effectiveRegion,
          buffer
        );
        setCostBreakdown(sim.cost_breakdown);
        setComponents(sim.components);
        setPricingProvenance(sim.pricing_provenance);
        setUnverifiedWarnings(sim.missing_price_warnings);
        if (sim.assumptions && sim.assumptions.length > 0) {
          setArchAssumptions(sim.assumptions);
        }
      } catch (err: unknown) {
        console.warn("Pricing simulation error:", err);
      } finally {
        setIsSimulating(false);
      }
    },
    [targetRegion]
  );

  // 4b. Region Change Handler (Updates Region & Triggers Simulation)
  const handleTargetRegionChange = (newRegion: string) => {
    setTargetRegion(newRegion);
    const updatedAssump: WorkloadAssumptions = {
      ...assumptions,
      target_region: newRegion,
    };
    setAssumptions(updatedAssump);
    if (components.length > 0) {
      triggerSimulation(components, updatedAssump, safetyBufferPct, newRegion);
    }
  };

  // 5. Presets Selector (Updates Assumptions & Triggers Simulation)
  const handlePresetSelect = (preset: number) => {
    setCustomerPreset(preset);
    let updatedAssump: WorkloadAssumptions;

    if (preset === 21) {
      updatedAssump = {
        ...assumptions,
        customer_count: 21,
        monthly_active_users: 15,
        requests_per_user_per_day: 10,
        peak_rps: 1.0,
        db_storage_gb: 10.0,
        blob_storage_gb: 20.0,
        monthly_egress_gb: 15.0,
        ai_support_monthly_tokens: 200000,
        ha_required: false,
        target_sla_percentage: 99.5,
      };
    } else if (preset === 51) {
      updatedAssump = {
        ...assumptions,
        customer_count: 51,
        monthly_active_users: 40,
        requests_per_user_per_day: 15,
        peak_rps: 5.0,
        db_storage_gb: 25.0,
        blob_storage_gb: 50.0,
        monthly_egress_gb: 40.0,
        ai_support_monthly_tokens: 500000,
        ha_required: false,
        target_sla_percentage: 99.9,
      };
    } else {
      updatedAssump = {
        ...assumptions,
        customer_count: 10000,
        monthly_active_users: 2500,
        requests_per_user_per_day: 20,
        peak_rps: 50.0,
        db_storage_gb: 100.0,
        blob_storage_gb: 200.0,
        monthly_egress_gb: 150.0,
        ai_support_monthly_tokens: 5000000,
        ha_required: true,
        target_sla_percentage: 99.95,
      };
    }

    setAssumptions(updatedAssump);
    if (components.length > 0) {
      triggerSimulation(components, updatedAssump, safetyBufferPct);
    }
  };

  // 6. Direct Assumptions Change Handler
  const handleAssumptionsChange = (updated: WorkloadAssumptions) => {
    setAssumptions(updated);
    if (components.length > 0) {
      triggerSimulation(components, updated, safetyBufferPct);
    }
  };

  // 7. Component Change Handler (Add / Remove / Quantity / SKU)
  const handleComponentsChange = (updatedComps: ArchitectureComponent[]) => {
    setComponents(updatedComps);
    triggerSimulation(updatedComps, assumptions, safetyBufferPct);
  };

  // 8. Buffer Slider Change Handler
  const handleSafetyBufferChange = (val: string) => {
    setSafetyBufferPct(val);
    if (components.length > 0) {
      triggerSimulation(components, assumptions, val);
    }
  };

  // Derived Telemetry States for Header
  const aiStatus: "standby" | "busy" | "verified" | "error" = foundryError
    ? "error"
    : isAnalyzing || isGeneratingArch
      ? "busy"
      : workloadProfile
        ? "verified"
        : "standby";

  const pricingStatus: "standby" | "verified" | "warning" = !costBreakdown
    ? "standby"
    : unverifiedWarnings.length > 0 || costBreakdown.is_complete === false
      ? "warning"
      : "verified";

  return (
    <div className="min-h-screen text-slate-900 pb-24">
      <Header
        backendStatus={backendStatus}
        aiStatus={aiStatus}
        pricingStatus={pricingStatus}
        hasProfile={!!workloadProfile}
        hasArchitecture={components.length > 0}
        hasCost={!!costBreakdown}
        hasAssessment={!!tradeOffs}
        monthlyTotal={costBreakdown?.total_monthly || null}
        activeViewMode={activeViewMode}
        onViewModeChange={setActiveViewMode}
      />

      <main className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        {/* Setup / Config Alert (HTTP 503 / API Errors) */}
        <FoundryConfigAlert
          errorDetail={foundryError}
          onDismiss={() => setFoundryError(null)}
        />

        {/* View Mode 1: AI Cloud Architect & Simulator (Phase A) */}
        {activeViewMode === "architect" && (
          <>
            {/* Step 01: Idea & Requirements Ingestion */}
            <SectionRequirements
              idea={idea}
              setIdea={setIdea}
              targetRegion={targetRegion}
              setTargetRegion={handleTargetRegionChange}
              customerPreset={customerPreset}
              setCustomerPreset={setCustomerPreset}
              onAnalyze={handleAnalyze}
              isAnalyzing={isAnalyzing}
              workloadProfile={workloadProfile}
              clarifyingQuestions={clarifyingQuestions}
              clarifyingAnswers={clarifyingAnswers}
              onAnswerChange={handleClarifyingAnswer}
              missingRequirements={missingRequirements}
              onGenerateArchitecture={handleGenerateArchitecture}
              isGeneratingArch={isGeneratingArch}
            />

            {/* Step 02: Workload Sizing & FinOps Assumptions */}
            <SectionAssumptions
              assumptions={assumptions}
              onAssumptionsChange={handleAssumptionsChange}
              onPresetSelect={handlePresetSelect}
              safetyBufferPct={safetyBufferPct}
              onSafetyBufferChange={handleSafetyBufferChange}
            />

            {/* Guidance Empty State before Architecture Synthesis */}
            {components.length === 0 && (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white/60 p-8 text-center">
                <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-200/80 text-blue-600 flex items-center justify-center mx-auto mb-3">
                  <Sparkles className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-semibold text-slate-900">
                  {workloadProfile
                    ? "Ready to Synthesize Production Azure Architecture"
                    : "Architecture & Cost Workspace Standby"}
                </h3>
                <p className="text-xs text-slate-500 max-w-xl mx-auto mt-1 leading-relaxed">
                  {workloadProfile
                    ? "Review the extracted profile and clarifying questions in Step 01, then click 'Generate Production Architecture' to build the topological blueprint, BOM, and 5-pillar trade-off scorecard."
                    : "Submit your workload specification in Step 01 to extract structured requirements, answer clarifying questions, and generate a deterministic Azure cost simulation."}
                </p>
              </div>
            )}

            {/* Step 03: Production Azure Architecture View */}
            {components.length > 0 && (
              <SectionArchitecture
                architectureDescription={architectureDescription}
                mermaidDiagram={mermaidDiagram}
                components={components}
                onComponentsChange={handleComponentsChange}
              />
            )}

            {/* Step 04: Deterministic Cost Simulator */}
            {costBreakdown && (
              <SectionCostSimulator
                costBreakdown={costBreakdown}
                components={components}
                pricingProvenance={pricingProvenance}
                unverifiedWarnings={unverifiedWarnings}
                isSimulating={isSimulating}
              />
            )}

            {/* Step 05: Architecture Analysis & 5-Pillar Trade-Offs */}
            {tradeOffs && (
              <SectionTradeOffs
                tradeOffs={tradeOffs}
                assumptions={archAssumptions}
                limitations={archLimitations}
              />
            )}
          </>
        )}

        {/* View Mode 2: Subscription & Project Hierarchy Intelligence (Phase B) */}
        {activeViewMode === "inventory" && <SectionCloudScopeInventory />}

        {/* View Mode 3: Multi-Cloud Comparison (Azure vs. GCP) */}
        {activeViewMode === "compare" && (
          <SectionMultiCloudCompare
            currentAssumptions={assumptions}
            currentBufferPct={safetyBufferPct}
          />
        )}
      </main>

      {/* Floating Glassmorphic FinOps Summary Dock (Visible when Cost Breakdown is active in Architect view) */}
      {activeViewMode === "architect" && costBreakdown && (
        <div className="fixed bottom-4 inset-x-0 z-40 px-4 pointer-events-none">
          <div className="max-w-4xl mx-auto glass-floating border border-slate-200/90 rounded-2xl shadow-floating px-4 py-2.5 pointer-events-auto flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1.5 font-semibold text-slate-800">
                {isSimulating ? (
                  <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
                ) : (
                  <Calculator className="w-4 h-4 text-blue-600" />
                )}
                <span>Live Estimate</span>
              </span>
              <span className="hidden sm:inline-flex items-center gap-1 text-slate-500">
                <Layers className="w-3.5 h-3.5 text-slate-400" />
                <span>{components.length} services</span>
              </span>
            </div>

            <div className="flex items-center gap-4 sm:gap-6 font-mono">
              <div>
                <span className="text-[10px] text-slate-400 uppercase font-sans block">
                  Monthly
                </span>
                <span className="font-bold text-slate-900 text-sm">
                  ${parseFloat(costBreakdown.total_monthly).toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </span>
              </div>
              <div className="hidden sm:block">
                <span className="text-[10px] text-slate-400 uppercase font-sans block">
                  5-Month
                </span>
                <span className="font-semibold text-slate-700 text-xs">
                  ${parseFloat(costBreakdown.total_five_month).toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 uppercase font-sans block">
                  Annual
                </span>
                <span className="font-semibold text-emerald-700 text-xs">
                  ${parseFloat(costBreakdown.total_annual).toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  const el = document.getElementById("section-cost");
                  if (el) el.scrollIntoView({ behavior: "smooth" });
                }}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-sans font-semibold text-[11px] transition"
              >
                <span>BOM</span>
                <ArrowDown className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
