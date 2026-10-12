"use client";

import React, { useState, useCallback } from "react";
import { Header } from "@/components/Header";
import { FoundryConfigAlert } from "@/components/FoundryConfigAlert";
import { SectionRequirements } from "@/components/SectionRequirements";
import { SectionAssumptions } from "@/components/SectionAssumptions";
import { SectionArchitecture } from "@/components/SectionArchitecture";
import { SectionCostSimulator } from "@/components/SectionCostSimulator";
import { SectionTradeOffs } from "@/components/SectionTradeOffs";
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
  generateArchitecture,
  simulatePricing,
  ApiError,
} from "@/lib/api";

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
  // Section A State
  const [idea, setIdea] = useState<string>(
    "I want a customer management platform for 10,000 customers with user authentication, a web frontend, REST APIs, PostgreSQL, document storage, monitoring, high availability, and AI-powered customer support."
  );
  const [targetRegion, setTargetRegion] = useState<string>("eastus");
  const [customerPreset, setCustomerPreset] = useState<number>(10000);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [workloadProfile, setWorkloadProfile] = useState<WorkloadProfile | null>(null);
  const [clarifyingQuestions, setClarifyingQuestions] = useState<ClarifyingQuestion[]>([]);
  const [clarifyingAnswers, setClarifyingAnswers] = useState<Record<string, string>>({});
  const [missingRequirements, setMissingRequirements] = useState<string[]>([]);
  const [foundryError, setFoundryError] = useState<ApiErrorDetail | null>(null);

  // Section B State
  const [assumptions, setAssumptions] = useState<WorkloadAssumptions>(DEFAULT_ASSUMPTIONS);
  const [safetyBufferPct, setSafetyBufferPct] = useState<string>("15.00");

  // Section C State
  const [isGeneratingArch, setIsGeneratingArch] = useState<boolean>(false);
  const [architectureDescription, setArchitectureDescription] = useState<string>("");
  const [mermaidDiagram, setMermaidDiagram] = useState<string>("");
  const [components, setComponents] = useState<ArchitectureComponent[]>([]);

  // Section D & E State
  const [costBreakdown, setCostBreakdown] = useState<CostBreakdown | null>(null);
  const [pricingProvenance, setPricingProvenance] = useState<PricingReference[]>([]);
  const [tradeOffs, setTradeOffs] = useState<TradeOffAssessment | null>(null);
  const [archAssumptions, setArchAssumptions] = useState<string[]>([]);
  const [archLimitations, setArchLimitations] = useState<string[]>([]);
  const [unverifiedWarnings, setUnverifiedWarnings] = useState<string[]>([]);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);

  // 1. Analyze Requirements Handler
  const handleAnalyze = async () => {
    setIsAnalyzing(true);
    setFoundryError(null);
    try {
      const res = await analyzeRequirements(idea, targetRegion, customerPreset);
      setWorkloadProfile(res.workload_profile);
      setClarifyingQuestions(res.clarifying_questions);
      setAssumptions(res.workload_assumptions);
      setMissingRequirements(res.missing_critical_requirements);

      // Pre-fill default answers
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
        setFoundryError({ message: err instanceof Error ? err.message : "Failed to analyze requirements." });
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

    const answersList: ClarifyingAnswer[] = Object.entries(clarifyingAnswers).map(
      ([qId, ans]) => ({
        question_id: qId,
        selected_option: ans,
      })
    );

    try {
      const report: RecommendationReport = await generateArchitecture(
        workloadProfile,
        assumptions,
        answersList,
        targetRegion
      );

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
        setFoundryError({ message: err instanceof Error ? err.message : "Architecture generation failed." });
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
      buffer: string
    ) => {
      if (compsToPrice.length === 0) return;
      setIsSimulating(true);

      try {
        const sim = await simulatePricing(compsToPrice, assumpToPrice, targetRegion, buffer);
        setCostBreakdown(sim.cost_breakdown);
        setComponents(sim.updated_components);
        setPricingProvenance(sim.pricing_provenance);
        setUnverifiedWarnings(sim.unverified_price_warnings);
      } catch (err: unknown) {
        console.warn("Pricing simulation error:", err);
      } finally {
        setIsSimulating(false);
      }
    },
    [targetRegion]
  );

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

  // 7. Component Change Handler (Add / Remove / Quantity)
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

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-16">
      <Header />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        {/* Setup / Config Alert (HTTP 503) */}
        <FoundryConfigAlert
          errorDetail={foundryError}
          onDismiss={() => setFoundryError(null)}
        />

        {/* Section A: Idea & Requirements */}
        <SectionRequirements
          idea={idea}
          setIdea={setIdea}
          targetRegion={targetRegion}
          setTargetRegion={setTargetRegion}
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

        {/* Section B: Sizing & Assumptions Controls */}
        <SectionAssumptions
          assumptions={assumptions}
          onAssumptionsChange={handleAssumptionsChange}
          onPresetSelect={handlePresetSelect}
          safetyBufferPct={safetyBufferPct}
          onSafetyBufferChange={handleSafetyBufferChange}
        />

        {/* Section C: Production Architecture View */}
        {components.length > 0 && (
          <SectionArchitecture
            architectureDescription={architectureDescription}
            mermaidDiagram={mermaidDiagram}
            components={components}
            onComponentsChange={handleComponentsChange}
          />
        )}

        {/* Section D: Deterministic Cost Simulator */}
        {costBreakdown && (
          <SectionCostSimulator
            costBreakdown={costBreakdown}
            components={components}
            pricingProvenance={pricingProvenance}
            unverifiedWarnings={unverifiedWarnings}
            isSimulating={isSimulating}
          />
        )}

        {/* Section E: Architecture Analysis & Trade-Offs */}
        {tradeOffs && (
          <SectionTradeOffs
            tradeOffs={tradeOffs}
            assumptions={archAssumptions}
            limitations={archLimitations}
          />
        )}
      </main>
    </div>
  );
}
