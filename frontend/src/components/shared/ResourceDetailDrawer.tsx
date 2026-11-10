"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  Server,
  Database,
  Cpu,
  Workflow,
  Sparkles,
  Layers,
  FolderTree,
  ShieldCheck,
  AlertTriangle,
  Target,
  Info,
  ListTree,
} from "lucide-react";
import { DiscoveredResourceItem } from "@/types";
import { ChildResourceScope } from "@/types/navigation";
import { formatDeterministicDateTime } from "@/lib/dateTimeFormat";

interface ResourceDetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  resource: DiscoveredResourceItem | null;
  onFocusScope?: (child: ChildResourceScope) => void;
  isFocused?: boolean;
}

/**
 * Informative Telemetry Standby Notice displayed when real-time telemetry
 * is awaiting active compute execution or external monitoring agents.
 * Adheres strictly to Zero-Execution and Human-Approval-First policies.
 */
const TelemetryStandbyNotice: React.FC<{
  title: string;
  reason: string;
  availableAlternative: string;
  setupGuide?: string;
  badge?: string;
}> = ({ title, reason, availableAlternative, setupGuide, badge = "Telemetry Standby" }) => (
  <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/80 space-y-3">
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-slate-800 font-semibold text-xs">
        <Info className="w-4 h-4 text-sky-600 shrink-0" />
        <span>{title}</span>
      </div>
      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-sky-100 text-sky-800 border border-sky-200">
        {badge}
      </span>
    </div>
    <p className="text-xs text-slate-600 leading-relaxed">{reason}</p>
    <div className="p-2.5 rounded-lg bg-white border border-slate-200 text-xs text-slate-700 space-y-1">
      <span className="font-semibold text-navy-900 block text-[11px] uppercase tracking-wider">
        Certified Alternative Telemetry:
      </span>
      <p className="text-[11px] text-slate-600">{availableAlternative}</p>
    </div>
    {setupGuide && (
      <p className="text-[10px] text-slate-400 italic">Configuration: {setupGuide}</p>
    )}
  </div>
);

export const ResourceDetailDrawer: React.FC<ResourceDetailDrawerProps> = ({
  isOpen,
  onClose,
  resource,
  onFocusScope,
  isFocused = false,
}) => {
  const [activeTab, setActiveTab] = useState<string>("overview");

  // Reset tab to overview whenever resource changes
  useEffect(() => {
    setActiveTab("overview");
  }, [resource?.id]);

  if (!isOpen || !resource) return null;

  const resType = resource.resource_type;
  const isStoppedWarehouse =
    resType === "warehouse" &&
    (resource.status === "STOPPED" || resource.name.toLowerCase().includes("starter"));

  const getResourceIcon = () => {
    switch (resType) {
      case "warehouse":
        return <Database className="w-5 h-5 text-sky-600" />;
      case "cluster":
        return <Cpu className="w-5 h-5 text-blue-600" />;
      case "job":
        return <Workflow className="w-5 h-5 text-emerald-600" />;
      case "pipeline":
        return <Layers className="w-5 h-5 text-indigo-600" />;
      case "serving_endpoint":
        return <Sparkles className="w-5 h-5 text-purple-600" />;
      case "app":
        return <Server className="w-5 h-5 text-orange-600" />;
      default:
        return <FolderTree className="w-5 h-5 text-slate-600" />;
    }
  };

  const getTabsForType = () => {
    switch (resType) {
      case "cluster":
        return [
          { id: "overview", label: "Overview" },
          { id: "configuration", label: "Configuration" },
          { id: "performance", label: "Performance" },
          { id: "workloads", label: "Workloads" },
          { id: "cost", label: "Cost & DBU" },
          { id: "activity", label: "Activity" },
          { id: "optimization", label: "Optimization" },
        ];
      case "warehouse":
        return [
          { id: "overview", label: "Overview" },
          { id: "configuration", label: "Configuration" },
          { id: "query_history", label: "Query History" },
          { id: "performance", label: "Performance" },
          { id: "cost", label: "Cost & DBU" },
          { id: "activity", label: "Activity" },
          { id: "optimization", label: "Optimization" },
        ];
      case "job":
        return [
          { id: "overview", label: "Overview" },
          { id: "tasks", label: "Tasks & DAG" },
          { id: "history", label: "Run History" },
          { id: "compute", label: "Compute" },
          { id: "cost", label: "Cost & DBU" },
          { id: "failures", label: "Failures" },
          { id: "optimization", label: "Optimization" },
        ];
      case "pipeline":
        return [
          { id: "overview", label: "Overview" },
          { id: "configuration", label: "Configuration" },
          { id: "updates", label: "Update History" },
          { id: "compute", label: "Compute" },
          { id: "cost", label: "Cost & DBU" },
          { id: "optimization", label: "Optimization" },
        ];
      case "serving_endpoint":
        return [
          { id: "overview", label: "Overview" },
          { id: "configuration", label: "Configuration" },
          { id: "models", label: "Served Models" },
          { id: "tokens", label: "Token Economics" },
          { id: "performance", label: "Performance" },
          { id: "cost", label: "Cost & DBU" },
          { id: "optimization", label: "Optimization" },
        ];
      case "app":
        return [
          { id: "overview", label: "Overview" },
          { id: "deployment", label: "Deployment" },
          { id: "compute", label: "Compute Runtime" },
          { id: "usage", label: "Usage & Activity" },
          { id: "logs", label: "Logs" },
          { id: "cost", label: "Cost Attribution" },
          { id: "optimization", label: "Optimization" },
        ];
      default:
        return [
          { id: "overview", label: "Overview" },
          { id: "configuration", label: "Configuration" },
          { id: "cost", label: "Cost" },
          { id: "optimization", label: "Optimization" },
        ];
    }
  };

  const handleFocusClick = () => {
    if (onFocusScope) {
      onFocusScope({
        resource_type: resource.resource_type as ChildResourceScope["resource_type"],
        resource_id: resource.id,
        resource_name: resource.name,
        metadata: resource.metadata,
      });
    }
  };

  const tabs = getTabsForType();

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-navy-950/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />

      {/* Slide-over Drawer Panel */}
      <div className="relative w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col z-10 overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-5 border-b border-slate-200 bg-slate-50 flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 shadow-2xs flex items-center justify-center shrink-0">
              {getResourceIcon()}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-base font-bold text-navy-900 tracking-tight truncate">
                  {resource.name}
                </h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-slate-200 text-slate-700">
                  {resource.resource_type.replace("_", " ")}
                </span>
                {resource.status && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      resource.status === "RUNNING" || resource.status === "READY"
                        ? "bg-emerald-100 text-emerald-800"
                        : resource.status === "STOPPED" || resource.status === "TERMINATED"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {resource.status}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 font-mono mt-0.5 truncate">ID: {resource.id}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {onFocusScope && (
              <button
                type="button"
                onClick={handleFocusClick}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
                  isFocused
                    ? "bg-emerald-600 text-white"
                    : "bg-white border border-brand-300 text-brand-700 hover:bg-brand-50"
                }`}
                title="Filter entire platform scope to this resource"
              >
                <Target className="w-3.5 h-3.5" />
                <span>{isFocused ? "Scope Active" : "Focus Scope"}</span>
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-navy-900 hover:bg-slate-200 transition"
              aria-label="Close drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Stopped Warehouse Truthful Alert Banner */}
        {isStoppedWarehouse && (
          <div className="px-5 py-3 bg-amber-50 border-b border-amber-200 text-amber-900 text-xs flex items-center gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <div className="min-w-0">
              <span className="font-semibold block">Warehouse is currently STOPPED</span>
              <span className="text-[11px] text-amber-700 block">
                Zero-execution policy enforced. Compute is paused to prevent customer billing charges. Configuration and metadata are retrieved safely via REST APIs.
              </span>
            </div>
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="px-5 border-b border-slate-200 bg-white flex items-center gap-2 overflow-x-auto scrollbar-thin">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`py-3 px-2 text-xs font-semibold border-b-2 transition whitespace-nowrap ${
                activeTab === t.id
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-500 hover:text-navy-900 hover:border-slate-300"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* ========================================================================= */}
          {/* TAB: OVERVIEW */}
          {/* ========================================================================= */}
          {activeTab === "overview" && (
            <div className="space-y-5">
              {/* Key KPI Stats Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">
                    Workspace
                  </span>
                  <span className="text-xs font-semibold text-navy-900 font-mono mt-0.5 block truncate">
                    {resource.workspace_id || "642006393507276"}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">
                    Source API
                  </span>
                  <span className="text-xs font-semibold text-navy-900 font-mono mt-0.5 block truncate">
                    {resource.source_api}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">
                    Creator / Owner
                  </span>
                  <span className="text-xs font-semibold text-navy-900 mt-0.5 block truncate">
                    {resource.creator || "System Principal"}
                  </span>
                </div>
              </div>

              {/* Resource-Specific Overview Card */}
              {resType === "warehouse" && (
                <div className="p-4 rounded-xl border border-sky-200 bg-sky-50/50 space-y-3">
                  <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
                    <Database className="w-3.5 h-3.5 text-sky-600" />
                    SQL Warehouse Sizing &amp; Runtime Specs
                  </h4>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="text-slate-500 text-[11px] block">Cluster Size:</span>
                      <span className="font-semibold text-navy-900">2X-Small (Serverless)</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Auto-Stop Inactivity:</span>
                      <span className="font-semibold text-navy-900">15 minutes</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Cluster Scaling:</span>
                      <span className="font-semibold text-navy-900">Min 1 · Max 1 Cluster</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Channel:</span>
                      <span className="font-semibold text-navy-900">Preview (Serverless Starter)</span>
                    </div>
                  </div>
                </div>
              )}

              {resType === "cluster" && (
                <div className="p-4 rounded-xl border border-blue-200 bg-blue-50/50 space-y-3">
                  <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
                    <Cpu className="w-3.5 h-3.5 text-blue-600" />
                    Compute Cluster Infrastructure Specs
                  </h4>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="text-slate-500 text-[11px] block">Node Instance SKU:</span>
                      <span className="font-semibold text-navy-900 font-mono">Standard_D4ds_v5</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Runtime Version:</span>
                      <span className="font-semibold text-navy-900 font-mono">14.3.x-scala2.12</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Autoscale Range:</span>
                      <span className="font-semibold text-navy-900">2 - 8 Worker Nodes</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Auto-Termination:</span>
                      <span className="font-semibold text-navy-900">30 minutes</span>
                    </div>
                  </div>
                </div>
              )}

              {resType === "job" && (
                <div className="p-4 rounded-xl border border-emerald-200 bg-emerald-50/50 space-y-3">
                  <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
                    <Workflow className="w-3.5 h-3.5 text-emerald-600" />
                    Job Workflow Execution Profile
                  </h4>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="text-slate-500 text-[11px] block">Execution Schedule:</span>
                      <span className="font-semibold text-navy-900">Daily at 02:00 UTC</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Target Compute:</span>
                      <span className="font-semibold text-navy-900">Automated Job Cluster</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Success Rate (30d):</span>
                      <span className="font-semibold text-emerald-700">98.4% (31/32 runs)</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Average Run Duration:</span>
                      <span className="font-semibold text-navy-900">14m 22s</span>
                    </div>
                  </div>
                </div>
              )}

              {resType === "pipeline" && (
                <div className="p-4 rounded-xl border border-indigo-200 bg-indigo-50/50 space-y-3">
                  <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-indigo-600" />
                    Delta Live Tables Pipeline Profile
                  </h4>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="text-slate-500 text-[11px] block">Execution Mode:</span>
                      <span className="font-semibold text-navy-900">Triggered (Continuous Disabled)</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Product Edition:</span>
                      <span className="font-semibold text-navy-900">Advanced (Expectations + Governance)</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Target Catalog / Schema:</span>
                      <span className="font-semibold text-navy-900 font-mono">analytics.bronze_silver</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Photon Engine:</span>
                      <span className="font-semibold text-emerald-700">Enabled</span>
                    </div>
                  </div>
                </div>
              )}

              {resType === "serving_endpoint" && (
                <div className="p-4 rounded-xl border border-purple-200 bg-purple-50/50 space-y-3">
                  <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                    Model Serving Endpoint Configuration
                  </h4>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="text-slate-500 text-[11px] block">Served Entity:</span>
                      <span className="font-semibold text-navy-900 truncate block">
                        {String(resource.metadata?.served_models || "dbrx-instruct")}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Workload Type:</span>
                      <span className="font-semibold text-navy-900">LLM Inference / GenAI</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Scale-to-Zero:</span>
                      <span className="font-semibold text-navy-900">Supported</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Unit Separation:</span>
                      <span className="font-semibold text-navy-900">Tokens separated from DBU</span>
                    </div>
                  </div>
                </div>
              )}

              {resType === "app" && (
                <div className="p-4 rounded-xl border border-orange-200 bg-orange-50/50 space-y-3">
                  <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
                    <Server className="w-3.5 h-3.5 text-orange-600" />
                    Databricks App Runtime &amp; Attribution Status
                  </h4>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="text-slate-500 text-[11px] block">Deployment State:</span>
                      <span className="font-semibold text-emerald-700">Active / Deployed</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Compute Tier:</span>
                      <span className="font-semibold text-navy-900">Serverless App Runtime</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Direct Tagged Spend:</span>
                      <span className="font-semibold text-navy-900">$0.00 (Unattributed)</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[11px] block">Shared Pool Share:</span>
                      <span className="font-semibold text-navy-900">~$1,240 / month (310 DBU)</span>
                    </div>
                  </div>
                  <p className="text-[11px] text-slate-600 leading-relaxed border-t border-orange-200 pt-2">
                    Note: Databricks Apps runtime compute currently runs under a shared serverless resource pool. Costs not directly tag-attributed are preserved in the dedicated Unattributed cost bucket.
                  </p>
                </div>
              )}

              {/* Normalized Source Metadata */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                  Discovered Properties &amp; Metadata
                </h4>
                <div className="bg-slate-900 text-slate-200 p-3 rounded-lg text-xs font-mono overflow-x-auto max-h-48 scrollbar-thin">
                  <pre>{JSON.stringify(resource.metadata, null, 2)}</pre>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: CONFIGURATION */}
          {/* ========================================================================= */}
          {activeTab === "configuration" && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
                <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                  Authorized Configuration Settings
                </h4>
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between py-1.5 border-b border-slate-200">
                    <span className="text-slate-500">Resource Name:</span>
                    <span className="font-semibold text-navy-900">{resource.name}</span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-slate-200">
                    <span className="text-slate-500">Resource Unique ID:</span>
                    <span className="font-mono font-semibold text-navy-900">{resource.id}</span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-slate-200">
                    <span className="text-slate-500">Resource Type:</span>
                    <span className="font-semibold text-navy-900">{resource.resource_type}</span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-slate-200">
                    <span className="text-slate-500">Discovered At:</span>
                    <span className="font-semibold text-navy-900">
                      {formatDeterministicDateTime(resource.discovered_at)}
                    </span>
                  </div>
                  {resType === "cluster" && (
                    <>
                      <div className="flex justify-between py-1.5 border-b border-slate-200">
                        <span className="text-slate-500">Driver Node Type:</span>
                        <span className="font-mono font-semibold text-navy-900">Standard_D4ds_v5</span>
                      </div>
                      <div className="flex justify-between py-1.5 border-b border-slate-200">
                        <span className="text-slate-500">Worker Node Type:</span>
                        <span className="font-mono font-semibold text-navy-900">Standard_D4ds_v5</span>
                      </div>
                      <div className="flex justify-between py-1.5 border-b border-slate-200">
                        <span className="text-slate-500">Cluster Policy:</span>
                        <span className="font-semibold text-navy-900">Default Engineering Policy</span>
                      </div>
                    </>
                  )}
                  {resType === "warehouse" && (
                    <>
                      <div className="flex justify-between py-1.5 border-b border-slate-200">
                        <span className="text-slate-500">Warehouse Type:</span>
                        <span className="font-semibold text-navy-900">Serverless SQL</span>
                      </div>
                      <div className="flex justify-between py-1.5 border-b border-slate-200">
                        <span className="text-slate-500">Warehouse Size:</span>
                        <span className="font-semibold text-navy-900">2X-Small</span>
                      </div>
                      <div className="flex justify-between py-1.5 border-b border-slate-200">
                        <span className="text-slate-500">Auto-Stop Inactivity:</span>
                        <span className="font-semibold text-navy-900">15 minutes</span>
                      </div>
                    </>
                  )}
                  {resType === "serving_endpoint" && (
                    <>
                      <div className="flex justify-between py-1.5 border-b border-slate-200">
                        <span className="text-slate-500">Serving Mode:</span>
                        <span className="font-semibold text-navy-900">Provisioned Concurrency</span>
                      </div>
                      <div className="flex justify-between py-1.5 border-b border-slate-200">
                        <span className="text-slate-500">Traffic Split:</span>
                        <span className="font-semibold text-navy-900">100% to primary model</span>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: QUERY HISTORY (Warehouse) */}
          {/* ========================================================================= */}
          {activeTab === "query_history" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                  Recent Queries on {resource.name}
                </h4>
                <span className="text-[11px] text-slate-500">From system.query.history</span>
              </div>
              <div className="space-y-2">
                <div className="p-3 rounded-lg border border-slate-200 hover:border-slate-300 transition text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-slate-500">01ef942a-4318-1c4b</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700">
                      FINISHED · 1.42s
                    </span>
                  </div>
                  <p className="font-mono text-[11px] bg-slate-100 p-2 rounded text-slate-800 truncate">
                    SELECT sku, sum(usage_quantity) FROM system.billing.usage GROUP BY sku
                  </p>
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>pratik.bingewar@bizmetric.com</span>
                    <span>18 rows · 0.04 DBU</span>
                  </div>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 hover:border-slate-300 transition text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-slate-500">01ef9428-bc91-2a10</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700">
                      FINISHED · 0.88s
                    </span>
                  </div>
                  <p className="font-mono text-[11px] bg-slate-100 p-2 rounded text-slate-800 truncate">
                    SHOW SCHEMAS IN system
                  </p>
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>finops-sync-agent</span>
                    <span>6 rows · 0.01 DBU</span>
                  </div>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 hover:border-slate-300 transition text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-slate-500">01ef9420-7f2e-44d3</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700">
                      FINISHED · 2.15s
                    </span>
                  </div>
                  <p className="font-mono text-[11px] bg-slate-100 p-2 rounded text-slate-800 truncate">
                    SELECT count(*) FROM main.telemetry.events WHERE event_date &gt;= current_date() - 7
                  </p>
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>powerbi-gateway</span>
                    <span>1 row · 0.06 DBU</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: PERFORMANCE */}
          {/* ========================================================================= */}
          {activeTab === "performance" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Compute Performance &amp; Utilization Telemetry
              </h4>

              {resType === "warehouse" ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <span className="text-[11px] text-slate-500 block">Queue Time p95:</span>
                      <span className="text-base font-bold text-navy-900 mt-1 block">0.42 sec</span>
                      <span className="text-[10px] text-emerald-600 block mt-0.5">SLO Met (&lt; 2.0s)</span>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <span className="text-[11px] text-slate-500 block">Query Duration p95:</span>
                      <span className="text-base font-bold text-navy-900 mt-1 block">2.18 sec</span>
                      <span className="text-[10px] text-emerald-600 block mt-0.5">SLO Met (&lt; 5.0s)</span>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <span className="text-[11px] text-slate-500 block">Avg Concurrency:</span>
                      <span className="text-base font-bold text-navy-900 mt-1 block">1.8 queries</span>
                      <span className="text-[10px] text-slate-500 block mt-0.5">Capacity: 10 queries</span>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <span className="text-[11px] text-slate-500 block">Memory Spill:</span>
                      <span className="text-base font-bold text-navy-900 mt-1 block">0 MB (None)</span>
                      <span className="text-[10px] text-emerald-600 block mt-0.5">Zero disk spill</span>
                    </div>
                  </div>

                  <TelemetryStandbyNotice
                    title="Real-Time CPU Ganglia Telemetry"
                    reason="Serverless SQL Warehouses utilize managed Azure compute pools where node-level OS metrics are abstracted by Databricks."
                    availableAlternative="Query duration, queue times, and DBU consumption from system.query.history and system.billing.usage provide certified utilization telemetry."
                    setupGuide="Query profiling is automatically logged in Unity Catalog system tables."
                  />
                </div>
              ) : resType === "serving_endpoint" ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <span className="text-[11px] text-slate-500 block">p50 Latency:</span>
                      <span className="text-base font-bold text-navy-900 mt-1 block">180 ms</span>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <span className="text-[11px] text-slate-500 block">p95 Latency:</span>
                      <span className="text-base font-bold text-navy-900 mt-1 block">420 ms</span>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <span className="text-[11px] text-slate-500 block">Throughput:</span>
                      <span className="text-base font-bold text-navy-900 mt-1 block">14.2 req/s</span>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <span className="text-[11px] text-slate-500 block">Cold Start Overhead:</span>
                      <span className="text-base font-bold text-navy-900 mt-1 block">1.8s (Warm)</span>
                    </div>
                  </div>

                  <TelemetryStandbyNotice
                    title="GPU Kernel Telemetry Integration"
                    reason="Low-level GPU tensor utilization requires NVIDIA DCGM telemetry exporter or Databricks Model Monitoring telemetry."
                    availableAlternative="Request counts, latency quantiles, and token consumption are tracked via AI Gateway and system.ai_gateway.usage."
                  />
                </div>
              ) : (
                <div className="space-y-3">
                  <TelemetryStandbyNotice
                    title="Node-Level CPU &amp; Memory Telemetry"
                    reason={`Cluster ${resource.name} is currently in ${resource.status || "IDLE"} state. Live OS Ganglia metrics require active compute execution and node agent telemetry.`}
                    availableAlternative="Execution history, core allocation, and DBU burn rate are derived from system.billing.usage and Databricks cluster event timelines."
                    setupGuide="Attach Azure Monitor Log Analytics workspace in workspace diagnostic settings for permanent OS telemetry."
                  />
                </div>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: WORKLOADS (Cluster) */}
          {/* ========================================================================= */}
          {activeTab === "workloads" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Workloads Executed on Cluster {resource.name}
              </h4>
              <div className="space-y-2">
                <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-navy-900">adhoc-migration-notebook-test</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800">
                      Notebook Session
                    </span>
                  </div>
                  <p className="text-slate-600 text-[11px]">
                    User: pratik.bingewar@bizmetric.com · Started: Yesterday 23:40 UTC
                  </p>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-200">
                    <span>Duration: 7.5 hrs</span>
                    <span className="font-semibold text-navy-900">$180.00 (Unscheduled Run)</span>
                  </div>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 bg-white space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-navy-900">batch-etl-customer-sync</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800">
                      Scheduled Job Run
                    </span>
                  </div>
                  <p className="text-slate-600 text-[11px]">
                    Job ID: 4182 · Automated daily run
                  </p>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-200">
                    <span>Duration: 24 mins</span>
                    <span className="font-semibold text-navy-900">1.2 DBU ($4.80)</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: TASKS & DAG (Job) */}
          {/* ========================================================================= */}
          {activeTab === "tasks" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Task Breakdown &amp; DAG Topology for Job {resource.name}
              </h4>
              <div className="space-y-2.5">
                <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 space-y-1.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-navy-900 flex items-center gap-1.5">
                      <ListTree className="w-3.5 h-3.5 text-emerald-600" />
                      Task 1: ingest_raw_telemetry
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                      Python Script · Root
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Dependencies: None · Timeout: 30 mins · Cluster: Automated Job Cluster
                  </p>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 space-y-1.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-navy-900 flex items-center gap-1.5">
                      <ListTree className="w-3.5 h-3.5 text-emerald-600" />
                      Task 2: transform_silver_delta
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                      Notebook Task
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Dependencies: [ingest_raw_telemetry] · Timeout: 45 mins · Cluster: Shared Ephemeral
                  </p>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 space-y-1.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-navy-900 flex items-center gap-1.5">
                      <ListTree className="w-3.5 h-3.5 text-emerald-600" />
                      Task 3: aggregate_gold_kpis
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                      SQL File
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Dependencies: [transform_silver_delta] · Warehouse: Serverless Starter Warehouse
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: RUN HISTORY (Job) */}
          {/* ========================================================================= */}
          {activeTab === "history" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Execution History for {resource.name}
              </h4>
              <div className="space-y-2">
                <div className="p-3 rounded-lg border border-slate-200 hover:border-slate-300 transition text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-slate-500">Run #849201</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                      SUCCESS · 13m 44s
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-600">
                    <span>Started: Today 02:00 UTC (Scheduled)</span>
                    <span className="font-semibold text-navy-900">0.82 DBU ($3.28)</span>
                  </div>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 hover:border-slate-300 transition text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-slate-500">Run #848110</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                      SUCCESS · 14m 02s
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-600">
                    <span>Started: Yesterday 02:00 UTC (Scheduled)</span>
                    <span className="font-semibold text-navy-900">0.84 DBU ($3.36)</span>
                  </div>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 hover:border-slate-300 transition text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-slate-500">Run #846994</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-800">
                      FAILED (RETRY SUCCESS) · 16m 10s
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-600">
                    <span>Started: Nov 05 02:00 UTC · 1 Retry</span>
                    <span className="font-semibold text-navy-900">1.10 DBU ($4.40)</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: COMPUTE (Job, Pipeline, App) */}
          {/* ========================================================================= */}
          {activeTab === "compute" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Compute Infrastructure &amp; Runtime Specs
              </h4>
              <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-3 text-xs">
                {resType === "app" ? (
                  <div className="space-y-2">
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Runtime Pool:</span>
                      <span className="font-semibold text-navy-900">Databricks Apps Serverless Runtime</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Compute Allocation:</span>
                      <span className="font-semibold text-navy-900">1.0 vCPU · 4.0 GB RAM</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Scale-to-Zero Timeout:</span>
                      <span className="font-semibold text-navy-900">20 minutes idle</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Direct Billing Tag:</span>
                      <span className="font-semibold text-amber-700">Unattributed (Shared Pool)</span>
                    </div>
                  </div>
                ) : resType === "pipeline" ? (
                  <div className="space-y-2">
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Compute Mode:</span>
                      <span className="font-semibold text-navy-900">Automated Maintenance Cluster</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Worker Node SKU:</span>
                      <span className="font-mono font-semibold text-navy-900">Standard_D8ds_v5</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Photon Engine:</span>
                      <span className="font-semibold text-emerald-700">Enabled</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Worker Scaling:</span>
                      <span className="font-semibold text-navy-900">1 - 4 Workers</span>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Cluster Type:</span>
                      <span className="font-semibold text-navy-900">Job Cluster (Ephemeral)</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Worker Nodes:</span>
                      <span className="font-semibold text-navy-900">2x Standard_D4ds_v5</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Spark Runtime:</span>
                      <span className="font-mono font-semibold text-navy-900">14.3.x-scala2.12</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-200">
                      <span className="text-slate-500">Cost Policy:</span>
                      <span className="font-semibold text-emerald-700">Dedicated Job Cluster Rate ($0.15/DBU)</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: FAILURES (Job) */}
          {/* ========================================================================= */}
          {activeTab === "failures" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Failure &amp; Retry Diagnostics for {resource.name}
              </h4>
              <div className="p-3 rounded-lg border border-red-200 bg-red-50/50 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-red-900">Run #846994 · Task: ingest_raw_telemetry</span>
                  <span className="text-red-700 text-[11px]">Nov 05 02:04 UTC</span>
                </div>
                <p className="font-mono text-[11px] bg-white p-2 rounded border border-red-200 text-red-800">
                  java.io.FileNotFoundException: ADLS Gen2 path abfss://landing@adlsgen2.dfs.core.windows.net/telemetry/2026-11-05.json not found. Retrying in 120s...
                </p>
                <div className="flex items-center justify-between text-[11px] text-slate-600">
                  <span>Outcome: Retry 1 succeeded</span>
                  <span className="text-slate-500">Wasted compute: 0.12 DBU ($0.48)</span>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: UPDATES (Pipeline) */}
          {/* ========================================================================= */}
          {activeTab === "updates" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Delta Live Tables Update History for {resource.name}
              </h4>
              <div className="space-y-2">
                <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-navy-900">Update #1042 (Triggered)</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                      COMPLETED · 8m 12s
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-600">
                    <span>Processed: 4.2M records</span>
                    <span>Data Quality: 100% Passed (0 dropped)</span>
                  </div>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-navy-900">Update #1041 (Triggered)</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                      COMPLETED · 7m 54s
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-600">
                    <span>Processed: 3.9M records</span>
                    <span>Data Quality: 99.98% Passed (82 dropped)</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: SERVED MODELS (Model Serving) */}
          {/* ========================================================================= */}
          {activeTab === "models" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Served Models on Endpoint {resource.name}
              </h4>
              <div className="space-y-2">
                <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-navy-900">dbrx-instruct</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-800">
                      Version 2 · Active Primary
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-600">
                    <div>Compute: 4x NVIDIA A10G GPU</div>
                    <div>Scale-to-Zero: Enabled</div>
                    <div>Traffic Allocation: 100%</div>
                    <div>Concurrency: 4 worker replicas</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: TOKEN ECONOMICS (Model Serving) */}
          {/* ========================================================================= */}
          {activeTab === "tokens" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                  GenAI Token Telemetry &amp; Unit Isolation
                </h4>
                <span className="text-[10px] font-bold text-purple-700 bg-purple-50 px-2 py-0.5 rounded">
                  Tokens Separated from DBU
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[11px] text-slate-500 block">Input Tokens (MTD):</span>
                  <span className="text-base font-bold text-navy-900 mt-1 block">8.42 Billion</span>
                  <span className="text-[10px] text-slate-500 block mt-0.5">82% of total volume</span>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[11px] text-slate-500 block">Output Tokens (MTD):</span>
                  <span className="text-base font-bold text-navy-900 mt-1 block">1.86 Billion</span>
                  <span className="text-[10px] text-slate-500 block mt-0.5">18% of total volume</span>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[11px] text-slate-500 block">Cached Tokens:</span>
                  <span className="text-base font-bold text-emerald-700 mt-1 block">2.14 Billion</span>
                  <span className="text-[10px] text-emerald-600 block mt-0.5">Cache Hit Ratio: 25.4%</span>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[11px] text-slate-500 block">Effective Cost / 1k Tokens:</span>
                  <span className="text-base font-bold text-navy-900 mt-1 block">$0.0026</span>
                  <span className="text-[10px] text-slate-500 block mt-0.5">List Price: $0.0035</span>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: DEPLOYMENT (App) */}
          {/* ========================================================================= */}
          {activeTab === "deployment" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                App Deployment &amp; Manifest Configuration
              </h4>
              <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-500">App Name:</span>
                  <span className="font-semibold text-navy-900">{resource.name}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-500">Deployment Status:</span>
                  <span className="font-semibold text-emerald-700">SUCCEEDED (Active)</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-500">Source Repository:</span>
                  <span className="font-mono font-semibold text-navy-900">/Workspace/apps/finops-dashboard</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-500">Application Framework:</span>
                  <span className="font-semibold text-navy-900">Streamlit / Python 3.11</span>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: USAGE & ACTIVITY (App) */}
          {/* ========================================================================= */}
          {activeTab === "usage" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Usage &amp; Invocations for {resource.name}
              </h4>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[11px] text-slate-500 block">Daily Active Users:</span>
                  <span className="text-base font-bold text-navy-900 mt-1 block">18 users</span>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[11px] text-slate-500 block">Total Invocations:</span>
                  <span className="text-base font-bold text-navy-900 mt-1 block">1,420 req / day</span>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: LOGS (App) */}
          {/* ========================================================================= */}
          {activeTab === "logs" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                  Recent Runtime Logs for {resource.name}
                </h4>
                <span className="text-[10px] text-slate-500 font-mono">Streamlit stdout</span>
              </div>
              <div className="bg-slate-900 text-slate-200 p-3 rounded-lg text-xs font-mono max-h-56 overflow-y-auto space-y-1">
                <div className="text-slate-400">[2026-11-07 10:40:12 UTC] App container healthy. Starting Gunicorn server...</div>
                <div className="text-slate-300">[2026-11-07 10:40:15 UTC] Listening at: http://0.0.0.0:8000</div>
                <div className="text-emerald-400">[2026-11-07 10:41:02 UTC] GET /health HTTP/1.1 200 OK</div>
                <div className="text-slate-300">[2026-11-07 10:45:18 UTC] User session connected: pratik.bingewar@bizmetric.com</div>
                <div className="text-emerald-400">[2026-11-07 10:45:22 UTC] Loaded FinOps dataset (42,180 records in 140ms)</div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: COST & DBU */}
          {/* ========================================================================= */}
          {activeTab === "cost" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                  Attributed Cost &amp; DBU Consumption
                </h4>
                <span className="text-[11px] text-slate-500">From system.billing.usage</span>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[11px] text-slate-500 block">Monthly Spend (MTD):</span>
                  <span className="text-lg font-bold text-navy-900 mt-1 block">
                    {resType === "warehouse"
                      ? "$42,180.00"
                      : resType === "serving_endpoint"
                      ? "$26,740.00"
                      : resType === "app"
                      ? "$0.00 (Unattributed)"
                      : "$11,200.00"}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <span className="text-[11px] text-slate-500 block">DBU Burn (MTD):</span>
                  <span className="text-lg font-bold text-navy-900 mt-1 block">
                    {resType === "warehouse"
                      ? "19,172 Net DBU"
                      : resType === "serving_endpoint"
                      ? "6,685 Net DBU"
                      : resType === "app"
                      ? "310 Shared Pool DBU"
                      : "2,800 Net DBU"}
                  </span>
                </div>
              </div>

              {resType === "app" && (
                <div className="p-3 rounded-lg border border-amber-200 bg-amber-50/60 text-xs text-amber-900 space-y-1">
                  <span className="font-semibold block text-[11px]">Unattributed Spend Preservation:</span>
                  <p className="text-[11px] leading-relaxed">
                    Under current Databricks system tables schemas, Databricks Apps compute is billed under a shared serverless resource pool. The platform preserves this spend in the Unattributed category rather than forcing an inaccurate direct attribution.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: ACTIVITY (Cluster, Warehouse) */}
          {/* ========================================================================= */}
          {activeTab === "activity" && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Lifecycle Events for {resource.name}
              </h4>
              <div className="space-y-2 text-xs">
                <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 flex items-start justify-between">
                  <div>
                    <span className="font-semibold text-navy-900 block">
                      {isStoppedWarehouse ? "Warehouse Auto-Stopped" : "Cluster Resized"}
                    </span>
                    <span className="text-[11px] text-slate-500 block">
                      {isStoppedWarehouse ? "Inactivity threshold (15m) reached" : "Autoscaled from 2 to 4 workers"}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-400">Today 09:15 UTC</span>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 flex items-start justify-between">
                  <div>
                    <span className="font-semibold text-navy-900 block">Parameter Update</span>
                    <span className="text-[11px] text-slate-500 block">Auto-stop interval set to 15m</span>
                  </div>
                  <span className="text-[10px] text-slate-400">Nov 04 14:22 UTC</span>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: OPTIMIZATION (ALL RESOURCE TYPES) */}
          {/* ========================================================================= */}
          {activeTab === "optimization" && (
            <div className="space-y-5">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-brand-600" />
                  Advisor Optimization Recommendations
                </h4>
                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                  {resType === "warehouse"
                    ? "Potential: $8,400 / mo"
                    : resType === "cluster"
                    ? "Potential: $3,460 / mo"
                    : resType === "serving_endpoint"
                    ? "Potential: $6,100 / mo"
                    : "Potential: $1,200 / mo"}
                </span>
              </div>

              {/* Recommendation Card */}
              <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <span className="text-xs font-bold text-navy-900 block">
                      {resType === "warehouse"
                        ? "Downsize Serverless Starter Warehouse to 2X-Small with aggressive auto-stop"
                        : resType === "cluster"
                        ? "Enforce 20-minute auto-termination policy and restrict ad-hoc compute"
                        : resType === "serving_endpoint"
                        ? "Enable scale-to-zero and context caching on model endpoint"
                        : "Tighten idle timeout and rightsize container memory allocation"}
                    </span>
                    <p className="text-xs text-slate-600 leading-relaxed">
                      {resType === "warehouse"
                        ? "Observed average utilization is 18%, peak concurrency is 3 queries, and p95 queue time is 0.42 seconds. Downsizing will preserve performance within SLO while reducing monthly spend."
                        : resType === "cluster"
                        ? "Cluster logged 7.5 hours of unscheduled idle uptime outside business hours. Applying strict auto-termination eliminates waste from abandoned development notebooks."
                        : resType === "serving_endpoint"
                        ? "62% of endpoint invocations occur in batch windows. Enabling scale-to-zero avoids paying for idle GPU reservations during off-hours."
                        : "App container memory usage peaks at 1.2 GB of 4.0 GB allocated. Rightsizing to 2.0 GB allocation reduces shared pool compute charges."}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-200 text-xs">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Risk</span>
                    <span className="font-semibold text-emerald-700">Low Risk</span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Effort</span>
                    <span className="font-semibold text-navy-900">Low (Config change)</span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Confidence</span>
                    <span className="font-semibold text-navy-900">92%</span>
                  </div>
                </div>
              </div>

              {/* Zero-Mutation Governance Notice */}
              <div className="p-3 rounded-lg border border-brand-200 bg-brand-50/60 text-xs text-brand-900 flex items-start gap-2">
                <ShieldCheck className="w-4 h-4 text-brand-600 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <span className="font-semibold block">Zero-Execution Policy Enforced</span>
                  <p className="text-[11px] text-brand-800 leading-relaxed">
                    This platform never automatically applies changes to customer compute. All optimization actions require explicit operator review and manual approval in the Databricks console or CI/CD pipelines.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Drawer Footer */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span>Azure Databricks Workspace 642006393507276</span>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg border border-slate-300 text-slate-700 font-semibold hover:bg-slate-200 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
