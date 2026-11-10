"use client";

import React, { useState } from "react";
import Image from "next/image";
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
  SlidersHorizontal,
  Server,
  Database,
  Cpu,
  Workflow,
  History,
  Clock,
  GitBranch,
  Cloud,
} from "lucide-react";

import { ENABLE_AI_ARCHITECT } from "@/config/features";
import { MonitoringSubTab } from "./SectionCentralizedMonitoring";
import { CloudScope, DatabricksModuleId } from "@/types/navigation";
import { FinOpsModule } from "@/types";
import { getDatabricksModules } from "@/lib/navigationRegistry";

export type ViewMode =
  | "home"
  | "dashboard"
  | "architect"
  | "inventory"
  | "monitoring"
  | "compare"
  | "configuration"
  | "databricks"
  | "finops"
  | "connections";

interface SidebarProps {
  currentView: ViewMode;
  onViewChange: (view: ViewMode) => void;
  currentMonitoringTab?: MonitoringSubTab;
  onSelectMonitoringTab?: (tab: MonitoringSubTab) => void;
  activeScope?: CloudScope | null;
  currentDatabricksModule?: DatabricksModuleId;
  onSelectDatabricksModule?: (mod: DatabricksModuleId) => void;
  currentFinOpsModule?: FinOpsModule;
  onSelectFinOpsModule?: (mod: FinOpsModule) => void;
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
  activeScope,
  currentDatabricksModule = "overview",
  onSelectDatabricksModule,
  onOpenSettings,
  isCollapsed,
  onToggleCollapse,
  isMobileOpen = false,
  onCloseMobile,
}) => {
  const [isMonitoringOpen, setIsMonitoringOpen] = useState<boolean>(true);
  const [isDatabricksOpen, setIsDatabricksOpen] = useState<boolean>(true);

  const databricksModules = getDatabricksModules();

  const monitoringSubNav: { id: MonitoringSubTab; label: string; icon: React.ReactNode }[] = [
    {
      id: "overview",
      label: "Overview & Trends",
      icon: <BarChart3 className="w-3.5 h-3.5" />,
    },
    {
      id: "resources",
      label: "Resources",
      icon: <Server className="w-3.5 h-3.5" />,
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
    if (viewId === "databricks" || viewId === "finops") {
      setIsDatabricksOpen(true);
    }
    if (isMobileOpen && onCloseMobile && viewId !== "monitoring" && viewId !== "databricks" && viewId !== "finops") {
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

  const handleDatabricksModuleClick = (moduleId: DatabricksModuleId) => {
    onViewChange("databricks");
    if (onSelectDatabricksModule) {
      onSelectDatabricksModule(moduleId);
    }
    if (isMobileOpen && onCloseMobile) {
      onCloseMobile();
    }
  };

  const getDatabricksIcon = (iconName: string) => {
    switch (iconName) {
      case "Cpu":
        return <Cpu className="w-3.5 h-3.5" />;
      case "Database":
        return <Database className="w-3.5 h-3.5" />;
      case "Workflow":
        return <Workflow className="w-3.5 h-3.5" />;
      case "GitBranch":
        return <GitBranch className="w-3.5 h-3.5" />;
      case "Layers":
        return <Layers className="w-3.5 h-3.5" />;
      case "Sparkles":
        return <Sparkles className="w-3.5 h-3.5" />;
      case "FolderTree":
        return <FolderTree className="w-3.5 h-3.5" />;
      case "Server":
        return <Server className="w-3.5 h-3.5" />;
      case "Terminal":
        return <Terminal className="w-3.5 h-3.5" />;
      case "History":
        return <History className="w-3.5 h-3.5" />;
      case "Coins":
        return <Coins className="w-3.5 h-3.5" />;
      case "ShieldCheck":
        return <ShieldCheck className="w-3.5 h-3.5" />;
      case "TrendingDown":
        return <TrendingDown className="w-3.5 h-3.5" />;
      case "Clock":
        return <Clock className="w-3.5 h-3.5" />;
      default:
        return <LayoutDashboard className="w-3.5 h-3.5" />;
    }
  };

  const isDatabricksActive =
    currentView === "databricks" ||
    currentView === "finops" ||
    activeScope?.provider === "databricks";

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
        className={`fixed top-0 bottom-0 left-0 z-50 bg-white border-r border-slate-200 flex flex-col transition-all duration-200 ${
          isMobileOpen ? "translate-x-0 w-64" : "-translate-x-full sm:translate-x-0"
        } ${isCollapsed ? "sm:w-16" : "sm:w-64"}`}
      >
        {/* 1. Header / Branding (Fixed at top, non-scrolling) */}
        <div className="h-14 shrink-0 border-b border-slate-200 px-3 flex items-center justify-between bg-white z-10">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="w-8 h-8 relative flex items-center justify-center shrink-0">
              <Image
                src="/bizmetric-logo.png"
                alt="Bizmetric Logo"
                width={32}
                height={32}
                className="w-full h-full object-contain"
                priority
              />
            </div>
            {!isCollapsed && (
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-bold text-xs text-navy-900 tracking-tight truncate">
                    FinOps Platform
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

        {/* 2. Navigation Scroll Container (THE ONLY SCROLLABLE CONTAINER) */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden min-h-0">
          {/* Active Scope Indicator Pill */}
          {!isCollapsed && activeScope && (
            <div className="px-3 pt-2 pb-1">
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-200 text-[11px] flex items-center justify-between">
                <div className="min-w-0">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block truncate">
                    {activeScope.selected_child_resource
                      ? `Child: ${activeScope.selected_child_resource.resource_type}`
                      : `Scope: ${activeScope.scope_type.replace("_", " ")}`}
                  </span>
                  <span className="font-semibold text-navy-900 truncate block">
                    {activeScope.selected_child_resource
                      ? activeScope.selected_child_resource.resource_name
                      : activeScope.display_name}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => handleNavClick("configuration")}
                  className="text-brand-600 hover:underline text-[10px] font-semibold shrink-0"
                >
                  Change
                </button>
              </div>
            </div>
          )}

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
            </button>

            {/* AI Architect */}
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
              </button>
            )}

            {/* Configuration */}
            <button
              type="button"
              onClick={() => handleNavClick("configuration")}
              title={isCollapsed ? "Configuration" : undefined}
              className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium transition ${
                currentView === "configuration"
                  ? "bg-brand-50 text-brand-700 font-semibold"
                  : "text-navy-700 hover:bg-slate-50 hover:text-navy-900"
              } ${isCollapsed ? "justify-center" : "justify-between"}`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <span className={currentView === "configuration" ? "text-brand-600" : "text-slate-500"}>
                  <SlidersHorizontal className="w-4 h-4" />
                </span>
                {!isCollapsed && <span className="truncate">Configuration</span>}
              </div>
            </button>

            {/* Subscriptions */}
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
                  <ChevronDown
                    className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-200 ${
                      isMonitoringOpen ? "rotate-180" : ""
                    }`}
                  />
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

            {/* DYNAMIC CONTEXTUAL SECTION: DATABRICKS WORKSPACE */}
            <div className="pt-2">
              <div className="px-2 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                {!isCollapsed && <span>Databricks Workspace</span>}
                {!isCollapsed && (
                  <span className="text-[9px] font-bold text-orange-600 font-mono">
                    642006393507276
                  </span>
                )}
              </div>

              <button
                type="button"
                onClick={() => {
                  if (isCollapsed) {
                    onViewChange("databricks");
                  } else {
                    if (currentView !== "databricks" && currentView !== "finops") {
                      onViewChange("databricks");
                      setIsDatabricksOpen(true);
                    } else {
                      setIsDatabricksOpen(!isDatabricksOpen);
                    }
                  }
                }}
                title={isCollapsed ? "Databricks Workspace" : undefined}
                className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium transition ${
                  isDatabricksActive
                    ? "bg-orange-50/80 text-orange-950 font-semibold border border-orange-200"
                    : "text-navy-700 hover:bg-slate-50 hover:text-navy-900"
                } ${isCollapsed ? "justify-center" : "justify-between"}`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className={isDatabricksActive ? "text-orange-600" : "text-slate-500"}>
                    <Server className="w-4 h-4" />
                  </span>
                  {!isCollapsed && <span className="truncate">Databricks Workspace</span>}
                </div>

                {!isCollapsed && (
                  <ChevronDown
                    className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-200 ${
                      isDatabricksOpen ? "rotate-180" : ""
                    }`}
                  />
                )}
              </button>

              {/* Sub-Nav: Single Continuous Flow (NO nested scrollbar, NO max-h) */}
              {!isCollapsed && isDatabricksOpen && (
                <div className="mt-1 ml-3 pl-2.5 border-l border-orange-200 space-y-0.5">
                  {/* 1. FinOps Command Center · Azure Databricks (PRIMARY FIRST ITEM) */}
                  <button
                    type="button"
                    onClick={() => handleNavClick("finops")}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-[11px] font-medium transition ${
                      currentView === "finops"
                        ? "bg-brand-50 text-brand-700 font-bold border border-brand-200/60"
                        : "text-brand-700 hover:bg-brand-50/60 hover:text-brand-900 font-semibold"
                    }`}
                    title="FinOps Command Center · Azure Databricks"
                  >
                    <span className={currentView === "finops" ? "text-brand-600" : "text-brand-600/80"}>
                      <BarChart3 className="w-3.5 h-3.5" />
                    </span>
                    <span className="truncate">FinOps Command Center · Azure Databricks</span>
                  </button>

                  {/* 2. Overview through 14. Discovery History (All badges removed) */}
                  {databricksModules.map((mod) => {
                    const isModActive =
                      currentView === "databricks" && currentDatabricksModule === mod.id;
                    return (
                      <button
                        key={mod.id}
                        type="button"
                        onClick={() => handleDatabricksModuleClick(mod.id)}
                        className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-[11px] font-medium transition ${
                          isModActive
                            ? "bg-orange-100/70 text-orange-950 font-bold"
                            : "text-slate-600 hover:bg-slate-50 hover:text-navy-900"
                        }`}
                        title={mod.title}
                      >
                        <span className={isModActive ? "text-orange-600" : "text-slate-400"}>
                          {getDatabricksIcon(mod.iconName)}
                        </span>
                        <span className="truncate">{mod.shortTitle}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </nav>
        </div>

        {/* 3. Bottom Footer Controls (Fixed at bottom, non-scrolling) */}
        <div className="shrink-0 p-2 border-t border-slate-200 space-y-1 bg-white">
          {/* Switch Cloud Connection button */}
          <button
            type="button"
            onClick={() => onViewChange("connections")}
            title={isCollapsed ? "Switch Cloud Scope" : undefined}
            className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-semibold text-emerald-800 bg-emerald-50/70 hover:bg-emerald-100/80 border border-emerald-200/80 transition ${
              isCollapsed ? "justify-center" : ""
            }`}
          >
            <Cloud className="w-4 h-4 text-emerald-600 shrink-0" />
            {!isCollapsed && <span className="truncate">Cloud Accounts &amp; Switch</span>}
          </button>

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
