"use client";

import React, { useState, useCallback, useEffect } from "react";
import { Sidebar, ViewMode } from "@/components/Sidebar";
import { TopNav } from "@/components/TopNav";
import { LandingView } from "@/components/LandingView";
import { DashboardView } from "@/components/DashboardView";
import { ArchitectStepper, ArchitectStep } from "@/components/ArchitectStepper";
import { FoundryConfigAlert } from "@/components/FoundryConfigAlert";
import { SectionRequirements } from "@/components/SectionRequirements";
import { SectionAssumptions } from "@/components/SectionAssumptions";
import { SectionArchitecture } from "@/components/SectionArchitecture";
import { SectionCostSimulator } from "@/components/SectionCostSimulator";
import { SectionSavingsReview } from "@/components/SectionSavingsReview";
import { SectionCloudScopeInventory } from "@/components/SectionCloudScopeInventory";
import {
  SectionCentralizedMonitoring,
  MonitoringSubTab,
} from "@/components/SectionCentralizedMonitoring";
import { SectionMultiCloudCompare } from "@/components/SectionMultiCloudCompare";
import { ConnectCloudView } from "@/components/ConnectCloudView";
import { SettingsModal } from "@/components/SettingsModal";
import {
  ApiErrorDetail,
  ArchitectureComponent,
  ClarifyingAnswer,
  ClarifyingQuestion,
  CloudConnection,
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
import {
  Sparkles,
  Calculator,
  ArrowRight,
  ArrowLeft,
  ShieldCheck,
  Layers,
} from "lucide-react";

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
  // Cloud Connection Onboarding State (Default null = Connect Cloud View)
  const [activeConnection, setActiveConnection] =
    useState<CloudConnection | null>(null);

  // Navigation & Shell State
  const [activeView, setActiveView] = useState<ViewMode>("monitoring");
  const [activeMonitoringTab, setActiveMonitoringTab] =
    useState<MonitoringSubTab>("overview");
  const [architectStep, setArchitectStep] = useState<ArchitectStep>("requirements");
  const [architectMode, setArchitectMode] = useState<"step" | "all">("step");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");

  const handleSelectMonitoringTab = useCallback((tab: MonitoringSubTab) => {
    setActiveMonitoringTab(tab);
    setActiveView("monitoring");
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", tab);
      url.searchParams.set("view", "monitoring");
      window.history.pushState({ tab, view: "monitoring" }, "", url.toString());
    }
  }, []);

  // Sync URL query params on initial mount and on popstate (browser back/forward navigation)
  useEffect(() => {
    const syncFromUrl = () => {
      if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search);
        const tabParam = params.get("tab") as MonitoringSubTab | null;
        const validTabs: MonitoringSubTab[] = [
          "overview",
          "resources",
          "health",
          "alerts",
          "hierarchy",
          "logs",
          "tokens",
          "cost_waste",
        ];
        if (tabParam && validTabs.includes(tabParam)) {
          setActiveMonitoringTab(tabParam);
        }
        const viewParam = params.get("view") as ViewMode | null;
        const validViews: ViewMode[] = [
          "home",
          "dashboard",
          "architect",
          "inventory",
          "monitoring",
          "compare",
        ];
        if (viewParam && validViews.includes(viewParam)) {
          setActiveView(viewParam);
        }
      }
    };

    syncFromUrl();
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
  }, []);

  // Backend Connectivity State
  const [backendStatus, setBackendStatus] = useState<
    "checking" | "online" | "offline"
  >("checking");

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

      // Automatically advance step to Blueprint
      setArchitectStep("blueprint");
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

  // 4b. Region Change Handler
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

  // 5. Presets Selector
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

  // 7. Component Change Handler
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

  // Telemetry status derivations
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

  const scrollToCostSection = () => {
    setActiveView("architect");
    setArchitectStep("simulator");
    setTimeout(() => {
      const el = document.getElementById("section-cost");
      if (el) el.scrollIntoView({ behavior: "smooth" });
    }, 100);
  };

  // If no cloud account is actively connected, show the First-Screen Onboarding
  if (!activeConnection) {
    return (
      <div className="min-h-screen bg-background text-navy-900 flex flex-col">
        {/* Connection Onboarding Top Header */}
        <header className="topbar-surface sticky top-0 z-30 h-14 px-4 sm:px-6 flex items-center justify-between border-b border-slate-200 bg-white">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-brand-600 text-white flex items-center justify-center font-bold shadow-2xs">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-xs text-navy-900 tracking-tight">
                  FinOps &amp; Infrastructure Intelligence Platform
                </span>
                <span className="text-[10px] uppercase font-bold px-1.5 py-0.2 rounded bg-blue-50 text-brand-600 border border-blue-200">
                  POC
                </span>
              </div>
              <span className="text-[10px] text-slate-400 block">
                Connect your cloud account to begin
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-medium">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              <span>Strictly Read-Only &bull; Zero-Execution Policy</span>
            </span>
          </div>
        </header>

        {/* Onboarding View Body */}
        <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-8">
          <ConnectCloudView
            onConnectionSelected={(conn) => {
              setActiveConnection(conn);
              setActiveView("monitoring");
            }}
            onContinueToDemo={() => {
              setActiveConnection({
                id: "conn-azure-reference",
                name: "Azure Reference Tenant",
                provider: "azure",
                scope_id: "f718c261-ab85-49fd-907e-99c022cc2aeb",
                display_name: "Azure Sponsorship (f718c261...)",
                auth_method: "azure_cli_credentials",
                status: "connected",
                is_live: true,
                capabilities: ["inventory", "monitoring", "pricing"],
                access_limitations: [],
                last_verified_at: new Date().toISOString(),
              });
              setActiveView("monitoring");
            }}
          />
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-navy-900 flex">
      {/* 1. Permanent / Collapsible Left Sidebar */}
      <Sidebar
        currentView={activeView}
        onViewChange={(view) => {
          setActiveView(view);
          setIsMobileMenuOpen(false);
        }}
        currentMonitoringTab={activeMonitoringTab}
        onSelectMonitoringTab={handleSelectMonitoringTab}
        onOpenSettings={() => setIsSettingsOpen(true)}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed((prev) => !prev)}
        isMobileOpen={isMobileMenuOpen}
        onCloseMobile={() => setIsMobileMenuOpen(false)}
      />

      {/* 2. Main Workspace Layout */}
      <div
        className={`flex-1 flex flex-col min-w-0 transition-all duration-200 ${
          isSidebarCollapsed ? "sm:pl-16" : "sm:pl-60"
        }`}
      >
        {/* Top Header Bar */}
        <TopNav
          backendStatus={backendStatus}
          aiStatus={aiStatus}
          pricingStatus={pricingStatus}
          monthlyTotal={costBreakdown?.total_monthly || null}
          targetRegion={targetRegion}
          onRegionChange={handleTargetRegionChange}
          onOpenMobileMenu={() => setIsMobileMenuOpen(true)}
          onScrollToCost={scrollToCostSection}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          connectedScope={{
            provider: activeConnection.provider,
            name: activeConnection.display_name || activeConnection.name,
            id: activeConnection.scope_id,
          }}
          onSwitchConnection={() => setActiveConnection(null)}
        />

        {/* Main Content Viewport */}
        <main className="flex-1 max-w-[1440px] w-full mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-16">
          {/* Foundry / Backend Error Notice */}
          <FoundryConfigAlert
            errorDetail={foundryError}
            onDismiss={() => setFoundryError(null)}
          />

          {/* SCREEN 1: Home / Product Landing */}
          {activeView === "home" && (
            <LandingView
              onNavigate={(v) => {
                if (v === "architect") {
                  setActiveView("architect");
                  setArchitectStep("requirements");
                } else {
                  setActiveView(v);
                }
              }}
              monthlyTotal={costBreakdown?.total_monthly || null}
              connectedScope={
                activeConnection
                  ? activeConnection.display_name ||
                    activeConnection.name ||
                    activeConnection.scope_id
                  : null
              }
            />
          )}

          {/* SCREEN 2: Executive FinOps Dashboard */}
          {activeView === "dashboard" && (
            <DashboardView
              onNavigate={(v) => {
                setActiveView(v);
                if (v === "architect") setArchitectStep("requirements");
              }}
              monthlyTotal={costBreakdown?.total_monthly || null}
              region={targetRegion}
              connectedScope={
                activeConnection
                  ? {
                      provider: activeConnection.provider,
                      name: activeConnection.display_name || activeConnection.name,
                      id: activeConnection.scope_id,
                    }
                  : null
              }
              costBreakdown={costBreakdown}
            />
          )}

          {/* SCREENS 3–7: AI Cloud Architect (5-Step Workspace) */}
          {activeView === "architect" && (
            <div className="space-y-6">
              {/* Architect Stepper Header */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-2 border-b border-slate-200">
                <div>
                  <h1 className="text-xl sm:text-2xl font-bold text-navy-900 tracking-tight">
                    AI Cloud Architect &amp; FinOps Simulator
                  </h1>
                  <p className="text-xs text-navy-600 mt-0.5">
                    Synthesize production architectures, explore deterministic bills of materials, and assess 5-pillar trade-offs.
                  </p>
                </div>

                {/* View Mode Toggle: Step-by-Step vs All Steps Combined */}
                <div className="flex items-center gap-2 self-start sm:self-auto">
                  <div className="flex items-center p-0.5 bg-slate-100 rounded-lg border border-slate-200 text-xs">
                    <button
                      type="button"
                      onClick={() => setArchitectMode("step")}
                      className={`px-3 py-1 rounded-md font-medium transition ${
                        architectMode === "step"
                          ? "bg-white text-navy-900 shadow-2xs font-semibold"
                          : "text-navy-600 hover:text-navy-900"
                      }`}
                    >
                      Step-by-Step Focus
                    </button>
                    <button
                      type="button"
                      onClick={() => setArchitectMode("all")}
                      className={`px-3 py-1 rounded-md font-medium transition ${
                        architectMode === "all"
                          ? "bg-white text-navy-900 shadow-2xs font-semibold"
                          : "text-navy-600 hover:text-navy-900"
                      }`}
                    >
                      Combined View
                    </button>
                  </div>
                </div>
              </div>

              {/* 5-Step Stepper Navigation */}
              <ArchitectStepper
                currentStep={architectStep}
                onStepChange={setArchitectStep}
                hasProfile={!!workloadProfile}
                hasArchitecture={components.length > 0}
                hasCost={!!costBreakdown}
                hasAssessment={!!tradeOffs}
              />

              {/* STEP 1: Requirements Ingestion & Clarifications (Screen 3) */}
              {(architectMode === "all" || architectStep === "requirements") && (
                <div className="space-y-4">
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

                  {architectMode === "step" && workloadProfile && (
                    <div className="flex justify-end pt-2">
                      <button
                        type="button"
                        onClick={() => setArchitectStep("sizing")}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-medium text-xs shadow-2xs transition"
                      >
                        <span>Continue to Workload Sizing (Step 02)</span>
                        <ArrowRight className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* STEP 2: Workload Sizing & Presets (Screen 4) */}
              {(architectMode === "all" || architectStep === "sizing") && (
                <div className="space-y-4">
                  <SectionAssumptions
                    assumptions={assumptions}
                    onAssumptionsChange={handleAssumptionsChange}
                    onPresetSelect={handlePresetSelect}
                    safetyBufferPct={safetyBufferPct}
                    onSafetyBufferChange={handleSafetyBufferChange}
                  />

                  {architectMode === "step" && (
                    <div className="flex items-center justify-between pt-2">
                      <button
                        type="button"
                        onClick={() => setArchitectStep("requirements")}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white hover:bg-slate-50 text-navy-700 font-medium text-xs border border-slate-200 transition"
                      >
                        <ArrowLeft className="w-4 h-4" />
                        <span>Back to Requirements</span>
                      </button>

                      {components.length > 0 ? (
                        <button
                          type="button"
                          onClick={() => setArchitectStep("blueprint")}
                          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-medium text-xs shadow-2xs transition"
                        >
                          <span>View Architecture Blueprint (Step 03)</span>
                          <ArrowRight className="w-4 h-4" />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={handleGenerateArchitecture}
                          disabled={!workloadProfile || isGeneratingArch}
                          className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 disabled:bg-slate-300 text-white font-medium text-xs shadow-2xs transition"
                        >
                          <Sparkles className="w-4 h-4" />
                          <span>Generate Architecture Blueprint</span>
                          <ArrowRight className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* STEP 3: Architecture Blueprint & Topology (Screen 5) */}
              {(architectMode === "all" || architectStep === "blueprint") && (
                <div className="space-y-4">
                  {components.length > 0 ? (
                    <>
                      <SectionArchitecture
                        architectureDescription={architectureDescription}
                        mermaidDiagram={mermaidDiagram}
                        components={components}
                        onComponentsChange={handleComponentsChange}
                      />

                      {architectMode === "step" && (
                        <div className="flex items-center justify-between pt-2">
                          <button
                            type="button"
                            onClick={() => setArchitectStep("sizing")}
                            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white hover:bg-slate-50 text-navy-700 font-medium text-xs border border-slate-200 transition"
                          >
                            <ArrowLeft className="w-4 h-4" />
                            <span>Back to Sizing</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => setArchitectStep("simulator")}
                            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-medium text-xs shadow-2xs transition"
                          >
                            <span>Open Cost Simulator &amp; BOM (Step 04)</span>
                            <ArrowRight className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="app-card p-8 text-center bg-white border border-dashed border-slate-300">
                      <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-200 text-brand-600 flex items-center justify-center mx-auto mb-3">
                        <Sparkles className="w-5 h-5" />
                      </div>
                      <h3 className="text-sm font-semibold text-navy-900">
                        No Architecture Blueprint Generated Yet
                      </h3>
                      <p className="text-xs text-navy-500 max-w-md mx-auto mt-1 mb-4 leading-relaxed">
                        Complete your requirements in Step 01 or sizing in Step 02 to synthesize a production topology with deterministic pricing.
                      </p>
                      <button
                        type="button"
                        onClick={() => setArchitectStep("requirements")}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-xs transition"
                      >
                        <span>Start in Requirements (Step 01)</span>
                        <ArrowRight className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* STEP 4: Deterministic Cost Simulator & BOM (Screen 6) */}
              {(architectMode === "all" || architectStep === "simulator") && (
                <div className="space-y-4">
                  {costBreakdown ? (
                    <>
                      <SectionCostSimulator
                        costBreakdown={costBreakdown}
                        components={components}
                        pricingProvenance={pricingProvenance}
                        unverifiedWarnings={unverifiedWarnings}
                        isSimulating={isSimulating}
                      />

                      {architectMode === "step" && (
                        <div className="flex items-center justify-between pt-2">
                          <button
                            type="button"
                            onClick={() => setArchitectStep("blueprint")}
                            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white hover:bg-slate-50 text-navy-700 font-medium text-xs border border-slate-200 transition"
                          >
                            <ArrowLeft className="w-4 h-4" />
                            <span>Back to Blueprint</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => setArchitectStep("review")}
                            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-medium text-xs shadow-2xs transition"
                          >
                            <span>View Savings &amp; Review (Step 05)</span>
                            <ArrowRight className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="app-card p-8 text-center bg-white border border-dashed border-slate-300">
                      <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200 text-accent-amber flex items-center justify-center mx-auto mb-3">
                        <Calculator className="w-5 h-5" />
                      </div>
                      <h3 className="text-sm font-semibold text-navy-900">
                        Cost Simulation Standby
                      </h3>
                      <p className="text-xs text-navy-500 max-w-md mx-auto mt-1 mb-4 leading-relaxed">
                        Generate an architecture blueprint first to calculate deterministic line-item prices using the official Azure Retail Prices API.
                      </p>
                      <button
                        type="button"
                        onClick={() => setArchitectStep("requirements")}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-xs transition"
                      >
                        <span>Start Requirements Analysis</span>
                        <ArrowRight className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* STEP 5: Savings Recommendations & Review (Screen 7) */}
              {(architectMode === "all" || architectStep === "review") && (
                <div className="space-y-4">
                  <SectionSavingsReview
                    tradeOffs={tradeOffs}
                    assumptions={archAssumptions}
                    limitations={archLimitations}
                    costBreakdown={costBreakdown}
                  />

                  {architectMode === "step" && (
                    <div className="flex items-center justify-between pt-2">
                      <button
                        type="button"
                        onClick={() => setArchitectStep("simulator")}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white hover:bg-slate-50 text-navy-700 font-medium text-xs border border-slate-200 transition"
                      >
                        <ArrowLeft className="w-4 h-4" />
                        <span>Back to Cost Simulator</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => setActiveView("monitoring")}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-xs shadow-2xs transition"
                      >
                        <span>Inspect Centralized Monitoring &rarr;</span>
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* SCREEN 8: Centralized Cloud Infrastructure Monitoring & Log Analysis */}
          {activeView === "monitoring" && (
            <SectionCentralizedMonitoring
              initialConnection={activeConnection}
              activeTab={activeMonitoringTab}
              onTabChange={handleSelectMonitoringTab}
              onSwitchConnection={() => setActiveConnection(null)}
            />
          )}

          {/* SCREEN 9a: Subscription & Resource Hierarchy Intelligence */}
          {activeView === "inventory" && <SectionCloudScopeInventory />}

          {/* SCREEN 9b: Multi-Cloud Comparison (Azure vs. GCP) */}
          {activeView === "compare" && (
            <SectionMultiCloudCompare
              currentAssumptions={assumptions}
              currentBufferPct={safetyBufferPct}
            />
          )}
        </main>
      </div>

      {/* Platform Governance & Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        backendStatus={backendStatus}
        targetRegion={targetRegion}
      />
    </div>
  );
}
