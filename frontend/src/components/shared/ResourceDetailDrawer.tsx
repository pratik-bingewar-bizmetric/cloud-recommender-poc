"use client";

import React from "react";
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
  Target,
  Info,
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

const ICONS: Record<string, React.ReactNode> = {
  warehouse: <Database className="w-5 h-5 text-sky-600" />,
  cluster: <Cpu className="w-5 h-5 text-blue-600" />,
  job: <Workflow className="w-5 h-5 text-emerald-600" />,
  pipeline: <Layers className="w-5 h-5 text-indigo-600" />,
  serving_endpoint: <Sparkles className="w-5 h-5 text-purple-600" />,
  app: <Server className="w-5 h-5 text-orange-600" />,
};

const formatValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "n/a";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

/**
 * Resource drill-down. Shows only what the Databricks APIs returned for the resource
 * (identity, state, creator, configuration). Utilization, cost and query telemetry are
 * intentionally absent: they require system tables, which are not read without approval.
 */
export const ResourceDetailDrawer: React.FC<ResourceDetailDrawerProps> = ({
  isOpen,
  onClose,
  resource,
  onFocusScope,
  isFocused = false,
}) => {
  if (!isOpen || !resource) return null;

  const entries = Object.entries(resource.metadata || {}).filter(
    ([, v]) => v !== null && v !== undefined && v !== ""
  );

  const handleFocusClick = () => {
    onFocusScope?.({
      resource_type: resource.resource_type as ChildResourceScope["resource_type"],
      resource_id: resource.id,
      resource_name: resource.name,
      metadata: resource.metadata,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="fixed inset-0 bg-navy-950/40 backdrop-blur-xs transition-opacity" onClick={onClose} />
      <div
        className="relative w-full max-w-xl bg-white h-full shadow-2xl flex flex-col"
        role="dialog"
        aria-label={`${resource.name} details`}
      >
        <div className="p-5 border-b border-slate-200 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center shrink-0">
              {ICONS[resource.resource_type] ?? <FolderTree className="w-5 h-5 text-slate-600" />}
            </div>
            <div className="min-w-0">
              <h3 className="text-base font-bold text-navy-900 truncate">{resource.name}</h3>
              <div className="text-[11px] text-slate-500 font-mono truncate">{resource.id}</div>
              <div className="flex items-center gap-2 mt-1 text-[10px]">
                <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-bold uppercase">
                  {resource.resource_type.replace(/_/g, " ")}
                </span>
                {resource.status && (
                  <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 font-bold border border-emerald-200">
                    {resource.status}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {onFocusScope && (
              <button
                type="button"
                onClick={handleFocusClick}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
                  isFocused ? "bg-emerald-600 text-white" : "bg-brand-600 hover:bg-brand-700 text-white"
                }`}
              >
                <Target className="w-3.5 h-3.5" />
                {isFocused ? "Scope focused" : "Focus scope"}
              </button>
            )}
            <button type="button" onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100" aria-label="Close">
              <X className="w-4 h-4 text-slate-500" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs">
          <div>
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider mb-1">Identity</h4>
            {[
              ["Workspace", resource.workspace_id],
              ["Creator / owner", resource.creator],
              ["Source API", resource.source_api],
              ["Discovered at", resource.discovered_at ? formatDeterministicDateTime(new Date(resource.discovered_at)) : null],
            ].map(([label, value]) => (
              <div key={label as string} className="flex justify-between gap-4 py-2 border-b border-slate-100">
                <span className="text-slate-500">{label}</span>
                <span className="font-medium text-navy-900 text-right break-all">{formatValue(value)}</span>
              </div>
            ))}
          </div>

          <div>
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider mb-1">
              Live configuration ({entries.length})
            </h4>
            {entries.length === 0 ? (
              <div className="text-slate-500">The API returned no configuration fields for this resource.</div>
            ) : (
              entries.map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 py-2 border-b border-slate-100">
                  <span className="text-slate-500 font-mono">{k}</span>
                  <span className="font-medium text-navy-900 text-right break-all">{formatValue(v)}</span>
                </div>
              ))
            )}
          </div>

          <div className="p-3 rounded-xl border border-slate-200 bg-slate-50/80 flex items-start gap-2 text-slate-600">
            <Info className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
            <span>
              Cost, DBU, utilization and query telemetry are not shown here. They come from Databricks system
              tables (<code>system.billing</code>, <code>system.compute</code>, <code>system.query</code>), which are
              read only after explicit approval to run read-only SQL.
            </span>
          </div>
        </div>

        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span className="flex items-center gap-1.5 font-mono text-[11px]">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            Read-only metadata
          </span>
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-semibold transition">
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
