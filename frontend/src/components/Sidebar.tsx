"use client";

import React, { useState } from "react";
import {
  Layers,
  LayoutDashboard,
  Sparkles,
  FolderTree,
  Activity,
  Settings,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Home,
  BarChart3,
  HeartPulse,
  BellRing,
  Terminal,
  Coins,
  TrendingDown,
} from "lucide-react";

import { ENABLE_AI_ARCHITECT } from "@/config/features";
import { MonitoringSubTab } from "./SectionCentralizedMonitoring";

export type ViewMode =
  | "home"
  | "dashboard"
  | "architect"
  | "inventory"
  | "monitoring"
  | "compare";

interface SidebarProps {
  currentView: ViewMode;
  onViewChange: (view: ViewMode) => void;
  currentMonitoringTab?: MonitoringSubTab;
  onSelectMonitoringTab?: (tab: MonitoringSubTab) => void;
  onOpenSettings: () => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentView,
  onViewChange,
  currentMonitoringTab = "overview",
  onSelectMonitoringTab,
  onOpenSettings,
  isCollapsed,
  onToggleCollapse,
  isMobileOpen = false,
  onCloseMobile,
}) => {
  const [isMonitoringOpen, setIsMonitoringOpen] = useState<boolean>(true);

  const monitoringSubNav: { id: MonitoringSubTab; label: string; icon: React.ReactNode }[] = [
    {
      id: "overview",
      label: "Overview & Trends",
      icon: <BarChart3 className="w-3.5 h-3.5" />,
    },
    {
      id: "resources",
      label: "Resources",
      icon: <Layers className="w-3.5 h-3.5" />,
    },
    {
      id: "health",
      label: "Health",
      icon: <HeartPulse className="w-3.5 h-3.5" />,
    },
    {
      id: "alerts",
      label: "Active Alerts",
      icon: <BellRing className="w-3.5 h-3.5" />,
    },
    {
      id: "hierarchy",
      label: "Hierarchy Explorer",
      icon: <FolderTree className="w-3.5 h-3.5" />,
    },
    {
      id: "logs",
      label: "Log Explorer",
      icon: <Terminal className="w-3.5 h-3.5" />,
    },
    {
      id: "tokens",
      label: "Token Economics",
      icon: <Coins className="w-3.5 h-3.5" />,
    },
    {
      id: "cost_waste",
      label: "Cost & Waste",
      icon: <TrendingDown className="w-3.5 h-3.5" />,
    },
  ];

  const handleNavClick = (viewId: ViewMode) => {
    onViewChange(viewId);
    if (viewId === "monitoring") {
      setIsMonitoringOpen(true);
    }
    if (isMobileOpen && onCloseMobile && viewId !== "monitoring") {
      onCloseMobile();
    }
  };

  const handleSubTabClick = (tabId: MonitoringSubTab) => {
    onViewChange("monitoring");
    if (onSelectMonitoringTab) {
      onSelectMonitoringTab(tabId);
    }
    if (isMobileOpen && onCloseMobile) {
      onCloseMobile();
    }
  };

  return (
    <>
      {/* Mobile Backdrop */}
      {isMobileOpen && (
        <div
          onClick={onCloseMobile}
          className="fixed inset-0 z-40 bg-navy-950/40 backdrop-blur-xs sm:hidden"
        />
      )}

      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 bg-white border-r border-slate-200 flex flex-col justify-between transition-all duration-200 ${
          isMobileOpen ? "translate-x-0 w-64" : "-translate-x-full sm:translate-x-0"
        } ${isCollapsed ? "sm:w-16" : "sm:w-64"}`}
      >
        {/* Top Branding */}
        <div className="flex-1 overflow-y-auto">
          <div className="h-14 border-b border-slate-200 px-3 flex items-center justify-between sticky top-0 bg-white z-10">
            <div className="flex items-center gap-2.5 overflow-hidden">
              <div className="w-8 h-8 rounded-lg bg-brand-600 text-white flex items-center justify-center font-bold shadow-2xs shrink-0">
                <Layers className="w-4 h-4" />
              </div>
              {!isCollapsed && (
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-xs text-navy-900 tracking-tight truncate">
                      FinOps Platform
                    </span>
                    <span className="text-[10px] uppercase font-bold px-1.5 py-0.2 rounded bg-blue-50 text-brand-600 border border-blue-200">
                      POC
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-400 block truncate">
                    Infrastructure Intel
                  </span>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={onToggleCollapse}
              aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              className="p-1 rounded-md text-slate-400 hover:text-navy-900 hover:bg-slate-100 transition hidden sm:flex items-center justify-center"
            >
              {isCollapsed ? (
                <ChevronRight className="w-3.5 h-3.5" />
              ) : (
                <ChevronLeft className="w-3.5 h-3.5" />
              )}
            </button>
          </div>

          {/* Navigation Items */}
          <nav className="p-2 space-y-1">
            {/* Home */}
            <button
              type="button"
              onClick={() => handleNavClick("home")}
              title={isCollapsed ? "Home" : undefined}
              className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium transition ${
                currentView === "home"
                  ? "bg-brand-50 text-brand-700 font-semibold"
                  : "text-navy-700 hover:bg-slate-50 hover:text-navy-900"
              } ${isCollapsed ? "justify-center" : "justify-between"}`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <span className={currentView === "home" ? "text-brand-600" : "text-slate-500"}>
                  <Home className="w-4 h-4" />
                </span>
                {!isCollapsed && <span className="truncate">Home</span>}
              </div>
            </button>

            {/* Dashboard */}
            <button
              type="button"
              onClick={() => handleNavClick("dashboard")}
              title={isCollapsed ? "Dashboard" : undefined}
              className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium transition ${
                currentView === "dashboard"
                  ? "bg-brand-50 text-brand-700 font-semibold"
                  : "text-navy-700 hover:bg-slate-50 hover:text-navy-900"
              } ${isCollapsed ? "justify-center" : "justify-between"}`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <span className={currentView === "dashboard" ? "text-brand-600" : "text-slate-500"}>
                  <LayoutDashboard className="w-4 h-4" />
                </span>
                {!isCollapsed && <span className="truncate">Dashboard</span>}
              </div>
              {!isCollapsed && (
                <span
                  className={`text-[10px] font-semibold px-1.5 py-0.2 rounded ${
                    currentView === "dashboard"
                      ? "bg-brand-100 text-brand-800"
                      : "bg-slate-100 text-slate-500"
                  }`}
                >
                  Live
                </span>
              )}
            </button>

            {/* AI Architect (Preserved, conditionally rendered) */}
            {ENABLE_AI_ARCHITECT && (
              <button
                type="button"
                onClick={() => handleNavClick("architect")}
                title={isCollapsed ? "AI Architect" : undefined}
                className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium transition ${
                  currentView === "architect"
                    ? "bg-brand-50 text-brand-700 font-semibold"
                    : "text-navy-700 hover:bg-slate-50 hover:text-navy-900"
                } ${isCollapsed ? "justify-center" : "justify-between"}`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className={currentView === "architect" ? "text-brand-600" : "text-slate-500"}>
                    <Sparkles className="w-4 h-4" />
                  </span>
                  {!isCollapsed && <span className="truncate">AI Architect</span>}
                </div>
                {!isCollapsed && (
                  <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-100 text-slate-500">
                    5 Steps
                  </span>
                )}
              </button>
            )}

            {/* Subscriptions / Inventory */}
            <button
              type="button"
              onClick={() => handleNavClick("inventory")}
              title={isCollapsed ? "Subscriptions" : undefined}
              className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium transition ${
                currentView === "inventory"
                  ? "bg-brand-50 text-brand-700 font-semibold"
                  : "text-navy-700 hover:bg-slate-50 hover:text-navy-900"
              } ${isCollapsed ? "justify-center" : "justify-between"}`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <span className={currentView === "inventory" ? "text-brand-600" : "text-slate-500"}>
                  <FolderTree className="w-4 h-4" />
                </span>
                {!isCollapsed && <span className="truncate">Subscriptions</span>}
              </div>
            </button>

            {/* EXPANDABLE MONITORING GROUP */}
            <div className="pt-0.5">
              <button
                type="button"
                onClick={() => {
                  if (isCollapsed) {
                    onViewChange("monitoring");
                  } else {
                    if (currentView !== "monitoring") {
                      onViewChange("monitoring");
                      setIsMonitoringOpen(true);
                    } else {
                      setIsMonitoringOpen(!isMonitoringOpen);
                    }
                  }
                }}
                title={isCollapsed ? "Monitoring" : undefined}
                className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium transition ${
                  currentView === "monitoring"
                    ? "bg-brand-50/80 text-brand-700 font-semibold"
                    : "text-navy-700 hover:bg-slate-50 hover:text-navy-900"
                } ${isCollapsed ? "justify-center" : "justify-between"}`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className={currentView === "monitoring" ? "text-brand-600" : "text-slate-500"}>
                    <Activity className="w-4 h-4" />
                  </span>
                  {!isCollapsed && <span className="truncate">Monitoring</span>}
                </div>

                {!isCollapsed && (
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-100 text-slate-500">
                      8 Sections
                    </span>
                    <ChevronDown
                      className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-200 ${
                        isMonitoringOpen ? "rotate-180" : ""
                      }`}
                    />
                  </div>
                )}
              </button>

              {/* Sub-Items (Expanded under Monitoring) */}
              {!isCollapsed && isMonitoringOpen && (
                <div className="mt-1 ml-3 pl-2.5 border-l border-slate-200 space-y-0.5">
                  {monitoringSubNav.map((sub) => {
                    const isSubActive =
                      currentView === "monitoring" && currentMonitoringTab === sub.id;
                    return (
                      <button
                        key={sub.id}
                        type="button"
                        onClick={() => handleSubTabClick(sub.id)}
                        className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-[11px] font-medium transition ${
                          isSubActive
                            ? "bg-brand-50 text-brand-700 font-semibold"
                            : "text-slate-600 hover:bg-slate-50 hover:text-navy-900"
                        }`}
                      >
                        <span className={isSubActive ? "text-brand-600" : "text-slate-400"}>
                          {sub.icon}
                        </span>
                        <span className="truncate">{sub.label}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

          </nav>
        </div>

        {/* Bottom Footer Controls */}
        <div className="p-2 border-t border-slate-200 space-y-1 bg-white">
          {/* Settings button */}
          <button
            type="button"
            onClick={onOpenSettings}
            title={isCollapsed ? "Platform Governance & Settings" : undefined}
            className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium text-navy-700 hover:bg-slate-50 hover:text-navy-900 transition ${
              isCollapsed ? "justify-center" : ""
            }`}
          >
            <Settings className="w-4 h-4 text-slate-500" />
            {!isCollapsed && <span>Governance &amp; Settings</span>}
          </button>

          {/* Read-Only Status Indicator */}
          {!isCollapsed && (
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-[11px] text-navy-600 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-accent-emerald shrink-0" />
              <div className="min-w-0">
                <span className="font-semibold text-navy-900 block truncate">Zero-Execution</span>
                <span className="text-[10px] text-slate-500 truncate block">100% Read-Only</span>
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  );
};
