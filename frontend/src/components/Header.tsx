"use client";

import React, { useState } from "react";
import {
  Layers,
  ShieldCheck,
  Sparkles,
  Calculator,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
  Menu,
  X,
  CircleDot,
} from "lucide-react";

export interface HeaderProps {
  backendStatus?: "checking" | "online" | "offline";
  aiStatus?: "standby" | "busy" | "verified" | "error";
  pricingStatus?: "standby" | "verified" | "warning";
  hasProfile?: boolean;
  hasArchitecture?: boolean;
  hasCost?: boolean;
  hasAssessment?: boolean;
  monthlyTotal?: string | null;
  activeViewMode?: "architect" | "inventory" | "compare";
  onViewModeChange?: (mode: "architect" | "inventory" | "compare") => void;
}

export const Header: React.FC<HeaderProps> = ({
  backendStatus = "checking",
  aiStatus = "standby",
  pricingStatus = "standby",
  hasProfile = false,
  hasArchitecture = false,
  hasCost = false,
  hasAssessment = false,
  monthlyTotal = null,
  activeViewMode = "architect",
  onViewModeChange,
}) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navSteps = [
    {
      id: "section-requirements",
      step: "1",
      label: "Requirements",
      complete: hasProfile,
      available: true,
    },
    {
      id: "section-sizing",
      step: "2",
      label: "Workload Sizing",
      complete: hasProfile,
      available: true,
    },
    {
      id: "section-architecture",
      step: "3",
      label: "Architecture",
      complete: hasArchitecture,
      available: hasArchitecture,
    },
    {
      id: "section-cost",
      step: "4",
      label: "Cost Simulator",
      complete: hasCost,
      available: hasCost,
    },
    {
      id: "section-assessment",
      step: "5",
      label: "Assessment",
      complete: hasAssessment,
      available: hasAssessment,
    },
  ];

  const scrollToSection = (id: string, available: boolean) => {
    if (!available) return;
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    setMobileMenuOpen(false);
  };

  const renderFoundryBadge = () => {
    if (backendStatus === "offline" || aiStatus === "error") {
      return (
        <span
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200/80 text-xs font-medium"
          title="Azure AI Foundry connection error or backend unreachable"
        >
          <XCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
          <span>Foundry Disconnected</span>
        </span>
      );
    }
    if (aiStatus === "busy" || backendStatus === "checking") {
      return (
        <span
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200/80 text-xs font-medium"
          title="Communicating with Azure AI Foundry"
        >
          <Loader2 className="w-3.5 h-3.5 text-blue-600 animate-spin shrink-0" />
          <span>Foundry Active</span>
        </span>
      );
    }
    if (aiStatus === "verified") {
      return (
        <span
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/80 text-xs font-medium"
          title="Azure AI Foundry inference verified"
        >
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
          <span>Azure AI Foundry Connected</span>
        </span>
      );
    }
    return (
      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 border border-slate-200/80 text-xs font-medium"
        title="Backend online; awaiting first AI inference call"
      >
        <Sparkles className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
        <span>Azure AI Foundry Ready</span>
      </span>
    );
  };

  const renderPricingBadge = () => {
    if (pricingStatus === "warning") {
      return (
        <span
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200/80 text-xs font-medium"
          title="One or more services have unverified or fallback pricing warnings"
        >
          <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
          <span>Pricing Notice</span>
        </span>
      );
    }
    if (pricingStatus === "verified") {
      return (
        <span
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/80 text-xs font-medium"
          title="All active service components matched to deterministic pricing meters"
        >
          <Calculator className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
          <span>Retail Prices Verified</span>
        </span>
      );
    }
    return (
      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200/80 text-xs font-medium"
        title="Azure Retail Prices deterministic engine standby"
      >
        <Calculator className="w-3.5 h-3.5 text-slate-500 shrink-0" />
        <span>Retail Prices API</span>
      </span>
    );
  };

  return (
    <header className="glass-header sticky top-0 z-50 border-b border-slate-200/80 transition-colors">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8">
        {/* Top Row: Brand & Status Telemetry */}
        <div className="h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 via-indigo-600 to-violet-600 text-white flex items-center justify-center shadow-2xs shrink-0">
              <Layers className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-slate-900 tracking-tight truncate">
                  FinOps &amp; Infrastructure Intelligence
                </h1>
                <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200/70 text-[11px] font-semibold tracking-wide shrink-0">
                  Platform
                </span>
              </div>
              <p className="text-[11px] text-slate-500 truncate hidden sm:block">
                Understand your infrastructure. Optimize your costs. Engineer what comes next.
              </p>
            </div>
          </div>

          {/* Desktop Status Indicators & Live Cost Pill */}
          <div className="hidden lg:flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100/90 text-slate-700 border border-slate-200/80 text-xs font-medium">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
              <span>Advisory Only</span>
            </span>
            {renderFoundryBadge()}
            {renderPricingBadge()}
            {monthlyTotal && (
              <button
                type="button"
                onClick={() => scrollToSection("section-cost", true)}
                className="ml-1 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-900 text-white text-xs font-semibold shadow-2xs hover:bg-slate-800 transition"
                title="Jump to Cost Simulator"
              >
                <span className="text-slate-300 font-normal">Est.</span>
                <span className="font-mono">${parseFloat(monthlyTotal).toFixed(2)}/mo</span>
              </button>
            )}
          </div>

          {/* Mobile Menu Button */}
          <div className="flex items-center gap-2 lg:hidden">
            {monthlyTotal && (
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-slate-900 text-white text-xs font-mono font-semibold">
                ${parseFloat(monthlyTotal).toFixed(0)}/mo
              </span>
            )}
            <button
              type="button"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              aria-expanded={mobileMenuOpen}
              aria-label="Toggle workspace navigation menu"
              className="p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Secondary Row: Mode Switcher & Stepper */}
        <nav
          aria-label="Workspace workflow modes and steps"
          className="hidden md:flex items-center justify-between py-2 border-t border-slate-200/60 text-xs gap-4"
        >
          {/* Main Mode Switcher */}
          <div className="flex items-center gap-1.5 p-0.5 bg-slate-100 rounded-lg border border-slate-200/80 shrink-0">
            <button
              type="button"
              onClick={() => onViewModeChange?.("architect")}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition ${
                activeViewMode === "architect"
                  ? "bg-white text-blue-700 shadow-xs border border-slate-200/60"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              AI Architect &amp; Simulator
            </button>
            <button
              type="button"
              onClick={() => onViewModeChange?.("inventory")}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition ${
                activeViewMode === "inventory"
                  ? "bg-white text-blue-700 shadow-xs border border-slate-200/60"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Subscription Hierarchy
            </button>
            <button
              type="button"
              onClick={() => onViewModeChange?.("compare")}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition ${
                activeViewMode === "compare"
                  ? "bg-white text-indigo-700 shadow-xs border border-slate-200/60"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Azure vs. GCP Compare
            </button>
          </div>

          {/* Stepper only active when in Architect view */}
          {activeViewMode === "architect" && (
            <ol className="flex items-center gap-1.5 overflow-x-auto">
              {navSteps.map((item, idx) => (
                <li key={item.id} className="flex items-center">
                  <button
                    type="button"
                    disabled={!item.available}
                    onClick={() => scrollToSection(item.id, item.available)}
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-medium text-[11px] transition ${
                      item.complete
                        ? "text-slate-900 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200"
                        : item.available
                          ? "text-slate-700 hover:text-blue-700 hover:bg-slate-100"
                          : "text-slate-400 cursor-not-allowed opacity-70"
                    }`}
                  >
                    {item.complete ? (
                      <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0" />
                    ) : item.available ? (
                      <CircleDot className="w-3 h-3 text-blue-600 shrink-0" />
                    ) : (
                      <span className="w-3.5 h-3.5 rounded-full bg-slate-200 text-slate-500 text-[9px] font-bold flex items-center justify-center shrink-0">
                        {item.step}
                      </span>
                    )}
                    <span>{item.label}</span>
                  </button>
                  {idx < navSteps.length - 1 && (
                    <span className="mx-0.5 text-slate-300 select-none" aria-hidden="true">
                      /
                    </span>
                  )}
                </li>
              ))}
            </ol>
          )}

          <div className="text-[11px] text-slate-400 font-medium hidden xl:block shrink-0">
            {activeViewMode === "compare" ? (
              <span>Comparing: <strong className="text-slate-700">Azure vs. GCP</strong></span>
            ) : (
              <span>Target Cloud: <strong className="text-slate-700">Microsoft Azure &amp; GCP</strong></span>
            )}
          </div>
        </nav>

        {/* Mobile Drawer Navigation */}
        {mobileMenuOpen && (
          <div className="lg:hidden py-3 border-t border-slate-200/80 space-y-3">
            {/* Mobile View Mode Switcher */}
            <div className="grid grid-cols-3 gap-1 p-1 bg-slate-100 rounded-lg border border-slate-200/80">
              <button
                type="button"
                onClick={() => {
                  onViewModeChange?.("architect");
                  setMobileMenuOpen(false);
                }}
                className={`py-1.5 px-2 rounded-md text-[11px] font-semibold text-center transition ${
                  activeViewMode === "architect"
                    ? "bg-white text-blue-700 shadow-xs border border-slate-200/60"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                AI Architect
              </button>
              <button
                type="button"
                onClick={() => {
                  onViewModeChange?.("inventory");
                  setMobileMenuOpen(false);
                }}
                className={`py-1.5 px-2 rounded-md text-[11px] font-semibold text-center transition ${
                  activeViewMode === "inventory"
                    ? "bg-white text-blue-700 shadow-xs border border-slate-200/60"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Hierarchy
              </button>
              <button
                type="button"
                onClick={() => {
                  onViewModeChange?.("compare");
                  setMobileMenuOpen(false);
                }}
                className={`py-1.5 px-2 rounded-md text-[11px] font-semibold text-center transition ${
                  activeViewMode === "compare"
                    ? "bg-white text-indigo-700 shadow-xs border border-slate-200/60"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Compare
              </button>
            </div>

            <div className="flex flex-wrap gap-1.5">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-medium">
                <ShieldCheck className="w-3 h-3 text-emerald-600" />
                Advisory Only
              </span>
              {renderFoundryBadge()}
              {renderPricingBadge()}
            </div>
            {activeViewMode === "architect" && (
              <nav aria-label="Mobile workspace steps" className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                {navSteps.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    disabled={!item.available}
                    onClick={() => {
                      scrollToSection(item.id, item.available);
                      setMobileMenuOpen(false);
                    }}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-left border transition ${
                      item.complete
                        ? "bg-emerald-50/70 border-emerald-200 text-slate-900"
                        : item.available
                          ? "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
                          : "bg-slate-50 border-slate-100 text-slate-400 cursor-not-allowed"
                    }`}
                  >
                    {item.complete ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                    ) : (
                      <span className="w-4 h-4 rounded-full bg-slate-200 text-slate-600 text-[10px] font-bold flex items-center justify-center shrink-0">
                        {item.step}
                      </span>
                    )}
                    <span className="truncate">{item.label}</span>
                  </button>
                ))}
              </nav>
            )}
          </div>
        )}
      </div>
    </header>
  );
};
